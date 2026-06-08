from dataclasses import dataclass
from typing import Any


SUPPORTED_STRATEGY_TYPES = {"ranked_rotation", "threshold_signal", "mean_reversion"}
SUPPORTED_REBALANCE = {"daily", "weekly"}
SUPPORTED_RANK_BY = {"signal_score", "qlib_score", "momentum_20d", "volume_adjusted_momentum"}
SUPPORTED_UNIVERSES = {"signal_top", "qlib_top", "watchlist", "iwencai_pool", "hotspot_pool"}
SUPPORTED_FILTERS = {
    "close_above_ma",
    "drawdown_3d_between",
    "turnover_min",
    "volatility_max",
    "signal_score_min",
    "qlib_score_min",
}

LEGACY_UNIVERSE_ALIASES = {"qlib_top": "signal_top"}
LEGACY_RANK_BY_ALIASES = {"qlib_score": "signal_score"}
LEGACY_FILTER_ALIASES = {"qlib_score_min": "signal_score_min"}


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
    dsl = normalize_strategy_dsl(dsl)
    if dsl.strategy_type not in SUPPORTED_STRATEGY_TYPES:
        raise ValueError(f"unsupported strategy_type: {dsl.strategy_type}")
    if dsl.universe not in SUPPORTED_UNIVERSES:
        raise ValueError(f"unsupported universe: {dsl.universe}")
    if dsl.rebalance not in SUPPORTED_REBALANCE:
        raise ValueError(f"unsupported rebalance: {dsl.rebalance}")
    if dsl.rank_by not in SUPPORTED_RANK_BY:
        raise ValueError(f"unsupported rank_by: {dsl.rank_by}")
    if type(dsl.max_holdings) is not int or not 1 <= dsl.max_holdings <= 20:
        raise ValueError("max_holdings must be an integer between 1 and 20")
    if dsl.stop_loss is None or not 0 < float(dsl.stop_loss) <= 0.2:
        raise ValueError("stop_loss must be in (0, 0.2]")
    if dsl.take_profit is not None and not 0 < float(dsl.take_profit) <= 1:
        raise ValueError("take_profit must be in (0, 1]")
    if dsl.max_holding_days is not None and (type(dsl.max_holding_days) is not int or dsl.max_holding_days < 1):
        raise ValueError("max_holding_days must be a positive integer")
    if not isinstance(dsl.filters, list):
        raise ValueError("filters must be a list")
    for item in dsl.filters:
        if not isinstance(item, dict) or len(item) != 1:
            raise ValueError("each filter must be a single-key object")
        key = next(iter(item))
        if key not in SUPPORTED_FILTERS:
            raise ValueError(f"unsupported filter: {key}")
    return dsl


def normalize_strategy_dsl(dsl: StrategyDSL) -> StrategyDSL:
    filters = dsl.filters
    if isinstance(filters, list):
        filters = [
            {LEGACY_FILTER_ALIASES.get(key, key): value for key, value in item.items()}
            if isinstance(item, dict)
            else item
            for item in filters
        ]
    return StrategyDSL(
        strategy_type=dsl.strategy_type,
        universe=LEGACY_UNIVERSE_ALIASES.get(dsl.universe, dsl.universe),
        rank_by=LEGACY_RANK_BY_ALIASES.get(dsl.rank_by, dsl.rank_by),
        filters=filters,
        rebalance=dsl.rebalance,
        max_holdings=dsl.max_holdings,
        stop_loss=dsl.stop_loss,
        take_profit=dsl.take_profit,
        max_holding_days=dsl.max_holding_days,
    )


def legacy_aliases_for_dsl(original: StrategyDSL, normalized: StrategyDSL) -> dict[str, Any]:
    aliases: dict[str, Any] = {}
    if original.universe != normalized.universe:
        aliases["universe"] = original.universe
    if original.rank_by != normalized.rank_by:
        aliases["rank_by"] = original.rank_by
    filter_aliases = []
    if isinstance(original.filters, list):
        for item in original.filters:
            if not isinstance(item, dict):
                continue
            for key in item:
                if LEGACY_FILTER_ALIASES.get(key) in {next(iter(n)) for n in normalized.filters if isinstance(n, dict) and n}:
                    filter_aliases.append(key)
    if filter_aliases:
        aliases["filters"] = filter_aliases
    return aliases
