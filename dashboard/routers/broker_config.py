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
    {"value": "ctp", "label": "CTP (期货)", "description": "综合交易平台，支持期货/期权"},
    {"value": "xtp", "label": "XTP (股票)", "description": "中泰证券极速交易接口"},
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
    """测试券商连接（模拟盘直接返回成功）"""
    config = _load_config()
    if config["broker_type"] == "simulated":
        return {"success": True, "message": "模拟盘连接正常"}
    # 真实券商连接测试需要具体 Gateway 实现
    return {"success": False, "message": f"券商 {config['broker_type']} 的 Gateway 尚未实现"}
