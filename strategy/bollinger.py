"""布林带策略"""
from collections import deque

from strategy.base import Bar, BaseStrategy, Direction, Trade


class BollingerStrategy(BaseStrategy):
    """布林带均值回归策略

    价格突破下轨 → 买入（超卖反弹）
    价格突破上轨 → 卖出（超买回落）
    """

    def __init__(self, window: int = 20, num_std: float = 2.0, position_pct: float = 0.9):
        super().__init__()
        self.window = window
        self.num_std = num_std
        self.position_pct = position_pct
        self._closes: deque = deque(maxlen=window)
        self._holding = False

    def on_trade(self, trade: Trade):
        if trade.direction == Direction.LONG:
            self._holding = True
        elif trade.direction == Direction.SHORT:
            self._holding = False

    def on_bar(self, bar: Bar):
        self._closes.append(bar.close)

        if len(self._closes) < self.window:
            return

        closes = list(self._closes)
        n = len(closes)
        mean = sum(closes) / n
        variance = sum((c - mean) ** 2 for c in closes) / (n - 1)  # 样本标准差
        std = variance ** 0.5

        upper = mean + self.num_std * std
        lower = mean - self.num_std * std

        if not self._holding and bar.close < lower:
            volume = int(self.portfolio.cash * self.position_pct / bar.close / 100) * 100
            if volume >= 100:
                self.buy(bar.code, bar.close, volume)

        elif self._holding and bar.close > upper:
            pos = self.portfolio.get_position(bar.code)
            if pos > 0:
                self.sell(bar.code, bar.close, pos)
