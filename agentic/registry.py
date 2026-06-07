from __future__ import annotations

from agentic.models import AgentProfile


class AgentRegistry:
    def __init__(self, agents: list[AgentProfile]):
        self._agents = {agent.id: agent for agent in agents}

    @classmethod
    def default(cls) -> "AgentRegistry":
        return cls(
            [
                AgentProfile(
                    "signal_agent",
                    "Signal Engine Agent",
                    "signal",
                    "Publishes ranked full-market signals from Signal Engine providers.",
                    ["read_market", "publish_signal"],
                ),
                AgentProfile(
                    "qlib_agent",
                    "Signal Engine Agent",
                    "signal",
                    "Legacy alias for Signal Engine ranked momentum signals.",
                    ["read_market", "publish_signal"],
                ),
                AgentProfile(
                    "hotspot_agent",
                    "Hotspot Attribution Agent",
                    "signal",
                    "Publishes theme and sector-driven signals.",
                    ["read_market", "publish_signal"],
                ),
                AgentProfile(
                    "iwencai_agent",
                    "Iwencai Screening Agent",
                    "signal",
                    "Publishes signals from saved iWencai result pools.",
                    ["read_market", "publish_signal"],
                ),
                AgentProfile(
                    "risk_agent",
                    "Risk Review Agent",
                    "risk",
                    "Publishes risk warnings only.",
                    ["read_market", "publish_risk_signal"],
                ),
                AgentProfile(
                    "openclaw_research_agent",
                    "OpenClaw Research Agent",
                    "research",
                    "Synthesizes structured research conclusions.",
                    ["read_market", "publish_signal", "create_research_job"],
                ),
            ]
        )

    def get(self, agent_id: str) -> AgentProfile:
        try:
            return self._agents[agent_id]
        except KeyError as exc:
            raise KeyError(f"unknown agent: {agent_id}") from exc

    def list(self) -> list[AgentProfile]:
        return list(self._agents.values())
