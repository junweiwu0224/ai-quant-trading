from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from agentic.models import PaperStrategyCandidate
from agentic.repository import AgenticRepository


class PaperStrategyCandidateService:
    def __init__(self, repository: AgenticRepository):
        self.repository = repository

    def enqueue(self, result: dict, sample: dict) -> PaperStrategyCandidate:
        promotion = dict(result.get("promotion") or {})
        if promotion.get("promoted") is not True:
            raise ValueError("only promoted candidates can be queued for paper trading")
        candidate = dict(result.get("candidate") or {})
        candidate_id = str(candidate.get("id") or "").strip()
        if not candidate_id:
            raise ValueError("candidate.id is required")
        record = PaperStrategyCandidate(
            id=f"paper_strategy_{uuid4().hex}",
            candidate_id=candidate_id,
            name=str(candidate.get("name") or candidate_id),
            dsl=dict(candidate.get("dsl") or {}),
            sample=dict(sample or {}),
            metrics=dict(result.get("metrics") or {}),
            promotion=promotion,
            status="paper_candidate",
            requires_confirmation=True,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.repository.save_paper_strategy_candidate(record)
        return record

    def list(self, limit: int = 100) -> list[PaperStrategyCandidate]:
        return self.repository.list_paper_strategy_candidates(limit=limit)
