"""条件选股 API

端点：
- POST /api/screener/run     — 执行条件选股
- GET  /api/screener/presets  — 获取预设策略
- GET  /api/screener/fields   — 获取可用字段列表
"""
from __future__ import annotations

from fastapi import APIRouter
from loguru import logger
from pydantic import BaseModel

from alpha.screener import StockScreener

router = APIRouter()
_screener = StockScreener()


# ── 请求模型 ──

class FilterItem(BaseModel):
    field: str
    op: str
    value: object


class ScreenerRequest(BaseModel):
    filters: list[FilterItem] = []
    sort_by: str = "change_pct"
    sort_desc: bool = True
    page: int = 1
    page_size: int = 50


class PresetRunRequest(BaseModel):
    preset_name: str
    sort_by: str = "change_pct"
    sort_desc: bool = True
    page: int = 1
    page_size: int = 50


# ── 端点 ──

@router.post("/run")
async def run_screener(req: ScreenerRequest):
    """执行条件选股"""
    try:
        filters = [f.model_dump() for f in req.filters]
        result = _screener.screen(
            filters=filters,
            sort_by=req.sort_by,
            sort_desc=req.sort_desc,
            page=req.page,
            page_size=req.page_size,
        )
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"选股失败: {e}")
        return {"success": False, "error": "选股执行失败，请稍后重试"}


@router.post("/run-preset")
async def run_preset(req: PresetRunRequest):
    """执行预设策略选股"""
    try:
        presets = _screener.get_presets()
        preset = presets.get(req.preset_name)
        if not preset:
            return {"success": False, "error": f"未找到预设策略: {req.preset_name}"}

        result = _screener.screen(
            filters=preset["filters"],
            sort_by=req.sort_by,
            sort_desc=req.sort_desc,
            page=req.page,
            page_size=req.page_size,
        )
        return {"success": True, "preset": req.preset_name, "desc": preset["desc"], **result}
    except Exception as e:
        logger.error(f"预设选股失败: {e}")
        return {"success": False, "error": "预设策略执行失败"}


@router.get("/presets")
async def get_presets():
    """获取所有预设策略"""
    presets = _screener.get_presets()
    return {
        "presets": [
            {"name": name, "desc": info["desc"], "filters": info["filters"]}
            for name, info in presets.items()
        ]
    }


@router.get("/fields")
async def get_fields():
    """获取可用筛选字段列表"""
    return {"fields": _screener.get_fields()}
