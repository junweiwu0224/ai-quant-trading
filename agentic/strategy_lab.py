from dataclasses import dataclass
from typing import Any

from agentic.strategy_dsl import StrategyDSL, validate_strategy_dsl


@dataclass(frozen=True)
class PromotionGate:
    min_trades: int = 10
    max_drawdown: float = 0.15
    min_sharpe: float = 0.7


@dataclass(frozen=True)
class StrategyIterationResult:
    dsl: StrategyDSL
    metrics: dict[str, Any]
    promoted: bool
    reason: str


class StrategyLab:
    def __init__(self, promotion_gate: PromotionGate | None = None):
        self.promotion_gate = promotion_gate or PromotionGate()

    def evaluate_iteration(self, dsl: StrategyDSL, metrics: dict[str, Any]) -> StrategyIterationResult:
        validated_dsl = validate_strategy_dsl(dsl)
        gate = self.promotion_gate

        trades = metrics.get("trades", 0)
        max_drawdown = metrics.get("max_drawdown", 1)
        sharpe = metrics.get("sharpe", 0)

        if trades < gate.min_trades:
            return StrategyIterationResult(validated_dsl, metrics, False, "insufficient trades")
        if max_drawdown > gate.max_drawdown:
            return StrategyIterationResult(validated_dsl, metrics, False, "max drawdown exceeded")
        if sharpe < gate.min_sharpe:
            return StrategyIterationResult(validated_dsl, metrics, False, "sharpe below threshold")
        return StrategyIterationResult(validated_dsl, metrics, True, "passed promotion gate")
