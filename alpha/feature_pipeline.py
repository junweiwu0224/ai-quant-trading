"""特征工程管道"""
import numpy as np
import pandas as pd
from loguru import logger

from alpha.factors.technical import TechnicalFactors
from alpha.factors.fundamental import FundamentalFactors


class FeaturePipeline:
    """特征工程管道：因子计算 → 清洗 → 标准化"""

    def __init__(self):
        self._tech = TechnicalFactors()
        self._fund = FundamentalFactors()

    def build_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """构建完整特征矩阵

        输入: 含 date/open/high/low/close/volume 的 DataFrame
        输出: 特征矩阵（含 label 列）
        """
        logger.info(f"构建特征: {len(df)} 行")

        # 1. 计算因子
        tech_factors = TechnicalFactors.compute_all(df)
        fund_factors = FundamentalFactors.compute_all(df)

        # 2. 合并
        features = pd.concat([tech_factors, fund_factors], axis=1)

        # 3. 构建标签（次日收益率 > 0 为正样本）
        features["label"] = (df["close"].shift(-1) / df["close"] - 1 > 0).astype(int)

        # 4. 去极值
        features = self._winsorize(features)

        # 5. 标准化
        features = self._standardize(features)

        # 6. 删除无效行
        features = features.dropna(subset=["label"])
        features = features.replace([np.inf, -np.inf], np.nan)

        logger.info(f"特征完成: {features.shape[1] - 1} 个特征, {len(features)} 行")
        return features

    def get_feature_names(self, df: pd.DataFrame) -> list[str]:
        """获取特征列名（不含 label）"""
        tech_factors = TechnicalFactors.compute_all(df)
        fund_factors = FundamentalFactors.compute_all(df)
        combined = pd.concat([tech_factors, fund_factors], axis=1)
        return [c for c in combined.columns if c != "label"]

    @staticmethod
    def _winsorize(df: pd.DataFrame, lower: float = 0.01, upper: float = 0.99) -> pd.DataFrame:
        """去极值（MAD 法）"""
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        feature_cols = [c for c in numeric_cols if c != "label"]

        result = df.copy()
        for col in feature_cols:
            series = result[col].dropna()
            if len(series) < 10:
                continue
            q_low = series.quantile(lower)
            q_high = series.quantile(upper)
            result[col] = result[col].clip(q_low, q_high)
        return result

    @staticmethod
    def _standardize(df: pd.DataFrame) -> pd.DataFrame:
        """Z-score 标准化"""
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        feature_cols = [c for c in numeric_cols if c != "label"]

        result = df.copy()
        for col in feature_cols:
            series = result[col]
            mean = series.mean()
            std = series.std()
            if std > 0:
                result[col] = (series - mean) / std
        return result
