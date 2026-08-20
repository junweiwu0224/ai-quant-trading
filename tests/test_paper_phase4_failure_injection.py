from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from engine.adapters.paper_adapter import PaperAdapter, QuoteSnapshot
from engine.execution_protocol import ExecutionPermit, OrderIntent, OrderIntentBatch, RiskDecision
from engine.research_facts import ResearchFactsStore
from engine.risk_gate import RiskGate, RiskPolicy, rebuild_account_snapshot, ensure_paper_account


def test_commit_failure_rolls_back_ledger_and_outbox(tmp_path: Path):
    db = tmp_path / "paper.db"
    store = ResearchFactsStore(db)
    run = store.ensure_paper_run(account_id="a", workspace_id="w", codes=["000001"], initial_cash=10000)
    ensure_paper_account(db, "a", "w", 10000)
    intent = OrderIntent(run.execution_run_id, "a", "paper", "000001", "buy", 100, "failure-key")
    batch = OrderIntentBatch("failure-batch", (intent,))
    account = rebuild_account_snapshot(db, "a", "w", initial_cash=10000, execution_run_id=run.execution_run_id)
    gate = RiskGate(RiskPolicy(max_single_position_pct=1, max_total_position_pct=1), db_path=db)
    _, permit = gate.authorize(batch, account, {"000001": __import__("engine.risk_gate", fromlist=["QuoteSnapshot"]).QuoteSnapshot("000001", 10, datetime.now(timezone.utc))}, fence_token="1", execution_run_id=run.execution_run_id)
    assert permit is not None
    adapter = PaperAdapter(str(db), workspace_id="w", failure_hook=lambda point: (_ for _ in ()).throw(RuntimeError(point)) if point == "commit_before_commit" else None)
    with pytest.raises(RuntimeError, match="commit_before_commit"):
        adapter.execute_batch(batch, permit, {"000001": QuoteSnapshot("000001", 10, datetime.now(timezone.utc).isoformat())})
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM paper_ledger").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM paper_outbox").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM paper_audit WHERE result = 'success'").fetchone()[0] == 0
