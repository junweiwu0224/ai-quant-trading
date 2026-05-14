"""多策略信号聚合"""
from strategy.base import Bar, BaseStrategy, Direction


class EnsembleStrategy(BaseStrategy):
    """多策略组合: 加权投票聚合信号"""

    def __init__(
        self,
        strategies: list[tuple[type, float]],
        aggregation: str = "weighted_average",
        buy_threshold: float = 0.3,
        sell_threshold: float = -0.3,
        position_pct: float = 0.9,
    ):
        super().__init__()
        self._strategy_specs = strategies
        self._aggregation = aggregation
        self._buy_threshold = buy_threshold
        self._sell_threshold = sell_threshold
        self._position_pct = position_pct
        self._instances: list[tuple[BaseStrategy, float]] = []

    def on_init(self):
        for cls, weight in self._strategy_specs:
            inst = cls()
            inst.init(self.portfolio)
            self._instances.append((inst, weight))

    def on_bar(self, bar: Bar):
        """运行所有子策略，聚合信号"""
        signals = []
        for strategy, weight in self._instances:
            before = len(strategy._pending_orders)
            strategy.on_bar(bar)
            new_orders = strategy._pending_orders[before:]
            for order in new_orders:
                signal = 1 if order.direction == Direction.LONG else -1
                signals.append(signal * weight)
            # 清除子策略的挂单（不直接提交给引擎）
            strategy._pending_orders = strategy._pending_orders[:before]

        if not signals:
            return

        if self._aggregation == "weighted_average":
            agg = sum(signals) / len(signals) if signals else 0
        elif self._aggregation == "majority_vote":
            buy_count = sum(1 for s in signals if s > 0)
            agg = 1 if buy_count > len(signals) / 2 else -1
        elif self._aggregation == "unanimous":
            if all(s > 0 for s in signals):
                agg = 1
            elif all(s < 0 for s in signals):
                agg = -1
            else:
                agg = 0
        else:
            agg = sum(signals) / len(signals) if signals else 0

        if agg >= self._buy_threshold:
            volume = int(self.portfolio.cash * self._position_pct / bar.close / 100) * 100
            if volume >= 100:
                self.buy(bar.code, bar.close, volume)
        elif agg <= self._sell_threshold:
            pos = self.portfolio.get_position(bar.code)
            if pos > 0:
                self.sell(bar.code, bar.close, pos)
