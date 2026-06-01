from __future__ import annotations

from datetime import datetime, timezone
import uuid

from agentic.models import TradingSignal
from agentic.repository import AgenticRepository


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SignalService:
    def __init__(self, repo: AgenticRepository):
        self.repo = repo

    def publish(
        self,
        *,
        agent_id: str,
        source: str,
        code: str,
        direction: str,
        confidence: float,
        time_horizon: str,
        entry_reasons: list[str],
        risk_notes: list[str],
        suggested_position: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        expires_at: str | None = None,
        metadata: dict | None = None,
    ) -> TradingSignal:
        signal = TradingSignal(
            f"sig_{uuid.uuid4().hex[:12]}",
            agent_id,
            source,
            code,
            direction,
            confidence,
            time_horizon,
            entry_reasons,
            risk_notes,
            suggested_position,
            stop_loss,
            take_profit,
            "new",
            iso_now(),
            expires_at,
            metadata or {},
        )
        self.repo.save_signal(signal)
        return signal

    def mark_paper_pending(self, signal_id: str, confirmed_by: str) -> TradingSignal:
        current = self.repo.get_signal(signal_id)
        if current.status not in {"new", "watching", "backtested"}:
            raise ValueError(f"signal cannot be promoted from status {current.status}")
        updated = TradingSignal(
            current.id,
            current.agent_id,
            current.source,
            current.code,
            current.direction,
            current.confidence,
            current.time_horizon,
            list(current.entry_reasons),
            list(current.risk_notes),
            current.suggested_position,
            current.stop_loss,
            current.take_profit,
            "paper_pending",
            current.created_at,
            current.expires_at,
            {**current.metadata, "confirmed_by": confirmed_by, "paper_pending_at": iso_now()},
        )
        self.repo.save_signal(updated)
        return updated

    def list(self, limit: int = 100) -> list[TradingSignal]:
        return self.repo.list_signals(limit=limit)
