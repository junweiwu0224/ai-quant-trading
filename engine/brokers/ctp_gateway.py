"""CTP 券商网关（桩代码）

CTP (Comprehensive Transaction Platform) 是上期技术提供的综合交易平台，
主要用于期货/期权交易。

桩代码实现：定义接口、连接流程、配置参数。
实际接入需要链接 CTP API 的 .so/.dll 动态库。
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
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
class CTPConfig:
    """CTP 连接配置"""
    broker_id: str = ""              # 期货公司代码
    investor_id: str = ""            # 投资者账号
    password: str = ""               # 密码
    front_addr: str = ""             # 前置地址 (tcp://180.168.146.187:10130)
    md_front_addr: str = ""          # 行情前置地址
    auth_code: str = ""              # 认证码
    app_id: str = ""                 # AppID
    user_product_info: str = ""      # 产品信息


class CTPGateway(BrokerGateway):
    """CTP 券商网关

    连接流程：
    1. 初始化 CTP API 动态库
    2. 创建 TraderApi 实例
    3. 注册前置连接 (RegisterFront)
    4. 订阅私有流/公有流
    5. 发起登录请求 (ReqUserLogin)
    6. 等待 OnRspUserLogin 回调
    7. 确认结算单 (ReqSettlementInfoConfirm)
    8. 查询账户/持仓

    桩代码状态：接口已定义，实际 CTP API 调用为 TODO。
    """

    def __init__(self, config: Optional[CTPConfig] = None):
        self._config = config or CTPConfig()
        self._connected = False
        self._logged_in = False
        self._api = None  # CTP TraderApi 实例
        self._lock = threading.Lock()
        self._order_counter = 0
        self._orders: dict[str, OrderResult] = {}

    def connect(self) -> bool:
        """连接 CTP 前置

        实际实现需要：
        1. 加载 libthosttraderapi_se.so
        2. 创建 CThostFtdcTraderApi 实例
        3. 注册 Spi 回调
        4. RegisterFront + Init + Join

        桩代码：模拟连接成功
        """
        logger.info(f"[CTP] 正在连接 {self._config.front_addr}...")

        if not self._config.front_addr:
            logger.error("[CTP] 前置地址未配置")
            return False

        if not self._config.investor_id:
            logger.error("[CTP] 投资者账号未配置")
            return False

        # TODO: 实际 CTP API 连接
        # from ctypes import cdll, c_char_p
        # self._api = cdll.LoadLibrary("libthosttraderapi_se.so")
        # api = self._api.createFtdcTraderApi(b"/tmp/ctp_flow/")
        # spi = CTPTraderSpi(self)
        # api.registerSpi(spi)
        # api.registerFront(c_char_p(self._config.front_addr.encode()))
        # api.init()
        # api.join()

        self._connected = True
        logger.info("[CTP] 前置连接已建立（桩实现）")

        # 模拟登录
        time.sleep(0.1)
        self._logged_in = True
        logger.info(f"[CTP] 登录成功: {self._config.investor_id}")
        return True

    def disconnect(self):
        """断开 CTP 连接"""
        # TODO: 调用 api.release()
        self._connected = False
        self._logged_in = False
        logger.info("[CTP] 已断开连接")

    def is_connected(self) -> bool:
        return self._connected and self._logged_in

    def get_account(self) -> AccountInfo:
        """查询账户资金

        实际实现：ReqQryTradingAccount → OnRspQryTradingAccount 回调
        """
        if not self.is_connected():
            return AccountInfo(0, 0, 0, 0, 0)

        # TODO: 调用 CTP API 查询
        # req = CThostFtdcQryTradingAccountField()
        # req.BrokerID = self._config.broker_id
        # req.InvestorID = self._config.investor_id
        # self._api.ReqQryTradingAccount(req, self._request_id())

        logger.debug("[CTP] 查询账户资金（桩实现返回空）")
        return AccountInfo(
            total_equity=0, cash=0, market_value=0,
            frozen=0, available=0,
        )

    def get_positions(self) -> list[PositionInfo]:
        """查询持仓

        实际实现：ReqQryInvestorPosition → OnRspQryInvestorPosition 回调
        """
        if not self.is_connected():
            return []

        # TODO: 调用 CTP API 查询
        logger.debug("[CTP] 查询持仓（桩实现返回空）")
        return []

    def place_order(
        self,
        code: str,
        side: OrderSide,
        price: float,
        volume: int,
    ) -> OrderResult:
        """CTP 报单

        实际实现：
        req = CThostFtdcInputOrderField()
        req.InstrumentID = code
        req.Direction = THOST_FTDC_D_Buy / THOST_FTDC_D_Sell
        req.LimitPrice = price
        req.VolumeTotalOriginal = volume
        req.OrderPriceType = THOST_FTDC_OPT_LimitPrice
        req.TimeCondition = THOST_FTDC_TC_GFD  # 当日有效
        req.ContingentCondition = THOST_FTDC_CC_Immediately
        req.CombOffsetFlag = THOST_FTDC_OF_Open / THOST_FTDC_OF_Close
        self._api.ReqOrderInsert(req, self._request_id())
        """
        if not self.is_connected():
            return OrderResult(
                order_id="", code=code, side=side,
                price=price, volume=volume,
                status=OrderStatus.REJECTED, message="CTP 未连接",
            )

        # 期货最小交易单位是 1 手（不同品种乘数不同）
        if volume <= 0:
            return OrderResult(
                order_id="", code=code, side=side,
                price=price, volume=volume,
                status=OrderStatus.REJECTED, message="交易量必须大于0",
            )

        with self._lock:
            self._order_counter += 1
            order_id = f"CTP-{self._order_counter:08d}"

        # TODO: 调用 ReqOrderInsert
        logger.info(f"[CTP] 报单: {side.value} {code} {volume}@{price} → {order_id}")

        result = OrderResult(
            order_id=order_id, code=code, side=side,
            price=price, volume=volume,
            status=OrderStatus.PENDING,
        )
        self._orders[order_id] = result
        return result

    def cancel_order(self, order_id: str) -> bool:
        """CTP 撤单

        实际实现：
        req = CThostFtdcInputOrderActionField()
        req.OrderRef = order_id
        req.ActionFlag = THOST_FTDC_AF_Delete
        self._api.ReqOrderAction(req, self._request_id())
        """
        if not self.is_connected():
            return False

        order = self._orders.get(order_id)
        if order and order.status == OrderStatus.PENDING:
            # TODO: 调用 ReqOrderAction
            self._orders[order_id] = OrderResult(
                order_id=order.order_id, code=order.code, side=order.side,
                price=order.price, volume=order.volume,
                status=OrderStatus.CANCELLED,
            )
            logger.info(f"[CTP] 撤单成功: {order_id}")
            return True

        logger.warning(f"[CTP] 撤单失败: {order_id} 不存在或非待撤状态")
        return False

    def get_order_status(self, order_id: str) -> Optional[OrderResult]:
        """查询委托状态"""
        return self._orders.get(order_id)
