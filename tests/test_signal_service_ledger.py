from agentic.promotion import PromotionContext, PromotionPolicy
from agentic.repository import AgenticRepository
from agentic.signals import SignalService


def test_signal_service_writes_projection_and_ledger(tmp_path):
    service = SignalService(AgenticRepository(tmp_path / "agentic.db"))
    signal = service.publish(
        agent_id="agent-1",
        source="fixture",
        code="600000",
        direction="buy",
        confidence=0.8,
        time_horizon="swing",
        entry_reasons=["fixture evidence"],
        risk_notes=["fixture risk"],
        suggested_position=0.1,
    )
    assert [event.to_status for event in service.ledger.timeline(signal.id)] == ["new"]
    context = PromotionContext(
        evidence_count=1,
        provenance_complete=True,
        backtest_passed=True,
        risk_approved=True,
        signal_validation_passed=True,
    )
    approval = service.approve_paper_pending(signal.id, context, operation_id="op-paper-gate-1")
    assert approval.approved is True
    updated = service.confirm_paper_pending(
        signal.id,
        confirmed_by="user-1",
        approval_operation_id="op-paper-gate-1",
        operation_id="op-paper-1",
    )
    assert updated.status == "paper_pending"
    assert [event.to_status for event in service.ledger.timeline(signal.id)] == ["new", "paper_pending"]


def test_signal_paper_pending_requires_two_phase_policy_decision_and_operation_id(tmp_path):
    service = SignalService(AgenticRepository(tmp_path / "agentic.db"))
    signal = service.publish(
        agent_id="agent-1",
        source="fixture",
        code="600000",
        direction="buy",
        confidence=0.8,
        time_horizon="swing",
        entry_reasons=["fixture evidence"],
        risk_notes=["fixture risk"],
        suggested_position=0.1,
    )

    try:
        service.mark_paper_pending(signal.id, confirmed_by="user-1", operation_id="op-no-decision")
    except ValueError as exc:
        assert "approval_operation_id is required" in str(exc)
    else:
        raise AssertionError("paper promotion must not bypass PromotionPolicy")

    decision = PromotionPolicy().evaluate(PromotionContext(), target="paper_pending")
    try:
        service.mark_paper_pending(signal.id, confirmed_by="user-1", decision=decision, operation_id="op-legacy")
    except ValueError as exc:
        assert "bare PromotionDecision" in str(exc)
    else:
        raise AssertionError("paper promotion commands must be idempotency-keyed")


def test_signal_paper_pending_replay_is_idempotent_and_conflict_is_rejected(tmp_path):
    service = SignalService(AgenticRepository(tmp_path / "agentic.db"))
    signal = service.publish(
        agent_id="agent-1",
        source="fixture",
        code="600000",
        direction="buy",
        confidence=0.8,
        time_horizon="swing",
        entry_reasons=["fixture evidence"],
        risk_notes=["fixture risk"],
        suggested_position=0.1,
    )
    context = PromotionContext(
        evidence_count=1,
        provenance_complete=True,
        backtest_passed=True,
        risk_approved=True,
        signal_validation_passed=True,
    )
    service.approve_paper_pending(signal.id, context, operation_id="op-replay-gate-1")
    decision = PromotionPolicy().evaluate(context, target="paper_pending")
    first = service.confirm_paper_pending(
        signal.id,
        confirmed_by="user-1",
        approval_operation_id="op-replay-gate-1",
        operation_id="op-replay-1",
    )
    replay = service.confirm_paper_pending(
        signal.id,
        confirmed_by="user-1",
        approval_operation_id="op-replay-gate-1",
        operation_id="op-replay-1",
    )
    assert replay == first
    assert len(service.ledger.timeline(signal.id)) == 2

    try:
        service.mark_paper_pending(signal.id, confirmed_by="user-2", decision=decision, operation_id="op-other")
    except ValueError as exc:
        assert "bare PromotionDecision" in str(exc)
    else:
        raise AssertionError("a different operation must not replay a completed transition")
