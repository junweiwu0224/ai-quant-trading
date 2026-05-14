"""模拟盘控制 API"""
import threading
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter()

# ── 内置策略类映射（name → 类） ──
# 新增内置策略只需在此添加一行，无需修改其他代码
_BUILTIN_STRATEGY_CLASSES: dict[str, type] = {}


def _get_builtin_classes() -> dict[str, type]:
    """延迟加载所有内置策略类"""
    if _BUILTIN_STRATEGY_CLASSES:
        return _BUILTIN_STRATEGY_CLASSES

    from strategy.dual_ma import DualMAStrategy
    from strategy.bollinger import BollingerStrategy
    from strategy.momentum import MomentumStrategy
    from strategy.rsi import RSIStrategy
    from strategy.macd import MACDStrategy
    from strategy.kdj import KDJStrategy
    from strategy.qlib_signal import QlibSignalStrategy

    _BUILTIN_STRATEGY_CLASSES.update({
        "dual_ma": DualMAStrategy,
        "bollinger": BollingerStrategy,
        "momentum": MomentumStrategy,
        "rsi": RSIStrategy,
        "macd": MACDStrategy,
        "kdj": KDJStrategy,
        "qlib_signal": QlibSignalStrategy,
    })
    return _BUILTIN_STRATEGY_CLASSES


def _filter_params(cls: type, params: dict) -> dict:
    """只保留策略构造函数接受的参数"""
    import inspect
    sig = inspect.signature(cls.__init__)
    valid = {p for p in sig.parameters if p != "self"}
    return {k: v for k, v in params.items() if k in valid}


def _create_builtin_strategy(name: str, cls: type, params: dict):
    """创建内置策略实例，特殊策略需要额外初始化"""
    from config.settings import QLIB_SERVICE_URL
    from strategy.qlib_signal import QlibSignalStrategy

    filtered = _filter_params(cls, params)
    # qlib_signal 需要从 qlib 服务加载预测分数
    if name == "qlib_signal":
        return QlibSignalStrategy.from_service(
            service_url=QLIB_SERVICE_URL,
            **filtered,
        )
    return cls(**filtered)


class StartRequest(BaseModel):
    strategy: str = "dual_ma"
    codes: list[str]
    interval: int = 30
    cash: float = 50_000
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
        from strategy.loader import load_strategy_from_code
        from strategy.manager import StrategyManager
        from config.settings import LOG_DIR

        builtin_classes = _get_builtin_classes()
        strategy_mgr = StrategyManager()

        # 优先使用自定义代码
        if req.custom_code:
            strategy = load_strategy_from_code(req.custom_code, params=req.params)
            if not strategy:
                raise ValueError("自定义策略代码加载失败")
        else:
            # 从策略管理系统查找策略
            strategy_info = strategy_mgr.get(req.strategy)
            if not strategy_info:
                raise ValueError(f"未知策略: {req.strategy}")

            if strategy_info.get("code"):
                # 自定义代码策略：从管理系统加载
                merged_params = {**(strategy_info.get("params") or {}), **(req.params or {})}
                strategy = load_strategy_from_code(strategy_info["code"], params=merged_params)
                if not strategy:
                    raise ValueError(f"自定义策略 {req.strategy} 代码加载失败")
            else:
                # 内置策略：使用管理系统保存的参数覆盖 + 请求参数
                cls = builtin_classes.get(req.strategy)
                if not cls:
                    raise ValueError(f"未找到策略类: {req.strategy}")
                # 参数优先级：请求参数 > 管理系统覆盖 > 默认值
                merged_params = {**(strategy_info.get("params") or {}), **(req.params or {})}
                strategy = _create_builtin_strategy(req.strategy, cls, merged_params)

        config = PaperConfig(
            interval_seconds=req.interval,
            state_dir=str(LOG_DIR / "paper"),
            enable_risk=req.enable_risk,
        )

        engine = PaperEngine(strategy=strategy, codes=req.codes, config=config)
        # 设置策略名称（用于 portfolio.strategies 记录）
        engine.strategy_name = req.strategy
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
        import json
        from config.settings import LOG_DIR
        state_file = LOG_DIR / "paper" / "portfolio_state.json"
        # 写入干净的初始状态（5万现金，无持仓）
        clean_state = {
            "cash": 50000.0,
            "positions": {},
            "avg_prices": {},
            "trade_count": 0,
            "entry_dates": {},
        }
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(clean_state, indent=2, ensure_ascii=False))
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
        positions = dict(portfolio.positions) if portfolio else {}

        # 从 QuoteService 获取当前价格，计算总权益（现金 + 持仓市值）
        equity = portfolio.cash if portfolio else 0
        if portfolio and positions:
            try:
                from data.collector.quote_service import get_quote_service
                qs = get_quote_service()
                prices = {}
                for code in positions:
                    q = qs.get_quote(code)
                    if q:
                        prices[code] = q.price
                equity = portfolio.get_total_equity(prices)
            except Exception:
                pass  # 获取行情失败时回退到现金

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
