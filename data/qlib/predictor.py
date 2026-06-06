"""Local deterministic predictor for the dashboard Qlib cache contract."""
from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from config.settings import DB_PATH, QLIB_PRED_CACHE


METHOD_NAME = "local_momentum_v1"
MIN_UNIVERSE_SIZE = 2
FULL_UNIVERSE_PREDICTION_LIMIT = 6000
MIN_PREDICTION_DATE_COVERAGE_RATIO = 0.8


@dataclass(frozen=True)
class QlibPredictionSummary:
    success: bool
    latest_date: str | None
    total: int
    cache_path: Path
    method: str = METHOD_NAME
    message: str = ""


def _remove_stale_cache(cache_path: Path) -> None:
    try:
        if cache_path.exists():
            cache_path.unlink()
    except OSError:
        pass


def _plain_code(code: str) -> str:
    raw = str(code or "").strip()
    if raw[:2].lower() in {"sh", "sz"}:
        raw = raw[2:]
    return raw if len(raw) == 6 and raw.isdigit() else ""


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _fetch_daily_rows(
    db_path: Path,
    lookback_days: int,
    limit: int | None = None,
) -> list[sqlite3.Row]:
    if not db_path.exists():
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(
            """WITH latest_dates AS (
                   SELECT DISTINCT date
                   FROM stock_daily
                   ORDER BY date DESC
                   LIMIT ?
               )
               SELECT code, date, open, high, low, close, volume, amount
               FROM stock_daily
               WHERE date IN (SELECT date FROM latest_dates)
               ORDER BY code, date""",
            (max(2, int(lookback_days)),),
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    return rows


def _score_series(rows: list[sqlite3.Row]) -> float | None:
    ordered = sorted(rows, key=lambda row: str(row["date"]))
    closes = [_safe_float(row["close"]) for row in ordered]
    closes = [value for value in closes if value is not None and value > 0]
    if len(closes) < 2:
        return None

    first = closes[0]
    last = closes[-1]
    momentum = (last / first) - 1.0
    returns = [
        (closes[index] / closes[index - 1]) - 1.0
        for index in range(1, len(closes))
        if closes[index - 1]
    ]
    avg_return = sum(returns) / len(returns) if returns else 0.0
    variance = (
        sum((item - avg_return) ** 2 for item in returns) / len(returns)
        if returns
        else 0.0
    )
    volatility = math.sqrt(variance)

    amounts = [_safe_float(row["amount"]) for row in ordered]
    amounts = [value for value in amounts if value is not None and value > 0]
    latest_amount = amounts[-1] if amounts else 0.0
    liquidity = math.log10(latest_amount + 1.0) / 10.0

    raw_score = 0.5 + momentum * 4.0 + avg_return * 6.0 - volatility * 2.0
    raw_score += liquidity * 0.12
    return raw_score


def _normalize_cross_section(scored: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Convert raw daily signals into rank-based 0..1 scores for that date."""
    if not scored:
        return []
    ordered = sorted(scored, key=lambda item: item[1], reverse=True)
    if len(ordered) == 1:
        return [(ordered[0][0], 1.0)]

    normalized: list[tuple[str, float]] = []
    index = 0
    total = len(ordered)
    while index < total:
        end = index + 1
        while end < total and math.isclose(
            ordered[end][1],
            ordered[index][1],
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            end += 1
        avg_rank = (index + end - 1) / 2
        score = 1.0 - (avg_rank / (total - 1))
        for code, _ in ordered[index:end]:
            normalized.append((code, round(max(0.0, min(1.0, score)), 6)))
        index = end
    return normalized


def _build_predictions(
    rows: list[sqlite3.Row],
    limit: int,
) -> tuple[str | None, dict[str, float]]:
    if not rows:
        return None, {}

    grouped: dict[str, list[sqlite3.Row]] = {}
    date_codes: dict[str, set[str]] = {}
    for row in rows:
        code = _plain_code(str(row["code"]))
        date = str(row["date"])
        if code:
            grouped.setdefault(code, []).append(row)
            date_codes.setdefault(date, set()).add(code)

    if not date_codes:
        return None, {}
    max_coverage = max(len(codes) for codes in date_codes.values())
    coverage_floor = max(
        1,
        int(math.ceil(max_coverage * MIN_PREDICTION_DATE_COVERAGE_RATIO)),
    )
    eligible_dates = [
        date for date, codes in date_codes.items() if len(codes) >= coverage_floor
    ]
    latest_date = max(eligible_dates or date_codes.keys())

    scored: list[tuple[str, float]] = []
    for code, series in grouped.items():
        usable_series = [row for row in series if str(row["date"]) <= latest_date]
        if not any(str(row["date"]) == latest_date for row in usable_series):
            continue
        score = _score_series(usable_series)
        if score is not None:
            scored.append((code, round(score, 6)))

    normalized = _normalize_cross_section(scored)
    return latest_date, dict(normalized[: max(1, int(limit))])


def _fetch_historical_daily_rows(db_path: Path, start_date: str, end_date: str) -> list[sqlite3.Row]:
    if not db_path.exists():
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT code, date, open, high, low, close, volume, amount
            FROM stock_daily
            WHERE date <= ?
            ORDER BY code, date
            """,
            (str(end_date),),
        ).fetchall()
    finally:
        conn.close()
    return [row for row in rows if str(row["date"]) <= str(end_date)]


def _build_historical_predictions(
    rows: list[sqlite3.Row],
    start_date: str,
    end_date: str,
    lookback_days: int,
    limit: int,
    min_history_days: int,
    min_universe_size: int,
) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[sqlite3.Row]] = {}
    date_codes: dict[str, set[str]] = {}
    for row in rows:
        code = _plain_code(str(row["code"]))
        date = str(row["date"])
        if not code:
            continue
        grouped.setdefault(code, []).append(row)
        if str(start_date) <= date <= str(end_date):
            date_codes.setdefault(date, set()).add(code)

    predictions: dict[str, dict[str, float]] = {}
    safe_lookback = max(2, int(lookback_days))
    safe_limit = max(1, int(limit))
    safe_min_history = max(2, int(min_history_days))
    safe_min_universe = max(1, int(min_universe_size))
    max_coverage = max((len(codes) for codes in date_codes.values()), default=0)
    coverage_floor = max(
        safe_min_universe,
        int(math.ceil(max_coverage * MIN_PREDICTION_DATE_COVERAGE_RATIO)) if max_coverage else safe_min_universe,
    )
    eligible_dates = {
        date for date, codes in date_codes.items() if len(codes) >= coverage_floor
    }
    scored_by_date: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for code, series in grouped.items():
        ordered = sorted(series, key=lambda row: str(row["date"]))
        for index, row in enumerate(ordered):
            date = str(row["date"])
            if date not in eligible_dates:
                continue
            history_count = index + 1
            if history_count < safe_min_history:
                continue
            window = ordered[max(0, history_count - safe_lookback):history_count]
            score = _score_series(window)
            if score is not None:
                scored_by_date[date].append((code, round(score, 6)))

    for date in sorted(eligible_dates):
        scored = scored_by_date.get(date, [])
        if len(scored) < safe_min_universe:
            continue
        normalized = _normalize_cross_section(scored)
        predictions[date] = dict(normalized[:safe_limit])
    return predictions


def write_predictions_cache(
    predictions: dict[str, dict[str, float]],
    cache_path: Path = QLIB_PRED_CACHE,
    method: str = METHOD_NAME,
) -> QlibPredictionSummary:
    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    latest_date = max(predictions.keys()) if predictions else None
    latest_predictions = predictions.get(latest_date, {}) if latest_date else {}
    payload = {
        "predictions": predictions,
        "latest_date": latest_date,
        "total": len(latest_predictions),
        "method": method,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    cache_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return QlibPredictionSummary(
        success=True,
        latest_date=latest_date,
        total=len(latest_predictions),
        cache_path=cache_path,
        method=method,
    )


def generate_predictions(
    db_path: Path = DB_PATH,
    cache_path: Path = QLIB_PRED_CACHE,
    lookback_days: int = 60,
    limit: int = FULL_UNIVERSE_PREDICTION_LIMIT,
    min_universe_size: int = MIN_UNIVERSE_SIZE,
) -> QlibPredictionSummary:
    db_path = Path(db_path)
    cache_path = Path(cache_path)
    rows = _fetch_daily_rows(
        db_path=db_path,
        lookback_days=lookback_days,
        limit=limit,
    )
    latest_date, latest_predictions = _build_predictions(rows, limit=limit)
    if not latest_predictions:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        _remove_stale_cache(cache_path)
        return QlibPredictionSummary(
            success=False,
            latest_date=latest_date,
            total=0,
            cache_path=cache_path,
            message=f"no usable stock_daily rows in {db_path}",
        )
    if len(latest_predictions) < max(1, int(min_universe_size)):
        _remove_stale_cache(cache_path)
        return QlibPredictionSummary(
            success=False,
            latest_date=latest_date,
            total=len(latest_predictions),
            cache_path=cache_path,
            message=(
                "insufficient stock_daily coverage: "
                f"{len(latest_predictions)} codes < {max(1, int(min_universe_size))}"
            ),
        )

    return write_predictions_cache(
        predictions={str(latest_date): latest_predictions},
        cache_path=cache_path,
        method=METHOD_NAME,
    )


def generate_historical_predictions(
    db_path: Path = DB_PATH,
    cache_path: Path = QLIB_PRED_CACHE,
    start_date: str = "",
    end_date: str = "",
    lookback_days: int = 60,
    limit: int = FULL_UNIVERSE_PREDICTION_LIMIT,
    min_history_days: int = 20,
    min_universe_size: int = MIN_UNIVERSE_SIZE,
) -> QlibPredictionSummary:
    db_path = Path(db_path)
    cache_path = Path(cache_path)
    if not start_date or not end_date:
        return QlibPredictionSummary(
            success=False,
            latest_date=None,
            total=0,
            cache_path=cache_path,
            message="start_date and end_date are required",
        )
    if str(start_date) > str(end_date):
        return QlibPredictionSummary(
            success=False,
            latest_date=None,
            total=0,
            cache_path=cache_path,
            message="start_date must be <= end_date",
        )

    rows = _fetch_historical_daily_rows(db_path, start_date=start_date, end_date=end_date)
    predictions = _build_historical_predictions(
        rows,
        start_date=start_date,
        end_date=end_date,
        lookback_days=lookback_days,
        limit=limit,
        min_history_days=min_history_days,
        min_universe_size=min_universe_size,
    )
    if not predictions:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        _remove_stale_cache(cache_path)
        return QlibPredictionSummary(
            success=False,
            latest_date=None,
            total=0,
            cache_path=cache_path,
            message=f"no usable historical predictions in {db_path}",
        )
    return write_predictions_cache(
        predictions=predictions,
        cache_path=cache_path,
        method=METHOD_NAME,
    )
