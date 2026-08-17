"""Deterministic walk-forward validation for decision portfolio versions.

This is an offline validation adapter, not a replacement trading engine.  It
uses the same built-in strategy output adapter as the decision runtime and
records an explicit next-bar execution rule, cost model, calendar and data
coverage in its result.
"""

from __future__ import annotations

import math
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Mapping

from .domain import score_strategy_outputs
from .strategies import builtin_strategy_outputs
from engine.execution_model import (
    DEFAULT_A_SHARE_EXECUTION_CONTRACT,
    DEFAULT_A_SHARE_EXECUTION_COST_MODEL,
    ExecutionCostModelVersion,
    ExecutionDataContract,
    resolve_execution_cost_model,
    resolve_execution_contract,
)
from data.markets import TradingCalendar, get_market_adapter
from engine.market_rules import MarketRule, get_market_rule


# A validation result is allowed to tolerate a small number of legitimate
# missing sessions (for example a provider gap or a suspension), but a date
# span alone is not evidence of usable history.  Keep this threshold explicit
# and apply it both to the full sample and to every out-of-sample window.
MIN_HISTORY_COVERAGE_PCT = 80.0

_UUID_REF_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_SHA256_REF_RE = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$", re.IGNORECASE)


def _normalise_universe_snapshot_ref(value: Any) -> tuple[str | None, str | None]:
    """Accept only durable snapshot identifiers or content hashes.

    A non-empty label such as ``"latest"`` or ``"fixture-universe-v1"`` is
    not a frozen universe reference: it cannot identify an immutable input on
    replay.  UUIDs cover stored snapshot ids; SHA-256 references cover
    content-addressed snapshots.
    """

    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, "universe_snapshot_ref_not_a_string"
    text = value.strip()
    if not text:
        return None, "universe_snapshot_ref_required"
    if _UUID_REF_RE.fullmatch(text):
        return text.lower(), None
    if _SHA256_REF_RE.fullmatch(text):
        digest = text.split(":", 1)[-1].lower()
        return f"sha256:{digest}", None
    return None, "universe_snapshot_ref_invalid"


def is_valid_universe_snapshot_ref(value: Any) -> bool:
    """Return whether ``value`` can identify a frozen universe snapshot."""

    normalised, reason = _normalise_universe_snapshot_ref(value)
    return normalised is not None and reason is None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result > 0 else None


def _add_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(month_index, 12)
    month = month_index + 1
    # The windows start on a calendar date; clamp month-end dates instead of
    # silently changing the requested duration.
    days_in_month = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return date(year, month, min(value.day, days_in_month[month - 1]))


def _annualized(total_return: float, trading_days: int, annualization_days: int = 252) -> float:
    if trading_days <= 0:
        return 0.0
    base = max(0.0, 1.0 + total_return)
    return base ** (max(1, annualization_days) / trading_days) - 1.0


def _max_drawdown(returns: Iterable[float]) -> float:
    equity = 1.0
    peak = equity
    largest = 0.0
    for item in returns:
        equity *= 1.0 + item
        peak = max(peak, equity)
        if peak:
            largest = max(largest, 1.0 - equity / peak)
    return largest


def _calendar_name(value: Any, fallback: str = "adapter_calendar") -> str:
    return str(getattr(value, "name", fallback))


def _calendar_verified(value: Any) -> bool:
    marker = getattr(value, "is_verified_exchange_calendar", False)
    if callable(marker):
        try:
            marker = marker()
        except Exception:
            return False
    return marker is True


_CALENDAR_MARKET_ALIASES = {
    "SSE/SZSE": "CN",
    "SSE": "CN",
    "SZSE": "CN",
    "HKEX": "HK",
    "NYSE/NASDAQ": "US",
    "NYSE": "US",
    "NASDAQ": "US",
    "TSE": "JP",
    "JPX": "JP",
    "KRX": "KR",
    "TWSE": "TW",
}


def _resolve_calendar(value: Any) -> tuple[Any, str]:
    if value is not None and callable(getattr(value, "is_trading_day", None)):
        return value, _calendar_name(value)
    normalized = str(value or "").strip().upper()
    if normalized in {"CN", "A", "A_SHARE", "ASHARE", "ASHARES", "SSE/SZSE", "SSE", "SZSE", "ADAPTER_CALENDAR", ""}:
        calendar = get_market_adapter("CN").calendar
        return calendar, _calendar_name(calendar)
    normalized = _CALENDAR_MARKET_ALIASES.get(normalized, normalized)
    try:
        adapter = get_market_adapter(normalized)
    except KeyError:
        calendar = TradingCalendar(name="unresolved_calendar", source="unresolved_calendar", kind="unresolved")
        return calendar, _calendar_name(calendar, "unresolved_calendar")
    return adapter.calendar, _calendar_name(adapter.calendar)


def _normalise_history(
    history: Mapping[str, Iterable[Mapping[str, Any]]],
    *,
    calendar: Any = None,
    market_rule: MarketRule | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    normalised: dict[str, list[dict[str, Any]]] = {}
    reasons: list[str] = []
    calendar, _ = _resolve_calendar(calendar)
    market_rule = market_rule or get_market_rule("CN")
    for symbol, raw_bars in history.items():
        rows: list[dict[str, Any]] = []
        for raw in raw_bars:
            day = _parse_date(raw.get("date") or raw.get("bar_end"))
            close = _number(raw.get("close"))
            opening = _number(raw.get("open"))
            if day is None or close is None or opening is None:
                if day is not None:
                    reasons.append(f"{symbol}:missing_quote:{day.isoformat()}")
                continue
            if not calendar.is_trading_day(day):
                continue
            volume = raw.get("volume", 1.0)
            row = {
                "symbol": str(symbol),
                "date": day.isoformat(),
                "open": opening,
                "close": close,
                "volume": volume,
                "pre_close": raw.get("pre_close"),
                "status": raw.get("status"),
                "suspended": raw.get("suspended", False),
                "limit_up": raw.get("limit_up"),
                "limit_down": raw.get("limit_down"),
            }
            row["bar_block_reason"] = market_rule.execution_block_reason(
                str(symbol),
                None,
                open_price=opening,
                close_price=close,
                volume=volume,
                pre_close=raw.get("pre_close"),
                bar_status=raw.get("status"),
                suspended=raw.get("suspended", False),
                limit_up=raw.get("limit_up"),
                limit_down=raw.get("limit_down"),
            )
            rows.append(row)
        original_dates = [item["date"] for item in rows]
        rows.sort(key=lambda item: item["date"])
        if original_dates != sorted(original_dates):
            reasons.append(f"{symbol}:bars_out_of_order")
        if len(rows) != len({item["date"] for item in rows}):
            reasons.append(f"{symbol}:duplicate_dates")
            deduped = {item["date"]: item for item in rows}
            rows = [deduped[key] for key in sorted(deduped)]
        if not rows:
            reasons.append(f"{symbol}:no_valid_bars")
        normalised[str(symbol)] = rows
    return normalised, reasons


def _normalise_benchmark_history(
    history: Mapping[str, Iterable[Mapping[str, Any]]],
    *,
    calendar: Any = None,
) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """Normalise an explicit total-return index series.

    A price close is retained as a compatibility fallback so old callers get a
    deterministic diagnostic instead of a parser error, but that diagnostic is
    a hard validation failure.  Runtime qualification therefore cannot silently
    treat an ordinary price index as a total-return benchmark.
    """

    normalised: dict[str, list[dict[str, Any]]] = {}
    reasons: list[str] = []
    calendar, _ = _resolve_calendar(calendar)
    for symbol, raw_bars in history.items():
        rows: list[dict[str, Any]] = []
        for raw in raw_bars:
            day = _parse_date(raw.get("date") or raw.get("bar_end"))
            value = _number(raw.get("total_return_index"))
            if value is None:
                value = _number(raw.get("total_return"))
            if value is None:
                value = _number(raw.get("close"))
                if value is not None:
                    reasons.append(f"{symbol}:total_return_field_required")
            opening = _number(raw.get("open")) or value
            if day is None or value is None or opening is None:
                continue
            if not calendar.is_trading_day(day):
                continue
            rows.append({
                "date": day.isoformat(),
                "open": opening,
                "close": value,
                "total_return_index": value,
            })
        original_dates = [item["date"] for item in rows]
        rows.sort(key=lambda item: item["date"])
        if original_dates != sorted(original_dates):
            reasons.append(f"{symbol}:bars_out_of_order")
        if len(rows) != len({item["date"] for item in rows}):
            reasons.append(f"{symbol}:duplicate_dates")
            deduped = {item["date"]: item for item in rows}
            rows = [deduped[key] for key in sorted(deduped)]
        if not rows:
            reasons.append(f"{symbol}:no_valid_bars")
        normalised[str(symbol)] = rows
    return normalised, reasons


def _next_tradable_row(
    rows: list[dict[str, Any]],
    index: int,
    *,
    side: str,
    market_rule: MarketRule,
    calendar: Any,
) -> dict[str, Any] | None:
    """Find the next complete, directionally executable bar."""

    for candidate_index in range(index + 1, len(rows)):
        candidate = rows[candidate_index]
        day = _parse_date(candidate.get("date"))
        if day is None or not calendar.is_trading_day(day):
            continue
        reason = market_rule.execution_block_reason(
            str(candidate.get("symbol") or ""),
            side,
            open_price=candidate.get("open"),
            close_price=candidate.get("close"),
            volume=candidate.get("volume", 1.0),
            # Do not synthesize a previous close here.  A caller that has no
            # frozen pre-close/limit fields cannot prove a limit lock; using
            # the prior close would turn an otherwise valid fixture or
            # provider gap into a fabricated execution block.
            pre_close=candidate.get("pre_close"),
            bar_status=candidate.get("status"),
            suspended=candidate.get("suspended", False),
            limit_up=candidate.get("limit_up"),
            limit_down=candidate.get("limit_down"),
        )
        if reason is None:
            return candidate
    return None


@dataclass(frozen=True)
class ValidationWindow:
    ordinal: int
    train_start: str
    train_end: str
    out_of_sample_start: str
    out_of_sample_end: str
    trading_days: int
    observations: int
    signals: int
    annualized_return: float
    benchmark_annualized_return: float
    max_drawdown: float
    annualized_turnover: float
    passed: bool
    reason: str = ""
    expected_trading_days: int = 0
    coverage_pct: Mapping[str, float] = field(default_factory=dict)
    minimum_coverage_pct: float = MIN_HISTORY_COVERAGE_PCT

    def as_dict(self) -> dict[str, Any]:
        return {
            "ordinal": self.ordinal,
            "train_start": self.train_start,
            "train_end": self.train_end,
            "out_of_sample_start": self.out_of_sample_start,
            "out_of_sample_end": self.out_of_sample_end,
            "trading_days": self.trading_days,
            "observations": self.observations,
            "signals": self.signals,
            "annualized_return": self.annualized_return,
            "benchmark_annualized_return": self.benchmark_annualized_return,
            "max_drawdown": self.max_drawdown,
            "annualized_turnover": self.annualized_turnover,
            "passed": self.passed,
            "reason": self.reason,
            "expected_trading_days": self.expected_trading_days,
            "coverage_pct": dict(self.coverage_pct),
            "minimum_coverage_pct": self.minimum_coverage_pct,
        }


@dataclass(frozen=True)
class WalkForwardValidation:
    passed: bool
    windows: tuple[ValidationWindow, ...]
    reasons: tuple[str, ...]
    history_start: str | None
    history_end: str | None
    calendar: str
    execution_rule: str
    cost_model_version: str
    lookahead_safe: bool
    coverage: Mapping[str, int]
    coverage_pct: Mapping[str, float] = field(default_factory=dict)
    expected_trading_days: int = 0
    annualization_days: int = 252
    required_windows: int = 3
    max_drawdown_limit: float = 0.25
    annualized_turnover_limit: float = 12.0
    survivorship_bias_control: bool = False
    universe_snapshot_ref: str | None = None
    execution_contract: Mapping[str, Any] = field(default_factory=lambda: DEFAULT_A_SHARE_EXECUTION_CONTRACT.as_dict())
    calendar_source: str = ""
    calendar_verified: bool = False
    minimum_history_coverage_pct: float = MIN_HISTORY_COVERAGE_PCT

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "windows": [item.as_dict() for item in self.windows],
            "reasons": list(self.reasons),
            "history_start": self.history_start,
            "history_end": self.history_end,
            "calendar": self.calendar,
            "calendar_source": self.calendar_source,
            "calendar_verified": self.calendar_verified,
            "calendar_status": "verified_exchange" if self.calendar_verified else "unverified_fallback",
            "execution_rule": self.execution_rule,
            "cost_model_version": self.cost_model_version,
            "lookahead_safe": self.lookahead_safe,
            "coverage": dict(self.coverage),
            "coverage_pct": dict(self.coverage_pct),
            "expected_trading_days": self.expected_trading_days,
            "window_count": len(self.windows),
            "annualization_days": self.annualization_days,
            "required_windows": self.required_windows,
            "max_drawdown_limit": self.max_drawdown_limit,
            "annualized_turnover_limit": self.annualized_turnover_limit,
            "survivorship_bias_control": self.survivorship_bias_control,
            "universe_snapshot_ref": self.universe_snapshot_ref,
            "minimum_history_coverage_pct": self.minimum_history_coverage_pct,
            "hard_gates": {
                "max_drawdown": self.max_drawdown_limit,
                "annualized_turnover": self.annualized_turnover_limit,
                "survivorship_bias_control": self.survivorship_bias_control,
            },
            "execution_contract": dict(self.execution_contract),
        }


def walk_forward_validate(
    history: Mapping[str, Iterable[Mapping[str, Any]]],
    weights: Mapping[str, Mapping[str, Any]] | Iterable[Mapping[str, Any]],
    *,
    calendar: Any = "adapter_calendar",
    cost_model_version: str = "generic-assumption-v1",
    cost_bps: float | None = 10.0,
    min_history_months: int = 54,
    train_months: int = 24,
    out_of_sample_months: int = 6,
    step_months: int = 6,
    annualization_days: int = 252,
    required_windows: int = 3,
    max_drawdown_limit: float = 0.25,
    annualized_turnover_limit: float = 12.0,
    survivorship_bias_control: bool = False,
    universe_snapshot_ref: str | None = None,
    execution_contract: ExecutionDataContract | Mapping[str, Any] | None = None,
    cost_model: ExecutionCostModelVersion | Mapping[str, Any] | None = None,
    benchmark_history: Mapping[str, Iterable[Mapping[str, Any]]] | None = None,
    trading_calendar: Any = None,
    market_rule: MarketRule | None = None,
) -> WalkForwardValidation:
    """Evaluate a version on rolling, next-bar out-of-sample windows."""

    if min_history_months <= 0 or train_months <= 0 or out_of_sample_months <= 0 or step_months <= 0:
        raise ValueError("validation window durations must be positive")
    if required_windows <= 0:
        raise ValueError("required_windows must be positive")
    if max_drawdown_limit < 0 or annualized_turnover_limit < 0:
        raise ValueError("validation hard gates cannot be negative")
    if annualization_days <= 0:
        raise ValueError("annualization_days must be positive")
    reasons: list[str] = []
    supplied_cost_model = cost_model or (
        execution_contract.get("cost_model") if isinstance(execution_contract, Mapping) else None
    )
    use_legacy_flat_cost = (
        supplied_cost_model is None
        and cost_bps is not None
        and not (
            cost_model_version == DEFAULT_A_SHARE_EXECUTION_COST_MODEL.version
            and float(cost_bps) == 10.0
        )
    )
    resolved_cost = resolve_execution_cost_model(
        supplied_cost_model,
        version=None if isinstance(supplied_cost_model, Mapping) and supplied_cost_model.get("version") else cost_model_version,
        legacy_cost_bps=cost_bps if use_legacy_flat_cost else None,
    )
    contract = resolve_execution_contract(execution_contract, cost_model=resolved_cost)
    contract_market = str(contract.market or "CN")
    market_rule = market_rule or get_market_rule(contract_market)
    calendar_input = trading_calendar or calendar
    if (
        isinstance(calendar_input, str)
        and calendar_input.strip().lower() == "adapter_calendar"
        and isinstance(execution_contract, Mapping)
    ):
        calendar_input = execution_contract.get("calendar_name") or execution_contract.get("exchange_calendar") or calendar_input
    calendar_impl, calendar_label = _resolve_calendar(calendar_input)
    calendar_source = str(getattr(calendar_impl, "source", "unknown"))
    calendar_verified = _calendar_verified(calendar_impl)
    if calendar_label == "unresolved_calendar":
        reasons.append("calendar_unresolved")
    data, history_reasons = _normalise_history(history, calendar=calendar_impl, market_rule=market_rule)
    reasons.extend(history_reasons)
    if "next_tradable_bar_open" not in contract.execution_rule:
        reasons.append("execution_rule_not_next_tradable_bar_open")
    benchmark_data: dict[str, list[dict[str, Any]]] | None = None
    if benchmark_history is not None:
        benchmark_data, benchmark_reasons = _normalise_benchmark_history(benchmark_history, calendar=calendar_impl)
        reasons.extend(f"benchmark:{reason}" for reason in benchmark_reasons)
    else:
        reasons.append("benchmark_total_return_series_required")
    normalised_universe_ref, universe_ref_reason = _normalise_universe_snapshot_ref(universe_snapshot_ref)
    if universe_ref_reason is not None and (
        survivorship_bias_control or universe_snapshot_ref is not None
    ):
        reasons.append(universe_ref_reason)
    elif survivorship_bias_control and normalised_universe_ref is None:
        reasons.append("universe_snapshot_ref_required")
    all_dates = [date.fromisoformat(row["date"]) for rows in data.values() for row in rows]
    if not all_dates:
        empty_reasons = reasons + ["no_valid_history"]
        if not survivorship_bias_control:
            empty_reasons.append("survivorship_bias_control_required")
        return WalkForwardValidation(
            passed=False,
            windows=(),
            reasons=tuple(dict.fromkeys(empty_reasons)),
            history_start=None,
            history_end=None,
            calendar=calendar_label,
            execution_rule=contract.execution_rule,
            cost_model_version=resolved_cost.version,
            lookahead_safe=not any(reason.endswith(":bars_out_of_order") for reason in reasons),
            coverage={key: len(value) for key, value in data.items()},
            coverage_pct={},
            expected_trading_days=0,
            annualization_days=annualization_days,
            required_windows=required_windows,
            max_drawdown_limit=max_drawdown_limit,
            annualized_turnover_limit=annualized_turnover_limit,
            survivorship_bias_control=survivorship_bias_control,
            universe_snapshot_ref=normalised_universe_ref,
            execution_contract=contract.as_dict(),
            calendar_source=calendar_source,
            calendar_verified=calendar_verified,
            minimum_history_coverage_pct=MIN_HISTORY_COVERAGE_PCT,
        )

    history_start, history_end = min(all_dates), max(all_dates)
    if history_end < _add_months(history_start, min_history_months):
        reasons.append("history_shorter_than_4_5_years")

    expected_history_days = len(calendar_impl.trading_days(history_start, history_end))
    history_coverage_pct = {
        symbol: round(
            len({date.fromisoformat(item["date"]) for item in rows})
            / max(1, expected_history_days)
            * 100,
            2,
        )
        for symbol, rows in data.items()
    }
    if expected_history_days <= 0:
        reasons.append("calendar_has_no_expected_trading_days")
    sparse_symbols = [
        symbol
        for symbol, coverage_pct in history_coverage_pct.items()
        if coverage_pct < MIN_HISTORY_COVERAGE_PCT
    ]
    if sparse_symbols:
        reasons.append("history_coverage_below_minimum")
        reasons.extend(f"{symbol}:history_coverage_below_minimum" for symbol in sparse_symbols)

    windows: list[ValidationWindow] = []
    window_start = history_start
    ordinal = 0
    cost = resolved_cost
    while True:
        train_end = _add_months(window_start, train_months)
        oos_end = _add_months(train_end, out_of_sample_months)
        if oos_end > history_end:
            break
        daily_returns: dict[date, list[float]] = {}
        benchmark_returns: dict[date, list[float]] = {}
        signals = 0
        for symbol, rows in data.items():
            for index, row in enumerate(rows[:-1]):
                current_day = date.fromisoformat(row["date"])
                if current_day < train_end or current_day >= oos_end:
                    continue
                prior_rows = rows[: index + 1]
                names = [str(key) for key, item in (weights.items() if isinstance(weights, Mapping) else ((item.get("strategy_name"), item) for item in weights)) if item and item.get("enabled", True) and key]
                evaluation = score_strategy_outputs(builtin_strategy_outputs(prior_rows, names), weights)
                if evaluation.valid and evaluation.action == "buy_candidate":
                    next_row = _next_tradable_row(
                        rows,
                        index,
                        side="buy",
                        market_rule=market_rule,
                        calendar=calendar_impl,
                    )
                    if next_row is not None and date.fromisoformat(next_row["date"]) < oos_end:
                        signals += 1
                        daily_returns.setdefault(current_day, []).append(
                            cost.round_trip_return(next_row["open"], next_row["close"])
                        )
                    else:
                        daily_returns.setdefault(current_day, []).append(0.0)
                else:
                    daily_returns.setdefault(current_day, []).append(0.0)
        if benchmark_data:
            for _symbol, rows in benchmark_data.items():
                for index, row in enumerate(rows[:-1]):
                    current_day = date.fromisoformat(row["date"])
                    if current_day < train_end or current_day >= oos_end:
                        continue
                    next_row = rows[index + 1]
                    benchmark_returns.setdefault(current_day, []).append(
                        next_row["close"] / row["close"] - 1.0
                    )
        elif benchmark_history is not None:
            reasons.append("benchmark:no_valid_total_return_bars")
        if benchmark_history is not None:
            missing_benchmark_days = sorted(set(daily_returns) - set(benchmark_returns))
            if missing_benchmark_days:
                reasons.append("benchmark:coverage_mismatch")
        observation_days = sorted(set(benchmark_returns) | set(daily_returns))
        portfolio_returns = [
            sum(daily_returns[day]) / len(daily_returns[day])
            for day in observation_days
            if daily_returns.get(day)
        ]
        benchmark_series = [
            sum(benchmark_returns[day]) / len(benchmark_returns[day])
            for day in observation_days
            if benchmark_returns.get(day)
        ]
        if benchmark_history is not None and not benchmark_series:
            reasons.append("benchmark:no_overlapping_out_of_sample_bars")
        total_return = math.prod(1.0 + item for item in portfolio_returns) - 1.0 if portfolio_returns else 0.0
        benchmark_total = math.prod(1.0 + item for item in benchmark_series) - 1.0 if benchmark_series else 0.0
        trading_days = len(portfolio_returns)
        turnover = signals * 2.0 / trading_days * max(1, annualization_days) if trading_days else 0.0
        max_drawdown = _max_drawdown(portfolio_returns)
        annualized_turnover = turnover
        window_reasons: list[str] = []
        expected_window_days = len(calendar_impl.trading_days(train_end, oos_end - timedelta(days=1)))
        window_coverage_pct = {
            symbol: round(
                sum(
                    1
                    for item in rows
                    if train_end <= date.fromisoformat(item["date"]) < oos_end
                )
                / max(1, expected_window_days)
                * 100,
                2,
            )
            for symbol, rows in data.items()
        }
        if not trading_days or not portfolio_returns:
            window_reasons.append("no_out_of_sample_observations")
        if expected_window_days <= 0:
            window_reasons.append("no_expected_out_of_sample_trading_days")
        if any(value < MIN_HISTORY_COVERAGE_PCT for value in window_coverage_pct.values()):
            window_reasons.append("window_history_coverage_below_minimum")
        if max_drawdown > max_drawdown_limit:
            window_reasons.append("max_drawdown_exceeded")
        if annualized_turnover > annualized_turnover_limit:
            window_reasons.append("annualized_turnover_exceeded")
        window_passed = not window_reasons
        windows.append(
            ValidationWindow(
                ordinal=ordinal,
                train_start=window_start.isoformat(),
                train_end=train_end.isoformat(),
                out_of_sample_start=train_end.isoformat(),
                out_of_sample_end=oos_end.isoformat(),
                trading_days=trading_days,
                observations=trading_days,
                signals=signals,
                annualized_return=_annualized(total_return, trading_days, annualization_days),
                benchmark_annualized_return=_annualized(benchmark_total, len(benchmark_series), annualization_days),
                max_drawdown=max_drawdown,
                annualized_turnover=annualized_turnover,
                passed=window_passed,
                reason=";".join(window_reasons),
                expected_trading_days=expected_window_days,
                coverage_pct=window_coverage_pct,
                minimum_coverage_pct=MIN_HISTORY_COVERAGE_PCT,
            )
        )
        ordinal += 1
        window_start = _add_months(window_start, step_months)

    if len(windows) < required_windows:
        reasons.append("at_least_%d_out_of_sample_windows_required" % required_windows)
    if any(not item.passed for item in windows):
        reasons.append("out_of_sample_window_failed_hard_gate")
    if not survivorship_bias_control:
        reasons.append("survivorship_bias_control_required")
    return WalkForwardValidation(
        passed=not reasons and len(windows) >= required_windows,
        windows=tuple(windows),
        reasons=tuple(dict.fromkeys(reasons)),
        history_start=history_start.isoformat(),
        history_end=history_end.isoformat(),
        calendar=calendar_label,
        execution_rule=contract.execution_rule,
        cost_model_version=resolved_cost.version,
        lookahead_safe=not any(reason.endswith(":bars_out_of_order") for reason in reasons),
        coverage={key: len(value) for key, value in data.items()},
        coverage_pct=history_coverage_pct,
        expected_trading_days=expected_history_days,
        annualization_days=annualization_days,
        required_windows=required_windows,
        max_drawdown_limit=max_drawdown_limit,
        annualized_turnover_limit=annualized_turnover_limit,
        survivorship_bias_control=survivorship_bias_control,
        universe_snapshot_ref=normalised_universe_ref,
        execution_contract=contract.as_dict(),
        calendar_source=calendar_source,
        calendar_verified=calendar_verified,
        minimum_history_coverage_pct=MIN_HISTORY_COVERAGE_PCT,
    )


def select_weight_candidate(
    current: Mapping[str, Any],
    candidates: Iterable[Mapping[str, Any]],
    *,
    min_oos_improvement: float = 0.02,
    max_drawdown: float = 0.25,
    max_annualized_turnover: float = 12.0,
    max_single_asset_weight: float = 0.20,
) -> dict[str, Any]:
    """Choose a validated weight candidate with a stable, auditable order.

    The candidate payload is intentionally constrained to a mapping containing
    ``weights`` (or ``strategies``) and three out-of-sample metrics.  Invalid
    LLM or optimizer output is reported and discarded; it never becomes a
    free-form decision.
    """

    def metric(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    def metrics(item: Mapping[str, Any]) -> tuple[float | None, float | None, float | None, float | None]:
        nested = item.get("metrics") if isinstance(item.get("metrics"), Mapping) else {}
        return (
            metric(item.get("oos_annualized_return", nested.get("oos_annualized_return", nested.get("annualized_return")))),
            metric(item.get("max_drawdown", nested.get("max_drawdown"))),
            metric(item.get("annualized_turnover", nested.get("annualized_turnover"))),
            metric(item.get("max_single_asset_weight", nested.get("max_single_asset_weight", nested.get("single_asset_max_weight")))),
        )

    def content_digest(item: Mapping[str, Any]) -> str:
        canonical = {
            str(key): value
            for key, value in item.items()
            if str(key) not in {"content_hash", "candidate_hash"}
        }
        return hashlib.sha256(
            json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()

    def validate_weights(item: Mapping[str, Any]) -> list[str]:
        raw = item.get("weights", item.get("strategies"))
        if isinstance(raw, Mapping):
            entries = [{"strategy_name": name, "weight": value} for name, value in raw.items()]
        elif isinstance(raw, (list, tuple)):
            entries = list(raw)
        else:
            return ["candidate_schema_invalid"]
        if not entries:
            return ["candidate_weights_empty"]
        names: set[str] = set()
        total = 0.0
        reasons: list[str] = []
        for entry in entries:
            if not isinstance(entry, Mapping):
                reasons.append("candidate_weight_entry_invalid")
                continue
            name = str(entry.get("strategy_name") or entry.get("name") or "").strip()
            if not name:
                reasons.append("candidate_strategy_name_missing")
            elif name in names:
                reasons.append("candidate_strategy_duplicate")
            names.add(name)
            enabled = entry.get("enabled", True)
            if not isinstance(enabled, bool):
                reasons.append("candidate_strategy_enabled_invalid")
            try:
                weight = float(entry.get("weight"))
            except (TypeError, ValueError, OverflowError):
                reasons.append("candidate_weight_invalid")
                continue
            if not math.isfinite(weight) or weight < 0:
                reasons.append("candidate_weight_invalid")
                continue
            if enabled and not bool(entry.get("is_risk_veto", False)):
                total += weight
        if total <= 0:
            reasons.append("candidate_weight_sum_invalid")
        return list(dict.fromkeys(reasons))

    current_return, current_drawdown, current_turnover, current_single_weight = metrics(current)
    current_hash = content_digest(current)
    if current_return is None:
        raise ValueError("current version must have an out-of-sample annualized return")
    baseline = {
        "candidate_id": str(current.get("candidate_id") or current.get("version_id") or "current"),
        "content_hash": current_hash,
        "oos_annualized_return": current_return,
        "max_drawdown": current_drawdown,
        "annualized_turnover": current_turnover,
        "max_single_asset_weight": current_single_weight,
    }
    evaluated: list[dict[str, Any]] = []
    for raw in candidates:
        item = dict(raw) if isinstance(raw, Mapping) else {}
        reasons: list[str] = []
        reasons.extend(validate_weights(item))
        sample_ref = str(
            item.get("frozen_sample_ref")
            or item.get("validation_evidence_id")
            or item.get("validation_hash")
            or item.get("sample_ref")
            or ""
        ).strip()
        if not sample_ref:
            reasons.append("frozen_sample_reference_missing")
        supplied_hash = str(item.get("content_hash") or item.get("candidate_hash") or "").strip()
        if supplied_hash and supplied_hash != content_digest(item):
            reasons.append("candidate_content_hash_mismatch")
        candidate_return, candidate_drawdown, candidate_turnover, candidate_single_weight = metrics(item)
        if candidate_return is None or candidate_drawdown is None or candidate_turnover is None or candidate_single_weight is None:
            reasons.append("candidate_metrics_missing_or_invalid")
        if candidate_drawdown is not None and not 0 <= candidate_drawdown <= 1:
            reasons.append("max_drawdown_invalid")
        if candidate_turnover is not None and candidate_turnover < 0:
            reasons.append("annualized_turnover_invalid")
        if candidate_single_weight is not None and not 0 <= candidate_single_weight <= 1:
            reasons.append("single_asset_weight_invalid")
        if candidate_return is not None and candidate_return < current_return + min_oos_improvement:
            reasons.append("oos_improvement_below_threshold")
        if candidate_drawdown is not None and candidate_drawdown > max_drawdown:
            reasons.append("max_drawdown_exceeded")
        if candidate_turnover is not None and candidate_turnover > max_annualized_turnover:
            reasons.append("annualized_turnover_exceeded")
        if candidate_single_weight is not None and candidate_single_weight > max_single_asset_weight:
            reasons.append("single_asset_weight_exceeded")
        evaluated.append({
            "candidate_id": str(item.get("candidate_id") or item.get("version_id") or ""),
            "content_hash": content_digest(item),
            "oos_annualized_return": candidate_return,
            "max_drawdown": candidate_drawdown,
            "annualized_turnover": candidate_turnover,
            "max_single_asset_weight": candidate_single_weight,
            "eligible": not reasons,
            "reasons": list(dict.fromkeys(reasons)),
            "candidate": item,
        })

    eligible = [item for item in evaluated if item["eligible"]]
    eligible.sort(key=lambda item: (-item["oos_annualized_return"], item["max_drawdown"], item["annualized_turnover"], item["content_hash"]))
    selected = baseline
    if eligible:
        top = eligible[0]
        if (top["oos_annualized_return"], top["max_drawdown"], top["annualized_turnover"], top["content_hash"]) != (baseline["oos_annualized_return"], baseline["max_drawdown"], baseline["annualized_turnover"], baseline["content_hash"]):
            selected = top
    return {
        "selected": selected,
        "selected_candidate_id": selected["candidate_id"],
        "current": baseline,
        "candidates": evaluated,
        "selection_policy": {
            "min_oos_improvement": min_oos_improvement,
            "max_drawdown": max_drawdown,
            "max_annualized_turnover": max_annualized_turnover,
            "max_single_asset_weight": max_single_asset_weight,
            "sort": ["oos_annualized_return_desc", "max_drawdown_asc", "annualized_turnover_asc", "content_hash_asc"],
        },
    }


__all__ = [
    "MIN_HISTORY_COVERAGE_PCT",
    "ValidationWindow",
    "WalkForwardValidation",
    "is_valid_universe_snapshot_ref",
    "select_weight_candidate",
    "walk_forward_validate",
]
