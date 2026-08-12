import sqlite3

from agentic.audit_read_model import AuditReadModel
from agentic.signal_ledger import SignalLedger
from data.evidence.models import EvidenceItem, EvidenceLink, EvidenceSnapshot
from data.evidence.store import InMemoryEvidenceStore


def test_audit_read_model_joins_signal_history_and_evidence_without_writes():
    evidence = InMemoryEvidenceStore()
    evidence.save_item(EvidenceItem("item", "source", "Title", "Fact", "2026-08-12T00:00:00Z"))
    evidence.save_snapshot(EvidenceSnapshot("snapshot", "2026-08-12T00:01:00Z", "fixture"))
    evidence.link(EvidenceLink("snapshot", "item"))
    ledger = SignalLedger(sqlite3.connect(":memory:"))
    ledger.append_transition("signal", None, "new")
    ledger.record_provenance("signal", source_type="evidence_snapshot", source_id="snapshot")
    read_model = AuditReadModel(evidence, ledger)
    signal_view = read_model.signal("signal")
    evidence_view = read_model.evidence("snapshot")
    assert signal_view.timeline[0].to_status == "new"
    assert signal_view.provenance[0].source_id == "snapshot"
    assert evidence_view.items[0].id == "item"


def test_audit_read_model_rejects_unknown_signal():
    read_model = AuditReadModel(InMemoryEvidenceStore(), SignalLedger(sqlite3.connect(":memory:")))
    try:
        read_model.signal("missing")
    except KeyError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("unknown signal should not produce an empty audit view")


def test_audit_read_model_rejects_orphan_provenance_without_signal_timeline():
    ledger = SignalLedger(sqlite3.connect(":memory:"))
    ledger.record_provenance("orphan", source_type="fixture", source_id="source")
    read_model = AuditReadModel(InMemoryEvidenceStore(), ledger)
    try:
        read_model.signal("orphan")
    except KeyError:
        pass
    else:
        raise AssertionError("orphan provenance should not create a signal audit view")


def test_audit_read_model_rejects_orphan_timeline_when_canonical_projection_exists():
    connection = sqlite3.connect(":memory:")
    ledger = SignalLedger(connection)
    connection.execute(
        "CREATE TABLE agentic_signals (id TEXT PRIMARY KEY)"
    )
    connection.commit()
    ledger.append_transition("orphan", None, "new")
    read_model = AuditReadModel(InMemoryEvidenceStore(), ledger)
    try:
        read_model.signal("orphan")
    except KeyError:
        pass
    else:
        raise AssertionError("orphan timeline should not create a signal audit view")
