"""AI Alpha API — 全功能版"""
import hashlib
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import re as _re

from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from pydantic import BaseModel

from alpha.feature_pipeline import FeaturePipeline
from alpha.models.lightgbm_model import LGBConfig, LGBModel
from alpha.models.xgb_model import XGBConfig, XGBModel
from alpha.models.ensemble_model import EnsembleModel, EnsembleConfig
from alpha.evaluator import StrategyEvaluator
from alpha.optimizer import HyperOptimizer, ModelType
from data.storage import DataStorage

router = APIRouter()
storage = DataStorage()
pipeline = FeaturePipeline()

# ── 模型缓存目录 ──
MODEL_CACHE_DIR = Path("models/alpha_cache")
MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ── 请求模型 ──

class PredictRequest(BaseModel):
    code: str = "000001"
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    threshold: float = 0.5
    model_type: str = "lightgbm"
    buy_threshold: float = 0.6
    sell_threshold: float = 0.4


class TrainRequest(BaseModel):
    code: str = "000001"
    start_date: str = "2023-01-01"
    end_date: str = "2024-12-31"
    model_type: str = "lightgbm"


class PerformanceRequest(BaseModel):
    code: str = "000001"
    start_date: str = "2023-01-01"
    end_date: str = "2024-12-31"
    model_type: str = "lightgbm"
    buy_threshold: float = 0.6
    sell_threshold: float = 0.4
    initial_cash: float = 1_000_000


class FactorEvalRequest(BaseModel):
    code: str = "000001"
    start_date: str = "2023-01-01"
    end_date: str = "2024-12-31"
    forward_period: int = 5


class ShapRequest(BaseModel):
    code: str = "000001"
    start_date: str = "2023-01-01"
    end_date: str = "2024-12-31"
    model_type: str = "lightgbm"


class WalkForwardRequest(BaseModel):
    code: str = "000001"
    start_date: str = "2022-01-01"
    end_date: str = "2024-12-31"
    model_type: str = "lightgbm"
    train_days: int = 252
    test_days: int = 21
    step_days: int = 21


class CompareRequest(BaseModel):
    code: str = "000001"
    start_date: str = "2023-01-01"
    end_date: str = "2024-12-31"


class FactorCorrelationRequest(BaseModel):
    code: str = "000001"
    start_date: str = "2023-01-01"
    end_date: str = "2024-12-31"


class FactorDecayRequest(BaseModel):
    code: str = "000001"
    start_date: str = "2023-01-01"
    end_date: str = "2024-12-31"
    top_n: int = 10


class MineRequest(BaseModel):
    code: str = "000001"
    start_date: str = "2023-01-01"
    end_date: str = "2024-12-31"
    top_n: int = 20


class OptimizeRequest(BaseModel):
    code: str = "000001"
    start_date: str = "2023-01-01"
    end_date: str = "2024-12-31"
    model_type: str = "lightgbm"
    n_trials: int = 50


# ── 内部工具函数 ──

def _cache_key(code: str, start: str, end: str, model_type: str) -> str:
    raw = f"{code}_{start}_{end}_{model_type}"
    return hashlib.md5(raw.encode()).hexdigest()


def _create_model(model_type: str, params: Optional[dict] = None):
    """根据类型创建模型实例"""
    if model_type == "xgboost":
        return XGBModel(params=params)
    elif model_type == "ensemble":
        lgb = LGBModel(params=params)
        xgb = XGBModel(params=params)
        return EnsembleModel([lgb, xgb])
    else:
        return LGBModel(params=params)


def _get_features(code: str, start_date: str, end_date: str):
    """获取特征矩阵和原始数据"""
    start = pd.Timestamp(start_date).date()
    end = pd.Timestamp(end_date).date()
    df = storage.get_stock_daily(code, start, end)
    if df.empty:
        raise ValueError(f"无数据: {code}")
    features = pipeline.build_features(df)
    feature_cols = [c for c in features.columns if c not in ["date", "label"]]
    return df, features, feature_cols


def _get_or_train(code: str, start_date: str, end_date: str,
                  model_type: str = "lightgbm", params: Optional[dict] = None,
                  force_retrain: bool = False):
    """带缓存的模型训练"""
    key = _cache_key(code, start_date, end_date, model_type)
    cache_path = MODEL_CACHE_DIR / f"{key}.txt"

    if not force_retrain and cache_path.exists():
        try:
            model = _create_model(model_type, params)
            model.load(str(cache_path))
            logger.info(f"模型缓存命中: {model_type} [{key[:8]}]")
            return model
        except Exception as e:
            logger.warning(f"缓存加载失败，重新训练: {e}")

    # 训练
    df, features, feature_cols = _get_features(code, start_date, end_date)
    X = features[feature_cols]
    y = features["label"]

    split = int(len(X) * 0.8)
    X_train, X_val = X.iloc[:split], X.iloc[split:]
    y_train, y_val = y.iloc[:split], y.iloc[split:]

    model = _create_model(model_type, params)
    model.train(X_train, y_train, X_val, y_val)

    # 保存缓存
    try:
        model.save(str(cache_path))
        logger.info(f"模型已缓存: {model_type} [{key[:8]}]")
    except Exception as e:
        logger.warning(f"缓存保存失败: {e}")

    return model


def _generate_signals(probs: np.ndarray, buy_threshold: float = 0.6,
                      sell_threshold: float = 0.4) -> np.ndarray:
    """双阈值信号生成：1=买入, -1=卖出, 0=持有"""
    signals = np.zeros(len(probs), dtype=int)
    signals[probs > buy_threshold] = 1
    signals[probs < sell_threshold] = -1
    return signals


def _simulate_equity(df: pd.DataFrame, signals: np.ndarray,
                     initial_cash: float = 1_000_000,
                     fee_rate: float = 0.0003,
                     stamp_tax: float = 0.001,
                     slippage: float = 0.002) -> tuple[list[dict], list[dict]]:
    """基于信号模拟交易权益曲线"""
    cash = initial_cash
    position = 0
    avg_price = 0.0
    equity_curve = []
    trades = []

    closes = df["close"].values
    dates = df["date"].values if "date" in df.columns else range(len(df))

    for i in range(len(closes)):
        price = closes[i]
        signal = signals[i] if i < len(signals) else 0

        if signal == 1 and position == 0:
            # 买入
            buy_price = price * (1 + slippage)
            shares = int(cash * 0.95 / buy_price / 100) * 100
            if shares > 0:
                cost = shares * buy_price * fee_rate
                cash -= shares * buy_price + cost
                position = shares
                avg_price = buy_price
                trades.append({"date": str(dates[i]), "type": "buy",
                               "price": round(buy_price, 2), "shares": shares})

        elif signal == -1 and position > 0:
            # 卖出
            sell_price = price * (1 - slippage)
            revenue = position * sell_price
            fee = revenue * fee_rate
            tax = revenue * stamp_tax
            cash += revenue - fee - tax
            trades.append({"date": str(dates[i]), "type": "sell",
                           "price": round(sell_price, 2), "shares": position,
                           "pnl": round((sell_price - avg_price) * position, 2)})
            position = 0
            avg_price = 0.0

        # 计算权益
        equity = cash + position * price
        equity_curve.append({"date": str(dates[i]), "equity": round(equity, 2)})

    return equity_curve, trades


# ── API 端点 ──

@router.get("/factor-importance")
async def get_factor_importance(
    code: str = Query("000001"),
    start_date: str = Query("2023-01-01"),
    end_date: str = Query("2024-12-31"),
    model_type: str = Query("lightgbm"),
):
    """获取因子重要性 Top 20"""
    try:
        model = _get_or_train(code, start_date, end_date, model_type)
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
    model_type: str = Query("lightgbm"),
):
    """获取模型训练曲线数据"""
    try:
        model = _get_or_train(code, start_date, end_date, model_type)
        evals = model.get_evals_result()

        if not evals:
            return {"epochs": [], "train_auc": [], "val_auc": [],
                    "train_loss": [], "val_loss": []}

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
        return {"epochs": [], "train_auc": [], "val_auc": [],
                "train_loss": [], "val_loss": []}


@router.post("/predict")
async def predict_signals(req: PredictRequest):
    """获取模型预测结果（含卖出信号）"""
    try:
        model = _get_or_train(req.code, req.start_date, req.end_date, req.model_type)
        df, features, feature_cols = _get_features(req.code, req.start_date, req.end_date)
        X = features[feature_cols]

        probs = model.predict(X)
        signals = _generate_signals(probs, req.buy_threshold, req.sell_threshold)

        from sklearn.metrics import accuracy_score, roc_auc_score
        valid_mask = features["label"].notna()
        y_true = features.loc[valid_mask, "label"]
        y_pred = probs[valid_mask]

        # 二值化信号用于 accuracy 计算
        binary_signal = (signals > 0).astype(int)
        y_signal = binary_signal[valid_mask]

        accuracy = round(accuracy_score(y_true, y_signal), 4) if len(y_true) > 0 else 0
        auc = round(roc_auc_score(y_true, y_pred), 4) if len(y_true) > 0 else 0

        predictions = []
        for idx, (_, row) in enumerate(features.iterrows()):
            predictions.append({
                "date": str(row.get("date", "")),
                "probability": round(float(probs[idx]), 4),
                "signal": int(signals[idx]),
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
    model_type: str = Query("lightgbm"),
    buy_threshold: float = Query(0.6),
    sell_threshold: float = Query(0.4),
):
    """获取K线数据和买卖信号"""
    if not _re.match(r'^\d{6}$', code):
        raise HTTPException(400, "股票代码必须为6位数字")
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

        try:
            model = _get_or_train(code, start_date, end_date, model_type)
            features = pipeline.build_features(df)
            feature_cols = [c for c in features.columns if c not in ["date", "label"]]
            X = features[feature_cols]
            probs = model.predict(X)
            raw_signals = _generate_signals(probs, buy_threshold, sell_threshold)

            signals = []
            for idx, (_, row) in enumerate(features.iterrows()):
                sig = raw_signals[idx]
                if idx < len(df):
                    price = round(float(df.iloc[idx]["close"]), 2)
                    sig_date = str(df.iloc[idx]["date"])
                else:
                    price = 0
                    sig_date = str(row.get("date", ""))
                if sig == 1:
                    signals.append({"date": sig_date,
                                    "type": "buy", "price": price})
                elif sig == -1:
                    signals.append({"date": sig_date,
                                    "type": "sell", "price": price})
            return {"kline": kline, "signals": signals}
        except Exception:
            return {"kline": kline, "signals": []}
    except Exception as e:
        logger.error(f"K线信号查询失败: {e}")
        return {"kline": [], "signals": []}


@router.post("/performance")
async def get_performance(req: PerformanceRequest):
    """策略绩效评估"""
    try:
        model = _get_or_train(req.code, req.start_date, req.end_date, req.model_type)
        df, features, feature_cols = _get_features(req.code, req.start_date, req.end_date)
        X = features[feature_cols]

        probs = model.predict(X)
        signals = _generate_signals(probs, req.buy_threshold, req.sell_threshold)

        equity_curve, trades = _simulate_equity(
            df, signals, req.initial_cash)

        # 评估
        metrics = StrategyEvaluator.evaluate(equity_curve, req.initial_cash)

        # 交易统计
        buy_count = sum(1 for t in trades if t["type"] == "buy")
        sell_count = sum(1 for t in trades if t["type"] == "sell")
        win_trades = [t for t in trades if t["type"] == "sell" and t.get("pnl", 0) > 0]
        loss_trades = [t for t in trades if t["type"] == "sell" and t.get("pnl", 0) <= 0]

        win_rate = len(win_trades) / sell_count if sell_count > 0 else 0
        avg_win = np.mean([t["pnl"] for t in win_trades]) if win_trades else 0
        avg_loss = np.mean([abs(t["pnl"]) for t in loss_trades]) if loss_trades else 0
        profit_ratio = avg_win / avg_loss if avg_loss > 0 else 0

        return {
            "metrics": metrics,
            "equity_curve": equity_curve,
            "trades": trades[-50:],  # 最近 50 笔
            "summary": {
                "buy_count": buy_count,
                "sell_count": sell_count,
                "win_rate": round(win_rate, 4),
                "profit_ratio": round(profit_ratio, 2),
                "avg_win": round(avg_win, 2),
                "avg_loss": round(avg_loss, 2),
            },
        }
    except Exception as e:
        logger.error(f"绩效评估失败: {e}")
        return {"metrics": {}, "equity_curve": [], "trades": [], "summary": {}}


@router.post("/factor-eval")
async def evaluate_factors(req: FactorEvalRequest):
    """因子评价：IC/IR/分层收益/换手率"""
    try:
        start = pd.Timestamp(req.start_date).date()
        end = pd.Timestamp(req.end_date).date()
        df = storage.get_stock_daily(req.code, start, end)
        if df.empty:
            return []

        features = pipeline.build_features(df)
        feature_cols = [c for c in features.columns if c not in ["date", "label"]]

        # 未来 N 日收益
        fwd_returns = df["close"].pct_change(req.forward_period).shift(-req.forward_period)

        results = []
        for col in feature_cols:
            factor = features[col].dropna()
            common_idx = factor.index.intersection(fwd_returns.dropna().index)
            if len(common_idx) < 30:
                continue

            f = factor.loc[common_idx]
            r = fwd_returns.loc[common_idx]

            # IC 序列（用滚动窗口计算）
            ic = f.corr(r, method='spearman')

            # 分层收益（5 组）
            try:
                groups = pd.qcut(f, 5, labels=False, duplicates='drop')
                quantile_ret = r.groupby(groups).mean()
                q_returns = [round(v, 6) for v in quantile_ret.values]
            except Exception:
                q_returns = []

            # 换手率
            n = max(int(len(f) * 0.2), 1)
            turnover_vals = []
            for day_idx in range(20, len(f)):
                today_top = set(f.iloc[day_idx - n:day_idx].nlargest(n).index)
                yesterday_top = set(f.iloc[day_idx - n - 1:day_idx - 1].nlargest(n).index)
                if yesterday_top:
                    changed = len(today_top - yesterday_top)
                    turnover_vals.append(changed / max(len(today_top), 1))
            avg_turnover = round(np.mean(turnover_vals), 4) if turnover_vals else 0

            results.append({
                "factor": col,
                "ic": round(ic, 4) if not np.isnan(ic) else 0,
                "abs_ic": round(abs(ic), 4) if not np.isnan(ic) else 0,
                "turnover": avg_turnover,
                "quantile_returns": q_returns,
            })

        return sorted(results, key=lambda x: x["abs_ic"], reverse=True)
    except Exception as e:
        logger.error(f"因子评价失败: {e}")
        return []


@router.post("/shap")
async def get_shap(req: ShapRequest):
    """SHAP 可解释性分析"""
    try:
        import shap as shap_lib

        model = _get_or_train(req.code, req.start_date, req.end_date, req.model_type)
        df, features, feature_cols = _get_features(req.code, req.start_date, req.end_date)
        X = features[feature_cols]

        # 获取底层模型
        if hasattr(model, '_model'):
            inner_model = model._model
        else:
            return {"global_importance": [], "dependence": {}, "error": "不支持的模型类型"}

        explainer = shap_lib.TreeExplainer(inner_model)
        shap_values = explainer.shap_values(X)

        # 如果返回 list（二分类取正类）
        if isinstance(shap_values, list):
            shap_values = shap_values[1]

        # 全局重要性
        global_imp = np.abs(shap_values).mean(axis=0)
        importance_list = sorted(
            [{"feature": feature_cols[i], "shap_importance": round(float(global_imp[i]), 6)}
             for i in range(len(feature_cols))],
            key=lambda x: x["shap_importance"], reverse=True
        )

        # SHAP 依赖图数据（Top 3 因子）
        top_features = [item["feature"] for item in importance_list[:3]]
        dependence = {}
        for feat in top_features:
            idx = feature_cols.index(feat)
            dependence[feat] = {
                "feature_values": [round(float(v), 4) for v in X.iloc[:, idx].values[:200]],
                "shap_values": [round(float(v), 6) for v in shap_values[:200, idx]],
            }

        # Beeswarm 数据（采样 100 条）
        sample_indices = np.linspace(0, len(X) - 1, min(100, len(X)), dtype=int)
        beeswarm = []
        for si in sample_indices:
            for fi, feat in enumerate(feature_cols):
                beeswarm.append({
                    "feature": feat,
                    "feature_value": round(float(X.iloc[si, fi]), 4),
                    "shap_value": round(float(shap_values[si, fi]), 6),
                })

        return {
            "global_importance": importance_list,
            "dependence": dependence,
            "beeswarm": beeswarm,
        }
    except ImportError:
        return {"global_importance": [], "dependence": {}, "error": "shap 未安装"}
    except Exception as e:
        logger.error(f"SHAP 分析失败: {e}")
        return {"global_importance": [], "dependence": {}, "error": "SHAP 分析失败，请查看服务端日志"}


@router.post("/walk-forward")
async def walk_forward(req: WalkForwardRequest):
    """Walk-forward 滚动验证"""
    try:
        df, features, feature_cols = _get_features(req.code, req.start_date, req.end_date)
        X = features[feature_cols]
        y = features["label"]

        from sklearn.metrics import roc_auc_score

        results = []
        n = len(X)
        start = 0

        while start + req.train_days + req.test_days <= n:
            train_end = start + req.train_days
            test_end = min(train_end + req.test_days, n)

            X_train = X.iloc[start:train_end]
            y_train = y.iloc[start:train_end]
            X_test = X.iloc[train_end:test_end]
            y_test = y.iloc[train_end:test_end]

            model = _create_model(req.model_type)
            val_split = int(len(X_train) * 0.85)
            model.train(
                X_train.iloc[:val_split], y_train.iloc[:val_split],
                X_train.iloc[val_split:], y_train.iloc[val_split:]
            )

            test_pred = model.predict(X_test)
            train_pred = model.predict(X_train)

            test_auc = roc_auc_score(y_test, test_pred) if len(y_test.unique()) > 1 else 0.5
            train_auc = roc_auc_score(y_train, train_pred) if len(y_train.unique()) > 1 else 0.5

            results.append({
                "window": len(results) + 1,
                "start": str(X.index[start]),
                "end": str(X.index[test_end - 1]),
                "train_auc": round(train_auc, 4),
                "test_auc": round(test_auc, 4),
                "gap": round(train_auc - test_auc, 4),
                "n_train": len(X_train),
                "n_test": len(X_test),
            })
            start += req.step_days

        # 稳定性分析
        test_aucs = [r["test_auc"] for r in results]
        stability = {
            "mean_auc": round(np.mean(test_aucs), 4) if test_aucs else 0,
            "std_auc": round(np.std(test_aucs), 4) if test_aucs else 0,
            "min_auc": round(min(test_aucs), 4) if test_aucs else 0,
            "max_auc": round(max(test_aucs), 4) if test_aucs else 0,
            "n_windows": len(results),
            "is_stable": bool(np.std(test_aucs) < 0.05) if test_aucs else False,
        }

        return {"windows": results, "stability": stability}
    except Exception as e:
        logger.error(f"Walk-forward 验证失败: {e}")
        return {"windows": [], "stability": {}}


@router.post("/compare")
async def compare_models(req: CompareRequest):
    """多模型对比"""
    try:
        df, features, feature_cols = _get_features(req.code, req.start_date, req.end_date)
        X = features[feature_cols]
        y = features["label"]

        from sklearn.metrics import accuracy_score, roc_auc_score
        split = int(len(X) * 0.8)
        X_train, X_val = X.iloc[:split], X.iloc[split:]
        y_train, y_val = y.iloc[:split], y.iloc[split:]

        results = {}
        for model_type in ["lightgbm", "xgboost", "ensemble"]:
            try:
                model = _create_model(model_type)
                model.train(X_train, y_train, X_val, y_val)

                val_pred = model.predict(X_val)
                val_signal = (val_pred > 0.5).astype(int)

                auc = round(roc_auc_score(y_val, val_pred), 4) if len(y_val.unique()) > 1 else 0
                acc = round(accuracy_score(y_val, val_signal), 4)

                importance = model.feature_importance().head(10).to_dict("records")

                results[model_type] = {
                    "auc": auc,
                    "accuracy": acc,
                    "top_features": importance,
                    "n_estimators": getattr(model, '_config', {}).get('n_estimators', 'N/A'),
                }
            except Exception as e:
                results[model_type] = {"error": str(e)}

        return results
    except Exception as e:
        logger.error(f"模型对比失败: {e}")
        return {}


@router.post("/factor-correlation")
async def factor_correlation(req: FactorCorrelationRequest):
    """因子相关性矩阵"""
    try:
        start = pd.Timestamp(req.start_date).date()
        end = pd.Timestamp(req.end_date).date()
        df = storage.get_stock_daily(req.code, start, end)
        if df.empty:
            return {"factors": [], "matrix": [], "high_corr_pairs": []}

        features = pipeline.build_features(df)
        feature_cols = [c for c in features.columns if c not in ("date", "label")]

        corr_matrix = features[feature_cols].corr(method='spearman')

        # 高相关因子对
        high_corr = []
        for i in range(len(feature_cols)):
            for j in range(i + 1, len(feature_cols)):
                val = corr_matrix.iloc[i, j]
                if abs(val) > 0.8:
                    high_corr.append({
                        "factor_a": feature_cols[i],
                        "factor_b": feature_cols[j],
                        "correlation": round(val, 3),
                    })
        high_corr.sort(key=lambda x: abs(x["correlation"]), reverse=True)

        return {
            "factors": feature_cols,
            "matrix": corr_matrix.round(3).values.tolist(),
            "high_corr_pairs": high_corr[:20],
        }
    except Exception as e:
        logger.error(f"因子相关性分析失败: {e}")
        return {"factors": [], "matrix": [], "high_corr_pairs": []}


@router.post("/factor-decay")
async def factor_decay(req: FactorDecayRequest):
    """因子衰减分析：IC 随持仓天数变化"""
    try:
        start = pd.Timestamp(req.start_date).date()
        end = pd.Timestamp(req.end_date).date()
        df = storage.get_stock_daily(code=req.code, start_date=start, end_date=end)
        if df.empty:
            return {}

        features = pipeline.build_features(df)
        feature_cols = [c for c in features.columns if c not in ("date", "label")]

        # 选 Top N 因子（按与次日收益的 IC 排序）
        fwd_1d = df["close"].pct_change(1).shift(-1)
        factor_ics = {}
        for col in feature_cols:
            common = features[col].dropna().index.intersection(fwd_1d.dropna().index)
            if len(common) > 30:
                ic = features[col].loc[common].corr(fwd_1d.loc[common], method='spearman')
                if not np.isnan(ic):
                    factor_ics[col] = abs(ic)

        top_factors = sorted(factor_ics, key=factor_ics.get, reverse=True)[:req.top_n]

        # 对每个因子计算不同持仓期的 IC
        periods = [1, 3, 5, 10, 20, 60]
        results = {}
        for factor_name in top_factors:
            results[factor_name] = {}
            for p in periods:
                fwd_ret = df["close"].pct_change(p).shift(-p)
                common = features[factor_name].dropna().index.intersection(fwd_ret.dropna().index)
                if len(common) > 30:
                    ic = features[factor_name].loc[common].corr(fwd_ret.loc[common], method='spearman')
                    results[factor_name][f"{p}d"] = round(ic, 4) if not np.isnan(ic) else 0
                else:
                    results[factor_name][f"{p}d"] = 0

        return results
    except Exception as e:
        logger.error(f"因子衰减分析失败: {e}")
        return {}


@router.post("/mine")
async def mine_factors(req: MineRequest):
    """自动因子挖掘"""
    try:
        start = pd.Timestamp(req.start_date).date()
        end = pd.Timestamp(req.end_date).date()
        df = storage.get_stock_daily(req.code, start, end)
        if df.empty:
            return []

        features = pipeline.build_features(df)
        feature_cols = [c for c in features.columns if c not in ("date", "label")]

        # 组合运算
        operations = {
            "diff": lambda a, b: a - b,
            "ratio": lambda a, b: a / b.replace(0, np.nan),
            "product": lambda a, b: a * b,
        }

        label = features["label"]
        candidates = []

        for i, a in enumerate(feature_cols):
            for b in feature_cols[i + 1:]:
                for op_name, op_fn in operations.items():
                    try:
                        new_factor = op_fn(features[a], features[b])
                        common = new_factor.dropna().index.intersection(label.dropna().index)
                        if len(common) < 30:
                            continue
                        ic = new_factor.loc[common].corr(label.loc[common], method='spearman')
                        if not np.isnan(ic) and abs(ic) > 0.02:
                            candidates.append({
                                "name": f"{op_name}({a},{b})",
                                "ic": round(ic, 4),
                                "abs_ic": round(abs(ic), 4),
                                "operation": op_name,
                                "parent_a": a,
                                "parent_b": b,
                            })
                    except Exception:
                        continue

        return sorted(candidates, key=lambda x: x["abs_ic"], reverse=True)[:req.top_n]
    except Exception as e:
        logger.error(f"因子挖掘失败: {e}")
        return []


@router.post("/optimize")
async def optimize_params(req: OptimizeRequest):
    """Optuna 超参优化"""
    try:
        df, features, feature_cols = _get_features(req.code, req.start_date, req.end_date)
        X = features[feature_cols]
        y = features["label"]

        if req.model_type == "lightgbm":
            model_type = ModelType.LIGHTGBM
        elif req.model_type == "xgboost":
            model_type = ModelType.XGBOOST
        else:
            return {"best_params": {}, "error": f"不支持的模型类型: {req.model_type}，仅支持 lightgbm/xgboost"}
        optimizer = HyperOptimizer(n_trials=req.n_trials, n_splits=3)
        best_params = optimizer.optimize(X, y, model_type)

        # 用优化后的参数重新训练并缓存
        model = _get_or_train(req.code, req.start_date, req.end_date,
                              req.model_type, params=best_params, force_retrain=True)

        return {
            "best_params": best_params,
            "model_type": req.model_type,
            "n_trials": req.n_trials,
            "status": "优化完成，模型已更新",
        }
    except Exception as e:
        logger.error(f"超参优化失败: {e}")
        return {"best_params": {}, "error": "超参优化失败，请查看服务端日志"}


# ── 跨截面 AI 选股端点 ──

from alpha.cross_sectional import CrossSectionalPipeline

_cs_pipeline = CrossSectionalPipeline()


class TrainGlobalRequest(BaseModel):
    model_type: str = "lightgbm"
    use_history: bool = False
    codes: list[str] = []
    start_date: str = "2023-01-01"
    end_date: str = "2024-12-31"
    forward_days: int = 5


@router.post("/train-global")
async def train_global(req: TrainGlobalRequest):
    """训练全市场截面选股模型"""
    try:
        if req.use_history and req.codes:
            result = _cs_pipeline.train_from_history(
                codes=req.codes,
                start_date=req.start_date,
                end_date=req.end_date,
                forward_days=req.forward_days,
                model_type=req.model_type,
            )
        else:
            result = _cs_pipeline.train_from_snapshot(
                model_type=req.model_type,
            )
        # 清理 NaN/Inf 值，确保 JSON 序列化兼容
        import math
        def _clean(v):
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                return 0.0
            if isinstance(v, dict):
                return {k: _clean(vv) for k, vv in v.items()}
            if isinstance(v, list):
                return [_clean(vv) for vv in v]
            return v
        return _clean(result)
    except Exception as e:
        logger.error(f"全市场训练失败: {e}")
        return {"success": False, "error": str(e)}


@router.get("/screen-ai")
async def screen_ai(
    top_n: int = Query(20, ge=1, le=100),
):
    """AI 截面选股：返回 TOP N 推荐股票"""
    try:
        results = _cs_pipeline.predict(top_n=top_n)
        return {
            "success": True,
            "stocks": [r.to_dict() for r in results],
            "total": len(results),
        }
    except RuntimeError:
        return {"success": False, "error": "模型未训练，请先执行训练", "stocks": []}
    except Exception as e:
        logger.error(f"AI 选股失败: {e}")
        return {"success": False, "error": str(e), "stocks": []}


@router.get("/model-status")
async def model_status():
    """检查截面模型状态"""
    from pathlib import Path
    model_dir = Path("models/cross_sectional")
    meta_path = model_dir / "meta.json"
    model_path = model_dir / "model"
    exists = meta_path.exists() and any(model_dir.glob("model*"))
    meta = {}
    if meta_path.exists():
        import json
        meta = json.loads(meta_path.read_text())
    return {
        "trained": exists,
        "feature_count": len(meta.get("feature_names", [])),
        "features": meta.get("feature_names", []),
    }


class BacktestPortfolioRequest(BaseModel):
    top_n: int = 20
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    rebalance_days: int = 5
    allocation: str = "equal"
    initial_cash: float = 1_000_000


@router.post("/backtest-portfolio")
async def backtest_portfolio(req: BacktestPortfolioRequest):
    """组合回测：基于 AI 选股结果模拟组合交易"""
    try:
        from alpha.backtest import PortfolioBacktester, BacktestConfig

        config = BacktestConfig(
            initial_cash=req.initial_cash,
            rebalance_days=req.rebalance_days,
            allocation=req.allocation,
        )
        backtester = PortfolioBacktester(config)

        # 获取预测结果（当前模型）
        predictions = _cs_pipeline.predict(top_n=req.top_n)
        pred_list = [p.to_dict() for p in predictions]

        # 获取价格数据
        codes = [p["code"] for p in pred_list]
        price_data = {}
        start = pd.Timestamp(req.start_date).date()
        end = pd.Timestamp(req.end_date).date()
        for code in codes:
            df = storage.get_stock_daily(code, start, end)
            if not df.empty:
                price_data[code] = df

        if not price_data:
            return {"success": False, "error": "无可用价格数据"}

        # 用同一天的预测模拟（简化：每天用相同预测）
        # 实际应按日期重新预测，此处为快速验证
        first_date = min(
            df["date"].iloc[0]
            for df in price_data.values()
            if len(df) > 0
        )
        predictions_by_date = {str(first_date): pred_list}

        result = backtester.run(predictions_by_date, price_data)
        return {"success": True, **result.to_dict()}
    except Exception as e:
        logger.error(f"组合回测失败: {e}")
        return {"success": False, "error": str(e)}
