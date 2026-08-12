from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import TYPE_CHECKING, Protocol

from agentic.models import TradingSignal
from agentic.promotion import PromotionDecision
from agentic.signal_ledger import SignalLedger

if TYPE_CHECKING:
    from agentic.repository import AgenticRepository


class SignalRepository(Protocol):
    """Repository seam needed by SignalService; concrete storage is replaceable."""

    db_path: object

    def save_signal(self, signal: TradingSignal) -> None: ...

    def get_signal(self, signal_id: str) -> TradingSignal: ...

    def list_signals(self, limit: int = 100) -> list[TradingSignal]: ...


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SignalService:
    def __init__(self, repo: SignalRepository, ledger: SignalLedger | None = None):
        self.repo = repo
        self.ledger = ledger or SignalLedger(repo.db_path)

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
        atomic_publish = getattr(self.repo, "publish_signal_atomically", None)
        if callable(atomic_publish):
            atomic_publish(signal)
        else:
            # Compatibility fallback for legacy repositories/test doubles.
            atomic_publish = None
            self.ledger.append_transition(
                signal.id,
                None,
                signal.status,
                actor="signal-service",
                reason="signal published",
                occurred_at=signal.created_at,
                metadata={"agent_id": agent_id, "source": source},
            )
            self.repo.save_signal(signal)
        return signal

    def mark_paper_pending(
        self,
        signal_id: str,
        confirmed_by: str,
        *,
        decision: PromotionDecision | None = None,
    ) -> TradingSignal:
        current = self.repo.get_signal(signal_id)
        if current.status not in {"new", "watching", "backtested"}:
            raise ValueError(f"signal cannot be promoted from status {current.status}")
        if decision is not None and (not decision.approved or decision.target != "paper_pending"):
            raise ValueError("paper promotion requires an approved paper_pending decision")
        decision_metadata = {}
        if decision is not None:
            decision_metadata = {
                "policy_version": decision.policy_version,
                "failed_gates": list(decision.failed_gates),
            }
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
            {
                **current.metadata,
                "confirmed_by": confirmed_by,
                "paper_pending_at": iso_now(),
                "promotion": decision_metadata,
            },
        )
        transition_metadata = {"confirmed_by": confirmed_by, "promotion": decision_metadata}
        atomic_transition = getattr(self.repo, "transition_signal_atomically", None)
        if callable(atomic_transition):
            atomic_transition(
                updated,
                expected_status=current.status,
                actor=confirmed_by,
                reason="paper promotion manually confirmed",
                metadata=transition_metadata,
            )
        else:
            # Compatibility fallback for legacy repositories/test doubles.
            self.ledger.ensure_status(current.id, current.status)
            self.ledger.append_transition(
                current.id,
                current.status,
                updated.status,
                actor=confirmed_by,
                reason="paper promotion manually confirmed",
                metadata=transition_metadata,
            )
            self.repo.save_signal(updated)
        return updated

    def list(self, limit: int = 100) -> list[TradingSignal]:
        return self.repo.list_signals(limit=limit)
