from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from engine.paper_projection import list_reconciliations, open_reconciliation, transition_reconciliation
from engine.paper_runtime import PaperRuntimeConflictError, PaperRuntimeStore
from engine.research_facts import ExecutionRunBlockedError, ResearchFactsStore


def test_runtime_rejects_illegal_resume(tmp_path: Path):
    store = PaperRuntimeStore(tmp_path / "runtime.db")
    record = store.create(account_id="a", run_id="r", status="starting", config={}, owner_id="o", ownership_fence="f")
    record = store.update("a", record.version, status="running")
    record = store.update("a", record.version, status="halt_requested")
    record = store.update("a", record.version, status="halted")
    with pytest.raises(PaperRuntimeConflictError):
        store.update("a", record.version, status="running")


def test_reconciliation_is_append_audited_and_guarded(tmp_path: Path):
    db = tmp_path / "paper.db"
    facts = ResearchFactsStore(db)
    run = facts.ensure_paper_run(account_id="a", workspace_id="w", codes=["000001"])
    reconciliation_id = open_reconciliation(db, account_id="a", workspace_id="w", execution_run_id=run.execution_run_id, category="lease_lost", reason="test")
    assert list_reconciliations(db, account_id="a", workspace_id="w", execution_run_id=run.execution_run_id)[0]["status"] == "open"
    assert transition_reconciliation(db, reconciliation_id, "acknowledged")["status"] == "acknowledged"
    assert transition_reconciliation(db, reconciliation_id, "resolved")["status"] == "resolved"
    with pytest.raises(Exception):
        transition_reconciliation(db, reconciliation_id, "open")


def test_restore_status_never_auto_resumes(tmp_path: Path):
    db = tmp_path / "paper.db"
    facts = ResearchFactsStore(db)
    run = facts.ensure_paper_run(account_id="a", workspace_id="w", codes=["000001"])
    facts.transition_execution_run(run.execution_run_id, "running")
    facts.transition_execution_run(run.execution_run_id, "reconciling", reason="restart")
    with pytest.raises(ExecutionRunBlockedError):
        facts.validate_execution_run(run.execution_run_id)
