"""集成模型 — 组合多个基模型"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger


class EnsembleStrategy(str, Enum):
    """集成策略"""
    AVERAGE = "average"  # 加权平均概率
    VOTE = "vote"  # 多数投票


@dataclass
class EnsembleConfig:
    """集成模型配置"""
    strategy: EnsembleStrategy = EnsembleStrategy.AVERAGE
    weights: Optional[list[float]] = None


class EnsembleModel:
    """集成模型：组合多个基模型通过加权平均或投票"""

    def __init__(
        self,
        models: list,
        config: Optional[EnsembleConfig] = None,
    ):
        if not models:
            raise ValueError("至少需要一个模型")
        self._models = models
        self._config = config or EnsembleConfig()

        if self._config.weights is not None:
            if len(self._config.weights) != len(models):
                raise ValueError("权重数量必须与模型数量一致")
            total = sum(self._config.weights)
            self._weights = [w / total for w in self._config.weights]
        else:
            self._weights = [1.0 / len(models)] * len(models)

    def train(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: Optional[pd.DataFrame] = None,
        y_val: Optional[pd.Series] = None,
    ) -> dict:
        """训练所有子模型，返回聚合指标"""
        all_metrics = {}
        for i, model in enumerate(self._models):
            name = model.__class__.__name__
            logger.info(f"训练子模型 {i}: {name}")
            m = model.train(X_train, y_train, X_val, y_val)
            for k, v in m.items():
                all_metrics[f"{name}_{k}"] = v
        return all_metrics

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """加权平均所有模型的概率预测"""
        preds = np.column_stack([m.predict(X) for m in self._models])
        return np.average(preds, axis=1, weights=self._weights)

    def predict_signal(self, X: pd.DataFrame, threshold: float = 0.5) -> pd.Series:
        """通过平均或投票生成信号"""
        if self._config.strategy == EnsembleStrategy.VOTE:
            signals = np.column_stack([
                m.predict_signal(X, threshold).values for m in self._models
            ])
            vote_sum = signals.sum(axis=1)
            majority = (vote_sum > len(self._models) / 2).astype(int)
            return pd.Series(majority, index=X.index)
        probs = self.predict(X)
        return pd.Series((probs > threshold).astype(int), index=X.index)

    def feature_importance(self) -> pd.DataFrame:
        """所有模型的平均特征重要性"""
        frames = [m.feature_importance() for m in self._models]
        merged = frames[0].rename(columns={"importance": "importance_0"})
        for i, f in enumerate(frames[1:], start=1):
            merged = merged.merge(
                f.rename(columns={"importance": f"importance_{i}"}),
                on="feature",
                how="outer",
            ).fillna(0)
        imp_cols = [c for c in merged.columns if c.startswith("importance_")]
        merged["importance"] = merged[imp_cols].mean(axis=1)
        return merged[["feature", "importance"]].sort_values("importance", ascending=False)

    def save(self, path: str):
        """保存所有子模型，path 作为前缀"""
        for i, model in enumerate(self._models):
            model.save(f"{path}_model{i}")

    def load(self, path: str):
        """加载所有子模型，path 作为前缀"""
        for i, model in enumerate(self._models):
            model.load(f"{path}_model{i}")
