"""L2 十档行情数据模型

定义 OrderBook（订单簿）数据结构和模拟器。
实际 L2 数据需要从交易所或数据供应商获取（如 Level 2 行情接口）。
当前为骨架实现，提供模拟数据生成器用于前端开发和测试。
"""
from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from loguru import logger


@dataclass(frozen=True)
class OrderBookLevel:
    """单档报价"""
    price: float
    volume: int       # 挂单量（手）
    order_count: int  # 委托笔数


@dataclass(frozen=True)
class OrderBook:
    """L2 十档行情

    买盘从高到低排列（买一最高），卖盘从低到高排列（卖一最低）。
    """
    code: str
    name: str
    datetime: datetime
    last_price: float
    last_volume: int
    bids: list[OrderBookLevel]   # 买一到买十（价格降序）
    asks: list[OrderBookLevel]   # 卖一到卖十（价格升序）
    total_bid_volume: int = 0    # 买盘总量
    total_ask_volume: int = 0    # 卖盘总量

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "datetime": self.datetime.isoformat(),
            "last_price": round(self.last_price, 2),
            "last_volume": self.last_volume,
            "bids": [
                {"price": round(l.price, 2), "volume": l.volume, "orders": l.order_count}
                for l in self.bids
            ],
            "asks": [
                {"price": round(l.price, 2), "volume": l.volume, "orders": l.order_count}
                for l in self.asks
            ],
            "total_bid_volume": self.total_bid_volume,
            "total_ask_volume": self.total_ask_volume,
        }

    @property
    def bid_ask_spread(self) -> float:
        """买卖价差"""
        if self.bids and self.asks:
            return round(self.asks[0].price - self.bids[0].price, 2)
        return 0.0

    @property
    def mid_price(self) -> float:
        """中间价"""
        if self.bids and self.asks:
            return round((self.bids[0].price + self.asks[0].price) / 2, 2)
        return self.last_price


class OrderBookSimulator:
    """L2 十档行情模拟器

    基于最新价格生成模拟的十档买卖盘数据。
    用于前端开发和测试，实际接入时替换为真实数据源。
    """

    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callbacks: list[Callable[[OrderBook], None]] = []
        self._lock = threading.Lock()
        self._subscribed: dict[str, float] = {}  # code -> last_price

    def subscribe(self, code: str, last_price: float = 0.0):
        """订阅某股票的 L2 行情"""
        with self._lock:
            self._subscribed[code] = last_price
        logger.info(f"[L2] 订阅: {code}")

    def unsubscribe(self, code: str):
        """取消订阅"""
        with self._lock:
            self._subscribed.pop(code, None)
        logger.info(f"[L2] 取消订阅: {code}")

    def on_update(self, callback: Callable[[OrderBook], None]):
        """注册更新回调"""
        self._callbacks.append(callback)

    def start(self, interval: float = 1.0):
        """启动模拟推送"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop, args=(interval,), daemon=True
        )
        self._thread.start()
        logger.info(f"[L2] 模拟器已启动, 间隔={interval}s")

    def stop(self):
        """停止推送"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
        logger.info("[L2] 模拟器已停止")

    def _poll_loop(self, interval: float):
        """后台轮询循环"""
        while self._running:
            try:
                with self._lock:
                    codes = list(self._subscribed.items())
                for code, base_price in codes:
                    book = self._generate_book(code, base_price)
                    for cb in self._callbacks:
                        try:
                            cb(book)
                        except Exception as e:
                            logger.warning(f"[L2] 回调异常: {e}")
            except Exception as e:
                logger.warning(f"[L2] 轮询异常: {e}")
            time.sleep(interval)

    def _generate_book(self, code: str, base_price: float) -> OrderBook:
        """生成模拟十档行情

        基于最新价格，生成围绕当前价格的十档买卖盘。
        买盘从高到低递减，卖盘从低到高递增。
        """
        if base_price <= 0:
            base_price = 10.0 + random.random() * 20

        # 价格步长（根据价格区间调整）
        tick_size = 0.01 if base_price < 100 else 0.05

        # 随机偏移当前价格
        mid = base_price * (1 + random.gauss(0, 0.001))

        # 生成买盘（从高到低）
        bids = []
        bid_price = round(mid - tick_size, 2)
        for i in range(10):
            vol = random.randint(50, 5000) * 10
            orders = random.randint(1, 50)
            bids.append(OrderBookLevel(
                price=round(bid_price, 2),
                volume=vol,
                order_count=orders,
            ))
            bid_price -= tick_size * random.randint(1, 3)

        # 生成卖盘（从低到高）
        asks = []
        ask_price = round(mid + tick_size, 2)
        for i in range(10):
            vol = random.randint(50, 5000) * 10
            orders = random.randint(1, 50)
            asks.append(OrderBookLevel(
                price=round(ask_price, 2),
                volume=vol,
                order_count=orders,
            ))
            ask_price += tick_size * random.randint(1, 3)

        last_price = round(mid, 2)
        last_vol = random.randint(1, 500) * 100

        return OrderBook(
            code=code,
            name="",
            datetime=datetime.now(),
            last_price=last_price,
            last_volume=last_vol,
            bids=bids,
            asks=asks,
            total_bid_volume=sum(l.volume for l in bids),
            total_ask_volume=sum(l.volume for l in asks),
        )


# ── 全局单例 ──
_l2_simulator: Optional[OrderBookSimulator] = None


def get_l2_simulator() -> OrderBookSimulator:
    """获取 L2 模拟器单例"""
    global _l2_simulator
    if _l2_simulator is None:
        _l2_simulator = OrderBookSimulator()
    return _l2_simulator
