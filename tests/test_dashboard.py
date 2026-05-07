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

    def test_backtest_page(self):
        res = client.get("/backtest")
        assert res.status_code == 200
        assert "回测报告" in res.text

    def test_portfolio_page(self):
        res = client.get("/portfolio")
        assert res.status_code == 200
        assert "持仓监控" in res.text

    def test_risk_page(self):
        res = client.get("/risk")
        assert res.status_code == 200
        assert "风控面板" in res.text


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
