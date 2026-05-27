"""Local deterministic predictor for the dashboard Qlib cache contract."""
from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from config.settings import DB_PATH, QLIB_PRED_CACHE


METHOD_NAME = "local_momentum_v1"
MIN_UNIVERSE_SIZE = 2


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
    limit: int,
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

    max_rows = max(1, int(limit)) * max(2, int(lookback_days)) * 4
    return rows[:max_rows]


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
    return max(0.0, min(1.0, raw_score))


def _build_predictions(
    rows: list[sqlite3.Row],
    limit: int,
) -> tuple[str | None, dict[str, float]]:
    if not rows:
        return None, {}

    latest_date = max(str(row["date"]) for row in rows)
    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        code = _plain_code(str(row["code"]))
        if code:
            grouped.setdefault(code, []).append(row)

    scored: list[tuple[str, float]] = []
    for code, series in grouped.items():
        if not any(str(row["date"]) == latest_date for row in series):
            continue
        score = _score_series(series)
        if score is not None:
            scored.append((code, round(score, 6)))

    scored.sort(key=lambda item: item[1], reverse=True)
    return latest_date, dict(scored[: max(1, int(limit))])


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
    limit: int = 300,
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
