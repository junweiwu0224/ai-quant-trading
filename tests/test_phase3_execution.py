"""Phase 3 frozen-fact, execution-run, and authoritative RiskGate tests."""
from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from engine.adapters.paper_adapter import PaperAdapter, QuoteSnapshot as AdapterQuote
from engine.execution_protocol import Environment, OrderIntent, OrderIntentBatch, RiskDecisionStatus, Side
from engine.research_facts import (
    Approval,
    DataSnapshot,
    ExecutionRunBlockedError,
    FactConflictError,
    Qualification,
    ResearchFactsStore,
    ScopeSnapshot,
    StrategyVersion,
    ValidationRun,
)
from engine.risk_gate import AccountSnapshot, QuoteSnapshot, RiskGate, RiskPolicy


UTC = timezone.utc


def now() -> datetime:
    return datetime.now(UTC)


def account(
    *,
    cash: str = "10000",
    total: str = "10000",
    positions: dict[str, str] | None = None,
    values: dict[str, str] | None = None,
    today_buys: set[str] | None = None,
    industries: dict[str, str] | None = None,
) -> AccountSnapshot:
    return AccountSnapshot(
        account_id="acct",
        workspace_id="ws",
        environment=Environment.PAPER,
        initial_cash=cash,
        cash=cash,
        total_equity=total,
        positions=positions or {},
        position_values=values or {},
        avg_prices={key: "10" for key in (positions or {})},
        today_buys=frozenset(today_buys or set()),
        industry_values=industries or {},
        fence_token="f-1",
    )


def batch(instrument: str = "000001", side: Side = Side.BUY, quantity: int = 100, *, run_id: str = "run-1", key: str = "key-1", emergency: bool = False) -> OrderIntentBatch:
    return OrderIntentBatch(
        batch_id=f"batch-{key}",
        intents=(OrderIntent(
            execution_run_id=run_id,
            account_id="acct",
            environment=Environment.PAPER,
            instrument=instrument,
            side=side,
            quantity=quantity,
            idempotency_key=key,
            emergency=emergency,
        ),),
    )


def quote(price: str = "10", **kwargs) -> QuoteSnapshot:
    return QuoteSnapshot("000001", price, now(), **kwargs)


def make_chain(db_path: Path, *, data_captured_at: datetime | None = None, data_freshness: int = 86400, ai_only: bool = False, mode: str = "executable", approved: bool = True):
    store = ResearchFactsStore(db_path)
    current = now()
    scope = ScopeSnapshot.create("scope-1", "universe", ["000001"], workspace_id="ws", account_id="acct", captured_at=current)
    data = DataSnapshot.create("data-1", "v1", current - timedelta(days=2), current, ["000001"], 10, "checksum", workspace_id="ws", account_id="acct", captured_at=data_captured_at or current, freshness_seconds=data_freshness)
    strategy = StrategyVersion.create("strategy", "def strategy(): return 1", {"window": 5}, strategy_version_id="strategy-1", workspace_id="ws", account_id="acct", captured_at=current, ai_only=ai_only)
    validation = ValidationRun.create("validation-1", scope=scope, data=data, strategy=strategy, metrics={"sharpe": 2}, mode=mode, completed_at=current)
    qualification = Qualification.create("qualification-1", validation=validation, passed=True, qualified_until=current + timedelta(days=1))
    approval = Approval.create("approval-1", qualification_id=qualification.qualification_id, approved_by="operator", authority="human", approved_at=current) if approved else None
    for fact, method in ((scope, store.save_scope), (data, store.save_data), (strategy, store.save_strategy), (validation, store.save_validation), (qualification, store.save_qualification)):
        method(fact)
    if approval:
        store.save_approval(approval)
    return store, scope, data, strategy, validation, qualification, approval


def test_snapshot_dataclasses_are_immutable_and_hashed():
    fact = ScopeSnapshot.create("scope", "instrument", ["000001"], captured_at=now())
    with pytest.raises(Exception):
        fact.members = ("000002",)
    same = ScopeSnapshot.create("scope", "instrument", ["000001"], captured_at=fact.captured_at)
    assert same.content_hash == fact.content_hash
    changed = ScopeSnapshot.create("scope", "instrument", ["000002"], captured_at=fact.captured_at)
    assert changed.content_hash != fact.content_hash


def test_strategy_hash_canonicalizes_mapping_order():
    first = StrategyVersion.create("s", "code", {"b": 2, "a": 1}, captured_at=now())
    second = StrategyVersion.create("s", "code", {"a": 1, "b": 2}, captured_at=first.captured_at)
    assert first.content_hash == second.content_hash


def test_fact_store_rejects_mutating_existing_fact(tmp_path: Path):
    store = ResearchFactsStore(tmp_path / "facts.db")
    fact = ScopeSnapshot.create("scope", "instrument", ["000001"], captured_at=now())
    store.save_scope(fact)
    store.save_scope(fact)
    changed = ScopeSnapshot.create("scope", "instrument", ["000002"], captured_at=fact.captured_at)
    with pytest.raises(FactConflictError):
        store.save_scope(changed)


def test_execution_run_requires_all_frozen_references(tmp_path: Path):
    store = ResearchFactsStore(tmp_path / "facts.db")
    with pytest.raises(ExecutionRunBlockedError, match="missing frozen references"):
        store.create_execution_run(execution_run_id="run", workspace_id="ws", account_id="acct", environment="paper", scope_snapshot_id="missing-scope", data_snapshot_id="missing-data", strategy_version_id="missing-strategy", validation_run_id="missing-validation", qualification_id="missing-qualification", require_approval=False)


def test_execution_run_requires_human_approval(tmp_path: Path):
    store, scope, data, strategy, validation, qualification, _ = make_chain(tmp_path / "facts.db", approved=False)
    with pytest.raises(ExecutionRunBlockedError, match="approval"):
        store.create_execution_run(execution_run_id="run", workspace_id="ws", account_id="acct", environment="paper", scope_snapshot_id=scope.scope_id, data_snapshot_id=data.data_id, strategy_version_id=strategy.strategy_version_id, validation_run_id=validation.validation_run_id, qualification_id=qualification.qualification_id)


def test_execution_run_accepts_complete_chain(tmp_path: Path):
    store, scope, data, strategy, validation, qualification, approval = make_chain(tmp_path / "facts.db")
    run = store.create_execution_run(execution_run_id="run", workspace_id="ws", account_id="acct", environment="paper", scope_snapshot_id=scope.scope_id, data_snapshot_id=data.data_id, strategy_version_id=strategy.strategy_version_id, validation_run_id=validation.validation_run_id, qualification_id=qualification.qualification_id, approval_id=approval.approval_id)
    assert run.status == "ready"
    assert store.validate_execution_run("run").content_hash == run.content_hash


def test_execution_run_rejects_stale_data(tmp_path: Path):
    store, scope, data, strategy, validation, qualification, approval = make_chain(tmp_path / "facts.db", data_captured_at=now() - timedelta(days=2), data_freshness=60)
    with pytest.raises(ExecutionRunBlockedError, match="stale"):
        store.create_execution_run(execution_run_id="run", workspace_id="ws", account_id="acct", environment="paper", scope_snapshot_id=scope.scope_id, data_snapshot_id=data.data_id, strategy_version_id=strategy.strategy_version_id, validation_run_id=validation.validation_run_id, qualification_id=qualification.qualification_id, approval_id=approval.approval_id)


def test_execution_run_rejects_ai_only_artifact(tmp_path: Path):
    store, scope, data, strategy, validation, qualification, approval = make_chain(tmp_path / "facts.db", ai_only=True)
    with pytest.raises(ExecutionRunBlockedError, match="AI-only"):
        store.create_execution_run(execution_run_id="run", workspace_id="ws", account_id="acct", environment="paper", scope_snapshot_id=scope.scope_id, data_snapshot_id=data.data_id, strategy_version_id=strategy.strategy_version_id, validation_run_id=validation.validation_run_id, qualification_id=qualification.qualification_id, approval_id=approval.approval_id)


def test_execution_run_rejects_exploratory_validation(tmp_path: Path):
    store, scope, data, strategy, validation, qualification, approval = make_chain(tmp_path / "facts.db", mode="exploratory")
    with pytest.raises(ExecutionRunBlockedError, match="exploratory"):
        store.create_execution_run(execution_run_id="run", workspace_id="ws", account_id="acct", environment="paper", scope_snapshot_id=scope.scope_id, data_snapshot_id=data.data_id, strategy_version_id=strategy.strategy_version_id, validation_run_id=validation.validation_run_id, qualification_id=qualification.qualification_id, approval_id=approval.approval_id)


def test_execution_run_rejects_hash_tampering(tmp_path: Path):
    db = tmp_path / "facts.db"
    store, scope, data, strategy, validation, qualification, approval = make_chain(db)
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE research_data_snapshots SET checksum = 'tampered' WHERE data_id = 'data-1'")
        connection.commit()
    with pytest.raises(ExecutionRunBlockedError, match="hash"):
        store.create_execution_run(execution_run_id="run", workspace_id="ws", account_id="acct", environment="paper", scope_snapshot_id=scope.scope_id, data_snapshot_id=data.data_id, strategy_version_id=strategy.strategy_version_id, validation_run_id=validation.validation_run_id, qualification_id=qualification.qualification_id, approval_id=approval.approval_id)


def test_live_execution_run_is_fail_closed(tmp_path: Path):
    store = ResearchFactsStore(tmp_path / "facts.db")
    with pytest.raises((ExecutionRunBlockedError, ValueError)):
        store.create_execution_run(execution_run_id="live", workspace_id="ws", account_id="acct", environment=Environment.LIVE, scope_snapshot_id="s", data_snapshot_id="d", strategy_version_id="v", validation_run_id="vr", qualification_id="q", require_approval=False)


def test_risk_gate_approves_valid_buy():
    gate = RiskGate(RiskPolicy(max_single_position_pct=1, max_total_position_pct=1))
    decision = gate.check_batch(batch(), account(), {"000001": quote()})
    assert decision.status is RiskDecisionStatus.APPROVED


def test_risk_gate_rejects_insufficient_cash():
    gate = RiskGate(RiskPolicy(max_single_position_pct=1, max_total_position_pct=1))
    decision = gate.check_batch(batch(quantity=1000), account(cash="10", total="10"), {"000001": quote()})
    assert decision.status is RiskDecisionStatus.REJECTED
    assert any("cash" in reason for reason in decision.reasons)


def test_risk_gate_rejects_non_lot_quantity():
    decision = RiskGate().check_batch(batch(quantity=1), account(), {"000001": quote()})
    assert decision.status is RiskDecisionStatus.REJECTED
    assert any("multiple" in reason for reason in decision.reasons)


def test_risk_gate_rejects_single_position_limit():
    policy = RiskPolicy(max_single_position_pct=Decimal("0.20"), max_total_position_pct=Decimal("1"))
    decision = RiskGate(policy).check_batch(batch(), account(cash="2000", total="1000"), {"000001": quote()})
    assert decision.status is RiskDecisionStatus.REJECTED
    assert any("single" in reason for reason in decision.reasons)


def test_risk_gate_rejects_total_position_limit():
    policy = RiskPolicy(max_single_position_pct=Decimal("1"), max_total_position_pct=Decimal("0.50"), max_industry_pct=Decimal("1"))
    decision = RiskGate(policy).check_batch(batch(), account(cash="3000", total="2000", positions={"x": "100"}, values={"x": "1000"}), {"000001": quote()})
    assert decision.status is RiskDecisionStatus.REJECTED
    assert any("total" in reason for reason in decision.reasons)


def test_risk_gate_rejects_industry_limit():
    policy = RiskPolicy(max_single_position_pct=Decimal("1"), max_total_position_pct=Decimal("1"), max_industry_pct=Decimal("0.50"))
    decision = RiskGate(policy).check_batch(batch(), account(cash="3000", total="2000", industries={"bank": "1000"}), {"000001": quote(industry="bank")})
    assert decision.status is RiskDecisionStatus.REJECTED
    assert any("industry" in reason for reason in decision.reasons)


def test_risk_gate_rejects_t1_sale():
    policy = RiskPolicy(max_single_position_pct=Decimal("1"), max_total_position_pct=Decimal("1"))
    decision = RiskGate(policy).check_batch(batch(side=Side.SELL), account(cash="0", total="1000", positions={"000001": "100"}, values={"000001": "1000"}, today_buys={"000001"}), {"000001": quote()})
    assert decision.status is RiskDecisionStatus.REJECTED
    assert any("T+1" in reason for reason in decision.reasons)


def test_risk_gate_rejects_insufficient_sell_quantity():
    decision = RiskGate().check_batch(batch(side=Side.SELL), account(cash="0", total="1000", positions={"000001": "0"}), {"000001": quote()})
    assert decision.status is RiskDecisionStatus.REJECTED
    assert any("position" in reason for reason in decision.reasons)


def test_risk_gate_rejects_limit_up_and_down():
    policy = RiskPolicy(max_single_position_pct=Decimal("1"), max_total_position_pct=Decimal("1"))
    buy_decision = RiskGate(policy).check_batch(batch(), account(), {"000001": quote(limit_up="9")})
    sell_decision = RiskGate(policy).check_batch(batch(side=Side.SELL), account(cash="0", positions={"000001": "100"}, values={"000001": "1000"}), {"000001": quote(limit_down="11")})
    assert buy_decision.status is RiskDecisionStatus.REJECTED
    assert sell_decision.status is RiskDecisionStatus.REJECTED


def test_risk_gate_rejects_suspended_quote():
    decision = RiskGate().check_batch(batch(), account(), {"000001": quote(is_suspended=True)})
    assert decision.status is RiskDecisionStatus.REJECTED


def test_risk_gate_supports_partial_approval():
    policy = RiskPolicy(max_single_position_pct=Decimal("1"), max_industry_pct=Decimal("1"), max_total_position_pct=Decimal("1"))
    first = batch(key="a")
    second = OrderIntent(execution_run_id="run-1", account_id="acct", environment="paper", instrument="000002", side=Side.BUY, quantity=1000, idempotency_key="b")
    combined = OrderIntentBatch("combined", (first.intents[0], second))
    decision = RiskGate(policy).check_batch(combined, account(cash="2000", total="2000"), {"000001": quote(), "000002": QuoteSnapshot("000002", "10", now())})
    assert decision.status is RiskDecisionStatus.PARTIALLY_APPROVED
    assert decision.approved_intent_keys == ("a",)


def test_authoritative_permit_is_persisted_and_adapter_accepts_it(tmp_path: Path):
    db = tmp_path / "paper.db"
    store = ResearchFactsStore(db)
    run = store.ensure_paper_run(account_id="acct", workspace_id="ws", codes=["000001"], initial_cash=10000)
    item = OrderIntent(run.execution_run_id, "acct", "paper", "000001", "buy", 100, "auth-key")
    order_batch = OrderIntentBatch("auth-batch", (item,))
    gate = RiskGate(RiskPolicy(max_single_position_pct=1, max_total_position_pct=1), db_path=db)
    account_snapshot = account(cash="10000", total="10000")
    decision, permit = gate.authorize(order_batch, account_snapshot, {"000001": quote()}, fence_token="1", execution_run_id=run.execution_run_id)
    assert permit is not None
    adapter = PaperAdapter(str(db), workspace_id="ws")
    fills = adapter.execute_batch(order_batch, permit, {"000001": AdapterQuote("000001", 10, now().isoformat())}, require_authoritative=True)
    assert len(fills) == 1
    assert adapter.execute_batch(order_batch, permit, {"000001": AdapterQuote("000001", 10, now().isoformat())}, require_authoritative=True) == []


def test_api_advisory_permit_cannot_be_used_without_authority(tmp_path: Path):
    db = tmp_path / "paper.db"
    store = ResearchFactsStore(db)
    run = store.ensure_paper_run(account_id="acct", workspace_id="ws", codes=["000001"])
    item = OrderIntent(run.execution_run_id, "acct", "paper", "000001", "buy", 100, "untrusted")
    order_batch = OrderIntentBatch("untrusted-batch", (item,))
    from engine.execution_protocol import ExecutionPermit, RiskDecision
    decision = RiskDecision.from_batch(order_batch, decision_id="api", policy_version="api", evaluated_at=now(), status="approved", approved_intent_keys=("untrusted",))
    permit = ExecutionPermit.from_decision(decision, permit_id="api-permit", expires_at=now() + timedelta(minutes=1), fence_token="1")
    adapter = PaperAdapter(str(db), workspace_id="ws")
    assert adapter.execute_batch(order_batch, permit, {"000001": AdapterQuote("000001", 10, now().isoformat())}, require_authoritative=True) == []
