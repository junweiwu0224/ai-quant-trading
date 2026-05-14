"""策略管理 API"""
import itertools
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from strategy.manager import StrategyManager
from strategy.loader import validate_strategy_code, STRATEGY_TEMPLATE

router = APIRouter()
_manager = StrategyManager()


class StrategyRequest(BaseModel):
    name: Optional[str] = None
    label: Optional[str] = None
    type: Optional[str] = "自定义"
    description: Optional[str] = ""
    params: Optional[dict] = {}
    code: Optional[str] = None


class CodeValidationRequest(BaseModel):
    code: str


@router.get("/list")
async def list_strategies():
    """获取所有策略（内置 + 自定义）"""
    return _manager.list_all()


@router.get("/template")
async def get_strategy_template():
    """获取策略代码模板"""
    return {"code": STRATEGY_TEMPLATE}


@router.post("/validate-code")
async def validate_code(req: CodeValidationRequest):
    """验证策略代码是否合法"""
    is_valid, error_msg = validate_strategy_code(req.code)
    return {"valid": is_valid, "error": error_msg}


@router.post("")
async def create_strategy(req: StrategyRequest):
    """新增自定义策略"""
    try:
        return _manager.add(req.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{name}")
async def get_strategy(name: str):
    """获取单个策略详情"""
    s = _manager.get(name)
    if not s:
        raise HTTPException(404, f"策略 {name} 不存在")
    return s


@router.put("/{name}")
async def update_strategy(name: str, req: StrategyRequest):
    """编辑自定义策略"""
    try:
        return _manager.update(name, req.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/{name}")
async def delete_strategy(name: str):
    """删除自定义策略"""
    if not _manager.delete(name):
        raise HTTPException(404, f"策略 {name} 不存在或是内置策略")
    return {"message": "删除成功", "name": name}


@router.post("/{name}/reset")
async def reset_strategy(name: str):
    """重置内置策略参数为默认值"""
    from strategy.manager import BUILTIN_STRATEGIES
    if not any(s["name"] == name for s in BUILTIN_STRATEGIES):
        raise HTTPException(404, f"内置策略 {name} 不存在")
    if name in _manager._overrides:
        del _manager._overrides[name]
        _manager._save()
    return _manager.get(name)


# ── 参数网格搜索 ──


class OptimizeRequest(BaseModel):
    strategy: str
    codes: list[str] = ["000001"]
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    initial_cash: float = 1_000_000
    param_ranges: dict = {}  # {"short_window": [3,5,10], "long_window": [15,20,30]}
    metric: str = "sharpe_ratio"  # 优化目标
    top_n: int = 5


class EnsembleBacktestRequest(BaseModel):
    strategies: list[dict]  # [{"name": "dual_ma", "weight": 1.0, "params": {}}]
    aggregation: str = "weighted_average"
    buy_threshold: float = 0.3
    sell_threshold: float = -0.3
    codes: list[str] = ["000001"]
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    initial_cash: float = 1_000_000
    position_pct: float = 0.9


@router.post("/ensemble-backtest")
async def ensemble_backtest(req: EnsembleBacktestRequest):
    """多策略聚合回测"""
    from strategy.strategies import STRATEGIES
    from strategy.ensemble import EnsembleStrategy
    from engine.backtest_engine import BacktestEngine, BacktestConfig

    specs = []
    for s in req.strategies:
        name = s.get("name", "")
        if name not in STRATEGIES:
            raise HTTPException(400, f"策略 {name} 不存在")
        weight = s.get("weight", 1.0)
        specs.append((STRATEGIES[name], weight))

    config = BacktestConfig(initial_cash=req.initial_cash)
    strategy = EnsembleStrategy(
        strategies=specs,
        aggregation=req.aggregation,
        buy_threshold=req.buy_threshold,
        sell_threshold=req.sell_threshold,
        position_pct=req.position_pct,
    )
    engine = BacktestEngine(config=config)
    result = engine.run(strategy, req.codes, req.start_date, req.end_date)

    return {
        "success": True,
        "total_return": round(result.total_return, 4),
        "annual_return": round(result.annual_return, 4),
        "max_drawdown": round(result.max_drawdown, 4),
        "sharpe_ratio": round(result.sharpe_ratio, 2),
        "win_rate": round(result.win_rate, 4),
        "total_trades": result.total_trades,
        "equity_curve": result.equity_curve[-200:],
    }


@router.post("/optimize")
async def optimize_strategy(req: OptimizeRequest):
    """参数网格搜索优化"""
    from strategy.strategies import STRATEGIES
    from engine.backtest_engine import BacktestEngine, BacktestConfig

    if req.strategy not in STRATEGIES:
        raise HTTPException(400, f"策略 {req.strategy} 不存在")

    if not req.param_ranges:
        raise HTTPException(400, "参数范围不能为空")

    # 生成所有参数组合
    keys = list(req.param_ranges.keys())
    values = [req.param_ranges[k] for k in keys]
    combos = list(itertools.product(*values))

    if len(combos) > 200:
        raise HTTPException(400, f"参数组合数 {len(combos)} 超过上限 200")

    config = BacktestConfig(initial_cash=req.initial_cash)
    results = []

    for combo in combos:
        params = dict(zip(keys, combo))
        try:
            strategy = STRATEGIES[req.strategy](**params)
            engine = BacktestEngine(config=config)
            result = engine.run(strategy, req.codes, req.start_date, req.end_date)
            results.append({
                "params": params,
                "total_return": round(result.total_return, 4),
                "annual_return": round(result.annual_return, 4),
                "max_drawdown": round(result.max_drawdown, 4),
                "sharpe_ratio": round(result.sharpe_ratio, 2),
                "win_rate": round(result.win_rate, 4),
                "total_trades": result.total_trades,
            })
        except Exception as e:
            results.append({"params": params, "error": str(e)})

    # 按优化目标排序
    valid = [r for r in results if "error" not in r]
    reverse = req.metric not in ("max_drawdown",)
    valid.sort(key=lambda r: r.get(req.metric, 0), reverse=reverse)

    return {
        "success": True,
        "strategy": req.strategy,
        "total_combos": len(combos),
        "metric": req.metric,
        "best": valid[:req.top_n] if valid else [],
        "worst": valid[-req.top_n:] if valid else [],
    }
