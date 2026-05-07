"""持仓与风控 API"""
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from loguru import logger
from pydantic import BaseModel

from config.settings import LOG_DIR

router = APIRouter()


class PositionInfo(BaseModel):
    code: str
    volume: int
    avg_price: float
    current_price: float = 0
    market_value: float = 0
    pnl: float = 0
    pnl_pct: float = 0


class PortfolioSnapshot(BaseModel):
    cash: float = 0
    market_value: float = 0
    total_equity: float = 0
    positions: list[PositionInfo] = []
    total_pnl: float = 0
    total_pnl_pct: float = 0


def _load_paper_state(state_dir: str = str(LOG_DIR / "paper")) -> Optional[dict]:
    """加载模拟盘状态"""
    state_file = Path(state_dir) / "portfolio_state.json"
    if not state_file.exists():
        return None
    try:
        return json.loads(state_file.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _load_trades_today(state_dir: str = str(LOG_DIR / "paper")) -> list[dict]:
    """加载今日交易记录"""
    from datetime import datetime
    log_file = Path(state_dir) / f"trades_{datetime.now():%Y%m%d}.jsonl"
    if not log_file.exists():
        return []
    trades = []
    for line in log_file.read_text().strip().split("\n"):
        if line:
            try:
                trades.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return trades


def _get_current_price(code: str) -> float:
    """获取最新收盘价"""
    try:
        from data.storage import DataStorage
        storage = DataStorage()
        df = storage.get_stock_daily(code)
        if not df.empty:
            return float(df.iloc[-1]["close"])
    except Exception:
        pass
    return 0.0


@router.get("/snapshot", response_model=PortfolioSnapshot)
async def get_portfolio():
    """获取当前持仓快照"""
    state = _load_paper_state()
    if not state:
        return PortfolioSnapshot()

    positions = []
    total_mv = 0
    total_pnl = 0
    for code, vol in state.get("positions", {}).items():
        avg_price = state.get("avg_prices", {}).get(code, 0)
        current_price = _get_current_price(code)
        if current_price <= 0:
            current_price = avg_price

        mv = current_price * vol
        pnl = (current_price - avg_price) * vol
        pnl_pct = (current_price - avg_price) / avg_price if avg_price > 0 else 0
        total_mv += mv
        total_pnl += pnl

        positions.append(PositionInfo(
            code=code,
            volume=vol,
            avg_price=round(avg_price, 3),
            current_price=round(current_price, 3),
            market_value=round(mv, 2),
            pnl=round(pnl, 2),
            pnl_pct=round(pnl_pct, 4),
        ))

    cash = state.get("cash", 0)
    total_equity = cash + total_mv
    total_pnl_pct = total_pnl / (total_equity - total_pnl) if (total_equity - total_pnl) > 0 else 0

    return PortfolioSnapshot(
        cash=round(cash, 2),
        market_value=round(total_mv, 2),
        total_equity=round(total_equity, 2),
        positions=positions,
        total_pnl=round(total_pnl, 2),
        total_pnl_pct=round(total_pnl_pct, 4),
    )


@router.get("/trades")
async def get_trades():
    """获取今日交易记录"""
    return _load_trades_today()


@router.get("/risk")
async def get_risk():
    """获取风控状态"""
    state = _load_paper_state()
    if not state:
        return {"status": "无数据"}

    cash = state.get("cash", 0)
    positions = state.get("positions", {})
    total_mv = sum(state.get("avg_prices", {}).get(c, 0) * v for c, v in positions.items())
    total_equity = cash + total_mv

    position_details = []
    for code, vol in positions.items():
        avg = state.get("avg_prices", {}).get(code, 0)
        mv = avg * vol
        pct = mv / total_equity if total_equity > 0 else 0
        position_details.append({
            "code": code,
            "volume": vol,
            "value": round(mv, 2),
            "pct": round(pct, 4),
        })

    return {
        "total_equity": round(total_equity, 2),
        "cash": round(cash, 2),
        "cash_pct": round(cash / total_equity, 4) if total_equity > 0 else 0,
        "position_count": len(positions),
        "positions": position_details,
    }


@router.get("/equity-history")
async def get_equity_history():
    """获取权益历史数据"""
    history_file = LOG_DIR / "paper" / "equity_history.jsonl"
    if not history_file.exists():
        return []
    records = []
    for line in history_file.read_text().strip().split("\n"):
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


@router.get("/industry-distribution")
async def get_industry_distribution():
    """获取持仓行业分布"""
    state = _load_paper_state()
    if not state:
        return []

    positions = state.get("positions", {})
    if not positions:
        return []

    try:
        from data.storage import DataStorage
        storage = DataStorage()
        stock_list = storage.get_stock_list()
        if stock_list.empty:
            return []

        industry_map = dict(zip(stock_list["code"], stock_list["industry"]))

        industry_data = {}
        for code, vol in positions.items():
            avg_price = state.get("avg_prices", {}).get(code, 0)
            current_price = _get_current_price(code)
            if current_price <= 0:
                current_price = avg_price
            mv = current_price * vol

            industry = industry_map.get(code, "未知") or "未知"
            if industry not in industry_data:
                industry_data[industry] = {"industry": industry, "count": 0, "value": 0}
            industry_data[industry]["count"] += 1
            industry_data[industry]["value"] += mv

        return sorted(industry_data.values(), key=lambda x: x["value"], reverse=True)
    except Exception as e:
        logger.error(f"行业分布查询失败: {e}")
        return []
