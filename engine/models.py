"""模拟盘数据模型"""
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from pathlib import Path
from typing import Optional

from config.settings import PROJECT_ROOT
from config.datetime_utils import now_beijing, now_beijing_iso, now_beijing_str, today_beijing, today_beijing_compact


class Direction(Enum):
    """交易方向"""
    LONG = "buy"
    SHORT = "sell"

    @classmethod
    def from_value(cls, value: "Direction | str") -> "Direction":
        if isinstance(value, cls):
            return value

        normalized = str(value).strip().lower()
        aliases = {
            "buy": cls.LONG,
            "long": cls.LONG,
            "sell": cls.SHORT,
            "short": cls.SHORT,
        }
        if normalized in aliases:
            return aliases[normalized]

        raise ValueError(f"{value!r} is not a valid Direction")


class OrderType(Enum):
    """订单类型"""
    MARKET = "market"           # 市价单
    LIMIT = "limit"             # 限价单
    STOP_LOSS = "stop_loss"     # 止损单
    TAKE_PROFIT = "take_profit" # 止盈单


class OrderStatus(Enum):
    """订单状态"""
    PENDING = "pending"      # 待撮合
    FILLED = "filled"        # 已成交
    PARTIAL = "partial"      # 部分成交
    CANCELLED = "cancelled"  # 已撤销
    REJECTED = "rejected"    # 已拒绝


@dataclass
class PaperOrder:
    """增强版订单"""
    order_id: str
    code: str
    direction: Direction
    order_type: OrderType
    price: Optional[float] = None  # 限价/止损价/止盈价
    volume: int = 0
    status: OrderStatus = OrderStatus.PENDING
    filled_price: Optional[float] = None
    filled_volume: int = 0
    commission: float = 0
    stamp_tax: float = 0
    slippage: float = 0
    strategy_name: Optional[str] = None
    signal_reason: Optional[str] = None
    created_at: datetime = field(default_factory=now_beijing)
    updated_at: datetime = field(default_factory=now_beijing)

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "code": self.code,
            "direction": self.direction.value,
            "order_type": self.order_type.value,
            "price": self.price,
            "volume": self.volume,
            "status": self.status.value,
            "filled_price": self.filled_price,
            "filled_volume": self.filled_volume,
            "commission": self.commission,
            "stamp_tax": self.stamp_tax,
            "slippage": self.slippage,
            "strategy_name": self.strategy_name,
            "signal_reason": self.signal_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass
class PaperPosition:
    """增强版持仓"""
    code: str
    volume: int
    avg_price: float
    current_price: float = 0
    market_value: float = 0
    unrealized_pnl: float = 0
    unrealized_pnl_pct: float = 0
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    max_position_pct: float = 0.3
    created_at: datetime = field(default_factory=now_beijing)
    updated_at: datetime = field(default_factory=now_beijing)

    def update_price(self, current_price: float):
        """更新当前价格和盈亏"""
        self.current_price = current_price
        self.market_value = self.volume * current_price
        cost = self.volume * self.avg_price
        self.unrealized_pnl = self.market_value - cost
        self.unrealized_pnl_pct = (self.unrealized_pnl / cost * 100) if cost > 0 else 0
        self.updated_at = now_beijing()

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "volume": self.volume,
            "avg_price": round(self.avg_price, 3),
            "current_price": round(self.current_price, 3),
            "market_value": round(self.market_value, 2),
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "unrealized_pnl_pct": round(self.unrealized_pnl_pct, 2),
            "stop_loss_price": self.stop_loss_price,
            "take_profit_price": self.take_profit_price,
            "max_position_pct": self.max_position_pct,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass
class PaperTrade:
    """增强版交易记录"""
    trade_id: str
    order_id: Optional[str]
    code: str
    direction: Direction
    price: float
    volume: int
    entry_price: float = 0
    profit: float = 0
    profit_pct: float = 0
    commission: float = 0
    stamp_tax: float = 0
    equity_after: float = 0
    strategy_name: Optional[str] = None
    signal_reason: Optional[str] = None
    created_at: datetime = field(default_factory=now_beijing)

    def to_dict(self) -> dict:
        return {
            "trade_id": self.trade_id,
            "order_id": self.order_id,
            "code": self.code,
            "direction": self.direction.value,
            "price": round(self.price, 3),
            "volume": self.volume,
            "entry_price": round(self.entry_price, 3),
            "profit": round(self.profit, 2),
            "profit_pct": round(self.profit_pct, 2),
            "commission": round(self.commission, 2),
            "stamp_tax": round(self.stamp_tax, 2),
            "equity_after": round(self.equity_after, 2),
            "strategy_name": self.strategy_name,
            "signal_reason": self.signal_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class PerformanceMetrics:
    """绩效指标"""
    total_equity: float = 0
    daily_return: float = 0
    cumulative_return: float = 0
    max_drawdown: float = 0
    sharpe_ratio: float = 0
    sortino_ratio: float = 0
    calmar_ratio: float = 0
    win_rate: float = 0
    profit_loss_ratio: float = 0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    avg_win: float = 0
    avg_loss: float = 0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    alpha: float = 0
    beta: float = 0
    information_ratio: float = 0

    def to_dict(self) -> dict:
        return {
            "total_equity": round(self.total_equity, 2),
            "daily_return": round(self.daily_return, 4),
            "cumulative_return": round(self.cumulative_return, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "sortino_ratio": round(self.sortino_ratio, 4),
            "calmar_ratio": round(self.calmar_ratio, 4),
            "win_rate": round(self.win_rate, 4),
            "profit_loss_ratio": round(self.profit_loss_ratio, 4),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "avg_win": round(self.avg_win, 2),
            "avg_loss": round(self.avg_loss, 2),
            "max_consecutive_wins": self.max_consecutive_wins,
            "max_consecutive_losses": self.max_consecutive_losses,
            "alpha": round(self.alpha, 4),
            "beta": round(self.beta, 4),
            "information_ratio": round(self.information_ratio, 4),
        }


@dataclass
class EquityCurvePoint:
    """资金曲线点"""
    timestamp: datetime
    equity: float
    cash: float
    market_value: float
    benchmark_value: Optional[float] = None
    drawdown: float = 0

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "equity": round(self.equity, 2),
            "cash": round(self.cash, 2),
            "market_value": round(self.market_value, 2),
            "benchmark_value": round(self.benchmark_value, 2) if self.benchmark_value else None,
            "drawdown": round(self.drawdown, 4),
        }


@dataclass
class RiskEvent:
    """风控事件"""
    event_type: str  # stop_loss / take_profit / position_limit / drawdown_limit
    code: Optional[str]
    trigger_price: Optional[float]
    action: str  # sell / reject / alert
    reason: str
    created_at: datetime = field(default_factory=now_beijing)

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "code": self.code,
            "trigger_price": self.trigger_price,
            "action": self.action,
            "reason": self.reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class PaperConfig:
    """模拟盘配置"""
    # 基础配置
    initial_cash: float = 50_000
    interval_seconds: int = 30
    enable_risk: bool = True

    # 费用配置
    commission_rate: float = 0.0003   # 万三佣金
    stamp_tax_rate: float = 0.001     # 千一印花税
    slippage: float = 0.002           # 0.2% 滑点

    # 风控配置
    max_position_pct: float = 0.3     # 单只最大仓位占比
    max_positions: int = 10           # 最大持仓数量
    max_drawdown: float = 0.2         # 最大回撤限制
    max_daily_loss: float = 0.05      # 单日最大亏损

    # 状态持久化
    state_dir: str = str(PROJECT_ROOT / "logs" / "paper")
    db_path: str = str(PROJECT_ROOT / "data" / "paper_trading.db")

    def to_dict(self) -> dict:
        return {
            "initial_cash": self.initial_cash,
            "interval_seconds": self.interval_seconds,
            "enable_risk": self.enable_risk,
            "commission_rate": self.commission_rate,
            "stamp_tax_rate": self.stamp_tax_rate,
            "slippage": self.slippage,
            "max_position_pct": self.max_position_pct,
            "max_positions": self.max_positions,
            "max_drawdown": self.max_drawdown,
            "max_daily_loss": self.max_daily_loss,
            "state_dir": self.state_dir,
            "db_path": self.db_path,
        }
