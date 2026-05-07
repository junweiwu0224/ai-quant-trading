"""基本面因子（基于日K数据衍生）"""
import numpy as np
import pandas as pd


class FundamentalFactors:
    """基本面因子库

    注：完整基本面因子需要财务数据（PE/PB/ROE等），
    这里先实现基于价量数据可计算的代理因子。
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

    @classmethod
    def compute_all(cls, df: pd.DataFrame) -> pd.DataFrame:
        """计算全部基本面因子"""
        result = pd.DataFrame(index=df.index)

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        result["price_mom_20"] = cls.price_momentum(close, 20)
        result["vpt"] = cls.volume_price_trend(close, volume)
        result["mfi_14"] = cls.money_flow(high, low, close, volume, 14)

        return result
