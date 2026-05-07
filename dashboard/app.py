"""FastAPI 可视化面板"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="AI 量化交易系统", version="0.1.0")

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


# ── API 路由 ──

from dashboard.routers import backtest, portfolio  # noqa: E402

app.include_router(backtest.router, prefix="/api/backtest", tags=["回测"])
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["持仓"])


# ── 页面路由 ──

from fastapi import Request  # noqa: E402


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/backtest")
async def backtest_page(request: Request):
    return templates.TemplateResponse(request, "backtest.html")


@app.get("/portfolio")
async def portfolio_page(request: Request):
    return templates.TemplateResponse(request, "portfolio.html")


@app.get("/risk")
async def risk_page(request: Request):
    return templates.TemplateResponse(request, "risk.html")
