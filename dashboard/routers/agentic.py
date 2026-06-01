from dataclasses import asdict

from fastapi import APIRouter

from agentic.registry import AgentRegistry
from agentic.repository import AgenticRepository
from agentic.signals import SignalService
from config.settings import DB_DIR

router = APIRouter()
registry = AgentRegistry.default()
signal_service = SignalService(AgenticRepository(DB_DIR / "agentic.db"))


@router.get("/agents")
def list_agents():
    return {"success": True, "agents": [asdict(agent) for agent in registry.list()]}


@router.get("/signals")
def list_signals(limit: int = 100):
    return {"success": True, "signals": [asdict(signal) for signal in signal_service.list(limit=limit)]}


@router.get("/health")
def agentic_health():
    return {
        "success": True,
        "components": {
            "registry": "online",
            "signals": "online",
            "research": "online",
            "strategy_lab": "online",
        },
    }
