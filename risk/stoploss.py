"""止损止盈规则"""
from dataclasses import dataclass
from datetime import date
from typing import Optional

from loguru import logger

from strategy.base import Direction, Portfolio, Trade


@dataclass(frozen=True)
class StopLossConfig:
    """止损止盈配置"""
    max_drawdown_pct: float = 0.15      # 最大回撤止损 15%
    daily_loss_limit_pct: float = 0.03  # 日亏损限额 3%
    atr_stop_multiple: float = 2.0      # ATR 止损倍数
    trailing_stop_pct: float = 0.08     # 追踪止损 8%
    fixed_stop_pct: float = 0.05        # 固定止损 5%
    take_profit_pct: float = 0.20       # 固定止盈 20%


@dataclass
class StopSignal:
    """止损/止盈信号"""
    code: str
    reason: str
    action: str  # "sell" or "reduce"
    urgency: int  # 1=最高, 5=最低


class StopLossManager:
    """止损止盈管理器"""

    def __init__(self, config: Optional[StopLossConfig] = None):
        self._config = config or StopLossConfig()
        self._peak_equity: float = 0.0
        self._daily_start_equity: float = 0.0
        self._current_date: Optional[date] = None
        self._trailing_highs: dict[str, float] = {}

    def update_equity(self, current_date: date, equity: float):
        """更新权益，用于回撤和日亏损计算"""
        if self._current_date != current_date:
            self._current_date = current_date
            self._daily_start_equity = equity

        if equity > self._peak_equity:
            self._peak_equity = equity

    def check_max_drawdown(self, equity: float) -> Optional[StopSignal]:
        """最大回撤止损 — 全部平仓"""
        if self._peak_equity <= 0:
            return None

        drawdown = (self._peak_equity - equity) / self._peak_equity
        if drawdown >= self._config.max_drawdown_pct:
            return StopSignal(
                code="*",
                reason=f"最大回撤 {drawdown:.1%} 触发止损（阈值 {self._config.max_drawdown_pct:.0%}），峰值 {self._peak_equity:,.0f}，当前 {equity:,.0f}",
                action="sell",
                urgency=1,
            )
        return None

    def check_daily_loss(self, equity: float) -> Optional[StopSignal]:
        """日亏损限额 — 当日停止交易"""
        if self._daily_start_equity <= 0:
            return None

        daily_loss = (self._daily_start_equity - equity) / self._daily_start_equity
        if daily_loss >= self._config.daily_loss_limit_pct:
            return StopSignal(
                code="*",
                reason=f"日亏损 {daily_loss:.1%} 触发限额（阈值 {self._config.daily_loss_limit_pct:.0%}），起始 {self._daily_start_equity:,.0f}，当前 {equity:,.0f}",
                action="reduce",
                urgency=1,
            )
        return None

    def check_atr_stop(
        self,
        code: str,
        entry_price: float,
        current_price: float,
        atr: float,
    ) -> Optional[StopSignal]:
        """ATR 波动率止损"""
        if atr <= 0 or entry_price <= 0:
            return None

        stop_price = entry_price - self._config.atr_stop_multiple * atr
        if current_price <= stop_price:
            loss_pct = (entry_price - current_price) / entry_price
            return StopSignal(
                code=code,
                reason=f"ATR 止损: 入场 {entry_price:.2f}，止损位 {stop_price:.2f}，当前 {current_price:.2f}，亏损 {loss_pct:.1%}",
                action="sell",
                urgency=2,
            )
        return None

    def check_trailing_stop(
        self,
        code: str,
        entry_price: float,
        current_price: float,
    ) -> Optional[StopSignal]:
        """追踪止损 — 浮盈回撤 N% 止盈"""
        if current_price <= entry_price:
            return None

        # 更新持仓最高价
        high = self._trailing_highs.get(code, entry_price)
        if current_price > high:
            self._trailing_highs[code] = current_price
            high = current_price

        # 计算从最高点的回撤
        pullback = (high - current_price) / high
        if pullback >= self._config.trailing_stop_pct:
            profit_pct = (current_price - entry_price) / entry_price
            return StopSignal(
                code=code,
                reason=f"追踪止损: 最高 {high:.2f}，当前 {current_price:.2f}，回撤 {pullback:.1%}，盈利 {profit_pct:.1%}",
                action="sell",
                urgency=3,
            )
        return None

    def check_fixed_stop(
        self,
        code: str,
        entry_price: float,
        current_price: float,
    ) -> Optional[StopSignal]:
        """固定止损"""
        if entry_price <= 0:
            return None

        loss_pct = (entry_price - current_price) / entry_price
        if loss_pct >= self._config.fixed_stop_pct:
            return StopSignal(
                code=code,
                reason=f"固定止损: 入场 {entry_price:.2f}，当前 {current_price:.2f}，亏损 {loss_pct:.1%}",
                action="sell",
                urgency=2,
            )
        return None

    def check_take_profit(
        self,
        code: str,
        entry_price: float,
        current_price: float,
    ) -> Optional[StopSignal]:
        """固定止盈"""
        if entry_price <= 0:
            return None

        profit_pct = (current_price - entry_price) / entry_price
        if profit_pct >= self._config.take_profit_pct:
            return StopSignal(
                code=code,
                reason=f"止盈: 入场 {entry_price:.2f}，当前 {current_price:.2f}，盈利 {profit_pct:.1%}",
                action="sell",
                urgency=4,
            )
        return None

    def check_all(
        self,
        code: str,
        entry_price: float,
        current_price: float,
        equity: float,
        atr: float = 0.0,
    ) -> list[StopSignal]:
        """检查所有止损止盈规则，返回触发的信号列表"""
        signals = []

        # 全局规则（优先级最高）
        dd_signal = self.check_max_drawdown(equity)
        if dd_signal:
            signals.append(dd_signal)

        dl_signal = self.check_daily_loss(equity)
        if dl_signal:
            signals.append(dl_signal)

        # 个股规则
        atr_signal = self.check_atr_stop(code, entry_price, current_price, atr)
        if atr_signal:
            signals.append(atr_signal)

        fixed_signal = self.check_fixed_stop(code, entry_price, current_price)
        if fixed_signal:
            signals.append(fixed_signal)

        trailing_signal = self.check_trailing_stop(code, entry_price, current_price)
        if trailing_signal:
            signals.append(trailing_signal)

        tp_signal = self.check_take_profit(code, entry_price, current_price)
        if tp_signal:
            signals.append(tp_signal)

        # 按 urgency 排序
        signals.sort(key=lambda s: s.urgency)
        return signals

    def clear_trailing_high(self, code: str):
        """清除追踪止损记录（持仓清仓后调用）"""
        self._trailing_highs.pop(code, None)

    def get_trailing_high(self, code: str) -> float:
        """获取追踪止损最高价"""
        return self._trailing_highs.get(code, 0.0)
