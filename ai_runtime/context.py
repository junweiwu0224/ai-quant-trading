"""Freeze and hash AI input snapshots without fetching hidden data."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any

from .models import AnalysisContext


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("analysis_context_non_finite_number")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ValueError(f"analysis_context_unsupported_value:{type(value).__name__}")


def stable_json(value: Any) -> str:
    return json.dumps(_json_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_hash(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def _quality_status(payload: Mapping[str, Any]) -> str:
    explicit = str(payload.get("quality_status") or payload.get("status") or "").strip().lower()
    if explicit in {"available", "partial", "missing", "stale", "failed", "unknown"}:
        return explicit
    blocks = payload.get("blocks")
    if not isinstance(blocks, Mapping) or not blocks:
        return "missing"
    statuses = [str(item.get("status") or "") for item in blocks.values() if isinstance(item, Mapping)]
    if not statuses:
        return "unknown"
    if any(status in {"failed", "missing", "stale"} for status in statuses):
        return "partial" if any(status in {"available", "partial"} for status in statuses) else statuses[0]
    return "partial" if any(status == "partial" for status in statuses) else "available"


def build_analysis_context(payload: Mapping[str, Any], *, market: str = "CN", instrument: str = "") -> AnalysisContext:
    """Create an immutable context from caller-supplied evidence.

    This function intentionally never calls a market or news provider.  The
    caller must pass the already-frozen evidence that is being analysed.
    """

    source = _json_safe(dict(payload or {}))
    if not isinstance(source, dict):
        raise ValueError("analysis_context_must_be_object")
    normalized_market = str(source.get("market") or market or "CN").strip().upper()
    normalized_instrument = str(source.get("instrument") or source.get("symbol") or instrument or "").strip()
    if not normalized_instrument:
        raise ValueError("analysis_instrument_required")
    blocks = source.get("blocks") if isinstance(source.get("blocks"), Mapping) else {}
    evidence = source.get("evidence") if isinstance(source.get("evidence"), list) else []
    canonical = {
        "market": normalized_market,
        "instrument": normalized_instrument,
        "as_of": str(source.get("as_of") or source.get("date") or ""),
        "blocks": blocks,
        "evidence": evidence,
        "quality_status": _quality_status(source),
        "source": str(source.get("source") or "provided_snapshot"),
    }
    return AnalysisContext(**canonical, context_hash=content_hash(canonical))

