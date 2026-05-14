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

BASE_DIR = Path(__file__).resolve().parent

# ── API 认证中间件（仅对 HTTP 请求生效，不影响 WebSocket）──
_QUANT_API_KEY = os.environ.get("QUANT_SYSTEM_API_KEY", "")


class APIKeyMiddleware(BaseHTTPMiddleware):
    """HTTP-only API Key 校验，WebSocket 请求自动跳过"""

    async def dispatch(self, request: Request, call_next):
        if _QUANT_API_KEY:
            key = request.headers.get("X-API-Key", "")
            if key != _QUANT_API_KEY:
                return Response(content='{"detail":"无效的 API Key"}', status_code=401,
                                media_type="application/json")
        return await call_next(request)


# ── 生命周期：启动/停止后台调度器 ──

@asynccontextmanager
async def lifespan(app: FastAPI):
    from data.scheduler import DataScheduler
    from data.collector.quote_service import get_quote_service

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

    yield

    quote_service.stop()
    scheduler.stop()


app = FastAPI(
    title="AI 量化交易系统",
    version="0.1.0",
    lifespan=lifespan,
)

# API 认证（HTTP-only 中间件，不影响 WebSocket）
if _QUANT_API_KEY:
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
    alerts, alpha, backtest, broker_config, conditional_orders, factor, llm, market, market_rules, optimization, paper_control,
    paper_trading, portfolio, portfolio_opt, qlib, realtime_quotes, screener, stock_detail, strategy,
    strategy_version, system, watchlist,
)

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
app.include_router(alerts.router, prefix="/api/alerts", tags=["预警管理"])
app.include_router(conditional_orders.router, prefix="/api/conditional-orders", tags=["条件单"])
app.include_router(market.router, prefix="/api/market", tags=["市场雷达"])
app.include_router(market_rules.router, prefix="/api/market-rules", tags=["市场规则"])
app.include_router(factor.router, prefix="/api/factor", tags=["因子分析"])
app.include_router(portfolio_opt.router, prefix="/api/portfolio-opt", tags=["组合优化"])
app.include_router(qlib.router, prefix="/api/qlib", tags=["qlib 预测"])


# ── 页面路由 ──

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")
