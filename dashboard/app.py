"""FastAPI 可视化面板"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger

BASE_DIR = Path(__file__).resolve().parent


# ── 生命周期：启动/停止后台调度器 ──

@asynccontextmanager
async def lifespan(app: FastAPI):
    from data.scheduler import DataScheduler
    scheduler = DataScheduler()
    try:
        scheduler.start()
        logger.info("数据同步调度器已启动")
    except Exception as e:
        logger.warning(f"调度器启动失败: {e}")
    yield
    scheduler.stop()


app = FastAPI(title="AI 量化交易系统", version="0.1.0", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


# ── API 路由 ──

from dashboard.routers import (  # noqa: E402
    alpha, backtest, broker_config, paper_control, portfolio, strategy, system, watchlist,
)

app.include_router(backtest.router, prefix="/api/backtest", tags=["回测"])
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["持仓"])
app.include_router(system.router, prefix="/api/system", tags=["系统"])
app.include_router(alpha.router, prefix="/api/alpha", tags=["AI Alpha"])
app.include_router(watchlist.router, prefix="/api/watchlist", tags=["自选股"])
app.include_router(paper_control.router, prefix="/api/paper", tags=["模拟盘"])
app.include_router(strategy.router, prefix="/api/strategy", tags=["策略管理"])
app.include_router(broker_config.router, prefix="/api/broker", tags=["券商配置"])


# ── 页面路由 ──

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")
