"""回测 API"""
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from data.storage import DataStorage
from engine.backtest_engine import BacktestConfig, BacktestEngine
from strategy.dual_ma import DualMAStrategy
from strategy.bollinger import BollingerStrategy
from strategy.momentum import MomentumStrategy

router = APIRouter()

STRATEGIES = {
    "dual_ma": DualMAStrategy,
    "bollinger": BollingerStrategy,
    "momentum": MomentumStrategy,
}

storage = DataStorage()


class BacktestRequest(BaseModel):
    strategy: str = "dual_ma"
    codes: list[str] = ["000001"]
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    initial_cash: float = 1_000_000
    enable_risk: bool = False


class CompareRequest(BaseModel):
    strategies: list[str] = ["dual_ma", "bollinger", "momentum"]
    codes: list[str] = ["000001"]
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    initial_cash: float = 1_000_000


class BacktestResponse(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_cash: float = 0
    final_equity: float = 0
    total_return: float = 0
    annual_return: float = 0
    max_drawdown: float = 0
    sharpe_ratio: float = 0
    win_rate: float = 0
    total_trades: int = 0
    equity_curve: list[dict] = []
    trades: list[dict] = []
    risk_alerts: list[dict] = []


@router.post("/run", response_model=BacktestResponse)
async def run_backtest(req: BacktestRequest):
    """运行回测"""
    if req.strategy not in STRATEGIES:
        return BacktestResponse()

    config = BacktestConfig(
        initial_cash=req.initial_cash,
        enable_risk=req.enable_risk,
    )
    strategy = STRATEGIES[req.strategy]()
    engine = BacktestEngine(config=config)

    result = engine.run(strategy, req.codes, req.start_date, req.end_date)

    return BacktestResponse(
        start_date=str(result.start_date) if result.start_date else None,
        end_date=str(result.end_date) if result.end_date else None,
        initial_cash=result.initial_cash,
        final_equity=round(result.final_equity, 2),
        total_return=round(result.total_return, 4),
        annual_return=round(result.annual_return, 4),
        max_drawdown=round(result.max_drawdown, 4),
        sharpe_ratio=round(result.sharpe_ratio, 2),
        win_rate=round(result.win_rate, 4),
        total_trades=result.total_trades,
        equity_curve=[
            {"date": str(p["date"]), "equity": round(p["equity"], 2)}
            for p in result.equity_curve
        ],
        trades=[
            {
                "code": t.code,
                "direction": t.direction.value,
                "price": round(t.price, 2),
                "volume": t.volume,
                "datetime": str(t.datetime) if t.datetime else None,
                "entry_price": round(t.entry_price, 2),
            }
            for t in result.trades
        ],
        risk_alerts=[
            {
                "date": str(a.date),
                "level": a.level.value,
                "category": a.category,
                "message": a.message,
            }
            for a in result.risk_alerts
        ],
    )


@router.get("/strategies")
async def list_strategies():
    """列出可用策略"""
    return [
        {"name": "dual_ma", "label": "双均线策略", "type": "趋势"},
        {"name": "bollinger", "label": "布林带策略", "type": "均值回归"},
        {"name": "momentum", "label": "动量策略", "type": "趋势"},
    ]


@router.get("/stocks")
async def search_stocks(q: str = Query("", description="搜索关键词")):
    """搜索股票（从数据库）"""
    import pandas as pd
    try:
        df = storage.get_stock_list()
        if df.empty:
            return []
        if q:
            df = df[df["code"].str.contains(q) | df["name"].str.contains(q)]
        return df.head(50).to_dict("records")
    except Exception:
        return []


@router.post("/compare")
async def compare_strategies(req: CompareRequest):
    """多策略收益对比"""
    results = []
    for strategy_name in req.strategies:
        if strategy_name not in STRATEGIES:
            continue
        try:
            config = BacktestConfig(initial_cash=req.initial_cash)
            strategy = STRATEGIES[strategy_name]()
            engine = BacktestEngine(config=config)
            result = engine.run(strategy, req.codes, req.start_date, req.end_date)

            results.append({
                "strategy": strategy_name,
                "total_return": round(result.total_return, 4),
                "max_drawdown": round(result.max_drawdown, 4),
                "sharpe_ratio": round(result.sharpe_ratio, 2),
                "equity_curve": [
                    {"date": str(p["date"]), "equity": round(p["equity"], 2)}
                    for p in result.equity_curve
                ],
            })
        except Exception:
            continue
    return results


@router.post("/monthly-returns")
async def monthly_returns(req: BacktestRequest):
    """月度收益热力图数据"""
    if req.strategy not in STRATEGIES:
        return []

    config = BacktestConfig(initial_cash=req.initial_cash, enable_risk=req.enable_risk)
    strategy = STRATEGIES[req.strategy]()
    engine = BacktestEngine(config=config)
    result = engine.run(strategy, req.codes, req.start_date, req.end_date)

    if not result.equity_curve:
        return []

    # 按月计算收益
    monthly = {}
    for i, point in enumerate(result.equity_curve):
        d = point["date"]
        year = d.year
        month = d.month
        key = (year, month)
        if key not in monthly:
            monthly[key] = {"first": point["equity"], "last": point["equity"]}
        monthly[key]["last"] = point["equity"]

    output = []
    initial = result.initial_cash
    prev_equity = initial
    for (year, month), vals in sorted(monthly.items()):
        ret = (vals["last"] - prev_equity) / prev_equity if prev_equity > 0 else 0
        output.append({
            "year": year,
            "month": month,
            "return_pct": round(ret, 4),
        })
        prev_equity = vals["last"]

    return output


@router.post("/drawdown")
async def drawdown_curve(req: BacktestRequest):
    """回撤曲线数据"""
    if req.strategy not in STRATEGIES:
        return []

    config = BacktestConfig(initial_cash=req.initial_cash, enable_risk=req.enable_risk)
    strategy = STRATEGIES[req.strategy]()
    engine = BacktestEngine(config=config)
    result = engine.run(strategy, req.codes, req.start_date, req.end_date)

    if not result.equity_curve:
        return []

    output = []
    peak = result.equity_curve[0]["equity"]
    for point in result.equity_curve:
        equity = point["equity"]
        if equity > peak:
            peak = equity
        dd = (equity - peak) / peak if peak > 0 else 0
        output.append({
            "date": str(point["date"]),
            "drawdown_pct": round(dd, 4),
        })

    return output
