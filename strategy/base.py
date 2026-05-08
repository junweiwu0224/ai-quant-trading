"""策略基类"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional


class Direction(Enum):
    LONG = "long"
    SHORT = "short"


@dataclass
class Bar:
    """K线数据"""
    code: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float

    def __post_init__(self):
        if self.high < self.low:
            raise ValueError(f"high({self.high}) < low({self.low}) on {self.date}")
        if self.volume < 0:
            raise ValueError(f"negative volume({self.volume}) on {self.date}")


@dataclass
class Order:
    """委托（市价单，price 为参考价，实际成交价由引擎撮合）"""
    code: str
    direction: Direction
    price: float
    volume: int
    order_id: int = 0
    status: str = "pending"  # pending / filled / partial / cancelled


@dataclass
class Trade:
    """成交"""
    code: str
    direction: Direction
    price: float
    volume: int
    trade_id: int = 0
    order_id: int = 0
    datetime: Optional[date] = None
    entry_price: float = 0.0  # 卖出时记录买入均价
    entry_date: Optional[date] = None  # 卖出时记录买入日期


@dataclass
class Portfolio:
    """投资组合状态"""
    cash: float = 1_000_000.0
    positions: dict = field(default_factory=dict)  # code -> volume
    avg_prices: dict = field(default_factory=dict)  # code -> avg_cost
    trades: list = field(default_factory=list)
    orders: list = field(default_factory=list)
    equity_curve: list = field(default_factory=list)
    entry_dates: dict = field(default_factory=dict)    # code -> date_str
    strategies: dict = field(default_factory=dict)      # code -> strategy_name

    def get_position(self, code: str) -> int:
        return self.positions.get(code, 0)

    def get_avg_price(self, code: str) -> float:
        return self.avg_prices.get(code, 0.0)

    def get_market_value(self, prices: dict[str, float]) -> float:
        return sum(
            vol * prices.get(code, 0)
            for code, vol in self.positions.items()
            if vol > 0
        )

    def get_total_equity(self, prices: dict[str, float]) -> float:
        return self.cash + self.get_market_value(prices)

    def to_dict(self, prices: dict[str, float]) -> dict:
        return {
            "cash": self.cash,
            "market_value": self.get_market_value(prices),
            "total_equity": self.get_total_equity(prices),
            "positions": dict(self.positions),
        }


class BaseStrategy(ABC):
    """策略基类，所有策略继承此类"""

    def __init__(self):
        self.portfolio: Optional[Portfolio] = None
        self._pending_orders: list[Order] = []
        self._order_counter = 0
        self._trade_counter = 0

    def init(self, portfolio: Portfolio):
        """引擎调用，注入投资组合"""
        self.portfolio = portfolio
        self.on_init()

    def on_init(self):
        """策略初始化，子类可覆盖"""
        pass

    @abstractmethod
    def on_bar(self, bar: Bar):
        """K线推送，子类必须实现"""
        ...

    def on_order(self, order: Order):
        """委托回报，子类可覆盖"""
        pass

    def on_trade(self, trade: Trade):
        """成交回报，子类可覆盖"""
        pass

    def buy(self, code: str, price: float, volume: int) -> Order:
        """买入开仓"""
        return self._submit_order(code, Direction.LONG, price, volume)

    def sell(self, code: str, price: float, volume: int) -> Order:
        """卖出平仓"""
        return self._submit_order(code, Direction.SHORT, price, volume)

    def _submit_order(self, code: str, direction: Direction, price: float, volume: int) -> Order:
        self._order_counter += 1
        order = Order(
            code=code,
            direction=direction,
            price=price,
            volume=volume,
            order_id=self._order_counter,
        )
        self._pending_orders.append(order)
        self.portfolio.orders.append(order)
        self.on_order(order)
        return order

    def get_pending_orders(self) -> list[Order]:
        orders = self._pending_orders[:]
        self._pending_orders.clear()
        return orders

    def record_trade(self, trade: Trade):
        self._trade_counter += 1
        trade.trade_id = self._trade_counter
        self.portfolio.trades.append(trade)
        self.on_trade(trade)
