"""AI 跨截面选股模型

基于全市场截面因子矩阵，训练集成模型（LightGBM + XGBoost），
预测个股未来 N 日收益排名，输出 TOP N 推荐列表。

数据源：
- 实时快照：screener._fetch_market_stocks()（东方财富 push2delay API）
- 历史数据：storage.get_stock_daily()（SQLite 日K线）
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger

from alpha.screener import _fetch_market_stocks, _DIV100_FIELDS, _DIV1E8_FIELDS


# ── 常量 ──

_MODEL_DIR = Path("models/cross_sectional")
_MODEL_DIR.mkdir(parents=True, exist_ok=True)

# 截面特征：从 screener 实时数据计算的横截面排名百分位
_CROSS_SECTIONAL_FEATURES = [
    "rank_change_pct", "rank_pe_ratio", "rank_pb_ratio",
    "rank_market_cap", "rank_turnover_rate",
    "rank_amplitude", "rank_price",
    "log_market_cap", "value_score", "activity_score",
]

_LABEL_COL = "label"
_TOP_QUANTILE = 0.3   # 正样本：未来收益排名前 30%
_BOTTOM_QUANTILE = 0.3  # 负样本：未来收益排名后 30%


# ── 数据类 ──

@dataclass
class PredictionResult:
    """单只股票的预测结果"""
    code: str
    name: str
    industry: str
    probability: float
    rank: int
    risk_score: float
    key_factors: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "industry": self.industry,
            "probability": round(self.probability, 4),
            "rank": self.rank,
            "risk_score": round(self.risk_score, 4),
            "key_factors": {k: round(v, 4) for k, v in self.key_factors.items()},
        }


# ── 工具函数 ──

def _compute_cross_sectional_features(stocks: list[dict]) -> pd.DataFrame:
    """从全市场快照计算截面特征

    输入: _fetch_market_stocks() 返回的 list[dict]
    输出: DataFrame，index=股票代码，columns=截面特征
    """
    df = pd.DataFrame(stocks)
    if df.empty:
        return pd.DataFrame()

    df = df.set_index("code")

    # 数值字段排名百分位
    rank_fields = [
        "change_pct", "pe_ratio", "pb_ratio", "market_cap",
        "turnover_rate", "amplitude", "price",
    ]
    for f in rank_fields:
        if f in df.columns:
            col = pd.to_numeric(df[f], errors="coerce")
            df[f"rank_{f}"] = col.rank(pct=True)

    # 对数市值
    if "market_cap" in df.columns:
        mc = pd.to_numeric(df["market_cap"], errors="coerce").clip(lower=1)
        df["log_market_cap"] = np.log10(mc)

    # 综合因子：价值分（PE 低 + PB 低 = 高分）
    if "rank_pe_ratio" in df.columns and "rank_pb_ratio" in df.columns:
        df["value_score"] = (1 - df["rank_pe_ratio"]) * 0.5 + (1 - df["rank_pb_ratio"]) * 0.5

    # 综合因子：活跃度分（volume_ratio 已移除，用 turnover_rate + amplitude 代替）
    act_fields = ["rank_turnover_rate", "rank_amplitude"]
    if all(f in df.columns for f in act_fields):
        df["activity_score"] = df[act_fields].mean(axis=1)

    feature_cols = [c for c in _CROSS_SECTIONAL_FEATURES if c in df.columns]
    return df[feature_cols].replace([np.inf, -np.inf], np.nan)


def _compute_labels(stocks: list[dict], forward_days: int = 5) -> pd.Series:
    """基于截面收益排名生成标签

    当前快照只能用 change_pct 作为代理（当日已实现收益）。
    历史训练时应使用真正的 N 日前瞻收益。
    """
    df = pd.DataFrame(stocks)
    if df.empty or "change_pct" not in df.columns:
        return pd.Series(dtype=float)

    df = df.set_index("code")
    ret = pd.to_numeric(df["change_pct"], errors="coerce")

    top_threshold = ret.quantile(1 - _TOP_QUANTILE)
    bottom_threshold = ret.quantile(_BOTTOM_QUANTILE)

    labels = pd.Series(np.nan, index=df.index)
    labels[ret >= top_threshold] = 1.0
    labels[ret <= bottom_threshold] = 0.0

    return labels.dropna()


# ── 核心类 ──

class CrossSectionalPipeline:
    """跨截面选股 Pipeline

    支持两种模式：
    1. 快照预测：基于当前全市场数据，使用已有模型预测
    2. 历史训练：从 storage 获取多股日K线，构建截面数据集训练
    """

    def __init__(self):
        self._model = None
        self._feature_names: list[str] = []

    def train_from_snapshot(
        self,
        top_n: int = 20,
        model_type: str = "lightgbm",
    ) -> dict:
        """基于当前快照训练模型（快速但精度有限）

        用当前截面数据的 change_pct 排名作为标签代理。
        适合快速验证 pipeline 是否工作。
        """
        from alpha.models.lightgbm_model import LGBModel
        from alpha.models.xgb_model import XGBModel
        from alpha.models.ensemble_model import EnsembleModel

        stocks = _fetch_market_stocks()
        if not stocks:
            raise ValueError("无法获取全市场数据")

        features = _compute_cross_sectional_features(stocks)
        labels = _compute_labels(stocks)

        common_idx = features.index.intersection(labels.index)
        X = features.loc[common_idx].dropna()
        y = labels.loc[X.index]

        if len(X) < 100:
            raise ValueError(f"样本不足: {len(X)}")

        self._feature_names = list(X.columns)

        split = int(len(X) * 0.8)
        X_train, X_val = X.iloc[:split], X.iloc[split:]
        y_train, y_val = y.iloc[:split], y.iloc[split:]

        if model_type == "ensemble":
            self._model = EnsembleModel([LGBModel(), XGBModel()])
        elif model_type == "xgboost":
            self._model = XGBModel()
        else:
            self._model = LGBModel()

        metrics = self._model.train(X_train, y_train, X_val, y_val)
        self._save_model()

        return {
            "success": True,
            "model_type": model_type,
            "n_samples": len(X),
            "n_features": len(self._feature_names),
            "metrics": metrics,
        }

    def train_from_history(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
        forward_days: int = 5,
        model_type: str = "ensemble",
    ) -> dict:
        """从历史数据构建截面数据集并训练

        从 storage 获取多只股票的日K线，按日期构建截面因子矩阵，
        用 N 日前瞻收益排名作为标签。
        """
        from alpha.models.lightgbm_model import LGBModel
        from alpha.models.xgb_model import XGBModel
        from alpha.models.ensemble_model import EnsembleModel
        from data.storage import DataStorage

        storage = DataStorage()
        start = pd.Timestamp(start_date).date()
        end = pd.Timestamp(end_date).date()

        all_frames = []
        for code in codes:
            df = storage.get_stock_daily(code, start, end)
            if df.empty or len(df) < forward_days + 60:
                continue
            df["code"] = code
            all_frames.append(df)

        if len(all_frames) < 20:
            raise ValueError(f"有效股票不足: {len(all_frames)}")

        combined = pd.concat(all_frames, ignore_index=True)
        logger.info(f"历史数据: {len(all_frames)} 只股票, {len(combined)} 行")

        dataset = self._build_cross_sectional_dataset(combined, forward_days)
        if dataset.empty:
            raise ValueError("截面数据集为空")

        feature_cols = [c for c in dataset.columns if c not in (_LABEL_COL, "code", "date")]
        X = dataset[feature_cols].dropna()
        y = dataset.loc[X.index, _LABEL_COL]

        self._feature_names = feature_cols

        split_idx = int(len(X) * 0.8)
        X_train, X_val = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_val = y.iloc[:split_idx], y.iloc[split_idx:]

        if model_type == "ensemble":
            self._model = EnsembleModel([LGBModel(), XGBModel()])
        elif model_type == "xgboost":
            self._model = XGBModel()
        else:
            self._model = LGBModel()

        metrics = self._model.train(X_train, y_train, X_val, y_val)
        self._save_model()

        return {
            "success": True,
            "model_type": model_type,
            "n_stocks": len(all_frames),
            "n_samples": len(X),
            "n_features": len(feature_cols),
            "metrics": metrics,
        }

    def predict(
        self,
        top_n: int = 20,
        model_path: Optional[str] = None,
    ) -> list[PredictionResult]:
        """基于当前市场快照预测 TOP N 股票"""
        if self._model is None:
            self._load_model(model_path)

        if self._model is None:
            raise RuntimeError("模型未训练，请先调用 train_from_snapshot() 或 train_from_history()")

        stocks = _fetch_market_stocks()
        if not stocks:
            raise ValueError("无法获取全市场数据")

        features = _compute_cross_sectional_features(stocks)

        missing = [f for f in self._feature_names if f not in features.columns]
        if missing:
            raise ValueError(f"特征缺失: {missing}")

        X = features[self._feature_names].dropna()
        if X.empty:
            raise ValueError("无有效特征数据")

        probs = self._model.predict(X)

        stock_map = {s["code"]: s for s in stocks}
        results = []
        for i, code in enumerate(X.index):
            stock = stock_map.get(code, {})
            risk = abs(probs[i] - 0.5) * 2
            key_factors = {}
            for col in self._feature_names[:5]:
                key_factors[col] = float(X.loc[code, col]) if col in X.columns else 0.0

            results.append(PredictionResult(
                code=str(code),
                name=stock.get("name", ""),
                industry=stock.get("industry", ""),
                probability=float(probs[i]),
                rank=0,
                risk_score=float(1 - risk),
                key_factors=key_factors,
            ))

        results.sort(key=lambda r: r.probability, reverse=True)
        for i, r in enumerate(results):
            r.rank = i + 1

        return results[:top_n]

    def get_feature_importance(self) -> list[dict]:
        """获取模型特征重要性"""
        if self._model is None:
            self._load_model()
        if self._model is None:
            return []

        imp = self._model.feature_importance()
        return imp.head(15).to_dict("records")

    def walk_forward_validate(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
        train_days: int = 120,
        test_days: int = 20,
        step_days: int = 20,
        forward_days: int = 5,
        model_type: str = "lightgbm",
    ) -> dict:
        """Walk-forward 滚动验证"""
        from alpha.models.lightgbm_model import LGBModel
        from alpha.models.xgb_model import XGBModel
        from sklearn.metrics import roc_auc_score
        from data.storage import DataStorage

        storage = DataStorage()
        start = pd.Timestamp(start_date).date()
        end = pd.Timestamp(end_date).date()

        all_frames = []
        for code in codes:
            df = storage.get_stock_daily(code, start, end)
            if df.empty or len(df) < train_days + test_days:
                continue
            df["code"] = code
            all_frames.append(df)

        if len(all_frames) < 20:
            return {"windows": [], "stability": {"error": "数据不足"}}

        combined = pd.concat(all_frames, ignore_index=True)
        dataset = self._build_cross_sectional_dataset(combined, forward_days)

        if dataset.empty:
            return {"windows": [], "stability": {"error": "截面数据集为空"}}

        feature_cols = [c for c in dataset.columns if c not in (_LABEL_COL, "code", "date")]
        dates = sorted(dataset["date"].unique())

        results = []
        for i in range(0, len(dates) - train_days - test_days, step_days):
            train_dates = dates[i:i + train_days]
            test_dates = dates[i + train_days:i + train_days + test_days]

            train_data = dataset[dataset["date"].isin(train_dates)].dropna(subset=feature_cols + [_LABEL_COL])
            test_data = dataset[dataset["date"].isin(test_dates)].dropna(subset=feature_cols + [_LABEL_COL])

            if len(train_data) < 100 or len(test_data) < 30:
                continue

            X_train = train_data[feature_cols]
            y_train = train_data[_LABEL_COL]
            X_test = test_data[feature_cols]
            y_test = test_data[_LABEL_COL]

            if model_type == "xgboost":
                model = XGBModel()
            else:
                model = LGBModel()

            val_split = int(len(X_train) * 0.85)
            model.train(X_train.iloc[:val_split], y_train.iloc[:val_split],
                        X_train.iloc[val_split:], y_train.iloc[val_split:])

            train_pred = model.predict(X_train)
            test_pred = model.predict(X_test)

            train_auc = roc_auc_score(y_train, train_pred) if len(y_train.unique()) > 1 else 0.5
            test_auc = roc_auc_score(y_test, test_pred) if len(y_test.unique()) > 1 else 0.5

            results.append({
                "window": len(results) + 1,
                "start": str(train_dates[0]),
                "end": str(test_dates[-1]),
                "train_auc": round(train_auc, 4),
                "test_auc": round(test_auc, 4),
                "gap": round(train_auc - test_auc, 4),
                "n_train": len(train_data),
                "n_test": len(test_data),
            })

        test_aucs = [r["test_auc"] for r in results]
        stability = {
            "mean_auc": round(float(np.mean(test_aucs)), 4) if test_aucs else 0,
            "std_auc": round(float(np.std(test_aucs)), 4) if test_aucs else 0,
            "min_auc": round(float(min(test_aucs)), 4) if test_aucs else 0,
            "max_auc": round(float(max(test_aucs)), 4) if test_aucs else 0,
            "n_windows": len(results),
            "is_stable": bool(np.std(test_aucs) < 0.05) if test_aucs else False,
        }

        return {"windows": results, "stability": stability}

    # ── 内部方法 ──

    def _build_cross_sectional_dataset(
        self, combined: pd.DataFrame, forward_days: int,
    ) -> pd.DataFrame:
        """从多股合并数据构建截面数据集"""
        from alpha.factors.technical import TechnicalFactors

        all_rows = []
        for code, group in combined.groupby("code"):
            group = group.sort_values("date").reset_index(drop=True)
            if len(group) < 60:
                continue

            tech = TechnicalFactors.compute_all(group)
            tech["code"] = code
            tech["date"] = group["date"]
            tech["close"] = group["close"]

            fwd_ret = group["close"].pct_change(forward_days).shift(-forward_days)
            tech["fwd_return"] = fwd_ret

            all_rows.append(tech)

        if not all_rows:
            return pd.DataFrame()

        merged = pd.concat(all_rows, ignore_index=True)

        feature_cols = [c for c in merged.columns
                        if c not in ("code", "date", "close", "fwd_return", _LABEL_COL)]

        rows = []
        for dt, group in merged.groupby("date"):
            group = group.dropna(subset=feature_cols + ["fwd_return"])
            if len(group) < 30:
                continue

            for col in feature_cols:
                group[f"cs_rank_{col}"] = group[col].rank(pct=True)

            rank_cols = [c for c in group.columns if c.startswith("cs_rank_")]

            top_thresh = group["fwd_return"].quantile(1 - _TOP_QUANTILE)
            bot_thresh = group["fwd_return"].quantile(_BOTTOM_QUANTILE)

            labeled = group[
                (group["fwd_return"] >= top_thresh) | (group["fwd_return"] <= bot_thresh)
            ].copy()
            labeled[_LABEL_COL] = (labeled["fwd_return"] >= top_thresh).astype(int)

            for _, row in labeled.iterrows():
                row_data = {col: row[col] for col in rank_cols}
                row_data[_LABEL_COL] = row[_LABEL_COL]
                row_data["code"] = row["code"]
                row_data["date"] = dt
                rows.append(row_data)

        return pd.DataFrame(rows)

    def _save_model(self):
        """保存模型和元数据"""
        if self._model is None:
            return
        model_path = _MODEL_DIR / "model"
        self._model.save(str(model_path))
        meta = {"feature_names": self._feature_names}
        (_MODEL_DIR / "meta.json").write_text(json.dumps(meta, ensure_ascii=False))
        logger.info(f"截面模型已保存: {_MODEL_DIR}")

    def _load_model(self, model_path: Optional[str] = None):
        """加载模型"""
        meta_path = _MODEL_DIR / "meta.json"
        if not meta_path.exists():
            return

        meta = json.loads(meta_path.read_text())
        self._feature_names = meta.get("feature_names", [])

        if model_path:
            path = Path(model_path)
        else:
            path = _MODEL_DIR / "model"

        suffix_files = list(path.parent.glob(f"{path.name}_model*"))
        if suffix_files:
            from alpha.models.ensemble_model import EnsembleModel
            from alpha.models.lightgbm_model import LGBModel
            from alpha.models.xgb_model import XGBModel
            self._model = EnsembleModel([LGBModel(), XGBModel()])
            self._model.load(str(path))
        else:
            from alpha.models.lightgbm_model import LGBModel
            self._model = LGBModel()
            self._model.load(str(path))

        logger.info(f"截面模型已加载: {path}")
