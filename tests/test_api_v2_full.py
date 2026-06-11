"""Phase 2: 全量 API 自动化测试

使用 FastAPI TestClient（无需启动真实服务器），
按路由器分组覆盖所有核心端点。

运行方式:
    pytest tests/test_api_v2_full.py -v --tb=short
    pytest tests/test_api_v2_full.py -v --tb=short -x  # 首次失败即停
"""
import json
import sqlite3
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from dashboard.app import app
from dashboard.routers import qlib as qlib_router
from dashboard.session import current_account
from engine.migrate import init_database
from engine.models import Direction


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def legacy_paper_direction_db(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "paper_trading.db"
    init_database(str(db_path))

    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO paper_trades
        (trade_id, order_id, code, direction, price, volume, entry_price, profit, profit_pct,
         commission, stamp_tax, equity_after, strategy_name, signal_reason, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "T-LEGACY-1", "O-LEGACY-1", "000001", "long", 10.0, 100,
            9.5, 50.0, 0.05, 1.0, 0.0, 50050.0, None, None, "2026-05-13T10:00:00"
        ),
    )
    conn.execute(
        """INSERT INTO paper_equity_curve
        (timestamp, equity, cash, market_value, benchmark_value, drawdown, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("2026-05-12T15:00:00", 50000.0, 50000.0, 0.0, None, 0.0, "2026-05-12T15:00:00"),
    )
    conn.execute(
        """INSERT INTO paper_equity_curve
        (timestamp, equity, cash, market_value, benchmark_value, drawdown, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("2026-05-13T15:00:00", 50050.0, 49050.0, 1000.0, None, 0.0, "2026-05-13T15:00:00"),
    )
    conn.commit()
    conn.close()

    from dashboard.routers import paper_trading as paper_trading_router
    from engine.models import PaperConfig
    from engine.order_manager import OrderManager
    from engine.performance_analyzer import PerformanceAnalyzer
    from engine.risk_manager import RiskManager

    config = PaperConfig(db_path=str(db_path))
    monkeypatch.setattr(paper_trading_router, "_config", config)
    monkeypatch.setattr(paper_trading_router, "_order_manager", OrderManager(config.db_path))
    monkeypatch.setattr(paper_trading_router, "_performance_analyzer", PerformanceAnalyzer(config.db_path))
    monkeypatch.setattr(paper_trading_router, "_risk_manager", RiskManager(config, config.db_path))

    return db_path


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  基础健康检查
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestHealth:
    """系统健康与基础连通性"""

    def test_index_page(self, client):
        """GET / — 首页模板渲染"""
        resp = client.get("/")
        assert resp.status_code == 200

    def test_system_status(self, client):
        """GET /api/system/status — 系统状态"""
        resp = client.get("/api/system/status")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    def test_qlib_health(self, client):
        """GET /api/qlib/health — qlib 服务健康"""
        resp = client.get("/api/qlib/health")
        assert resp.status_code == 200


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  回测模块
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestBacktest:
    """回测相关端点"""

    def test_list_strategies(self, client):
        """GET /api/backtest/strategies — 策略列表"""
        resp = client.get("/api/backtest/strategies")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_search_stocks(self, client):
        """GET /api/backtest/stocks?q=茅台 — 股票搜索"""
        resp = client.get("/api/backtest/stocks", params={"q": "茅台"})
        assert resp.status_code == 200

    def test_list_benchmarks(self, client):
        """GET /api/backtest/benchmarks — 基准列表"""
        resp = client.get("/api/backtest/benchmarks")
        assert resp.status_code == 200

    def test_get_periods(self, client):
        """GET /api/backtest/periods — 回测区间"""
        resp = client.get("/api/backtest/periods")
        assert resp.status_code == 200

    def test_run_backtest_with_defaults(self, client):
        """POST /api/backtest/run — 空 body 使用默认参数"""
        resp = client.post("/api/backtest/run", json={})
        assert resp.status_code == 200

    def test_run_backtest_empty_codes(self, client):
        """POST /api/backtest/run — 空 codes 应返回 422"""
        resp = client.post("/api/backtest/run", json={"codes": []})
        assert resp.status_code == 422

    def test_run_backtest_invalid_strategy(self, client):
        """POST /api/backtest/run — 无效策略应返回 422"""
        resp = client.post("/api/backtest/run", json={"strategy": "nonexistent"})
        assert resp.status_code == 422


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  持仓与组合
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestPortfolio:
    """持仓相关端点"""

    def test_portfolio_snapshot(self, client):
        """GET /api/portfolio/snapshot — 组合快照"""
        resp = client.get("/api/portfolio/snapshot")
        assert resp.status_code == 200

    def test_portfolio_trades(self, client):
        """GET /api/portfolio/trades — 交易记录"""
        resp = client.get("/api/portfolio/trades")
        assert resp.status_code == 200

    def test_portfolio_risk(self, client):
        """GET /api/portfolio/risk — 风险指标"""
        resp = client.get("/api/portfolio/risk")
        assert resp.status_code == 200


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  模拟盘
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestPaperTrading:
    """模拟盘端点"""

    @pytest.mark.parametrize(
        ("raw_value", "expected"),
        [
            ("buy", Direction.LONG),
            ("long", Direction.LONG),
            ("sell", Direction.SHORT),
            ("short", Direction.SHORT),
        ],
    )
    def test_direction_from_value_accepts_current_and_legacy_values(self, raw_value, expected):
        assert Direction.from_value(raw_value) is expected

    def test_get_paper_status(self, client):
        """GET /api/paper/status — 模拟盘状态"""
        resp = client.get("/api/paper/status")
        assert resp.status_code == 200

    def test_get_orders(self, client):
        """GET /api/paper/orders — 订单列表"""
        resp = client.get("/api/paper/orders")
        assert resp.status_code == 200

    def test_get_positions(self, client):
        """GET /api/paper/positions — 持仓列表"""
        resp = client.get("/api/paper/positions")
        assert resp.status_code == 200

    def test_get_performance(self, client):
        """GET /api/paper/performance — 绩效指标"""
        resp = client.get("/api/paper/performance")
        assert resp.status_code == 200

    def test_get_performance_accepts_legacy_trade_direction(self, legacy_paper_direction_db):
        """GET /api/paper/performance — 兼容历史 long/short 方向值"""
        with TestClient(app) as client:
            resp = client.get("/api/paper/performance")

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        assert payload["data"]["total_trades"] == 1

    def test_get_trades_v2(self, client):
        """GET /api/paper/trades-v2 — 交易记录"""
        resp = client.get("/api/paper/trades-v2")
        assert resp.status_code == 200

    def test_get_risk_rules(self, client):
        """GET /api/paper/risk/rules — 风控规则"""
        resp = client.get("/api/paper/risk/rules")
        assert resp.status_code == 200

    def test_create_order_validation(self, client):
        """POST /api/paper/orders — 缺少必填字段应返回 422"""
        resp = client.post("/api/paper/orders", json={})
        assert resp.status_code in (400, 422)

    def test_cancel_nonexistent_order(self, client):
        """DELETE /api/paper/orders/FAKE-ID — 不存在的订单"""
        resp = client.delete("/api/paper/orders/FAKE-ID-99999")
        assert resp.status_code in (400, 404, 422)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  策略管理
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestStrategy:
    """策略管理端点"""

    def test_list_strategies(self, client):
        """GET /api/strategy/list — 策略列表"""
        resp = client.get("/api/strategy/list")
        assert resp.status_code == 200

    def test_strategy_version_list(self, client):
        """GET /api/strategy-version/versions/{name} — 策略版本"""
        resp = client.get("/api/strategy-version/versions/dual_ma")
        assert resp.status_code in (200, 404)

    def test_strategy_records(self, client):
        """GET /api/strategy-version/records — 回测记录"""
        resp = client.get("/api/strategy-version/records")
        assert resp.status_code == 200


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  自选股与行情
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestWatchlist:
    """自选股端点"""

    @pytest.fixture
    def watchlist_account(self):
        account = {
            "user": {"id": "watch-user", "username": "watch-user"},
            "workspace": {"id": "watch-workspace"},
            "permissions": {},
        }
        app.dependency_overrides[current_account] = lambda: account
        try:
            yield account
        finally:
            app.dependency_overrides.pop(current_account, None)

    def test_get_watchlist(self, client):
        """GET /api/watchlist — 自选股列表"""
        resp = client.get("/api/watchlist")
        assert resp.status_code == 401

    def test_get_watchlist_uses_current_workspace(self, client, monkeypatch, watchlist_account):
        """GET /api/watchlist — 当前工作区自选股列表"""
        from dashboard.routers import watchlist as watchlist_router

        calls = {}
        def fake_get_watchlist_with_info(workspace_id):
            calls["workspace_id"] = workspace_id
            return []

        monkeypatch.setattr(
            watchlist_router.storage,
            "get_watchlist_with_info",
            fake_get_watchlist_with_info,
        )

        resp = client.get("/api/watchlist")

        assert resp.status_code == 200
        assert calls["workspace_id"] == "watch-workspace"

    def test_add_watchlist_rejects_invalid_code(self, client, watchlist_account):
        resp = client.post("/api/watchlist", json={"code": "600519.SH"})
        assert resp.status_code == 400

    def test_add_watchlist_uses_current_workspace(self, client, monkeypatch, watchlist_account):
        from dashboard.routers import watchlist as watchlist_router

        calls = {}
        stock_list = pd.DataFrame({"code": ["600519"], "name": ["贵州茅台"]})
        def fake_add_to_watchlist(code, workspace_id):
            calls["add"] = (code, workspace_id)
            return False

        monkeypatch.setattr(watchlist_router.storage, "get_stock_list", lambda: stock_list)
        monkeypatch.setattr(
            watchlist_router.storage,
            "add_to_watchlist",
            fake_add_to_watchlist,
        )
        monkeypatch.setattr(
            watchlist_router,
            "get_quote_service",
            lambda: type("QS", (), {
                "get_or_fetch_quote": lambda self, code: None,
                "subscribe": lambda self, codes: None,
            })(),
        )

        resp = client.post("/api/watchlist", json={"code": "600519"})

        assert resp.status_code == 200
        assert calls["add"] == ("600519", "watch-workspace")

    def test_add_watchlist_rejects_unknown_code(self, client, monkeypatch, watchlist_account):
        from dashboard.routers import watchlist as watchlist_router

        class FakeCollector:
            def get_stock_list(self):
                return pd.DataFrame({"code": ["000001"], "name": ["平安银行"]})

        monkeypatch.setattr(
            "data.collector.StockCollector",
            lambda: FakeCollector(),
        )
        monkeypatch.setattr(watchlist_router.storage, "get_stock_list", lambda: pd.DataFrame())

        resp = client.post("/api/watchlist", json={"code": "123456"})

        assert resp.status_code == 404

    def test_remove_watchlist_normalizes_code_before_unsubscribe(self, client, monkeypatch, watchlist_account):
        from dashboard.routers import watchlist as watchlist_router

        calls = {}
        monkeypatch.setattr(
            watchlist_router.storage,
            "remove_from_watchlist",
            lambda code, workspace_id: calls.setdefault("removed", (code, workspace_id)) == ("600519", "watch-workspace"),
        )
        monkeypatch.setattr(
            watchlist_router,
            "get_quote_service",
            lambda: type("QS", (), {"unsubscribe": lambda self, codes: calls.setdefault("unsubscribed", list(codes))})(),
        )

        resp = client.delete("/api/watchlist/sh600519")

        assert resp.status_code == 200
        assert calls["removed"] == ("600519", "watch-workspace")
        assert calls["unsubscribed"] == ["600519"]

    def test_realtime_quotes_status(self, client):
        """GET /quotes/status — 行情服务状态"""
        resp = client.get("/quotes/status")
        assert resp.status_code == 200


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  股票详情
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestStockDetail:
    """股票详情端点"""

    def test_stock_search(self, client):
        """GET /api/stock/search — 股票搜索"""
        resp = client.get("/api/stock/search")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["query"] == ""
        assert "source" in data
        assert data["degraded"] is False
        assert isinstance(data["results"], list)

    def test_stock_search_prioritizes_exact_code(self, client, monkeypatch):
        """GET /api/stock/search?q=600519 — 精确代码优先"""
        import time

        import pandas as pd
        from dashboard.routers import stock_detail as stock_detail_router

        monkeypatch.setattr(
            stock_detail_router,
            "_stock_list_cache",
            {"df": pd.DataFrame([
                {"code": "000001", "name": "平安银行"},
                {"code": "600519", "name": "贵州茅台"},
                {"code": "600520", "name": "三六零"},
            ]), "ts": time.time()},
        )

        resp = client.get("/api/stock/search", params={"q": "600519", "limit": 10})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["results"][0]["code"] == "600519"

    def test_stock_search_prioritizes_name_match(self, client, monkeypatch):
        """GET /api/stock/search?q=茅台 — 名称匹配排序"""
        import time

        import pandas as pd
        from dashboard.routers import stock_detail as stock_detail_router

        monkeypatch.setattr(
            stock_detail_router,
            "_stock_list_cache",
            {"df": pd.DataFrame([
                {"code": "600000", "name": "浦发银行"},
                {"code": "600519", "name": "贵州茅台"},
                {"code": "000568", "name": "泸州老窖"},
            ]), "ts": time.time()},
        )

        resp = client.get("/api/stock/search", params={"q": "茅台", "limit": 10})
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"][0]["name"] == "贵州茅台"

    def test_stock_detail_missing_code(self, client):
        """GET /api/stock/detail/ — 缺少 code 参数"""
        resp = client.get("/api/stock/detail/")
        assert resp.status_code in (400, 404, 422)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  市场雷达
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestMarket:
    """市场雷达端点"""

    def test_market_radar(self, client):
        """GET /api/market/radar — 市场雷达"""
        resp = client.get("/api/market/radar")
        assert resp.status_code == 200

    def test_market_radar_returns_stale_data_during_refresh(self, client, monkeypatch):
        """GET /api/market/radar — 有上次成功数据时不被慢数据源阻塞"""
        from dashboard.routers import market as market_router

        previous_last_radar = market_router._last_radar
        previous_refresh_task = market_router._radar_refresh_task
        market_router._cache.delete("market_radar")
        market_router._last_radar = {
            "success": True,
            "top_gainers": [],
            "top_losers": [],
            "top_amplitude": [],
            "top_turnover": [],
            "total_stocks": 0,
            "source": "eastmoney_full_market_rank",
            "universe": "all_a",
        }
        market_router._radar_refresh_task = None

        def fail_if_blocking():
            raise AssertionError("stale radar response should not fetch synchronously")

        monkeypatch.setattr(market_router, "_fetch_market_radar_snapshot", fail_if_blocking)

        try:
            resp = client.get("/api/market/radar")

            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["stale"] is True
        finally:
            market_router._cache.delete("market_radar")
            market_router._last_radar = previous_last_radar
            market_router._radar_refresh_task = previous_refresh_task

    def test_market_radar_uses_full_market_snapshot(self, client, monkeypatch):
        """GET /api/market/radar — 首屏使用全A股排行快照"""
        from dashboard.routers import market as market_router

        previous_last_radar = market_router._last_radar
        market_router._cache.delete("market_radar")
        market_router._last_radar = None
        monkeypatch.setattr(
            market_router,
            "_fetch_market_radar_snapshot",
            lambda: {
                "success": True,
                "top_gainers": [{"code": "920211", "name": "N新睿", "value": 800.67}],
                "top_losers": [],
                "top_amplitude": [],
                "top_turnover": [],
                "total_stocks": 5861,
                "source": "eastmoney_full_market_rank",
                "universe": "all_a",
            },
        )

        try:
            resp = client.get("/api/market/radar")
            data = resp.json()
            assert resp.status_code == 200
            assert data["success"] is True
            assert data["source"] == "eastmoney_full_market_rank"
            assert data["universe"] == "all_a"
            assert data["total_stocks"] == 5861
            assert "local_fallback" not in data
        finally:
            market_router._cache.delete("market_radar")
            market_router._last_radar = previous_last_radar

    def test_market_radar_falls_back_to_local_full_daily_coverage_when_live_source_fails(self, client, monkeypatch):
        """GET /api/market/radar — 实时源失败时返回本地全量覆盖池，不返回业务失败"""
        from dashboard.routers import market as market_router

        previous_last_radar = market_router._last_radar
        market_router._cache.delete("market_radar")
        market_router._last_radar = None

        local_rows = [
            {
                "code": "000001",
                "name": "平安银行",
                "price": 11.0,
                "change_pct": 10.0,
                "amplitude": 4.0,
                "turnover_rate": 30.0,
                "date": "2026-06-05",
                "source": "local_stock_daily",
            },
            {
                "code": "600519",
                "name": "贵州茅台",
                "price": 1570.0,
                "change_pct": -2.0,
                "amplitude": 3.0,
                "turnover_rate": 20.0,
                "date": "2026-06-05",
                "source": "local_stock_daily",
            },
        ]

        monkeypatch.setattr(
            market_router,
            "_fetch_market_radar_snapshot",
            lambda: (_ for _ in ()).throw(RuntimeError("live source unavailable")),
        )
        monkeypatch.setattr(market_router, "_local_market_stock_rows", lambda limit=None: local_rows)

        try:
            resp = client.get("/api/market/radar")
            data = resp.json()

            assert resp.status_code == 200
            assert data["success"] is True
            assert data["source"] == "local_stock_daily"
            assert data["local_fallback"] is True
            assert data["stale"] is True
            assert data["total_stocks"] == 2
            assert data["top_gainers"][0]["code"] == "000001"
            assert data["top_losers"][0]["code"] == "600519"
        finally:
            market_router._cache.delete("market_radar")
            market_router._last_radar = previous_last_radar

    def test_market_radar_fast_uses_local_daily_without_live_fetch(self, client, monkeypatch):
        """GET /api/market/radar?fast=true — 首屏快路径不等待实时源"""
        from dashboard.routers import market as market_router

        previous_last_radar = market_router._last_radar
        market_router._cache.delete("market_radar")
        market_router._cache.delete("market_radar:fast")
        market_router._last_radar = None
        calls = {"live": 0}

        local_rows = [
            {
                "code": "000001",
                "name": "平安银行",
                "price": 11.0,
                "change_pct": 10.0,
                "amplitude": 4.0,
                "turnover_rate": 30.0,
                "date": "2026-06-05",
                "source": "local_stock_daily",
            },
            {
                "code": "600519",
                "name": "贵州茅台",
                "price": 1570.0,
                "change_pct": -2.0,
                "amplitude": 3.0,
                "turnover_rate": 20.0,
                "date": "2026-06-05",
                "source": "local_stock_daily",
            },
        ]

        def fail_if_live_fetch():
            calls["live"] += 1
            raise RuntimeError("live source should not be used by fast path")

        monkeypatch.setattr(market_router, "_fetch_market_radar_snapshot", fail_if_live_fetch)
        monkeypatch.setattr(market_router, "_local_market_stock_rows", lambda limit=None: local_rows)

        try:
            resp = client.get("/api/market/radar?fast=true")
            data = resp.json()

            assert resp.status_code == 200
            assert calls["live"] == 0
            assert data["success"] is True
            assert data["fast"] is True
            assert data["source"] == "local_stock_daily"
            assert data["local_fallback"] is True
            assert data["total_stocks"] == 2
            assert data["top_gainers"][0]["code"] == "000001"
            assert data["top_losers"][0]["code"] == "600519"
        finally:
            market_router._cache.delete("market_radar")
            market_router._cache.delete("market_radar:fast")
            market_router._last_radar = previous_last_radar

    def test_market_radar_local_fallback_exposes_trust_metadata(self, client, monkeypatch):
        """GET /api/market/radar?fast=true — 本地覆盖池回退说明统计口径"""
        from dashboard.routers import market as market_router

        previous_last_radar = market_router._last_radar
        market_router._cache.delete("market_radar")
        market_router._cache.delete("market_radar:fast")
        market_router._last_radar = None

        local_rows = [
            {
                "code": "000001",
                "name": "平安银行",
                "price": 11.0,
                "change_pct": 10.0,
                "amplitude": 4.0,
                "turnover_rate": 30.0,
                "date": "2026-06-05",
                "source": "local_stock_daily",
            },
        ]

        monkeypatch.setattr(market_router, "_local_market_stock_rows", lambda limit=None: local_rows)

        try:
            resp = client.get("/api/market/radar?fast=true")
            data = resp.json()

            assert resp.status_code == 200
            assert data["success"] is True
            assert data["source"] == "local_stock_daily"
            assert data["universe"] == "local_stock_daily_coverage_pool"
            assert data["coverage_note"]
            assert data["generated_at"]
            assert data["fast_path_note"]
        finally:
            market_router._cache.delete("market_radar")
            market_router._cache.delete("market_radar:fast")
            market_router._last_radar = previous_last_radar

    def test_market_breadth_uses_local_full_daily_coverage(self, client, monkeypatch):
        """GET /api/market/breadth — 返回本地全量覆盖池涨跌广度"""
        from dashboard.routers import market as market_router

        previous_last_breadth = market_router._last_breadth
        market_router._cache.delete("market_breadth")
        market_router._last_breadth = None

        class FakeStorage:
            def get_market_breadth(self):
                return {
                    "stock_count": 5525,
                    "total_stocks": 5525,
                    "effective_count": 5515,
                    "daily_covered": 5525,
                    "daily_missing": 0,
                    "coverage_pct": 100.0,
                    "latest_date": "2026-06-05",
                    "previous_date": "2026-06-04",
                    "latest_date_covered": 5515,
                    "latest_date_missing": 10,
                    "up_count": 2310,
                    "down_count": 2860,
                    "flat_count": 355,
                    "no_prev_count": 0,
                    "limit_up": 68,
                    "limit_down": 21,
                    "avg_change_pct": -0.12,
                    "up_ratio": 41.81,
                }

        monkeypatch.setattr(market_router, "DataStorage", lambda: FakeStorage())

        try:
            resp = client.get("/api/market/breadth")
            data = resp.json()
            assert resp.status_code == 200
            assert data["success"] is True
            assert data["source"] == "local_stock_daily"
            assert data["universe"] == "local_stock_info_all_a"
            assert data["stock_count"] == 5525
            assert data["total_stocks"] == 5525
            assert data["effective_count"] == 5515
            assert data["up_count"] == 2310
            assert data["down_count"] == 2860
            assert data["flat_count"] == 355
            assert data["limit_up"] == 68
            assert data["limit_down"] == 21
            assert data["latest_date"] == "2026-06-05"
            assert data["latest_date_missing"] == 10
        finally:
            market_router._cache.delete("market_breadth")
            market_router._last_breadth = previous_last_breadth

    def test_market_news_empty_response_exposes_source_unavailable_metadata(self, client, monkeypatch):
        """GET /api/market/news — 空新闻不能伪装成真实 0 条"""
        from dashboard.routers import market as market_router

        previous_last_news = market_router._last_news
        market_router._cache.delete("market_news")
        market_router._last_news = None

        async def fake_news_summary():
            return {
                "timestamp": "2026-06-08T15:30:00",
                "news": [],
                "overall_sentiment": 0,
                "sources": [],
                "errors": ["no_news_source"],
            }

        monkeypatch.setitem(
            __import__("sys").modules,
            "alpha.news_collector",
            type("FakeNewsCollector", (), {"fetch_market_news_summary": fake_news_summary}),
        )

        try:
            resp = client.get("/api/market/news")
            data = resp.json()

            assert resp.status_code == 200
            assert data["success"] is True
            assert data["source"] == "market_news_multi_source"
            assert data["generated_at"]
            assert data["timestamp"] == "2026-06-08T15:30:00"
            assert data["coverage_note"]
            assert data["source_unavailable"] is True
            assert data["stale"] is True
            assert data["stale_reason"] == "no_news_source"
        finally:
            market_router._cache.delete("market_news")
            market_router._last_news = previous_last_news

    def test_market_news_without_source_timestamp_uses_generated_timestamp(self, client, monkeypatch):
        """GET /api/market/news — 成功路径必须给前端可用 timestamp"""
        from dashboard.routers import market as market_router

        previous_last_news = market_router._last_news
        market_router._cache.delete("market_news")
        market_router._last_news = None

        async def fake_news_summary():
            return {
                "news": [{"title": "市场回暖", "time": "2026-06-08 15:29:00", "source": "东方财富快讯"}],
                "overall_sentiment": 0.2,
                "sources": [{"name": "东方财富快讯"}],
            }

        monkeypatch.setitem(
            __import__("sys").modules,
            "alpha.news_collector",
            type("FakeNewsCollector", (), {"fetch_market_news_summary": fake_news_summary}),
        )

        try:
            resp = client.get("/api/market/news")
            data = resp.json()

            assert resp.status_code == 200
            assert data["success"] is True
            assert data["source"] == "market_news_multi_source"
            assert data["timestamp"]
            assert data["generated_at"] == data["timestamp"]
            assert data["coverage_note"] == "多源市场新闻聚合：东方财富快讯"
            assert data["news"][0]["title"] == "市场回暖"
        finally:
            market_router._cache.delete("market_news")
            market_router._last_news = previous_last_news

    def test_market_news_returns_linked_stock_and_topic_metadata(self, client, monkeypatch):
        """GET /api/market/news — 新闻应透传股票/主题关联元数据"""
        from dashboard.routers import market as market_router

        previous_last_news = market_router._last_news
        market_router._cache.delete("market_news")
        market_router._last_news = None

        async def fake_news_summary():
            return {
                "timestamp": "2026-06-08T15:30:00",
                "news": [
                    {
                        "title": "宁德时代带动新能源车产业链订单增长",
                        "time": "2026-06-08 15:29:00",
                        "source": "东方财富快讯",
                        "sentiment": 0.4,
                        "stocks": [
                            {"code": "300750", "name": "宁德时代", "industry": "电力设备", "match": "name"}
                        ],
                        "topics": [
                            {"name": "电力设备", "match": "stock", "stock_count": 1},
                            {"name": "新能源车", "match": "keyword", "stock_count": 0},
                        ],
                        "value_score": 8.4,
                        "value_reasons": ["关联个股", "关联主题", "情绪显著"],
                    }
                ],
                "overall_sentiment": 0.4,
                "sources": [{"name": "东方财富快讯", "count": 1}],
                "linked_news_count": 1,
                "linked_stock_count": 1,
                "topic_count": 2,
                "ranking": {
                    "method": "actionable_value",
                    "description": "按个股关联、主题关联、情绪强度和来源可信度综合排序",
                },
            }

        monkeypatch.setitem(
            __import__("sys").modules,
            "alpha.news_collector",
            type("FakeNewsCollector", (), {"fetch_market_news_summary": fake_news_summary}),
        )

        try:
            resp = client.get("/api/market/news")
            data = resp.json()

            assert resp.status_code == 200
            assert data["success"] is True
            assert data["linked_news_count"] == 1
            assert data["linked_stock_count"] == 1
            assert data["topic_count"] == 2
            assert data["ranking"]["method"] == "actionable_value"
            assert data["news"][0]["stocks"][0]["code"] == "300750"
            assert data["news"][0]["topics"][1]["name"] == "新能源车"
            assert data["news"][0]["value_score"] == 8.4
            assert data["news"][0]["value_reasons"] == ["关联个股", "关联主题", "情绪显著"]
        finally:
            market_router._cache.delete("market_news")
            market_router._last_news = previous_last_news

    def test_market_sectors(self, client):
        """GET /api/market/sectors — 板块数据"""
        resp = client.get("/api/market/sectors")
        assert resp.status_code == 200

    def test_market_sectors_fast_uses_local_daily_without_external_fetch(self, client, monkeypatch):
        """GET /api/market/sectors?fast=true — 首屏快路径不等待板块源"""
        from dashboard.routers import market as market_router

        previous_last_sectors = market_router._last_sectors
        market_router._cache.delete("sectors:industry")
        market_router._cache.delete("sectors:industry:fast")
        market_router._last_sectors = None
        calls = {"external": 0}

        local_rows = [
            {"code": "000001", "name": "平安银行", "industry": "银行", "change_pct": 2.0, "amount": 1e10},
            {"code": "600000", "name": "浦发银行", "industry": "银行", "change_pct": -1.0, "amount": 2e10},
            {"code": "300750", "name": "宁德时代", "industry": "电池", "change_pct": 3.0, "amount": 3e10},
        ]

        def fail_if_external_fetch(sector_type):
            calls["external"] += 1
            raise RuntimeError("sector source should not be used by fast path")

        monkeypatch.setattr(market_router, "_fetch_sector_ranking", fail_if_external_fetch)
        monkeypatch.setattr(market_router, "_local_market_stock_rows", lambda limit=None: local_rows)

        try:
            resp = client.get("/api/market/sectors?type=industry&fast=true")
            data = resp.json()

            assert resp.status_code == 200
            assert calls["external"] == 0
            assert data["success"] is True
            assert data["fast"] is True
            assert data["source"] == "local_stock_daily"
            assert data["local_fallback"] is True
            assert data["type"] == "industry"
            assert [row["name"] for row in data["sectors"][:2]] == ["电池", "银行"]
        finally:
            market_router._cache.delete("sectors:industry")
            market_router._cache.delete("sectors:industry:fast")
            market_router._last_sectors = previous_last_sectors

    def test_market_heatmap_fetches_all_eastmoney_pages(self, client, monkeypatch):
        """GET /api/market/heatmap — 不只统计涨幅榜第一页前 100 个板块"""
        from dashboard.routers import market as market_router

        previous_last_heatmap = market_router._last_heatmap
        market_router._cache.delete("sector_heatmap")
        market_router._last_heatmap = None
        calls = []

        def fake_fetch_json(url, timeout=10):
            calls.append(url)
            if "pn=1" in url:
                return {
                    "data": {
                        "total": 205,
                        "diff": [
                            {"f12": "BK001", "f14": "强势板块", "f3": 3.2, "f104": 10, "f105": 0, "f20": 100_000_000_000},
                        ],
                    }
                }
            if "pn=2" in url:
                return {
                    "data": {
                        "diff": [
                            {"f12": "BK002", "f14": "中性板块", "f3": 0.0, "f104": 5, "f105": 5, "f20": 80_000_000_000},
                        ],
                    }
                }
            return {
                "data": {
                    "diff": [
                        {"f12": "BK003", "f14": "弱势板块", "f3": -2.4, "f104": 1, "f105": 12, "f20": 60_000_000_000},
                    ],
                }
            }

        monkeypatch.setattr(market_router, "fetch_json", fake_fetch_json)

        try:
            resp = client.get("/api/market/heatmap")
            data = resp.json()
            assert resp.status_code == 200
            assert data["success"] is True
            assert data["total"] == 205
            assert data["fetched"] == 3
            assert data["up_count"] == 1
            assert data["down_count"] == 1
            assert data["flat_count"] == 1
            assert data["source"] == "eastmoney_sector_board"
            assert len(calls) == 3
        finally:
            market_router._cache.delete("sector_heatmap")
            market_router._last_heatmap = previous_last_heatmap

    def test_market_heatmap_fast_uses_local_daily_without_external_fetch(self, client, monkeypatch):
        """GET /api/market/heatmap?fast=true — 首屏快路径不等待板块热力源"""
        from dashboard.routers import market as market_router

        previous_last_heatmap = market_router._last_heatmap
        market_router._cache.delete("sector_heatmap")
        market_router._cache.delete("sector_heatmap:fast")
        market_router._last_heatmap = None
        calls = {"external": 0}

        local_rows = [
            {"code": "000001", "name": "平安银行", "industry": "银行", "change_pct": 2.0, "amount": 1e10},
            {"code": "600000", "name": "浦发银行", "industry": "银行", "change_pct": -1.0, "amount": 2e10},
            {"code": "300750", "name": "宁德时代", "industry": "电池", "change_pct": 3.0, "amount": 3e10},
        ]

        def fail_if_external_fetch():
            calls["external"] += 1
            raise RuntimeError("heatmap source should not be used by fast path")

        monkeypatch.setattr(market_router, "_fetch_sector_heatmap", fail_if_external_fetch)
        monkeypatch.setattr(market_router, "_local_market_stock_rows", lambda limit=None: local_rows)

        try:
            resp = client.get("/api/market/heatmap?fast=true")
            data = resp.json()

            assert resp.status_code == 200
            assert calls["external"] == 0
            assert data["success"] is True
            assert data["fast"] is True
            assert data["source"] == "local_stock_daily"
            assert data["local_fallback"] is True
            assert data["total"] == 2
            assert data["up_count"] == 2
            assert data["down_count"] == 0
            assert [row["name"] for row in data["sectors"][:2]] == ["电池", "银行"]
        finally:
            market_router._cache.delete("sector_heatmap")
            market_router._cache.delete("sector_heatmap:fast")
            market_router._last_heatmap = previous_last_heatmap

    def test_market_heatmap_fast_uses_exchange_board_when_local_industry_is_sparse(self, client, monkeypatch):
        """GET /api/market/heatmap?fast=true — 本地行业缺失时按交易板块全量聚合"""
        from dashboard.routers import market as market_router

        previous_last_heatmap = market_router._last_heatmap
        market_router._cache.delete("sector_heatmap")
        market_router._cache.delete("sector_heatmap:fast")
        market_router._last_heatmap = None
        local_rows = [
            {"code": "000001", "name": "平安银行", "industry": "", "change_pct": 2.0, "amount": 1e10},
            {"code": "600000", "name": "浦发银行", "industry": "", "change_pct": -1.0, "amount": 2e10},
            {"code": "300750", "name": "宁德时代", "industry": "", "change_pct": 3.0, "amount": 3e10},
            {"code": "688001", "name": "华兴源创", "industry": "", "change_pct": -2.0, "amount": 4e10},
            {"code": "830799", "name": "艾融软件", "industry": "", "change_pct": 1.0, "amount": 5e10},
        ]

        monkeypatch.setattr(market_router, "_fetch_sector_heatmap", lambda: (_ for _ in ()).throw(RuntimeError("unused")))
        monkeypatch.setattr(market_router, "_local_market_stock_rows", lambda limit=None: local_rows)

        try:
            resp = client.get("/api/market/heatmap?fast=true")
            data = resp.json()

            assert resp.status_code == 200
            assert data["success"] is True
            assert data["fast"] is True
            assert data["local_fallback"] is True
            assert data["grouping"] == "exchange_board"
            assert data["weight_basis"] == "stock_count"
            assert data["industry_coverage_pct"] == 0
            names = {row["name"] for row in data["sectors"]}
            assert {"深主板", "沪主板", "创业板", "科创板", "北交所"} <= names
            assert "本地覆盖池" not in names
            assert all(row["total_mv"] == 0 for row in data["sectors"])
            assert all(row["stock_count"] == 1 for row in data["sectors"])
            assert all(row["turnover_amount"] > 0 for row in data["sectors"])
            assert "交易板块" in data["coverage_note"]
        finally:
            market_router._cache.delete("sector_heatmap")
            market_router._cache.delete("sector_heatmap:fast")
            market_router._last_heatmap = previous_last_heatmap

    def test_market_heatmap_fast_empty_response_exposes_trust_metadata(self, client, monkeypatch):
        """GET /api/market/heatmap?fast=true — 空热力也必须说明来源和降级原因"""
        from dashboard.routers import market as market_router

        previous_last_heatmap = market_router._last_heatmap
        market_router._cache.delete("sector_heatmap")
        market_router._cache.delete("sector_heatmap:fast")
        market_router._last_heatmap = None

        monkeypatch.setattr(market_router, "_fetch_sector_heatmap", lambda: (_ for _ in ()).throw(RuntimeError("unused")))
        monkeypatch.setattr(market_router, "_build_local_sector_snapshot", lambda: {
            "sectors": [],
            "grouping": "industry",
            "weight_basis": "stock_count",
            "stock_count": 0,
            "industry_covered": 0,
            "industry_coverage_pct": 0,
        })

        try:
            resp = client.get("/api/market/heatmap?fast=true")
            data = resp.json()

            assert resp.status_code == 200
            assert data["success"] is False
            assert data["fast"] is True
            assert data["fast_path"] is True
            assert data["source"] == "local_stock_daily"
            assert data["source_unavailable"] is True
            assert data["stale"] is True
            assert data["stale_reason"] == "fast_local_coverage_unavailable"
            assert data["coverage_note"]
            assert data["generated_at"]
            assert data["total"] == 0
            assert data["fetched"] == 0
            assert data["sectors"] == []
        finally:
            market_router._cache.delete("sector_heatmap")
            market_router._cache.delete("sector_heatmap:fast")
            market_router._last_heatmap = previous_last_heatmap

    def test_market_heatmap_live_empty_response_exposes_trust_metadata(self, client, monkeypatch):
        """GET /api/market/heatmap — 外部源和本地源都失败时不能裸返回空 sectors"""
        from dashboard.routers import market as market_router

        previous_last_heatmap = market_router._last_heatmap
        market_router._cache.delete("sector_heatmap")
        market_router._cache.delete("sector_heatmap:fast")
        market_router._last_heatmap = None

        monkeypatch.setattr(market_router, "_fetch_sector_heatmap", lambda: (_ for _ in ()).throw(RuntimeError("heatmap unavailable")))
        monkeypatch.setattr(market_router, "_build_local_sector_snapshot", lambda: {
            "sectors": [],
            "grouping": "industry",
            "weight_basis": "stock_count",
            "stock_count": 0,
            "industry_covered": 0,
            "industry_coverage_pct": 0,
        })

        try:
            resp = client.get("/api/market/heatmap")
            data = resp.json()

            assert resp.status_code == 200
            assert data["success"] is False
            assert data["source"] == "eastmoney_sector_board"
            assert data["source_unavailable"] is True
            assert data["stale"] is True
            assert data["stale_reason"] == "heatmap_source_unavailable"
            assert "heatmap unavailable" in data["error"]
            assert data["coverage_note"]
            assert data["generated_at"]
            assert data["total"] == 0
            assert data["fetched"] == 0
            assert data["sectors"] == []
        finally:
            market_router._cache.delete("sector_heatmap")
            market_router._cache.delete("sector_heatmap:fast")
            market_router._last_heatmap = previous_last_heatmap

    def test_market_sector_members_returns_local_constituents_with_trust_context(self, client, monkeypatch):
        """GET /api/market/sector-members — 板块热力图可钻到本地覆盖池成分股"""
        from dashboard.routers import market as market_router

        market_router._cache.delete("sector_members:industry:银行:10")
        local_rows = [
            {"code": "000001", "name": "平安银行", "industry": "银行", "change_pct": 2.0, "amount": 1e10, "price": 11.2},
            {"code": "600000", "name": "浦发银行", "industry": "银行", "change_pct": -1.0, "amount": 2e10, "price": 8.5},
            {"code": "300750", "name": "宁德时代", "industry": "电池", "change_pct": 3.0, "amount": 3e10, "price": 210.0},
        ]
        monkeypatch.setattr(market_router, "_local_market_stock_rows", lambda limit=None: local_rows)
        monkeypatch.setattr(
            market_router,
            "build_signal_context",
            lambda top_limit=500: {
                "provider": "local_momentum",
                "model_version": "local_momentum_v1",
                "latest_date": "2026-06-05",
                "raw_source": "legacy_qlib",
                "items": {
                    "000001": {
                        "signal_rank": 3,
                        "signal_score": 0.91,
                        "signal_confidence": "validated_positive",
                    }
                },
            },
        )

        try:
            resp = client.get("/api/market/sector-members?name=银行&grouping=industry&limit=10")
            data = resp.json()

            assert resp.status_code == 200
            assert data["success"] is True
            assert data["sector_name"] == "银行"
            assert data["source"] == "local_stock_daily"
            assert data["universe"] == "local_stock_daily_coverage_pool"
            assert data["grouping"] == "industry"
            assert data["total_count"] == 2
            assert data["effective_count"] == 2
            assert data["display_count"] == 2
            assert data["generated_at"]
            assert "本地 stock_daily" in data["coverage_note"]
            assert [item["code"] for item in data["members"]] == ["000001", "600000"]
            assert data["members"][0]["sector_name"] == "银行"
            assert data["members"][0]["source"] == "local_stock_daily"
            evidence = data["evidence_context"]
            assert evidence["summary"]["direction"] == "多空均衡"
            assert evidence["summary"]["member_count"] == 2
            assert evidence["summary"]["leader"]["code"] == "000001"
            assert evidence["liquidity"]["total_amount_yi"] == 300.0
            assert evidence["liquidity"]["top_amount_member"]["code"] == "600000"
            assert evidence["signal_overlap"]["count"] == 1
            assert evidence["signal_overlap"]["items"][0]["code"] == "000001"
            assert evidence["signal_overlap"]["provider"] == "local_momentum"
            assert evidence["news_research"]["status"] == "missing"
            assert "新闻/研报" in evidence["news_research"]["missing_reason"]
            assert evidence["related_index"]["status"] == "missing"
            assert [item["id"] for item in evidence["next_actions"]] == ["send_screener", "open_stock", "draft_backtest"]
            assert data["source_context"]["context_type"] == "sector"
            assert data["source_context"]["sector_name"] == "银行"
        finally:
            market_router._cache.delete("sector_members:industry:银行:10")

    def test_market_sector_members_evidence_uses_full_sector_not_display_limit(self, client, monkeypatch):
        """GET /api/market/sector-members — 证据上下文按全量板块计算，不被 limit 截断"""
        from dashboard.routers import market as market_router

        market_router._cache.delete("sector_members:industry:银行:1")
        local_rows = [
            {"code": "000001", "name": "平安银行", "industry": "银行", "change_pct": 3.0, "amount": 1e10, "price": 11.2},
            {"code": "600000", "name": "浦发银行", "industry": "银行", "change_pct": 2.0, "amount": 5e10, "price": 8.5},
            {"code": "601398", "name": "工商银行", "industry": "银行", "change_pct": 1.0, "amount": 2e10, "price": 6.2},
        ]
        monkeypatch.setattr(market_router, "_local_market_stock_rows", lambda limit=None: local_rows)
        monkeypatch.setattr(
            market_router,
            "build_signal_context",
            lambda top_limit=500: {
                "provider": "local_momentum",
                "model_version": "local_momentum_v1",
                "latest_date": "2026-06-05",
                "items": {
                    "600000": {
                        "signal_rank": 9,
                        "signal_score": 0.88,
                        "signal_confidence": "validated_positive",
                    }
                },
            },
        )

        try:
            resp = client.get("/api/market/sector-members?name=银行&grouping=industry&limit=1")
            data = resp.json()

            assert resp.status_code == 200
            assert data["display_count"] == 1
            assert [item["code"] for item in data["members"]] == ["000001"]
            evidence = data["evidence_context"]
            assert evidence["summary"]["member_count"] == 3
            assert evidence["summary"]["leader"]["code"] == "000001"
            assert evidence["liquidity"]["total_amount_yi"] == 800.0
            assert evidence["liquidity"]["top_amount_member"]["code"] == "600000"
            assert evidence["signal_overlap"]["count"] == 1
            assert evidence["signal_overlap"]["items"][0]["code"] == "600000"
        finally:
            market_router._cache.delete("sector_members:industry:银行:1")

    def test_market_sector_members_empty_result_is_not_source_unavailable(self, client, monkeypatch):
        """GET /api/market/sector-members — 无匹配成分是成功空态，不应误报数据源异常"""
        from dashboard.routers import market as market_router

        market_router._cache.delete("sector_members:industry:银行:10")
        local_rows = [
            {"code": "300750", "name": "宁德时代", "industry": "电池", "change_pct": 3.0, "amount": 3e10, "price": 210.0},
        ]
        monkeypatch.setattr(market_router, "_local_market_stock_rows", lambda limit=None: local_rows)

        try:
            resp = client.get("/api/market/sector-members?name=银行&grouping=industry&limit=10")
            data = resp.json()

            assert resp.status_code == 200
            assert data["success"] is True
            assert data["members"] == []
            assert data["total_count"] == 0
            assert data["source_unavailable"] is False
            assert data["missing_reason"] == "本地覆盖池暂无银行成分股"
            assert "暂无 银行 成分股" in data["coverage_note"]
            assert data["source_context"]["context_type"] == "sector"
            assert data["evidence_context"]["summary"]["member_count"] == 0
            assert data["evidence_context"]["signal_overlap"]["missing_reason"] == "板块暂无成分股，无法计算 Signal 重叠"
            assert data["evidence_context"]["news_research"]["status"] == "missing"
            assert data["evidence_context"]["related_index"]["status"] == "missing"
        finally:
            market_router._cache.delete("sector_members:industry:银行:10")

    def test_market_northbound_returns_soft_unavailable_state_when_source_fails(self, client, monkeypatch):
        """GET /api/market/northbound — 北向源不可用时不让情报页进入硬失败"""
        from dashboard.routers import market as market_router

        previous_last_northbound = market_router._last_northbound
        market_router._cache.delete("northbound")
        market_router._last_northbound = None
        monkeypatch.setattr(
            market_router,
            "_fetch_northbound",
            lambda: (_ for _ in ()).throw(RuntimeError("northbound unavailable")),
        )

        try:
            resp = client.get("/api/market/northbound")
            data = resp.json()

            assert resp.status_code == 200
            assert data["success"] is True
            assert data["today_net"] == 0
            assert data["flow"] == []
            assert data["stale"] is True
            assert data["source_unavailable"] is True
            assert data["source"] == "eastmoney_northbound"
        finally:
            market_router._cache.delete("northbound")
            market_router._last_northbound = previous_last_northbound

    def test_market_hotspot_returns_soft_unavailable_state_when_source_fails(self, client, monkeypatch):
        """GET /api/market/hotspot — 热点源不可用时不让情报页硬失败"""
        from dashboard.routers import market as market_router

        previous_last_hotspot = market_router._last_hotspot
        market_router._cache.delete("hotspot")
        market_router._last_hotspot = None

        async def fail_hotspot():
            raise RuntimeError("hotspot unavailable")

        import alpha.hotspot_attribution as hotspot_module

        monkeypatch.setattr(hotspot_module, "get_hotspot_attribution", fail_hotspot)

        try:
            resp = client.get("/api/market/hotspot")
            data = resp.json()

            assert resp.status_code == 200
            assert data["success"] is True
            assert data["source"] == "hotspot_attribution"
            assert data["provider"] == "hotspot_attribution"
            assert data["source_unavailable"] is True
            assert data["stale"] is True
            assert data["stale_reason"] == "hotspot_source_unavailable"
            assert "hotspot unavailable" in data["error"]
            assert data["coverage_note"]
            assert data["generated_at"]
            assert data["timestamp"] == data["generated_at"]
            assert data["summary"] == "暂无热点数据"
            assert data["concepts"] == []
            assert data["industries"] == []
            assert data["fund_flow"] == []
            assert "hotspot unavailable" in data["partial_errors"][0]
        finally:
            market_router._cache.delete("hotspot")
            market_router._last_hotspot = previous_last_hotspot

    def test_market_northbound_fast_returns_soft_unavailable_without_external_fetch(self, client, monkeypatch):
        """GET /api/market/northbound?fast=true — 无缓存时快路径不等待北向源"""
        from dashboard.routers import market as market_router

        previous_last_northbound = market_router._last_northbound
        market_router._cache.delete("northbound")
        market_router._cache.delete("northbound:fast")
        market_router._last_northbound = None
        calls = {"external": 0}

        def fail_if_external_fetch():
            calls["external"] += 1
            raise RuntimeError("northbound source should not be used by fast path")

        monkeypatch.setattr(market_router, "_fetch_northbound", fail_if_external_fetch)

        try:
            resp = client.get("/api/market/northbound?fast=true")
            data = resp.json()

            assert resp.status_code == 200
            assert calls["external"] == 0
            assert data["success"] is True
            assert data["fast"] is True
            assert data["source_unavailable"] is True
            assert data["source"] == "eastmoney_northbound"
            assert data["flow"] == []
        finally:
            market_router._cache.delete("northbound")
            market_router._cache.delete("northbound:fast")
            market_router._last_northbound = previous_last_northbound

    def test_market_rules_list(self, client):
        """GET /api/market-rules/list — 市场规则"""
        resp = client.get("/api/market-rules/list")
        assert resp.status_code == 200


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  条件选股
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestScreener:
    """条件选股端点"""

    def test_screener_presets(self, client):
        """GET /api/screener/presets — 预设条件"""
        resp = client.get("/api/screener/presets")
        assert resp.status_code == 200

    def test_screener_run_respects_explicit_code_pool(self, client, monkeypatch):
        """POST /api/screener/run — codes 应限定问财推送池"""
        captured = {}

        def fake_screen(**kwargs):
            captured.update(kwargs)
            return {
                "total": len(kwargs["codes"]),
                "page": 1,
                "page_size": 10000,
                "stocks": [{"code": code} for code in kwargs["codes"]],
            }

        monkeypatch.setattr("dashboard.routers.screener._screener.screen", fake_screen)

        resp = client.post(
            "/api/screener/run",
            json={
                "codes": ["600519.SH", "000001", "000001"],
                "page_size": 10000,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["total"] == 2
        assert captured["codes"] == ["600519", "000001"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  预警管理
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestAlerts:
    """预警管理端点"""

    def test_get_alert_rules(self, client):
        """GET /api/alerts/rules — 预警规则"""
        resp = client.get("/api/alerts/rules")
        assert resp.status_code == 200

    def test_get_alert_history(self, client):
        """GET /api/alerts/history — 预警历史"""
        resp = client.get("/api/alerts/history")
        assert resp.status_code == 200

    def test_get_alert_conditions(self, client):
        """GET /api/alerts/conditions — 预警条件类型"""
        resp = client.get("/api/alerts/conditions")
        assert resp.status_code == 200


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  券商配置
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestBrokerConfig:
    """券商配置端点"""

    def test_get_broker_types(self, client):
        """GET /api/broker/types — 券商类型"""
        resp = client.get("/api/broker/types")
        assert resp.status_code == 200

    def test_get_broker_config(self, client):
        """GET /api/broker — 券商配置"""
        resp = client.get("/api/broker")
        assert resp.status_code == 200


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  AI 助手
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestLLM:
    """AI 助手端点"""

    def test_list_conversations(self, client):
        """GET /api/llm/conversations — 对话列表"""
        resp = client.get("/api/llm/conversations")
        assert resp.status_code == 200

    def test_chat_missing_params(self, client):
        """POST /api/llm/chat — 缺少参数"""
        resp = client.post("/api/llm/chat", json={})
        assert resp.status_code in (400, 422)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  因子分析
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestFactor:
    """因子分析端点"""

    def test_list_factors(self, client):
        """GET /api/factor/list — 因子列表"""
        resp = client.get("/api/factor/list")
        assert resp.status_code == 200


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  组合优化
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestPortfolioOpt:
    """组合优化端点"""

    def test_portfolio_opt_methods(self, client):
        """GET /api/portfolio-opt/methods — 优化方法列表"""
        resp = client.get("/api/portfolio-opt/methods")
        assert resp.status_code == 200


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Alpha 模块
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestAlpha:
    """AI Alpha 端点"""

    def test_alpha_factor_importance(self, client):
        """GET /api/alpha/factor-importance — 因子重要性"""
        resp = client.get("/api/alpha/factor-importance")
        assert resp.status_code in (200, 404)

    def test_alpha_training_metrics(self, client):
        """GET /api/alpha/training-metrics — 训练指标"""
        resp = client.get("/api/alpha/training-metrics")
        assert resp.status_code in (200, 404)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  参数优化
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestOptimization:
    """参数优化端点"""

    def test_optimization_param_ranges(self, client):
        """GET /api/optimization/param-ranges/dual_ma — 参数范围"""
        resp = client.get("/api/optimization/param-ranges/dual_ma")
        assert resp.status_code in (200, 404)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  AI 信号兼容接口
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestQlib:
    """AI 信号 legacy qlib 兼容端点"""

    def test_top_predictions(self, client):
        """GET /api/qlib/top — AI 信号 Top N 兼容路径"""
        resp = client.get("/api/qlib/top")
        assert resp.status_code == 200

    def test_top_predictions_reads_cache_and_enriches_rows(self, client, monkeypatch, tmp_path):
        cache_path = tmp_path / "predictions_cache.json"
        cache_path.write_text(
            '{"predictions":{"2026-05-22":{"600519":0.81,"000001":0.62}}}',
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

        resp = client.get("/api/qlib/top", params={"top_n": 1})

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        assert payload["date"] == "2026-05-22"
        assert payload["total"] == 2
        assert payload["predictions"][0]["code"] == "600519"
        assert payload["predictions"][0]["name"] == "贵州茅台"
        assert payload["predictions"][0]["score"] == 0.81

    def test_qlib_health_reports_cache_metadata(self, client, monkeypatch, tmp_path):
        cache_path = tmp_path / "predictions_cache.json"
        cache_path.write_text(
            '{"predictions":{"2026-05-22":{"600519":0.81,"000001":0.62}}}',
            encoding="utf-8",
        )
        monkeypatch.setattr(qlib_router, "PRED_CACHE_FILE", cache_path)

        resp = client.get("/api/qlib/health")

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        assert payload["status"] in {"online", "stale", "offline"}
        assert payload["cache_exists"] is True
        assert payload["cache_path"] == str(cache_path)
        assert payload["last_update"] == "2026-05-22"
        assert payload["prediction_total"] == 2
        assert payload["service_url"] == qlib_router.QLIB_SERVICE_URL
        assert payload["legacy"] is True
        assert payload["primary_endpoint"] == "/api/signals/health"
        assert payload["adapter_for"] == "signals"

    def test_qlib_health_reports_daily_sync_status(self, client, monkeypatch, tmp_path):
        cache_path = tmp_path / "predictions_cache.json"
        status_path = tmp_path / "sync_status.json"
        cache_path.write_text(
            '{"predictions":{"2026-05-27":{"600519":0.81,"000001":0.62}}}',
            encoding="utf-8",
        )
        status_path.write_text(
            json.dumps(
                {
                    "source": "scheduler",
                    "success": False,
                    "started_at": "2026-05-27T16:40:00",
                    "finished_at": "2026-05-27T16:41:05",
                    "duration_sec": 65.2,
                    "target_count": 3,
                    "success_count": 2,
                    "fail_count": 1,
                    "prediction_success": True,
                    "prediction_latest_date": "2026-05-27",
                    "prediction_total": 2,
                    "prediction_message": "",
                    "items": [
                        {"code": "600519", "success": True},
                        {"code": "000001", "success": True},
                        {"code": "300750", "success": False, "error": "remote closed"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(qlib_router, "PRED_CACHE_FILE", cache_path)
        monkeypatch.setattr(qlib_router, "SYNC_STATUS_FILE", status_path)

        resp = client.get("/api/qlib/health")

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["sync_status"]["source"] == "scheduler"
        assert payload["sync_status"]["success"] is False
        assert payload["sync_status"]["target_count"] == 3
        assert payload["sync_status"]["success_count"] == 2
        assert payload["sync_status"]["fail_count"] == 1
        assert payload["sync_status"]["last_error_samples"] == [
            {"code": "300750", "error": "remote closed"}
        ]

    def test_enrich_stock_info_accepts_plain_codes_against_prefixed_db(self, monkeypatch, tmp_path):
        db_path = tmp_path / "quant.db"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE stock_info (code TEXT PRIMARY KEY, name TEXT, industry TEXT)")
        conn.execute(
            """CREATE TABLE stock_daily (
                code TEXT,
                date TEXT,
                close REAL,
                volume REAL,
                amount REAL
            )"""
        )
        conn.execute(
            "INSERT INTO stock_info (code, name, industry) VALUES (?, ?, ?)",
            ("sh600519", "贵州茅台", "白酒"),
        )
        conn.execute(
            "INSERT INTO stock_daily (code, date, close, volume, amount) VALUES (?, ?, ?, ?, ?)",
            ("sh600519", "2026-05-22", 1688.0, 1000.0, 1688000.0),
        )
        conn.commit()
        conn.close()
        monkeypatch.setattr(qlib_router, "DB_PATH", db_path)

        info = qlib_router._enrich_with_stock_info(["600519"])

        assert info["600519"]["name"] == "贵州茅台"
        assert info["600519"]["industry"] == "白酒"
        assert info["600519"]["price"] == 1688.0

    def test_train_status_uses_configured_service_url(self, client, monkeypatch):
        """GET /api/qlib/train/status — 应使用配置的 qlib 服务地址"""

        called = {}

        class MockResponse:
            def json(self):
                return {"training": False}

        class MockAsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, url):
                called["url"] = url
                return MockResponse()

        monkeypatch.setattr(qlib_router.httpx, "AsyncClient", MockAsyncClient)

        resp = client.get("/api/qlib/train/status")

        assert resp.status_code == 200
        assert called["url"] == qlib_router.QLIB_TRAIN_STATUS_URL

    def test_train_failure_uses_signal_model_wording(self, client, monkeypatch):
        class MockAsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, url):
                raise RuntimeError("offline")

        monkeypatch.setattr(qlib_router.httpx, "AsyncClient", MockAsyncClient)

        resp = client.post("/api/qlib/train")

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is False
        assert "AI 信号模型服务不可用" in payload["message"]
        assert "qlib 服务不可用" not in payload["message"]
