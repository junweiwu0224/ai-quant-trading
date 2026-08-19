"""多市场交易规则抽象

每种市场（A股/港股/期货）有独立的 MarketRule 实现，
封装交易时间、手数、涨跌停、费率等差异。
引擎通过 MarketRule 接口获取规则，不再硬编码 A 股逻辑。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, time as dtime
import math
from typing import Any, Optional

from data.markets import TradingCalendar, WeekdayTradingCalendar

@dataclass(frozen=True)
class MarketSession:
    """一个交易时段"""
    open: dtime
    close: dtime
    label: str = ""  # "早盘" / "午盘" / "夜盘"

@dataclass(frozen=True)
class FeeStructure:
    """费率结构"""
    commission_rate: float = 0.0003    # 佣金费率
    commission_min: float = 5.0        # 最低佣金
    stamp_tax_rate: float = 0.001      # 印花税（卖出）
    slippage: float = 0.002            # 滑点
    transfer_fee: float = 0.0          # 过户费
    margin_rate: float = 0.0           # 保证金率（期货）
    version: str = "generic-assumption-v1"

class MarketRule(ABC):
    """市场规则接口"""

    def __init__(self, calendar: TradingCalendar | None = None) -> None:
        self._calendar = calendar or WeekdayTradingCalendar()

    @property
    @abstractmethod
    def market_code(self) -> str:
        """市场标识: 'CN' / 'HK' / 'FUTURES'"""

    @property
    @abstractmethod
    def market_name(self) -> str:
        """市场中文名"""

    @abstractmethod
    def trading_sessions(self, weekday: int) -> list[MarketSession]:
        """某星期几的交易时段列表（weekday: 0=周一）"""

    @abstractmethod
    def lot_size(self, code: str) -> int:
        """最小交易手数（A股100，港股按股票，期货1）"""

    @abstractmethod
    def price_limit(self, code: str, pre_close: float) -> Optional[tuple[float, float]]:
        """涨跌停价格 (lower, upper)，无限制返回 None"""

    @abstractmethod
    def fees(self) -> FeeStructure:
        """费率结构"""

    @abstractmethod
    def is_t_plus_1(self) -> bool:
        """是否 T+1 交割"""

    @property
    def calendar(self) -> TradingCalendar:
        """The same date calendar seam used by market adapters."""

        return self._calendar

    def is_trading_day(
        self,
        when: int | date | datetime,
        *,
        holidays: set[date] | frozenset[date] = frozenset(),
    ) -> bool:
        """Return a calendar answer while preserving the old weekday API."""

        if isinstance(when, int) and not isinstance(when, bool):
            return len(self.trading_sessions(when)) > 0
        return bool(self.calendar.is_trading_day(when, holidays=holidays))

    def trading_days(
        self,
        start: date | datetime,
        end: date | datetime,
        *,
        holidays: set[date] | frozenset[date] = frozenset(),
    ) -> tuple[date, ...]:
        return self.calendar.trading_days(start, end, holidays=holidays)

    def next_trading_day(
        self,
        when: date | datetime,
        *,
        holidays: set[date] | frozenset[date] = frozenset(),
        include_current: bool = False,
    ) -> date | None:
        return self.calendar.next_trading_day(when, holidays=holidays, include_current=include_current)

    def is_trading_time(self, weekday: int, t: dtime) -> bool:
        """当前是否在交易时段内"""
        for session in self.trading_sessions(weekday):
            if session.open <= t <= session.close:
                return True
        return False

    def round_volume(self, code: str, volume: int) -> int:

        """将下单量调整为合法手数"""
        lot = self.lot_size(code)
        return (volume // lot) * lot

    def execution_block_reason(
        self,
        code: str,
        side: str | None,
        *,
        open_price: Any,
        close_price: Any,
        volume: Any,
        pre_close: Any = None,
        bar_status: Any = None,
        suspended: Any = False,
        limit_up: Any = None,
        limit_down: Any = None,
    ) -> str | None:
        """Return why a bar cannot be used for a fill, or ``None`` if valid.

        A missing/invalid quote and a halt are deliberately different from a
        zero return.  Callers can retain the order and retry on a later bar.
        """

        if bool(suspended):
            return "halted"
        if isinstance(bar_status, str):
            status = bar_status.strip().lower()
            if status in {"halt", "halted", "suspended", "停牌", "停牌中"}:
                return "halted"
        elif bar_status is True:
            return "halted"

        try:
            opening = float(open_price)
            closing = float(close_price)
            traded_volume = float(volume)
        except (TypeError, ValueError, OverflowError):
            return "missing_quote"
        if not all(math.isfinite(value) for value in (opening, closing, traded_volume)):
            return "missing_quote"
        if traded_volume <= 0:
            return "halted"
        if opening <= 0 or closing <= 0:
            return "missing_quote"

        if limit_up is None or limit_down is None:
            try:
                previous = float(pre_close)
            except (TypeError, ValueError, OverflowError):
                previous = 0.0
            if math.isfinite(previous) and previous > 0:
                limits = self.price_limit(code, previous)
                if limits is not None:
                    limit_down, limit_up = limits
        try:
            upper = float(limit_up) if limit_up is not None else None
            lower = float(limit_down) if limit_down is not None else None
        except (TypeError, ValueError, OverflowError):
            upper = lower = None
        side_value = getattr(side, "value", side)
        side_value = str(side_value or "").strip().lower()
        tolerance = max(1e-9, abs(opening) * 1e-8)
        if side_value in {"buy", "long", "多", "买入"} and upper is not None and opening >= upper - tolerance:
            return "limit_up"
        if side_value in {"sell", "short", "空", "卖出"} and lower is not None and opening <= lower + tolerance:
            return "limit_down"
        return None



# ── A 股规则 ──

    def is_bar_tradable(self, code: str, *, open_price: Any, close_price: Any, volume: Any, **kwargs: Any) -> bool:
        return self.execution_block_reason(
            code,
            None,
            open_price=open_price,
            close_price=close_price,
            volume=volume,
            **kwargs,
        ) is None

class CNStockRule(MarketRule):
    """中国 A 股交易规则"""

    @property
    def market_code(self) -> str:
        return "CN"

    @property
    def market_name(self) -> str:
        return "A股"

    def trading_sessions(self, weekday: int) -> list[MarketSession]:
        if weekday >= 5:
            return []
        return [
            MarketSession(dtime(9, 30), dtime(11, 30), "早盘"),
            MarketSession(dtime(13, 0), dtime(15, 0), "午盘"),
        ]

    def lot_size(self, code: str) -> int:
        return 100

    def price_limit(self, code: str, pre_close: float) -> Optional[tuple[float, float]]:
        # 科创板/创业板 20%，ST 股 5%，主板 10%
        normalized_code = str(code or "").upper().replace("SH.", "").replace("SZ.", "")
        try:
            previous = float(pre_close)
        except (TypeError, ValueError, OverflowError):
            return None
        if not math.isfinite(previous) or previous <= 0:
            return None
        if normalized_code.startswith(("688", "300")):
            pct = 0.20
        elif normalized_code.startswith(("ST", "*ST")):
            pct = 0.05
        else:
            pct = 0.10
        lower = round(previous * (1 - pct), 2)
        upper = round(previous * (1 + pct), 2)
        return (lower, upper)

    def fees(self) -> FeeStructure:
        return FeeStructure(
            commission_rate=0.0003,
            commission_min=5.0,
            stamp_tax_rate=0.001,
            slippage=0.002,
            transfer_fee=0.00001,
        )

    def is_t_plus_1(self) -> bool:
        return True

# ── 港股规则 ──

class HKStockRule(MarketRule):
    """香港股票交易规则"""

    @property
    def market_code(self) -> str:
        return "HK"

    @property
    def market_name(self) -> str:
        return "港股"

    def trading_sessions(self, weekday: int) -> list[MarketSession]:
        if weekday >= 5:
            return []
        return [
            MarketSession(dtime(9, 30), dtime(12, 0), "早盘"),
            MarketSession(dtime(13, 0), dtime(16, 0), "午盘"),
        ]

    def lot_size(self, code: str) -> int:
        # 港股每手股数因股票而异，这里用常见默认值
        # 实际应从行情接口查询
        return 100

    def price_limit(self, code: str, pre_close: float) -> Optional[tuple[float, float]]:
        return None  # 港股无涨跌停

    def fees(self) -> FeeStructure:
        return FeeStructure(
            commission_rate=0.0003,  # 佣金（券商不同）
            commission_min=5.0,
            stamp_tax_rate=0.0013,   # 印花税 0.13%
            slippage=0.003,
            transfer_fee=0.00002,    # 交易征费
        )

    def is_t_plus_1(self) -> bool:
        return False  # 港股 T+0

# ── 期货规则 ──

class FuturesRule(MarketRule):
    """国内期货交易规则"""

    @property
    def market_code(self) -> str:
        return "FUTURES"

    @property
    def market_name(self) -> str:
        return "期货"

    def trading_sessions(self, weekday: int) -> list[MarketSession]:
        if weekday >= 5:
            return []
        sessions = [
            MarketSession(dtime(9, 0), dtime(11, 30), "早盘"),
            MarketSession(dtime(13, 30), dtime(15, 0), "午盘"),
        ]
        # 夜盘（周一至周五）
        if weekday < 5:
            sessions.append(MarketSession(dtime(21, 0), dtime(23, 0), "夜盘"))
        return sessions

    def lot_size(self, code: str) -> int:
        return 1  # 期货按手，每手合约乘数不同

    def price_limit(self, code: str, pre_close: float) -> Optional[tuple[float, float]]:
        # 期货涨跌停因品种而异，一般 5%-20%
        pct = 0.10  # 默认 10%
        lower = round(pre_close * (1 - pct), 2)
        upper = round(pre_close * (1 + pct), 2)
        return (lower, upper)

    def fees(self) -> FeeStructure:
        return FeeStructure(
            commission_rate=0.00005,  # 期货手续费极低
            commission_min=0.0,
            stamp_tax_rate=0.0,       # 期货无印花税
            slippage=0.001,
            margin_rate=0.10,         # 10% 保证金
        )

    def is_t_plus_1(self) -> bool:
        return False  # 期货 T+0

# ── 市场规则注册表 ──

_RULES: dict[str, MarketRule] = {
    "CN": CNStockRule(),
    "HK": HKStockRule(),
    "FUTURES": FuturesRule(),
}

def get_market_rule(market: str) -> MarketRule:
    """获取市场规则"""
    normalized = str(market or "").strip().upper()
    aliases = {"A": "CN", "A_SHARE": "CN", "ASHARE": "CN", "A股": "CN", "港股": "HK"}
    rule = _RULES.get(aliases.get(normalized, normalized))
    if not rule:
        raise ValueError(f"未知市场: {market}，可用: {list(_RULES.keys())}")
    return rule

def get_rule_for_code(code: str) -> MarketRule:
    """根据股票代码自动推断市场"""
    normalized = str(code or "").strip().upper()
    if normalized.startswith(("SH.", "SZ.")) and normalized[3:].isdigit() and len(normalized[3:]) == 6:
        return _RULES["CN"]
    if normalized.startswith("HK.") and normalized[3:].isdigit():
        return _RULES["HK"]
    if normalized.isdigit() and len(normalized) == 6:
        return _RULES["CN"]
    if normalized.isdigit() and len(normalized) == 5:
        return _RULES["HK"]
    # 期货代码通常是字母+数字
    if normalized.isalpha() or (len(normalized) > 6 and not normalized.isdigit()):
        return _RULES["FUTURES"]
    return _RULES["CN"]  # 默认 A 股

def list_markets() -> list[dict]:
    """列出所有支持的市场"""
    return [
        {"code": r.market_code, "name": r.market_name}
        for r in _RULES.values()
    ]
