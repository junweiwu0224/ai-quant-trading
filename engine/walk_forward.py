"""Walk-Forward Analysis 引擎

滚动窗口优化验证，模拟真实交易中的参数再优化过程。
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
from loguru import logger

from engine.backtest_engine import BacktestConfig, BacktestEngine, BacktestResult
from strategy.base import BaseStrategy


@dataclass(frozen=True)
class WalkForwardWindow:
    """Walk-Forward 窗口结果"""
    window_index: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    best_params: dict
    train_sharpe: float
    test_sharpe: float
    test_return: float
    test_max_drawdown: float
    test_total_trades: int


@dataclass(frozen=True)
class WalkForwardResult:
    """Walk-Forward 整体结果"""
    windows: list[WalkForwardWindow]
    oos_equity_curve: list[dict]
    oos_total_return: float
    oos_sharpe_ratio: float
    oos_max_drawdown: float
    oos_win_rate: float
    oos_total_trades: int
    stability_score: float
    param_stability: dict
    error: Optional[str] = None


def _calculate_date_range(
    start_date: str,
    end_date: str,
    train_window: int,
    test_window: int,
    n_splits: int,
) -> list[tuple[str, str, str, str]]:
    """计算滚动窗口的日期范围

    Args:
        start_date: 起始日期
        end_date: 结束日期
        train_window: 训练窗口（交易日）
        test_window: 测试窗口（交易日）
        n_splits: 分割次数

    Returns:
        [(train_start, train_end, test_start, test_end), ...]
    """
    # 简化处理：按自然日计算（实际应该按交易日）
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    total_days = (end - start).days
    # 每个窗口的天数（训练 + 测试）
    # 预留一些重叠空间
    window_days = total_days // n_splits

    windows = []
    for i in range(n_splits):
        # 计算训练集起止
        train_start = start + timedelta(days=i * window_days)
        train_end = train_start + timedelta(days=int(window_days * 0.7))

        # 计算测试集起止
        test_start = train_end + timedelta(days=1)
        test_end = test_start + timedelta(days=int(window_days * 0.3))

        # 确保不超出范围
        if test_end > end:
            test_end = end

        windows.append((
            train_start.strftime("%Y-%m-%d"),
            train_end.strftime("%Y-%m-%d"),
            test_start.strftime("%Y-%m-%d"),
            test_end.strftime("%Y-%m-%d"),
        ))

    return windows


def _run_optimization(
    strategy_name: str,
    strategy_cls: type,
    param_ranges: dict,
    codes: list[str],
    start_date: str,
    end_date: str,
    config: BacktestConfig,
    metric: str = "sharpe_ratio",
    n_trials: int = 30,
) -> tuple[dict, float]:
    """在指定时间窗口内运行参数优化

    Args:
        strategy_name: 策略名称
        strategy_cls: 策略类
        param_ranges: 参数范围
        codes: 股票代码列表
        start_date: 起始日期
        end_date: 结束日期
        config: 回测配置
        metric: 优化指标
        n_trials: 试验次数

    Returns:
        (best_params, best_metric_value)
    """
    from engine.optimization_engine import optuna_search

    try:
        result = optuna_search(
            strategy_cls=strategy_cls,
            param_ranges=param_ranges,
            codes=codes,
            start_date=start_date,
            end_date=end_date,
            config=config,
            metric=metric,
            n_trials=n_trials,
        )
        return result.best_params, result.best_metric
    except Exception as e:
        logger.error(f"优化失败: {e}")
        # 返回默认参数
        default_params = {k: v["default"] for k, v in param_ranges.items() if "default" in v}
        return default_params, 0.0


def run_walk_forward(
    strategy_name: str,
    strategy_cls: type,
    param_ranges: dict,
    codes: list[str],
    start_date: str,
    end_date: str,
    train_window: int = 252,
    test_window: int = 63,
    n_splits: int = 4,
    optimize_method: str = "optuna",
    n_trials: int = 30,
    metric: str = "sharpe_ratio",
    config: Optional[BacktestConfig] = None,
    progress_callback=None,
) -> WalkForwardResult:
    """运行 Walk-Forward Analysis

    Args:
        strategy_name: 策略名称
        strategy_cls: 策略类
        param_ranges: 参数范围
        codes: 股票代码列表
        start_date: 起始日期
        end_date: 结束日期
        train_window: 训练窗口（交易日）
        test_window: 测试窗口（交易日）
        n_splits: 分割次数
        optimize_method: 优化方法
        n_trials: 每个窗口的优化试验次数
        metric: 优化指标
        config: 回测配置
        progress_callback: 进度回调函数

    Returns:
        WalkForwardResult
    """
    if config is None:
        config = BacktestConfig()

    # 计算日期范围
    date_ranges = _calculate_date_range(
        start_date, end_date, train_window, test_window, n_splits
    )

    if not date_ranges:
        return WalkForwardResult(
            windows=[],
            oos_equity_curve=[],
            oos_total_return=0.0,
            oos_sharpe_ratio=0.0,
            oos_max_drawdown=0.0,
            oos_win_rate=0.0,
            oos_total_trades=0,
            stability_score=0.0,
            param_stability={},
            error="无法计算日期范围",
        )

    windows = []
    oos_equity_curves = []
    all_test_sharpes = []
    all_params = []

    total_windows = len(date_ranges)

    for i, (train_start, train_end, test_start, test_end) in enumerate(date_ranges):
        logger.info(f"Walk-Forward 窗口 {i+1}/{total_windows}: "
                    f"训练 {train_start}~{train_end}, 测试 {test_start}~{test_end}")

        # 1. 在训练集上优化参数
        best_params, train_sharpe = _run_optimization(
            strategy_name=strategy_name,
            strategy_cls=strategy_cls,
            param_ranges=param_ranges,
            codes=codes,
            start_date=train_start,
            end_date=train_end,
            config=config,
            metric=metric,
            n_trials=n_trials,
        )

        # 2. 用最优参数在测试集上运行回测
        strategy = strategy_cls()
        # 注入优化后的参数
        for k, v in best_params.items():
            if hasattr(strategy, k):
                setattr(strategy, k, v)

        engine = BacktestEngine(config=config)
        test_result = engine.run(strategy, codes, test_start, test_end)

        # 记录窗口结果
        window = WalkForwardWindow(
            window_index=i,
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
            best_params=best_params,
            train_sharpe=round(train_sharpe, 4),
            test_sharpe=round(test_result.sharpe_ratio, 4),
            test_return=round(test_result.total_return, 4),
            test_max_drawdown=round(test_result.max_drawdown, 4),
            test_total_trades=test_result.total_trades,
        )
        windows.append(window)

        # 收集测试集权益曲线
        if test_result.equity_curve:
            oos_equity_curves.append(test_result.equity_curve)

        all_test_sharpes.append(test_result.sharpe_ratio)
        all_params.append(best_params)

        # 报告进度
        if progress_callback:
            progress = (i + 1) / total_windows
            progress_callback(progress)

    # 3. 拼接样本外权益曲线
    oos_equity_curve = []
    for curve in oos_equity_curves:
        oos_equity_curve.extend(curve)

    # 4. 计算整体绩效
    if oos_equity_curve:
        equities = [p["equity"] for p in oos_equity_curve]
        total_return = (equities[-1] - equities[0]) / equities[0] if equities[0] > 0 else 0
        # 简化的夏普计算
        if len(equities) > 1:
            daily_returns = [(equities[i] - equities[i-1]) / equities[i-1] for i in range(1, len(equities)) if equities[i-1] > 0]
            mean_return = sum(daily_returns) / len(daily_returns)
            std_return = (sum((r - mean_return)**2 for r in daily_returns) / len(daily_returns)) ** 0.5
            sharpe = (mean_return / std_return) * (252 ** 0.5) if std_return > 0 else 0
        else:
            sharpe = 0

        # 计算最大回撤
        peak = equities[0]
        max_dd = 0
        for eq in equities:
            if eq > peak:
                peak = eq
            dd = (eq - peak) / peak if peak > 0 else 0
            if dd < max_dd:
                max_dd = dd

        # 计算胜率
        total_trades = sum(w.test_total_trades for w in windows)
    else:
        total_return = 0
        sharpe = 0
        max_dd = 0
        total_trades = 0

    # 5. 计算稳定性评分（各窗口夏普的变异系数的倒数）
    if all_test_sharpes and len(all_test_sharpes) > 1:
        mean_sharpe = sum(all_test_sharpes) / len(all_test_sharpes)
        if mean_sharpe > 0:
            std_sharpe = (sum((s - mean_sharpe)**2 for s in all_test_sharpes) / len(all_test_sharpes)) ** 0.5
            cv = std_sharpe / mean_sharpe
            stability_score = 1 / (1 + cv)  # 归一化到 0-1
        else:
            stability_score = 0.0
    else:
        stability_score = 0.0

    # 6. 计算参数稳定性
    param_stability = {}
    if all_params:
        for key in all_params[0].keys():
            values = [p.get(key) for p in all_params if key in p]
            if values:
                try:
                    numeric_values = [float(v) for v in values]
                    mean_val = sum(numeric_values) / len(numeric_values)
                    std_val = (sum((v - mean_val)**2 for v in numeric_values) / len(numeric_values)) ** 0.5
                    param_stability[key] = {
                        "mean": round(mean_val, 4),
                        "std": round(std_val, 4),
                        "cv": round(std_val / mean_val, 4) if mean_val != 0 else 0,
                    }
                except (TypeError, ValueError):
                    param_stability[key] = {"mean": None, "std": None, "cv": None}

    return WalkForwardResult(
        windows=windows,
        oos_equity_curve=oos_equity_curve,
        oos_total_return=round(total_return, 4),
        oos_sharpe_ratio=round(sharpe, 4),
        oos_max_drawdown=round(max_dd, 4),
        oos_win_rate=0.0,  # 需要从交易记录计算
        oos_total_trades=total_trades,
        stability_score=round(stability_score, 4),
        param_stability=param_stability,
    )
