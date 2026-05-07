"""策略和回测引擎测试"""
from datetime import date

import pytest

from engine.backtest_engine import BacktestEngine, BacktestConfig
from strategy.base import Bar, BaseStrategy, Direction, Portfolio


class AlwaysBuyStrategy(BaseStrategy):
    """测试用策略：第一天全仓买入"""
    def on_bar(self, bar: Bar):
        if self.portfolio.get_position(bar.code) == 0:
            volume = int(self.portfolio.cash / bar.close / 100) * 100
            if volume >= 100:
                self.buy(bar.code, bar.close, volume)


class NeverTradeStrategy(BaseStrategy):
    """测试用策略：不交易"""
    def on_bar(self, bar: Bar):
        pass


def make_bars(code: str, closes: list[float], start: date = date(2024, 1, 2)) -> list[Bar]:
    """生成测试K线"""
    bars = []
    for i, c in enumerate(closes):
        d = date(start.year, start.month, start.day + i) if start.day + i <= 28 else start
        bars.append(Bar(
            code=code,
            date=date(2024, 1, 2 + i),
            open=c * 0.99,
            high=c * 1.02,
            low=c * 0.98,
            close=c,
            volume=100000,
            amount=c * 100000,
        ))
    return bars


@pytest.fixture
def db_with_data(tmp_path):
    """创建带测试数据的数据库"""
    import pandas as pd
    from data.storage.storage import DataStorage

    db_url = f"sqlite:///{tmp_path / 'test.db'}"
    storage = DataStorage(db_url=db_url)
    storage.init_db()

    # 写入股票信息
    info_df = pd.DataFrame({"code": ["000001"], "name": ["测试股票"], "industry": ["测试"], "list_date": ["2020-01-01"]})
    storage.save_stock_info(info_df)

    # 写入日K数据（30天）
    dates = pd.date_range("2024-01-02", periods=30, freq="B")
    closes = [10.0 + i * 0.1 for i in range(30)]  # 缓慢上涨
    daily_df = pd.DataFrame({
        "date": dates,
        "open": [c * 0.99 for c in closes],
        "high": [c * 1.02 for c in closes],
        "low": [c * 0.98 for c in closes],
        "close": closes,
        "volume": [100000] * 30,
        "amount": [c * 100000 for c in closes],
    })
    storage.save_stock_daily("000001", daily_df)

    return storage, db_url


class TestPortfolio:
    def test_initial_state(self):
        p = Portfolio(cash=100000)
        assert p.cash == 100000
        assert p.get_position("000001") == 0

    def test_market_value(self):
        p = Portfolio(cash=50000, positions={"000001": 1000})
        mv = p.get_market_value({"000001": 10.0})
        assert mv == 10000.0

    def test_total_equity(self):
        p = Portfolio(cash=50000, positions={"000001": 1000})
        eq = p.get_total_equity({"000001": 10.0})
        assert eq == 60000.0


class TestBacktestEngine:
    def test_no_trade_strategy(self, db_with_data):
        """不交易策略：权益不变"""
        _, db_url = db_with_data
        config = BacktestConfig(initial_cash=100000)
        engine = BacktestEngine(config)
        engine._storage = type(engine._storage)(db_url=db_url)

        result = engine.run(NeverTradeStrategy(), ["000001"], "20240102", "20240201")
        assert result.total_return == 0.0
        assert result.total_trades == 0

    def test_buy_and_hold(self, db_with_data):
        """买入持有策略：有交易记录"""
        _, db_url = db_with_data
        config = BacktestConfig(initial_cash=100000)
        engine = BacktestEngine(config)
        engine._storage = type(engine._storage)(db_url=db_url)

        result = engine.run(AlwaysBuyStrategy(), ["000001"], "20240102", "20240201")
        assert result.total_trades > 0
        assert result.final_equity > 0

    def test_result_summary_keys(self, db_with_data):
        """回测报告包含所有指标"""
        _, db_url = db_with_data
        config = BacktestConfig(initial_cash=100000)
        engine = BacktestEngine(config)
        engine._storage = type(engine._storage)(db_url=db_url)

        result = engine.run(NeverTradeStrategy(), ["000001"], "20240102", "20240201")
        summary = result.summary()
        assert "总收益率" in summary
        assert "最大回撤" in summary
        assert "夏普比率" in summary
        assert "胜率" in summary
