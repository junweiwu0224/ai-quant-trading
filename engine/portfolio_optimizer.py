"""组合优化: 等权/风险平价/最小方差/最大夏普"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from loguru import logger
from scipy.optimize import minimize

from data.storage import DataStorage


@dataclass
class PortfolioResult:
    """组合优化结果"""
    weights: dict = field(default_factory=dict)
    expected_return: float = 0.0
    expected_volatility: float = 0.0
    sharpe_ratio: float = 0.0
    method: str = ""


def _load_returns(codes: list[str], start_date: str, end_date: str) -> pd.DataFrame:
    """加载多只股票的日收益率 DataFrame"""
    storage = DataStorage()
    import pandas as pd
    start = pd.Timestamp(start_date).date()
    end = pd.Timestamp(end_date).date()
    dfs = {}
    for code in codes:
        df = storage.get_stock_daily(code, start, end)
        if not df.empty and len(df) > 30:
            df = df.set_index("date")[["close"]].rename(columns={"close": code})
            dfs[code] = df
    if not dfs:
        return pd.DataFrame()
    combined = pd.concat(dfs.values(), axis=1).dropna()
    return combined.pct_change().dropna()


def equal_weight(codes: list[str]) -> PortfolioResult:
    """等权组合"""
    n = len(codes)
    w = {code: round(1.0 / n, 4) for code in codes}
    return PortfolioResult(weights=w, method="equal_weight")


def risk_parity(returns_df: pd.DataFrame) -> PortfolioResult:
    """风险平价: 权重与波动率成反比"""
    vols = returns_df.std()
    inv_vols = 1.0 / vols
    weights = (inv_vols / inv_vols.sum()).round(4)
    port_ret = (returns_df.mean() * 252).dot(weights)
    port_vol = np.sqrt(weights.values @ (returns_df.cov() * 252).values @ weights.values)
    sharpe = (port_ret - 0.03) / port_vol if port_vol > 0 else 0
    return PortfolioResult(
        weights=weights.to_dict(),
        expected_return=round(float(port_ret), 4),
        expected_volatility=round(float(port_vol), 4),
        sharpe_ratio=round(float(sharpe), 4),
        method="risk_parity",
    )


def min_variance(returns_df: pd.DataFrame) -> PortfolioResult:
    """最小方差组合"""
    cov = returns_df.cov().values * 252
    n = len(cov)

    def objective(w):
        return w @ cov @ w

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
    bounds = [(0, 1)] * n
    w0 = np.ones(n) / n
    result = minimize(objective, w0, method="SLSQP", bounds=bounds, constraints=constraints)

    if not result.success:
        logger.warning(f"最小方差优化未收敛: {result.message}")
        return equal_weight(list(returns_df.columns))

    weights = np.round(result.x, 4)
    w_dict = dict(zip(returns_df.columns, weights))
    port_ret = (returns_df.mean() * 252).dot(weights)
    port_vol = np.sqrt(objective(result.x))
    sharpe = (port_ret - 0.03) / port_vol if port_vol > 0 else 0
    return PortfolioResult(
        weights=w_dict,
        expected_return=round(float(port_ret), 4),
        expected_volatility=round(float(port_vol), 4),
        sharpe_ratio=round(float(sharpe), 4),
        method="min_variance",
    )


def max_sharpe(returns_df: pd.DataFrame, risk_free: float = 0.03) -> PortfolioResult:
    """最大夏普比率组合"""
    mean_returns = returns_df.mean() * 252
    cov = returns_df.cov() * 252
    n = len(mean_returns)

    def neg_sharpe(w):
        port_ret = w @ mean_returns.values
        port_vol = np.sqrt(w @ cov.values @ w)
        return -(port_ret - risk_free) / port_vol if port_vol > 0 else 0

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
    bounds = [(0, 1)] * n
    w0 = np.ones(n) / n
    result = minimize(neg_sharpe, w0, method="SLSQP", bounds=bounds, constraints=constraints)

    if not result.success:
        logger.warning(f"最大夏普优化未收敛: {result.message}")
        return equal_weight(list(returns_df.columns))

    weights = np.round(result.x, 4)
    w_dict = dict(zip(returns_df.columns, weights))
    port_ret = float(mean_returns.dot(weights))
    port_vol = float(np.sqrt(weights @ cov.values @ weights))
    sharpe = (port_ret - risk_free) / port_vol if port_vol > 0 else 0
    return PortfolioResult(
        weights=w_dict,
        expected_return=round(port_ret, 4),
        expected_volatility=round(port_vol, 4),
        sharpe_ratio=round(float(sharpe), 4),
        method="max_sharpe",
    )


METHODS = {
    "equal_weight": lambda df: equal_weight(list(df.columns)),
    "risk_parity": risk_parity,
    "min_variance": min_variance,
    "max_sharpe": max_sharpe,
}


def optimize_portfolio(
    codes: list[str],
    start_date: str,
    end_date: str,
    method: str = "max_sharpe",
    risk_free: float = 0.03,
) -> PortfolioResult:
    """执行组合优化"""
    if method == "equal_weight":
        return equal_weight(codes)

    returns_df = _load_returns(codes, start_date, end_date)
    if returns_df.empty:
        logger.warning("无法加载收益率数据")
        return PortfolioResult(method=method)

    if len(returns_df) < 30:
        logger.warning("数据不足30天，回退等权")
        return equal_weight(codes)

    func = METHODS.get(method, max_sharpe)
    if method == "max_sharpe":
        return func(returns_df, risk_free)
    return func(returns_df)
