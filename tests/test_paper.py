"""模拟盘引擎测试"""
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config.settings import QLIB_SERVICE_URL
from data.collector.quote_service import QuoteData
from dashboard.routers.paper_control import _create_builtin_strategy
from engine.paper_engine import PaperConfig, PaperEngine, PaperStateManager, PaperTradeLog
from strategy.base import Bar, BaseStrategy, Direction, Portfolio, Trade


def make_quote(code: str, price: float, **kwargs) -> QuoteData:
    """创建测试用行情"""
    return QuoteData(
        code=code,
        name=kwargs.get("name", f"测试{code}"),
        price=price,
        open=kwargs.get("open", price),
        high=kwargs.get("high", price * 1.02),
        low=kwargs.get("low", price * 0.98),
        pre_close=kwargs.get("pre_close", price),
        volume=kwargs.get("volume", 100000),
        amount=kwargs.get("amount", price * 100000),
        change_pct=kwargs.get("change_pct", 0.0),
        timestamp=time.time(),
    )


class BuyOnceStrategy(BaseStrategy):
    """测试策略：首次收到行情时买入"""

    def __init__(self, buy_code: str = "000001", buy_volume: int = 1000):
        super().__init__()
        self._buy_code = buy_code
        self._buy_volume = buy_volume
        self._bought = False

    def on_bar(self, bar: Bar):
        if bar.code == self._buy_code and not self._bought:
            self.buy(bar.code, bar.close, self._buy_volume)
            self._bought = True


class SellAfterBuyStrategy(BaseStrategy):
    """测试策略：买入后下一轮卖出"""

    def __init__(self):
        super().__init__()
        self._step = 0

    def on_bar(self, bar: Bar):
        self._step += 1
        if self._step == 1:
            self.buy(bar.code, bar.close, 1000)
        elif self._step == 2:
            pos = self.portfolio.get_position(bar.code)
            if pos > 0:
                self.sell(bar.code, bar.close, pos)


# ── QuoteData 测试 ──

class TestQuoteData:
    def test_create_quote(self):
        q = make_quote("000001", 10.5)
        assert q.code == "000001"
        assert q.price == 10.5

    def test_frozen(self):
        q = make_quote("000001", 10.0)
        with pytest.raises(AttributeError):
            q.price = 11.0


# ── PaperTradeLog 测试 ──

class TestPaperTradeLog:
    def test_record_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = PaperTradeLog(tmpdir)
            trade = Trade(
                code="000001", direction=Direction.LONG,
                price=10.0, volume=1000, entry_price=0.0,
            )
            log.record(trade, 1_000_000)

            files = list(Path(tmpdir).glob("trades_*.jsonl"))
            assert len(files) == 1

            with open(files[0]) as f:
                entry = json.loads(f.readline())
            assert entry["code"] == "000001"
            assert entry["direction"] == "long"
            assert entry["volume"] == 1000

    def test_today_trades(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = PaperTradeLog(tmpdir)
            trade = Trade(
                code="000001", direction=Direction.LONG,
                price=10.0, volume=100, entry_price=0.0,
            )
            log.record(trade, 1_000_000)
            assert len(log.today_trades) == 1


# ── PaperStateManager 测试 ──

class TestPaperStateManager:
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = PaperStateManager(tmpdir)
            portfolio = Portfolio(cash=900_000, positions={"000001": 1000}, avg_prices={"000001": 10.0})

            mgr.save(portfolio)
            state = mgr.load()

            assert state is not None
            assert state["cash"] == 900_000
            assert state["positions"]["000001"] == 1000

    def test_load_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = PaperStateManager(tmpdir)
            assert mgr.load() is None

    def test_load_corrupted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = PaperStateManager(tmpdir)
            state_file = Path(tmpdir) / "portfolio_state.json"
            state_file.write_text("not valid json")
            assert mgr.load() is None


# ── PaperEngine 测试 ──

class TestPaperEngine:
    def test_create_builtin_qlib_strategy_uses_configured_service_url(self, monkeypatch):
        called = {}

        class StubQlibSignalStrategy:
            def __init__(self, buy_threshold=0.5, top_n=3):
                self.buy_threshold = buy_threshold
                self.top_n = top_n

            @classmethod
            def from_service(cls, service_url, **kwargs):
                called["service_url"] = service_url
                called["kwargs"] = kwargs
                return "stub-strategy"

        monkeypatch.setattr("strategy.qlib_signal.QlibSignalStrategy", StubQlibSignalStrategy)

        strategy = _create_builtin_strategy(
            "qlib_signal",
            StubQlibSignalStrategy,
            {"buy_threshold": 0.6, "top_n": 5},
        )

        assert strategy == "stub-strategy"
        assert called["service_url"] == QLIB_SERVICE_URL
        assert called["kwargs"]["buy_threshold"] == 0.6
        assert called["kwargs"]["top_n"] == 5

    def _make_engine(self, strategy=None, codes=None, tmpdir=None):
        """创建测试引擎"""
        codes = codes or ["000001"]
        strategy = strategy or BuyOnceStrategy(codes[0])
        state_dir = tmpdir or tempfile.mkdtemp()
        config = PaperConfig(
            interval_seconds=1,
            state_dir=state_dir,
            enable_risk=False,
            db_path=str(Path(state_dir) / "paper_trading_test.db"),
        )
        return PaperEngine(strategy=strategy, codes=codes, config=config)

    @patch("engine.paper_engine.get_quote_service")
    def test_run_once_buy(self, MockService):
        mock_service = MockService.return_value
        mock_service.get_all_quotes.return_value = {
            "000001": make_quote("000001", 10.0),
        }

        engine = self._make_engine()
        result = engine.run_once()

        assert "error" not in result
        assert result["new_trades"] == 1
        assert "000001" in result["positions"]
        assert result["positions"]["000001"] == 1000
        assert result["cash"] < 1_000_000

    @patch("engine.paper_engine.get_quote_service")
    def test_run_once_no_quotes(self, MockService):
        mock_service = MockService.return_value
        mock_service.get_all_quotes.return_value = {}

        engine = self._make_engine()
        result = engine.run_once()
        assert "error" in result

    @patch("engine.paper_engine.get_quote_service")
    def test_run_once_buy_and_sell(self, MockService):
        mock_service = MockService.return_value
        mock_service.get_all_quotes.side_effect = [
            {"000001": make_quote("000001", 10.0)},
            {"000001": make_quote("000001", 10.5)},
        ]

        strategy = SellAfterBuyStrategy()
        engine = self._make_engine(strategy=strategy)

        # 第一轮：买入
        result1 = engine.run_once()
        assert result1["new_trades"] == 1

        # T+1 结算（模拟次日）
        engine._today_bought.clear()
        engine._today_date = ""

        # 第二轮：卖出
        result2 = engine.run_once()
        assert result2["new_trades"] == 1
        assert "000001" not in result2["positions"] or result2["positions"]["000001"] == 0

    @patch("engine.paper_engine.get_quote_service")
    def test_state_persistence(self, MockService):
        mock_service = MockService.return_value
        mock_service.get_all_quotes.return_value = {
            "000001": make_quote("000001", 10.0),
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            # 第一次运行：买入
            engine1 = self._make_engine(tmpdir=tmpdir)
            engine1.run_once()

            # 第二次运行：恢复状态
            engine2 = self._make_engine(tmpdir=tmpdir)
            assert engine2.portfolio.positions.get("000001", 0) == 1000
            assert engine2.portfolio.cash < 1_000_000

    @patch("engine.paper_engine.get_quote_service")
    def test_insufficient_funds(self, MockService):
        mock_service = MockService.return_value
        mock_service.get_all_quotes.return_value = {
            "600519": make_quote("600519", 1800.0),
        }

        # 资金不够买 1000 股茅台
        config = PaperConfig(state_dir=tempfile.mkdtemp(), enable_risk=False)
        strategy = BuyOnceStrategy("600519", 1000)
        engine = PaperEngine(strategy=strategy, codes=["600519"], config=config)

        result = engine.run_once()
        assert result["new_trades"] == 0
        assert engine.portfolio.positions.get("600519", 0) == 0

    @patch("engine.paper_engine.get_quote_service")
    def test_commission_and_slippage(self, MockService):
        mock_service = MockService.return_value
        mock_service.get_all_quotes.return_value = {
            "000001": make_quote("000001", 10.0),
        }

        engine = self._make_engine()
        engine.run_once()

        # 现金应减少（含佣金和滑点）
        spent = engine._config.initial_cash - engine.portfolio.cash
        # 1000 * 10 * (1 + 0.002 slippage) = 10020 + commission
        assert spent > 10_020
        assert spent < 10_100  # 不应太多

    @patch("engine.paper_engine.get_quote_service")
    def test_stop_engine(self, MockService):
        mock_service = MockService.return_value
        mock_service.get_all_quotes.return_value = {
            "000001": make_quote("000001", 10.0),
        }

        engine = self._make_engine()
        engine._running = True
        engine.stop()
        assert engine._running is False
