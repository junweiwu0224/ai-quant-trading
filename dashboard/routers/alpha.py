"""AI Alpha API"""
from datetime import date, datetime
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Query
from loguru import logger
from pydantic import BaseModel

from alpha.feature_pipeline import FeaturePipeline
from alpha.models.lightgbm_model import LGBConfig, LGBModel
from data.storage import DataStorage

router = APIRouter()
storage = DataStorage()
pipeline = FeaturePipeline()


class PredictRequest(BaseModel):
    code: str = "000001"
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    threshold: float = 0.5


class TrainRequest(BaseModel):
    code: str = "000001"
    start_date: str = "2023-01-01"
    end_date: str = "2024-12-31"


def _train_model(code: str, start_date: str, end_date: str) -> LGBModel:
    """即时训练模型"""
    start = pd.Timestamp(start_date).date()
    end = pd.Timestamp(end_date).date()
    df = storage.get_stock_daily(code, start, end)
    if df.empty:
        raise ValueError(f"无数据: {code}")

    features = pipeline.build_features(df)
    feature_cols = [c for c in features.columns if c not in ["date", "label"]]
    X = features[feature_cols]
    y = features["label"]

    split = int(len(X) * 0.8)
    X_train, X_val = X.iloc[:split], X.iloc[split:]
    y_train, y_val = y.iloc[:split], y.iloc[split:]

    model = LGBModel()
    model.train(X_train, y_train, X_val, y_val)
    return model


@router.get("/factor-importance")
async def get_factor_importance(
    code: str = Query("000001"),
    start_date: str = Query("2023-01-01"),
    end_date: str = Query("2024-12-31"),
):
    """获取因子重要性 Top 20"""
    try:
        model = _train_model(code, start_date, end_date)
        importance = model.feature_importance().head(20)
        return importance.to_dict("records")
    except Exception as e:
        logger.error(f"因子重要性查询失败: {e}")
        return []


@router.get("/training-metrics")
async def get_training_metrics(
    code: str = Query("000001"),
    start_date: str = Query("2023-01-01"),
    end_date: str = Query("2024-12-31"),
):
    """获取模型训练曲线数据"""
    try:
        model = _train_model(code, start_date, end_date)
        evals = model.get_evals_result()

        if not evals:
            return {"epochs": [], "train_auc": [], "val_auc": [], "train_loss": [], "val_loss": []}

        # LightGBM evals_result 格式: {"training": {"auc": [...], "binary_logloss": [...]}, "valid_0": {...}}
        train_data = evals.get("training", {})
        val_data = evals.get("valid_0", {})

        train_auc = train_data.get("auc", [])
        val_auc = val_data.get("auc", [])
        train_loss = train_data.get("binary_logloss", [])
        val_loss = val_data.get("binary_logloss", [])

        epochs = list(range(1, len(train_auc) + 1))

        return {
            "epochs": epochs,
            "train_auc": [round(v, 4) for v in train_auc],
            "val_auc": [round(v, 4) for v in val_auc],
            "train_loss": [round(v, 4) for v in train_loss],
            "val_loss": [round(v, 4) for v in val_loss],
        }
    except Exception as e:
        logger.error(f"训练指标查询失败: {e}")
        return {"epochs": [], "train_auc": [], "val_auc": [], "train_loss": [], "val_loss": []}


@router.post("/predict")
async def predict_signals(req: PredictRequest):
    """获取模型预测结果"""
    try:
        model = _train_model(req.code, req.start_date, req.end_date)

        start = pd.Timestamp(req.start_date).date()
        end = pd.Timestamp(req.end_date).date()
        df = storage.get_stock_daily(req.code, start, end)
        features = pipeline.build_features(df)
        feature_cols = [c for c in features.columns if c not in ["date", "label"]]
        X = features[feature_cols]

        probs = model.predict(X)
        signals = model.predict_signal(X, req.threshold)

        from sklearn.metrics import accuracy_score, roc_auc_score
        valid_mask = features["label"].notna()
        y_true = features.loc[valid_mask, "label"]
        y_pred = probs[valid_mask]
        y_signal = signals[valid_mask]

        accuracy = round(accuracy_score(y_true, y_signal), 4) if len(y_true) > 0 else 0
        auc = round(roc_auc_score(y_true, y_pred), 4) if len(y_true) > 0 else 0

        predictions = []
        for i, row in features.iterrows():
            predictions.append({
                "date": str(row.get("date", "")),
                "probability": round(float(probs[i]), 4),
                "signal": int(signals.iloc[i]),
            })

        return {"predictions": predictions, "accuracy": accuracy, "auc": auc}
    except Exception as e:
        logger.error(f"预测失败: {e}")
        return {"predictions": [], "accuracy": 0, "auc": 0}


@router.get("/kline-signals")
async def get_kline_signals(
    code: str = Query("000001"),
    start_date: str = Query("2024-01-01"),
    end_date: str = Query("2024-12-31"),
):
    """获取K线数据和交易信号"""
    try:
        start = pd.Timestamp(start_date).date()
        end = pd.Timestamp(end_date).date()
        df = storage.get_stock_daily(code, start, end)
        if df.empty:
            return {"kline": [], "signals": []}

        kline = []
        for _, row in df.iterrows():
            kline.append({
                "date": str(row["date"]),
                "open": round(row["open"], 2),
                "high": round(row["high"], 2),
                "low": round(row["low"], 2),
                "close": round(row["close"], 2),
                "volume": int(row["volume"]),
            })

        # 生成简单信号（基于模型预测）
        try:
            model = _train_model(code, start_date, end_date)
            features = pipeline.build_features(df)
            feature_cols = [c for c in features.columns if c not in ["date", "label"]]
            X = features[feature_cols]
            signals_series = model.predict_signal(X)

            signals = []
            for i, row in features.iterrows():
                if signals_series.iloc[i] == 1:
                    signals.append({
                        "date": str(row.get("date", "")),
                        "type": "buy",
                        "price": round(float(df.iloc[i]["close"]), 2) if i < len(df) else 0,
                    })
            return {"kline": kline, "signals": signals}
        except Exception:
            return {"kline": kline, "signals": []}
    except Exception as e:
        logger.error(f"K线信号查询失败: {e}")
        return {"kline": [], "signals": []}
