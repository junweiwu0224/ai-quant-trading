"""因子分析模块: IC/IR/相关性/分层收益"""
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from loguru import logger
from scipy import stats

from data.storage import DataStorage


@dataclass
class FactorAnalysisResult:
    """因子分析结果"""
    factor_name: str
    ic_series: list[dict] = field(default_factory=list)
    ir: float = 0.0
    avg_ic: float = 0.0
    ic_std: float = 0.0
    quantile_returns: list[float] = field(default_factory=list)


# 可用因子列表
AVAILABLE_FACTORS = {
    # 技术因子
    "ma_5_ratio": "5日均线比",
    "ma_20_ratio": "20日均线比",
    "rsi_14": "RSI(14)",
    "macd_hist": "MACD柱",
    "boll_width": "布林带宽",
    "atr_14": "ATR(14)",
    "volatility_20": "20日波动率",
    "ret_5d": "5日收益率",
    "ret_10d": "10日收益率",
    "ret_20d": "20日收益率",
    "volume_ratio_5": "5日量比",
    # 基本面因子
    "pe_ttm": "市盈率TTM",
    "pb_ratio": "市净率",
    "ps_ratio": "市销率",
    "roe": "ROE",
    "dividend_yield": "股息率",
    "market_cap": "市值",
    "turnover_rate": "换手率",
}


class FactorAnalyzer:
    """因子分析器"""

    def __init__(self):
        self._storage = DataStorage()

    def _compute_factor(self, df: pd.DataFrame, factor_name: str) -> pd.Series:
        """计算单个因子值"""
        from alpha.factors.technical import TechnicalFactors
        tech = TechnicalFactors.compute_all(df)
        if factor_name in tech.columns:
            return tech[factor_name]
        return pd.Series(dtype=float)

    def _compute_returns(self, df: pd.DataFrame, period: int = 5) -> pd.Series:
        """计算前瞻收益率"""
        return df["close"].pct_change(period).shift(-period)

    def calc_factor_ic(
        self, factor_values: pd.Series, returns: pd.Series
    ) -> float:
        """Spearman Rank IC"""
        common = factor_values.dropna().index.intersection(returns.dropna().index)
        if len(common) < 30:
            return 0.0
        ic, _ = stats.spearmanr(
            factor_values.loc[common].values, returns.loc[common].values
        )
        return round(ic, 6) if not np.isnan(ic) else 0.0

    def calc_factor_ir(self, ic_series: list[float]) -> float:
        """Information Ratio = IC均值 / IC标准差"""
        if len(ic_series) < 5:
            return 0.0
        arr = np.array(ic_series)
        mean_ic = np.mean(arr)
        std_ic = np.std(arr)
        return round(float(mean_ic / std_ic), 4) if std_ic > 0 else 0.0

    def calc_factor_correlation(
        self, factor_matrix: pd.DataFrame
    ) -> dict:
        """因子相关性矩阵"""
        corr = factor_matrix.corr(method="spearman")
        return {
            "factors": list(corr.columns),
            "matrix": corr.round(4).values.tolist(),
        }

    def analyze_factor(
        self,
        factor_name: str,
        stock_codes: list[str],
        start_date: str,
        end_date: str,
        forward_period: int = 5,
    ) -> FactorAnalysisResult:
        """完整因子分析: IC序列, IR, 分层收益"""
        import pandas as pd
        start = pd.Timestamp(start_date).date()
        end = pd.Timestamp(end_date).date()

        # 加载所有股票数据
        all_data = {}
        for code in stock_codes:
            df = self._storage.get_stock_daily(code, start, end)
            if not df.empty and len(df) > 30:
                df = df.set_index("date").sort_index()
                all_data[code] = df

        if not all_data:
            return FactorAnalysisResult(factor_name=factor_name)

        # 计算各股票的因子值和前瞻收益
        factor_by_date = defaultdict(list)
        ret_by_date = defaultdict(list)

        for code, df in all_data.items():
            factor_vals = self._compute_factor(df, factor_name)
            fwd_returns = self._compute_returns(df, forward_period)
            for idx in factor_vals.index:
                fv = factor_vals.loc[idx]
                fr = fwd_returns.loc[idx] if idx in fwd_returns.index else np.nan
                if not np.isnan(fv) and not np.isnan(fr):
                    factor_by_date[idx].append(fv)
                    ret_by_date[idx].append(fr)

        # 计算每日截面 IC
        ic_series = []
        ic_values = []
        for d in sorted(factor_by_date.keys()):
            fvals = factor_by_date[d]
            rvals = ret_by_date[d]
            if len(fvals) < 5:
                continue
            ic, _ = stats.spearmanr(fvals, rvals)
            if not np.isnan(ic):
                ic_series.append({"date": str(d), "ic": round(ic, 6)})
                ic_values.append(ic)

        if not ic_values:
            return FactorAnalysisResult(factor_name=factor_name)

        # 计算 IR
        ir = self.calc_factor_ir(ic_values)

        # 分层收益: 按因子值分5组，计算各组平均收益
        group_returns = defaultdict(list)
        for d in sorted(factor_by_date.keys()):
            fvals = np.array(factor_by_date[d])
            rvals = np.array(ret_by_date[d])
            if len(fvals) < 10:
                continue
            quantiles = np.percentile(fvals, [20, 40, 60, 80])
            for fv, rv in zip(fvals, rvals):
                if fv <= quantiles[0]:
                    group_returns[0].append(rv)
                elif fv <= quantiles[1]:
                    group_returns[1].append(rv)
                elif fv <= quantiles[2]:
                    group_returns[2].append(rv)
                elif fv <= quantiles[3]:
                    group_returns[3].append(rv)
                else:
                    group_returns[4].append(rv)

        quantile_returns = [
            round(float(np.mean(group_returns[g])), 4) if group_returns[g] else 0.0
            for g in range(5)
        ]

        return FactorAnalysisResult(
            factor_name=factor_name,
            ic_series=ic_series[-100:],
            ir=ir,
            avg_ic=round(float(np.mean(ic_values)), 6),
            ic_std=round(float(np.std(ic_values)), 6),
            quantile_returns=quantile_returns,
        )

    def analyze_multiple_factors(
        self,
        factor_names: list[str],
        stock_codes: list[str],
        start_date: str,
        end_date: str,
    ) -> dict:
        """多因子相关性分析"""
        import pandas as pd
        start = pd.Timestamp(start_date).date()
        end = pd.Timestamp(end_date).date()

        # 取第一只股票的数据计算因子矩阵
        if not stock_codes:
            return {"error": "股票列表为空"}
        df = self._storage.get_stock_daily(stock_codes[0], start, end)
        if df.empty:
            return {"error": f"股票 {stock_codes[0]} 无数据"}

        from alpha.factors.technical import TechnicalFactors
        tech = TechnicalFactors.compute_all(df)
        available = [f for f in factor_names if f in tech.columns]
        if len(available) < 2:
            return {"error": "可用因子不足2个"}

        return self.calc_factor_correlation(tech[available])
