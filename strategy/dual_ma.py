"""双均线策略"""
from collections import deque

from strategy.base import Bar, BaseStrategy, Direction, Trade


class DualMAStrategy(BaseStrategy):
    """经典双均线交叉策略

    短期均线上穿长期均线 → 买入
    短期均线下穿长期均线 → 卖出
    """

    def __init__(self, short_window: int = 5, long_window: int = 20, position_pct: float = 0.9):
        super().__init__()
        self.short_window = short_window
        self.long_window = long_window
        self.position_pct = position_pct
        self._closes: deque = deque(maxlen=long_window)
        self._holding = False

    def on_trade(self, trade: Trade):
        if trade.direction == Direction.LONG:
            self._holding = True
        elif trade.direction == Direction.SHORT:
            self._holding = False

    def on_bar(self, bar: Bar):
        self._closes.append(bar.close)

        if len(self._closes) < self.long_window:
            return

        short_ma = sum(list(self._closes)[-self.short_window:]) / self.short_window
        long_ma = sum(self._closes) / self.long_window

        if not self._holding and short_ma > long_ma:
            volume = int(self.portfolio.cash * self.position_pct / bar.close / 100) * 100
            if volume >= 100:
                self.buy(bar.code, bar.close, volume)

        elif self._holding and short_ma < long_ma:
            pos = self.portfolio.get_position(bar.code)
            if pos > 0:
                self.sell(bar.code, bar.close, pos)
