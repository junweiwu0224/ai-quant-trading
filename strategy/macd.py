"""MACD 策略"""
from strategy.base import Bar, BaseStrategy, Direction, Trade


class MACDStrategy(BaseStrategy):
    """MACD 金叉死叉策略

    MACD 金叉（DIF 上穿 DEA）→ 买入
    MACD 死叉（DIF 下穿 DEA）→ 卖出
    """

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9,
                 position_pct: float = 0.9):
        super().__init__()
        self.fast = fast
        self.slow = slow
        self.signal = signal
        self.position_pct = position_pct
        self._ema_fast = 0.0
        self._ema_slow = 0.0
        self._dea = 0.0
        self._dif = 0.0
        self._prev_dif = 0.0
        self._prev_dea = 0.0
        self._count = 0
        self._holding = False

    def on_trade(self, trade: Trade):
        if trade.direction == Direction.LONG:
            self._holding = True
        elif trade.direction == Direction.SHORT:
            self._holding = False

    def _ema(self, prev: float, value: float, period: int) -> float:
        k = 2 / (period + 1)
        return value * k + prev * (1 - k)

    def on_bar(self, bar: Bar):
        self._count += 1

        if self._count == 1:
            self._ema_fast = bar.close
            self._ema_slow = bar.close
            return

        self._ema_fast = self._ema(self._ema_fast, bar.close, self.fast)
        self._ema_slow = self._ema(self._ema_slow, bar.close, self.slow)
        self._prev_dif = self._dif
        self._prev_dea = self._dea
        self._dif = self._ema_fast - self._ema_slow
        self._dea = self._ema(self._dea, self._dif, self.signal)

        if self._count < self.slow + self.signal:
            return

        golden_cross = self._prev_dif <= self._prev_dea and self._dif > self._dea
        death_cross = self._prev_dif >= self._prev_dea and self._dif < self._dea

        if not self._holding and golden_cross:
            volume = int(self.portfolio.cash * self.position_pct / bar.close / 100) * 100
            if volume >= 100:
                self.buy(bar.code, bar.close, volume)

        elif self._holding and death_cross:
            pos = self.portfolio.get_position(bar.code)
            if pos > 0:
                self.sell(bar.code, bar.close, pos)
