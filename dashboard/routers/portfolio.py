"""持仓与风控 API"""
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
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


@router.get("/snapshot", response_model=PortfolioSnapshot)
async def get_portfolio():
    """获取当前持仓快照"""
    state = _load_paper_state()
    if not state:
        return PortfolioSnapshot()

    positions = []
    total_mv = 0
    for code, vol in state.get("positions", {}).items():
        avg_price = state.get("avg_prices", {}).get(code, 0)
        mv = avg_price * vol
        total_mv += mv
        positions.append(PositionInfo(
            code=code,
            volume=vol,
            avg_price=round(avg_price, 3),
            current_price=round(avg_price, 3),  # 无实时行情时用均价
            market_value=round(mv, 2),
            pnl=0,
            pnl_pct=0,
        ))

    cash = state.get("cash", 0)
    total_equity = cash + total_mv

    return PortfolioSnapshot(
        cash=round(cash, 2),
        market_value=round(total_mv, 2),
        total_equity=round(total_equity, 2),
        positions=positions,
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
