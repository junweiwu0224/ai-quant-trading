"""Control-plane API for reproducible decisions and read-only reports."""

from __future__ import annotations

import asyncio
import math
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from config.settings import DB_DIR
from data.providers.astock_data_adapter import fetch_kline
from data.providers.market_data import MarketProviderError, fetch_market_history
from data.storage.storage import DataStorage
from dashboard.session import current_account
from decision.market import MARKET_ADAPTERS, get_market_adapter
from decision.report_export import report_to_json, report_to_markdown, report_to_pdf
from decision.store import DecisionStore, normalize_protected_ref
from engine.decision_worker import SQLiteWorkerLease


router = APIRouter()
store = DecisionStore(DB_DIR / "decisions.db")
research_storage = DataStorage()


class PortfolioRequest(BaseModel):
    market: str = "CN"
    name: str = Field(min_length=1, max_length=100)


class MemberRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    name: str = Field(default="", max_length=100)


class VersionRequest(BaseModel):
    strategies: list[dict[str, Any]] = Field(default_factory=list)
    thresholds: dict[str, Any] = Field(default_factory=dict)
    validation: dict[str, Any] = Field(default_factory=dict)
    risk_rules: dict[str, Any] = Field(default_factory=dict)


class TargetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    channel: Literal["wecom_robot", "pushplus", "feishu_robot", "qq_official_bot"]
    label: str = Field(min_length=1, max_length=100)
    secret_ref: str = Field(min_length=1, max_length=300)
    endpoint_ref: str = Field(default="", max_length=300)

    @field_validator("secret_ref")
    @classmethod
    def validate_secret_ref(cls, value: str) -> str:
        return normalize_protected_ref(value, field="secret_ref", required=True)

    @field_validator("endpoint_ref")
    @classmethod
    def validate_endpoint_ref(cls, value: str) -> str:
        return normalize_protected_ref(value, field="endpoint_ref", required=False)


class RouteRequest(BaseModel):
    portfolio_id: str
    target_id: str
    event_type: Literal["scheduled", "state_change", "major_risk"] = "scheduled"


class CommentaryRequest(BaseModel):
    model: str = Field(min_length=1, max_length=100)
    prompt: str = Field(min_length=1, max_length=20_000)
    input_hash: str = Field(min_length=8, max_length=128)
    content: str = Field(min_length=1, max_length=50_000)


def _workspace(account: dict) -> str:
    return str(account["workspace"]["id"])


def _portfolio_or_404(workspace_id: str, portfolio_id: str) -> dict[str, Any]:
    portfolio = store.get_portfolio(workspace_id, portfolio_id)
    if not portfolio:
        raise HTTPException(404, "策略组合不存在")
    return portfolio


def _stored_eligibility(workspace_id: str, portfolio_id: str) -> dict[str, Any]:
    """Read the last Worker-produced qualification without executing work."""

    version = store.get_current_version(workspace_id, portfolio_id)
    if not version:
        return {
            "eligible": False,
            "version_id": None,
            "checks": {},
            "reasons": ["current_version_required"],
            "stored": None,
        }
    stored = store.get_eligibility(version["id"])
    if not stored:
        return {
            "eligible": False,
            "version_id": version["id"],
            "checks": {
                "preview_ok": False,
                "validation_ok": False,
                "health_ok": False,
                "adapter_ok": False,
                "target_ok": False,
            },
            "reasons": ["eligibility_not_checked"],
            "stored": None,
        }
    checks = {
        key: bool(stored.get(key))
        for key in ("preview_ok", "validation_ok", "health_ok", "adapter_ok", "target_ok")
    }
    return {
        "eligible": all(checks.values()) and not stored.get("reasons"),
        "version_id": version["id"],
        "checks": checks,
        "reasons": list(stored.get("reasons") or []),
        "stored": stored,
    }


def _queue_command(
    workspace_id: str,
    command_type: str,
    payload: dict[str, Any],
    *,
    portfolio_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    key = str(idempotency_key or "").strip() or f"{command_type}:{uuid.uuid4().hex}"
    try:
        command = store.enqueue_command(
            workspace_id,
            command_type,
            payload,
            key,
            portfolio_id=portfolio_id,
        )
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    return {
        **command,
        "command_id": command["id"],
        "status_url": f"/api/decisions/commands/{command['id']}",
    }


@router.get("/markets")
async def markets(_account: dict = Depends(current_account)):
    return {"items": [adapter.capabilities() for adapter in MARKET_ADAPTERS.values()]}


@router.get("/portfolios")
async def list_portfolios(market: str | None = None, account: dict = Depends(current_account)):
    workspace_id = _workspace(account)
    result = []
    for portfolio in store.list_portfolios(workspace_id, market.upper() if market else None):
        portfolio["members"] = store.list_members(workspace_id, portfolio["id"])
        portfolio["version"] = store.get_current_version(workspace_id, portfolio["id"])
        result.append(portfolio)
    return {"items": result}


@router.post("/portfolios", status_code=201)
async def create_portfolio(request: PortfolioRequest, account: dict = Depends(current_account)):
    market = request.market.upper()
    if market not in MARKET_ADAPTERS:
        raise HTTPException(400, "不支持的市场")
    workspace_id = _workspace(account)
    portfolio = store.create_portfolio(workspace_id, market, request.name)
    portfolio["version"] = store.create_version(workspace_id, portfolio["id"], {})
    return portfolio


@router.get("/portfolios/{portfolio_id}")
async def portfolio_detail(portfolio_id: str, account: dict = Depends(current_account)):
    workspace_id = _workspace(account)
    portfolio = _portfolio_or_404(workspace_id, portfolio_id)
    return {
        "portfolio": portfolio,
        "members": store.list_members(workspace_id, portfolio_id),
        "version": store.get_current_version(workspace_id, portfolio_id),
        "eligibility": _stored_eligibility(workspace_id, portfolio_id),
    }


@router.post("/portfolios/{portfolio_id}/members", status_code=201)
async def add_member(portfolio_id: str, request: MemberRequest, account: dict = Depends(current_account)):
    workspace_id = _workspace(account)
    _portfolio_or_404(workspace_id, portfolio_id)
    return store.add_member(workspace_id, portfolio_id, request.symbol, request.name)


@router.delete("/portfolios/{portfolio_id}/members/{symbol}")
async def remove_member(portfolio_id: str, symbol: str, account: dict = Depends(current_account)):
    workspace_id = _workspace(account)
    if not store.remove_member(workspace_id, portfolio_id, symbol):
        raise HTTPException(404, "组合成员不存在")
    return {"removed": True, "symbol": symbol}


@router.post("/portfolios/{portfolio_id}/versions", status_code=201)
async def create_version(portfolio_id: str, request: VersionRequest, account: dict = Depends(current_account)):
    workspace_id = _workspace(account)
    try:
        return store.create_version(workspace_id, portfolio_id, request.model_dump())
    except KeyError:
        raise HTTPException(404, "策略组合不存在") from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.post("/portfolios/{portfolio_id}/preview", status_code=202)
async def preview_portfolio(
    portfolio_id: str,
    account: dict = Depends(current_account),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    workspace_id = _workspace(account)
    _portfolio_or_404(workspace_id, portfolio_id)
    return _queue_command(
        workspace_id,
        "decision.preview",
        {"portfolio_id": portfolio_id},
        portfolio_id=portfolio_id,
        idempotency_key=idempotency_key,
    )


@router.post("/portfolios/{portfolio_id}/analyze", status_code=202)
async def analyze_portfolio(
    portfolio_id: str,
    account: dict = Depends(current_account),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    workspace_id = _workspace(account)
    _portfolio_or_404(workspace_id, portfolio_id)
    return _queue_command(
        workspace_id,
        "decision.analyze",
        {"portfolio_id": portfolio_id},
        portfolio_id=portfolio_id,
        idempotency_key=idempotency_key,
    )


@router.post("/portfolios/{portfolio_id}/validate", status_code=202)
async def validate_portfolio(
    portfolio_id: str,
    account: dict = Depends(current_account),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    workspace_id = _workspace(account)
    _portfolio_or_404(workspace_id, portfolio_id)
    return _queue_command(
        workspace_id,
        "decision.validate",
        {"portfolio_id": portfolio_id},
        portfolio_id=portfolio_id,
        idempotency_key=idempotency_key,
    )


@router.get("/portfolios/{portfolio_id}/eligibility")
async def eligibility(portfolio_id: str, account: dict = Depends(current_account)):
    workspace_id = _workspace(account)
    _portfolio_or_404(workspace_id, portfolio_id)
    return _stored_eligibility(workspace_id, portfolio_id)


@router.post("/portfolios/{portfolio_id}/auto-push", status_code=202)
async def enable_auto_push(
    portfolio_id: str,
    account: dict = Depends(current_account),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    workspace_id = _workspace(account)
    _portfolio_or_404(workspace_id, portfolio_id)
    workspace_settings = account["workspace"].get("settings", {})
    if not bool(workspace_settings.get("decision_worker_enabled")):
        raise HTTPException(409, {"message": "独立决策 Worker 尚未启用", "reasons": ["decision_worker_disabled"]})
    return _queue_command(
        workspace_id,
        "decision.enable_auto_push",
        {"portfolio_id": portfolio_id},
        portfolio_id=portfolio_id,
        idempotency_key=idempotency_key,
    )


@router.delete("/portfolios/{portfolio_id}/auto-push", status_code=202)
async def disable_auto_push(
    portfolio_id: str,
    account: dict = Depends(current_account),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    workspace_id = _workspace(account)
    _portfolio_or_404(workspace_id, portfolio_id)
    return _queue_command(
        workspace_id,
        "decision.disable_auto_push",
        {"portfolio_id": portfolio_id},
        portfolio_id=portfolio_id,
        idempotency_key=idempotency_key,
    )


@router.get("/commands/{command_id}")
async def command_status(command_id: str, account: dict = Depends(current_account)):
    command = store.get_command(_workspace(account), command_id)
    if not command:
        raise HTTPException(404, "决策命令不存在")
    return {
        **command,
        "command_id": command["id"],
        "status_url": f"/api/decisions/commands/{command['id']}",
    }


@router.get("/reports")
async def reports(portfolio_id: str | None = None, limit: int = Query(50, ge=1, le=200), account: dict = Depends(current_account)):
    return {"items": store.list_reports(_workspace(account), portfolio_id, limit)}


@router.get("/reports/{report_id}")
async def report_detail(report_id: str, account: dict = Depends(current_account)):
    report = store.get_report(_workspace(account), report_id)
    if not report:
        raise HTTPException(404, "报告不存在")
    return report


@router.get("/reports/{report_id}/export")
async def export_report(report_id: str, format: Literal["json", "markdown", "pdf"] = Query("json"), account: dict = Depends(current_account)):
    """Download a read-only evidence projection of a frozen report."""

    report = store.get_report(_workspace(account), report_id)
    if not report:
        raise HTTPException(404, "报告不存在")
    if format == "json":
        content, media_type, extension = report_to_json(report), "application/json", "json"
    elif format == "markdown":
        content, media_type, extension = report_to_markdown(report), "text/markdown", "md"
    else:
        content, media_type, extension = report_to_pdf(report), "application/pdf", "pdf"
    safe_id = "".join(char for char in report_id if char.isalnum() or char in "-_")[:80] or "report"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="decision-report-{safe_id}.{extension}"'},
    )


@router.get("/reports/{report_id}/deliveries")
async def report_deliveries(report_id: str, account: dict = Depends(current_account)):
    workspace_id = _workspace(account)
    if not store.get_report(workspace_id, report_id):
        raise HTTPException(404, "报告不存在")
    return {
        "items": store.list_delivery_attempts(workspace_id, report_id),
        "claims": store.list_delivery_claims(workspace_id, report_id),
    }


@router.post("/reports/{report_id}/share", status_code=201)
async def share_report(report_id: str, ttl_days: int = Query(7, ge=1, le=30), account: dict = Depends(current_account)):
    try:
        token, link = store.issue_share_link(_workspace(account), report_id, ttl_days)
    except KeyError:
        raise HTTPException(404, "报告不存在") from None
    return {"link": link, "url": f"/report/{token}"}


@router.delete("/share-links/{link_id}")
async def revoke_share_link(link_id: str, account: dict = Depends(current_account)):
    if not store.revoke_share(_workspace(account), link_id):
        raise HTTPException(404, "分享链接不存在")
    return {"revoked": True}


async def get_shared_report(token: str):
    """Called by the public ``/report/{token}`` route without a workspace cookie."""
    shared = store.resolve_share(token)
    if not shared:
        raise HTTPException(404, "报告链接不存在、已过期或已撤销")
    public_commentary = [
        {key: item.get(key) for key in ("model", "input_hash", "content", "created_at")}
        for item in shared.get("ai_commentary", [])
    ]
    public_deliveries = [
        {key: item.get(key) for key in ("channel", "attempt_no", "status", "created_at")}
        for item in shared.get("delivery_attempts", [])
    ]
    return {
        "report": shared["body"],
        "report_hash": shared["report_hash"],
        "expires_at": shared["expires_at"],
        "ai_commentary": public_commentary,
        "ai_commentary_status": shared.get("ai_commentary_status", "not_available"),
        "delivery_attempts": public_deliveries,
    }


@router.get("/shared/{token}")
async def shared_report_api(token: str):
    return await get_shared_report(token)


@router.post("/reports/{report_id}/commentary", status_code=201)
async def add_commentary(report_id: str, request: CommentaryRequest, account: dict = Depends(current_account)):
    """Store an AI explanation only; this endpoint cannot alter a report or decision."""
    try:
        return store.add_ai_commentary(_workspace(account), report_id, request.model, request.prompt, request.input_hash, request.content)
    except KeyError:
        raise HTTPException(404, "报告不存在") from None


@router.get("/targets")
async def targets(account: dict = Depends(current_account)):
    return {"items": store.list_targets(_workspace(account))}


@router.post("/targets", status_code=201)
async def create_target(request: TargetRequest, account: dict = Depends(current_account)):
    # The target config is a protected-reference contract.  Credentials never
    # enter this database, API response, report, or repository.
    return store.create_target(_workspace(account), request.channel, request.label, {"secret_ref": request.secret_ref, "endpoint_ref": request.endpoint_ref})


@router.post("/targets/{target_id}/test", status_code=202)
async def test_target(
    target_id: str,
    account: dict = Depends(current_account),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    workspace_id = _workspace(account)
    if not store.get_target(workspace_id, target_id):
        raise HTTPException(404, "通知目标不存在")
    return _queue_command(
        workspace_id,
        "notification.test_target",
        {"target_id": target_id},
        idempotency_key=idempotency_key,
    )


@router.get("/delivery-attempts")
async def delivery_attempts(report_id: str | None = None, account: dict = Depends(current_account)):
    return {"items": store.list_delivery_attempts(_workspace(account), report_id)}


@router.get("/delivery-claims")
async def delivery_claims(report_id: str | None = None, account: dict = Depends(current_account)):
    """List durable dispatch/ambiguity states for operator review."""

    return {"items": store.list_delivery_claims(_workspace(account), report_id)}


@router.get("/routes")
async def routes(portfolio_id: str | None = None, account: dict = Depends(current_account)):
    return {"items": store.list_routes(_workspace(account), portfolio_id)}


@router.post("/routes", status_code=201)
async def create_route(request: RouteRequest, account: dict = Depends(current_account)):
    workspace_id = _workspace(account)
    _portfolio_or_404(workspace_id, request.portfolio_id)
    if not any(item["id"] == request.target_id for item in store.list_targets(workspace_id)):
        raise HTTPException(404, "通知目标不存在")
    return store.create_route(workspace_id, request.portfolio_id, request.target_id, request.event_type)


@router.get("/research/{market}/{symbol}")
async def research(market: str, symbol: str, account: dict = Depends(current_account)):
    try:
        adapter = get_market_adapter(market)
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, f"无效的市场或标的: {market}/{symbol}") from exc
    normalized_market = adapter.market
    if normalized_market != "CN":
        try:
            external = await asyncio.to_thread(fetch_market_history, normalized_market, symbol, count=180, period="daily")
        except (MarketProviderError, KeyError, ValueError) as exc:
            return {
                "symbol": symbol,
                "market": adapter.capabilities(),
                "bars": [],
                "status": "provider_unavailable",
                "source": "yahoo_finance_chart",
                "authoritative": False,
                "data_quality": {"status": "unavailable", "authoritative": False, "manual_research_only": True},
                "fallback_reason": str(exc),
            }
        bars = list(external.get("klines") or [])
        return {
            "symbol": symbol,
            "market": adapter.capabilities(),
            "bars": bars,
            "status": "manual_research" if bars else "no_data",
            "source": external.get("source") or "yahoo_finance_chart",
            "provider": external.get("provider"),
            "latest_date": external.get("as_of"),
            "updated_at": external.get("updated_at"),
            "authoritative": False,
            "data_quality": {
                "status": "partial" if bars else "unavailable",
                "bars": len(bars),
                "coverage_pct": external.get("coverage_pct"),
                "authoritative": False,
                "manual_research_only": True,
            },
            "fallback_reason": "manual_research_provider; not eligible for deterministic decisions",
        }
    frame = research_storage.get_stock_daily(symbol)
    if not frame.empty:
        bars = [
            {
                "date": str(row["date"]),
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"],
                "amount": row.get("amount") if hasattr(row, "get") else None,
            }
            for _, row in frame.tail(180).iterrows()
        ]
        latest_date = bars[-1].get("date") if bars else None
        return {
            "symbol": symbol,
            "market": adapter.capabilities(),
            "bars": bars,
            "status": "ok" if bars else "no_local_data",
            "source": "local_stock_daily",
            "latest_date": latest_date,
            "updated_at": None,
            "data_quality": {
                "status": "available" if bars else "unavailable",
                "bars": len(bars),
                "authoritative": True,
                "manual_research_only": False,
            },
            "authoritative": True,
            "fallback_reason": "",
        }

    # Keep manual research usable when local coverage is empty, but make the
    # provenance explicit. This path must never feed deterministic decisions,
    # risk checks, or automatic delivery eligibility.
    try:
        raw = await asyncio.to_thread(fetch_kline, symbol, count=180, period="day")
    except Exception:
        raw = None
    bars: list[dict[str, Any]] = []
    for parts in (raw or {}).get("klines_raw", []):
        if len(parts) < 6:
            continue
        try:
            values = [float(parts[index]) for index in range(1, 6)]
        except (TypeError, ValueError):
            continue
        if not all(math.isfinite(value) for value in values):
            continue
        bars.append(
            {
                "date": str(parts[0]),
                "open": values[0],
                "close": values[1],
                "high": values[2],
                "low": values[3],
                "volume": values[4],
                "amount": _safe_optional_float(parts[6]) if len(parts) > 6 else None,
            }
        )
    bars = bars[-180:]
    if bars:
        return {
            "symbol": symbol,
            "market": adapter.capabilities(),
            "bars": bars,
            "status": "degraded",
            "source": "external_kline_fallback",
            "latest_date": bars[-1].get("date"),
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "data_quality": {
                "status": "partial",
                "bars": len(bars),
                "authoritative": False,
                "manual_research_only": True,
            },
            "authoritative": False,
            "fallback_reason": "local_stock_daily_empty; external_kline_for_manual_research_only",
        }
    return {
        "symbol": symbol,
        "market": adapter.capabilities(),
        "bars": [],
        "status": "no_data",
        "source": "none",
        "latest_date": None,
        "updated_at": None,
        "data_quality": {"status": "unavailable", "bars": 0, "authoritative": False, "manual_research_only": True},
        "authoritative": False,
        "fallback_reason": "local_stock_daily_empty; external_kline_unavailable",
    }


def _safe_optional_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


@router.get("/status")
async def status(account: dict = Depends(current_account)):
    workspace = account["workspace"]
    lease = SQLiteWorkerLease(DB_DIR / "worker_leases.db")
    try:
        readiness = lease.readiness()
    finally:
        lease.close()
    worker_automation_enabled = bool(workspace.get("settings", {}).get("decision_worker_enabled"))
    worker_process_ready = bool(readiness.get("ready"))
    return {
        # Keep the legacy field stable for existing API consumers. The new
        # fields distinguish process liveness from workspace automation.
        "worker_enabled": worker_automation_enabled,
        "worker_automation_enabled": worker_automation_enabled,
        "worker_process_ready": worker_process_ready,
        "auto_push_enabled": bool(workspace.get("settings", {}).get("decision_auto_push_enabled")),
        "worker_readiness": readiness,
        "markets": [item.capabilities() for item in MARKET_ADAPTERS.values()],
    }


@router.get("/worker/readiness")
async def worker_readiness(_account: dict = Depends(current_account)):
    lease = SQLiteWorkerLease(DB_DIR / "worker_leases.db")
    try:
        return lease.readiness()
    finally:
        lease.close()
