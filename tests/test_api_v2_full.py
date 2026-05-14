"""Phase 2: 全量 API 自动化测试

使用 FastAPI TestClient（无需启动真实服务器），
按路由器分组覆盖所有核心端点。

运行方式:
    pytest tests/test_api_v2_full.py -v --tb=short
    pytest tests/test_api_v2_full.py -v --tb=short -x  # 首次失败即停
"""
import sqlite3
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from dashboard.app import app
from dashboard.routers import qlib as qlib_router
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

    def test_get_watchlist(self, client):
        """GET /api/watchlist — 自选股列表"""
        resp = client.get("/api/watchlist")
        assert resp.status_code == 200

    def test_add_watchlist_rejects_invalid_code(self, client):
        resp = client.post("/api/watchlist", json={"code": "600519.SH"})
        assert resp.status_code == 400

    def test_add_watchlist_rejects_unknown_code(self, client, monkeypatch):
        from dashboard.routers import watchlist as watchlist_router

        class FakeCollector:
            def get_stock_list(self):
                return pd.DataFrame({"code": ["000001"], "name": ["平安银行"]})

        monkeypatch.setattr(
            "data.collector.collector.StockCollector",
            lambda: FakeCollector(),
        )
        monkeypatch.setattr(watchlist_router.storage, "get_stock_list", lambda: pd.DataFrame())

        resp = client.post("/api/watchlist", json={"code": "123456"})

        assert resp.status_code == 404

    def test_remove_watchlist_normalizes_code_before_unsubscribe(self, client, monkeypatch):
        from dashboard.routers import watchlist as watchlist_router

        calls = {}
        monkeypatch.setattr(watchlist_router.storage, "remove_from_watchlist", lambda code: calls.setdefault("removed", code) == "600519")
        monkeypatch.setattr(
            watchlist_router,
            "get_quote_service",
            lambda: type("QS", (), {"unsubscribe": lambda self, codes: calls.setdefault("unsubscribed", list(codes))})(),
        )

        resp = client.delete("/api/watchlist/sh600519")

        assert resp.status_code == 200
        assert calls["removed"] == "600519"
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
        assert resp.status_code in (200, 422)

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

    def test_market_sectors(self, client):
        """GET /api/market/sectors — 板块数据"""
        resp = client.get("/api/market/sectors")
        assert resp.status_code == 200

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
#  qlib 预测
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestQlib:
    """qlib 预测端点"""

    def test_top_predictions(self, client):
        """GET /api/qlib/top — Top N 预测"""
        resp = client.get("/api/qlib/top")
        assert resp.status_code == 200

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
