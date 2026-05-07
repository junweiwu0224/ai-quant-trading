"""可视化面板 API 测试"""
import pytest
from fastapi.testclient import TestClient

from dashboard.app import app

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
        assert len(strategies) == 3
        names = [s["name"] for s in strategies]
        assert "dual_ma" in names
        assert "bollinger" in names
        assert "momentum" in names

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
        assert res.status_code == 200
        data = res.json()
        assert data["total_trades"] == 0

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
        assert data["cash"] == 0
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
        assert len(data) == 3
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
