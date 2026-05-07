"""策略评估指标"""
import numpy as np
import pandas as pd
from loguru import logger


class StrategyEvaluator:
    """策略评估器"""

    @staticmethod
    def evaluate(equity_curve: list[dict], initial_cash: float = 1_000_000) -> dict:
        """评估策略表现

        输入: equity_curve [{"date": date, "equity": float}, ...]
        输出: 评估指标字典
        """
        if not equity_curve:
            return {}

        equities = [p["equity"] for p in equity_curve]
        dates = [p["date"] for p in equity_curve]
        n = len(equities)

        # 总收益率
        total_return = (equities[-1] - initial_cash) / initial_cash

        # 年化收益率
        days = (dates[-1] - dates[0]).days if n > 1 else 0
        annual_return = (1 + total_return) ** (365 / max(days, 1)) - 1 if days > 0 else 0.0

        # 日收益率
        daily_returns = [
            (equities[i] - equities[i - 1]) / equities[i - 1]
            for i in range(1, n)
        ] if n > 1 else []

        # 最大回撤
        peak = equities[0]
        max_dd = 0.0
        dd_start = 0
        dd_end = 0
        current_start = 0
        for i, eq in enumerate(equities):
            if eq > peak:
                peak = eq
                current_start = i
            dd = (peak - eq) / peak
            if dd > max_dd:
                max_dd = dd
                dd_start = current_start
                dd_end = i

        # 夏普比率
        if daily_returns:
            avg_ret = np.mean(daily_returns)
            std_ret = np.std(daily_returns, ddof=1)
            sharpe = (avg_ret / std_ret * np.sqrt(252)) if std_ret > 0 else 0.0
        else:
            sharpe = 0.0

        # 索提诺比率
        if daily_returns:
            downside = [r for r in daily_returns if r < 0]
            downside_std = np.std(downside, ddof=1) if len(downside) > 1 else 0.0
            sortino = (np.mean(daily_returns) / downside_std * np.sqrt(252)) if downside_std > 0 else 0.0
        else:
            sortino = 0.0

        # 卡尔玛比率
        calmar = annual_return / max_dd if max_dd > 0 else 0.0

        return {
            "总收益率": f"{total_return:.2%}",
            "年化收益率": f"{annual_return:.2%}",
            "最大回撤": f"{max_dd:.2%}",
            "最大回撤区间": f"{dates[dd_start]} ~ {dates[dd_end]}" if n > 0 else "N/A",
            "夏普比率": f"{sharpe:.2f}",
            "索提诺比率": f"{sortino:.2f}",
            "卡尔玛比率": f"{calmar:.2f}",
            "交易天数": n,
            "_annual_return": annual_return,
            "_max_drawdown": max_dd,
            "_sharpe": sharpe,
        }

    @staticmethod
    def evaluate_trades(trades: list) -> dict:
        """评估交易记录"""
        if not trades:
            return {"总交易次数": 0}

        from strategy.base import Direction

        sell_trades = [t for t in trades if t.direction == Direction.SHORT]
        total = len(sell_trades)

        if total == 0:
            return {"总交易次数": len(trades), "平仓次数": 0}

        wins = [t for t in sell_trades if t.entry_price > 0 and t.price > t.entry_price]
        losses = [t for t in sell_trades if t.entry_price > 0 and t.price <= t.entry_price]

        win_pnl = [(t.price - t.entry_price) / t.entry_price for t in wins]
        loss_pnl = [(t.entry_price - t.price) / t.entry_price for t in losses]

        avg_win = np.mean(win_pnl) if win_pnl else 0.0
        avg_loss = np.mean(loss_pnl) if loss_pnl else 0.0
        profit_factor = (sum(win_pnl) / abs(sum(loss_pnl))) if loss_pnl and sum(loss_pnl) != 0 else float("inf")

        return {
            "总交易次数": len(trades),
            "平仓次数": total,
            "胜率": f"{len(wins) / total:.2%}",
            "盈亏比": f"{avg_win / avg_loss:.2f}" if avg_loss > 0 else "N/A",
            "盈利因子": f"{profit_factor:.2f}",
            "平均盈利": f"{avg_win:.2%}",
            "平均亏损": f"{avg_loss:.2%}",
        }
