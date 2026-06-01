from __future__ import annotations

from dataclasses import dataclass
import math
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

        try:
            trades = _finite_metric(metrics, "trades")
            max_drawdown = _finite_metric(metrics, "max_drawdown")
            sharpe = _finite_metric(metrics, "sharpe")
        except ValueError as exc:
            return StrategyIterationResult(validated_dsl, metrics, False, str(exc))

        if not trades.is_integer() or trades < 0:
            return StrategyIterationResult(validated_dsl, metrics, False, "trades must be a non-negative integer")
        if max_drawdown < 0:
            return StrategyIterationResult(validated_dsl, metrics, False, "max_drawdown must be non-negative")

        if int(trades) < gate.min_trades:
            return StrategyIterationResult(validated_dsl, metrics, False, "insufficient trades")
        if max_drawdown > gate.max_drawdown:
            return StrategyIterationResult(validated_dsl, metrics, False, "max drawdown exceeded")
        if sharpe < gate.min_sharpe:
            return StrategyIterationResult(validated_dsl, metrics, False, "sharpe below threshold")
        return StrategyIterationResult(validated_dsl, metrics, True, "passed promotion gate")


def _finite_metric(metrics: dict[str, Any], key: str) -> float:
    if key not in metrics:
        raise ValueError(f"missing metric: {key}")
    try:
        value = float(metrics[key])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"metric {key} must be numeric") from exc
    if not math.isfinite(value):
        raise ValueError(f"metric {key} must be finite")
    return value
