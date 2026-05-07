"""回测 API"""
import asyncio
import json
import time
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from loguru import logger
from pydantic import BaseModel

from data.storage import DataStorage
from data.collector.collector import StockCollector
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
collector = StockCollector()


def _ensure_benchmark_data(benchmark_code: str, start_date: str, end_date: str):
    """确保基准指数数据已入库，没有则自动采集"""
    import pandas as pd
    from datetime import date
    start = pd.Timestamp(start_date).date()
    end = pd.Timestamp(end_date).date()
    existing = storage.get_stock_daily(benchmark_code, start, end)
    if not existing.empty and len(existing) >= 10:
        return
    try:
        logger.info(f"采集基准数据: {benchmark_code}")
        df = collector.get_index_daily(benchmark_code, start_date.replace("-", ""), end_date.replace("-", ""))
        if not df.empty:
            storage.save_stock_daily(benchmark_code, df)
    except Exception as e:
        logger.warning(f"基准数据采集失败: {e}")


class BacktestRequest(BaseModel):
    strategy: str = "dual_ma"
    codes: list[str] = ["000001"]
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    initial_cash: float = 1_000_000
    commission_rate: float = 0.0003
    stamp_tax_rate: float = 0.001
    slippage: float = 0.002
    benchmark: str = ""
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
    sortino_ratio: float = 0
    calmar_ratio: float = 0
    information_ratio: float = 0
    alpha: float = 0
    beta: float = 0
    win_rate: float = 0
    profit_loss_ratio: float = 0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    total_trades: int = 0
    equity_curve: list[dict] = []
    benchmark_curve: list[dict] = []
    trades: list[dict] = []
    risk_alerts: list[dict] = []
    warmup_days: int = 0
    error: Optional[str] = None


@router.post("/run", response_model=BacktestResponse)
async def run_backtest(req: BacktestRequest):
    """运行回测"""
    if req.strategy not in STRATEGIES:
        return BacktestResponse()

    config = BacktestConfig(
        initial_cash=req.initial_cash,
        commission_rate=req.commission_rate,
        stamp_tax_rate=req.stamp_tax_rate,
        slippage=req.slippage,
        enable_risk=req.enable_risk,
    )
    strategy = STRATEGIES[req.strategy]()
    engine = BacktestEngine(config=config)

    # 确保基准数据可用
    if req.benchmark:
        _ensure_benchmark_data(req.benchmark, req.start_date, req.end_date)

    result = engine.run(
        strategy, req.codes, req.start_date, req.end_date,
        benchmark_code=req.benchmark,
    )

    return BacktestResponse(
        start_date=str(result.start_date) if result.start_date else None,
        end_date=str(result.end_date) if result.end_date else None,
        initial_cash=result.initial_cash,
        final_equity=round(result.final_equity, 2),
        total_return=round(result.total_return, 4),
        annual_return=round(result.annual_return, 4),
        max_drawdown=round(result.max_drawdown, 4),
        sharpe_ratio=round(result.sharpe_ratio, 2),
        sortino_ratio=round(result.sortino_ratio, 2),
        calmar_ratio=round(result.calmar_ratio, 2),
        information_ratio=round(result.information_ratio, 2),
        alpha=round(result.alpha, 4),
        beta=round(result.beta, 4),
        win_rate=round(result.win_rate, 4),
        profit_loss_ratio=round(result.profit_loss_ratio, 2),
        max_consecutive_wins=result.max_consecutive_wins,
        max_consecutive_losses=result.max_consecutive_losses,
        total_trades=result.total_trades,
        equity_curve=[
            {"date": str(p["date"]), "equity": round(p["equity"], 2)}
            for p in result.equity_curve
        ],
        benchmark_curve=[
            {"date": str(p["date"]), "equity": round(p["equity"], 4)}
            for p in result.benchmark_curve
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
        warmup_days=result.warmup_days,
        error=result.error,
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
            df = df[df["code"].str.contains(q, na=False) | df["name"].str.contains(q, na=False)]
        return df.to_dict("records")
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


@router.get("/benchmarks")
async def list_benchmarks():
    """列出可用基准指数"""
    return [
        {"code": "sh000300", "name": "沪深300"},
        {"code": "sh000905", "name": "中证500"},
        {"code": "sh000016", "name": "上证50"},
        {"code": "sz399006", "name": "创业板指"},
        {"code": "sz399303", "name": "国证2000"},
    ]


@router.websocket("/ws/run")
async def ws_backtest(ws: WebSocket):
    """WebSocket 回测（带实时进度推送）"""
    await ws.accept()
    try:
        raw = await ws.receive_text()
        req = json.loads(raw)

        strategy_name = req.get("strategy", "dual_ma")
        if strategy_name not in STRATEGIES:
            await ws.send_json({"type": "error", "message": f"未知策略: {strategy_name}"})
            await ws.close()
            return

        config = BacktestConfig(
            initial_cash=req.get("initial_cash", 100000),
            commission_rate=req.get("commission_rate", 0.0003),
            stamp_tax_rate=req.get("stamp_tax_rate", 0.001),
            slippage=req.get("slippage", 0.002),
            enable_risk=req.get("enable_risk", False),
        )
        strategy = STRATEGIES[strategy_name]()
        engine = BacktestEngine(config=config)

        benchmark = req.get("benchmark", "")
        if benchmark:
            _ensure_benchmark_data(benchmark, req["start_date"], req["end_date"])

        start_time = time.time()
        total_days = [0]

        def on_progress(progress, current_date, day_idx, total):
            total_days[0] = total
            elapsed = time.time() - start_time
            remaining = (elapsed / progress - elapsed) if progress > 0 else 0
            try:
                asyncio.get_event_loop().create_task(ws.send_json({
                    "type": "progress",
                    "progress": round(progress, 4),
                    "current_date": current_date,
                    "day_index": day_idx,
                    "total_days": total,
                    "elapsed": round(elapsed, 1),
                    "remaining": round(remaining, 1),
                }))
            except Exception:
                pass

        # 在线程中运行回测
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: engine.run(
            strategy, req.get("codes", ["000001"]),
            req["start_date"], req["end_date"],
            benchmark_code=benchmark,
            progress_callback=on_progress,
        ))

        # 发送最终结果
        await ws.send_json({
            "type": "complete",
            "data": {
                "start_date": str(result.start_date) if result.start_date else None,
                "end_date": str(result.end_date) if result.end_date else None,
                "initial_cash": result.initial_cash,
                "final_equity": round(result.final_equity, 2),
                "total_return": round(result.total_return, 4),
                "annual_return": round(result.annual_return, 4),
                "max_drawdown": round(result.max_drawdown, 4),
                "sharpe_ratio": round(result.sharpe_ratio, 2),
                "sortino_ratio": round(result.sortino_ratio, 2),
                "calmar_ratio": round(result.calmar_ratio, 2),
                "information_ratio": round(result.information_ratio, 2),
                "alpha": round(result.alpha, 4),
                "beta": round(result.beta, 4),
                "win_rate": round(result.win_rate, 4),
                "profit_loss_ratio": round(result.profit_loss_ratio, 2),
                "max_consecutive_wins": result.max_consecutive_wins,
                "max_consecutive_losses": result.max_consecutive_losses,
                "total_trades": result.total_trades,
                "equity_curve": [
                    {"date": str(p["date"]), "equity": round(p["equity"], 2)}
                    for p in result.equity_curve
                ],
                "benchmark_curve": [
                    {"date": str(p["date"]), "equity": round(p["equity"], 4)}
                    for p in result.benchmark_curve
                ],
                "trades": [
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
                "risk_alerts": [
                    {
                        "date": str(a.date),
                        "level": a.level.value,
                        "category": a.category,
                        "message": a.message,
                    }
                    for a in result.risk_alerts
                ],
                "warmup_days": result.warmup_days,
                "error": result.error,
            },
        })
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket回测异常: {e}")
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass


@router.post("/analysis/returns")
async def analysis_returns(req: BacktestRequest):
    """收益分布分析（直方图、偏度、峰度）"""
    if req.strategy not in STRATEGIES:
        return {"error": "未知策略"}

    config = BacktestConfig(
        initial_cash=req.initial_cash,
        commission_rate=req.commission_rate,
        stamp_tax_rate=req.stamp_tax_rate,
        slippage=req.slippage,
        enable_risk=req.enable_risk,
    )
    strategy = STRATEGIES[req.strategy]()
    engine = BacktestEngine(config=config)
    result = engine.run(strategy, req.codes, req.start_date, req.end_date)

    if not result.equity_curve or len(result.equity_curve) < 2:
        return {"error": "数据不足"}

    equities = [p["equity"] for p in result.equity_curve]
    daily_returns = [(equities[i] - equities[i - 1]) / equities[i - 1] for i in range(1, len(equities))]

    if not daily_returns:
        return {"error": "无日收益率数据"}

    n = len(daily_returns)
    mean = sum(daily_returns) / n
    variance = sum((r - mean) ** 2 for r in daily_returns) / n
    std = variance ** 0.5

    # 偏度
    skewness = sum((r - mean) ** 3 for r in daily_returns) / (n * std ** 3) if std > 0 else 0
    # 峰度
    kurtosis = sum((r - mean) ** 4 for r in daily_returns) / (n * std ** 4) - 3 if std > 0 else 0

    # 直方图分桶
    min_r = min(daily_returns)
    max_r = max(daily_returns)
    bin_count = min(30, max(10, n // 10))
    bin_width = (max_r - min_r) / bin_count if max_r > min_r else 0.001
    bins = []
    counts = []
    for i in range(bin_count):
        lo = min_r + i * bin_width
        hi = lo + bin_width
        count = sum(1 for r in daily_returns if lo <= r < hi)
        bins.append(round((lo + hi) / 2 * 100, 3))  # 百分比
        counts.append(count)

    return {
        "histogram": {"bins": bins, "counts": counts},
        "stats": {
            "mean": round(mean * 100, 4),
            "std": round(std * 100, 4),
            "skewness": round(skewness, 4),
            "kurtosis": round(kurtosis, 4),
            "min": round(min_r * 100, 4),
            "max": round(max_r * 100, 4),
            "positive_days": sum(1 for r in daily_returns if r > 0),
            "negative_days": sum(1 for r in daily_returns if r < 0),
        },
    }


@router.post("/analysis/trades")
async def analysis_trades(req: BacktestRequest):
    """交易分析（盈亏分布、持仓时间、连续盈亏）"""
    if req.strategy not in STRATEGIES:
        return {"error": "未知策略"}

    config = BacktestConfig(
        initial_cash=req.initial_cash,
        commission_rate=req.commission_rate,
        stamp_tax_rate=req.stamp_tax_rate,
        slippage=req.slippage,
        enable_risk=req.enable_risk,
    )
    strategy = STRATEGIES[req.strategy]()
    engine = BacktestEngine(config=config)
    result = engine.run(strategy, req.codes, req.start_date, req.end_date)

    sell_trades = [t for t in result.trades if t.direction.value == "short"]
    if not sell_trades:
        return {"trades": [], "stats": {}}

    pnl_list = []
    holding_days_list = []
    for t in sell_trades:
        if t.entry_price > 0:
            pnl_pct = (t.price - t.entry_price) / t.entry_price * 100
            pnl_list.append(round(pnl_pct, 4))
            # 简单估算持仓天数（如果有entry_date信息可用，否则跳过）

    # 盈亏分布直方图
    if pnl_list:
        min_pnl = min(pnl_list)
        max_pnl = max(pnl_list)
        bin_count = min(20, max(5, len(pnl_list) // 3))
        bin_width = (max_pnl - min_pnl) / bin_count if max_pnl > min_pnl else 0.5
        pnl_bins = []
        pnl_counts = []
        for i in range(bin_count):
            lo = min_pnl + i * bin_width
            hi = lo + bin_width
            count = sum(1 for p in pnl_list if lo <= p < hi)
            pnl_bins.append(round((lo + hi) / 2, 2))
            pnl_counts.append(count)
    else:
        pnl_bins, pnl_counts = [], []

    # 连续盈亏统计
    streaks_w, streaks_l = [], []
    cur_w, cur_l = 0, 0
    for p in pnl_list:
        if p > 0:
            cur_w += 1
            if cur_l > 0:
                streaks_l.append(cur_l)
            cur_l = 0
        else:
            cur_l += 1
            if cur_w > 0:
                streaks_w.append(cur_w)
            cur_w = 0
    if cur_w > 0:
        streaks_w.append(cur_w)
    if cur_l > 0:
        streaks_l.append(cur_l)

    return {
        "pnl_distribution": {"bins": pnl_bins, "counts": pnl_counts},
        "pnl_list": pnl_list,
        "stats": {
            "total_trades": len(sell_trades),
            "win_count": sum(1 for p in pnl_list if p > 0),
            "loss_count": sum(1 for p in pnl_list if p <= 0),
            "avg_win": round(sum(p for p in pnl_list if p > 0) / max(1, sum(1 for p in pnl_list if p > 0)), 2),
            "avg_loss": round(sum(p for p in pnl_list if p <= 0) / max(1, sum(1 for p in pnl_list if p <= 0)), 2),
            "max_win": round(max(pnl_list), 2) if pnl_list else 0,
            "max_loss": round(min(pnl_list), 2) if pnl_list else 0,
            "max_consecutive_wins": max(streaks_w) if streaks_w else 0,
            "max_consecutive_losses": max(streaks_l) if streaks_l else 0,
        },
    }


@router.post("/analysis/weekday")
async def analysis_weekday(req: BacktestRequest):
    """星期几效应分析"""
    if req.strategy not in STRATEGIES:
        return {"error": "未知策略"}

    config = BacktestConfig(
        initial_cash=req.initial_cash,
        commission_rate=req.commission_rate,
        stamp_tax_rate=req.stamp_tax_rate,
        slippage=req.slippage,
        enable_risk=req.enable_risk,
    )
    strategy = STRATEGIES[req.strategy]()
    engine = BacktestEngine(config=config)
    result = engine.run(strategy, req.codes, req.start_date, req.end_date)

    if not result.equity_curve or len(result.equity_curve) < 2:
        return {"error": "数据不足"}

    # 按星期几分组计算日收益
    weekday_returns = {i: [] for i in range(5)}  # 0=周一 ... 4=周五
    equities = result.equity_curve
    for i in range(1, len(equities)):
        d = equities[i]["date"]
        wd = d.weekday()
        if wd < 5:
            ret = (equities[i]["equity"] - equities[i - 1]["equity"]) / equities[i - 1]["equity"]
            weekday_returns[wd].append(ret)

    labels = ["周一", "周二", "周三", "周四", "周五"]
    avg_returns = []
    for wd in range(5):
        rets = weekday_returns[wd]
        avg = sum(rets) / len(rets) * 100 if rets else 0
        avg_returns.append(round(avg, 4))

    return {
        "labels": labels,
        "avg_returns": avg_returns,
        "counts": [len(weekday_returns[i]) for i in range(5)],
    }
