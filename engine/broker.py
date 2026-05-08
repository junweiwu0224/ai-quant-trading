"""券商网关接口"""
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from loguru import logger


class OrderStatus(Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class OrderResult:
    """委托结果"""
    order_id: str
    code: str
    side: OrderSide
    price: float
    volume: int
    status: OrderStatus
    filled_volume: int = 0
    filled_price: float = 0.0
    message: str = ""


@dataclass(frozen=True)
class PositionInfo:
    """持仓信息"""
    code: str
    volume: int
    available: int  # 可卖数量
    avg_price: float
    market_value: float
    pnl: float
    pnl_pct: float


@dataclass(frozen=True)
class AccountInfo:
    """账户信息"""
    total_equity: float
    cash: float
    market_value: float
    frozen: float  # 冻结资金
    available: float  # 可用资金


class BrokerGateway(ABC):
    """券商网关抽象接口"""

    @abstractmethod
    def connect(self) -> bool:
        """连接券商"""
        ...

    @abstractmethod
    def disconnect(self):
        """断开连接"""
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """是否已连接"""
        ...

    @abstractmethod
    def get_account(self) -> AccountInfo:
        """获取账户信息"""
        ...

    @abstractmethod
    def get_positions(self) -> list[PositionInfo]:
        """获取持仓列表"""
        ...

    @abstractmethod
    def place_order(
        self,
        code: str,
        side: OrderSide,
        price: float,
        volume: int,
    ) -> OrderResult:
        """下单

        Args:
            code: 股票代码
            side: 买/卖
            price: 委托价格
            volume: 委托数量

        Returns:
            OrderResult
        """
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """撤单"""
        ...

    @abstractmethod
    def get_order_status(self, order_id: str) -> Optional[OrderResult]:
        """查询委托状态"""
        ...


class SimulatedBroker(BrokerGateway):
    """模拟券商（用于测试和模拟盘）"""

    def __init__(self, initial_cash: float = 1_000_000.0):
        self._initial_cash = initial_cash
        self._cash = initial_cash
        self._positions: dict[str, dict] = {}  # code -> {volume, avg_price, available}
        self._orders: dict[str, OrderResult] = {}
        self._order_counter = 0
        self._connected = False
        self._prices: dict[str, float] = {}  # 模拟价格
        self._lock = threading.Lock()

    def connect(self) -> bool:
        self._connected = True
        logger.info("[模拟券商] 已连接")
        return True

    def disconnect(self):
        self._connected = False
        logger.info("[模拟券商] 已断开")

    def is_connected(self) -> bool:
        return self._connected

    def set_price(self, code: str, price: float):
        """设置模拟价格（测试用）"""
        self._prices[code] = price

    def get_account(self) -> AccountInfo:
        mv = sum(
            p["volume"] * self._prices.get(c, p["avg_price"])
            for c, p in self._positions.items()
        )
        return AccountInfo(
            total_equity=self._cash + mv,
            cash=self._cash,
            market_value=mv,
            frozen=0,
            available=self._cash,
        )

    def get_positions(self) -> list[PositionInfo]:
        result = []
        for code, pos in self._positions.items():
            if pos["volume"] <= 0:
                continue
            price = self._prices.get(code, pos["avg_price"])
            mv = pos["volume"] * price
            cost = pos["volume"] * pos["avg_price"]
            pnl = mv - cost
            pnl_pct = pnl / cost if cost > 0 else 0
            result.append(PositionInfo(
                code=code,
                volume=pos["volume"],
                available=pos["available"],
                avg_price=pos["avg_price"],
                market_value=round(mv, 2),
                pnl=round(pnl, 2),
                pnl_pct=round(pnl_pct, 4),
            ))
        return result

    def place_order(
        self,
        code: str,
        side: OrderSide,
        price: float,
        volume: int,
    ) -> OrderResult:
        with self._lock:
            if not self._connected:
                return self._reject(code, side, price, volume, "未连接")

            # A 股最小交易单位 100 股
            if volume <= 0 or volume % 100 != 0:
                return self._reject(code, side, price, volume, "交易量必须是100的整数倍")

            self._order_counter += 1
            order_id = f"SIM-{self._order_counter:06d}"

            if side == OrderSide.BUY:
                cost = price * volume
                commission = max(cost * 0.0003, 5.0)
                if self._cash < cost + commission:
                    return self._reject(code, side, price, volume, "资金不足")

                self._cash -= cost + commission
                pos = self._positions.get(code, {"volume": 0, "avg_price": 0, "available": 0})
                old_vol = pos["volume"]
                new_vol = old_vol + volume
                new_avg = (pos["avg_price"] * old_vol + price * volume) / new_vol
                self._positions[code] = {
                    "volume": new_vol,
                    "avg_price": new_avg,
                    "available": pos["available"],  # T+1，当日买入不可卖
                }

                result = OrderResult(
                    order_id=order_id, code=code, side=side,
                    price=price, volume=volume,
                    status=OrderStatus.FILLED,
                    filled_volume=volume, filled_price=price,
                )

            elif side == OrderSide.SELL:
                pos = self._positions.get(code)
                if not pos or pos["available"] <= 0:
                    return self._reject(code, side, price, volume, "无可卖持仓")

                actual_vol = min(volume, pos["available"])
                revenue = price * actual_vol
                commission = max(revenue * 0.0003, 5.0)
                stamp_tax = revenue * 0.001

                self._cash += revenue - commission - stamp_tax
                pos["volume"] -= actual_vol
                pos["available"] -= actual_vol
                if pos["volume"] <= 0:
                    del self._positions[code]

                result = OrderResult(
                    order_id=order_id, code=code, side=side,
                    price=price, volume=volume,
                    status=OrderStatus.FILLED if actual_vol >= volume else OrderStatus.PARTIAL,
                    filled_volume=actual_vol, filled_price=price,
                )
            else:
                return self._reject(code, side, price, volume, "未知方向")

            self._orders[order_id] = result
            logger.info(f"[模拟券商] {side.value} {code} {volume}股@{price} → {result.status.value}")
            return result

    def cancel_order(self, order_id: str) -> bool:
        order = self._orders.get(order_id)
        if order and order.status == OrderStatus.PENDING:
            self._orders[order_id] = OrderResult(
                order_id=order.order_id, code=order.code, side=order.side,
                price=order.price, volume=order.volume,
                status=OrderStatus.CANCELLED,
            )
            return True
        return False

    def get_order_status(self, order_id: str) -> Optional[OrderResult]:
        return self._orders.get(order_id)

    def _reject(self, code, side, price, volume, msg) -> OrderResult:
        logger.warning(f"[模拟券商] 拒绝: {msg}")
        return OrderResult(
            order_id="", code=code, side=side,
            price=price, volume=volume,
            status=OrderStatus.REJECTED, message=msg,
        )

    def settle_t1(self):
        """T+1 结算：将当日买入的股票设为可卖"""
        for pos in self._positions.values():
            pos["available"] = pos["volume"]
