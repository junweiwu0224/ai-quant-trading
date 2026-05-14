"""条件单 API"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from engine.conditional_order import ConditionalOrderEngine

router = APIRouter()
_engine: ConditionalOrderEngine | None = None


def get_engine() -> ConditionalOrderEngine:
    global _engine
    if _engine is None:
        _engine = ConditionalOrderEngine()
    return _engine


class ConditionalOrderCreate(BaseModel):
    alert_rule_id: int = Field(..., gt=0)
    code: str = Field(..., pattern="^\\d{6}$")
    direction: str = Field(..., pattern="^(buy|sell)$")
    order_type: str = Field(default="market", pattern="^(market|limit)$")
    price: Optional[float] = Field(default=None, gt=0)
    volume: int = Field(..., gt=0)
    max_amount: float = Field(default=0, ge=0)
    enabled: bool = False
    cooldown: int = Field(default=300, ge=0)

    @model_validator(mode="after")
    def validate_limit_price(self):
        if self.volume % 100 != 0:
            raise ValueError("数量必须是100的整数倍")
        if self.order_type == "limit" and self.price is None:
            raise ValueError("限价条件单必须指定价格")
        return self


class ConditionalOrderUpdate(BaseModel):
    alert_rule_id: Optional[int] = Field(default=None, gt=0)
    code: Optional[str] = Field(default=None, pattern="^\\d{6}$")
    direction: Optional[str] = Field(default=None, pattern="^(buy|sell)$")
    order_type: Optional[str] = Field(default=None, pattern="^(market|limit)$")
    price: Optional[float] = Field(default=None, gt=0)
    volume: Optional[int] = Field(default=None, gt=0)
    max_amount: Optional[float] = Field(default=None, ge=0)
    enabled: Optional[bool] = None
    cooldown: Optional[int] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_volume(self):
        if self.volume is not None and self.volume % 100 != 0:
            raise ValueError("数量必须是100的整数倍")
        return self


@router.get("/rules")
async def list_rules():
    return {"success": True, "data": [rule.to_dict() for rule in get_engine().list_rules()]}


@router.post("/rules")
async def create_rule(req: ConditionalOrderCreate):
    try:
        rule = get_engine().create_rule(**req.model_dump())
        return {"success": True, "data": rule.to_dict()}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/rules/{rule_id}")
async def update_rule(rule_id: int, req: ConditionalOrderUpdate):
    try:
        updates = {key: value for key, value in req.model_dump().items() if value is not None}
        if not updates:
            return {"success": False, "error": "无更新内容"}
        rule = get_engine().update_rule(rule_id, updates)
        return {"success": True, "data": rule.to_dict()}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: int):
    deleted = get_engine().delete_rule(rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="条件单不存在")
    return {"success": True}


@router.get("/events")
async def list_events(limit: int = Query(default=50, ge=1, le=500)):
    return {"success": True, "data": [event.to_dict() for event in get_engine().list_events(limit)]}
