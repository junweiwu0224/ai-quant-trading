"""实盘交易引擎测试"""
import tempfile
import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from data.collector.quote_service import QuoteData
from engine.broker import AccountInfo, OrderResult, OrderSide, OrderStatus, PositionInfo, SimulatedBroker
from engine.live_engine import LiveConfig, LiveTradingEngine, LivePortfolioAdapter
from strategy.base import Bar, BaseStrategy, Direction, Portfolio


def make_quote(code: str, price: float) -> QuoteData:
    return QuoteData(
        code=code, name=f"测试{code}", price=price,
        open=price, high=price * 1.02, low=price * 0.98,
        pre_close=price, volume=100000, amount=price * 100000,
        change_pct=0.0, timestamp=time.time(),
    )


class BuyOnceStrategy(BaseStrategy):
    def __init__(self, code="000001", vol=1000):
        super().__init__()
        self._code = code
        self._vol = vol
        self._bought = False

    def on_bar(self, bar: Bar):
        if bar.code == self._code and not self._bought:
            self.buy(bar.code, bar.close, self._vol)
            self._bought = True


# ── SimulatedBroker 测试 ──

class TestSimulatedBroker:
    def test_connect_disconnect(self):
        broker = SimulatedBroker()
        assert broker.connect() is True
        assert broker.is_connected() is True
        broker.disconnect()
        assert broker.is_connected() is False

    def test_get_account_initial(self):
        broker = SimulatedBroker(initial_cash=500_000)
        broker.connect()
        account = broker.get_account()
        assert account.total_equity == 500_000
        assert account.cash == 500_000
        assert account.market_value == 0

    def test_buy_order(self):
        broker = SimulatedBroker()
        broker.connect()
        broker.set_price("000001", 10.0)

        result = broker.place_order("000001", OrderSide.BUY, 10.0, 1000)
        assert result.status == OrderStatus.FILLED
        assert result.filled_volume == 1000

        positions = broker.get_positions()
        assert len(positions) == 1
        assert positions[0].code == "000001"
        assert positions[0].volume == 1000

    def test_sell_order(self):
        broker = SimulatedBroker()
        broker.connect()
        broker.set_price("000001", 10.0)

        # 先买入
        broker.place_order("000001", OrderSide.BUY, 10.0, 1000)
        # T+1 结算
        broker.settle_t1()
        # 卖出
        result = broker.place_order("000001", OrderSide.SELL, 10.5, 1000)
        assert result.status == OrderStatus.FILLED

        positions = broker.get_positions()
        assert len(positions) == 0

    def test_sell_insufficient(self):
        broker = SimulatedBroker()
        broker.connect()

        result = broker.place_order("000001", OrderSide.SELL, 10.0, 1000)
        assert result.status == OrderStatus.REJECTED
        assert "无可卖" in result.message

    def test_buy_insufficient_funds(self):
        broker = SimulatedBroker(initial_cash=1000)
        broker.connect()
        broker.set_price("000001", 10.0)

        result = broker.place_order("000001", OrderSide.BUY, 10.0, 1000)
        assert result.status == OrderStatus.REJECTED
        assert "资金不足" in result.message

    def test_not_connected(self):
        broker = SimulatedBroker()
        result = broker.place_order("000001", OrderSide.BUY, 10.0, 100)
        assert result.status == OrderStatus.REJECTED

    def test_commission_deducted(self):
        broker = SimulatedBroker(initial_cash=100_000)
        broker.connect()
        broker.set_price("000001", 10.0)

        broker.place_order("000001", OrderSide.BUY, 10.0, 1000)
        account = broker.get_account()
        # cost = 10000 + commission(~5) = ~10005
        assert account.cash < 90_000
        assert account.cash > 89_990

    def test_cancel_order(self):
        broker = SimulatedBroker()
        broker.connect()
        # 模拟券商直接成交，撤单应返回 False
        broker.set_price("000001", 10.0)
        result = broker.place_order("000001", OrderSide.BUY, 10.0, 100)
        assert broker.cancel_order(result.order_id) is False  # 已成交

    def test_t1_settle(self):
        broker = SimulatedBroker()
        broker.connect()
        broker.set_price("000001", 10.0)

        broker.place_order("000001", OrderSide.BUY, 10.0, 1000)
        positions = broker.get_positions()
        assert positions[0].available == 0  # T+1，当日不可卖

        broker.settle_t1()
        positions = broker.get_positions()
        assert positions[0].available == 1000  # 结算后可卖


# ── LivePortfolioAdapter 测试 ──

class TestLivePortfolioAdapter:
    def test_get_account_snapshot(self):
        broker = SimulatedBroker()
        broker.connect()
        broker.set_price("000001", 10.0)
        broker.place_order("000001", OrderSide.BUY, 10.0, 1000)

        adapter = LivePortfolioAdapter(broker)
        snapshot = adapter.get_account_snapshot()
        assert snapshot["cash"] < 1_000_000
        assert "000001" in snapshot["positions"]

    def test_record_equity(self):
        broker = SimulatedBroker()
        adapter = LivePortfolioAdapter(broker)
        adapter.record_equity(datetime.now().date(), 1_000_000)
        assert len(adapter.equity_curve) == 1


# ── LiveTradingEngine 测试 ──

class TestLiveTradingEngine:
    @patch("engine.live_engine.get_quote_service")
    def test_run_once_dry_run(self, MockService):
        mock_service = MockService.return_value
        mock_service.get_all_quotes.return_value = {
            "000001": make_quote("000001", 10.0),
        }

        broker = SimulatedBroker()
        config = LiveConfig(
            interval_seconds=1,
            state_dir=tempfile.mkdtemp(),
            enable_risk=False,
            dry_run=True,
        )
        strategy = BuyOnceStrategy()
        engine = LiveTradingEngine(
            strategy=strategy, codes=["000001"],
            broker=broker, config=config,
        )

        result = engine.run_once()
        assert "error" not in result
        assert result["new_trades"] == 1
        assert "000001" in result["positions"]

    @patch("engine.live_engine.get_quote_service")
    def test_run_once_no_quotes(self, MockService):
        mock_service = MockService.return_value
        mock_service.get_all_quotes.return_value = {}

        broker = SimulatedBroker()
        config = LiveConfig(state_dir=tempfile.mkdtemp(), enable_risk=False)
        engine = LiveTradingEngine(
            strategy=BuyOnceStrategy(), codes=["000001"],
            broker=broker, config=config,
        )

        result = engine.run_once()
        assert "error" in result

    @patch("engine.live_engine.get_quote_service")
    def test_stop_engine(self, MockService):
        mock_service = MockService.return_value
        mock_service.get_all_quotes.return_value = {}

        broker = SimulatedBroker()
        config = LiveConfig(state_dir=tempfile.mkdtemp(), enable_risk=False)
        engine = LiveTradingEngine(
            strategy=BuyOnceStrategy(), codes=["000001"],
            broker=broker, config=config,
        )

        engine._running = True
        engine.stop()
        assert engine._running is False

    @patch("engine.live_engine.get_quote_service")
    def test_insufficient_funds(self, MockService):
        mock_service = MockService.return_value
        mock_service.get_all_quotes.return_value = {
            "600519": make_quote("600519", 1800.0),
        }

        broker = SimulatedBroker(initial_cash=100_000)
        config = LiveConfig(state_dir=tempfile.mkdtemp(), enable_risk=False)
        strategy = BuyOnceStrategy("600519", 1000)
        engine = LiveTradingEngine(
            strategy=strategy, codes=["600519"],
            broker=broker, config=config,
        )

        result = engine.run_once()
        assert result["new_trades"] == 0

    def test_no_broker_live_mode(self):
        """实盘模式不提供 broker 应报错"""
        config = LiveConfig(dry_run=False)
        with pytest.raises(ValueError, match="必须提供 broker"):
            LiveTradingEngine(
                strategy=BuyOnceStrategy(), codes=["000001"],
                broker=None, config=config,
            )
