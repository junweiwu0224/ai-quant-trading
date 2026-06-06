"""Provider adapter for the legacy local momentum prediction cache."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from config.settings import QLIB_PRED_CACHE
from data.signals.models import (
    DEFAULT_CONFIDENCE,
    DEFAULT_COVERAGE,
    DEFAULT_HORIZON,
    LEGACY_QLIB_PROVIDER,
    LOCAL_MOMENTUM_PROVIDER,
    SignalRecord,
    plain_code,
)

DEFAULT_MODEL_VERSION = "local_momentum_v1"


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def load_cache(cache_path: Path = QLIB_PRED_CACHE) -> dict[str, Any]:
    path = Path(cache_path)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def extract_predictions(payload: dict[str, Any]) -> dict[str, dict[str, float]]:
    raw_predictions = payload.get("predictions", payload)
    if not isinstance(raw_predictions, dict):
        return {}
    predictions: dict[str, dict[str, float]] = {}
    for date, rows in raw_predictions.items():
        if not isinstance(rows, dict):
            continue
        normalized: dict[str, float] = {}
        for raw_code, raw_score in rows.items():
            code = plain_code(raw_code)
            score = _safe_float(raw_score)
            if code and score is not None:
                normalized[code] = score
        if normalized:
            predictions[str(date)] = normalized
    return predictions


def model_version(payload: dict[str, Any]) -> str:
    return str(payload.get("method") or DEFAULT_MODEL_VERSION)


def latest_date(predictions: dict[str, dict[str, float]]) -> str | None:
    return max(predictions.keys()) if predictions else None


def records_from_predictions(
    predictions: dict[str, dict[str, float]],
    *,
    date: str | None = None,
    provider: str = LOCAL_MOMENTUM_PROVIDER,
    model: str = DEFAULT_MODEL_VERSION,
    limit: int | None = None,
    confidence: str = DEFAULT_CONFIDENCE,
    horizon: str = DEFAULT_HORIZON,
) -> list[SignalRecord]:
    selected_date = date or latest_date(predictions)
    if not selected_date:
        return []
    latest_rows = predictions.get(str(selected_date)) or {}
    sorted_rows = sorted(latest_rows.items(), key=lambda item: item[1], reverse=True)
    if limit is not None:
        sorted_rows = sorted_rows[: max(1, int(limit))]
    return [
        SignalRecord(
            code=code,
            date=str(selected_date),
            provider=provider,
            model_version=model,
            score=float(score),
            rank=rank,
            horizon=horizon,
            confidence=confidence,
            coverage=DEFAULT_COVERAGE,
            raw_source=LEGACY_QLIB_PROVIDER,
        )
        for rank, (code, score) in enumerate(sorted_rows, start=1)
    ]


def load_records(
    *,
    cache_path: Path = QLIB_PRED_CACHE,
    date: str | None = None,
    limit: int | None = None,
    confidence: str = DEFAULT_CONFIDENCE,
) -> tuple[list[SignalRecord], dict[str, Any]]:
    payload = load_cache(cache_path)
    predictions = extract_predictions(payload)
    model = model_version(payload)
    records = records_from_predictions(
        predictions,
        date=date,
        model=model,
        limit=limit,
        confidence=confidence,
    )
    meta = {
        "provider": LOCAL_MOMENTUM_PROVIDER,
        "model_version": model,
        "latest_date": latest_date(predictions),
        "total": len(predictions.get(latest_date(predictions) or "", {})) if predictions else 0,
        "generated_at": payload.get("generated_at"),
        "cache_path": str(cache_path),
        "raw_source": LEGACY_QLIB_PROVIDER,
    }
    return records, meta
