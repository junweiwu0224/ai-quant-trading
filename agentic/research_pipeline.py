from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from agentic.models import ResearchJob, normalize_signal_code
from agentic.repository import AgenticRepository
from agentic.signal_validation import evaluate_signal_validation

RESEARCH_ROLES = ("signal", "market", "theme", "bear", "decision")
PAPER_CANDIDATE_THRESHOLD = 0.6


class ResearchPipeline:
    def __init__(self, repository: AgenticRepository):
        self.repository = repository

    def run(self, code: str, context: dict | None = None) -> ResearchJob:
        context = dict(context or {})
        normalized_code = normalize_signal_code(code)
        used_legacy_score = "signal_score" not in context and "qlib_score" in context
        signal_score = _as_score(context.get("signal_score", context.get("qlib_score", 0.0)))
        signal_validation = evaluate_signal_validation(context.get("signal_validation"))
        decision = (
            "paper_candidate"
            if signal_score >= PAPER_CANDIDATE_THRESHOLD and signal_validation.passed
            else "observe"
        )
        now = _utc_now_iso()
        final_report = {
            "code": normalized_code,
            "decision": decision,
            "signal_score": signal_score,
            "signal_validation": {
                "confidence": signal_validation.confidence,
                "sample_days": signal_validation.sample_days,
                "passed": signal_validation.passed,
                "label": signal_validation.label,
                "reason": signal_validation.reason,
            },
            "roles": {
                "signal": {
                    "score": signal_score,
                    "validation": signal_validation.to_gate_check(),
                },
                "market": {"summary": context.get("market", "market context unavailable")},
                "theme": {"theme": context.get("theme", "unclassified")},
                "bear": {"risk": _risk_note(context.get("risk"), signal_validation)},
                "decision": {"rationale": _decision_rationale(decision, signal_score, signal_validation)},
            },
        }
        if used_legacy_score:
            final_report["input_aliases"] = {"qlib_score": "signal_score"}
        job = ResearchJob(
            id=f"research_{uuid4().hex}",
            code=normalized_code,
            status="completed",
            roles=RESEARCH_ROLES,
            final_report=final_report,
            created_at=now,
            updated_at=now,
        )
        self.repository.save_research_job(job)
        return job


def _as_score(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("signal_score must be numeric") from exc


def _decision_rationale(decision: str, signal_score: float, signal_validation) -> str:
    if decision == "paper_candidate":
        return "signal_score meets paper threshold"
    if signal_score >= PAPER_CANDIDATE_THRESHOLD and not signal_validation.passed:
        return signal_validation.detail
    return "signal_score below paper threshold"


def _risk_note(value: object, signal_validation) -> str:
    base = str(value or "position sizing and stop-loss required")
    if signal_validation.passed:
        return base
    prefix = "AI验证样本不足" if signal_validation.reason == "AI signal validation sample is insufficient" else "AI未验证"
    return f"{prefix}；{base}"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
