import asyncio
import inspect
import os
from dataclasses import asdict
from typing import Any
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from agentic.backtest_compiler import BacktestCompileRequest, BacktestCompiler
from agentic.candidate_backtester import StrategyCandidateBacktester
from agentic.backtest_runner import AgenticBacktestRunner
from agentic.paper_strategy_candidates import PaperOrderRecoveryRequired, PaperStrategyCandidateService
from agentic.operations import OperationConflict
from agentic.promotion import PromotionContext
from agentic.registry import AgentRegistry
from agentic.sample_selector import BacktestSampleSelector
from agentic.signal_validation import evaluate_signal_validation
from agentic.strategy_candidates import StrategyCandidateGenerator
from agentic.repository import (
    DEFAULT_WORKSPACE_ID,
    AgenticRepository,
    normalize_workspace_id,
    paper_db_path,
)
from agentic.research_pipeline import ResearchPipeline
from agentic.signals import SignalService
from agentic.strategy_dsl import StrategyDSL
from config.settings import DB_DIR
from data.evidence.store import SQLiteEvidenceStore
from data.signals.validation import validate_signal_provider
from data.storage import DataStorage
from agentic.outcome_evaluator import DecisionSignalOutcomeEvaluator
from agentic.daily_run import DailyResearchRunService
from engine.events.outbox import SQLiteOutbox
from engine.order_manager import OrderManager
from alpha.screening_runtime import ScreeningRuntime
from dashboard.session import optional_account

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
research_pipeline = ResearchPipeline(agentic_repository, signal_service=signal_service)
screening_runtime = ScreeningRuntime()
_workspace_service_cache: dict[tuple[str, str], dict[str, Any]] = {}


def _workspace_id(account: dict | None) -> str:
    """Resolve the request workspace, with a test-only anonymous fallback."""

    raw_workspace_id = str((account or {}).get("workspace", {}).get("id") or "").strip()
    if raw_workspace_id:
        try:
            return normalize_workspace_id(raw_workspace_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if os.getenv("APP_ENV", "development").lower() == "test":
        return DEFAULT_WORKSPACE_ID
    raise HTTPException(status_code=401, detail="请先登录")


def _agentic_services(account: dict | None) -> dict[str, Any]:
    """Return all stateful Agentic adapters bound to one workspace."""

    workspace_id = _workspace_id(account)
    if workspace_id == DEFAULT_WORKSPACE_ID:
        # Keep the existing module-level seams available to APP_ENV=test API
        # fixtures and to legacy callers that replace these adapters.
        return {
            "workspace_id": workspace_id,
            "repository": agentic_repository,
            "signal_service": signal_service,
            "paper_service": paper_strategy_candidate_service,
            "research_pipeline": research_pipeline,
        }

    cache_key = (workspace_id, str(DB_DIR))
    cached = _workspace_service_cache.get(cache_key)
    if cached is not None:
        return cached

    repository = AgenticRepository.for_workspace(workspace_id, base_dir=DB_DIR)
    workspace_signal_service = SignalService(repository)
    workspace_paper_service = PaperStrategyCandidateService(
        repository,
        order_manager=OrderManager(
            str(paper_db_path(workspace_id, base_dir=DB_DIR.parent))
        ),
    )
    workspace_research_pipeline = ResearchPipeline(
        repository,
        signal_service=workspace_signal_service,
    )
    services = {
        "workspace_id": workspace_id,
        "repository": repository,
        "signal_service": workspace_signal_service,
        "paper_service": workspace_paper_service,
        "research_pipeline": workspace_research_pipeline,
    }
    _workspace_service_cache[cache_key] = services
    return services


def _signal_repository(services: dict[str, Any]):
    return getattr(services["signal_service"], "repo", None) or services["repository"]


def _paper_repository(services: dict[str, Any]):
    return getattr(services["paper_service"], "repository", None) or services["repository"]


def _workspace_feature_enabled(key: str, account: dict | None = None, default: bool = True) -> bool:
    """Resolve a workspace feature flag without weakening API-key/test fallbacks."""
    if account is None:
        return default
    settings = (account.get("workspace") or {}).get("settings") or {}
    return bool(settings.get(key, default))


def _daily_run_service(account: dict | None = None) -> DailyResearchRunService:
    services = _agentic_services(account)
    workspace_id = services["workspace_id"]
    evidence_store = SQLiteEvidenceStore(DB_DIR / "evidence.db")
    outbox = SQLiteOutbox(DB_DIR / "events.db")
    service = DailyResearchRunService(
        evidence_store,
        services["repository"],
        outbox,
        signal_service=services["signal_service"],
        research_pipeline=services["research_pipeline"],
        workspace_id=workspace_id,
    )
    service.close_after_run = True
    return service


def _workspace_watchlist(account: dict | None) -> list[str]:
    """Return the authenticated workspace's watchlist for account-scoped runs."""
    workspace_id = str((account or {}).get("workspace", {}).get("id") or "").strip()
    if not workspace_id:
        return []
    try:
        return DataStorage().get_watchlist(workspace_id)
    except Exception:
        return []


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
    operation_id: str = Field(default="", max_length=128)


class PaperStrategyOperationPayload(BaseModel):
    operation_id: str = Field(default="", max_length=128)


class ConfirmPaperExecutionPayload(BaseModel):
    operation_id: str = Field(default="", max_length=128)
    confirmed_by: str = Field(default="dashboard-user", max_length=128)
    portfolio: dict[str, Any] = {}
    risk_context: dict[str, Any] = {}


class ConfirmPaperCandidatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str = Field(default="", max_length=128)
    confirmed_by: str = Field(default="dashboard-user", max_length=128)


class CreateOrderDraftsPayload(BaseModel):
    volume_per_code: int = 100
    operation_id: str = Field(default="", max_length=128)


class PromotionContextPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_count: int = Field(default=0, ge=0)
    provenance_complete: bool = False
    backtest_passed: bool = False
    risk_approved: bool = False
    paper_observations: int = Field(default=0, ge=0)
    paper_return: float | None = None
    max_drawdown: float | None = None
    manual_approval: bool = False
    signal_validation_passed: bool = False
    min_trades: int = Field(default=0, ge=0)
    sharpe: float | None = None

    def to_context(self) -> PromotionContext:
        return PromotionContext(**self.model_dump())


class ApprovePaperPendingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str = Field(..., min_length=1, max_length=128)
    context: PromotionContextPayload


class ConfirmPaperPendingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str = Field(..., min_length=1, max_length=128)
    approval_operation_id: str = Field(..., min_length=1, max_length=128)
    confirmed_by: str = Field(..., min_length=1, max_length=128)


class ResearchRunPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    context: dict[str, Any] = {}
    run_key: str = Field(default="", max_length=256)
    evidence_snapshot_id: str = ""
    publish_signal: bool = True


class ScreeningRunPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_name: str = "daily_stock_analysis_default"
    filters: list[dict[str, Any]] = []
    codes: list[str] = []
    sort_by: str = "change_pct"
    sort_desc: bool = True
    page_size: int = Field(default=50, ge=1, le=500)
    namespace: str = "screening"
    strategy: dict[str, Any] | str | None = None
    strategy_yaml: dict[str, Any] | str | None = None
    llm_rerank: bool = False


class DailyResearchRunPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    watchlist: list[str] = []
    run_key: str = Field(default="", max_length=256)
    operation_id: str = Field(default="", max_length=128)
    captured_at: str = ""
    max_market_items: int = Field(default=30, ge=1, le=200)
    max_stock_items: int = Field(default=20, ge=1, le=100)
    contexts: dict[str, Any] = {}


def _public_research_job(job) -> dict[str, Any]:
    payload = asdict(job)
    payload["roles"] = list(job.roles)
    payload["context"] = dict(job.context)
    payload["report"] = dict(job.report)
    payload["decision_signal"] = dict(job.decision_signal)
    payload["final_report"] = dict(job.final_report)
    return payload


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


def _public_operation_payload(operation) -> dict[str, Any]:
    return {
        "operation_id": operation.operation_id,
        "command": operation.command,
        "aggregate_type": operation.aggregate_type,
        "aggregate_id": operation.aggregate_id,
        "request": dict(operation.request),
        "request_hash": operation.request_hash,
        "status": operation.status,
        "result": dict(operation.result),
        "created_at": operation.created_at,
        "completed_at": operation.completed_at,
    }


def _operation_response(operation, *, replayed: bool = False, recoverable: bool = False, message: str = "") -> dict[str, Any]:
    if operation is None:
        return {}
    recovered = bool(operation.result.get("recovered"))
    is_replay = bool(replayed or recovered)
    operation_state = "recoverable" if recoverable else "replayed" if is_replay else operation.status
    status_message = (
        "可恢复"
        if recoverable
        else "已恢复"
        if is_replay
        else message or "已完成"
    )
    return {
        "operation": _public_operation_payload(operation),
        "operation_id": operation.operation_id,
        "operation_status": operation.status,
        "operation_state": operation_state,
        "replayed": is_replay,
        "recoverable": bool(recoverable),
        "message": status_message,
    }


def _operation_conflict(exc: OperationConflict) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "operation_conflict",
            "message": "操作冲突：同一个 operation id 对应的请求事实已改变",
            "conflict": True,
            "reason": str(exc),
        },
    )


def _existing_operation(store, operation_id: str | None):
    if store is None or not operation_id:
        return None
    try:
        return store.get_operation(operation_id)
    except KeyError:
        return None


def _legacy_operation_id(kind: str, aggregate_id: str, suffix: str = "") -> str:
    value = "-".join(part for part in (kind, aggregate_id, suffix) if part)
    return "legacy-%s" % value


def _operation_store(account: dict | None = None, services: dict[str, Any] | None = None):
    services = services or _agentic_services(account)
    signal_store = getattr(services["signal_service"], "repo", None)
    if callable(getattr(signal_store, "get_operation", None)):
        return signal_store
    paper_store = getattr(services["paper_service"], "repository", None)
    if callable(getattr(paper_store, "get_operation", None)):
        return paper_store
    return services["repository"]


def _call_service(method, *args, **kwargs):
    """Call a write service while keeping pre-operation adapters callable."""

    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        signature = None
    if signature is not None:
        parameters = signature.parameters.values()
        accepts_kwargs = any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters)
        if not accepts_kwargs:
            accepted = set(signature.parameters)
            kwargs = {key: value for key, value in kwargs.items() if key in accepted}
    return method(*args, **kwargs)


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
def list_signals(
    limit: int = 100,
    account: dict | None = Depends(optional_account),
):
    services = _agentic_services(account)
    return {
        "success": True,
        "signals": [asdict(signal) for signal in services["signal_service"].list(limit=limit)],
    }


@router.get("/research")
def list_research(
    limit: int = 50,
    code: str | None = None,
    status: str | None = None,
    account: dict | None = Depends(optional_account),
):
    repository = _agentic_services(account)["repository"]
    try:
        jobs = repository.list_research_jobs(limit=limit, code=code, status=status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "research": [_public_research_job(job) for job in jobs]}


@router.get("/research/{job_id}")
def get_research(job_id: str, account: dict | None = Depends(optional_account)):
    repository = _agentic_services(account)["repository"]
    try:
        job = repository.get_research_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    evidence = None
    snapshot_id = str((job.context or {}).get("evidence_snapshot_id") or "").strip()
    if snapshot_id:
        store = None
        try:
            store = SQLiteEvidenceStore(DB_DIR / "evidence.db", readonly=True)
            snapshot = store.get_snapshot(snapshot_id)
            if snapshot is not None:
                evidence = {
                    "snapshot": {
                        "id": snapshot.id,
                        "captured_at": snapshot.captured_at,
                        "query": snapshot.query,
                        "sealed": snapshot.sealed,
                        "citable": snapshot.citable,
                        "metadata": dict(snapshot.metadata),
                    },
                    "items": [
                        {
                            "id": item.id,
                            "title": item.title,
                            "content": item.content,
                            "observed_at": item.observed_at,
                            "url": item.url,
                            "symbol": item.symbol,
                            "source_id": item.source_id,
                        }
                        for item in store.list_items(snapshot_id)
                    ],
                }
        finally:
            if store is not None:
                store.close()
    return {"success": True, "research": _public_research_job(job), "evidence": evidence}


@router.get("/briefs/daily")
def list_daily_briefs(
    limit: int = 30,
    trade_date: str | None = None,
    account: dict | None = Depends(optional_account),
):
    repository = _agentic_services(account)["repository"]
    return {"success": True, "briefs": repository.list_daily_briefs(limit=limit, trade_date=trade_date)}


@router.get("/briefs/daily/{trade_date}")
def get_daily_brief(trade_date: str, account: dict | None = Depends(optional_account)):
    repository = _agentic_services(account)["repository"]
    briefs = repository.list_daily_briefs(limit=1, trade_date=trade_date)
    if not briefs:
        raise HTTPException(status_code=404, detail="daily brief not found: %s" % trade_date)
    return {"success": True, "brief": briefs[0]}


@router.get("/screening/runs")
def list_screening_runs(
    limit: int = 30,
    account: dict | None = Depends(optional_account),
):
    repository = _agentic_services(account)["repository"]
    return {"success": True, "runs": repository.list_screening_runs(limit=limit)}


@router.post("/screening/run")
def run_screening(
    payload: ScreeningRunPayload,
    account: dict | None = Depends(optional_account),
):
    repository = _agentic_services(account)["repository"]
    if not _workspace_feature_enabled("screening_enabled", account):
        raise HTTPException(status_code=409, detail="当前工作区已关闭候选筛选入口")
    try:
        strategy = payload.strategy
        if payload.llm_rerank:
            if isinstance(strategy, dict):
                strategy = {**strategy, "llm_rerank": True}
            elif strategy is None:
                strategy = {"llm_rerank": True}
        run = screening_runtime.run(
            strategy_name=payload.strategy_name,
            filters=payload.filters,
            codes=payload.codes,
            sort_by=payload.sort_by,
            sort_desc=payload.sort_desc,
            page_size=payload.page_size,
            namespace=payload.namespace,
            strategy=strategy,
            strategy_yaml=payload.strategy_yaml,
            llm_reranker=None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload_dict = run.to_dict()
    repository.save_screening_run(payload_dict)
    return {"success": True, "run": payload_dict}


@router.get("/screening/runs/{run_id}")
def get_screening_run(run_id: str, account: dict | None = Depends(optional_account)):
    repository = _agentic_services(account)["repository"]
    run = repository.get_screening_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="screening run not found: %s" % run_id)
    return {"success": True, "run": run}


@router.get("/screening/candidates/{code}/history")
def get_screening_candidate_history(
    code: str,
    limit: int = 30,
    namespace: str | None = None,
    account: dict | None = Depends(optional_account),
):
    repository = _agentic_services(account)["repository"]
    try:
        history = repository.list_screening_candidate_history(
            code, limit=limit, strategy_namespace=namespace
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "code": code, "history": history}


@router.get("/screening/runs/{run_id}/candidates/{code}/actions")
def get_screening_candidate_actions(
    run_id: str,
    code: str,
    account: dict | None = Depends(optional_account),
):
    repository = _agentic_services(account)["repository"]
    try:
        actions = repository.list_screening_candidate_actions(run_id, code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not actions and repository.get_screening_run(run_id) is None:
        raise HTTPException(status_code=404, detail="screening run not found: %s" % run_id)
    return {"success": True, "run_id": run_id, "code": code, "actions": actions}


@router.post("/briefs/daily/run")
async def run_daily_brief(
    payload: DailyResearchRunPayload,
    account: dict | None = Depends(optional_account),
):
    if not _workspace_feature_enabled("daily_research_enabled", account):
        raise HTTPException(status_code=409, detail="当前工作区已关闭每日投研入口")
    watchlist = payload.watchlist
    if not watchlist and account is not None:
        watchlist = _workspace_watchlist(account)
    if not watchlist and account is None:
        try:
            watchlist = DataStorage().get_watchlist()
        except Exception:
            watchlist = []
    run_key = payload.run_key or "daily:%s:%s" % (
        (payload.captured_at or datetime.now(timezone.utc).isoformat())[:10],
        ",".join(sorted(set(watchlist))),
    )
    service = None
    try:
        service = _call_service(_daily_run_service, account=account)
        result = await service.run(
            watchlist=watchlist,
            run_key=run_key,
            operation_id=payload.operation_id or None,
            captured_at=payload.captured_at or None,
            max_market_items=payload.max_market_items,
            max_stock_items=payload.max_stock_items,
            contexts=payload.contexts,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OperationConflict as exc:
        raise _operation_conflict(exc) from exc
    finally:
        if service is not None:
            if getattr(service, "close_after_run", False):
                close_store = getattr(service.evidence_store, "close", None)
                if callable(close_store):
                    close_store()
                close_outbox = getattr(service.outbox, "close", None)
                if callable(close_outbox):
                    close_outbox()
    operation = result.operation
    return {
        "success": True,
        "brief": {
            "snapshot_id": result.brief.snapshot_id,
            "captured_at": result.brief.captured_at,
            "watchlist": list(result.brief.watchlist),
            "evidence_count": result.brief.evidence_count,
            "event_id": result.brief.event_id,
            "research_jobs": list(result.brief.research_jobs),
            "report_count": result.brief.report_count,
            "markdown": result.brief.markdown,
            "run_key": result.brief.run_key,
        },
        "collection": dict(result.collection),
        "operation": None if operation is None else _public_operation_payload(operation),
        "replayed": bool(result.collection.get("status") == "replayed" or (operation and operation.result.get("replayed"))),
    }


@router.post("/research/run")
def run_research(
    payload: ResearchRunPayload,
    account: dict | None = Depends(optional_account),
):
    research_pipeline = _agentic_services(account)["research_pipeline"]
    try:
        job = research_pipeline.run(
            payload.code,
            payload.context,
            run_key=payload.run_key or None,
            evidence_snapshot_id=payload.evidence_snapshot_id or None,
            publish_signal=payload.publish_signal,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "research": _public_research_job(job), "replayed": bool(payload.run_key and job.run_key == payload.run_key)}


@router.get("/signals/{signal_id}/provenance")
def get_signal_provenance(signal_id: str, account: dict | None = Depends(optional_account)):
    services = _agentic_services(account)
    repository = _signal_repository(services)
    signal_service = services["signal_service"]
    try:
        signal = repository.get_signal(signal_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    provenance = signal_service.ledger.provenance(signal_id)
    return {
        "success": True,
        "signal": asdict(signal),
        "provenance": [asdict(item) for item in provenance],
    }


@router.get("/signals/{signal_id}/outcome")
def get_signal_outcome(signal_id: str, account: dict | None = Depends(optional_account)):
    services = _agentic_services(account)
    repository = _signal_repository(services)
    signal_service = services["signal_service"]
    try:
        signal = repository.get_signal(signal_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    outcome = signal_service.ledger.latest_outcome(signal_id)
    return {"success": True, "signal_id": signal.id, "outcome": None if outcome is None else asdict(outcome)}


@router.get("/outcomes/aggregate")
def get_outcome_aggregate(
    limit: int = 100,
    min_samples: int = 5,
    source: str | None = None,
    profile: str | None = None,
    horizon_days: int | None = None,
    market_phase: str | None = None,
    account: dict | None = Depends(optional_account),
):
    """Read-only T+N product metrics; this is not a strategy performance view."""

    repository = _agentic_services(account)["repository"]
    try:
        aggregates = repository.list_outcome_aggregates(
            limit=limit,
            min_samples=min_samples,
            source=source,
            profile=profile,
            horizon_days=horizon_days,
            market_phase=market_phase,
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "success": True,
        "metric_scope": "decision_signal_outcome",
        "ranked_by": "direction.hit_rate",
        "min_samples": max(1, int(min_samples)),
        "aggregates": aggregates,
    }


@router.post("/signals/{signal_id}/outcome")
def evaluate_signal_outcome(
    signal_id: str,
    horizon_days: int = 5,
    end: str = "",
    account: dict | None = Depends(optional_account),
):
    services = _agentic_services(account)
    repository = _signal_repository(services)
    signal_service = services["signal_service"]
    try:
        signal = repository.get_signal(signal_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    storage = DataStorage()
    try:
        evaluator = DecisionSignalOutcomeEvaluator(
            signal_service.ledger,
            lambda code, start, end: storage.get_stock_daily(code).to_dict("records"),
        )
        observed_at = end or datetime.now(timezone.utc).isoformat()
        result = evaluator.evaluate(signal, horizon_days=horizon_days, end=observed_at)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "evaluation": asdict(result)}


@router.post("/signals/{signal_id}/paper-gate")
def approve_signal_paper_gate(
    signal_id: str,
    payload: ApprovePaperPendingPayload,
    account: dict | None = Depends(optional_account),
):
    signal_service = _agentic_services(account)["signal_service"]
    try:
        decision = signal_service.approve_paper_pending(
            signal_id,
            payload.context.to_context(),
            operation_id=payload.operation_id,
        )
        operation = signal_service.repo.get_operation(payload.operation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OperationConflict as exc:
        raise _operation_conflict(exc) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "success": True,
        "decision": decision.to_dict(),
        "operation": _public_operation_payload(operation),
    }


@router.post("/signals/{signal_id}/paper-pending")
def confirm_signal_paper_pending(
    signal_id: str,
    payload: ConfirmPaperPendingPayload,
    account: dict | None = Depends(optional_account),
):
    signal_service = _agentic_services(account)["signal_service"]
    try:
        signal = signal_service.confirm_paper_pending(
            signal_id,
            confirmed_by=payload.confirmed_by,
            approval_operation_id=payload.approval_operation_id,
            operation_id=payload.operation_id,
        )
        operation = signal_service.repo.get_operation(payload.operation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OperationConflict as exc:
        raise _operation_conflict(exc) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "success": True,
        "signal": asdict(signal),
        "operation": _public_operation_payload(operation),
    }



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
def list_paper_strategy_candidates(
    limit: int = 100,
    account: dict | None = Depends(optional_account),
):
    paper_service = _agentic_services(account)["paper_service"]
    return {
        "success": True,
        "candidates": [_public_candidate_payload(candidate) for candidate in paper_service.list(limit=limit)],
    }


@router.post("/strategy/paper-candidates")
def enqueue_paper_strategy_candidate(
    payload: PaperStrategyCandidatePayload,
    account: dict | None = Depends(optional_account),
):
    services = _agentic_services(account)
    repository = _paper_repository(services)
    paper_service = services["paper_service"]
    try:
        result_id = str(payload.result_id or "").strip()
        if not result_id:
            raise ValueError("server result_id is required")
        result, sample = repository.get_candidate_backtest_result(result_id)
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
        operation_id = payload.operation_id or _legacy_operation_id(
            "paper-candidate-enqueue", str(result.get("candidate", {}).get("id", ""))
        )
        operation_store = getattr(paper_service, "repository", None) or repository
        previous_operation = _existing_operation(operation_store, operation_id)
        candidate = _call_service(
            paper_service.enqueue,
            result,
            sample,
            operation_id=operation_id,
            operation_request={
                "result_id": result_id,
                "candidate_id": str(result.get("candidate", {}).get("id", "")),
                "sample": dict(sample or {}),
            },
        )
        operation = _existing_operation(operation_store, operation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OperationConflict as exc:
        raise _operation_conflict(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "success": True,
        "candidate": _public_candidate_payload(candidate),
        **_operation_response(operation, replayed=previous_operation is not None, message="候选已加入模拟盘候选"),
    }


@router.post("/strategy/paper-candidates/{candidate_id}/confirm")
def confirm_paper_strategy_candidate(
    candidate_id: str,
    payload: ConfirmPaperCandidatePayload | None = None,
    account: dict | None = Depends(optional_account),
):
    services = _agentic_services(account)
    repository = _paper_repository(services)
    paper_service = services["paper_service"]
    try:
        payload = payload or ConfirmPaperCandidatePayload()
        operation_store = getattr(paper_service, "repository", None) or repository
        operation_id = payload.operation_id or _legacy_operation_id("paper-candidate-confirm", candidate_id)
        previous_operation = _existing_operation(operation_store, operation_id)
        candidate = _call_service(
            paper_service.confirm,
            candidate_id,
            operation_id=operation_id,
            confirmed_by=payload.confirmed_by,
        )
        operation = _existing_operation(operation_store, operation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OperationConflict as exc:
        raise _operation_conflict(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "success": True,
        "candidate": _public_candidate_payload(candidate),
        **_operation_response(operation, replayed=previous_operation is not None, message="候选确认已完成"),
    }


@router.get("/strategy/paper-executions")
def list_paper_strategy_executions(
    limit: int = 100,
    account: dict | None = Depends(optional_account),
):
    paper_service = _agentic_services(account)["paper_service"]
    return {
        "success": True,
        "executions": [_public_execution_payload(item) for item in paper_service.list_executions(limit=limit)],
    }


@router.get("/operations")
def list_agentic_operations(
    limit: int = 100,
    aggregate_type: str | None = None,
    aggregate_id: str | None = None,
    account: dict | None = Depends(optional_account),
):
    """Read-only operation audit trail for Agentic actions."""

    store = _operation_store(account)
    lister = getattr(store, "list_operations", None)
    operations = lister(
        limit=limit,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
    ) if callable(lister) else []
    return {
        "success": True,
        "operations": [_public_operation_payload(operation) for operation in operations],
    }


@router.get("/operations/{operation_id}")
def get_agentic_operation(
    operation_id: str,
    account: dict | None = Depends(optional_account),
):
    store = _operation_store(account)
    getter = getattr(store, "get_operation", None)
    if not callable(getter):
        raise HTTPException(status_code=404, detail="operation not found: %s" % operation_id)
    try:
        operation = getter(operation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, "operation": _public_operation_payload(operation)}


@router.post("/strategy/paper-candidates/{candidate_id}/run")
def run_paper_strategy_candidate(
    candidate_id: str,
    payload: PaperStrategyOperationPayload | None = None,
    account: dict | None = Depends(optional_account),
):
    services = _agentic_services(account)
    repository = _paper_repository(services)
    paper_service = services["paper_service"]
    try:
        payload = payload or PaperStrategyOperationPayload()
        operation_store = getattr(paper_service, "repository", None) or repository
        operation_id = payload.operation_id or _legacy_operation_id("paper-strategy-run", candidate_id)
        previous_operation = _existing_operation(operation_store, operation_id)
        execution = _call_service(
            paper_service.run_active,
            candidate_id,
            operation_id=operation_id,
        )
        operation = _existing_operation(operation_store, operation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OperationConflict as exc:
        raise _operation_conflict(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "execution": _public_execution_payload(execution), **_operation_response(operation, replayed=previous_operation is not None, message="交易意图已生成")}


@router.post("/strategy/paper-executions/{execution_id}/confirm")
def confirm_paper_strategy_execution(
    execution_id: str,
    payload: ConfirmPaperExecutionPayload | None = None,
    account: dict | None = Depends(optional_account),
):
    services = _agentic_services(account)
    repository = _paper_repository(services)
    paper_service = services["paper_service"]
    try:
        payload = payload or ConfirmPaperExecutionPayload()
        operation_store = getattr(paper_service, "repository", None) or repository
        operation_id = payload.operation_id or _legacy_operation_id("paper-execution-confirm", execution_id)
        previous_operation = _existing_operation(operation_store, operation_id)
        execution = _call_service(
            paper_service.confirm_execution,
            execution_id,
            portfolio=payload.portfolio,
            risk_context=payload.risk_context,
            operation_id=operation_id,
            confirmed_by=payload.confirmed_by,
        )
        operation = _existing_operation(operation_store, operation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OperationConflict as exc:
        raise _operation_conflict(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    response = {"success": True, "execution": _public_execution_payload(execution)}
    if operation is not None:
        response.update(_operation_response(operation, replayed=previous_operation is not None, message="交易意图确认已完成"))
    return response


@router.get("/strategy/order-drafts")
def list_agentic_order_drafts(
    limit: int = 100,
    account: dict | None = Depends(optional_account),
):
    repository = _paper_repository(_agentic_services(account))
    return {
        "success": True,
        "drafts": [_public_order_draft_payload(item) for item in repository.list_agentic_order_drafts(limit=limit)],
    }


@router.post("/strategy/paper-executions/{execution_id}/order-drafts")
def create_agentic_order_drafts(
    execution_id: str,
    payload: CreateOrderDraftsPayload | None = None,
    account: dict | None = Depends(optional_account),
):
    services = _agentic_services(account)
    repository = _paper_repository(services)
    paper_service = services["paper_service"]
    try:
        payload = payload or CreateOrderDraftsPayload()
        operation_store = getattr(paper_service, "repository", None) or repository
        operation_id = payload.operation_id or _legacy_operation_id(
            "paper-order-drafts", execution_id, str(payload.volume_per_code)
        )
        previous_operation = _existing_operation(operation_store, operation_id)
        drafts = _call_service(
            paper_service.create_order_drafts,
            execution_id,
            volume_per_code=payload.volume_per_code,
            operation_id=operation_id,
        )
        operation = _existing_operation(operation_store, operation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OperationConflict as exc:
        raise _operation_conflict(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    response = {"success": True, "drafts": [_public_order_draft_payload(item) for item in drafts]}
    if operation is not None:
        response.update(_operation_response(operation, replayed=previous_operation is not None, message="订单草案已生成"))
    return response


@router.post("/strategy/paper-executions/{execution_id}/paper-orders")
def submit_agentic_paper_orders(
    execution_id: str,
    payload: CreateOrderDraftsPayload | None = None,
    account: dict | None = Depends(optional_account),
):
    services = _agentic_services(account)
    repository = _paper_repository(services)
    paper_service = services["paper_service"]
    try:
        payload = payload or CreateOrderDraftsPayload()
        operation_store = getattr(paper_service, "repository", None) or repository
        operation_id = payload.operation_id or _legacy_operation_id(
            "paper-order-submit", execution_id, str(payload.volume_per_code)
        )
        previous_operation = _existing_operation(operation_store, operation_id)
        orders = _call_service(
            paper_service.submit_confirmed_execution_orders,
            execution_id,
            volume_per_code=payload.volume_per_code,
            operation_id=operation_id,
        )
        operation = _existing_operation(operation_store, operation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PaperOrderRecoveryRequired as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "paper_order_recovery_required",
                "message": "订单已写入，但 Agentic 状态更新失败，可恢复",
                "operation_id": exc.operation_id,
                "recoverable": True,
                "orders": [_public_paper_order_payload(item) for item in exc.orders],
            },
        ) from exc
    except OperationConflict as exc:
        raise _operation_conflict(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    response = {"success": True, "orders": [_public_paper_order_payload(item) for item in orders]}
    if operation is not None:
        recovered = bool(operation and operation.result.get("recovered"))
        response.update(_operation_response(operation, replayed=previous_operation is not None, recoverable=False, message="模拟盘订单已恢复" if recovered else "模拟盘订单已写入"))
    return response

@router.post("/strategy/run-candidates")
async def run_strategy_candidates(
    payload: RunCandidateBacktestsPayload,
    account: dict | None = Depends(optional_account),
):
    repository = _agentic_services(account)["repository"]
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
            result["result_id"] = repository.save_candidate_backtest_result(result, sample)
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
