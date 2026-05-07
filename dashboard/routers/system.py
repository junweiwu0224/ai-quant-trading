"""系统状态与策略管理 API"""
from fastapi import APIRouter

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
    except Exception:
        pass

    paper_running = False
    try:
        from dashboard.routers.paper_control import _manager
        paper_running = _manager.is_running
    except Exception:
        pass

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


@router.get("/risk/rules")
async def get_risk_rules():
    """返回风控规则及当前状态"""
    state = None
    try:
        import json
        from pathlib import Path
        from config.settings import LOG_DIR
        state_file = LOG_DIR / "paper" / "portfolio_state.json"
        if state_file.exists():
            state = json.loads(state_file.read_text())
    except Exception:
        pass

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
