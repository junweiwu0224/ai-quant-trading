from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from engine.adapters.paper_adapter import PaperAdapter, QuoteSnapshot
from engine.execution_protocol import OrderIntent, OrderIntentBatch
from engine.paper_projection import open_reconciliation, transition_reconciliation
from engine.research_facts import ResearchFactsStore, ScopeSnapshot
from engine.risk_gate import RiskGate, RiskPolicy, QuoteSnapshot as RiskQuoteSnapshot, ensure_paper_account, rebuild_account_snapshot


def test_adapter_ignores_authority_opt_out_and_requires_run_scope(tmp_path: Path):
    db = tmp_path / "paper.db"
    facts = ResearchFactsStore(db)
    run = facts.ensure_paper_run(account_id="a", workspace_id="w", codes=["000001"], initial_cash=10_000)
    ensure_paper_account(db, "a", "w", 10_000)
    intent = OrderIntent(run.execution_run_id, "a", "paper", "000001", "buy", 100, "key")
    batch = OrderIntentBatch("batch", (intent,))
    account = rebuild_account_snapshot(db, "a", "w", initial_cash=10_000, execution_run_id=run.execution_run_id)
    now = datetime.now(timezone.utc)
    decision, permit = RiskGate(RiskPolicy(max_single_position_pct=1, max_total_position_pct=1), db_path=db).authorize(
        batch, account, {"000001": RiskQuoteSnapshot("000001", 10, now)}, fence_token="1", execution_run_id=run.execution_run_id
    )
    assert permit is not None
    adapter = PaperAdapter(str(db), workspace_id="w")
    assert adapter.execute_batch(batch, permit, {"000001": QuoteSnapshot("000001", 10, now.isoformat())}, require_authoritative=False)
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM paper_ledger").fetchone()[0] == 1


def test_nested_fact_mapping_is_immutable(tmp_path: Path):
    context = {"source": {"provider": "test"}}
    fact = ScopeSnapshot.create("scope", "instrument", ["000001"], market_context=context)
    context["source"]["provider"] = "mutated"
    with pytest.raises(TypeError):
        fact.market_context["source"]["provider"] = "blocked"
    assert fact.market_context["source"]["provider"] == "test"


def test_reconciliation_events_are_append_only(tmp_path: Path):
    db = tmp_path / "paper.db"
    run = ResearchFactsStore(db).ensure_paper_run(account_id="a", workspace_id="w", codes=["000001"])
    case = open_reconciliation(db, account_id="a", workspace_id="w", execution_run_id=run.execution_run_id, category="test", reason="divergence")
    transition_reconciliation(db, case, "acknowledged", owner_id="operator")
    with sqlite3.connect(db) as connection:
        count = connection.execute("SELECT COUNT(*) FROM paper_reconciliation_events WHERE reconciliation_id = ?", (case,)).fetchone()[0]
    assert count == 2
