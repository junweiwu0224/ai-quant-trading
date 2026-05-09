"""预警管理 API

端点：
- GET    /api/alerts/rules     — 获取所有规则
- POST   /api/alerts/rules     — 添加规则
- PUT    /api/alerts/rules/{id} — 更新规则
- DELETE /api/alerts/rules/{id} — 删除规则
- GET    /api/alerts/history    — 获取触发历史
- GET    /api/alerts/conditions — 获取可用条件类型
- POST   /api/alerts/reload     — 重新加载规则到引擎
"""
from __future__ import annotations

from fastapi import APIRouter
from loguru import logger
from pydantic import BaseModel

from data.storage import DataStorage

router = APIRouter()
storage = DataStorage()


class AlertRuleCreate(BaseModel):
    code: str
    condition: str
    threshold: float
    name: str = ""
    cooldown: int = 300
    webhook_url: str = ""


class AlertRuleUpdate(BaseModel):
    condition: str | None = None
    threshold: float | None = None
    enabled: bool | None = None
    name: str | None = None
    cooldown: int | None = None
    webhook_url: str | None = None


@router.get("/rules")
async def get_rules():
    """获取所有预警规则"""
    try:
        rules = storage.get_alert_rules()
        return {"success": True, "rules": rules}
    except Exception as e:
        logger.error(f"获取预警规则失败: {e}")
        return {"success": False, "error": str(e), "rules": []}


@router.post("/rules")
async def create_rule(req: AlertRuleCreate):
    """添加预警规则"""
    try:
        rule_id = storage.add_alert_rule(
            code=req.code, condition=req.condition,
            threshold=req.threshold, name=req.name, cooldown=req.cooldown,
            webhook_url=req.webhook_url,
        )
        _reload_engine()
        return {"success": True, "id": rule_id}
    except Exception as e:
        logger.error(f"添加预警规则失败: {e}")
        return {"success": False, "error": str(e)}


@router.put("/rules/{rule_id}")
async def update_rule(rule_id: int, req: AlertRuleUpdate):
    """更新预警规则"""
    try:
        updates = {k: v for k, v in req.model_dump().items() if v is not None}
        if not updates:
            return {"success": False, "error": "无更新内容"}
        ok = storage.update_alert_rule(rule_id, **updates)
        if ok:
            _reload_engine()
            return {"success": True}
        return {"success": False, "error": "规则不存在"}
    except Exception as e:
        logger.error(f"更新预警规则失败: {e}")
        return {"success": False, "error": str(e)}


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: int):
    """删除预警规则"""
    try:
        ok = storage.delete_alert_rule(rule_id)
        if ok:
            _reload_engine()
            return {"success": True}
        return {"success": False, "error": "规则不存在"}
    except Exception as e:
        logger.error(f"删除预警规则失败: {e}")
        return {"success": False, "error": str(e)}


@router.get("/history")
async def get_history(limit: int = 50):
    """获取最近触发的预警"""
    try:
        from dashboard.routers.realtime_quotes import _get_alert_engine
        engine = _get_alert_engine()
        history = engine.get_recent_alerts(limit)
        return {"success": True, "alerts": history}
    except Exception as e:
        logger.error(f"获取预警历史失败: {e}")
        return {"success": False, "error": str(e), "alerts": []}


@router.get("/conditions")
async def get_conditions():
    """获取可用条件类型"""
    from engine.alert_engine import AlertEngine
    return {"conditions": AlertEngine.get_condition_labels()}


@router.post("/reload")
async def reload_rules():
    """重新加载规则到引擎"""
    try:
        _reload_engine()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _reload_engine():
    """重新加载规则到内存引擎"""
    try:
        from dashboard.routers.realtime_quotes import _get_alert_engine, _load_alert_rules
        _get_alert_engine()
        _load_alert_rules()
    except Exception as e:
        logger.warning(f"重新加载预警引擎失败: {e}")
