"""XTP 券商网关（桩代码）

XTP (Xtang Trading Platform) 是中泰证券提供的极速交易接口，
主要用于股票/ETF/可转债等交易。

桩代码实现：定义接口、连接流程、配置参数。
实际接入需要链接 XTP API 的 .so/.dll 动态库。
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional

from loguru import logger

from engine.broker import (
    AccountInfo,
    BrokerGateway,
    OrderResult,
    OrderSide,
    OrderStatus,
    PositionInfo,
)


@dataclass(frozen=True)
class XTPConfig:
    """XTP 连接配置"""
    account_id: str = ""             # 资金账号
    password: str = ""               # 密码
    client_id: int = 1               # 客户端ID
    trade_server_ip: str = ""        # 交易服务器IP
    trade_server_port: int = 0       # 交易服务器端口
    quote_server_ip: str = ""        # 行情服务器IP
    quote_server_port: int = 0       # 行情服务器端口
    auth_code: str = ""              # 认证码
    app_id: int = 0                  # AppID
    sock_type: int = 1               # 1=TCP, 2=UDP


class XTPGateway(BrokerGateway):
    """XTP 券商网关

    连接流程：
    1. 加载 libxtptraderapi.so
    2. 创建 TraderApi 实例
    3. 订阅公有流/私有流
    4. 登录交易服务器 (login)
    5. 等待登录回调
    6. 查询账户/持仓

    桩代码状态：接口已定义，实际 XTP API 调用为 TODO。
    """

    def __init__(self, config: Optional[XTPConfig] = None):
        self._config = config or XTPConfig()
        self._connected = False
        self._session_id = 0
        self._api = None  # XTP TraderApi 实例
        self._lock = threading.Lock()
        self._order_counter = 0
        self._orders: dict[str, OrderResult] = {}

    def connect(self) -> bool:
        """连接 XTP 交易服务器

        实际实现需要：
        1. 加载 libxtptraderapi.so
        2. 创建 TraderApi: api = TraderApi.createTraderApi(client_id, log_path)
        3. 注册 Spi: api.registerSpi(spi)
        4. 订阅公有流/私有流
        5. 登录: session = api.login(ip, port, account_id, password, sock_type, auth_code)

        桩代码：模拟连接成功
        """
        logger.info(f"[XTP] 正在连接 {self._config.trade_server_ip}:{self._config.trade_server_port}...")

        if not self._config.trade_server_ip:
            logger.error("[XTP] 交易服务器地址未配置")
            return False

        if not self._config.account_id:
            logger.error("[XTP] 资金账号未配置")
            return False

        # TODO: 实际 XTP API 连接
        # from ctypes import cdll
        # lib = cdll.LoadLibrary("libxtptraderapi.so")
        # api = lib.createTraderApi(self._config.client_id, b"/tmp/xtp_log/")
        # spi = XTPTraderSpi(self)
        # api.registerSpi(spi)
        # api.subscribePublicTopic(0)  # 0=THOST_TERT_RESTART
        # api.subscribePrivateTopic(0)
        # session = api.login(
        #     self._config.trade_server_ip.encode(),
        #     self._config.trade_server_port,
        #     self._config.account_id.encode(),
        #     self._config.password.encode(),
        #     self._config.sock_type,
        #     self._config.auth_code.encode(),
        # )

        self._connected = True
        self._session_id = 1  # 模拟 session
        logger.info(f"[XTP] 登录成功: {self._config.account_id}, session={self._session_id}")
        return True

    def disconnect(self):
        """断开 XTP 连接"""
        # TODO: 调用 api.release()
        self._connected = False
        self._session_id = 0
        logger.info("[XTP] 已断开连接")

    def is_connected(self) -> bool:
        return self._connected and self._session_id > 0

    def get_account(self) -> AccountInfo:
        """查询账户资金

        实际实现：api.queryAsset(session_id) → onQueryAsset 回调
        """
        if not self.is_connected():
            return AccountInfo(0, 0, 0, 0, 0)

        # TODO: 调用 XTP API
        logger.debug("[XTP] 查询账户资金（桩实现返回空）")
        return AccountInfo(
            total_equity=0, cash=0, market_value=0,
            frozen=0, available=0,
        )

    def get_positions(self) -> list[PositionInfo]:
        """查询持仓

        实际实现：api.queryPosition("", session_id) → onQueryPosition 回调
        """
        if not self.is_connected():
            return []

        # TODO: 调用 XTP API
        logger.debug("[XTP] 查询持仓（桩实现返回空）")
        return []

    def place_order(
        self,
        code: str,
        side: OrderSide,
        price: float,
        volume: int,
    ) -> OrderResult:
        """XTP 下单

        实际实现：
        order = XTPOrderInsertInfo()
        order.ticker = code
        order.market = XTP_MKT_SZ_A / XTP_MKT_SH_A  # 根据代码判断市场
        order.price = price
        order.quantity = volume
        order.order_type = XTP_PRICE_LIMIT  # 限价单
        order.side = XTP_SIDE_BUY / XTP_SIDE_SELL
        order_id = api.insertOrder(order, session_id)
        """
        if not self.is_connected():
            return OrderResult(
                order_id="", code=code, side=side,
                price=price, volume=volume,
                status=OrderStatus.REJECTED, message="XTP 未连接",
            )

        if volume <= 0 or volume % 100 != 0:
            return OrderResult(
                order_id="", code=code, side=side,
                price=price, volume=volume,
                status=OrderStatus.REJECTED, message="交易量必须是100的整数倍",
            )

        with self._lock:
            self._order_counter += 1
            order_id = f"XTP-{self._order_counter:08d}"

        # TODO: 调用 api.insertOrder()
        logger.info(f"[XTP] 下单: {side.value} {code} {volume}@{price} → {order_id}")

        result = OrderResult(
            order_id=order_id, code=code, side=side,
            price=price, volume=volume,
            status=OrderStatus.PENDING,
        )
        self._orders[order_id] = result
        return result

    def cancel_order(self, order_id: str) -> bool:
        """XTP 撤单

        实际实现：api.cancelOrder(order_id_int, session_id)
        """
        if not self.is_connected():
            return False

        order = self._orders.get(order_id)
        if order and order.status == OrderStatus.PENDING:
            # TODO: 调用 api.cancelOrder()
            self._orders[order_id] = OrderResult(
                order_id=order.order_id, code=order.code, side=order.side,
                price=order.price, volume=order.volume,
                status=OrderStatus.CANCELLED,
            )
            logger.info(f"[XTP] 撤单成功: {order_id}")
            return True

        logger.warning(f"[XTP] 撤单失败: {order_id}")
        return False

    def get_order_status(self, order_id: str) -> Optional[OrderResult]:
        """查询委托状态"""
        return self._orders.get(order_id)

    def get_market_code(self, code: str) -> int:
        """根据股票代码判断市场

        Returns:
            1=深圳, 2=上海
        """
        if code.startswith(("0", "3")):
            return 1  # XTP_MKT_SZ_A
        if code.startswith(("6", "9")):
            return 2  # XTP_MKT_SH_A
        return 1  # 默认深圳
