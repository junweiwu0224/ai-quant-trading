"""LightGBM 模型封装"""
from dataclasses import dataclass, field
from typing import Optional

import lightgbm as lgb
import numpy as np
import pandas as pd
from loguru import logger


@dataclass
class LGBConfig:
    """LightGBM 默认参数"""
    objective: str = "binary"
    metric: str = "auc"
    boosting_type: str = "gbdt"
    num_leaves: int = 31
    learning_rate: float = 0.05
    feature_fraction: float = 0.8
    bagging_fraction: float = 0.8
    bagging_freq: int = 5
    verbose: int = -1
    n_estimators: int = 200
    early_stopping_rounds: int = 20


class LGBModel:
    """LightGBM 二分类模型"""

    def __init__(self, config: Optional[LGBConfig] = None, params: Optional[dict] = None):
        self._config = config or LGBConfig()
        self._params = params or {}
        self._model: Optional[lgb.LGBMClassifier] = None
        self._feature_names: list[str] = []

    def train(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: Optional[pd.DataFrame] = None,
        y_val: Optional[pd.Series] = None,
    ) -> dict:
        """训练模型"""
        self._feature_names = list(X_train.columns)

        params = {
            "objective": self._config.objective,
            "metric": self._config.metric,
            "boosting_type": self._config.boosting_type,
            "num_leaves": self._config.num_leaves,
            "learning_rate": self._config.learning_rate,
            "feature_fraction": self._config.feature_fraction,
            "bagging_fraction": self._config.bagging_fraction,
            "bagging_freq": self._config.bagging_freq,
            "verbose": self._config.verbose,
            "n_estimators": self._config.n_estimators,
        }
        params.update(self._params)

        self._model = lgb.LGBMClassifier(**params)

        fit_params = {}
        if X_val is not None and y_val is not None:
            fit_params["eval_set"] = [(X_val, y_val)]
            fit_params["callbacks"] = [lgb.early_stopping(self._config.early_stopping_rounds)]

        self._model.fit(X_train, y_train, **fit_params)

        metrics = {}
        if X_val is not None and y_val is not None:
            val_pred = self._model.predict_proba(X_val)[:, 1]
            from sklearn.metrics import roc_auc_score
            metrics["val_auc"] = roc_auc_score(y_val, val_pred)

        logger.info(f"训练完成: {self._model.n_estimators_} 棵树, 特征 {len(self._feature_names)}")
        return metrics

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """预测概率"""
        if self._model is None:
            raise RuntimeError("模型未训练")
        return self._model.predict_proba(X)[:, 1]

    def predict_signal(self, X: pd.DataFrame, threshold: float = 0.5) -> pd.Series:
        """生成交易信号 (1=买入, 0=不操作)"""
        probs = self.predict(X)
        return pd.Series((probs > threshold).astype(int), index=X.index)

    def feature_importance(self) -> pd.DataFrame:
        """特征重要性"""
        if self._model is None:
            raise RuntimeError("模型未训练")
        return pd.DataFrame({
            "feature": self._feature_names,
            "importance": self._model.feature_importances_,
        }).sort_values("importance", ascending=False)

    def save(self, path: str):
        """保存模型"""
        if self._model is not None:
            self._model.booster_.save_model(path)
            logger.info(f"模型已保存: {path}")

    def load(self, path: str):
        """加载模型"""
        self._model = lgb.LGBMClassifier()
        self._model.booster_ = lgb.Booster(model_file=path)
        logger.info(f"模型已加载: {path}")
