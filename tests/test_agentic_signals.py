from agentic.repository import AgenticRepository
from agentic.signals import SignalService


def test_signal_service_publishes_signal_with_generated_id(tmp_path):
    service = SignalService(AgenticRepository(tmp_path / "agentic.db"))

    signal = service.publish(
        agent_id="signal_agent",
        source="signal",
        code="605066.SH",
        direction="buy",
        confidence=0.71,
        time_horizon="3-10d",
        entry_reasons=["AI signal Top", "MA20 uptrend"],
        risk_notes=["Break MA20 invalidates"],
        suggested_position=0.1,
        stop_loss=0.05,
        take_profit=0.12,
        metadata={"pool": "signal_top"},
    )

    assert signal.id.startswith("sig_")
    assert signal.status == "new"
    assert signal.code == "605066"
    assert signal.metadata == {"pool": "signal_top"}
    assert service.list(limit=1)[0].id == signal.id
