from pathlib import Path


def test_audit_router_does_not_keep_module_level_sqlite_read_connections():
    source = (Path(__file__).resolve().parents[1] / "dashboard" / "routers" / "audit.py").read_text()
    assert "_evidence_store = SQLiteEvidenceStore" not in source
    assert "_signal_ledger = SignalLedger" not in source
    assert "def _read_model() -> AuditReadModel" in source
    assert "readonly=True" in source
    assert "model.close()" in source
