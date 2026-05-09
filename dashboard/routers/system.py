"""系统状态与策略管理 API"""
import asyncio
import json

from fastapi import APIRouter
from loguru import logger

from data.storage.storage import DataStorage

router = APIRouter()
storage = DataStorage()


@router.get("/status")
async def get_system_status():
    """获取系统状态"""
    stock_count = 0
    watchlist_count = 0
    data_range = None
    try:
        codes = storage.get_all_stock_codes()
        stock_count = len(codes)
        watchlist_count = len(storage.get_watchlist())
        if codes:
            from datetime import date
            latest = storage.get_latest_date(codes[0])
            if latest:
                data_range = str(latest)
    except Exception as e:
        logger.warning(f"获取系统状态失败: {e}")

    paper_running = False
    try:
        from dashboard.routers.paper_control import _manager
        paper_running = _manager.is_running
    except Exception as e:
        logger.warning(f"获取模拟盘状态失败: {e}")

    return {
        "db_stats": {
            "stock_count": stock_count,
            "watchlist_count": watchlist_count,
            "latest_date": data_range,
        },
        "paper_running": paper_running,
        "ai_model": "LightGBM + XGBoost",
    }


@router.get("/strategies")
async def list_strategies():
    """返回策略列表（委托给 StrategyManager）"""
    from strategy.manager import StrategyManager
    return StrategyManager().list_all()


@router.get("/strategies/export")
async def export_strategies(name: str = ""):
    """导出策略为 JSON（全部或单个）"""
    from strategy.manager import StrategyManager
    mgr = StrategyManager()
    if name:
        data = mgr.export_strategy(name)
        if not data:
            return {"success": False, "error": f"策略 {name} 不存在"}
        return {"success": True, "data": data}
    return {"success": True, "data": mgr.export_all()}


@router.post("/strategies/import")
async def import_strategies(data: dict):
    """导入策略 JSON"""
    from strategy.manager import StrategyManager
    try:
        mgr = StrategyManager()
        overwrite = data.get("overwrite", False)
        result = mgr.import_strategies(data, overwrite=overwrite)
        return {"success": True, **result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/strategies/compare")
async def compare_strategy(data: dict):
    """比较策略版本差异"""
    from strategy.manager import StrategyManager
    name = data.get("name", "")
    other = data.get("strategy", {})
    if not name or not other:
        return {"success": False, "error": "缺少策略名称或策略数据"}
    mgr = StrategyManager()
    result = mgr.compare_versions(name, other)
    return {"success": True, **result}


@router.get("/risk/rules")
async def get_risk_rules():
    """返回风控规则及当前状态"""
    state = None
    try:
        from pathlib import Path
        from config.settings import LOG_DIR
        state_file = LOG_DIR / "paper" / "portfolio_state.json"
        if state_file.exists():
            content = await asyncio.to_thread(state_file.read_text)
            state = json.loads(content)
    except Exception as e:
        logger.warning(f"读取风控状态失败: {e}")

    cash = state.get("cash", 0) if state else 0
    positions = state.get("positions", {}) if state else {}
    avg_prices = state.get("avg_prices", {}) if state else {}
    total_mv = sum(avg_prices.get(c, 0) * v for c, v in positions.items())
    total_equity = cash + total_mv

    max_single_pct = 0
    for code, vol in positions.items():
        mv = avg_prices.get(code, 0) * vol
        pct = mv / total_equity if total_equity > 0 else 0
        max_single_pct = max(max_single_pct, pct)

    cash_pct = cash / total_equity if total_equity > 0 else 1.0

    rules = [
        {
            "name": "单票仓位上限",
            "threshold": "20%",
            "current": f"{max_single_pct * 100:.1f}%",
            "status": "ok" if max_single_pct <= 0.2 else "alert",
        },
        {
            "name": "行业集中度",
            "threshold": "40%",
            "current": "--",
            "status": "ok",
        },
        {
            "name": "最大回撤止损",
            "threshold": "15%",
            "current": "--",
            "status": "ok",
        },
        {
            "name": "日亏损限额",
            "threshold": "3%",
            "current": "--",
            "status": "ok",
        },
        {
            "name": "固定止损",
            "threshold": "5%",
            "current": "--",
            "status": "ok",
        },
        {
            "name": "追踪止损",
            "threshold": "8%",
            "current": "--",
            "status": "ok",
        },
    ]
    return rules
