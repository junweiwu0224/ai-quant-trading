from dataclasses import asdict

from fastapi import APIRouter
from pydantic import BaseModel

from agentic.backtest_compiler import BacktestCompileRequest, BacktestCompiler
from agentic.registry import AgentRegistry
from agentic.repository import AgenticRepository
from agentic.signals import SignalService
from agentic.strategy_dsl import StrategyDSL
from config.settings import DB_DIR

router = APIRouter()
registry = AgentRegistry.default()
signal_service = SignalService(AgenticRepository(DB_DIR / "agentic.db"))
backtest_compiler = BacktestCompiler()


class StrategyDSLPayload(BaseModel):
    strategy_type: str
    universe: str
    rank_by: str
    filters: list[dict] = []
    rebalance: str = "daily"
    max_holdings: int
    stop_loss: float
    take_profit: float | None = None
    max_holding_days: int | None = None

    def to_dsl(self) -> StrategyDSL:
        return StrategyDSL(
            self.strategy_type,
            self.universe,
            self.rank_by,
            self.filters,
            self.rebalance,
            self.max_holdings,
            self.stop_loss,
            self.take_profit,
            self.max_holding_days,
        )


class CompileBacktestPayload(BaseModel):
    dsl: StrategyDSLPayload
    codes: list[str]
    start_date: str
    end_date: str
    initial_cash: float = 1_000_000
    commission_rate: float = 0.0003
    stamp_tax_rate: float = 0.001
    slippage: float = 0.002
    benchmark: str = ""
    period: str = "daily"


@router.get("/agents")
def list_agents():
    return {"success": True, "agents": [asdict(agent) for agent in registry.list()]}


@router.get("/signals")
def list_signals(limit: int = 100):
    return {"success": True, "signals": [asdict(signal) for signal in signal_service.list(limit=limit)]}


@router.post("/strategy/compile-backtest")
def compile_strategy_backtest(payload: CompileBacktestPayload):
    compiled = backtest_compiler.compile(
        BacktestCompileRequest(
            dsl=payload.dsl.to_dsl(),
            codes=payload.codes,
            start_date=payload.start_date,
            end_date=payload.end_date,
            initial_cash=payload.initial_cash,
            commission_rate=payload.commission_rate,
            stamp_tax_rate=payload.stamp_tax_rate,
            slippage=payload.slippage,
            benchmark=payload.benchmark,
            period=payload.period,
        )
    )
    return {"success": True, "backtest_request": compiled}


@router.get("/health")
def agentic_health():
    return {
        "success": True,
        "components": {
            "registry": "online",
            "signals": "online",
            "research": "online",
            "strategy_lab": "online",
            "backtest_compiler": "online",
        },
    }
