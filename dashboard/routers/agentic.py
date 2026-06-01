from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agentic.backtest_compiler import BacktestCompileRequest, BacktestCompiler
from agentic.candidate_backtester import StrategyCandidateBacktester
from agentic.backtest_runner import AgenticBacktestRunner
from agentic.registry import AgentRegistry
from agentic.sample_selector import BacktestSampleSelector
from agentic.strategy_candidates import StrategyCandidateGenerator
from agentic.repository import AgenticRepository
from agentic.signals import SignalService
from agentic.strategy_dsl import StrategyDSL
from config.settings import DB_DIR

router = APIRouter()
registry = AgentRegistry.default()
signal_service = SignalService(AgenticRepository(DB_DIR / "agentic.db"))
backtest_compiler = BacktestCompiler()
backtest_runner = AgenticBacktestRunner(compiler=backtest_compiler)
sample_selector = BacktestSampleSelector()
strategy_candidate_generator = StrategyCandidateGenerator()
candidate_backtester = StrategyCandidateBacktester(candidate_generator=strategy_candidate_generator, sample_selector=sample_selector, runner=backtest_runner)


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


class RunCandidateBacktestsPayload(BaseModel):
    context: dict[str, Any] = {}
    limit: int = 4
    min_days: int = 60
    max_codes: int = 5
    initial_cash: float = 1_000_000


@router.get("/agents")
def list_agents():
    return {"success": True, "agents": [asdict(agent) for agent in registry.list()]}


@router.get("/signals")
def list_signals(limit: int = 100):
    return {"success": True, "signals": [asdict(signal) for signal in signal_service.list(limit=limit)]}



@router.get("/backtest-sample")
def get_backtest_sample(min_days: int = 60, max_codes: int = 5):
    try:
        sample = sample_selector.select(min_days=min_days, max_codes=max_codes)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, "sample": sample.to_dict()}


@router.get("/strategy/candidates")
def list_strategy_candidates(
    limit: int = 4,
    universe: str | None = None,
    risk_mode: str | None = None,
    max_holdings: int | None = None,
):
    context = {
        "universe": universe,
        "risk_mode": risk_mode,
        "max_holdings": max_holdings,
    }
    candidates = strategy_candidate_generator.generate(context=context, limit=limit)
    return {"success": True, "candidates": [candidate.to_dict() for candidate in candidates]}

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


@router.post("/strategy/run-candidates")
async def run_strategy_candidates(payload: RunCandidateBacktestsPayload):
    batch = await candidate_backtester.run(
        context=payload.context,
        limit=payload.limit,
        min_days=payload.min_days,
        max_codes=payload.max_codes,
        initial_cash=payload.initial_cash,
    )
    return {"success": True, **batch.to_dict()}

@router.post("/strategy/run-backtest")
async def run_strategy_backtest(payload: CompileBacktestPayload):
    result = await backtest_runner.run_and_evaluate(
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
    return {
        "success": True,
        "backtest_request": result.compiled_request,
        "backtest": result.backtest_response,
        "metrics": result.metrics,
        "promotion": {
            "promoted": result.promotion.promoted,
            "reason": result.promotion.reason,
            "metrics": result.promotion.metrics,
        },
    }

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
