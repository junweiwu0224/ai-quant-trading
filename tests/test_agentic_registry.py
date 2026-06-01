from agentic.registry import AgentRegistry


def test_builtin_agents_cover_quant_research_and_signal_sources():
    registry = AgentRegistry.default()

    assert registry.get("qlib_agent").name == "Qlib Momentum Agent"
    assert registry.get("hotspot_agent").kind == "signal"
    assert registry.get("risk_agent").permissions == ["read_market", "publish_risk_signal"]
    assert "publish_signal" in registry.get("openclaw_research_agent").permissions


def test_default_registry_lists_all_builtin_agents():
    registry = AgentRegistry.default()

    assert [agent.id for agent in registry.list()] == [
        "qlib_agent",
        "hotspot_agent",
        "iwencai_agent",
        "risk_agent",
        "openclaw_research_agent",
    ]
