"""Deterministic daily vertical slice: evidence to signal to notification."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from typing import List, Optional, Sequence, Tuple

from data.evidence.models import EvidenceItem, EvidenceLink, EvidenceSnapshot, EvidenceSource, utc_now
from data.evidence.store import EvidenceStore
from engine.events.models import DomainEvent
from engine.events.outbox import SQLiteOutbox

from .promotion import PromotionContext, PromotionDecision, PromotionPolicy
from .signal_ledger import SignalLedger


@dataclass(frozen=True)
class SignalCandidate:
    signal_id: str
    symbol: str
    from_status: Optional[str]
    target: str
    context: PromotionContext


@dataclass(frozen=True)
class PromotionResult:
    signal_id: str
    decision: PromotionDecision
    ledger_event_id: Optional[str] = None


@dataclass(frozen=True)
class DailyBrief:
    snapshot_id: str
    captured_at: str
    watchlist: Tuple[str, ...]
    evidence_count: int
    promotions: Tuple[PromotionResult, ...]
    event_id: str


class DailyWorkflowRunner:
    """Deep workflow seam with replaceable evidence and transport adapters."""

    def __init__(
        self,
        evidence_store: EvidenceStore,
        signal_ledger: SignalLedger,
        promotion_policy: PromotionPolicy,
        outbox: SQLiteOutbox,
    ) -> None:
        self.evidence_store = evidence_store
        self.signal_ledger = signal_ledger
        self.promotion_policy = promotion_policy
        self.outbox = outbox

    def run(
        self,
        *,
        watchlist: Sequence[str],
        source: EvidenceSource,
        evidence_items: Sequence[EvidenceItem],
        candidates: Sequence[SignalCandidate] = (),
        query: str = "watchlist_daily_brief",
        captured_at: Optional[str] = None,
    ) -> DailyBrief:
        timestamp = captured_at or utc_now()
        symbols = tuple(dict.fromkeys(watchlist))
        self.evidence_store.save_source(source)
        snapshot = EvidenceSnapshot(
            id=uuid.uuid4().hex,
            captured_at=timestamp,
            query=query,
            metadata={"watchlist": list(symbols)},
        )
        self.evidence_store.save_snapshot(snapshot)
        stored_items: List[EvidenceItem] = []
        for item in evidence_items:
            stored = self.evidence_store.save_item(item)
            stored_items.append(stored)
            self.evidence_store.link(
                EvidenceLink(snapshot_id=snapshot.id, item_id=stored.id, symbol=stored.symbol)
            )
        snapshot = self.evidence_store.seal(snapshot.id)

        promotion_results: List[PromotionResult] = []
        for candidate in candidates:
            evidence_count = sum(
                1 for item in stored_items if item.symbol in {None, candidate.symbol}
            )
            context = candidate.context
            if evidence_count > context.evidence_count:
                context = replace(context, evidence_count=evidence_count)
            decision = self.promotion_policy.evaluate(context, target=candidate.target)
            provenance = self.signal_ledger.record_provenance(
                candidate.signal_id,
                source_type="evidence_snapshot",
                source_id=snapshot.id,
                evidence_snapshot_id=snapshot.id,
                details={"symbol": candidate.symbol, "policy_version": decision.policy_version},
                recorded_at=timestamp,
            )
            ledger_event_id: Optional[str] = None
            if decision.approved:
                event = self.signal_ledger.append_transition(
                    candidate.signal_id,
                    candidate.from_status,
                    decision.target,
                    actor="daily_workflow",
                    reason="promotion policy approved",
                    evidence_snapshot_id=snapshot.id,
                    metadata={"provenance_id": provenance.provenance_id, "policy_version": decision.policy_version},
                    occurred_at=timestamp,
                )
                ledger_event_id = event.event_id
            promotion_results.append(
                PromotionResult(signal_id=candidate.signal_id, decision=decision, ledger_event_id=ledger_event_id)
            )

        payload = {
            "snapshot_id": snapshot.id,
            "watchlist": list(symbols),
            "evidence_count": len(stored_items),
            "promotions": [
                {
                    "signal_id": result.signal_id,
                    "target": result.decision.target,
                    "approved": result.decision.approved,
                    "failed_gates": list(result.decision.failed_gates),
                }
                for result in promotion_results
            ],
        }
        event = DomainEvent.create(
            "daily.brief.ready",
            snapshot.id,
            payload,
            idempotency_key="daily-brief:%s" % snapshot.id,
            occurred_at=timestamp,
        )
        event_id = self.outbox.publish(event)
        return DailyBrief(
            snapshot_id=snapshot.id,
            captured_at=timestamp,
            watchlist=symbols,
            evidence_count=len(stored_items),
            promotions=tuple(promotion_results),
            event_id=event_id,
        )
