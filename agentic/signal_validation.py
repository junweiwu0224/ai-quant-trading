from __future__ import annotations

from dataclasses import dataclass
from typing import Any


MIN_VALIDATION_SAMPLE_DAYS = 20


@dataclass(frozen=True)
class SignalValidationGate:
    confidence: str
    sample_days: int
    passed: bool
    label: str
    reason: str
    detail: str

    def to_gate_check(self) -> dict[str, Any]:
        return {
            "id": "signal_validation",
            "label": "AI信号验证",
            "passed": self.passed,
            "detail": self.detail,
        }


def evaluate_signal_validation(validation: dict[str, Any] | None) -> SignalValidationGate:
    payload = validation if isinstance(validation, dict) else {}
    confidence = str(payload.get("confidence") or "unverified")
    sample_days = _as_int(payload.get("sample_days"))
    confidence_validated = confidence.startswith("validated")
    passed = confidence_validated and sample_days >= MIN_VALIDATION_SAMPLE_DAYS
    label = _confidence_label(confidence)
    if passed:
        reason = "signal validation passed"
        detail = f"{label} · 样本 {sample_days} 天"
    elif confidence_validated:
        reason = "AI signal validation sample is insufficient"
        detail = f"AI验证样本不足 · {label} · 样本 {sample_days}/{MIN_VALIDATION_SAMPLE_DAYS} 天"
    else:
        reason = "AI signal is not validated"
        detail = f"AI未验证 · {label} · 样本 {sample_days} 天"
    return SignalValidationGate(
        confidence=confidence,
        sample_days=sample_days,
        passed=passed,
        label=label,
        reason=reason,
        detail=detail,
    )


def _confidence_label(confidence: str) -> str:
    return {
        "validated_positive": "验证偏正",
        "validated_neutral": "验证中性",
        "validated_weak": "验证较弱",
        "unverified": "未验证",
    }.get(confidence, "未验证")


def _as_int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
