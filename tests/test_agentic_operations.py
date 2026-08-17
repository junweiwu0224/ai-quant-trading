import pytest

from agentic.operations import OperationConflict
from agentic.promotion import PromotionContext, PromotionPolicy
from agentic.repository import AgenticRepository
from agentic.signals import SignalService


def _publish(service: SignalService, code: str):
    return service.publish(
        agent_id="signal_agent",
        source="fixture",
        code=code,
        direction="buy",
        confidence=0.8,
        time_horizon="swing",
        entry_reasons=["fixture evidence"],
        risk_notes=["fixture risk"],
        suggested_position=0.1,
    )


def _decision():
    return PromotionPolicy().evaluate(
        PromotionContext(
            evidence_count=1,
            provenance_complete=True,
            backtest_passed=True,
            risk_approved=True,
            signal_validation_passed=True,
        ),
        target="paper_pending",
    )


def _context():
    return PromotionContext(
        evidence_count=1,
        provenance_complete=True,
        backtest_passed=True,
        risk_approved=True,
        signal_validation_passed=True,
    )


def test_paper_gate_persists_policy_decision_without_transition_and_replays(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    service = SignalService(repo)
    signal = _publish(service, "600000")

    first = service.approve_paper_pending(
        signal.id,
        _context(),
        operation_id="op-gate-persisted-1",
    )
    replay = service.approve_paper_pending(
        signal.id,
        _context(),
        operation_id="op-gate-persisted-1",
    )

    assert first == replay
    assert first.approved is True
    assert repo.get_signal(signal.id).status == "new"
    operation = repo.get_operation("op-gate-persisted-1")
    assert operation.command == "signal.paper_gate"
    assert operation.result["decision"]["approved"] is True
    assert service.ledger.timeline(signal.id)[0].to_status == "new"


def test_paper_confirmation_requires_persisted_approved_gate_and_replays(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    service = SignalService(repo)
    signal = _publish(service, "600000")

    service.approve_paper_pending(signal.id, _context(), operation_id="op-gate-1")
    first = service.confirm_paper_pending(
        signal.id,
        confirmed_by="user-1",
        approval_operation_id="op-gate-1",
        operation_id="op-confirm-1",
    )
    replay = service.confirm_paper_pending(
        signal.id,
        confirmed_by="user-1",
        approval_operation_id="op-gate-1",
        operation_id="op-confirm-1",
    )

    assert replay == first
    assert first.status == "paper_pending"
    assert first.metadata["promotion_approval"]["operation_id"] == "op-gate-1"
    assert len(service.ledger.timeline(signal.id)) == 2


def test_paper_confirmation_rejects_unapproved_or_missing_gate(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    service = SignalService(repo)
    signal = _publish(service, "600000")
    rejected = service.approve_paper_pending(
        signal.id,
        PromotionContext(),
        operation_id="op-gate-rejected-1",
    )
    assert rejected.approved is False

    with pytest.raises(ValueError, match="not approved"):
        service.confirm_paper_pending(
            signal.id,
            confirmed_by="user-1",
            approval_operation_id="op-gate-rejected-1",
            operation_id="op-confirm-rejected-1",
        )

    with pytest.raises(KeyError, match="operation not found"):
        service.confirm_paper_pending(
            signal.id,
            confirmed_by="user-1",
            approval_operation_id="op-missing-gate-1",
            operation_id="op-confirm-missing-1",
        )


def test_signal_transition_persists_operation_and_replays_without_new_ledger_event(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    service = SignalService(repo)
    signal = _publish(service, "600000")
    service.approve_paper_pending(signal.id, _context(), operation_id="op-persisted-gate-1")
    first = service.confirm_paper_pending(
        signal.id,
        confirmed_by="user-1",
        approval_operation_id="op-persisted-gate-1",
        operation_id="op-persisted-1",
    )
    replay = service.confirm_paper_pending(
        signal.id,
        confirmed_by="user-1",
        approval_operation_id="op-persisted-gate-1",
        operation_id="op-persisted-1",
    )
    operation = repo.get_operation("op-persisted-1")

    assert replay == first
    assert operation.command == "signal.paper_pending.confirm"
    assert operation.aggregate_id == signal.id
    assert operation.status == "completed"
    assert operation.result["status"] == "paper_pending"
    assert len(service.ledger.timeline(signal.id)) == 2


def test_signal_operation_id_cannot_be_reused_for_another_signal_or_changed_facts(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    service = SignalService(repo)
    first_signal = _publish(service, "600000")
    second_signal = _publish(service, "000001")
    service.approve_paper_pending(first_signal.id, _context(), operation_id="op-global-gate-1")
    service.confirm_paper_pending(
        first_signal.id,
        confirmed_by="user-1",
        approval_operation_id="op-global-gate-1",
        operation_id="op-global-1",
    )

    with pytest.raises(OperationConflict, match="different command facts"):
        service.confirm_paper_pending(
            first_signal.id,
            confirmed_by="user-2",
            approval_operation_id="op-global-gate-1",
            operation_id="op-global-1",
        )

    service.approve_paper_pending(second_signal.id, _context(), operation_id="op-global-gate-2")
    with pytest.raises(OperationConflict, match="different command facts"):
        service.confirm_paper_pending(
            second_signal.id,
            confirmed_by="user-1",
            approval_operation_id="op-global-gate-2",
            operation_id="op-global-1",
        )
