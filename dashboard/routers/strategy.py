"""策略管理 API"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from strategy.manager import StrategyManager
from strategy.loader import validate_strategy_code, STRATEGY_TEMPLATE

router = APIRouter()
_manager = StrategyManager()


class StrategyRequest(BaseModel):
    name: Optional[str] = None
    label: Optional[str] = None
    type: Optional[str] = "自定义"
    description: Optional[str] = ""
    params: Optional[dict] = {}
    code: Optional[str] = None


class CodeValidationRequest(BaseModel):
    code: str


@router.get("/list")
async def list_strategies():
    """获取所有策略（内置 + 自定义）"""
    return _manager.list_all()


@router.post("")
async def create_strategy(req: StrategyRequest):
    """新增自定义策略"""
    try:
        return _manager.add(req.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.put("/{name}")
async def update_strategy(name: str, req: StrategyRequest):
    """编辑自定义策略"""
    try:
        return _manager.update(name, req.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/{name}")
async def delete_strategy(name: str):
    """删除自定义策略"""
    if not _manager.delete(name):
        raise HTTPException(404, f"策略 {name} 不存在或是内置策略")
    return {"message": "删除成功", "name": name}


@router.get("/template")
async def get_strategy_template():
    """获取策略代码模板"""
    return {"code": STRATEGY_TEMPLATE}


@router.post("/validate-code")
async def validate_code(req: CodeValidationRequest):
    """验证策略代码是否合法"""
    is_valid, error_msg = validate_strategy_code(req.code)
    return {"valid": is_valid, "error": error_msg}
