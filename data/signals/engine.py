"""Signal Engine v2 orchestration.

This module is the read-side boundary between legacy prediction caches and
dashboard consumers. New callers should use this instead of Qlib-specific
helpers.
"""
from __future__ import annotations

import statistics
from pathlib import Path
from typing import Any

from config.settings import QLIB_PRED_CACHE
from data.signals.models import LOCAL_MOMENTUM_PROVIDER, SignalRecord
from data.signals.providers import local_momentum

DEFAULT_PROVIDER = LOCAL_MOMENTUM_PROVIDER


def get_signal_records(
    *,
    provider: str = DEFAULT_PROVIDER,
    top_n: int | None = 50,
    date: str | None = None,
    cache_path: Path = QLIB_PRED_CACHE,
    confidence: str = "unverified",
) -> tuple[list[SignalRecord], dict[str, Any]]:
    if provider not in {LOCAL_MOMENTUM_PROVIDER, "qlib", "legacy_qlib"}:
        return [], {
            "provider": provider,
            "model_version": "",
            "latest_date": None,
            "total": 0,
            "error": f"unsupported provider: {provider}",
        }
    return local_momentum.load_records(
        cache_path=cache_path,
        date=date,
        limit=top_n,
        confidence=confidence,
    )


def load_prediction_history(
    *,
    provider: str = DEFAULT_PROVIDER,
    cache_path: Path = QLIB_PRED_CACHE,
) -> tuple[dict[str, dict[str, float]], dict[str, Any]]:
    if provider not in {LOCAL_MOMENTUM_PROVIDER, "qlib", "legacy_qlib"}:
        return {}, {"provider": provider, "model_version": "", "latest_date": None, "total": 0}
    payload = local_momentum.load_cache(cache_path)
    predictions = local_momentum.extract_predictions(payload)
    latest = local_momentum.latest_date(predictions)
    return predictions, {
        "provider": LOCAL_MOMENTUM_PROVIDER,
        "model_version": local_momentum.model_version(payload),
        "latest_date": latest,
        "total": len(predictions.get(latest or "", {})) if latest else 0,
        "generated_at": payload.get("generated_at"),
        "cache_path": str(cache_path),
        "raw_source": "legacy_qlib",
    }


def build_signal_context(
    *,
    provider: str = DEFAULT_PROVIDER,
    top_limit: int | None = None,
    cache_path: Path = QLIB_PRED_CACHE,
    confidence: str = "unverified",
) -> dict[str, Any]:
    predictions, meta = load_prediction_history(provider=provider, cache_path=cache_path)
    return build_signal_context_from_predictions(
        predictions,
        top_limit=top_limit,
        provider=meta.get("provider") or provider,
        model_version=meta.get("model_version") or "",
        confidence=confidence,
        raw_source=meta.get("raw_source") or "legacy_qlib",
        generated_at=meta.get("generated_at"),
    )


def build_signal_context_from_predictions(
    predictions: dict[str, dict[str, float]],
    *,
    top_limit: int | None = None,
    provider: str = DEFAULT_PROVIDER,
    model_version: str = "",
    confidence: str = "unverified",
    raw_source: str = "legacy_qlib",
    generated_at: str | None = None,
) -> dict[str, Any]:
    latest_date = local_momentum.latest_date(predictions)
    latest_preds = predictions.get(str(latest_date), {}) if latest_date else {}
    if not latest_preds:
        return {
            "latest_date": latest_date,
            "total": 0,
            "provider": provider,
            "model_version": model_version,
            "items": {},
            "ordered_codes": [],
            "raw_source": raw_source,
        }

    sorted_latest = sorted(latest_preds.items(), key=lambda item: item[1], reverse=True)
    safe_top_limit = max(1, int(top_limit)) if top_limit else len(sorted_latest)
    top_codes = {code for code, _ in sorted_latest[:safe_top_limit]}

    history: dict[str, list[float]] = {code: [] for code in top_codes}
    for day, preds in predictions.items():
        if day == latest_date:
            continue
        for code in top_codes:
            score = preds.get(code)
            if score is not None:
                history.setdefault(code, []).append(float(score))

    items: dict[str, dict[str, Any]] = {}
    ordered_codes: list[str] = []
    for rank, (code, score) in enumerate(sorted_latest, start=1):
        hist = history.get(code, [])
        hist_std = None
        ic_adj = None
        if len(hist) >= 3:
            try:
                hist_std = statistics.pstdev(hist)
                if hist_std and hist_std > 0:
                    ic_adj = round(float(score) / hist_std, 4)
            except Exception:
                hist_std = None
                ic_adj = None
        payload = {
            "signal_rank": rank,
            "signal_score": round(float(score), 6),
            "signal_provider": provider,
            "signal_model_version": model_version,
            "signal_confidence": confidence,
            "signal_horizon": "1d",
            "signal_raw_source": raw_source,
            "signal_consistency": ic_adj,
            "signal_appearances": len(hist),
            # Legacy compatibility. Existing consumers will be migrated off these
            # keys gradually, but keeping them avoids a hard dashboard break.
            "qlib_rank": rank,
            "qlib_score": round(float(score), 6),
            "qlib_ic_adj": ic_adj,
            "qlib_diamond": bool(ic_adj is not None and ic_adj > 2),
            "qlib_appearances": len(hist),
        }
        items[code] = payload
        if len(ordered_codes) < safe_top_limit:
            ordered_codes.append(code)

    return {
        "latest_date": latest_date,
        "total": len(sorted_latest),
        "provider": provider,
        "model_version": model_version,
        "items": items,
        "ordered_codes": ordered_codes,
        "raw_source": raw_source,
        "generated_at": generated_at,
    }
