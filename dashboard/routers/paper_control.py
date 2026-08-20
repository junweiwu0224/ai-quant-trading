"""模拟盘控制 API - V2 command-based"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from loguru import logger

from config.settings import DB_DIR
from engine.paper_commands import PaperCommandClient
from engine.operations_store import IdempotencyConflictError

router = APIRouter()


class StartRequest(BaseModel):
    strategy: str = "dual_ma"
    codes: list[str]
    interval: int = 30
    cash: float = 50_000
    enable_risk: bool = True
    account_id: str = "paper-default"
    params: Optional[dict] = None
    custom_code: Optional[str] = None

    @field_validator("enable_risk")
    @classmethod
    def require_risk(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("Paper 模拟盘必须启用风控")
        return value

    @field_validator("account_id")
    @classmethod
    def require_account_id(cls, value: str) -> str:
        value = value.strip()
        if not value or value in {".", ".."} or "/" in value or "\\" in value:
            raise ValueError("account_id 不能为空且必须是单一路径标识")
        return value


@router.post("/start")
async def start_paper(req: StartRequest):
    """启动模拟盘 (V2: enqueue command)"""
    if not req.codes:
        raise HTTPException(400, "股票代码不能为空")
    try:
        client = PaperCommandClient(DB_DIR / "operations.db")
        acceptance = client.enqueue_start(
            account_id=req.account_id,
            strategy_name=req.strategy,
            codes=req.codes,
            interval_seconds=req.interval,
            initial_cash=req.cash,
            params=req.params,
            custom_code=req.custom_code,
        )
        client.close()
        return {
            "message": "模拟盘启动命令已提交",
            "command_id": acceptance.command.id,
            "task_id": acceptance.task.id,
            "status": acceptance.task.status,
        }
    except IdempotencyConflictError:
        raise HTTPException(409, "相同 idempotency key 但不同配置的启动请求")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/stop")
async def stop_paper(account_id: str = "paper-default"):
    """停止模拟盘 (V2: enqueue command)"""
    try:
        client = PaperCommandClient(DB_DIR / "operations.db")
        acceptance = client.enqueue_stop(account_id=account_id)
        client.close()
        return {
            "message": "模拟盘停止命令已提交",
            "command_id": acceptance.command.id,
            "task_id": acceptance.task.id,
            "status": acceptance.task.status,
        }
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/status")
async def get_paper_status(account_id: str = "paper-default"):
    """获取模拟盘状态 (V2: stub - 实际状态由 PaperWorker 管理)"""
    # V2: 应该查询 PaperRuntimeStore 和 OperationsStore
    # 当前返回兼容性存根，避免前端崩溃
    return {
        "running": False,
        "config": None,
        "uptime": None,
        "equity": None,
        "cash": None,
        "positions": {},
        "trade_count": 0,
        "message": "V2: 状态由 PaperWorker 管理，使用 PaperRiskView 查看",
    }


@router.post("/reset")
async def reset_paper(account_id: str = "paper-default", initial_cash: float = 50_000.0):
    """重置模拟盘状态 (V2: enqueue command)"""
    try:
        client = PaperCommandClient(DB_DIR / "operations.db")
        acceptance = client.enqueue_reset(
            account_id=account_id,
            initial_cash=initial_cash,
        )
        client.close()
        return {
            "message": "模拟盘重置命令已提交",
            "command_id": acceptance.command.id,
            "task_id": acceptance.task.id,
            "status": acceptance.task.status,
        }
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/trades")
async def get_paper_trades(account_id: str = "paper-default"):
    """获取模拟盘交易历史 (V2: stub)"""
    return {"trades": [], "total": 0, "message": "V2: 使用专用交易查询 API"}


@router.get("/equity-curve")
async def get_equity_curve(account_id: str = "paper-default"):
    """获取模拟盘权益曲线 (V2: stub)"""
    return {"curve": [], "message": "V2: 使用专用权益查询 API"}
