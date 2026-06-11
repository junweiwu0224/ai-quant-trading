import pandas as pd


def test_signal_top_api_returns_unified_rows(client, monkeypatch, tmp_path):
    from dashboard.routers import signals as signal_router

    cache_path = tmp_path / "predictions_cache.json"
    cache_path.write_text(
        '{"method":"local_momentum_v1","predictions":{"2026-05-22":{"600519":0.81,"000001":0.62}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(signal_router, "QLIB_PRED_CACHE", cache_path)
    monkeypatch.setattr(
        signal_router,
        "_enrich_with_stock_info",
        lambda codes: {
            "600519": {"name": "贵州茅台", "industry": "白酒", "price": 1688.0},
            "000001": {"name": "平安银行", "industry": "银行", "price": 10.5},
        },
    )

    resp = client.get("/api/signals/top?limit=1")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    assert payload["provider"] == "local_momentum"
    assert payload["model_version"] == "local_momentum_v1"
    assert payload["date"] == "2026-05-22"
    assert payload["total"] == 2
    assert payload["primary_collection"] == "signals"
    assert payload["legacy_aliases"]["predictions"] == "signals"
    assert payload["runtime_boundary"] == "signals"
    assert payload["raw_source_role"] == "legacy_cache"
    assert payload["predictions"] == payload["signals"]
    assert payload["signals"][0]["code"] == "600519"
    assert payload["signals"][0]["signal_provider"] == "local_momentum"
    assert payload["signals"][0]["qlib_rank"] == 1


def test_signal_top_api_uses_valuation_snapshot_as_industry_fallback(client, monkeypatch, tmp_path):
    from data.storage.storage import DataStorage
    from dashboard.routers import qlib as qlib_router
    from dashboard.routers import signals as signal_router

    db_path = tmp_path / "quant.db"
    storage = DataStorage(db_url=f"sqlite:///{db_path}")
    storage.save_stock_info(pd.DataFrame([{"code": "sh600396", "name": "华电辽能", "industry": ""}]))
    storage.save_data_snapshot(
        "600396",
        "valuation",
        "local_derived",
        "v1",
        {
            "name": "华电辽能",
            "industry": "电力、热力、燃气及水生产和供应业-电力、热力生产和供应业",
            "sector": "电力",
        },
    )

    cache_path = tmp_path / "predictions_cache.json"
    cache_path.write_text(
        '{"method":"local_momentum_v1","predictions":{"2026-05-22":{"600396":0.81}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(signal_router, "QLIB_PRED_CACHE", cache_path)
    monkeypatch.setattr(qlib_router, "DB_PATH", db_path)

    resp = client.get("/api/signals/top?limit=1")

    assert resp.status_code == 200
    payload = resp.json()
    signal = payload["signals"][0]
    assert signal["name"] == "华电辽能"
    assert signal["industry"] == "电力、热力、燃气及水生产和供应业-电力、热力生产和供应业"
    assert signal["sector"] == "电力"
    assert signal["industry_source"] == "valuation_snapshot"


def test_signal_health_fast_mode_returns_light_validation_evidence(client, monkeypatch, tmp_path):
    from dashboard.routers import signals as signal_router

    cache_path = tmp_path / "predictions_cache.json"
    cache_path.write_text(
        '{"method":"local_momentum_v1","predictions":{"2026-05-22":{"600519":0.81,"000001":0.62}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(signal_router, "QLIB_PRED_CACHE", cache_path)

    def fail_validation(*args, **kwargs):
        raise AssertionError("fast signal health must not run full historical validation")

    monkeypatch.setattr(signal_router, "validate_signal_provider", fail_validation)

    resp = client.get("/api/signals/health?fast=true")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    assert payload["fast_mode"] is True
    assert payload["validation"]["confidence"] == "unverified"
    assert payload["validation"]["sample_days"] == 0
    assert payload["validation"]["provider"] == "local_momentum"
    assert payload["validation"]["penalty_applied"] is True


def test_qlib_top_api_is_legacy_signal_adapter(client, monkeypatch, tmp_path):
    from dashboard.routers import qlib as qlib_router

    cache_path = tmp_path / "predictions_cache.json"
    cache_path.write_text(
        '{"method":"local_momentum_v1","predictions":{"2026-05-22":{"600519":0.81,"000001":0.62}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(qlib_router, "PRED_CACHE_FILE", cache_path)
    monkeypatch.setattr(
        qlib_router,
        "_enrich_with_stock_info",
        lambda codes: {
            "600519": {"name": "贵州茅台", "industry": "白酒", "price": 1688.0},
        },
    )

    resp = client.get("/api/qlib/top?top_n=1")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    assert payload["legacy"] is True
    assert payload["provider"] == "local_momentum"
    assert payload["model_version"] == "local_momentum_v1"
    assert payload["predictions"][0]["code"] == "600519"
    assert payload["predictions"][0]["signal_provider"] == "local_momentum"


def test_signal_train_routes_are_primary_aliases(client, monkeypatch):
    from dashboard.routers import qlib as qlib_router

    called_urls = []

    class MockResponse:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url):
            called_urls.append(url)
            return MockResponse({"success": True, "message": "started"})

        async def get(self, url):
            called_urls.append(url)
            return MockResponse({"training": False})

    monkeypatch.setattr(qlib_router.httpx, "AsyncClient", MockAsyncClient)

    train_resp = client.post("/api/signals/train")
    status_resp = client.get("/api/signals/train/status")

    assert train_resp.status_code == 200
    assert status_resp.status_code == 200
    assert train_resp.json() == {
        "success": True,
        "message": "started",
        "primary_action": "refresh_signals",
        "legacy_adapter": "/api/qlib/train",
        "adapter_for": "signals",
    }
    assert status_resp.json() == {
        "training": False,
        "primary_action": "refresh_signals_status",
        "legacy_adapter": "/api/qlib/train/status",
        "adapter_for": "signals",
    }
    assert called_urls == [qlib_router.QLIB_TRAIN_URL, qlib_router.QLIB_TRAIN_STATUS_URL]


def test_signal_consistency_api_is_primary_alias(client, monkeypatch, tmp_path):
    from dashboard.routers import qlib as qlib_router

    cache_path = tmp_path / "predictions_cache.json"
    cache_path.write_text(
        """
        {
          "predictions": {
            "2026-05-19": {"600519": 0.30, "000001": 0.20},
            "2026-05-20": {"600519": 0.40, "000001": 0.30},
            "2026-05-21": {"600519": 0.50, "000001": 0.40},
            "2026-05-22": {"600519": 0.90, "000001": 0.70}
          }
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(qlib_router, "PRED_CACHE_FILE", cache_path)
    monkeypatch.setattr(
        qlib_router,
        "_enrich_with_stock_info",
        lambda codes: {
            "600519": {"name": "贵州茅台", "industry": "白酒", "price": 1688.0},
            "000001": {"name": "平安银行", "industry": "银行", "price": 10.5},
        },
    )

    resp = client.get("/api/signals/consistency?top_n=1")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    assert payload["provider"] == "local_momentum"
    assert payload["raw_source"] == "legacy_qlib"
    assert payload["date"] == "2026-05-22"
    assert payload["items"][0]["code"] == "600519"
    assert payload["items"][0]["name"] == "贵州茅台"
    assert payload["items"][0]["appearances"] == 3
    assert payload["items"][0]["ic_adj"] > 0
    assert payload["items"][0]["signal_provider"] == "local_momentum"
