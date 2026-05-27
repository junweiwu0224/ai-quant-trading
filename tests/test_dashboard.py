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
        assert "AI前10" in decision["reason_tags"]
        assert decision["decision_score"] >= 70

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
