"""Validation metrics for signal providers."""
from __future__ import annotations

import math
import sqlite3
import time
from pathlib import Path
from typing import Any

from config.settings import DB_PATH, QLIB_PRED_CACHE
from data.signals.engine import DEFAULT_PROVIDER, load_prediction_history
from data.signals.models import SignalValidationSummary, plain_code

_VALIDATION_CACHE: dict[tuple[str, str, int, int | None, int | None], dict[str, Any]] = {}


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _rank(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(indexed):
        end = index + 1
        while end < len(indexed) and math.isclose(indexed[end][1], indexed[index][1], rel_tol=1e-12, abs_tol=1e-12):
            end += 1
        avg = (index + end - 1) / 2 + 1
        for original_index, _ in indexed[index:end]:
            ranks[original_index] = avg
        index = end
    return ranks


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    return _pearson(_rank(xs), _rank(ys))


def _load_dates(db_path: Path) -> list[str]:
    path = Path(db_path)
    if not path.exists():
        return []
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute("SELECT DISTINCT date FROM stock_daily ORDER BY date").fetchall()
    finally:
        conn.close()
    return [str(row[0]) for row in rows if row and row[0]]


def _load_close_matrix(
    db_path: Path,
    *,
    codes: set[str],
    dates: set[str],
) -> dict[str, dict[str, float]]:
    path = Path(db_path)
    if not path.exists() or not codes or not dates:
        return {}
    storage_codes: set[str] = set()
    for code in codes:
        storage_codes.add(code)
        if code.startswith("6"):
            storage_codes.add(f"sh{code}")
        elif code.startswith(("0", "3", "9")):
            storage_codes.add(f"sz{code}")
    conn = sqlite3.connect(path)
    try:
        code_placeholders = ",".join("?" * len(storage_codes))
        date_placeholders = ",".join("?" * len(dates))
        rows = conn.execute(
            f"""SELECT code, date, close
                FROM stock_daily
                WHERE code IN ({code_placeholders})
                  AND date IN ({date_placeholders})
                ORDER BY date, code""",
            [*storage_codes, *dates],
        ).fetchall()
    finally:
        conn.close()
    closes: dict[str, dict[str, float]] = {}
    for raw_code, raw_date, raw_close in rows:
        code = plain_code(raw_code)
        close = _safe_float(raw_close)
        date = str(raw_date)
        if not code or close is None or close <= 0:
            continue
        closes.setdefault(code, {})[date] = close
    return closes


def _future_date(dates: list[str], date: str, horizon_days: int) -> str | None:
    try:
        index = dates.index(date)
    except ValueError:
        return None
    future_index = index + horizon_days
    if future_index >= len(dates):
        return None
    return dates[future_index]


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _round_pct(value: float | None) -> float | None:
    return round(value * 100, 3) if value is not None else None


def _confidence(status: str, metrics: dict[str, Any]) -> str:
    if status != "validated":
        return "unverified"
    one_day = metrics.get("1d") or {}
    excess = _safe_float(one_day.get("top_excess_return_pct"))
    rank_ic = _safe_float(one_day.get("rank_ic"))
    if excess is not None and rank_ic is not None and excess > 0 and rank_ic > 0:
        return "validated_positive"
    if excess is not None and excess < 0:
        return "validated_weak"
    return "validated_neutral"


def validate_signal_provider(
    *,
    provider: str = DEFAULT_PROVIDER,
    db_path: Path = DB_PATH,
    cache_path: Path = QLIB_PRED_CACHE,
    top_n: int = 50,
    horizons: tuple[int, ...] = (1, 5),
) -> SignalValidationSummary:
    cache_stat = Path(cache_path).stat() if Path(cache_path).exists() else None
    db_stat = Path(db_path).stat() if Path(db_path).exists() else None
    cache_key = (
        str(cache_path),
        str(db_path),
        int(top_n),
        cache_stat.st_mtime_ns if cache_stat else None,
        db_stat.st_mtime_ns if db_stat else None,
    )
    cached = _VALIDATION_CACHE.get(cache_key)
    if cached is not None:
        return SignalValidationSummary(**cached)

    predictions, meta = load_prediction_history(provider=provider, cache_path=cache_path)
    model_version = str(meta.get("model_version") or "")
    if not predictions:
        summary = SignalValidationSummary(
            provider=str(meta.get("provider") or provider),
            model_version=model_version,
            status="insufficient_data",
            confidence="unverified",
            sample_days=0,
            metrics={},
            message="no signal predictions available",
        )
        _VALIDATION_CACHE[cache_key] = summary.__dict__
        return summary

    dates = _load_dates(db_path)
    if not dates:
        summary = SignalValidationSummary(
            provider=str(meta.get("provider") or provider),
            model_version=model_version,
            status="insufficient_data",
            confidence="unverified",
            sample_days=0,
            metrics={},
            message="no local stock_daily close data available",
        )
        _VALIDATION_CACHE[cache_key] = summary.__dict__
        return summary

    needed_dates: set[str] = set()
    needed_codes: set[str] = set()
    for date, rows in predictions.items():
        needed_dates.add(str(date))
        for horizon in horizons:
            future = _future_date(dates, str(date), horizon)
            if future:
                needed_dates.add(future)
        for code in rows:
            normalized = plain_code(code)
            if normalized:
                needed_codes.add(normalized)
    closes = _load_close_matrix(db_path, codes=needed_codes, dates=needed_dates)
    if not closes:
        summary = SignalValidationSummary(
            provider=str(meta.get("provider") or provider),
            model_version=model_version,
            status="insufficient_data",
            confidence="unverified",
            sample_days=0,
            metrics={},
            message="no overlapping local stock_daily close data available",
        )
        _VALIDATION_CACHE[cache_key] = summary.__dict__
        return summary

    metrics: dict[str, Any] = {}
    sample_days = 0
    for horizon in horizons:
        day_top_returns: list[float] = []
        day_base_returns: list[float] = []
        day_hit_rates: list[float] = []
        day_rank_ics: list[float] = []
        valid_days = 0
        for date, rows in sorted(predictions.items()):
            future = _future_date(dates, date, horizon)
            if not future:
                continue
            scored_returns: list[tuple[str, float, float]] = []
            for code, score in rows.items():
                start = closes.get(code, {}).get(date)
                end = closes.get(code, {}).get(future)
                if start is None or end is None or start <= 0:
                    continue
                scored_returns.append((code, float(score), (end / start) - 1))
            if len(scored_returns) < 2:
                continue
            scored_returns.sort(key=lambda item: item[1], reverse=True)
            top_returns = [item[2] for item in scored_returns[: max(1, int(top_n))]]
            base_returns = [item[2] for item in scored_returns]
            scores = [item[1] for item in scored_returns]
            rets = [item[2] for item in scored_returns]
            rank_ic = _spearman(scores, rets)
            top_mean = _mean(top_returns)
            base_mean = _mean(base_returns)
            if top_mean is None or base_mean is None:
                continue
            valid_days += 1
            day_top_returns.append(top_mean)
            day_base_returns.append(base_mean)
            day_hit_rates.append(sum(1 for ret in top_returns if ret > 0) / len(top_returns))
            if rank_ic is not None:
                day_rank_ics.append(rank_ic)
        sample_days = max(sample_days, valid_days)
        top_avg = _mean(day_top_returns)
        base_avg = _mean(day_base_returns)
        metrics[f"{horizon}d"] = {
            "sample_days": valid_days,
            "top_n": int(top_n),
            "top_return_pct": _round_pct(top_avg),
            "baseline_return_pct": _round_pct(base_avg),
            "top_excess_return_pct": _round_pct(top_avg - base_avg) if top_avg is not None and base_avg is not None else None,
            "hit_rate_pct": _round_pct(_mean(day_hit_rates)),
            "rank_ic": round(_mean(day_rank_ics), 4) if day_rank_ics else None,
        }

    status = "validated" if sample_days > 0 else "insufficient_data"
    summary = SignalValidationSummary(
        provider=str(meta.get("provider") or provider),
        model_version=model_version,
        status=status,
        confidence=_confidence(status, metrics),
        sample_days=sample_days,
        metrics=metrics,
        message="" if status == "validated" else "not enough overlapping future return data",
    )
    _VALIDATION_CACHE[cache_key] = summary.__dict__
    if len(_VALIDATION_CACHE) > 8:
        oldest_key = next(iter(_VALIDATION_CACHE))
        _VALIDATION_CACHE.pop(oldest_key, None)
    return summary
