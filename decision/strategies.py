"""Pure, versioned strategy adapters used by decisions and validation.

The decision runtime and the offline validator must evaluate the same strategy
implementation.  Keeping the small built-in adapter here prevents a second,
slightly different scoring implementation from appearing in the validator.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping


def _series(bars: Iterable[Mapping[str, Any]]) -> list[float]:
    values: list[float] = []
    for item in bars:
        try:
            value = float(item.get("close"))
        except (TypeError, ValueError):
            continue
        if value > 0:
            values.append(value)
    return values


def _clip(value: float) -> float:
    return max(0.0, min(100.0, value))


def builtin_strategy_outputs(
    bars: Iterable[Mapping[str, Any]],
    strategy_names: Iterable[str],
    *,
    strategy_version: str = "builtin-v1",
) -> list[dict[str, Any]]:
    """Return deterministic outputs for the currently supported built-ins.

    This adapter deliberately returns an invalid output for an enabled but
    unknown strategy.  Callers must not silently drop that strategy and make
    a partial score look valid.
    """

    bar_list = list(bars)
    closes = _series(bar_list)
    names = sorted({str(name) for name in strategy_names if str(name)})
    if len(closes) < 30:
        return [
            {
                "strategy_name": name,
                "strategy_version": strategy_version,
                "normalized_score": None,
                "confidence": 0,
                "data_quality": 0,
                "reason_codes": ["insufficient_history"],
            }
            for name in names
        ]

    last = closes[-1]
    twenty = closes[-21]
    short = sum(closes[-10:]) / 10
    long = sum(closes[-30:]) / 30
    recent_return = (last / twenty - 1) * 100
    trend_gap = (short / long - 1) * 100
    mean_gap = (last / long - 1) * 100
    high = max(closes[-60:])
    drawdown = (last / high - 1) * 100
    values: list[dict[str, Any]] = []
    for name in names:
        if name == "momentum":
            score = _clip(50 + recent_return * 4)
            reasons = ["positive_20d_return" if recent_return >= 0 else "negative_20d_return"]
        elif name == "trend":
            score = _clip(50 + trend_gap * 12)
            reasons = ["short_ma_above_long_ma" if short >= long else "short_ma_below_long_ma"]
        elif name == "mean_reversion":
            score = _clip(50 - mean_gap * 8)
            reasons = ["price_above_mean" if mean_gap >= 0 else "price_below_mean"]
        elif name == "drawdown_risk":
            values.append(
                {
                    "strategy_name": name,
                    "strategy_version": strategy_version,
                    "normalized_score": 0,
                    "confidence": 1,
                    "data_quality": 1,
                    "risk_veto": drawdown <= -20,
                    "reason_codes": ["drawdown_over_20pct" if drawdown <= -20 else "drawdown_within_limit"],
                }
            )
            continue
        else:
            values.append(
                {
                    "strategy_name": name,
                    "strategy_version": "unknown",
                    "normalized_score": None,
                    "confidence": 0,
                    "data_quality": 0,
                    "reason_codes": ["strategy_not_implemented"],
                }
            )
            continue
        values.append(
            {
                "strategy_name": name,
                "strategy_version": strategy_version,
                "normalized_score": round(score, 6),
                "confidence": 0.9,
                "data_quality": 1.0,
                "reason_codes": reasons,
            }
        )
    return values


__all__ = ["builtin_strategy_outputs"]
