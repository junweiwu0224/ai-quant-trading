"""Read-only audit query seam for dashboard and reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Tuple

from data.evidence.models import EvidenceItem, EvidenceSnapshot
from data.evidence.store import EvidenceStore

from .signal_ledger import SignalEvent, SignalLedger, SignalOutcome, SignalProvenance


@dataclass(frozen=True)
class SignalAuditView:
    signal_id: str
    timeline: Tuple[SignalEvent, ...]
    provenance: Tuple[SignalProvenance, ...]
    latest_outcome: Optional[SignalOutcome]


@dataclass(frozen=True)
class EvidenceAuditView:
    snapshot: EvidenceSnapshot
    items: Tuple[EvidenceItem, ...]
    item_symbols: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)


class AuditReadModel:
    """Small read-only Interface; it never mutates projections or evidence."""

    def __init__(self, evidence_store: EvidenceStore, signal_ledger: SignalLedger) -> None:
        self.evidence_store = evidence_store
        self.signal_ledger = signal_ledger

    def close(self) -> None:
        for adapter in (self.evidence_store, self.signal_ledger):
            close = getattr(adapter, "close", None)
            if callable(close):
                close()

    def signal(self, signal_id: str) -> SignalAuditView:
        timeline = tuple(self.signal_ledger.timeline(signal_id))
        provenance = tuple(self.signal_ledger.provenance(signal_id))
        latest_outcome = self.signal_ledger.latest_outcome(signal_id)
        # A provenance/outcome row without a signal timeline is an orphan, not
        # proof that the requested signal exists.  Keep unknown IDs 404-able.
        canonical_exists = self.signal_ledger.canonical_signal_exists(signal_id)
        if not timeline or canonical_exists is False:
            raise KeyError("signal audit not found: %s" % signal_id)
        return SignalAuditView(
            signal_id=signal_id,
            timeline=timeline,
            provenance=provenance,
            latest_outcome=latest_outcome,
        )

    def evidence(self, snapshot_id: str) -> EvidenceAuditView:
        snapshot = self.evidence_store.get_snapshot(snapshot_id)
        if snapshot is None:
            raise KeyError("evidence snapshot not found: %s" % snapshot_id)
        items = tuple(self.evidence_store.list_items(snapshot_id))
        return EvidenceAuditView(
            snapshot=snapshot,
            items=items,
            item_symbols={
                item.id: tuple(self.evidence_store.list_item_symbols(snapshot_id, item.id))
                for item in items
            },
        )
