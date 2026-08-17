"""Read-only audit routes for evidence and signal provenance."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from agentic.audit_read_model import AuditReadModel
from agentic.signal_ledger import SignalLedger
from config.settings import DB_DIR
from data.evidence.store import SQLiteEvidenceStore


router = APIRouter(prefix="/audit", tags=["audit"])
def _read_model() -> AuditReadModel:
    """Create per-request SQLite adapters so handlers are thread-safe."""
    evidence_store = None
    try:
        evidence_store = SQLiteEvidenceStore(DB_DIR / "evidence.db", readonly=True)
        signal_ledger = SignalLedger(DB_DIR / "agentic.db", readonly=True)
        return AuditReadModel(evidence_store, signal_ledger)
    except Exception:
        if evidence_store is not None:
            evidence_store.close()
        raise


def _event_payload(event):
    return {
        "event_id": event.event_id,
        "signal_id": event.signal_id,
        "sequence": event.sequence,
        "from_status": event.from_status,
        "to_status": event.to_status,
        "occurred_at": event.occurred_at,
        "actor": event.actor,
        "reason": event.reason,
        "evidence_snapshot_id": event.evidence_snapshot_id,
        "metadata": dict(event.metadata),
    }


def _provenance_payload(item):
    return {
        "provenance_id": item.provenance_id,
        "signal_id": item.signal_id,
        "source_type": item.source_type,
        "source_id": item.source_id,
        "evidence_snapshot_id": item.evidence_snapshot_id,
        "recorded_at": item.recorded_at,
        "details": dict(item.details),
    }


def _outcome_payload(item):
    if item is None:
        return None
    return {
        "outcome_id": item.outcome_id,
        "signal_id": item.signal_id,
        "observed_at": item.observed_at,
        "status": item.status,
        "realized_return": item.realized_return,
        "max_drawdown": item.max_drawdown,
        "metadata": dict(item.metadata),
    }


def _evidence_payload(item):
    return {
        "id": item.id,
        "source_id": item.source_id,
        "title": item.title,
        "content": item.content,
        "observed_at": item.observed_at,
        "url": item.url,
        "symbol": item.symbol,
        "fingerprint": item.fingerprint,
        "metadata": dict(item.metadata),
    }


@router.get("/signals/{signal_id}")
def get_signal_audit(signal_id: str):
    model = _read_model()
    try:
        view = model.signal(signal_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        model.close()
    return {
        "signal_id": view.signal_id,
        "timeline": [_event_payload(item) for item in view.timeline],
        "provenance": [_provenance_payload(item) for item in view.provenance],
        "latest_outcome": _outcome_payload(view.latest_outcome),
    }


@router.get("/evidence/{snapshot_id}")
def get_evidence_audit(snapshot_id: str):
    model = _read_model()
    try:
        view = model.evidence(snapshot_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        model.close()
    return {
        "snapshot": {
            "id": view.snapshot.id,
            "captured_at": view.snapshot.captured_at,
            "query": view.snapshot.query,
            "record_ids": list(view.snapshot.record_ids),
            "sealed": view.snapshot.sealed,
            "citable": view.snapshot.citable,
            "metadata": dict(view.snapshot.metadata),
        },
        "items": [
            {
                **_evidence_payload(item),
                "symbols": list(view.item_symbols.get(item.id, ()))
                or ([item.symbol] if item.symbol else []),
            }
            for item in view.items
        ],
    }
