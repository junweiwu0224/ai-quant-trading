"""绩效分析器"""
import sqlite3
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional

from loguru import logger

from config.settings import PROJECT_ROOT
from engine.models import (
    Direction, EquityCurvePoint, PaperTrade, PerformanceMetrics
)

DEFAULT_DB_PATH = str(PROJECT_ROOT / "data" / "paper_trading.db")


class PerformanceAnalyzer:
    """绩效分析器"""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path

    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def calculate_metrics(
        self,
        initial_cash: float = 1_000_000,
        benchmark_returns: Optional[List[float]] = None,
    ) -> PerformanceMetrics:
        """计算完整绩效指标"""
        trades = self._get_trades()
        equity_curve = self._get_equity_curve()

        if not equity_curve:
            return PerformanceMetrics()

        # 计算每日收益率
        daily_returns = self._calculate_daily_returns(equity_curve)

        # 计算各项指标
        metrics = PerformanceMetrics(
            total_equity=equity_curve[-1].equity if equity_curve else initial_cash,
            daily_return=daily_returns[-1] if daily_returns else 0,
            cumulative_return=self._calc_cumulative_return(equity_curve, initial_cash),
            max_drawdown=self._calc_max_drawdown(equity_curve),
            sharpe_ratio=self._calc_sharpe_ratio(daily_returns),
            sortino_ratio=self._calc_sortino_ratio(daily_returns),
            calmar_ratio=self._calc_calmar_ratio(daily_returns, equity_curve),
            win_rate=self._calc_win_rate(trades),
            profit_loss_ratio=self._calc_profit_loss_ratio(trades),
            total_trades=len(trades),
            winning_trades=sum(1 for t in trades if t.profit > 0),
            losing_trades=sum(1 for t in trades if t.profit < 0),
            avg_win=self._calc_avg_win(trades),
            avg_loss=self._calc_avg_loss(trades),
            max_consecutive_wins=self._calc_max_consecutive(trades, True),
            max_consecutive_losses=self._calc_max_consecutive(trades, False),
            alpha=self._calc_alpha(daily_returns, benchmark_returns) if benchmark_returns else 0,
            beta=self._calc_beta(daily_returns, benchmark_returns) if benchmark_returns else 0,
            information_ratio=self._calc_information_ratio(daily_returns, benchmark_returns) if benchmark_returns else 0,
        )

        return metrics

    def get_monthly_returns(self) -> Dict[str, float]:
        """获取月度收益"""
        equity_curve = self._get_equity_curve()
        if not equity_curve:
            return {}

        monthly = {}
        for point in equity_curve:
            month_key = point.timestamp.strftime("%Y-%m")
            monthly[month_key] = point.equity

        return monthly

    def get_return_distribution(self, bins: int = 20) -> Dict:
        """获取收益分布"""
        equity_curve = self._get_equity_curve()
        if not equity_curve:
            return {"counts": [], "edges": []}

        daily_returns = self._calculate_daily_returns(equity_curve)
        if not daily_returns:
            return {"counts": [], "edges": []}

        # 计算直方图
        import numpy as np
        hist, edges = np.histogram(daily_returns, bins=bins)

        return {
            "counts": hist.tolist(),
            "edges": edges.tolist(),
        }

    def get_weekday_effect(self) -> Dict[str, float]:
        """获取星期效应"""
        equity_curve = self._get_equity_curve()
        if not equity_curve:
            return {}

        weekday_returns = {i: [] for i in range(5)}

        for i in range(1, len(equity_curve)):
            prev = equity_curve[i - 1]
            curr = equity_curve[i]
            weekday = curr.timestamp.weekday()

            if weekday < 5 and prev.equity > 0:
                daily_return = (curr.equity - prev.equity) / prev.equity
                weekday_returns[weekday].append(daily_return)

        import numpy as np
        return {
            "周一": float(np.mean(weekday_returns[0])) if weekday_returns[0] else 0,
            "周二": float(np.mean(weekday_returns[1])) if weekday_returns[1] else 0,
            "周三": float(np.mean(weekday_returns[2])) if weekday_returns[2] else 0,
            "周四": float(np.mean(weekday_returns[3])) if weekday_returns[3] else 0,
            "周五": float(np.mean(weekday_returns[4])) if weekday_returns[4] else 0,
        }

    def get_drawdown_curve(self, days: int = 30) -> List[Dict]:
        """获取回撤曲线"""
        equity_curve = self._get_equity_curve(days=days)
        if not equity_curve:
            return []

        drawdown_curve = []
        peak = equity_curve[0].equity

        for point in equity_curve:
            if point.equity > peak:
                peak = point.equity

            drawdown = (peak - point.equity) / peak if peak > 0 else 0
            drawdown_curve.append({
                "timestamp": point.timestamp.isoformat(),
                "drawdown": round(drawdown, 4),
            })

        return drawdown_curve

    def get_equity_curve(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        interval: str = "1d",
    ) -> List[Dict]:
        """获取资金曲线"""
        equity_curve = self._get_equity_curve(start_date, end_date)
        return [point.to_dict() for point in equity_curve]

    def save_performance_snapshot(self, metrics: PerformanceMetrics, trade_date: date):
        """保存绩效快照"""
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO paper_performance
                (date, total_equity, daily_return, cumulative_return, max_drawdown,
                 sharpe_ratio, sortino_ratio, calmar_ratio, win_rate, profit_loss_ratio,
                 total_trades, winning_trades, losing_trades, avg_win, avg_loss,
                 max_consecutive_wins, max_consecutive_losses, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    trade_date.isoformat(),
                    metrics.total_equity,
                    metrics.daily_return,
                    metrics.cumulative_return,
                    metrics.max_drawdown,
                    metrics.sharpe_ratio,
                    metrics.sortino_ratio,
                    metrics.calmar_ratio,
                    metrics.win_rate,
                    metrics.profit_loss_ratio,
                    metrics.total_trades,
                    metrics.winning_trades,
                    metrics.losing_trades,
                    metrics.avg_win,
                    metrics.avg_loss,
                    metrics.max_consecutive_wins,
                    metrics.max_consecutive_losses,
                    datetime.now().isoformat(),
                )
            )
            conn.commit()
        except Exception as e:
            logger.error(f"保存绩效快照失败: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

    def save_equity_point(self, point: EquityCurvePoint):
        """保存资金曲线点"""
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO paper_equity_curve
                (timestamp, equity, cash, market_value, benchmark_value, drawdown, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    point.timestamp.isoformat(),
                    point.equity,
                    point.cash,
                    point.market_value,
                    point.benchmark_value,
                    point.drawdown,
                    datetime.now().isoformat(),
                )
            )
            conn.commit()
        except Exception as e:
            logger.error(f"保存资金曲线点失败: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

    def _get_trades(self, days: Optional[int] = None) -> List[PaperTrade]:
        """获取交易记录"""
        conn = self._get_conn()
        try:
            if days:
                start_date = (datetime.now() - timedelta(days=days)).isoformat()
                cursor = conn.execute(
                    "SELECT * FROM paper_trades WHERE created_at >= ? ORDER BY created_at ASC",
                    (start_date,)
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM paper_trades ORDER BY created_at ASC"
                )

            rows = cursor.fetchall()
            trades = []

            for row in rows:
                trades.append(PaperTrade(
                    trade_id=row["trade_id"],
                    order_id=row["order_id"],
                    code=row["code"],
                    direction=Direction(row["direction"]),
                    price=row["price"],
                    volume=row["volume"],
                    entry_price=row["entry_price"] or 0,
                    profit=row["profit"] or 0,
                    profit_pct=row["profit_pct"] or 0,
                    commission=row["commission"] or 0,
                    stamp_tax=row["stamp_tax"] or 0,
                    equity_after=row["equity_after"] or 0,
                    strategy_name=row["strategy_name"],
                    signal_reason=row["signal_reason"],
                    created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
                ))

            return trades
        finally:
            conn.close()

    def _get_equity_curve(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        days: Optional[int] = None,
    ) -> List[EquityCurvePoint]:
        """获取资金曲线"""
        conn = self._get_conn()
        try:
            conditions = []
            params = []

            if start_date:
                conditions.append("timestamp >= ?")
                params.append(start_date.isoformat())

            if end_date:
                conditions.append("timestamp <= ?")
                params.append(end_date.isoformat())

            if days:
                start = (datetime.now() - timedelta(days=days)).isoformat()
                conditions.append("timestamp >= ?")
                params.append(start)

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            cursor = conn.execute(
                f"SELECT * FROM paper_equity_curve WHERE {where_clause} "
                f"ORDER BY timestamp ASC",
                params
            )

            rows = cursor.fetchall()
            curve = []

            for row in rows:
                curve.append(EquityCurvePoint(
                    timestamp=datetime.fromisoformat(row["timestamp"]) if row["timestamp"] else None,
                    equity=row["equity"],
                    cash=row["cash"],
                    market_value=row["market_value"] or 0,
                    benchmark_value=row["benchmark_value"],
                    drawdown=row["drawdown"] or 0,
                ))

            return curve
        finally:
            conn.close()

    def _calculate_daily_returns(self, equity_curve: List[EquityCurvePoint]) -> List[float]:
        """计算每日收益率"""
        if len(equity_curve) < 2:
            return []

        returns = []
        for i in range(1, len(equity_curve)):
            prev = equity_curve[i - 1]
            curr = equity_curve[i]

            if prev.equity > 0:
                daily_return = (curr.equity - prev.equity) / prev.equity
                returns.append(daily_return)

        return returns

    def _calc_cumulative_return(self, equity_curve: List[EquityCurvePoint], initial_cash: float) -> float:
        """计算累计收益率"""
        if not equity_curve or initial_cash <= 0:
            return 0
        return (equity_curve[-1].equity - initial_cash) / initial_cash

    def _calc_max_drawdown(self, equity_curve: List[EquityCurvePoint]) -> float:
        """计算最大回撤"""
        if not equity_curve:
            return 0

        peak = equity_curve[0].equity
        max_dd = 0

        for point in equity_curve:
            if point.equity > peak:
                peak = point.equity

            if peak > 0:
                dd = (peak - point.equity) / peak
                if dd > max_dd:
                    max_dd = dd

        return max_dd

    def _calc_sharpe_ratio(self, daily_returns: List[float], risk_free_rate: float = 0.03) -> float:
        """计算夏普比率"""
        if not daily_returns:
            return 0

        import numpy as np
        excess_returns = np.array(daily_returns) - risk_free_rate / 252

        if np.std(excess_returns) == 0:
            return 0

        return float(np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252))

    def _calc_sortino_ratio(self, daily_returns: List[float], risk_free_rate: float = 0.03) -> float:
        """计算Sortino比率"""
        if not daily_returns:
            return 0

        import numpy as np
        excess_returns = np.array(daily_returns) - risk_free_rate / 252
        downside_returns = excess_returns[excess_returns < 0]

        if len(downside_returns) == 0 or np.std(downside_returns) == 0:
            return 0

        return float(np.mean(excess_returns) / np.std(downside_returns) * np.sqrt(252))

    def _calc_calmar_ratio(self, daily_returns: List[float], equity_curve: List[EquityCurvePoint]) -> float:
        """计算Calmar比率"""
        if not daily_returns or not equity_curve:
            return 0

        import numpy as np
        annual_return = np.mean(daily_returns) * 252
        max_drawdown = self._calc_max_drawdown(equity_curve)

        if max_drawdown == 0:
            return 0

        return float(annual_return / max_drawdown)

    def _calc_win_rate(self, trades: List[PaperTrade]) -> float:
        """计算胜率"""
        if not trades:
            return 0
        winning = sum(1 for t in trades if t.profit > 0)
        return winning / len(trades)

    def _calc_profit_loss_ratio(self, trades: List[PaperTrade]) -> float:
        """计算盈亏比"""
        wins = [t.profit for t in trades if t.profit > 0]
        losses = [abs(t.profit) for t in trades if t.profit < 0]

        if not wins or not losses:
            return 0

        import numpy as np
        return float(np.mean(wins) / np.mean(losses))

    def _calc_avg_win(self, trades: List[PaperTrade]) -> float:
        """计算平均盈利"""
        wins = [t.profit for t in trades if t.profit > 0]
        if not wins:
            return 0

        import numpy as np
        return float(np.mean(wins))

    def _calc_avg_loss(self, trades: List[PaperTrade]) -> float:
        """计算平均亏损"""
        losses = [abs(t.profit) for t in trades if t.profit < 0]
        if not losses:
            return 0

        import numpy as np
        return float(np.mean(losses))

    def _calc_max_consecutive(self, trades: List[PaperTrade], is_win: bool) -> int:
        """计算最大连续盈利/亏损次数"""
        if not trades:
            return 0

        max_count = 0
        current_count = 0

        for trade in trades:
            if (is_win and trade.profit > 0) or (not is_win and trade.profit < 0):
                current_count += 1
                max_count = max(max_count, current_count)
            else:
                current_count = 0

        return max_count

    def _calc_alpha(self, daily_returns: List[float], benchmark_returns: List[float]) -> float:
        """计算Alpha"""
        if not daily_returns or not benchmark_returns:
            return 0

        import numpy as np
        min_len = min(len(daily_returns), len(benchmark_returns))
        returns = np.array(daily_returns[:min_len])
        benchmark = np.array(benchmark_returns[:min_len])

        # Alpha = 年化超额收益
        excess_returns = returns - benchmark
        return float(np.mean(excess_returns) * 252)

    def _calc_beta(self, daily_returns: List[float], benchmark_returns: List[float]) -> float:
        """计算Beta"""
        if not daily_returns or not benchmark_returns:
            return 0

        import numpy as np
        min_len = min(len(daily_returns), len(benchmark_returns))
        returns = np.array(daily_returns[:min_len])
        benchmark = np.array(benchmark_returns[:min_len])

        # Beta = Cov(Rp, Rm) / Var(Rm)
        covariance = np.cov(returns, benchmark)[0][1]
        variance = np.var(benchmark)

        if variance == 0:
            return 0

        return float(covariance / variance)

    def _calc_information_ratio(self, daily_returns: List[float], benchmark_returns: List[float]) -> float:
        """计算信息比率"""
        if not daily_returns or not benchmark_returns:
            return 0

        import numpy as np
        min_len = min(len(daily_returns), len(benchmark_returns))
        returns = np.array(daily_returns[:min_len])
        benchmark = np.array(benchmark_returns[:min_len])

        excess_returns = returns - benchmark
        tracking_error = np.std(excess_returns)

        if tracking_error == 0:
            return 0

        return float(np.mean(excess_returns) / tracking_error * np.sqrt(252))
