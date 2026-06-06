"""FastAPI 可视化面板"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

from dashboard.auth import api_key_enabled, is_valid_api_key, request_api_key
from dashboard.account_store import account_store

BASE_DIR = Path(__file__).resolve().parent


class APIKeyMiddleware(BaseHTTPMiddleware):
    """HTTP API Key 校验。WebSocket 在各端点握手前校验。"""

    async def dispatch(self, request: Request, call_next):
        if request.url.path in ("/", "/favicon.ico", "/sw.js") or request.url.path.startswith("/static/"):
            return await call_next(request)
        if request.url.path.startswith("/api/account/"):
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
        "/api/account/me",
        "/api/account/login",
        "/api/account/register",
        "/api/account/logout",
    }

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if os.environ.get("APP_ENV") == "test":
            return await call_next(request)
        if path in self._allowed_paths or path.startswith("/static/"):
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


# ── 生命周期：启动/停止后台调度器 ──

@asynccontextmanager
async def lifespan(app: FastAPI):
    from data.scheduler import DataScheduler
    from data.collector.quote_service import get_quote_service
    from dashboard.openclaw_service import openclaw_service_manager

    scheduler = DataScheduler()
    quote_service = get_quote_service(interval=1.0)

    try:
        scheduler.start()
        logger.info("数据同步调度器已启动")
    except Exception as e:
        logger.warning(f"调度器启动失败: {e}")

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

    try:
        status = await openclaw_service_manager.ensure_started()
        logger.info(f"OpenClaw 托管状态: {status.get('state')} {status.get('gateway_url')}")
    except Exception as e:
        logger.warning(f"OpenClaw 托管启动失败: {e}")

    yield

    await openclaw_service_manager.shutdown()
    quote_service.stop()
    scheduler.stop()


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
templates = Jinja2Templates(directory=BASE_DIR / "templates")


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
    agentic, account, alerts, alpha, backtest, broker_config, conditional_orders, datahub, factor, llm, market, market_rules, openclaw, optimization, paper_control,
    paper_trading, portfolio, portfolio_opt, qlib, realtime_quotes, screener, signals, stock_detail, strategy,
    strategy_version, system, valuation, watchlist,
)

app.include_router(account.router, prefix="/api/account", tags=["用户与工作区"])
app.include_router(agentic.router, prefix="/api/agentic", tags=["Agentic 交易平台"])
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
app.include_router(openclaw.router, prefix="/api/openclaw", tags=["OpenClaw"])
app.include_router(screener.router, prefix="/api/screener", tags=["条件选股"])
app.include_router(valuation.router, prefix="/api/valuation", tags=["估值数据中心"])
app.include_router(datahub.router, prefix="/api/datahub", tags=["数据底座"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["预警管理"])
app.include_router(conditional_orders.router, prefix="/api/conditional-orders", tags=["条件单"])
app.include_router(market.router, prefix="/api/market", tags=["市场雷达"])
app.include_router(market_rules.router, prefix="/api/market-rules", tags=["市场规则"])
app.include_router(factor.router, prefix="/api/factor", tags=["因子分析"])
app.include_router(portfolio_opt.router, prefix="/api/portfolio-opt", tags=["组合优化"])
app.include_router(signals.router, prefix="/api/signals", tags=["AI 信号"])
app.include_router(qlib.router, prefix="/api/qlib", tags=["qlib 预测"])


# ── 页面路由 ──

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")
