"""KDJ 策略"""
from collections import deque

from strategy.base import Bar, BaseStrategy, Direction, Trade


class KDJStrategy(BaseStrategy):
    """KDJ 随机指标策略

    K 线上穿 D 线且 J 值超卖 → 买入
    K 线下穿 D 线且 J 值超买 → 卖出
    """

    def __init__(self, period: int = 9, k_period: int = 3, d_period: int = 3,
                 oversold: float = 20, overbought: float = 80,
                 position_pct: float = 0.9):
        super().__init__()
        self.period = period
        self.k_period = k_period
        self.d_period = d_period
        self.oversold = oversold
        self.overbought = overbought
        self.position_pct = position_pct
        self._highs: deque = deque(maxlen=period)
        self._lows: deque = deque(maxlen=period)
        self._k = 50.0
        self._d = 50.0
        self._prev_k = 50.0
        self._prev_d = 50.0
        self._count = 0
        self._holding = False

    def on_trade(self, trade: Trade):
        if trade.direction == Direction.LONG:
            self._holding = True
        elif trade.direction == Direction.SHORT:
            self._holding = False

    def on_bar(self, bar: Bar):
        self._count += 1
        self._highs.append(bar.high)
        self._lows.append(bar.low)

        if len(self._highs) < self.period:
            return

        highest = max(self._highs)
        lowest = min(self._lows)

        if highest == lowest:
            rsv = 50.0
        else:
            rsv = (bar.close - lowest) / (highest - lowest) * 100

        self._prev_k = self._k
        self._prev_d = self._d
        self._k = (2 / self.k_period) * rsv + (1 - 2 / self.k_period) * self._k
        self._d = (2 / self.d_period) * self._k + (1 - 2 / self.d_period) * self._d
        j = 3 * self._k - 2 * self._d

        golden_cross = self._prev_k <= self._prev_d and self._k > self._d
        death_cross = self._prev_k >= self._prev_d and self._k < self._d

        if not self._holding and golden_cross and j < self.oversold:
            volume = int(self.portfolio.cash * self.position_pct / bar.close / 100) * 100
            if volume >= 100:
                self.buy(bar.code, bar.close, volume)

        elif self._holding and death_cross and j > self.overbought:
            pos = self.portfolio.get_position(bar.code)
            if pos > 0:
                self.sell(bar.code, bar.close, pos)
