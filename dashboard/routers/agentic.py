import asyncio
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from agentic.backtest_compiler import BacktestCompileRequest, BacktestCompiler
from agentic.candidate_backtester import StrategyCandidateBacktester
from agentic.backtest_runner import AgenticBacktestRunner
from agentic.paper_strategy_candidates import PaperStrategyCandidateService
from agentic.registry import AgentRegistry
from agentic.sample_selector import BacktestSampleSelector
from agentic.signal_validation import evaluate_signal_validation
from agentic.strategy_candidates import StrategyCandidateGenerator
from agentic.repository import AgenticRepository
from agentic.signals import SignalService
from agentic.strategy_dsl import StrategyDSL
from config.settings import DB_DIR
from data.signals.validation import validate_signal_provider

router = APIRouter()
registry = AgentRegistry.default()
agentic_repository = AgenticRepository(DB_DIR / "agentic.db")
signal_service = SignalService(agentic_repository)
backtest_compiler = BacktestCompiler()
backtest_runner = AgenticBacktestRunner(compiler=backtest_compiler)
sample_selector = BacktestSampleSelector()
strategy_candidate_generator = StrategyCandidateGenerator()
candidate_backtester = StrategyCandidateBacktester(candidate_generator=strategy_candidate_generator, sample_selector=sample_selector, runner=backtest_runner)
paper_strategy_candidate_service = PaperStrategyCandidateService(agentic_repository)


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


class PaperStrategyCandidatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result_id: str = ""


class ConfirmPaperExecutionPayload(BaseModel):
    portfolio: dict[str, Any] = {}
    risk_context: dict[str, Any] = {}


class CreateOrderDraftsPayload(BaseModel):
    volume_per_code: int = 100


_LEGACY_STRATEGY_DISPLAY_NAMES = {
    "qlib_ranked_core": "AI信号基线轮动",
    "signal_ranked_core": "AI信号基线轮动",
    "Qlib 核心轮动": "AI信号基线轮动",
}

_LEGACY_CANDIDATE_ID_ALIASES = {
    "qlib_ranked_core": "signal_ranked_core",
}


def _public_strategy_name(candidate_id: str | None, name: str | None) -> str:
    candidate_key = str(candidate_id or "").strip()
    name_key = str(name or "").strip()
    return _LEGACY_STRATEGY_DISPLAY_NAMES.get(candidate_key) or _LEGACY_STRATEGY_DISPLAY_NAMES.get(name_key) or name_key or candidate_key


def _canonical_candidate_id(candidate_id: str | None) -> str:
    value = str(candidate_id or "").strip()
    return _LEGACY_CANDIDATE_ID_ALIASES.get(value, value)


def _legacy_candidate_id(candidate_id: str | None) -> str:
    value = str(candidate_id or "").strip()
    canonical = _canonical_candidate_id(value)
    return value if canonical != value else ""


def _public_strategy_id(strategy_name: str | None) -> str:
    raw = str(strategy_name or "").strip()
    prefix = "agentic:"
    if not raw.startswith(prefix):
        return _canonical_candidate_id(raw)
    return f"{prefix}{_canonical_candidate_id(raw.removeprefix(prefix))}"


def _public_candidate_payload(candidate) -> dict[str, Any]:
    payload = asdict(candidate)
    candidate_id = payload.get("candidate_id")
    payload["canonical_candidate_id"] = _canonical_candidate_id(candidate_id)
    payload["legacy_candidate_id"] = _legacy_candidate_id(candidate_id)
    payload["name"] = _public_strategy_name(candidate_id, payload.get("name"))
    return payload


def _public_execution_payload(execution) -> dict[str, Any]:
    payload = asdict(execution)
    candidate_id = payload.get("candidate_id")
    payload["canonical_candidate_id"] = _canonical_candidate_id(candidate_id)
    payload["legacy_candidate_id"] = _legacy_candidate_id(candidate_id)
    payload["name"] = _public_strategy_name(candidate_id, payload.get("name"))
    return payload


def _public_order_draft_payload(draft) -> dict[str, Any]:
    payload = asdict(draft)
    strategy_name = str(payload.get("strategy_name") or "")
    candidate_id = strategy_name.removeprefix("agentic:")
    display_id = _public_strategy_id(strategy_name)
    payload["strategy_display_id"] = display_id
    payload["legacy_strategy_name"] = strategy_name if display_id != strategy_name else ""
    payload["strategy_display_name"] = _public_strategy_name(candidate_id, strategy_name)
    return payload


def _public_paper_order_payload(order) -> dict[str, Any]:
    payload = order.to_dict()
    raw_strategy = str(payload.get("strategy_name") or "")
    display_id = _public_strategy_id(raw_strategy)
    if display_id != raw_strategy:
        payload["legacy_strategy_name"] = raw_strategy
        payload["strategy_name"] = display_id
    else:
        payload["legacy_strategy_name"] = ""
    candidate_id = raw_strategy.removeprefix("agentic:")
    payload["strategy_display_name"] = _public_strategy_name(candidate_id, raw_strategy)
    return payload


async def _context_with_server_signal_validation(context: dict[str, Any] | None) -> dict[str, Any]:
    enriched = dict(context or {})
    try:
        validation = await asyncio.to_thread(validate_signal_provider, top_n=50)
        enriched["signal_validation"] = validation.to_dict()
    except Exception as exc:
        enriched["signal_validation"] = {
            "confidence": "unverified",
            "sample_days": 0,
            "status": "unavailable",
            "message": f"signal validation unavailable: {exc}",
        }
    return enriched


def _result_with_server_signal_validation(result: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(result or {})
    try:
        validation = validate_signal_provider(top_n=50).to_dict()
    except Exception as exc:
        validation = {
            "confidence": "unverified",
            "sample_days": 0,
            "status": "unavailable",
            "message": f"signal validation unavailable: {exc}",
        }
    gate = evaluate_signal_validation(validation)
    gate_checks = [
        dict(item)
        for item in (enriched.get("gate_checks") or [])
        if isinstance(item, dict) and item.get("id") != "signal_validation"
    ]
    gate_checks.append(gate.to_gate_check())
    enriched["gate_checks"] = gate_checks
    if not gate.passed:
        promotion = dict(enriched.get("promotion") or {})
        promotion["promoted"] = False
        promotion["reason"] = gate.reason
        enriched["promotion"] = promotion
    return enriched


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



@router.get("/strategy/paper-candidates")
def list_paper_strategy_candidates(limit: int = 100):
    return {
        "success": True,
        "candidates": [_public_candidate_payload(candidate) for candidate in paper_strategy_candidate_service.list(limit=limit)],
    }


@router.post("/strategy/paper-candidates")
def enqueue_paper_strategy_candidate(payload: PaperStrategyCandidatePayload):
    try:
        result_id = str(payload.result_id or "").strip()
        if not result_id:
            raise ValueError("server result_id is required")
        result, sample = agentic_repository.get_candidate_backtest_result(result_id)
        if dict((result or {}).get("promotion") or {}).get("promoted") is not True:
            raise ValueError("only promoted candidates can be queued for paper trading")
        result = _result_with_server_signal_validation(result)
        if dict(result.get("promotion") or {}).get("promoted") is not True:
            failed_gate = next(
                (
                    item
                    for item in result.get("gate_checks", [])
                    if isinstance(item, dict) and item.get("id") == "signal_validation" and item.get("passed") is False
                ),
                {},
            )
            raise ValueError(str(failed_gate.get("detail") or "AI信号验证未通过"))
        candidate = paper_strategy_candidate_service.enqueue(result, sample)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "candidate": _public_candidate_payload(candidate)}


@router.post("/strategy/paper-candidates/{candidate_id}/confirm")
def confirm_paper_strategy_candidate(candidate_id: str):
    try:
        candidate = paper_strategy_candidate_service.confirm(candidate_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "candidate": _public_candidate_payload(candidate)}


@router.get("/strategy/paper-executions")
def list_paper_strategy_executions(limit: int = 100):
    return {
        "success": True,
        "executions": [_public_execution_payload(item) for item in paper_strategy_candidate_service.list_executions(limit=limit)],
    }


@router.post("/strategy/paper-candidates/{candidate_id}/run")
def run_paper_strategy_candidate(candidate_id: str):
    try:
        execution = paper_strategy_candidate_service.run_active(candidate_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "execution": _public_execution_payload(execution)}


@router.post("/strategy/paper-executions/{execution_id}/confirm")
def confirm_paper_strategy_execution(execution_id: str, payload: ConfirmPaperExecutionPayload):
    try:
        execution = paper_strategy_candidate_service.confirm_execution(
            execution_id,
            portfolio=payload.portfolio,
            risk_context=payload.risk_context,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "execution": _public_execution_payload(execution)}


@router.get("/strategy/order-drafts")
def list_agentic_order_drafts(limit: int = 100):
    return {
        "success": True,
        "drafts": [_public_order_draft_payload(item) for item in agentic_repository.list_agentic_order_drafts(limit=limit)],
    }


@router.post("/strategy/paper-executions/{execution_id}/order-drafts")
def create_agentic_order_drafts(execution_id: str, payload: CreateOrderDraftsPayload):
    try:
        drafts = paper_strategy_candidate_service.create_order_drafts(
            execution_id,
            volume_per_code=payload.volume_per_code,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "drafts": [_public_order_draft_payload(item) for item in drafts]}


@router.post("/strategy/paper-executions/{execution_id}/paper-orders")
def submit_agentic_paper_orders(execution_id: str, payload: CreateOrderDraftsPayload):
    try:
        orders = paper_strategy_candidate_service.submit_confirmed_execution_orders(
            execution_id,
            volume_per_code=payload.volume_per_code,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "orders": [_public_paper_order_payload(item) for item in orders]}

@router.post("/strategy/run-candidates")
async def run_strategy_candidates(payload: RunCandidateBacktestsPayload):
    context = await _context_with_server_signal_validation(payload.context)
    batch = await candidate_backtester.run(
        context=context,
        limit=payload.limit,
        min_days=payload.min_days,
        max_codes=payload.max_codes,
        initial_cash=payload.initial_cash,
    )
    response = batch.to_dict()
    sample = response.get("sample") or {}
    for result in response.get("results") or []:
        if isinstance(result, dict):
            result["result_id"] = agentic_repository.save_candidate_backtest_result(result, sample)
    return {"success": True, **response}

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
