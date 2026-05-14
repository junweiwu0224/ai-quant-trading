"""回测指标计算工具模块"""
from collections import defaultdict
from typing import Optional

from strategy.base import Direction, Trade


def calc_monthly_returns(equity_curve: list[dict]) -> dict[str, float]:
    """计算月度收益率"""
    if not equity_curve:
        return {}
    monthly = {}
    for point in equity_curve:
        d = point["date"]
        key = d.strftime("%Y-%m") if hasattr(d, "strftime") else str(d)[:7]
        if key not in monthly:
            monthly[key] = {"first": point["equity"], "last": point["equity"]}
        monthly[key]["last"] = point["equity"]
    return {
        k: round((v["last"] - v["first"]) / v["first"], 4) if v["first"] > 0 else 0.0
        for k, v in monthly.items()
    }


def calc_rolling_sharpe(equity_curve: list[dict], window: int = 60) -> list[dict]:
    """计算滚动夏普比率"""
    if len(equity_curve) < window + 1:
        return []
    equities = [p["equity"] for p in equity_curve]
    dates = [p["date"] for p in equity_curve]
    daily_returns = [
        (equities[i] - equities[i - 1]) / equities[i - 1]
        for i in range(1, len(equities))
        if equities[i - 1] > 0
    ]
    result = []
    for i in range(window, len(daily_returns)):
        wr = daily_returns[i - window:i]
        avg = sum(wr) / window
        std = (sum((r - avg) ** 2 for r in wr) / window) ** 0.5
        sharpe_val = (avg / std * 252 ** 0.5) if std > 0 else 0.0
        result.append({
            "date": str(dates[i + 1]) if i + 1 < len(dates) else "",
            "sharpe": round(sharpe_val, 4),
        })
    return result


def calc_rolling_drawdown(equity_curve: list[dict], window: int = 60) -> list[dict]:
    """计算滚动最大回撤"""
    if len(equity_curve) < window:
        return []
    equities = [p["equity"] for p in equity_curve]
    dates = [p["date"] for p in equity_curve]
    result = []
    for i in range(window, len(equities)):
        window_eq = equities[i - window:i + 1]
        peak = window_eq[0]
        max_dd = 0.0
        for eq in window_eq:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
        result.append({
            "date": str(dates[i]),
            "drawdown": round(max_dd, 4),
        })
    return result


def calc_per_stock_pnl(trades: list[Trade]) -> list[dict]:
    """计算逐股盈亏"""
    sell_trades = [t for t in trades if t.direction == Direction.SHORT and t.entry_price > 0]
    if not sell_trades:
        return []
    per_stock = defaultdict(lambda: {"trades": 0, "pnl_pct": 0.0, "wins": 0, "total_pnl": 0.0})
    for t in sell_trades:
        pnl_pct = (t.price - t.entry_price) / t.entry_price
        pnl_amount = (t.price - t.entry_price) * t.volume
        per_stock[t.code]["trades"] += 1
        per_stock[t.code]["pnl_pct"] += pnl_pct
        per_stock[t.code]["total_pnl"] += pnl_amount
        if pnl_pct > 0:
            per_stock[t.code]["wins"] += 1
    result = []
    for code, data in per_stock.items():
        result.append({
            "code": code,
            "trades": data["trades"],
            "total_pnl": round(data["total_pnl"], 2),
            "avg_pnl_pct": round(data["pnl_pct"] / data["trades"], 4) if data["trades"] > 0 else 0,
            "win_rate": round(data["wins"] / data["trades"], 4) if data["trades"] > 0 else 0,
        })
    result.sort(key=lambda x: x["total_pnl"], reverse=True)
    return result


def calc_holding_period_stats(trades: list[Trade]) -> dict:
    """计算持仓周期统计"""
    from datetime import timedelta
    sell_trades = [t for t in trades if t.direction == Direction.SHORT and t.entry_date]
    if not sell_trades:
        return {"avg": 0, "median": 0, "max": 0, "min": 0}
    periods = []
    for t in sell_trades:
        if hasattr(t.datetime, "toordinal") and hasattr(t.entry_date, "toordinal"):
            delta = (t.datetime - t.entry_date).days
        else:
            delta = 0
        periods.append(max(delta, 0))
    if not periods:
        return {"avg": 0, "median": 0, "max": 0, "min": 0}
    periods.sort()
    return {
        "avg": round(sum(periods) / len(periods), 1),
        "median": periods[len(periods) // 2],
        "max": max(periods),
        "min": min(periods),
    }


def calc_turnover(trades: list[Trade], initial_cash: float, equity_curve: list[dict]) -> float:
    """计算换手率: 总成交额 / 平均权益"""
    total_traded = sum(t.price * t.volume for t in trades)
    if not equity_curve:
        return 0.0
    avg_equity = sum(p["equity"] for p in equity_curve) / len(equity_curve)
    return round(total_traded / avg_equity, 4) if avg_equity > 0 else 0.0


def calc_all_metrics(
    equity_curve: list[dict],
    trades: list[Trade],
    initial_cash: float,
    rolling_window: int = 60,
) -> dict:
    """计算所有增强指标"""
    return {
        "monthly_returns": calc_monthly_returns(equity_curve),
        "rolling_sharpe": calc_rolling_sharpe(equity_curve, rolling_window),
        "rolling_drawdown": calc_rolling_drawdown(equity_curve, rolling_window),
        "per_stock_pnl": calc_per_stock_pnl(trades),
        "holding_period_stats": calc_holding_period_stats(trades),
        "turnover_rate": calc_turnover(trades, initial_cash, equity_curve),
    }
