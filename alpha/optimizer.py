"""Optuna 超参优化"""
from typing import Optional

import lightgbm as lgb
import optuna
import pandas as pd
from loguru import logger
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import TimeSeriesSplit

from alpha.models.lightgbm_model import LGBConfig, LGBModel


class HyperOptimizer:
    """超参优化器"""

    def __init__(self, n_trials: int = 50, n_splits: int = 3):
        self.n_trials = n_trials
        self.n_splits = n_splits

    def optimize(self, X: pd.DataFrame, y: pd.Series) -> dict:
        """运行超参搜索，返回最佳参数"""
        logger.info(f"开始超参搜索: {self.n_trials} trials, {self.n_splits} 折")

        def objective(trial: optuna.Trial) -> float:
            params = {
                "num_leaves": trial.suggest_int("num_leaves", 15, 63),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
                "feature_fraction": trial.suggest_float("feature_fraction", 0.5, 1.0),
                "bagging_fraction": trial.suggest_float("bagging_fraction", 0.5, 1.0),
                "min_child_samples": trial.suggest_int("min_child_samples", 5, 50),
                "reg_alpha": trial.suggest_float("reg_alpha", 1e-3, 10.0, log=True),
                "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
            }

            tscv = TimeSeriesSplit(n_splits=self.n_splits)
            auc_scores = []

            for train_idx, val_idx in tscv.split(X):
                X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
                y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

                config = LGBConfig(n_estimators=200, early_stopping_rounds=20)
                model = LGBModel(config=config, params=params)
                model.train(X_train, y_train, X_val, y_val)

                val_pred = model.predict(X_val)
                auc = roc_auc_score(y_val, val_pred)
                auc_scores.append(auc)

            return sum(auc_scores) / len(auc_scores)

        study = optuna.create_study(direction="maximize")
        study.optimize(objective, n_trials=self.n_trials, show_progress_bar=True)

        best = study.best_params
        logger.info(f"最佳 AUC: {study.best_value:.4f}, 参数: {best}")
        return best
