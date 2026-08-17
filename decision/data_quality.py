"""Deterministic quality checks for market bars used by decisions.

The decision engine must never turn an incomplete quote into a positive signal.
This module is deliberately independent of pandas and providers so the same
rules can be used by snapshots, tests and replay.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping


REQUIRED_BAR_FIELDS = ("date", "open", "high", "low", "close", "volume")
PRICE_FIELDS = ("open", "high", "low", "close")
REVISION_FIELDS = ("revision", "revised", "provider_revision", "is_revision")


def parse_bar_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(text[:10])
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _finite_number(value: Any, *, allow_zero: bool = True) -> bool:
    if isinstance(value, bool):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return math.isfinite(number) and (allow_zero or number > 0)


@dataclass(frozen=True)
class BarQuality:
    valid: bool
    bar_count: int
    valid_bar_count: int
    latest_bar: str
    field_coverage: dict[str, float]
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "bar_count": self.bar_count,
            "valid_bar_count": self.valid_bar_count,
            "latest_bar": self.latest_bar,
            "field_coverage": dict(self.field_coverage),
            "reasons": list(self.reasons),
        }


def validate_bars(
    bars: Iterable[Mapping[str, Any]],
    *,
    minimum_bars: int = 30,
) -> BarQuality:
    """Validate a complete ordered bar series without repairing it.

    Any malformed row, duplicate timestamp, out-of-order timestamp or provider
    revision invalidates the series.  The caller may retain the raw rows for
    evidence, but must not feed an invalid series to a strategy.
    """

    items = [item for item in bars if isinstance(item, Mapping)]
    reasons: list[str] = []
    field_counts = {field: 0 for field in REQUIRED_BAR_FIELDS}
    parsed_times: list[datetime | None] = []
    valid_rows = 0

    for index, item in enumerate(items):
        row_reasons: list[str] = []
        for field in REQUIRED_BAR_FIELDS:
            if field not in item or item.get(field) is None or item.get(field) == "":
                row_reasons.append(f"missing:{field}")
            elif field == "date":
                if parse_bar_time(item.get(field)) is not None:
                    field_counts[field] += 1
            elif _finite_number(item.get(field), allow_zero=field == "volume"):
                field_counts[field] += 1
        bar_time = parse_bar_time(item.get("date"))
        parsed_times.append(bar_time)
        if bar_time is None:
            row_reasons.append("invalid:date")
        for field in PRICE_FIELDS:
            if not _finite_number(item.get(field), allow_zero=False):
                row_reasons.append(f"invalid:{field}")
        if not _finite_number(item.get("volume"), allow_zero=True):
            row_reasons.append("invalid:volume")
        if not row_reasons:
            try:
                opening = float(item["open"])
                high = float(item["high"])
                low = float(item["low"])
                close = float(item["close"])
                if high < max(opening, close) or low > min(opening, close) or low > high:
                    row_reasons.append("invalid:ohlc_relationship")
            except (TypeError, ValueError, OverflowError):
                row_reasons.append("invalid:ohlc")
        if any(bool(item.get(field)) for field in REVISION_FIELDS) or str(item.get("status") or "").lower() in {"revised", "revision"}:
            row_reasons.append("provider_revision")
        if row_reasons:
            reasons.extend(f"bar_{index}:{reason}" for reason in row_reasons)
        else:
            valid_rows += 1

    comparable_times = [value for value in parsed_times if value is not None]
    if len(comparable_times) != len(set(comparable_times)):
        reasons.append("duplicate_bar_time")
    if any(first >= second for first, second in zip(comparable_times, comparable_times[1:])):
        reasons.append("bars_out_of_order")

    coverage = {
        field: round(count / max(1, len(items)) * 100.0, 2)
        for field, count in field_counts.items()
    }
    latest = comparable_times[-1].isoformat(timespec="seconds") if comparable_times else ""
    if len(items) < max(1, int(minimum_bars)):
        reasons.append("insufficient_bar_coverage")
    valid = bool(items) and valid_rows == len(items) and len(items) >= max(1, int(minimum_bars)) and not reasons
    return BarQuality(
        valid=valid,
        bar_count=len(items),
        valid_bar_count=valid_rows,
        latest_bar=latest,
        field_coverage=coverage,
        reasons=tuple(dict.fromkeys(reasons)),
    )


__all__ = ["BarQuality", "REQUIRED_BAR_FIELDS", "parse_bar_time", "validate_bars"]
