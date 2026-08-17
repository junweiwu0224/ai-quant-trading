import sqlite3

import pytest

from agentic.promotion import PromotionContext, PromotionPolicy
from agentic.signal_ledger import SignalLedger, SignalLedgerConflict


def test_signal_ledger_requires_current_status_and_keeps_history():
    ledger = SignalLedger(sqlite3.connect(":memory:"))
    first = ledger.append_transition("sig-1", None, "new", reason="created")
    second = ledger.append_transition("sig-1", "new", "paper_pending", reason="gate passed")
    assert [event.to_status for event in ledger.timeline("sig-1")] == ["new", "paper_pending"]
    assert second.sequence == first.sequence + 1
    ledger.record_provenance("sig-1", source_type="snapshot", source_id="snap-1")
    outcome = ledger.record_outcome("sig-1", status="closed", realized_return=0.05)
    assert ledger.latest_outcome("sig-1") == outcome
    with pytest.raises(SignalLedgerConflict):
        ledger.append_transition("sig-1", "new", "closed")


def test_promotion_policy_separates_paper_from_live():
    policy = PromotionPolicy(min_paper_observations=3)
    context = PromotionContext(
        evidence_count=2,
        provenance_complete=True,
        backtest_passed=True,
        risk_approved=True,
        signal_validation_passed=True,
        paper_observations=3,
        paper_return=0.02,
        max_drawdown=0.05,
    )
    paper = policy.evaluate(context, target="paper_pending")
    live_without_manual = policy.evaluate(context, target="live_eligible")
    assert paper.approved
    assert not live_without_manual.approved
    assert "manual_approval" in live_without_manual.failed_gates
    assert live_without_manual.target == "live_eligible"
