from agentic.models import AgentProfile, ResearchJob, TradingSignal, normalize_signal_code


def test_normalize_signal_code_accepts_exchange_suffix():
    assert normalize_signal_code("605066.SH") == "605066"
    assert normalize_signal_code("sz000001") == "000001"
    assert normalize_signal_code("BJ920099") == "920099"


def test_normalize_signal_code_rejects_ambiguous_or_overlong_input():
    for raw in ["foo1234567", "2026-06-01 605066", "12345", "000001000002"]:
        try:
            normalize_signal_code(raw)
        except ValueError as exc:
            assert "6-digit A-share code" in str(exc)
        else:
            raise AssertionError(f"{raw} should be rejected")


def test_trading_signal_requires_structured_reason_and_risk():
    signal = TradingSignal(
        id="sig_1",
        agent_id="signal_agent",
        source="signal",
        code="605066.SH",
        direction="buy",
        confidence="0.72",
        time_horizon="3-10d",
        entry_reasons=["AI signal top 5", "close above MA20"],
        risk_notes=["break MA20 invalidates signal"],
        suggested_position="0.1",
        stop_loss="0.05",
        take_profit="0.12",
        status="new",
        created_at="2026-06-01T15:00:00+08:00",
        expires_at="2026-06-08T15:00:00+08:00",
    )

    assert signal.code == "605066"
    assert signal.confidence == 0.72
    assert signal.suggested_position == 0.1
    assert signal.entry_reasons[0] == "AI signal top 5"
    assert isinstance(signal.entry_reasons, tuple)


def test_trading_signal_rejects_invalid_direction_and_status():
    base = dict(
        id="sig_1",
        agent_id="signal_agent",
        source="signal",
        code="605066",
        direction="buy",
        confidence=0.72,
        time_horizon="3-10d",
        entry_reasons=["AI signal top 5"],
        risk_notes=["break MA20 invalidates signal"],
        suggested_position=0.1,
        stop_loss=0.05,
        take_profit=0.12,
        status="new",
        created_at="2026-06-01T15:00:00+08:00",
    )

    for patch, message in [({"direction": "strong_buy"}, "unsupported signal direction"), ({"status": "ready"}, "unsupported signal status")]:
        try:
            TradingSignal(**{**base, **patch})
        except ValueError as exc:
            assert message in str(exc)
        else:
            raise AssertionError(f"{patch} should be rejected")


def test_agent_profile_permissions_are_immutable_tuple():
    profile = AgentProfile("a", "Agent", "signal", "desc", ["read_market"])

    assert profile.permissions == ("read_market",)


def test_research_job_normalizes_code_and_roles():
    job = ResearchJob(
        id="research_1",
        code="SH605066",
        status="completed",
        roles=["signal", "market", "theme", "bear", "decision"],
        final_report={"decision": "paper_candidate"},
        created_at="2026-06-01T20:30:00+08:00",
        updated_at="2026-06-01T20:30:00+08:00",
    )

    assert job.code == "605066"
    assert job.roles == ("signal", "market", "theme", "bear", "decision")
