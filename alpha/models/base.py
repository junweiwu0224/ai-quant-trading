"""模型协议定义"""
from typing import Optional, Protocol

import numpy as np
import pandas as pd


class ModelProtocol(Protocol):
    """所有模型必须实现的接口"""

    def train(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: Optional[pd.DataFrame] = None,
        y_val: Optional[pd.Series] = None,
    ) -> dict: ...

    def predict(self, X: pd.DataFrame) -> np.ndarray: ...

    def predict_signal(self, X: pd.DataFrame, threshold: float = 0.5) -> pd.Series: ...

    def feature_importance(self) -> pd.DataFrame: ...

    def save(self, path: str) -> None: ...

    def load(self, path: str) -> None: ...
