"""风险监控"""
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional

from loguru import logger

from strategy.base import Portfolio


class AlertLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class RiskAlert:
    """风险告警"""
    date: date
    level: AlertLevel
    category: str
    message: str
    value: float
    threshold: float


@dataclass
class RiskMetrics:
    """风险指标快照"""
    date: date
    total_equity: float
    cash: float
    market_value: float
    position_count: int
    max_single_pct: float
    cash_pct: float
    daily_pnl: float
    daily_pnl_pct: float
    peak_equity: float
    drawdown_pct: float
    industry_concentration: dict[str, float] = field(default_factory=dict)


class RiskMonitor:
    """风险监控器"""

    def __init__(
        self,
        drawdown_warn_pct: float = 0.10,
        daily_loss_warn_pct: float = 0.02,
        single_position_warn_pct: float = 0.15,
        cash_warn_pct: float = 0.10,
    ):
        self._drawdown_warn = drawdown_warn_pct
        self._daily_loss_warn = daily_loss_warn_pct
        self._single_position_warn = single_position_warn_pct
        self._cash_warn = cash_warn_pct

        self._peak_equity: float = 0.0
        self._daily_start_equity: float = 0.0
        self._current_date: Optional[date] = None
        self._alerts: list[RiskAlert] = []

    @property
    def alerts(self) -> list[RiskAlert]:
        return list(self._alerts)

    def clear_alerts(self):
        self._alerts.clear()

    def snapshot(
        self,
        current_date: date,
        portfolio: Portfolio,
        prices: dict[str, float],
        industry_map: Optional[dict[str, str]] = None,
    ) -> RiskMetrics:
        """生成风险指标快照"""
        total_equity = portfolio.get_total_equity(prices)
        market_value = portfolio.get_market_value(prices)

        # 日期切换时重置日起始权益
        if self._current_date != current_date:
            self._current_date = current_date
            self._daily_start_equity = total_equity

        # 更新峰值
        if total_equity > self._peak_equity:
            self._peak_equity = total_equity

        # 持仓数
        active_positions = {c: v for c, v in portfolio.positions.items() if v > 0}
        position_count = len(active_positions)

        # 单票最大占比
        max_single_pct = 0.0
        for code, vol in active_positions.items():
            value = vol * prices.get(code, 0)
            pct = value / total_equity if total_equity > 0 else 0
            if pct > max_single_pct:
                max_single_pct = pct

        # 现金占比
        cash_pct = portfolio.cash / total_equity if total_equity > 0 else 0

        # 日盈亏
        daily_pnl = total_equity - self._daily_start_equity
        daily_pnl_pct = daily_pnl / self._daily_start_equity if self._daily_start_equity > 0 else 0

        # 回撤
        drawdown_pct = 0.0
        if self._peak_equity > 0:
            drawdown_pct = (self._peak_equity - total_equity) / self._peak_equity

        # 行业集中度
        industry_concentration = {}
        if industry_map and total_equity > 0:
            industry_values: dict[str, float] = {}
            for code, vol in active_positions.items():
                ind = industry_map.get(code, "未知")
                value = vol * prices.get(code, 0)
                industry_values[ind] = industry_values.get(ind, 0) + value
            industry_concentration = {
                ind: val / total_equity for ind, val in industry_values.items()
            }

        metrics = RiskMetrics(
            date=current_date,
            total_equity=total_equity,
            cash=portfolio.cash,
            market_value=market_value,
            position_count=position_count,
            max_single_pct=max_single_pct,
            cash_pct=cash_pct,
            daily_pnl=daily_pnl,
            daily_pnl_pct=daily_pnl_pct,
            peak_equity=self._peak_equity,
            drawdown_pct=drawdown_pct,
            industry_concentration=industry_concentration,
        )

        # 检查告警
        self._check_alerts(current_date, metrics)
        return metrics

    def _check_alerts(self, current_date: date, m: RiskMetrics):
        """检查并生成告警"""
        # 回撤预警
        if m.drawdown_pct >= self._drawdown_warn:
            self._add_alert(
                current_date, AlertLevel.WARNING, "回撤",
                f"当前回撤 {m.drawdown_pct:.1%}（预警 {self._drawdown_warn:.0%}）",
                m.drawdown_pct, self._drawdown_warn,
            )

        # 日亏损预警
        if m.daily_pnl_pct <= -self._daily_loss_warn:
            self._add_alert(
                current_date, AlertLevel.WARNING, "日亏损",
                f"日亏损 {m.daily_pnl_pct:.1%}（预警 {self._daily_loss_warn:.0%}）",
                abs(m.daily_pnl_pct), self._daily_loss_warn,
            )

        # 单票集中预警
        if m.max_single_pct >= self._single_position_warn:
            self._add_alert(
                current_date, AlertLevel.WARNING, "单票集中",
                f"单票占比 {m.max_single_pct:.1%}（预警 {self._single_position_warn:.0%}）",
                m.max_single_pct, self._single_position_warn,
            )

        # 现金不足预警
        if m.cash_pct <= self._cash_warn:
            self._add_alert(
                current_date, AlertLevel.WARNING, "现金不足",
                f"现金占比 {m.cash_pct:.1%}（预警 {self._cash_warn:.0%}）",
                m.cash_pct, self._cash_warn,
            )

        # 行业集中预警
        for ind, pct in m.industry_concentration.items():
            if pct >= 0.30:
                self._add_alert(
                    current_date, AlertLevel.WARNING, "行业集中",
                    f"行业 {ind} 占比 {pct:.1%}（预警 30%）",
                    pct, 0.30,
                )

    def _add_alert(
        self,
        current_date: date,
        level: AlertLevel,
        category: str,
        message: str,
        value: float,
        threshold: float,
    ):
        # 去重：同日同类别只记一次
        for a in self._alerts:
            if a.date == current_date and a.category == category:
                return
        alert = RiskAlert(
            date=current_date, level=level, category=category,
            message=message, value=value, threshold=threshold,
        )
        self._alerts.append(alert)
        if level == AlertLevel.CRITICAL:
            logger.error(f"[风控] {message}")
        else:
            logger.warning(f"[风控] {message}")
