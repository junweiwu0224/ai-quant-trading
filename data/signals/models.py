"""Signal Engine v2 data contracts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_HORIZON = "1d"
DEFAULT_CONFIDENCE = "unverified"
DEFAULT_COVERAGE = "full_a_local"
LOCAL_MOMENTUM_PROVIDER = "local_momentum"
LEGACY_QLIB_PROVIDER = "legacy_qlib"


def plain_code(code: Any) -> str:
    raw = str(code or "").strip()
    if raw[:2].lower() in {"sh", "sz"}:
        raw = raw[2:]
    return raw if len(raw) == 6 and raw.isdigit() else ""


@dataclass(frozen=True)
class SignalRecord:
    code: str
    date: str
    provider: str
    model_version: str
    score: float
    rank: int
    horizon: str = DEFAULT_HORIZON
    confidence: str = DEFAULT_CONFIDENCE
    coverage: str = DEFAULT_COVERAGE
    raw_source: str = LEGACY_QLIB_PROVIDER

    def to_dict(self, *, legacy_keys: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "date": self.date,
            "provider": self.provider,
            "model_version": self.model_version,
            "score": round(float(self.score), 6),
            "rank": int(self.rank),
            "horizon": self.horizon,
            "confidence": self.confidence,
            "coverage": self.coverage,
            "raw_source": self.raw_source,
        }
        if legacy_keys:
            payload.update(
                {
                    "qlib_rank": int(self.rank),
                    "qlib_score": round(float(self.score), 6),
                    "signal_rank": int(self.rank),
                    "signal_score": round(float(self.score), 6),
                    "signal_provider": self.provider,
                    "signal_model_version": self.model_version,
                    "signal_confidence": self.confidence,
                }
            )
        return payload


@dataclass(frozen=True)
class SignalValidationSummary:
    provider: str
    model_version: str
    status: str
    confidence: str
    sample_days: int
    metrics: dict[str, Any]
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model_version": self.model_version,
            "status": self.status,
            "confidence": self.confidence,
            "sample_days": self.sample_days,
            "metrics": self.metrics,
            "message": self.message,
        }
