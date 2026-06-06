"""可视化面板 API 测试"""
import pytest
from fastapi.testclient import TestClient

from dashboard.app import app
from dashboard.session import current_account
from data.storage.storage import DataStorage

client = TestClient(app)


class TestPages:
    def test_index(self):
        res = client.get("/")
        assert res.status_code == 200
        assert "AI 量化交易系统" in res.text

    def test_old_routes_removed(self):
        """旧的多页面路由应返回 404"""
        for path in ["/backtest", "/portfolio", "/risk"]:
            res = client.get(path)
            assert res.status_code == 404


class TestBacktestAPI:
    def test_list_strategies(self):
        res = client.get("/api/backtest/strategies")
        assert res.status_code == 200
        strategies = res.json()
        assert len(strategies) == 7
        names = [s["name"] for s in strategies]
        assert "dual_ma" in names
        assert "bollinger" in names
        assert "momentum" in names
        assert "rsi" in names
        assert "macd" in names
        assert "kdj" in names
        assert "qlib_signal" in names

    def test_search_stocks(self):
        res = client.get("/api/backtest/stocks")
        assert res.status_code == 200

    def test_run_backtest_invalid_strategy(self):
        res = client.post("/api/backtest/run", json={
            "strategy": "nonexistent",
            "codes": ["000001"],
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
        })
        assert res.status_code == 422

    def test_run_backtest_no_data(self):
        """无数据时回测应返回空结果"""
        res = client.post("/api/backtest/run", json={
            "strategy": "dual_ma",
            "codes": ["999999"],
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["total_return"] == 0


class TestPortfolioAPI:
    def test_snapshot_no_data(self):
        res = client.get("/api/portfolio/snapshot")
        assert res.status_code == 200
        data = res.json()
        assert data["cash"] == 50000.0
        assert data["positions"] == []

    def test_trades_no_data(self):
        res = client.get("/api/portfolio/trades")
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_risk_no_data(self):
        res = client.get("/api/portfolio/risk")
        assert res.status_code == 200


class TestSystemAPI:
    def test_system_status(self):
        res = client.get("/api/system/status")
        assert res.status_code == 200
        data = res.json()
        assert "db_stats" in data
        assert "paper_running" in data
        assert "ai_model" in data

    def test_system_strategies(self):
        res = client.get("/api/system/strategies")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 7
        for s in data:
            assert "name" in s
            assert "label" in s
            assert "description" in s
            assert "params" in s

    def test_risk_rules(self):
        res = client.get("/api/system/risk/rules")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 6
        for rule in data:
            assert "name" in rule
            assert "threshold" in rule
            assert "status" in rule


class TestValuationDataHubAPI:
    def test_decision_score_does_not_flag_ai_uncovered_when_qlib_rank_exists(self):
        from dashboard.routers.datahub import _score_decision

        decision = _score_decision(
            {
                "peg_next_year": 1.2,
                "growth_next_year_pct": 20,
                "report_count": 3,
            },
            {
                "qlib_rank": 8,
                "qlib_score": 0.76,
                "qlib_diamond": False,
            },
        )

        assert "AI未覆盖" not in decision["risk_tags"]
        assert "AI候选" in decision["reason_tags"]
        assert "AI未验证" in decision["risk_tags"]
        assert decision["decision_score"] >= 60

    def test_signal_validation_quality_summary_explains_unverified_penalty(self):
        from dashboard.routers.datahub import _signal_validation_quality

        quality = _signal_validation_quality({
            "confidence": "unverified",
            "sample_days": 0,
            "metrics": {},
        })

        assert quality["label"] == "未验证"
        assert quality["sample_days"] == 0
        assert quality["penalty_applied"] is True
        assert "降权" in quality["message"]

        positive = _signal_validation_quality({
            "confidence": "validated_positive",
            "sample_days": 42,
            "metrics": {"1d": {"top_excess_return_pct": 1.23, "hit_rate_pct": 58.6, "rank_ic": 0.071}},
        })

        assert positive["label"] == "验证偏正"
        assert positive["sample_days"] == 42
        assert positive["penalty_applied"] is False
        assert positive["top_excess_return_pct"] == 1.23

    def test_load_qlib_context_keeps_full_items_when_ordered_codes_are_limited(self, monkeypatch):
        from dashboard.routers import datahub

        monkeypatch.setattr(
            "dashboard.routers.qlib._load_predictions",
            lambda: {
                "2026-06-04": {"600519": 0.7, "000001": 0.6, "002475": 0.5},
                "2026-06-05": {"600519": 0.9, "000001": 0.8, "002475": 0.7},
            },
        )

        ctx = datahub._load_qlib_context(top_limit=1)

        assert ctx["total"] == 3
        assert ctx["ordered_codes"] == ["600519"]
        assert ctx["items"]["002475"]["qlib_rank"] == 3
        assert ctx["items"]["002475"]["qlib_score"] == 0.7

    def test_stock_detail_includes_source_provenance(self, monkeypatch):
        from data.collector import quote_service
        from data.collector.quote_service import QuoteData

        class FakeQuoteService:
            def get_quote(self, code):
                return QuoteData(
                    code=code,
                    name="平安银行",
                    price=10.0,
                    open=9.9,
                    high=10.2,
                    low=9.8,
                    pre_close=9.9,
                    volume=1000,
                    amount=10000,
                    change_pct=1.01,
                    timestamp=1.0,
                )

            def get_financial_data(self, code):
                return None

        monkeypatch.setattr(quote_service, "get_quote_service", lambda: FakeQuoteService())
        monkeypatch.setattr("dashboard.routers.stock_detail.DATA_SOURCE_MODE", "new", raising=False)
        monkeypatch.setattr("dashboard.routers.stock_detail.now_beijing_iso", lambda: "2026-05-24T12:00:00+08:00", raising=False)

        res = client.get("/api/stock/detail/000001")

        assert res.status_code == 200
        data = res.json()
        assert data["source"] == "astock"
        assert data["source_version"]
        assert data["updated_at"] == "2026-05-24T12:00:00+08:00"

    def test_valuation_health_endpoint_exposes_source_health(self):
        res = client.get("/api/valuation/health")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "source_health" in data
        assert "quality_summary" in data
        assert "shadow" in data
        assert "coverage" in data

    def test_valuation_service_builds_local_prediction_when_reports_missing(self, monkeypatch):
        import pandas as pd

        from data.services.valuation_service import ValuationService

        class FakeStorage:
            def get_stock_list(self):
                return pd.DataFrame([{"code": "000001", "name": "平安银行", "industry": "银行"}])

            def get_stock_daily(self, code):
                return pd.DataFrame(
                    [
                        {
                            "date": pd.Timestamp("2026-04-01") + pd.Timedelta(days=i),
                            "open": 10 + i * 0.02,
                            "high": 10.2 + i * 0.02,
                            "low": 9.9 + i * 0.02,
                            "close": 10 + i * 0.03,
                            "volume": 1000 + i,
                            "amount": 100000 + i,
                        }
                        for i in range(70)
                    ]
                )

            def save_data_source_version(self, *args, **kwargs):
                return 1

            def save_data_snapshot(self, *args, **kwargs):
                return 1

            def get_latest_data_snapshot(self, *args, **kwargs):
                return None

        class EmptyAdapter:
            SOURCE_NAME = "astock"
            SOURCE_VERSION = "empty"

            def get_valuation_snapshot(self, code, report_limit=8):
                return {"code": code, "stock_name": "", "report_count": 0, "reports": []}

        monkeypatch.setattr("data.services.valuation_service.ValuationService._load_qlib_signal", lambda self, code: {"qlib_rank": 1, "qlib_score": 0.9})

        service = ValuationService(storage=FakeStorage())
        service.adapter = EmptyAdapter()
        snapshot = service.build_snapshot("000001", report_limit=3)

        assert snapshot["source"] == "local_derived"
        assert snapshot["source_version"] == "stock_daily+signal+momentum"
        assert snapshot["report_count"] == 1
        assert snapshot["report_source"] == "local_derived"
        assert snapshot["reports"][0]["source_note"]

    def test_datahub_health_includes_quality_summary(self):
        res = client.get("/api/datahub/health")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "source_health" in data
        assert "quality_summary" in data
        assert "shadow" in data
        assert "valuation" in data
        assert "quote" in data
        assert "temporary_subscriptions" in data["quote"]
        assert "stock_daily" in data
        assert "daily_covered" in data["stock_daily"]
        assert "full_daily_sync" in data

    def test_datahub_decision_matrix_includes_snapshot_metadata(self, monkeypatch):
        storage = DataStorage()
        storage.save_data_snapshot(
            "000001",
            "valuation",
            "astock",
            "v-test",
            {"peg_next_year": 0.88},
            quality_status="warn",
        )
        monkeypatch.setattr("dashboard.routers.datahub.DataStorage", lambda: storage)
        monkeypatch.setattr("dashboard.routers.datahub._load_qlib_context", lambda top_limit=300: {"latest_date": None, "total": 0, "items": {}, "ordered_codes": []})
        app.dependency_overrides[current_account] = lambda: {"workspace": {"id": "test-workspace"}}

        try:
            res = client.get("/api/datahub/decision-matrix?scope=codes&codes=000001&limit=1&fast=true")
        finally:
            app.dependency_overrides.pop(current_account, None)

        assert res.status_code == 200
        item = res.json()["items"][0]
        assert item["source"] == "astock"
        assert item["source_version"] == "v-test"
        assert item["quality_status"] == "warn"
        assert item["snapshot_at"]

    def test_datahub_decision_matrix_uses_full_qlib_items_beyond_display_top(self, monkeypatch):
        storage = DataStorage()
        monkeypatch.setattr("dashboard.routers.datahub.DataStorage", lambda: storage)
        monkeypatch.setattr("dashboard.routers.datahub._load_qlib_context", lambda top_limit=None: {
            "latest_date": "2026-06-05",
            "total": 3,
            "items": {
                "600519": {"qlib_rank": 1, "qlib_score": 0.91},
                "000001": {"qlib_rank": 2, "qlib_score": 0.82},
                "002475": {"qlib_rank": 3, "qlib_score": 0.73},
            },
            "ordered_codes": ["600519"],
        })
        app.dependency_overrides[current_account] = lambda: {"workspace": {"id": "test-workspace"}}

        try:
            res = client.get("/api/datahub/decision-matrix?scope=codes&codes=002475&limit=1&fast=true")
        finally:
            app.dependency_overrides.pop(current_account, None)

        assert res.status_code == 200
        item = res.json()["items"][0]
        assert item["code"] == "002475"
        assert item["qlib_rank"] == 3
        assert item["qlib_score"] == 0.73
        assert "AI未覆盖" not in item["risk_tags"]

    def test_datahub_decision_matrix_summary_includes_ledger_health(self, monkeypatch):
        storage = DataStorage()
        monkeypatch.setattr("dashboard.routers.datahub.DataStorage", lambda: storage)
        monkeypatch.setattr("dashboard.routers.datahub._load_qlib_context", lambda top_limit=300: {"latest_date": None, "total": 0, "items": {}, "ordered_codes": []})
        app.dependency_overrides[current_account] = lambda: {"workspace": {"id": "test-workspace"}}

        try:
            res = client.get("/api/datahub/decision-matrix?scope=codes&codes=000001&limit=1&fast=true")
        finally:
            app.dependency_overrides.pop(current_account, None)

        assert res.status_code == 200
        summary = res.json()["summary"]
        assert "source_health" in summary
        assert "quality_summary" in summary
        assert "shadow" in summary

    def test_datahub_decision_matrix_force_fallback_uses_default_candidates(self, monkeypatch):
        storage = DataStorage()
        monkeypatch.setattr("dashboard.routers.datahub.DataStorage", lambda: storage)
        monkeypatch.setattr(storage, "get_watchlist", lambda workspace_id: ["000001"])
        monkeypatch.setattr("dashboard.routers.datahub._fallback_seed_codes", lambda storage, limit: ["600519"][:limit])
        monkeypatch.setattr("dashboard.routers.datahub._load_qlib_context", lambda top_limit=300: {"latest_date": None, "total": 0, "items": {}, "ordered_codes": []})
        app.dependency_overrides[current_account] = lambda: {"workspace": {"id": "test-workspace"}}

        try:
            res = client.get("/api/datahub/decision-matrix?scope=watchlist&limit=3&fast=true&force_fallback=true")
        finally:
            app.dependency_overrides.pop(current_account, None)

        assert res.status_code == 200
        data = res.json()
        assert data["items"]
        assert [item["code"] for item in data["items"]] == ["600519"]
        assert data["summary"]["used_fallback"] is True
        assert data["summary"]["fallback_reason"] == "forced_default"

    def test_datahub_decision_matrix_refreshes_stale_quote_cache(self, monkeypatch):
        storage = DataStorage()
        calls = []

        class Quote:
            def __init__(self, price, timestamp):
                self.code = "000001"
                self.name = "平安银行"
                self.price = price
                self.open = price
                self.high = price
                self.low = price
                self.pre_close = price
                self.volume = 1000
                self.amount = 10000
                self.change_pct = 1.0
                self.timestamp = timestamp
                self.industry = "银行"
                self.turnover_rate = 1.2
                self.volume_ratio = 1.1

        class FakeQuoteService:
            def get_or_fetch_quote(self, code, max_age_sec=None):
                calls.append((code, max_age_sec))
                return Quote(price=11.0, timestamp=2000.0)

        monkeypatch.setattr("dashboard.routers.datahub.DataStorage", lambda: storage)
        monkeypatch.setattr("dashboard.routers.datahub._load_qlib_context", lambda top_limit=300: {"latest_date": None, "total": 0, "items": {}, "ordered_codes": []})
        monkeypatch.setattr("dashboard.routers.datahub.time.time", lambda: 2000.0)
        monkeypatch.setattr("data.collector.quote_service.get_quote_service", lambda: FakeQuoteService())
        app.dependency_overrides[current_account] = lambda: {"workspace": {"id": "test-workspace"}}

        try:
            res = client.get("/api/datahub/decision-matrix?scope=codes&codes=000001&limit=1&fast=true")
        finally:
            app.dependency_overrides.pop(current_account, None)

        assert res.status_code == 200
        item = res.json()["items"][0]
        assert calls == [("000001", 900)]
        assert item["price"] == 11.0
        assert item["quote_age_sec"] == 0.0
        assert "行情缓存偏旧" not in item["risk_tags"]

    def test_datahub_decision_matrix_refreshes_quotes_in_one_batch(self, monkeypatch):
        storage = DataStorage()
        calls = []

        class Quote:
            def __init__(self, code, price, timestamp):
                self.code = code
                self.name = code
                self.price = price
                self.open = price
                self.high = price
                self.low = price
                self.pre_close = price
                self.volume = 1000
                self.amount = 10000
                self.change_pct = 1.0
                self.timestamp = timestamp
                self.industry = ""
                self.turnover_rate = 1.2
                self.volume_ratio = 1.1

        class FakeQuoteService:
            def get_or_fetch_quotes(self, codes, max_age_sec=None, refresh_timeout_sec=None):
                calls.append((list(codes), max_age_sec, refresh_timeout_sec))
                return {
                    "000001": Quote("000001", 11.0, 2000.0),
                    "600519": Quote("600519", 1500.0, 2000.0),
                }

        monkeypatch.setattr("dashboard.routers.datahub.DataStorage", lambda: storage)
        monkeypatch.setattr("dashboard.routers.datahub._load_qlib_context", lambda top_limit=300: {"latest_date": None, "total": 0, "items": {}, "ordered_codes": []})
        monkeypatch.setattr("dashboard.routers.datahub.time.time", lambda: 2000.0)
        monkeypatch.setattr("data.collector.quote_service.get_quote_service", lambda: FakeQuoteService())
        app.dependency_overrides[current_account] = lambda: {"workspace": {"id": "test-workspace"}}

        try:
            res = client.get("/api/datahub/decision-matrix?scope=codes&codes=000001,600519&limit=2&fast=true")
        finally:
            app.dependency_overrides.pop(current_account, None)

        assert res.status_code == 200
        assert calls == [(["000001", "600519"], 900, 2.0)]
        items = {item["code"]: item for item in res.json()["items"]}
        assert items["000001"]["quote_age_sec"] == 0.0
        assert items["600519"]["quote_age_sec"] == 0.0

    def test_datahub_decision_matrix_uses_short_quote_refresh_budget(self, monkeypatch):
        storage = DataStorage()
        calls = []

        class FakeQuoteService:
            def get_or_fetch_quotes(self, codes, max_age_sec=None, refresh_timeout_sec=None):
                calls.append((list(codes), max_age_sec, refresh_timeout_sec))
                return {}

        monkeypatch.setattr("dashboard.routers.datahub.DataStorage", lambda: storage)
        monkeypatch.setattr("dashboard.routers.datahub._load_qlib_context", lambda top_limit=300: {"latest_date": None, "total": 0, "items": {}, "ordered_codes": []})
        monkeypatch.setattr("data.collector.quote_service.get_quote_service", lambda: FakeQuoteService())
        app.dependency_overrides[current_account] = lambda: {"workspace": {"id": "test-workspace"}}

        try:
            res = client.get("/api/datahub/decision-matrix?scope=codes&codes=000001,600519&limit=2&fast=true")
        finally:
            app.dependency_overrides.pop(current_account, None)

        assert res.status_code == 200
        assert calls == [(["000001", "600519"], 900, 2.0)]

    def test_datahub_decision_matrix_adds_candidates_to_temporary_quote_pool(self, monkeypatch):
        storage = DataStorage()
        temporary_calls = []

        class FakeQuoteService:
            def add_temporary_subscriptions(self, codes, ttl_sec=None):
                temporary_calls.append((list(codes), ttl_sec))

            def get_or_fetch_quotes(self, codes, max_age_sec=None, refresh_timeout_sec=None):
                return {}

        monkeypatch.setattr("dashboard.routers.datahub.DataStorage", lambda: storage)
        monkeypatch.setattr("dashboard.routers.datahub._load_qlib_context", lambda top_limit=300: {"latest_date": None, "total": 0, "items": {}, "ordered_codes": []})
        monkeypatch.setattr("data.collector.quote_service.get_quote_service", lambda: FakeQuoteService())
        app.dependency_overrides[current_account] = lambda: {"workspace": {"id": "test-workspace"}}

        try:
            res = client.get("/api/datahub/decision-matrix?scope=codes&codes=000001,600519&limit=2&fast=true")
        finally:
            app.dependency_overrides.pop(current_account, None)

        assert res.status_code == 200
        assert temporary_calls == [(["000001", "600519"], 1800)]

    def test_datahub_decision_matrix_uses_local_quotes_when_quote_service_stopped(self, monkeypatch):
        storage = DataStorage()

        class FakeQuoteService:
            is_running = False

            def get_or_fetch_quotes(self, *args, **kwargs):
                raise AssertionError("stopped quote service should not fetch live quotes")

            def get_quote(self, code):
                return None

        monkeypatch.setattr("dashboard.routers.datahub.DataStorage", lambda: storage)
        monkeypatch.setattr(
            storage,
            "get_latest_market_rows",
            lambda: [
                {
                    "code": "000001",
                    "date": "2026-06-05",
                    "close": 11.0,
                    "prev_close": 10.0,
                    "high": 11.2,
                    "low": 10.8,
                    "amount": 100000,
                    "volume": 1000,
                }
            ],
        )
        monkeypatch.setattr(
            storage,
            "get_latest_market_rows_for_codes",
            lambda codes: [
                {
                    "code": "000001",
                    "date": "2026-06-05",
                    "close": 11.0,
                    "prev_close": 10.0,
                    "high": 11.2,
                    "low": 10.8,
                    "amount": 100000,
                    "volume": 1000,
                }
            ],
        )
        monkeypatch.setattr("dashboard.routers.datahub._load_qlib_context", lambda top_limit=300: {"latest_date": None, "total": 0, "items": {}, "ordered_codes": []})
        monkeypatch.setattr("data.collector.quote_service.get_quote_service", lambda: FakeQuoteService())
        app.dependency_overrides[current_account] = lambda: {"workspace": {"id": "test-workspace"}}

        try:
            res = client.get("/api/datahub/decision-matrix?scope=codes&codes=000001&limit=1&fast=true")
        finally:
            app.dependency_overrides.pop(current_account, None)

        assert res.status_code == 200
        item = res.json()["items"][0]
        assert item["price"] == 11.0
        assert item["change_pct"] == 10.0
        assert item["quote_source"] == "local_stock_daily"
