"""券商账户配置 API"""
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

from config.settings import PROJECT_ROOT

CONFIG_FILE = PROJECT_ROOT / "data" / "broker_config.json"

router = APIRouter()


class BrokerConfig(BaseModel):
    broker_type: str = "simulated"  # simulated / ctp / xtp
    account_id: str = ""
    gateway_addr: str = ""
    auth_code: str = ""
    app_id: str = ""
    extra: dict = {}


def _load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"broker_type": "simulated", "account_id": "", "gateway_addr": "", "auth_code": "", "app_id": "", "extra": {}}


def _save_config(data: dict):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


BROKER_TYPES = [
    {"value": "simulated", "label": "模拟盘", "description": "使用内置模拟撮合引擎"},
    {"value": "ctp", "label": "CTP (期货)", "description": "综合交易平台，支持期货/期权", "status": "桩代码"},
    {"value": "xtp", "label": "XTP (股票)", "description": "中泰证券极速交易接口", "status": "桩代码"},
]


@router.get("/types")
async def get_broker_types():
    """获取支持的券商类型"""
    return BROKER_TYPES


@router.get("")
async def get_config():
    """获取当前券商配置"""
    config = _load_config()
    if config.get("auth_code"):
        config["auth_code"] = "***"
    return config


@router.put("")
async def update_config(req: BrokerConfig):
    """更新券商配置"""
    data = req.model_dump()
    _save_config(data)
    logger.info(f"券商配置已更新: broker_type={data['broker_type']}")
    # 返回时 mask auth_code，防止凭据泄露
    response_data = data.copy()
    if response_data.get("auth_code"):
        response_data["auth_code"] = "***"
    return {"message": "配置已保存", "config": response_data}


@router.post("/test")
async def test_connection():
    """测试券商连接"""
    config = _load_config()
    broker_type = config.get("broker_type", "simulated")

    if broker_type == "simulated":
        return {"success": True, "message": "模拟盘连接正常", "type": "simulated"}

    if broker_type == "ctp":
        try:
            from engine.brokers.ctp_gateway import CTPConfig, CTPGateway
            ctp_config = CTPConfig(
                front_addr=config.get("gateway_addr", ""),
                investor_id=config.get("account_id", ""),
                auth_code=config.get("auth_code", ""),
                app_id=config.get("app_id", ""),
            )
            gateway = CTPGateway(ctp_config)
            success = gateway.connect()
            return {
                "success": success,
                "message": "CTP 连接成功（桩实现）" if success else "CTP 连接失败",
                "type": "ctp",
                "stub": True,
            }
        except Exception as e:
            return {"success": False, "message": f"CTP 连接异常: {e}", "type": "ctp"}

    if broker_type == "xtp":
        try:
            from engine.brokers.xtp_gateway import XTPConfig, XTPGateway
            xtp_config = XTPConfig(
                trade_server_ip=config.get("gateway_addr", ""),
                account_id=config.get("account_id", ""),
                auth_code=config.get("auth_code", ""),
            )
            gateway = XTPGateway(xtp_config)
            success = gateway.connect()
            return {
                "success": success,
                "message": "XTP 连接成功（桩实现）" if success else "XTP 连接失败",
                "type": "xtp",
                "stub": True,
            }
        except Exception as e:
            return {"success": False, "message": f"XTP 连接异常: {e}", "type": "xtp"}

    return {"success": False, "message": f"未知券商类型: {broker_type}"}


@router.get("/gateway-info")
async def get_gateway_info():
    """获取各券商网关的接口信息（桩代码说明）"""
    return {
        "gateways": {
            "ctp": {
                "name": "CTP 综合交易平台",
                "vendor": "上期技术",
                "asset_types": ["期货", "期权"],
                "protocol": "CTP API (.so/.dll)",
                "connection_flow": [
                    "1. 加载 libthosttraderapi_se.so",
                    "2. 创建 TraderApi 实例",
                    "3. 注册 Spi 回调",
                    "4. RegisterFront + Init",
                    "5. ReqUserLogin 登录",
                    "6. ReqSettlementInfoConfirm 确认结算",
                    "7. 查询账户/持仓",
                ],
                "status": "桩代码已就绪，需链接 CTP 动态库",
                "config_fields": [
                    {"name": "broker_id", "label": "期货公司代码", "required": True},
                    {"name": "investor_id", "label": "投资者账号", "required": True},
                    {"name": "front_addr", "label": "前置地址", "required": True, "placeholder": "tcp://180.168.146.187:10130"},
                    {"name": "auth_code", "label": "认证码", "required": True, "secret": True},
                    {"name": "app_id", "label": "AppID", "required": True},
                ],
            },
            "xtp": {
                "name": "XTP 极速交易平台",
                "vendor": "中泰证券",
                "asset_types": ["股票", "ETF", "可转债"],
                "protocol": "XTP API (.so/.dll)",
                "connection_flow": [
                    "1. 加载 libxtptraderapi.so",
                    "2. 创建 TraderApi 实例",
                    "3. 注册 Spi 回调",
                    "4. subscribePublicTopic / subscribePrivateTopic",
                    "5. login 登录",
                    "6. 查询账户/持仓",
                ],
                "status": "桩代码已就绪，需链接 XTP 动态库",
                "config_fields": [
                    {"name": "account_id", "label": "资金账号", "required": True},
                    {"name": "trade_server_ip", "label": "交易服务器IP", "required": True},
                    {"name": "trade_server_port", "label": "交易端口", "required": True},
                    {"name": "auth_code", "label": "认证码", "required": True, "secret": True},
                    {"name": "app_id", "label": "AppID", "required": True},
                ],
            },
        },
    }
