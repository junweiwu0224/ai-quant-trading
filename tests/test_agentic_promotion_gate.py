from agentic.repository import AgenticRepository
from agentic.signals import SignalService


def test_signal_can_move_to_paper_pending_after_manual_confirmation(tmp_path):
    service = SignalService(AgenticRepository(tmp_path / "agentic.db"))
    signal = service.publish(
        agent_id="qlib_agent",
        source="qlib",
        code="605066",
        direction="buy",
        confidence=0.75,
        time_horizon="3-10d",
        entry_reasons=["Qlib Top"],
        risk_notes=["stop loss required"],
        suggested_position=0.1,
        stop_loss=0.05,
    )

    updated = service.mark_paper_pending(signal.id, confirmed_by="user_1")

    assert updated.status == "paper_pending"
    assert updated.metadata["confirmed_by"] == "user_1"
