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
from engine.backtest_cache import get_backtest_cache
from engine.report_generator import generate_backtest_report
from strategy.strategies import STRATEGIES

router = APIRouter()

storage = DataStorage()
collector = StockCollector()


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
    period: str = "daily"  # daily / 1m / 5m / 15m / 30m / 60m


def _get_cached_backtest_result(req: BacktestRequest) -> dict:
    """获取缓存的回测结果（如果未命中则运行回测）

    Args:
        req: 回测请求参数

    Returns:
        回测结果字典
    """
    cache = get_backtest_cache()

    # 构建缓存 key 参数
    cache_params = {
        "strategy": req.strategy,
        "codes": req.codes,
        "start_date": req.start_date,
        "end_date": req.end_date,
        "initial_cash": req.initial_cash,
        "commission_rate": req.commission_rate,
        "stamp_tax_rate": req.stamp_tax_rate,
        "slippage": req.slippage,
        "enable_risk": req.enable_risk,
        "period": req.period,
    }

    def run_backtest():
        """运行回测并返回结果字典"""
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

        # 根据 period 选择引擎
        from engine.tick_engine import BarPeriod, TickBacktestEngine
        period = BarPeriod(req.period) if req.period != "daily" else BarPeriod.DAILY

        if period != BarPeriod.DAILY:
            engine = TickBacktestEngine(config=config)
            result = engine.run(
                strategy, req.codes, req.start_date, req.end_date,
                period=period, benchmark_code=req.benchmark,
            )
        else:
            engine = BacktestEngine(config=config)
            # 确保基准数据可用
            if req.benchmark:
                _ensure_benchmark_data(req.benchmark, req.start_date, req.end_date)
            result = engine.run(
                strategy, req.codes, req.start_date, req.end_date,
                benchmark_code=req.benchmark,
            )

        return {
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
            "period": req.period,
            "equity_curve": [
                {**{"date": str(p["date"]), "equity": round(p["equity"], 2)},
                 **({"datetime": p["datetime"]} if "datetime" in p else {})}
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
        }

    return cache.get_or_run(cache_params, run_backtest)


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
    period: str = "daily"
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

    # 根据 period 选择引擎
    from engine.tick_engine import BarPeriod, TickBacktestEngine
    period = BarPeriod(req.period) if req.period != "daily" else BarPeriod.DAILY

    if period != BarPeriod.DAILY:
        engine = TickBacktestEngine(config=config)
        result = engine.run(
            strategy, req.codes, req.start_date, req.end_date,
            period=period, benchmark_code=req.benchmark,
        )
    else:
        engine = BacktestEngine(config=config)
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
            {**{"date": str(p["date"]), "equity": round(p["equity"], 2)},
             **({"datetime": p["datetime"]} if "datetime" in p else {})}
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
        period=req.period,
    )


@router.get("/strategies")
async def list_strategies():
    """列出可用策略（动态查询 StrategyManager）"""
    from strategy.manager import StrategyManager
    manager = StrategyManager()
    strategies = manager.list_all()
    # 只返回 name, label, type 字段
    return [
        {
            "name": s["name"],
            "label": s.get("label", s["name"]),
            "type": s.get("type", "自定义"),
        }
        for s in strategies
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


class MonteCarloRequest(BaseModel):
    """蒙特卡洛模拟请求"""
    strategy: str = "dual_ma"
    codes: list[str] = ["000001"]
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    initial_cash: float = 100000
    commission_rate: float = 0.0003
    stamp_tax_rate: float = 0.001
    slippage: float = 0.002
    enable_risk: bool = False
    simulations: int = 1000


@router.post("/monte-carlo")
async def monte_carlo(req: MonteCarloRequest):
    """蒙特卡洛模拟（后端执行）"""
    from engine.backtest_engine import monte_carlo_simulation

    # 从缓存获取回测结果
    backtest_req = BacktestRequest(
        strategy=req.strategy,
        codes=req.codes,
        start_date=req.start_date,
        end_date=req.end_date,
        initial_cash=req.initial_cash,
        commission_rate=req.commission_rate,
        stamp_tax_rate=req.stamp_tax_rate,
        slippage=req.slippage,
        enable_risk=req.enable_risk,
    )
    result_data = _get_cached_backtest_result(backtest_req)

    if "error" in result_data and result_data["error"]:
        return {"error": result_data["error"]}

    trades = result_data.get("trades", [])
    if not trades:
        return {"error": "无交易记录"}

    # 运行蒙特卡洛模拟
    mc_result = monte_carlo_simulation(
        trades=trades,
        simulations=req.simulations,
    )

    return mc_result


class OutOfSampleRequest(BaseModel):
    """样本外测试请求"""
    strategy: str = "dual_ma"
    codes: list[str] = ["000001"]
    full_start_date: str = "2023-01-01"
    full_end_date: str = "2024-12-31"
    train_ratio: float = 0.7  # 训练集比例，默认 70%
    initial_cash: float = 100000
    commission_rate: float = 0.0003
    stamp_tax_rate: float = 0.001
    slippage: float = 0.002
    enable_risk: bool = False
    benchmark: str = ""


@router.post("/out-of-sample")
async def out_of_sample_test(req: OutOfSampleRequest):
    """样本外测试

    将数据按比例分割为训练集和测试集，分别运行回测，
    对比样本内和样本外表现，计算过拟合风险指标。
    """
    from datetime import datetime, timedelta

    if req.strategy not in STRATEGIES:
        return {"error": "未知策略"}

    # 计算分割日期
    full_start = datetime.strptime(req.full_start_date, "%Y-%m-%d")
    full_end = datetime.strptime(req.full_end_date, "%Y-%m-%d")
    total_days = (full_end - full_start).days
    train_days = int(total_days * req.train_ratio)

    train_end = full_start + timedelta(days=train_days)
    test_start = train_end + timedelta(days=1)

    train_start_str = req.full_start_date
    train_end_str = train_end.strftime("%Y-%m-%d")
    test_start_str = test_start.strftime("%Y-%m-%d")
    test_end_str = req.full_end_date

    # 运行训练集回测
    train_req = BacktestRequest(
        strategy=req.strategy,
        codes=req.codes,
        start_date=train_start_str,
        end_date=train_end_str,
        initial_cash=req.initial_cash,
        commission_rate=req.commission_rate,
        stamp_tax_rate=req.stamp_tax_rate,
        slippage=req.slippage,
        enable_risk=req.enable_risk,
        benchmark=req.benchmark,
    )
    train_result = _get_cached_backtest_result(train_req)

    if "error" in train_result and train_result["error"]:
        return {"error": f"训练集回测失败: {train_result['error']}"}

    # 运行测试集回测
    test_req = BacktestRequest(
        strategy=req.strategy,
        codes=req.codes,
        start_date=test_start_str,
        end_date=test_end_str,
        initial_cash=req.initial_cash,
        commission_rate=req.commission_rate,
        stamp_tax_rate=req.stamp_tax_rate,
        slippage=req.slippage,
        enable_risk=req.enable_risk,
        benchmark=req.benchmark,
    )
    test_result = _get_cached_backtest_result(test_req)

    if "error" in test_result and test_result["error"]:
        return {"error": f"测试集回测失败: {test_result['error']}"}

    # 计算过拟合风险指标
    train_sharpe = train_result.get("sharpe_ratio", 0)
    test_sharpe = test_result.get("sharpe_ratio", 0)
    train_return = train_result.get("total_return", 0)
    test_return = test_result.get("total_return", 0)

    # 夏普衰减比
    sharpe_decay = 0.0
    if train_sharpe > 0:
        sharpe_decay = (train_sharpe - test_sharpe) / train_sharpe

    # 收益衰减比
    return_decay = 0.0
    if train_return > 0:
        return_decay = (train_return - test_return) / train_return

    # 过拟合风险等级
    overfit_risk = "low"
    if sharpe_decay > 0.5:
        overfit_risk = "high"
    elif sharpe_decay > 0.3:
        overfit_risk = "medium"

    return {
        "in_sample": {
            "start_date": train_start_str,
            "end_date": train_end_str,
            "total_return": train_result.get("total_return"),
            "annual_return": train_result.get("annual_return"),
            "max_drawdown": train_result.get("max_drawdown"),
            "sharpe_ratio": train_result.get("sharpe_ratio"),
            "win_rate": train_result.get("win_rate"),
            "total_trades": train_result.get("total_trades"),
            "equity_curve": train_result.get("equity_curve", []),
        },
        "out_of_sample": {
            "start_date": test_start_str,
            "end_date": test_end_str,
            "total_return": test_result.get("total_return"),
            "annual_return": test_result.get("annual_return"),
            "max_drawdown": test_result.get("max_drawdown"),
            "sharpe_ratio": test_result.get("sharpe_ratio"),
            "win_rate": test_result.get("win_rate"),
            "total_trades": test_result.get("total_trades"),
            "equity_curve": test_result.get("equity_curve", []),
        },
        "comparison": {
            "train_ratio": req.train_ratio,
            "train_days": train_days,
            "test_days": total_days - train_days,
            "sharpe_decay": round(sharpe_decay, 4),
            "return_decay": round(return_decay, 4),
            "overfit_risk": overfit_risk,
        },
    }


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
    # 从缓存获取回测结果
    result_data = _get_cached_backtest_result(req)

    if "error" in result_data and result_data["error"]:
        return []

    equity_curve = result_data.get("equity_curve", [])
    if not equity_curve:
        return []

    # 按月计算收益
    monthly = {}
    for point in equity_curve:
        d = point["date"]
        # 解析日期字符串
        if isinstance(d, str):
            from datetime import datetime
            d = datetime.strptime(d, "%Y-%m-%d").date()
        year = d.year
        month = d.month
        key = (year, month)
        if key not in monthly:
            monthly[key] = {"first": point["equity"], "last": point["equity"]}
        monthly[key]["last"] = point["equity"]

    output = []
    initial = result_data.get("initial_cash", 100000)
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
    # 从缓存获取回测结果
    result_data = _get_cached_backtest_result(req)

    if "error" in result_data and result_data["error"]:
        return []

    equity_curve = result_data.get("equity_curve", [])
    if not equity_curve:
        return []

    output = []
    peak = equity_curve[0]["equity"]
    for point in equity_curve:
        equity = point["equity"]
        if equity > peak:
            peak = equity
        dd = (equity - peak) / peak if peak > 0 else 0
        output.append({
            "date": point["date"],
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


@router.post("/analysis/turnover")
async def analysis_turnover(req: BacktestRequest):
    """换手率分析（交易频率、成本影响）"""
    # 从缓存获取回测结果
    result_data = _get_cached_backtest_result(req)

    if "error" in result_data and result_data["error"]:
        return {"error": result_data["error"]}

    trades = result_data.get("trades", [])
    equity_curve = result_data.get("equity_curve", [])
    initial_cash = result_data.get("initial_cash", 100000)

    if not trades or not equity_curve:
        return {"error": "数据不足"}

    # 按日期统计交易
    from collections import defaultdict
    from datetime import datetime

    daily_turnover = defaultdict(float)  # date -> 交易金额
    total_buy_amount = 0.0
    total_sell_amount = 0.0

    for t in trades:
        trade_date = t.get("datetime", "")
        if isinstance(trade_date, str) and trade_date:
            # 只取日期部分
            date_str = trade_date[:10]
            amount = t["price"] * t["volume"]
            daily_turnover[date_str] += amount

            if t["direction"] == "long":
                total_buy_amount += amount
            else:
                total_sell_amount += amount

    # 计算日换手率序列
    turnover_series = []
    for point in equity_curve:
        date_str = point["date"]
        if isinstance(date_str, str):
            date_str = date_str[:10]
        equity = point["equity"]
        turnover = daily_turnover.get(date_str, 0)
        turnover_rate = turnover / equity if equity > 0 else 0
        turnover_series.append({
            "date": date_str,
            "turnover_rate": round(turnover_rate, 6),
            "turnover_amount": round(turnover, 2),
        })

    # 计算月度换手率
    monthly_turnover = defaultdict(float)
    monthly_equity = defaultdict(float)
    for item in turnover_series:
        month = item["date"][:7]  # YYYY-MM
        monthly_turnover[month] += item["turnover_amount"]
        # 使用月末权益
        monthly_equity[month] = item["turnover_amount"]

    monthly_stats = []
    for month in sorted(monthly_turnover.keys()):
        turnover = monthly_turnover[month]
        # 使用初始资金估算（实际应该用月末权益）
        turnover_rate = turnover / initial_cash
        monthly_stats.append({
            "month": month,
            "turnover": round(turnover, 2),
            "turnover_rate": round(turnover_rate, 4),
        })

    # 计算交易成本
    commission_rate = req.commission_rate or 0.0003
    stamp_tax_rate = req.stamp_tax_rate or 0.001
    slippage = req.slippage or 0.002

    total_commission = (total_buy_amount + total_sell_amount) * commission_rate
    total_stamp_tax = total_sell_amount * stamp_tax_rate
    total_slippage_cost = (total_buy_amount + total_sell_amount) * slippage
    total_cost = total_commission + total_stamp_tax + total_slippage_cost

    # 计算平均日换手率
    avg_daily_turnover = sum(d["turnover_rate"] for d in turnover_series) / len(turnover_series) if turnover_series else 0

    # 计算持仓天数（简化：交易天数 / 交易次数）
    trading_days = len(set(d["date"] for d in turnover_series if d["turnover_amount"] > 0))
    total_trades_count = len(trades)

    return {
        "turnover_series": turnover_series[-30:],  # 返回最近30天
        "monthly_stats": monthly_stats,
        "cost_breakdown": {
            "commission": round(total_commission, 2),
            "stamp_tax": round(total_stamp_tax, 2),
            "slippage": round(total_slippage_cost, 2),
            "total": round(total_cost, 2),
        },
        "summary": {
            "avg_daily_turnover": round(avg_daily_turnover, 6),
            "total_buy_amount": round(total_buy_amount, 2),
            "total_sell_amount": round(total_sell_amount, 2),
            "total_trades": total_trades_count,
            "trading_days": trading_days,
            "cost_drag": round(total_cost / initial_cash, 4),
        },
    }


@router.post("/analysis/holding-period")
async def analysis_holding_period(req: BacktestRequest):
    """持仓周期分析（持有天数分布、盈亏与持仓时长关系）"""
    result_data = _get_cached_backtest_result(req)

    if "error" in result_data and result_data["error"]:
        return {"error": result_data["error"]}

    trades = result_data.get("trades", [])

    if not trades:
        return {"error": "无交易记录"}

    from collections import defaultdict
    from datetime import datetime

    # 配对买卖交易，计算持仓天数
    # 按股票代码分组
    trades_by_code = defaultdict(list)
    for t in trades:
        trades_by_code[t["code"]].append(t)

    holding_periods = []  # [{code, entry_date, exit_date, days, pnl_pct, direction}]

    for code, code_trades in trades_by_code.items():
        # 按时间排序
        sorted_trades = sorted(code_trades, key=lambda x: x.get("datetime", ""))
        entry_price = None
        entry_date = None

        for t in sorted_trades:
            if t["direction"] == "long":
                entry_price = t["price"]
                entry_date_str = t.get("datetime", "")
                if isinstance(entry_date_str, str) and len(entry_date_str) >= 10:
                    entry_date = entry_date_str[:10]
            elif t["direction"] == "short" and entry_price is not None:
                exit_date_str = t.get("datetime", "")
                exit_date = exit_date_str[:10] if isinstance(exit_date_str, str) and len(exit_date_str) >= 10 else ""

                # 计算持仓天数
                if entry_date and exit_date:
                    try:
                        d1 = datetime.strptime(entry_date, "%Y-%m-%d")
                        d2 = datetime.strptime(exit_date, "%Y-%m-%d")
                        days = (d2 - d1).days
                    except ValueError:
                        days = 0
                else:
                    days = 0

                # 计算盈亏
                pnl_pct = (t["price"] - entry_price) / entry_price if entry_price > 0 else 0

                holding_periods.append({
                    "code": code,
                    "entry_date": entry_date,
                    "exit_date": exit_date,
                    "days": max(days, 0),
                    "entry_price": round(entry_price, 4),
                    "exit_price": round(t["price"], 4),
                    "pnl_pct": round(pnl_pct, 4),
                })
                entry_price = None
                entry_date = None

    if not holding_periods:
        return {"error": "无完整持仓周期"}

    # 持仓天数分布
    days_list = [h["days"] for h in holding_periods]
    bins = [0, 3, 7, 14, 30, 60, 90, 180, 365, 9999]
    bin_labels = ["1-3天", "4-7天", "8-14天", "15-30天", "31-60天", "61-90天", "91-180天", "181-365天", ">365天"]
    dist_counts = [0] * len(bin_labels)

    for d in days_list:
        for i in range(len(bins) - 1):
            if bins[i] <= d < bins[i + 1]:
                dist_counts[i] += 1
                break

    # 按持仓时长分组统计盈亏
    period_pnl = defaultdict(list)
    for h in holding_periods:
        if h["days"] <= 3:
            period_pnl["1-3天"].append(h["pnl_pct"])
        elif h["days"] <= 7:
            period_pnl["4-7天"].append(h["pnl_pct"])
        elif h["days"] <= 14:
            period_pnl["8-14天"].append(h["pnl_pct"])
        elif h["days"] <= 30:
            period_pnl["15-30天"].append(h["pnl_pct"])
        elif h["days"] <= 60:
            period_pnl["31-60天"].append(h["pnl_pct"])
        elif h["days"] <= 90:
            period_pnl["61-90天"].append(h["pnl_pct"])
        elif h["days"] <= 180:
            period_pnl["91-180天"].append(h["pnl_pct"])
        else:
            period_pnl[">180天"].append(h["pnl_pct"])

    pnl_by_period = []
    for label in ["1-3天", "4-7天", "8-14天", "15-30天", "31-60天", "61-90天", "91-180天", ">180天"]:
        pnls = period_pnl.get(label, [])
        if pnls:
            avg_pnl = sum(pnls) / len(pnls)
            win_count = sum(1 for p in pnls if p > 0)
            pnl_by_period.append({
                "period": label,
                "count": len(pnls),
                "avg_pnl": round(avg_pnl * 100, 2),
                "win_rate": round(win_count / len(pnls) * 100, 1),
            })

    # 统计
    avg_days = sum(days_list) / len(days_list) if days_list else 0
    median_days = sorted(days_list)[len(days_list) // 2] if days_list else 0
    win_trades = [h for h in holding_periods if h["pnl_pct"] > 0]
    loss_trades = [h for h in holding_periods if h["pnl_pct"] <= 0]
    avg_win_days = sum(h["days"] for h in win_trades) / len(win_trades) if win_trades else 0
    avg_loss_days = sum(h["days"] for h in loss_trades) / len(loss_trades) if loss_trades else 0

    return {
        "distribution": {
            "labels": bin_labels,
            "counts": dist_counts,
        },
        "pnl_by_period": pnl_by_period,
        "summary": {
            "total_round_trips": len(holding_periods),
            "avg_holding_days": round(avg_days, 1),
            "median_holding_days": median_days,
            "max_holding_days": max(days_list) if days_list else 0,
            "min_holding_days": min(days_list) if days_list else 0,
            "avg_win_days": round(avg_win_days, 1),
            "avg_loss_days": round(avg_loss_days, 1),
        },
    }


@router.post("/analysis/attribution")
async def analysis_attribution(req: BacktestRequest):
    """绩效归因分析（Brinson 模型）"""
    result_data = _get_cached_backtest_result(req)

    if "error" in result_data and result_data["error"]:
        return {"error": result_data["error"]}

    trades = result_data.get("trades", [])
    equity_curve = result_data.get("equity_curve", [])
    initial_cash = result_data.get("initial_cash", 100000)

    if not trades:
        return {"error": "无交易记录"}

    # 获取股票行业映射
    try:
        storage_inst = DataStorage()
        stock_df = storage_inst.get_stock_list()
        sector_map = {}
        if stock_df is not None and not stock_df.empty:
            for _, row in stock_df.iterrows():
                sector_map[row.get("code", "")] = row.get("industry", "其他") or "其他"
    except Exception:
        sector_map = {}

    # 获取基准数据
    benchmark_data = []
    if req.benchmark:
        try:
            from datetime import datetime as dt
            bm_start = dt.strptime(req.start_date, "%Y-%m-%d").date() if req.start_date else None
            bm_end = dt.strptime(req.end_date, "%Y-%m-%d").date() if req.end_date else None
            bm_df = storage_inst.get_stock_daily(req.benchmark, bm_start, bm_end)
            if bm_df is not None and not bm_df.empty:
                benchmark_data = bm_df[["date", "close"]].to_dict("records")
                for d in benchmark_data:
                    if hasattr(d["date"], "strftime"):
                        d["date"] = d["date"].strftime("%Y-%m-%d")
        except Exception:
            pass

    from engine.attribution import brinson_attribution

    result = brinson_attribution(
        portfolio_trades=trades,
        portfolio_equity_curve=equity_curve,
        benchmark_data=benchmark_data,
        sector_map=sector_map,
        initial_cash=initial_cash,
    )

    if result.error:
        return {"error": result.error}

    return {
        "sectors": [
            {
                "sector": s.sector,
                "portfolio_weight": s.portfolio_weight,
                "benchmark_weight": s.benchmark_weight,
                "portfolio_return": s.portfolio_return,
                "benchmark_return": s.benchmark_return,
                "allocation_effect": s.allocation_effect,
                "selection_effect": s.selection_effect,
                "interaction_effect": s.interaction_effect,
                "total_effect": s.total_effect,
            }
            for s in result.sectors
        ],
        "summary": {
            "total_allocation": result.total_allocation,
            "total_selection": result.total_selection,
            "total_interaction": result.total_interaction,
            "total_excess_return": result.total_excess_return,
        },
    }


@router.get("/periods")
async def get_periods():
    """获取支持的回测周期列表"""
    return {
        "periods": [
            {"value": "daily", "label": "日线", "description": "传统日K线回测"},
            {"value": "1m", "label": "1分钟", "description": "分钟级高频回测（需要分钟线数据）"},
            {"value": "5m", "label": "5分钟", "description": "5分钟K线回测"},
            {"value": "15m", "label": "15分钟", "description": "15分钟K线回测"},
            {"value": "30m", "label": "30分钟", "description": "30分钟K线回测"},
            {"value": "60m", "label": "60分钟", "description": "60分钟K线回测"},
        ]
    }


@router.get("/tick-info")
async def get_tick_info(code: str = Query(..., description="股票代码")):
    """获取某股票的 Tick/分钟线数据可用性"""
    try:
        from data.storage.tick_storage import TickStorage
        tick_storage = TickStorage()
        info = tick_storage.get_data_range(code)
        return {
            "code": code,
            "tick_data": info.get("tick", {}),
            "minute_data": info.get("minute", {}),
            "has_tick_data": (info.get("tick", {}).get("count", 0)) > 0,
            "has_minute_data": (info.get("minute", {}).get("count", 0)) > 0,
        }
    except Exception as e:
        return {
            "code": code,
            "tick_data": {"start": None, "end": None, "count": 0},
            "minute_data": {"start": None, "end": None, "count": 0},
            "has_tick_data": False,
            "has_minute_data": False,
            "error": str(e),
        }


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

        # 根据 period 选择引擎
        from engine.tick_engine import BarPeriod, TickBacktestEngine
        period_str = req.get("period", "daily")
        period = BarPeriod(period_str) if period_str != "daily" else BarPeriod.DAILY

        if period != BarPeriod.DAILY:
            engine = TickBacktestEngine(config=config)
        else:
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
                asyncio.get_running_loop().create_task(ws.send_json({
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

        # 取消支持
        cancelled = {"flag": False}

        async def _listen_cancel():
            """监听客户端取消消息"""
            try:
                while True:
                    msg = await ws.receive_text()
                    data = json.loads(msg)
                    if data.get("type") == "cancel":
                        cancelled["flag"] = True
                        logger.info("回测取消请求已收到")
                        break
            except Exception:
                pass

        cancel_task = asyncio.create_task(_listen_cancel())

        def on_progress_cancellable(progress, current_date, day_idx, total):
            if cancelled["flag"]:
                raise InterruptedError("用户取消回测")
            on_progress(progress, current_date, day_idx, total)

        # 在线程中运行回测
        loop = asyncio.get_running_loop()
        try:
            def _run():
                if period != BarPeriod.DAILY:
                    return engine.run(
                        strategy, req.get("codes", ["000001"]),
                        req["start_date"], req["end_date"],
                        period=period, benchmark_code=benchmark,
                        progress_callback=on_progress_cancellable,
                    )
                else:
                    return engine.run(
                        strategy, req.get("codes", ["000001"]),
                        req["start_date"], req["end_date"],
                        benchmark_code=benchmark,
                        progress_callback=on_progress_cancellable,
                    )

            result = await loop.run_in_executor(None, _run)
        except (InterruptedError, Exception) as e:
            cancel_task.cancel()
            if cancelled["flag"]:
                await ws.send_json({"type": "cancelled", "message": "回测已取消"})
                await ws.close()
                return
            raise
        finally:
            cancel_task.cancel()

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
                "period": req.get("period", "daily"),
                "equity_curve": [
                    {**{"date": str(p["date"]), "equity": round(p["equity"], 2)},
                     **({"datetime": p["datetime"]} if "datetime" in p else {})}
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
    # 从缓存获取回测结果
    result_data = _get_cached_backtest_result(req)

    if "error" in result_data and result_data["error"]:
        return {"error": result_data["error"]}

    equity_curve = result_data.get("equity_curve", [])
    if not equity_curve or len(equity_curve) < 2:
        return {"error": "数据不足"}

    equities = [p["equity"] for p in equity_curve]
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
    # 从缓存获取回测结果
    result_data = _get_cached_backtest_result(req)

    if "error" in result_data and result_data["error"]:
        return {"error": result_data["error"]}

    trades = result_data.get("trades", [])
    sell_trades = [t for t in trades if t["direction"] == "short"]
    if not sell_trades:
        return {"trades": [], "stats": {}}

    pnl_list = []
    holding_days_list = []
    for t in sell_trades:
        entry_price = t.get("entry_price", 0)
        if entry_price > 0:
            pnl_pct = (t["price"] - entry_price) / entry_price * 100
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
    # 从缓存获取回测结果
    result_data = _get_cached_backtest_result(req)

    if "error" in result_data and result_data["error"]:
        return {"error": result_data["error"]}

    equity_curve = result_data.get("equity_curve", [])
    if not equity_curve or len(equity_curve) < 2:
        return {"error": "数据不足"}

    # 按星期几分组计算日收益
    weekday_returns = {i: [] for i in range(5)}  # 0=周一 ... 4=周五
    for i in range(1, len(equity_curve)):
        d = equity_curve[i]["date"]
        # 解析日期字符串
        if isinstance(d, str):
            from datetime import datetime
            d = datetime.strptime(d, "%Y-%m-%d").date()
        wd = d.weekday()
        if wd < 5:
            ret = (equity_curve[i]["equity"] - equity_curve[i - 1]["equity"]) / equity_curve[i - 1]["equity"]
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


@router.post("/report/pdf")
async def generate_report_pdf(req: BacktestRequest):
    """生成回测 PDF 报告"""
    if req.strategy not in STRATEGIES:
        return {"error": "未知策略"}

    strategy_cls = STRATEGIES[req.strategy]
    strategy = strategy_cls()

    config = BacktestConfig(
        initial_cash=req.initial_cash,
        commission_rate=req.commission_rate,
        stamp_tax_rate=req.stamp_tax_rate,
        slippage=req.slippage,
        enable_risk=req.enable_risk,
    )
    if req.benchmark:
        _ensure_benchmark_data(req.benchmark, req.start_date, req.end_date)
        config.benchmark_code = req.benchmark

    engine = BacktestEngine(config=config)
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, lambda: engine.run(strategy, req.codes, req.start_date, req.end_date)
    )

    # 构建报告数据
    report_data = {
        "strategy": req.strategy,
        "codes": req.codes,
        "start_date": req.start_date,
        "end_date": req.end_date,
        "initial_cash": req.initial_cash,
        "commission_rate": req.commission_rate,
        "stamp_tax_rate": req.stamp_tax_rate,
        "slippage": req.slippage,
        "benchmark": req.benchmark or "None",
        "total_return": result.total_return,
        "annual_return": result.annual_return,
        "sharpe_ratio": result.sharpe_ratio,
        "sortino_ratio": result.sortino_ratio,
        "max_drawdown": result.max_drawdown,
        "calmar_ratio": result.calmar_ratio,
        "win_rate": result.win_rate,
        "profit_loss_ratio": result.profit_loss_ratio,
        "alpha": result.alpha,
        "beta": result.beta,
        "information_ratio": result.information_ratio,
        "total_trades": result.total_trades,
        "max_consecutive_wins": result.max_consecutive_wins,
        "max_consecutive_losses": result.max_consecutive_losses,
        "trades": [t.__dict__ if hasattr(t, '__dict__') else t for t in result.trades],
        "risk_alerts": result.risk_alerts if hasattr(result, 'risk_alerts') else [],
    }

    pdf_bytes = generate_backtest_report(report_data)

    from fastapi.responses import Response
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=backtest_report.pdf"},
    )


class WalkForwardRequest(BaseModel):
    """Walk-Forward Analysis 请求"""
    strategy: str = "dual_ma"
    codes: list[str] = ["000001"]
    start_date: str = "2023-01-01"
    end_date: str = "2024-12-31"
    train_window: int = 252  # 训练窗口（交易日），默认约1年
    test_window: int = 63    # 测试窗口（交易日），默认约3个月
    n_splits: int = 4        # 分割次数
    optimize_method: str = "optuna"  # 优化方法
    n_trials: int = 30       # 每个窗口的优化试验次数
    metric: str = "sharpe_ratio"
    initial_cash: float = 100000
    commission_rate: float = 0.0003
    stamp_tax_rate: float = 0.001
    slippage: float = 0.002


@router.websocket("/ws/walk-forward")
async def ws_walk_forward(ws: WebSocket):
    """WebSocket Walk-Forward Analysis（带实时进度推送）"""
    await ws.accept()
    try:
        raw = await ws.receive_text()
        req = json.loads(raw)

        strategy_name = req.get("strategy", "dual_ma")
        if strategy_name not in STRATEGIES:
            await ws.send_json({"type": "error", "message": f"未知策略: {strategy_name}"})
            await ws.close()
            return

        from engine.walk_forward import run_walk_forward
        from engine.optimization_engine import STRATEGY_PARAM_RANGES

        strategy_cls = STRATEGIES[strategy_name]
        param_ranges = STRATEGY_PARAM_RANGES.get(strategy_name, {})

        config = BacktestConfig(
            initial_cash=req.get("initial_cash", 100000),
            commission_rate=req.get("commission_rate", 0.0003),
            stamp_tax_rate=req.get("stamp_tax_rate", 0.001),
            slippage=req.get("slippage", 0.002),
        )

        def on_progress(progress):
            try:
                asyncio.get_running_loop().create_task(ws.send_json({
                    "type": "progress",
                    "progress": round(progress, 4),
                }))
            except Exception:
                pass

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, lambda: run_walk_forward(
            strategy_name=strategy_name,
            strategy_cls=strategy_cls,
            param_ranges=param_ranges,
            codes=req.get("codes", ["000001"]),
            start_date=req["start_date"],
            end_date=req["end_date"],
            train_window=req.get("train_window", 252),
            test_window=req.get("test_window", 63),
            n_splits=req.get("n_splits", 4),
            optimize_method=req.get("optimize_method", "optuna"),
            n_trials=req.get("n_trials", 30),
            metric=req.get("metric", "sharpe_ratio"),
            config=config,
            progress_callback=on_progress,
        ))

        # 发送最终结果
        await ws.send_json({
            "type": "complete",
            "data": {
                "windows": [
                    {
                        "window_index": w.window_index,
                        "train_start": w.train_start,
                        "train_end": w.train_end,
                        "test_start": w.test_start,
                        "test_end": w.test_end,
                        "best_params": w.best_params,
                        "train_sharpe": w.train_sharpe,
                        "test_sharpe": w.test_sharpe,
                        "test_return": w.test_return,
                        "test_max_drawdown": w.test_max_drawdown,
                        "test_total_trades": w.test_total_trades,
                    }
                    for w in result.windows
                ],
                "oos_equity_curve": result.oos_equity_curve,
                "oos_total_return": result.oos_total_return,
                "oos_sharpe_ratio": result.oos_sharpe_ratio,
                "oos_max_drawdown": result.oos_max_drawdown,
                "oos_win_rate": result.oos_win_rate,
                "oos_total_trades": result.oos_total_trades,
                "stability_score": result.stability_score,
                "param_stability": result.param_stability,
                "error": result.error,
            },
        })
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Walk-Forward WebSocket异常: {e}")
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass
