from dataclasses import dataclass
from typing import Any


SUPPORTED_STRATEGY_TYPES = {"ranked_rotation", "threshold_signal", "mean_reversion"}
SUPPORTED_REBALANCE = {"daily", "weekly"}
SUPPORTED_RANK_BY = {"qlib_score", "momentum_20d", "volume_adjusted_momentum"}


@dataclass(frozen=True)
class StrategyDSL:
    strategy_type: str
    universe: str
    rank_by: str
    filters: list[dict[str, Any]]
    rebalance: str
    max_holdings: int
    stop_loss: float
    take_profit: float | None
    max_holding_days: int | None


def validate_strategy_dsl(dsl: StrategyDSL) -> StrategyDSL:
    if dsl.strategy_type not in SUPPORTED_STRATEGY_TYPES:
        raise ValueError(f"unsupported strategy_type: {dsl.strategy_type}")
    if dsl.rebalance not in SUPPORTED_REBALANCE:
        raise ValueError(f"unsupported rebalance: {dsl.rebalance}")
    if dsl.rank_by not in SUPPORTED_RANK_BY:
        raise ValueError(f"unsupported rank_by: {dsl.rank_by}")
    if not 1 <= dsl.max_holdings <= 20:
        raise ValueError("max_holdings must be between 1 and 20")
    if dsl.stop_loss is None or not 0 < dsl.stop_loss <= 0.2:
        raise ValueError("stop_loss must be in (0, 0.2]")
    return dsl
