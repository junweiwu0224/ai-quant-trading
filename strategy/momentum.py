"""动量策略"""
from collections import deque

from strategy.base import Bar, BaseStrategy


class MomentumStrategy(BaseStrategy):
    """N日动量策略

    过去N日涨幅超过阈值 → 买入（趋势跟随）
    持仓后跌破止损线或涨幅回落 → 卖出
    """

    def __init__(
        self,
        lookback: int = 20,
        entry_threshold: float = 0.1,
        stop_loss: float = -0.05,
        take_profit: float = 0.2,
        position_pct: float = 0.9,
    ):
        super().__init__()
        self.lookback = lookback
        self.entry_threshold = entry_threshold
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.position_pct = position_pct
        self._closes: deque = deque(maxlen=lookback + 1)
        self._entry_price = 0.0

    def on_bar(self, bar: Bar):
        self._closes.append(bar.close)

        if len(self._closes) <= self.lookback:
            return

        # 计算N日动量
        past_close = self._closes[0]
        momentum = (bar.close - past_close) / past_close

        pos = self.portfolio.get_position(bar.code)

        if pos == 0:
            # 无持仓，动量超阈值则买入
            if momentum > self.entry_threshold:
                volume = int(self.portfolio.cash * self.position_pct / bar.close / 100) * 100
                if volume >= 100:
                    self.buy(bar.code, bar.close, volume)
                    self._entry_price = bar.close
        else:
            # 有持仓，检查止盈止损
            pnl_pct = (bar.close - self._entry_price) / self._entry_price
            if pnl_pct <= self.stop_loss or pnl_pct >= self.take_profit:
                self.sell(bar.code, bar.close, pos)
