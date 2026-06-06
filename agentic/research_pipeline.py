from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from agentic.models import ResearchJob, normalize_signal_code
from agentic.repository import AgenticRepository

RESEARCH_ROLES = ("signal", "market", "theme", "bear", "decision")
PAPER_CANDIDATE_THRESHOLD = 0.6


class ResearchPipeline:
    def __init__(self, repository: AgenticRepository):
        self.repository = repository

    def run(self, code: str, context: dict | None = None) -> ResearchJob:
        context = dict(context or {})
        normalized_code = normalize_signal_code(code)
        signal_score = _as_score(context.get("signal_score", context.get("qlib_score", 0.0)))
        decision = "paper_candidate" if signal_score >= PAPER_CANDIDATE_THRESHOLD else "observe"
        now = _utc_now_iso()
        final_report = {
            "code": normalized_code,
            "decision": decision,
            "signal_score": signal_score,
            "qlib_score": signal_score,
            "roles": {
                "signal": {"score": signal_score},
                "qlib": {"score": signal_score},
                "market": {"summary": context.get("market", "market context unavailable")},
                "theme": {"theme": context.get("theme", "unclassified")},
                "bear": {"risk": context.get("risk", "position sizing and stop-loss required")},
                "decision": {"rationale": _decision_rationale(decision)},
            },
        }
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


def _decision_rationale(decision: str) -> str:
    if decision == "paper_candidate":
        return "signal_score meets paper threshold"
    return "signal_score below paper threshold"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
