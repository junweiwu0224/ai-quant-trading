"""系统状态与策略管理 API"""
from fastapi import APIRouter

from data.storage import DataStorage

router = APIRouter()
storage = DataStorage()


@router.get("/status")
async def get_system_status():
    """获取系统模块状态"""
    stock_count = 0
    data_range = None
    try:
        codes = storage.get_all_stock_codes()
        stock_count = len(codes)
        if codes:
            from datetime import date
            latest = storage.get_latest_date(codes[0])
            if latest:
                data_range = str(latest)
    except Exception:
        pass

    return {
        "modules": [
            {"name": "数据层", "desc": "AKShare 采集 + SQLite 存储", "status": "ok"},
            {"name": "回测引擎", "desc": "策略模板 + 3 个内置策略", "status": "ok"},
            {"name": "AI Alpha", "desc": "因子库 + LightGBM + Optuna", "status": "ok"},
            {"name": "风控模块", "desc": "仓位管理 + 止损止盈 + 监控", "status": "ok"},
            {"name": "模拟盘", "desc": "实时行情 + 虚拟下单", "status": "ok"},
            {"name": "可视化面板", "desc": "FastAPI + Jinja2 + Chart.js", "status": "current"},
        ],
        "db_stats": {
            "stock_count": stock_count,
            "latest_date": data_range,
        },
    }


@router.get("/strategies")
async def list_strategies():
    """返回策略详情"""
    return [
        {
            "name": "dual_ma",
            "label": "双均线策略",
            "type": "趋势",
            "description": "短期均线上穿长期均线买入，下穿卖出。参数：short_window=5, long_window=20",
            "params": {"short_window": 5, "long_window": 20},
        },
        {
            "name": "bollinger",
            "label": "布林带策略",
            "type": "均值回归",
            "description": "价格触及下轨买入，触及上轨卖出。参数：window=20, num_std=2",
            "params": {"window": 20, "num_std": 2},
        },
        {
            "name": "momentum",
            "label": "动量策略",
            "type": "趋势",
            "description": "基于 N 日收益率动量信号交易。参数：lookback=20, threshold=0.05",
            "params": {"lookback": 20, "threshold": 0.05},
        },
    ]


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

    # 计算单票最大占比
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
