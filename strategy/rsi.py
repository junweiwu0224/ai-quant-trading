"""RSI 策略"""
from collections import deque

from strategy.base import Bar, BaseStrategy, Direction, Trade


class RSIStrategy(BaseStrategy):
    """RSI 超买超卖策略

    RSI 低于超卖线 → 买入
    RSI 高于超买线 → 卖出
    """

    def __init__(self, period: int = 14, oversold: float = 30, overbought: float = 70,
                 position_pct: float = 0.9):
        super().__init__()
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.position_pct = position_pct
        self._closes: deque = deque(maxlen=period + 1)
        self._holding = False

    def on_trade(self, trade: Trade):
        if trade.direction == Direction.LONG:
            self._holding = True
        elif trade.direction == Direction.SHORT:
            self._holding = False

    def _calc_rsi(self) -> float:
        closes = list(self._closes)
        gains, losses = [], []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            gains.append(max(diff, 0))
            losses.append(max(-diff, 0))
        avg_gain = sum(gains[-self.period:]) / self.period
        avg_loss = sum(losses[-self.period:]) / self.period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def on_bar(self, bar: Bar):
        self._closes.append(bar.close)

        if len(self._closes) < self.period + 1:
            return

        rsi = self._calc_rsi()

        if not self._holding and rsi < self.oversold:
            volume = int(self.portfolio.cash * self.position_pct / bar.close / 100) * 100
            if volume >= 100:
                self.buy(bar.code, bar.close, volume)

        elif self._holding and rsi > self.overbought:
            pos = self.portfolio.get_position(bar.code)
            if pos > 0:
                self.sell(bar.code, bar.close, pos)
