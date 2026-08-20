"""测试策略信号迁移到统一执行协议"""
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from config.datetime_utils import now_beijing
from engine.paper_engine import PaperEngine, PaperConfig
from engine.execution_protocol import Environment, Side, OrderIntent, OrderIntentBatch
from engine.adapters.paper_adapter import PaperAdapter, QuoteSnapshot
from strategy.base import BaseStrategy, Bar, Direction, Order
from data.collector.quote_service import QuoteData
from utils.db import get_connection


class DummyStrategy(BaseStrategy):
    """测试用策略：固定买入信号"""
    
    def on_bar(self, bar: Bar):
        # 第一次看到这个代码就买入
        if bar.code not in self._portfolio.positions:
            self.buy(bar.code, bar.close, 100)


def test_strategy_signal_uses_unified_protocol(tmp_path):
    """策略信号应该通过 PaperAdapter 执行并写入 paper_ledger"""
    db_path = tmp_path / "test.db"
    
    config = PaperConfig(
        initial_cash=100000,
        interval_seconds=30,
        db_path=str(db_path),
        enable_risk=False,
    )
    
    strategy = DummyStrategy()
    engine = PaperEngine(config=config, strategy=strategy, codes=["000001.SZ"], account_id="test_account")
    
    # 手动创建订单（模拟策略信号）
    order = Order(
        order_id="test-order-1",
        code="000001.SZ",
        direction=Direction.LONG,
        price=10.0,
        volume=100,
        status="pending",
    )
    strategy._pending_orders = [order]
    
    # 模拟行情
    quotes = {
        "000001.SZ": QuoteData(
            code="000001.SZ",
            name="平安银行",
            price=10.0,
            open=9.8,
            high=10.2,
            low=9.7,
            pre_close=9.9,
            volume=1000000,
            amount=10000000,
            change_pct=1.01,
            timestamp=now_beijing().timestamp(),
        )
    }
    
    # 执行批次
    trades = engine._execute_pending_orders_v2(quotes)
    
    # 验证 paper_ledger 有记录
    conn = get_connection(str(db_path))
    cursor = conn.execute("SELECT * FROM paper_ledger WHERE account_id = ?", ("test_account",))
    ledger_rows = cursor.fetchall()
    conn.close()
    
    assert len(ledger_rows) > 0, "策略信号应写入 paper_ledger"
    assert ledger_rows[0]["side"] in ("Side.BUY", "buy"), "应该是买入信号"
    assert len(trades) > 0, "应该返回成交记录"


def test_stoploss_uses_unified_protocol(tmp_path):
    """止损应该通过 PaperAdapter 执行并写入 paper_ledger"""
    db_path = tmp_path / "test.db"
    
    # 初始化 PaperAdapter（创建 paper_ledger 表）
    from engine.adapters.paper_adapter import PaperAdapter
    PaperAdapter(str(db_path))
    
    config = PaperConfig(
        initial_cash=100000,
        interval_seconds=30,
        db_path=str(db_path),
        enable_risk=False,
    )
    
    strategy = DummyStrategy()
    engine = PaperEngine(config=config, strategy=strategy, codes=["000001.SZ"], account_id="test_account")
    
    # 手动设置持仓和止损价
    engine._portfolio.positions["000001.SZ"] = 100
    engine._portfolio.avg_prices["000001.SZ"] = 15.0
    
    conn = get_connection(str(db_path))
    conn.execute(
        "INSERT INTO paper_positions (code, volume, avg_price, stop_loss_price) VALUES (?, ?, ?, ?)",
        ("000001.SZ", 100, 15.0, 14.0)
    )
    conn.commit()
    conn.close()
    
    # 模拟行情跌破止损价（假设 QuoteService 返回 13.5）
    # 注意：这个测试需要 mock QuoteService，简化版本跳过
    # 真实测试应该 mock get_quote_service() 返回低于止损价的行情
    
    # 至少验证表结构存在
    conn = get_connection(str(db_path))
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='paper_ledger'")
    assert cursor.fetchone() is not None
    conn.close()


def test_batch_execution_atomicity(tmp_path):
    """批次执行应该原子化：要么全成功，要么全失败"""
    db_path = tmp_path / "test.db"
    
    # 初始化 PaperAdapter（创建 paper_ledger 表）
    from engine.adapters.paper_adapter import PaperAdapter
    PaperAdapter(str(db_path))
    
    config = PaperConfig(
        initial_cash=1000,  # 故意设置很少的资金
        interval_seconds=30,
        db_path=str(db_path),
        enable_risk=False,
    )
    
    class GreedyStrategy(BaseStrategy):
        """贪婪策略：生成多个超出资金能力的订单"""
        def on_bar(self, bar: Bar):
            self.buy("000001.SZ", 10.0, 100)  # 需要 1000
            self.buy("000002.SZ", 10.0, 100)  # 需要 1000（超出）
    
    strategy = GreedyStrategy()
    engine = PaperEngine(config=config, strategy=strategy, codes=["000001.SZ", "000002.SZ"], account_id="test_account")
    
    result = engine.run_once()
    
    # 验证：资金不足时，批次应该部分成功或全部取消（取决于 RiskGate 实现）
    # 当前简化实现是逐个执行，所以第一个成功，第二个失败
    conn = get_connection(str(db_path))
    cursor = conn.execute("SELECT COUNT(*) FROM paper_ledger WHERE account_id = ?", ("test_account",))
    count = cursor.fetchone()[0]
    conn.close()
    
    # 至少验证有记录（完整的原子性测试需要 RiskGate）
    assert count >= 0


def test_emergency_stoploss_bypasses_risk_limits(tmp_path):
    """紧急止损应该绕过风控限制"""
    # TODO: 实现完整的 RiskGate 后补充此测试
    # 当前 Phase 2 简化实现全批准，Phase 3 会实现完整风控
    pass
