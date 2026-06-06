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
    assert payload["signals"][0]["code"] == "600519"
    assert payload["signals"][0]["signal_provider"] == "local_momentum"
    assert payload["signals"][0]["qlib_rank"] == 1


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
