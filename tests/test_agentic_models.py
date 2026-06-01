from agentic.models import AgentProfile, TradingSignal, normalize_signal_code


def test_normalize_signal_code_accepts_exchange_suffix():
    assert normalize_signal_code("605066.SH") == "605066"
    assert normalize_signal_code("sz000001") == "000001"


def test_trading_signal_requires_structured_reason_and_risk():
    signal = TradingSignal(
        id="sig_1",
        agent_id="qlib_agent",
        source="qlib",
        code="605066.SH",
        direction="buy",
        confidence=0.72,
        time_horizon="3-10d",
        entry_reasons=["Qlib score top 5", "close above MA20"],
        risk_notes=["break MA20 invalidates signal"],
        suggested_position=0.1,
        stop_loss=0.05,
        take_profit=0.12,
        status="new",
        created_at="2026-06-01T15:00:00+08:00",
        expires_at="2026-06-08T15:00:00+08:00",
    )

    assert signal.code == "605066"
    assert signal.confidence == 0.72
    assert signal.entry_reasons[0] == "Qlib score top 5"


def test_agent_profile_defaults_to_enabled():
    profile = AgentProfile(
        id="risk_agent",
        name="Risk Review Agent",
        kind="risk",
        description="Publishes risk warnings only.",
    )

    assert profile.permissions == []
    assert profile.enabled is True
