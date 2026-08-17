from agentic.repository import AgenticRepository
from agentic.signals import SignalService


def test_signal_can_move_to_paper_pending_after_manual_confirmation(tmp_path):
    service = SignalService(AgenticRepository(tmp_path / "agentic.db"))
    signal = service.publish(
        agent_id="signal_agent",
        source="signal",
        code="605066",
        direction="buy",
        confidence=0.75,
        time_horizon="3-10d",
        entry_reasons=["AI signal Top"],
        risk_notes=["stop loss required"],
        suggested_position=0.1,
        stop_loss=0.05,
    )

    from agentic.promotion import PromotionContext, PromotionPolicy

    context = PromotionContext(
        evidence_count=1,
        provenance_complete=True,
        backtest_passed=True,
        risk_approved=True,
        signal_validation_passed=True,
    )
    service.approve_paper_pending(signal.id, context, operation_id="op-gate-1")
    updated = service.confirm_paper_pending(
        signal.id,
        confirmed_by="user_1",
        approval_operation_id="op-gate-1",
        operation_id="op-confirm-1",
    )

    assert updated.status == "paper_pending"
    assert updated.metadata["confirmed_by"] == "user_1"
