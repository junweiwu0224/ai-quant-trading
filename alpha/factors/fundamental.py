"""基本面因子

支持两种数据源：
1. 价量代理因子（无财务数据时的降级方案）
2. 真实财务因子（从 quote_service 获取 PE/ROE/EPS 等）
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


# ── 真实财务因子 ──

class RealFundamentalFactors:
    """基于东方财富财务数据的真实基本面因子"""

    @staticmethod
    def compute(financial: dict, df_index: pd.Index = None) -> pd.DataFrame:
        """从财务数据字典计算因子

        Args:
            financial: quote_service.get_financial_data() 返回的 dict
            df_index: 用于对齐的 DataFrame index（单值广播到全序列）
        """
        result = pd.DataFrame(index=df_index if df_index is not None else [0])

        # 估值因子
        result["pe_ttm"] = financial.get("pe_ttm", 0) or 0
        result["ps_ratio"] = financial.get("ps_ratio", 0) or 0
        result["dividend_yield"] = financial.get("dividend_yield", 0) or 0

        # 盈利因子
        result["roe"] = financial.get("roe", 0) or 0
        result["eps"] = financial.get("eps", 0) or 0
        result["bps"] = financial.get("bps", 0) or 0
        result["gross_margin"] = financial.get("gross_margin", 0) or 0
        result["net_margin"] = financial.get("net_margin", 0) or 0

        # 成长因子
        result["revenue_growth"] = financial.get("revenue_growth", 0) or 0
        result["net_profit_growth"] = financial.get("net_profit_growth", 0) or 0

        # 风险因子
        result["debt_ratio"] = financial.get("debt_ratio", 0) or 0

        # 流动性因子
        total_shares = financial.get("total_shares", 0) or 0
        circ_shares = financial.get("circulating_shares", 0) or 0
        result["circ_ratio"] = (circ_shares / total_shares) if total_shares > 0 else 0

        return result


# ── 代理因子（价量数据衍生）──

class FundamentalFactors:
    """基本面因子库

    当无真实财务数据时，使用价量数据的代理因子。
    当有真实财务数据时，代理因子仍然保留作为补充。
    """

    @staticmethod
    def turnover_rate(volume: pd.Series, total_shares: float) -> pd.Series:
        """换手率"""
        return volume / total_shares if total_shares > 0 else volume * 0

    @staticmethod
    def price_momentum(close: pd.Series, window: int = 20) -> pd.Series:
        """价格动量（N日涨幅排名百分位）"""
        ret = close.pct_change(window)
        return ret.rank(pct=True)

    @staticmethod
    def volume_price_trend(close: pd.Series, volume: pd.Series) -> pd.Series:
        """量价趋势（VPT）"""
        ret = close.pct_change()
        vpt = (ret * volume).cumsum()
        return vpt

    @staticmethod
    def money_flow(high: pd.Series, low: pd.Series, close: pd.Series,
                   volume: pd.Series, window: int = 14) -> pd.Series:
        """资金流向指标（MFI）"""
        typical_price = (high + low + close) / 3
        raw_mf = typical_price * volume
        delta = typical_price.diff()
        pos_mf = raw_mf.where(delta > 0, 0.0).rolling(window).sum()
        neg_mf = raw_mf.where(delta <= 0, 0.0).rolling(window).sum()
        mfi = 100 - (100 / (1 + pos_mf / neg_mf.replace(0, np.nan)))
        return mfi

    @staticmethod
    def price_to_ma_ratio(close: pd.Series, window: int = 20) -> pd.Series:
        """价格偏离均线比率"""
        ma = close.rolling(window=window, min_periods=window).mean()
        return close / ma.replace(0, np.nan) - 1

    @staticmethod
    def volume_zscore(volume: pd.Series, window: int = 20) -> pd.Series:
        """成交量 Z-score（异常放量/缩量）"""
        mean = volume.rolling(window=window, min_periods=window).mean()
        std = volume.rolling(window=window, min_periods=window).std()
        return (volume - mean) / std.replace(0, np.nan)

    @classmethod
    def compute_all(cls, df: pd.DataFrame, financial: Optional[dict] = None) -> pd.DataFrame:
        """计算全部基本面因子

        Args:
            df: 含 open/high/low/close/volume 的 DataFrame
            financial: 可选的财务数据字典（来自 quote_service）
        """
        result = pd.DataFrame(index=df.index)

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        # 代理因子
        result["price_mom_20"] = cls.price_momentum(close, 20)
        result["vpt"] = cls.volume_price_trend(close, volume)
        result["mfi_14"] = cls.money_flow(high, low, close, volume, 14)
        result["price_ma20_ratio"] = cls.price_to_ma_ratio(close, 20)
        result["vol_zscore_20"] = cls.volume_zscore(volume, 20)

        # 合并真实财务因子（单值广播到全序列）
        if financial:
            real = RealFundamentalFactors.compute(financial, df.index)
            for col in real.columns:
                result[col] = real[col].values

        return result
