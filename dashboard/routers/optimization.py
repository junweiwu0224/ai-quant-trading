"""参数优化 API"""
import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from loguru import logger
from pydantic import BaseModel

from engine.backtest_engine import BacktestConfig
from engine.optimization_engine import (
    STRATEGY_PARAM_RANGES,
    METRICS,
    grid_search,
    optuna_search,
    sensitivity_analysis,
)
from strategy.strategies import STRATEGIES

router = APIRouter()


class OptimizeRequest(BaseModel):
    strategy: str = "dual_ma"
    codes: list[str] = ["000001"]
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    initial_cash: float = 100000
    commission_rate: float = 0.0003
    stamp_tax_rate: float = 0.001
    slippage: float = 0.002
    metric: str = "sharpe_ratio"
    method: str = "grid_search"
    n_trials: int = Query(default=50, ge=1, le=200)
    param_ranges: Optional[dict] = None


class SensitivityRequest(BaseModel):
    strategy: str = "dual_ma"
    codes: list[str] = ["000001"]
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    initial_cash: float = 100000
    commission_rate: float = 0.0003
    stamp_tax_rate: float = 0.001
    slippage: float = 0.002
    metric: str = "sharpe_ratio"
    param_x: str = "short_window"
    param_y: str = "long_window"


@router.get("/param-ranges/{strategy}")
async def get_param_ranges(strategy: str):
    """获取策略的默认参数范围"""
    if strategy not in STRATEGY_PARAM_RANGES:
        return {"error": "未知策略"}
    return {
        "params": STRATEGY_PARAM_RANGES[strategy],
        "metrics": METRICS,
    }


@router.post("/run")
async def run_optimization(req: OptimizeRequest):
    """运行参数优化（同步，适合小规模搜索）"""
    if req.strategy not in STRATEGIES:
        return {"error": "未知策略"}

    strategy_cls = STRATEGIES[req.strategy]
    param_ranges = req.param_ranges or STRATEGY_PARAM_RANGES.get(req.strategy, {})
    if not param_ranges:
        return {"error": "无参数范围"}

    config = BacktestConfig(
        initial_cash=req.initial_cash,
        commission_rate=req.commission_rate,
        stamp_tax_rate=req.stamp_tax_rate,
        slippage=req.slippage,
    )

    if req.method == "optuna":
        result = optuna_search(
            strategy_cls, param_ranges, req.codes,
            req.start_date, req.end_date, config,
            metric=req.metric, n_trials=req.n_trials,
        )
    else:
        result = grid_search(
            strategy_cls, param_ranges, req.codes,
            req.start_date, req.end_date, config,
            metric=req.metric,
        )

    return {
        "best_params": result.best_params,
        "best_metric": result.best_metric,
        "metric_name": result.metric_name,
        "total_trials": result.total_trials,
        "elapsed_seconds": result.elapsed_seconds,
        "results": result.results,
    }


@router.post("/sensitivity")
async def run_sensitivity(req: SensitivityRequest):
    """参数敏感性分析（热力图数据）"""
    if req.strategy not in STRATEGIES:
        return {"error": "未知策略"}

    strategy_cls = STRATEGIES[req.strategy]
    param_ranges = STRATEGY_PARAM_RANGES.get(req.strategy, {})
    if req.param_x not in param_ranges or req.param_y not in param_ranges:
        return {"error": "参数名无效"}

    config = BacktestConfig(
        initial_cash=req.initial_cash,
        commission_rate=req.commission_rate,
        stamp_tax_rate=req.stamp_tax_rate,
        slippage=req.slippage,
    )

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, lambda: sensitivity_analysis(
        strategy_cls, param_ranges, req.codes,
        req.start_date, req.end_date, config,
        metric=req.metric,
        param_x=req.param_x,
        param_y=req.param_y,
    ))

    return result


@router.websocket("/ws/run")
async def ws_optimization(ws: WebSocket):
    """WebSocket 参数优化（带进度推送）"""
    await ws.accept()
    try:
        raw = await ws.receive_text()
        req = json.loads(raw)

        strategy_name = req.get("strategy", "dual_ma")
        if strategy_name not in STRATEGIES:
            await ws.send_json({"type": "error", "message": f"未知策略: {strategy_name}"})
            await ws.close()
            return

        strategy_cls = STRATEGIES[strategy_name]
        param_ranges = req.get("param_ranges") or STRATEGY_PARAM_RANGES.get(strategy_name, {})
        if not param_ranges:
            await ws.send_json({"type": "error", "message": "无参数范围"})
            await ws.close()
            return

        config = BacktestConfig(
            initial_cash=req.get("initial_cash", 100000),
            commission_rate=req.get("commission_rate", 0.0003),
            stamp_tax_rate=req.get("stamp_tax_rate", 0.001),
            slippage=req.get("slippage", 0.002),
        )
        metric = req.get("metric", "sharpe_ratio")
        method = req.get("method", "grid_search")
        n_trials = req.get("n_trials", 50)

        def on_progress(progress):
            try:
                asyncio.get_running_loop().create_task(ws.send_json({
                    "type": "progress",
                    "progress": round(progress, 4),
                }))
            except Exception:
                pass

        loop = asyncio.get_running_loop()

        if method == "optuna":
            result = await loop.run_in_executor(None, lambda: optuna_search(
                strategy_cls, param_ranges, req.get("codes", ["000001"]),
                req["start_date"], req["end_date"], config,
                metric=metric, n_trials=n_trials,
                progress_callback=on_progress,
            ))
        else:
            result = await loop.run_in_executor(None, lambda: grid_search(
                strategy_cls, param_ranges, req.get("codes", ["000001"]),
                req["start_date"], req["end_date"], config,
                metric=metric,
                progress_callback=on_progress,
            ))

        await ws.send_json({
            "type": "complete",
            "data": {
                "best_params": result.best_params,
                "best_metric": result.best_metric,
                "metric_name": result.metric_name,
                "total_trials": result.total_trials,
                "elapsed_seconds": result.elapsed_seconds,
                "results": result.results,
            },
        })
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"优化WebSocket异常: {e}")
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass
