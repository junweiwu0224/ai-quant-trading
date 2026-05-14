"""参数优化引擎"""
import itertools
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from loguru import logger

from engine.backtest_engine import BacktestConfig, BacktestEngine
from strategy.base import BaseStrategy


@dataclass
class OptimizationResult:
    """优化结果"""
    best_params: dict = field(default_factory=dict)
    best_metric: float = 0.0
    metric_name: str = ""
    total_trials: int = 0
    elapsed_seconds: float = 0.0
    results: list[dict] = field(default_factory=list)
    error: Optional[str] = None


# 各策略的默认参数范围
STRATEGY_PARAM_RANGES = {
    "dual_ma": {
        "short_window": {"min": 3, "max": 20, "step": 1, "type": "int"},
        "long_window": {"min": 15, "max": 60, "step": 5, "type": "int"},
    },
    "bollinger": {
        "window": {"min": 10, "max": 40, "step": 5, "type": "int"},
        "num_std": {"min": 1.5, "max": 3.0, "step": 0.25, "type": "float"},
    },
    "momentum": {
        "lookback": {"min": 5, "max": 30, "step": 5, "type": "int"},
        "entry_threshold": {"min": 0.05, "max": 0.2, "step": 0.05, "type": "float"},
        "stop_loss": {"min": -0.1, "max": -0.03, "step": 0.02, "type": "float"},
        "take_profit": {"min": 0.1, "max": 0.4, "step": 0.1, "type": "float"},
    },
    "rsi": {
        "period": {"min": 6, "max": 24, "step": 2, "type": "int"},
        "oversold": {"min": 20, "max": 35, "step": 5, "type": "int"},
        "overbought": {"min": 65, "max": 80, "step": 5, "type": "int"},
    },
    "macd": {
        "fast_period": {"min": 8, "max": 16, "step": 2, "type": "int"},
        "slow_period": {"min": 20, "max": 32, "step": 2, "type": "int"},
        "signal_period": {"min": 6, "max": 12, "step": 1, "type": "int"},
    },
    "kdj": {
        "k_period": {"min": 7, "max": 15, "step": 2, "type": "int"},
        "d_period": {"min": 2, "max": 5, "step": 1, "type": "int"},
        "j_oversold": {"min": 15, "max": 30, "step": 5, "type": "int"},
        "j_overbought": {"min": 70, "max": 85, "step": 5, "type": "int"},
    },
}

METRICS = {
    "sharpe_ratio": "夏普比率",
    "total_return": "总收益率",
    "annual_return": "年化收益率",
    "calmar_ratio": "Calmar比率",
    "sortino_ratio": "Sortino比率",
    "win_rate": "胜率",
}


def _run_single_backtest(
    strategy_cls: type,
    params: dict,
    codes: list[str],
    start_date: str,
    end_date: str,
    config: BacktestConfig,
    metric: str,
) -> dict:
    """运行单次回测，返回参数和指标值"""
    try:
        strategy = strategy_cls(**params)
        engine = BacktestEngine(config=config)
        result = engine.run(strategy, codes, start_date, end_date)
        metric_value = getattr(result, metric, 0.0)
        if metric_value is None:
            metric_value = 0.0
        return {
            "params": params,
            "metric": round(metric_value, 6),
            "total_return": round(result.total_return, 4),
            "max_drawdown": round(result.max_drawdown, 4),
            "sharpe_ratio": round(result.sharpe_ratio, 4),
            "win_rate": round(result.win_rate, 4),
            "total_trades": result.total_trades,
        }
    except Exception as e:
        logger.debug(f"回测失败 params={params}: {e}")
        return {"params": params, "metric": 0.0, "error": str(e)}


def grid_search(
    strategy_cls: type,
    param_ranges: dict,
    codes: list[str],
    start_date: str,
    end_date: str,
    config: BacktestConfig,
    metric: str = "sharpe_ratio",
    max_workers: int = 4,
    progress_callback: Optional[Callable] = None,
) -> OptimizationResult:
    """网格搜索"""
    start_time = time.time()

    # 生成参数网格
    param_names = []
    param_values = []
    for name, spec in param_ranges.items():
        param_names.append(name)
        values = []
        v = spec["min"]
        step = spec.get("step", 1)
        while v <= spec["max"] + step * 0.01:
            if spec.get("type") == "int":
                values.append(int(round(v)))
            else:
                values.append(round(v, 4))
            v += step
        # 去重并排序
        param_values.append(sorted(set(values)))

    grid = list(itertools.product(*param_values))
    total = len(grid)
    logger.info(f"网格搜索: {total} 组参数")

    results = []
    best_metric = float("-inf")
    best_params = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for combo in grid:
            params = dict(zip(param_names, combo))
            # 跳过无效组合（如 short_window >= long_window）
            if "short_window" in params and "long_window" in params:
                if params["short_window"] >= params["long_window"]:
                    total -= 1
                    continue
            fut = executor.submit(
                _run_single_backtest, strategy_cls, params,
                codes, start_date, end_date, config, metric,
            )
            futures[fut] = params

        for i, fut in enumerate(as_completed(futures)):
            res = fut.result()
            results.append(res)
            if res["metric"] > best_metric:
                best_metric = res["metric"]
                best_params = res["params"]
            if progress_callback:
                progress_callback((i + 1) / len(futures))

    results.sort(key=lambda x: x["metric"], reverse=True)

    return OptimizationResult(
        best_params=best_params,
        best_metric=round(best_metric, 6),
        metric_name=METRICS.get(metric, metric),
        total_trials=len(results),
        elapsed_seconds=round(time.time() - start_time, 1),
        results=results[:100],  # 最多返回100条
    )


def optuna_search(
    strategy_cls: type,
    param_ranges: dict,
    codes: list[str],
    start_date: str,
    end_date: str,
    config: BacktestConfig,
    metric: str = "sharpe_ratio",
    n_trials: int = 50,
    progress_callback: Optional[Callable] = None,
) -> OptimizationResult:
    """Optuna 贝叶斯优化"""
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    start_time = time.time()
    results = []

    def objective(trial):
        params = {}
        for name, spec in param_ranges.items():
            if spec.get("type") == "int":
                params[name] = trial.suggest_int(name, int(spec["min"]), int(spec["max"]))
            else:
                params[name] = trial.suggest_float(name, spec["min"], spec["max"])

        # 约束
        if "short_window" in params and "long_window" in params:
            if params["short_window"] >= params["long_window"]:
                return float("-inf")

        res = _run_single_backtest(
            strategy_cls, params, codes, start_date, end_date, config, metric,
        )
        results.append(res)
        if progress_callback:
            progress_callback(len(results) / n_trials)
        return res["metric"]

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=n_trials)

    best = study.best_trial
    results.sort(key=lambda x: x["metric"], reverse=True)

    return OptimizationResult(
        best_params=best.params,
        best_metric=round(best.value, 6) if best.value != float("-inf") else 0.0,
        metric_name=METRICS.get(metric, metric),
        total_trials=len(results),
        elapsed_seconds=round(time.time() - start_time, 1),
        results=results[:100],
    )


def sensitivity_analysis(
    strategy_cls: type,
    param_ranges: dict,
    codes: list[str],
    start_date: str,
    end_date: str,
    config: BacktestConfig,
    metric: str = "sharpe_ratio",
    param_x: str = "short_window",
    param_y: str = "long_window",
    max_workers: int = 4,
) -> dict:
    """参数敏感性分析，返回热力图数据"""
    start_time = time.time()

    spec_x = param_ranges[param_x]
    spec_y = param_ranges[param_y]

    def _gen_values(spec):
        values = []
        v = spec["min"]
        step = spec.get("step", 1)
        while v <= spec["max"] + step * 0.01:
            if spec.get("type") == "int":
                values.append(int(round(v)))
            else:
                values.append(round(v, 4))
            v += step
        return sorted(set(values))

    xs = _gen_values(spec_x)
    ys = _gen_values(spec_y)

    # 构建参数组合
    combos = []
    for y_val in ys:
        for x_val in xs:
            # 跳过无效组合
            if param_x == "short_window" and param_y == "long_window":
                if x_val >= y_val:
                    combos.append((x_val, y_val, None))
                    continue
            if param_x == "long_window" and param_y == "short_window":
                if y_val >= x_val:
                    combos.append((x_val, y_val, None))
                    continue
            combos.append((x_val, y_val, {param_x: x_val, param_y: y_val}))

    # 并行回测
    grid_data = []
    best_metric = float("-inf")
    best_params = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for x_val, y_val, params in combos:
            if params is None:
                continue
            # 用其他参数的默认中间值填充
            full_params = {}
            for name, spec in param_ranges.items():
                if name == param_x:
                    full_params[name] = x_val
                elif name == param_y:
                    full_params[name] = y_val
                else:
                    mid = (spec["min"] + spec["max"]) / 2
                    if spec.get("type") == "int":
                        full_params[name] = int(round(mid))
                    else:
                        full_params[name] = round(mid, 4)
            fut = executor.submit(
                _run_single_backtest, strategy_cls, full_params,
                codes, start_date, end_date, config, metric,
            )
            futures[fut] = (x_val, y_val)

        for fut in as_completed(futures):
            x_val, y_val = futures[fut]
            res = fut.result()
            grid_data.append({
                "x": x_val,
                "y": y_val,
                "metric": res["metric"],
                "params": res.get("params", {}),
            })
            if res["metric"] > best_metric:
                best_metric = res["metric"]
                best_params = {param_x: x_val, param_y: y_val}

    return {
        "param_x": param_x,
        "param_y": param_y,
        "x_values": xs,
        "y_values": ys,
        "grid": grid_data,
        "best_params": best_params,
        "best_metric": round(best_metric, 6),
        "metric_name": METRICS.get(metric, metric),
        "total_trials": len(grid_data),
        "elapsed_seconds": round(time.time() - start_time, 1),
    }
