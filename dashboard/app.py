"""FastAPI 可视化面板"""
import os
import asyncio
import sqlite3
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

from dashboard.auth import api_key_enabled, is_valid_api_key, request_api_key
from dashboard.account_store import account_store

BASE_DIR = Path(__file__).resolve().parent


def _is_public_share_api(path: str) -> bool:
    """Allow only the tokenized, read-only report resolver without a session."""

    parts = path.split("/")
    return len(parts) == 5 and parts[:4] == ["", "api", "decisions", "shared"] and _is_share_token(parts[4])


def _is_share_token(value: str) -> bool:
    """Match the URL-safe token alphabet emitted by ``issue_share_link``."""

    return bool(value) and all(character.isalnum() or character in "-_" for character in value)


def _is_public_share_page(path: str) -> bool:
    """Allow only the single-segment public report shell route."""

    parts = path.split("/")
    return len(parts) == 3 and parts[:2] == ["", "report"] and _is_share_token(parts[2])


def _is_public_vue_asset(path: str) -> bool:
    """Vue assets contain no workspace data and must load for public reports."""

    return path.startswith("/app/assets/")


def _is_vue_shell(path: str) -> bool:
    """The Vue shell is safe to serve before login; its APIs remain gated."""

    return path == "/app" or path.startswith("/app/")


class APIKeyMiddleware(BaseHTTPMiddleware):
    """HTTP API Key 校验。WebSocket 在各端点握手前校验。"""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if (
            path in ("/", "/health", "/readiness", "/favicon.ico", "/sw.js")
            or path.startswith("/static/")
            or _is_vue_shell(path)
            or _is_public_vue_asset(path)
            or _is_public_share_api(path)
            or _is_public_share_page(path)
        ):
            return await call_next(request)
        if path.startswith("/api/account/"):
            return await call_next(request)
        if request.cookies.get("quant_session"):
            return await call_next(request)
        if not is_valid_api_key(request_api_key(request)):
            return Response(
                content='{"detail":"无效的 API Key"}',
                status_code=401,
                media_type="application/json",
            )
        return await call_next(request)


class SessionGateMiddleware(BaseHTTPMiddleware):
    """Require login for all app APIs except account bootstrap endpoints."""

    _allowed_paths = {
        "/",
        "/favicon.ico",
        "/sw.js",
        "/health",
        "/readiness",
        "/api/account/me",
        "/api/account/login",
        "/api/account/register",
        "/api/account/logout",
    }

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if os.environ.get("APP_ENV") == "test":
            return await call_next(request)
        if path in self._allowed_paths or path.startswith("/static/") or _is_public_vue_asset(path) or _is_public_share_api(path) or _is_public_share_page(path):
            return await call_next(request)
        if not path.startswith("/api/"):
            return await call_next(request)
        if api_key_enabled() and is_valid_api_key(request_api_key(request)):
            return await call_next(request)
        if request.cookies.get("quant_session"):
            token = request.cookies.get("quant_session") or ""
            if account_store.get_user_by_session(token):
                return await call_next(request)
        return Response(
            content='{"detail":"请先登录"}',
            status_code=401,
            media_type="application/json",
        )


def _dashboard_owns_background_work() -> bool:
    """Legacy compatibility only; the standalone worker is the production owner."""

    enabled = os.environ.get("DASHBOARD_BACKGROUND_WORKER", "false").lower() in {"1", "true", "yes", "on"}
    ownership = os.environ.get("WORKER_OWNERSHIP", "standalone").strip().lower()
    return enabled and ownership == "dashboard-legacy"


# ── 生命周期：只在显式 legacy 模式启动后台任务 ──

@asynccontextmanager
async def lifespan(app: FastAPI):
    from data.collector.quote_service import get_quote_service
    from dashboard.routers.realtime_quotes import configure_broadcast_loop
    from dashboard.routers.realtime_quotes import close_alert_outbox
    scheduler = None
    legacy_lease = None
    legacy_lease_token = ""
    legacy_lease_stop: asyncio.Event | None = None
    legacy_lease_task: asyncio.Task | None = None
    legacy_lease_owner = f"dashboard-legacy:{os.getpid()}"
    quote_service = get_quote_service(interval=1.0)
    configure_broadcast_loop(asyncio.get_running_loop())
    notification_stop: asyncio.Event | None = None
    notification_task: asyncio.Task | None = None
    notification_outbox = None

    async def _notification_worker():
        assert notification_stop is not None
        assert notification_outbox is not None
        from engine.notifications.adapters import AlertWebhookNotificationAdapter, DailyBriefNotificationAdapter
        from engine.notifications.dispatcher import NotificationDispatcher

        notification_dispatcher = NotificationDispatcher(
            notification_outbox,
            AlertWebhookNotificationAdapter(),
            consumer="legacy-alert-webhook-worker",
            event_types=("market.alert.triggered",),
        )
        daily_brief_dispatcher = NotificationDispatcher(
            notification_outbox,
            DailyBriefNotificationAdapter(os.environ.get("DAILY_BRIEF_WEBHOOK_URL", "")),
            consumer="legacy-daily-brief-worker",
            event_types=("daily.brief.ready",),
        )
        while not notification_stop.is_set():
            try:
                await asyncio.to_thread(
                    notification_outbox.reclaim_stale,
                    older_than_seconds=300,
                )
                await asyncio.to_thread(notification_dispatcher.dispatch, limit=50)
                await asyncio.to_thread(daily_brief_dispatcher.dispatch, limit=20)
            except Exception as exc:
                logger.warning(f"通知 outbox worker 异常: {exc}")
            try:
                await asyncio.wait_for(notification_stop.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

    async def _legacy_lease_guard():
        assert legacy_lease is not None
        assert legacy_lease_stop is not None
        ttl_seconds = 30.0
        while not legacy_lease_stop.is_set():
            try:
                await asyncio.wait_for(legacy_lease_stop.wait(), timeout=max(1.0, ttl_seconds / 3.0))
                continue
            except asyncio.TimeoutError:
                pass
            try:
                renewed = await asyncio.to_thread(
                    legacy_lease.renew,
                    legacy_lease_owner,
                    fence_token=legacy_lease_token,
                    ttl_seconds=ttl_seconds,
                )
                if renewed is None or not await asyncio.to_thread(
                    legacy_lease.heartbeat,
                    legacy_lease_owner,
                    fence_token=legacy_lease_token,
                    status="running",
                ):
                    logger.error("Dashboard legacy background lease was lost; stopping legacy workers")
                    legacy_lease_stop.set()
                    if notification_stop is not None:
                        notification_stop.set()
                    if scheduler is not None:
                        await asyncio.to_thread(scheduler.stop)
                    return
            except Exception as exc:
                logger.error(f"Dashboard legacy lease renewal failed: {exc}")
                legacy_lease_stop.set()
                if notification_stop is not None:
                    notification_stop.set()
                if scheduler is not None:
                    await asyncio.to_thread(scheduler.stop)
                return

    if _dashboard_owns_background_work():
        from config.settings import DB_DIR
        from data.scheduler import DataScheduler
        from engine.events.outbox import SQLiteOutbox
        from engine.decision_worker import SQLiteWorkerLease

        legacy_lease = SQLiteWorkerLease(DB_DIR / "worker_leases.db")
        acquired = legacy_lease.acquire(legacy_lease_owner, ttl_seconds=30.0)
        if acquired is None:
            logger.warning("Dashboard legacy 后台任务未启动：独立 Worker 已持有 ownership lease")
            legacy_lease.close()
            legacy_lease = None
        elif not legacy_lease.heartbeat(legacy_lease_owner, fence_token=acquired.fence_token, status="ready"):
            logger.error("Dashboard legacy 后台任务未启动：ownership lease heartbeat 初始化失败")
            legacy_lease.release(legacy_lease_owner, fence_token=acquired.fence_token)
            legacy_lease.close()
            legacy_lease = None
        else:
            legacy_lease_token = acquired.fence_token
            scheduler = DataScheduler()
            notification_outbox = SQLiteOutbox(DB_DIR / "events.db")
            notification_stop = asyncio.Event()
            legacy_lease_stop = asyncio.Event()
            notification_task = asyncio.create_task(_notification_worker(), name="legacy-notification-outbox-worker")
            try:
                scheduler.start()
                logger.warning("Dashboard 正在运行 legacy 后台任务；生产环境应使用独立 worker")
            except Exception as e:
                logger.warning(f"调度器启动失败: {e}")
            legacy_lease_task = asyncio.create_task(_legacy_lease_guard(), name="legacy-worker-lease-guard")
    else:
        logger.info("Dashboard 控制面模式：后台调度与通知由独立 worker 所有")

    # 启动行情服务，自动订阅自选股
    try:
        from data.storage import DataStorage
        from dashboard.routers.realtime_quotes import _sync_broadcast
        storage = DataStorage()
        watchlist = storage.get_watchlist()
        if watchlist:
            quote_service.subscribe(watchlist)
            logger.info(f"行情服务订阅自选股: {watchlist}")
        quote_service.on_update(_sync_broadcast)
        quote_service.start()
        logger.info("实时行情服务已启动")
    except Exception as e:
        logger.warning(f"行情服务启动失败: {e}")

    yield

    quote_service.stop()
    if legacy_lease_stop is not None:
        legacy_lease_stop.set()
    if legacy_lease_task is not None:
        await legacy_lease_task
    if scheduler is not None:
        scheduler.stop()
    if notification_stop is not None:
        notification_stop.set()
    if notification_task is not None:
        await notification_task
    if notification_outbox is not None:
        notification_outbox.close()
    if legacy_lease is not None:
        legacy_lease.release(legacy_lease_owner, fence_token=legacy_lease_token)
        legacy_lease.close()
    close_alert_outbox()
    configure_broadcast_loop(None)


app = FastAPI(
    title="AI 量化交易系统",
    version="0.1.0",
    lifespan=lifespan,
)

# 登录门
app.add_middleware(SessionGateMiddleware)

# API 认证
if api_key_enabled():
    app.add_middleware(APIKeyMiddleware)

# CORS — 生产环境只允许 HTTPS，开发环境允许 localhost
_ENV = os.environ.get("APP_ENV", "development")
_origins = (
    ["https://biga.junwei.fun"]
    if _ENV == "production"
    else ["https://biga.junwei.fun", "http://localhost:8001", "http://127.0.0.1:8001"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
UI_DIST = BASE_DIR / "ui" / "dist"
if UI_DIST.exists():
    app.mount("/app/assets", StaticFiles(directory=UI_DIST / "assets"), name="vue-assets")


def _probe_sqlite() -> dict[str, object]:
    from config.settings import DB_PATH

    try:
        with sqlite3.connect(DB_PATH, timeout=2) as connection:
            connection.execute("SELECT 1").fetchone()
        return {"ready": True, "status": "ready", "path": str(DB_PATH)}
    except Exception as exc:
        return {"ready": False, "status": "unavailable", "error": str(exc)[:200]}


def _probe_qlib() -> dict[str, object]:
    url = os.getenv("QLIB_SERVICE_URL", "http://127.0.0.1:8002").rstrip("/") + "/health"
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            import json
            payload = json.loads(response.read().decode("utf-8"))
        ready = isinstance(payload, dict) and payload.get("success") is True
        return {"ready": ready, "status": payload.get("status", "unknown"), "response": payload}
    except (OSError, ValueError, TypeError, urllib.error.URLError) as exc:
        return {"ready": False, "status": "unavailable", "error": str(exc)[:200]}


def _probe_worker(lease_name: str) -> dict[str, object]:
    from config.settings import DB_DIR
    from engine.decision_worker import SQLiteWorkerLease

    lease = SQLiteWorkerLease(DB_DIR / "worker_leases.db", lease_name=lease_name)
    try:
        state = lease.readiness()
        return {
            key: state[key]
            for key in (
                "ready",
                "status",
                "worker_name",
                "age_seconds",
                "draining",
                "lease_matches",
            )
            if key in state
        }
    finally:
        lease.close()


def _readiness_state() -> dict[str, object]:
    from data.collector.quote_service import get_quote_service

    dependencies: dict[str, object] = {
        "database": _probe_sqlite(),
        "quote_service": {
            "ready": get_quote_service().is_running,
            "status": "ready" if get_quote_service().is_running else "unavailable",
        },
        "qlib": _probe_qlib(),
    }
    if os.getenv("DECISION_WORKER_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}:
        dependencies["decision_worker"] = _probe_worker("decision-worker")
    if os.getenv("PI_AGENT_WORKER_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}:
        dependencies["pi_agent_worker"] = _probe_worker("ai-worker")

    failed = [name for name, state in dependencies.items() if not bool(state.get("ready"))]
    status = "ready" if not failed else "degraded" if len(failed) < len(dependencies) else "unavailable"
    return {"status": status, "service": "dashboard", "dependencies": dependencies, "failed": failed}


@app.get("/health", tags=["运行状态"])
async def health():
    """Liveness probe that does not require authentication or external services."""

    return {"status": "ok", "service": "dashboard"}


@app.get("/readiness", tags=["运行状态"])
async def readiness(response: Response):
    """Readiness probe for load balancers and container orchestration."""

    state = await asyncio.to_thread(_readiness_state)
    if state["status"] != "ready":
        response.status_code = 503
    return state


@app.get("/sw.js")
async def service_worker():
    """Service Worker 必须从根路径提供以获得完整 scope"""
    from fastapi.responses import FileResponse
    sw_path = BASE_DIR / "static" / "sw.js"
    if sw_path.exists():
        return FileResponse(sw_path, media_type="application/javascript",
                            headers={"Cache-Control": "no-cache"})
    return ""


@app.get("/favicon.ico")
async def favicon():
    from fastapi.responses import FileResponse
    return FileResponse(BASE_DIR / "static" / "icons" / "icon-192.svg", media_type="image/svg+xml")


# ── API 路由 ──

from dashboard.routers import (  # noqa: E402
    agentic, account, ai, alerts, alpha, audit, backtest, broker_config, conditional_orders, datahub, factor, llm, market, market_rules, optimization, paper_control,
    paper_trading, portfolio, portfolio_opt, qlib, realtime_quotes, screener, signals, stock_detail, strategy,
    strategy_version, system, valuation, watchlist,
)

from dashboard.routers import decisions

app.include_router(account.router, prefix="/api/account", tags=["用户与工作区"])
app.include_router(agentic.router, prefix="/api/agentic", tags=["Agentic 交易平台"])
app.include_router(ai.router, prefix="/api/ai", tags=["AI Runtime"])
app.include_router(backtest.router, prefix="/api/backtest", tags=["回测"])
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["持仓"])
app.include_router(system.router, prefix="/api/system", tags=["系统"])
app.include_router(alpha.router, prefix="/api/alpha", tags=["AI Alpha"])
app.include_router(watchlist.router, prefix="/api/watchlist", tags=["自选股"])
app.include_router(paper_control.router, prefix="/api/paper", tags=["模拟盘"])
app.include_router(paper_trading.router, prefix="/api/paper", tags=["模拟盘完整功能"])
app.include_router(strategy.router, prefix="/api/strategy", tags=["策略管理"])
app.include_router(broker_config.router, prefix="/api/broker", tags=["券商配置"])
app.include_router(realtime_quotes.router, tags=["实时行情"])
app.include_router(stock_detail.router, prefix="/api/stock", tags=["股票详情"])
app.include_router(optimization.router, prefix="/api/optimization", tags=["参数优化"])
app.include_router(strategy_version.router, prefix="/api/strategy-version", tags=["策略版本管理"])
app.include_router(llm.router, prefix="/api/llm", tags=["AI 助手"])
app.include_router(screener.router, prefix="/api/screener", tags=["条件选股"])
app.include_router(valuation.router, prefix="/api/valuation", tags=["估值数据中心"])
app.include_router(datahub.router, prefix="/api/datahub", tags=["数据底座"])
app.include_router(audit.router, prefix="/api", tags=["审计"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["预警管理"])
app.include_router(conditional_orders.router, prefix="/api/conditional-orders", tags=["条件单"])
app.include_router(market.router, prefix="/api/market", tags=["市场雷达"])
app.include_router(market_rules.router, prefix="/api/market-rules", tags=["市场规则"])
app.include_router(factor.router, prefix="/api/factor", tags=["因子分析"])
app.include_router(portfolio_opt.router, prefix="/api/portfolio-opt", tags=["组合优化"])
app.include_router(signals.router, prefix="/api/signals", tags=["AI 信号"])
app.include_router(qlib.router, prefix="/api/qlib", tags=["AI 信号兼容接口"])
app.include_router(decisions.router, prefix="/api/decisions", tags=["可复现决策与报告"])


# ── 页面路由 ──

def _vue_shell_response() -> FileResponse:
    if not UI_DIST.exists() or not (UI_DIST / "index.html").exists():
        raise HTTPException(status_code=503, detail="Vue 应用尚未构建")
    return FileResponse(UI_DIST / "index.html", media_type="text/html", headers={"Cache-Control": "no-cache"})


@app.get("/auth")
async def auth_application():
    """Serve the Vue history-mode shell for the authentication route."""

    return _vue_shell_response()


@app.get("/")
async def index(request: Request):
    if (
        UI_DIST.exists()
        and request.url.query
        and (
            request.query_params.get('code') or request.query_params.get('symbol')
            or any(request.query_params.get(key) for key in ("route", "tab", "view", "page"))
        )
    ):
        return RedirectResponse(f"/app/decision?{request.url.query}")
    if not UI_DIST.exists() or not (UI_DIST / "index.html").exists():
        raise HTTPException(status_code=503, detail="Vue 应用尚未构建")
    return FileResponse(UI_DIST / "index.html", media_type="text/html", headers={"Cache-Control": "no-cache"})


@app.get("/app/{path:path}")
async def vue_application(path: str, request: Request):
    """Serve the Vue history-mode shell without exposing legacy static paths."""

    if not UI_DIST.exists() or not (UI_DIST / "index.html").exists():
        raise HTTPException(status_code=503, detail="Vue 应用尚未构建")
    return FileResponse(UI_DIST / "index.html", media_type="text/html", headers={"Cache-Control": "no-cache"})


@app.get("/report/{token}")
async def shared_report(token: str):
    """Validate the public token before serving the Vue report shell."""

    shared = await decisions.get_shared_report(token)
    if UI_DIST.exists() and (UI_DIST / "index.html").exists():
        return FileResponse(UI_DIST / "index.html", media_type="text/html", headers={"Cache-Control": "no-cache"})
    return shared
