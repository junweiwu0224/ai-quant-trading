"""XGBoost 模型封装"""
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
import xgboost as xgb
from loguru import logger
from sklearn.metrics import roc_auc_score


@dataclass
class XGBConfig:
    """XGBoost 默认参数"""
    objective: str = "binary:logistic"
    eval_metric: str = "auc"
    tree_method: str = "hist"
    max_depth: int = 6
    learning_rate: float = 0.05
    colsample_bytree: float = 0.8
    subsample: float = 0.8
    n_estimators: int = 200
    early_stopping_rounds: int = 20


class XGBModel:
    """XGBoost 二分类模型"""

    def __init__(self, config: Optional[XGBConfig] = None, params: Optional[dict] = None):
        self._config = config or XGBConfig()
        self._params = params or {}
        self._model: Optional[xgb.XGBClassifier] = None
        self._feature_names: list[str] = []
        self._evals_result: dict = {}

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
            "eval_metric": self._config.eval_metric,
            "tree_method": self._config.tree_method,
            "max_depth": self._config.max_depth,
            "learning_rate": self._config.learning_rate,
            "colsample_bytree": self._config.colsample_bytree,
            "subsample": self._config.subsample,
            "n_estimators": self._config.n_estimators,
        }
        params.update(self._params)

        self._model = xgb.XGBClassifier(**params)

        fit_params = {}
        if X_val is not None and y_val is not None:
            fit_params["eval_set"] = [(X_val, y_val)]
            fit_params["verbose"] = False
            fit_params["callbacks"] = [
                xgb.callback.EarlyStopping(
                    rounds=self._config.early_stopping_rounds,
                    metric_name="auc",
                    maximize=True,
                )
            ]

        self._model.fit(X_train, y_train, **fit_params)

        # 采集训练过程指标
        self._evals_result = {}
        if hasattr(self._model, "evals_result_"):
            self._evals_result = self._model.evals_result_

        metrics = {}
        if X_val is not None and y_val is not None:
            val_pred = self._model.predict_proba(X_val)[:, 1]
            metrics["val_auc"] = roc_auc_score(y_val, val_pred)

        logger.info(f"XGB 训练完成: {self._config.n_estimators} 棵树, 特征 {len(self._feature_names)}")
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

    def get_evals_result(self) -> dict:
        """获取训练过程指标（用于绘制训练曲线）"""
        return self._evals_result

    def save(self, path: str):
        """保存模型"""
        if self._model is not None:
            self._model.save_model(path)
            logger.info(f"XGB 模型已保存: {path}")

    def load(self, path: str):
        """加载模型"""
        self._model = xgb.XGBClassifier()
        self._model.load_model(path)
        logger.info(f"XGB 模型已加载: {path}")
