"""技术因子计算"""
import numpy as np
import pandas as pd


class TechnicalFactors:
    """技术因子库"""

    @staticmethod
    def ma(close: pd.Series, window: int) -> pd.Series:
        """简单移动平均"""
        return close.rolling(window=window, min_periods=window).mean()

    @staticmethod
    def ema(close: pd.Series, window: int) -> pd.Series:
        """指数移动平均"""
        return close.ewm(span=window, adjust=False).mean()

    @staticmethod
    def rsi(close: pd.Series, window: int = 14) -> pd.Series:
        """RSI 相对强弱指标"""
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.rolling(window=window, min_periods=window).mean()
        avg_loss = loss.rolling(window=window, min_periods=window).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple:
        """MACD 指标，返回 (dif, dea, macd_hist)"""
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        dif = ema_fast - ema_slow
        dea = dif.ewm(span=signal, adjust=False).mean()
        macd_hist = 2 * (dif - dea)
        return dif, dea, macd_hist

    @staticmethod
    def bollinger(close: pd.Series, window: int = 20, num_std: float = 2.0) -> tuple:
        """布林带，返回 (upper, middle, lower)"""
        middle = close.rolling(window=window, min_periods=window).mean()
        std = close.rolling(window=window, min_periods=window).std()
        upper = middle + num_std * std
        lower = middle - num_std * std
        return upper, middle, lower

    @staticmethod
    def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
        """ATR 平均真实波幅"""
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)
        return tr.rolling(window=window, min_periods=window).mean()

    @staticmethod
    def kdj(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 9) -> tuple:
        """KDJ 指标，返回 (k, d, j)"""
        lowest = low.rolling(window=window, min_periods=window).min()
        highest = high.rolling(window=window, min_periods=window).max()
        rsv = (close - lowest) / (highest - lowest).replace(0, np.nan) * 100
        k = rsv.ewm(com=2, adjust=False).mean()
        d = k.ewm(com=2, adjust=False).mean()
        j = 3 * k - 2 * d
        return k, d, j

    @staticmethod
    def volume_ratio(volume: pd.Series, window: int = 5) -> pd.Series:
        """量比"""
        avg_vol = volume.rolling(window=window, min_periods=window).mean()
        return volume / avg_vol.replace(0, np.nan)

    @staticmethod
    def returns(close: pd.Series, periods: list[int] = None) -> dict[str, pd.Series]:
        """N日收益率"""
        if periods is None:
            periods = [1, 5, 10, 20]
        return {f"ret_{n}d": close.pct_change(n) for n in periods}

    @staticmethod
    def volatility(close: pd.Series, window: int = 20) -> pd.Series:
        """历史波动率（年化）"""
        log_ret = np.log(close / close.shift(1))
        return log_ret.rolling(window=window, min_periods=window).std() * np.sqrt(252)

    @classmethod
    def compute_all(cls, df: pd.DataFrame) -> pd.DataFrame:
        """计算全部技术因子，输入需含 open/high/low/close/volume 列"""
        result = pd.DataFrame(index=df.index)

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        # 均线
        for w in [5, 10, 20, 60]:
            result[f"ma_{w}"] = cls.ma(close, w)
            result[f"ma_{w}_ratio"] = close / result[f"ma_{w}"]

        # RSI
        result["rsi_14"] = cls.rsi(close, 14)

        # MACD
        dif, dea, hist = cls.macd(close)
        result["macd_dif"] = dif
        result["macd_dea"] = dea
        result["macd_hist"] = hist

        # 布林带
        upper, middle, lower = cls.bollinger(close)
        result["boll_upper"] = upper
        result["boll_lower"] = lower
        result["boll_width"] = (upper - lower) / middle

        # ATR
        result["atr_14"] = cls.atr(high, low, close, 14)

        # KDJ
        k, d, j = cls.kdj(high, low, close)
        result["kdj_k"] = k
        result["kdj_d"] = d
        result["kdj_j"] = j

        # 量比
        result["volume_ratio_5"] = cls.volume_ratio(volume, 5)

        # 收益率
        for name, series in cls.returns(close).items():
            result[name] = series

        # 波动率
        result["volatility_20"] = cls.volatility(close, 20)

        return result
