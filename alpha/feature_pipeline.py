"""特征工程管道

支持三类因子：
1. 技术因子（时序）：MA/RSI/MACD/ATR/Bollinger 等
2. 基本面因子（混合）：代理因子 + 真实财务因子
3. 增量因子（API）：资金流/情绪/宏观（可选，按需接入）
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger

from alpha.factors.technical import TechnicalFactors
from alpha.factors.fundamental import FundamentalFactors, RealFundamentalFactors


class FeaturePipeline:
    """特征工程管道：因子计算 → 清洗 → 标准化"""

    def __init__(self, enable_api_factors: bool = False):
        """
        Args:
            enable_api_factors: 是否启用 API 因子（资金流/情绪/宏观）
                               启用后 build_features() 需要 code 参数
        """
        self._enable_api = enable_api_factors

    def build_features(
        self,
        df: pd.DataFrame,
        financial: Optional[dict] = None,
        code: Optional[str] = None,
    ) -> pd.DataFrame:
        """构建完整特征矩阵

        Args:
            df: 含 date/open/high/low/close/volume 的 DataFrame
            financial: 可选的财务数据字典（来自 quote_service）
            code: 股票代码（启用 API 因子时必需）
        """
        logger.info(f"构建特征: {len(df)} 行")

        # 1. 技术因子
        tech_factors = TechnicalFactors.compute_all(df)

        # 2. 基本面因子（代理 + 真实财务）
        fund_factors = FundamentalFactors.compute_all(df, financial)

        # 3. 合并基础因子
        features = pd.concat([tech_factors, fund_factors], axis=1)

        # 4. API 增量因子（可选）
        if self._enable_api and code:
            api_features = self._fetch_api_factors(code, df.index)
            if not api_features.empty:
                features = pd.concat([features, api_features], axis=1)

        # 5. 构建标签（次日收益率 > 0 为正样本）
        features["label"] = (df["close"].shift(-1) / df["close"] - 1 > 0).astype(int)

        # 6. 去极值
        features = self._winsorize(features)

        # 7. 标准化
        features = self._standardize(features)

        # 8. 删除无效行
        features = features.dropna(subset=["label"])
        features = features.replace([np.inf, -np.inf], np.nan)

        logger.info(f"特征完成: {features.shape[1] - 1} 个特征, {len(features)} 行")
        return features

    def get_feature_names(self, df: pd.DataFrame, code: Optional[str] = None) -> list[str]:
        """获取特征列名（不含 label）"""
        tech_factors = TechnicalFactors.compute_all(df)
        fund_factors = FundamentalFactors.compute_all(df)
        combined = pd.concat([tech_factors, fund_factors], axis=1)

        if self._enable_api and code:
            api_features = self._fetch_api_factors(code, df.index)
            if not api_features.empty:
                combined = pd.concat([combined, api_features], axis=1)

        return [c for c in combined.columns if c != "label"]

    @staticmethod
    def _fetch_api_factors(code: str, index: pd.Index) -> pd.DataFrame:
        """获取 API 增量因子（资金流 + 情绪 + 宏观）

        返回 DataFrame，每行相同值（全市场统一赋值的宏观因子 + 个股因子广播）。
        失败时返回空 DataFrame，不中断流程。
        """
        result = pd.DataFrame(index=index)

        # 资金流因子
        try:
            from alpha.factors.flow import compute_flow_factors
            flow = compute_flow_factors(code)
            for k, v in flow.items():
                result[k] = v
        except Exception as e:
            logger.debug(f"资金流因子获取失败 {code}: {e}")

        # 情绪因子
        try:
            from alpha.factors.sentiment import fetch_news_sentiment
            sentiment = fetch_news_sentiment(code)
            for k, v in sentiment.items():
                result[k] = v
        except Exception as e:
            logger.debug(f"情绪因子获取失败 {code}: {e}")

        # 宏观因子（全市场统一）
        try:
            from alpha.factors.macro import fetch_macro_factors
            macro = fetch_macro_factors()
            for k, v in macro.items():
                result[k] = v
        except Exception as e:
            logger.debug(f"宏观因子获取失败: {e}")

        return result

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
