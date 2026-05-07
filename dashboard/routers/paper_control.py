"""模拟盘控制 API"""
import threading
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter()


class StartRequest(BaseModel):
    strategy: str = "dual_ma"
    codes: list[str]
    interval: int = 30
    cash: float = 1_000_000
    enable_risk: bool = True
    params: Optional[dict] = None
    custom_code: Optional[str] = None


class PaperManager:
    """模拟盘进程管理器（单例）"""

    def __init__(self):
        self._engine = None
        self._thread: Optional[threading.Thread] = None
        self._config: Optional[dict] = None
        self._start_time: Optional[float] = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, req: StartRequest):
        if self.is_running:
            raise RuntimeError("模拟盘已在运行中")

        from engine.paper_engine import PaperEngine, PaperConfig
        from strategy.dual_ma import DualMAStrategy
        from strategy.bollinger import BollingerStrategy
        from strategy.momentum import MomentumStrategy
        from strategy.loader import load_strategy_from_code
        from config.settings import LOG_DIR

        strategy_map = {
            "dual_ma": DualMAStrategy,
            "bollinger": BollingerStrategy,
            "momentum": MomentumStrategy,
        }

        # 优先使用自定义代码
        if req.custom_code:
            strategy = load_strategy_from_code(req.custom_code, params=req.params)
            if not strategy:
                raise ValueError("自定义策略代码加载失败")
        else:
            cls = strategy_map.get(req.strategy)
            if not cls:
                raise ValueError(f"未知策略: {req.strategy}")
            strategy = cls(**(req.params or {}))

        config = PaperConfig(
            interval_seconds=req.interval,
            state_dir=str(LOG_DIR / "paper"),
            enable_risk=req.enable_risk,
        )

        engine = PaperEngine(strategy=strategy, codes=req.codes, config=config)
        # 恢复或重置资金
        if not engine._state_mgr.load():
            engine._portfolio.cash = req.cash

        self._engine = engine
        self._config = {
            "strategy": req.strategy,
            "codes": req.codes,
            "interval": req.interval,
            "cash": req.cash,
            "enable_risk": req.enable_risk,
        }
        self._start_time = time.time()

        def _run():
            try:
                engine.run_loop()
            except Exception as e:
                logger.error(f"模拟盘线程异常: {e}")

        self._thread = threading.Thread(target=_run, daemon=True, name="paper-engine")
        self._thread.start()
        logger.info(f"模拟盘启动: {req.strategy} {req.codes}")

    def stop(self):
        if not self.is_running:
            return
        if self._engine:
            self._engine.stop()
        if self._thread:
            self._thread.join(timeout=10)
        self._thread = None
        logger.info("模拟盘已停止")

    def reset(self):
        self.stop()
        from config.settings import LOG_DIR
        state_file = LOG_DIR / "paper" / "portfolio_state.json"
        if state_file.exists():
            state_file.unlink()
        self._engine = None
        self._config = None
        self._start_time = None
        logger.info("模拟盘状态已重置")

    def get_status(self) -> dict:
        if not self.is_running:
            return {
                "running": False,
                "config": self._config,
                "uptime": None,
                "equity": None,
                "cash": None,
                "positions": {},
                "trade_count": 0,
            }

        engine = self._engine
        portfolio = engine.portfolio if engine else None
        equity = portfolio.cash if portfolio else 0
        positions = dict(portfolio.positions) if portfolio else {}

        # 从 trade log 获取今日交易数
        trade_count = 0
        if engine:
            trade_count = len(engine.trade_log.today_trades)

        uptime = time.time() - self._start_time if self._start_time else 0

        return {
            "running": True,
            "config": self._config,
            "uptime": int(uptime),
            "equity": round(equity, 2),
            "cash": round(portfolio.cash, 2) if portfolio else 0,
            "positions": positions,
            "trade_count": trade_count,
        }


_manager = PaperManager()


@router.post("/start")
async def start_paper(req: StartRequest):
    """启动模拟盘"""
    if not req.codes:
        raise HTTPException(400, "股票代码不能为空")
    try:
        _manager.start(req)
        return {"message": "模拟盘已启动", "config": _manager._config}
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/stop")
async def stop_paper():
    """停止模拟盘"""
    if not _manager.is_running:
        return {"message": "模拟盘未在运行"}
    _manager.stop()
    return {"message": "模拟盘已停止"}


@router.get("/status")
async def get_paper_status():
    """获取模拟盘状态"""
    return _manager.get_status()


@router.post("/reset")
async def reset_paper():
    """重置模拟盘状态"""
    _manager.reset()
    return {"message": "模拟盘已重置"}


@router.get("/trades")
async def get_paper_trades():
    """获取模拟盘交易历史"""
    if not _manager.is_running or not _manager._engine:
        return {"trades": [], "total": 0}

    trades = _manager._engine.trade_log.today_trades
    return {"trades": trades, "total": len(trades)}


@router.get("/equity-curve")
async def get_equity_curve():
    """获取模拟盘权益曲线"""
    if not _manager.is_running or not _manager._engine:
        return {"curve": []}

    # 从交易日志中提取权益曲线
    trades = _manager._engine.trade_log.today_trades
    curve = []
    for t in trades:
        if "equity" in t:
            curve.append({
                "time": t.get("time", ""),
                "equity": t["equity"],
            })
    return {"curve": curve}
