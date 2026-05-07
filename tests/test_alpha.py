"""AI Alpha 层测试"""
import numpy as np
import pandas as pd
import pytest

from alpha.factors.technical import TechnicalFactors
from alpha.factors.fundamental import FundamentalFactors
from alpha.feature_pipeline import FeaturePipeline
from alpha.models.lightgbm_model import LGBConfig, LGBModel
from alpha.optimizer import HyperOptimizer
from alpha.evaluator import StrategyEvaluator


@pytest.fixture
def sample_ohlcv():
    """生成模拟 OHLCV 数据"""
    np.random.seed(42)
    n = 100
    dates = pd.date_range("2024-01-02", periods=n, freq="B")
    close = 10.0 + np.cumsum(np.random.randn(n) * 0.2)
    close = np.maximum(close, 1.0)
    return pd.DataFrame({
        "date": dates,
        "open": close * (1 + np.random.randn(n) * 0.005),
        "high": close * (1 + np.abs(np.random.randn(n) * 0.01)),
        "low": close * (1 - np.abs(np.random.randn(n) * 0.01)),
        "close": close,
        "volume": np.random.randint(50000, 200000, n).astype(float),
    })


class TestTechnicalFactors:
    def test_ma(self, sample_ohlcv):
        ma5 = TechnicalFactors.ma(sample_ohlcv["close"], 5)
        assert len(ma5) == len(sample_ohlcv)
        assert ma5.iloc[:4].isna().all()
        assert ma5.iloc[4:].notna().all()

    def test_rsi_range(self, sample_ohlcv):
        rsi = TechnicalFactors.rsi(sample_ohlcv["close"], 14)
        valid = rsi.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()

    def test_macd(self, sample_ohlcv):
        dif, dea, hist = TechnicalFactors.macd(sample_ohlcv["close"])
        assert len(dif) == len(sample_ohlcv)
        assert dif.notna().any()

    def test_atr_positive(self, sample_ohlcv):
        atr = TechnicalFactors.atr(
            sample_ohlcv["high"], sample_ohlcv["low"], sample_ohlcv["close"]
        )
        valid = atr.dropna()
        assert (valid >= 0).all()

    def test_compute_all(self, sample_ohlcv):
        result = TechnicalFactors.compute_all(sample_ohlcv)
        assert len(result) == len(sample_ohlcv)
        assert "rsi_14" in result.columns
        assert "macd_dif" in result.columns
        assert "ma_5_ratio" in result.columns


class TestFundamentalFactors:
    def test_money_flow(self, sample_ohlcv):
        mfi = FundamentalFactors.money_flow(
            sample_ohlcv["high"], sample_ohlcv["low"],
            sample_ohlcv["close"], sample_ohlcv["volume"]
        )
        valid = mfi.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()

    def test_compute_all(self, sample_ohlcv):
        result = FundamentalFactors.compute_all(sample_ohlcv)
        assert "mfi_14" in result.columns
        assert "vpt" in result.columns


class TestFeaturePipeline:
    def test_build_features(self, sample_ohlcv):
        pipeline = FeaturePipeline()
        features = pipeline.build_features(sample_ohlcv)
        assert "label" in features.columns
        assert len(features.columns) > 10
        assert features["label"].isin([0, 1]).all()

    def test_get_feature_names(self, sample_ohlcv):
        pipeline = FeaturePipeline()
        names = pipeline.get_feature_names(sample_ohlcv)
        assert len(names) > 10
        assert "label" not in names


class TestLGBModel:
    def test_train_predict(self, sample_ohlcv):
        pipeline = FeaturePipeline()
        features = pipeline.build_features(sample_ohlcv)

        feature_cols = [c for c in features.columns if c != "label"]
        X = features[feature_cols].dropna()
        y = features.loc[X.index, "label"]

        split = int(len(X) * 0.7)
        X_train, X_val = X.iloc[:split], X.iloc[split:]
        y_train, y_val = y.iloc[:split], y.iloc[split:]

        config = LGBConfig(n_estimators=50, early_stopping_rounds=10)
        model = LGBModel(config=config)
        metrics = model.train(X_train, y_train, X_val, y_val)

        assert "val_auc" in metrics
        assert 0.0 <= metrics["val_auc"] <= 1.0

        preds = model.predict(X_val)
        assert len(preds) == len(X_val)
        assert (preds >= 0).all()
        assert (preds <= 1).all()

    def test_feature_importance(self, sample_ohlcv):
        pipeline = FeaturePipeline()
        features = pipeline.build_features(sample_ohlcv)
        feature_cols = [c for c in features.columns if c != "label"]
        X = features[feature_cols].dropna()
        y = features.loc[X.index, "label"]

        model = LGBModel(config=LGBConfig(n_estimators=20))
        model.train(X, y)

        imp = model.feature_importance()
        assert len(imp) == len(feature_cols)
        assert "importance" in imp.columns


class TestStrategyEvaluator:
    def test_evaluate(self):
        from datetime import date
        curve = [
            {"date": date(2024, 1, 2), "equity": 1000000},
            {"date": date(2024, 1, 3), "equity": 1010000},
            {"date": date(2024, 1, 4), "equity": 1005000},
            {"date": date(2024, 1, 5), "equity": 1020000},
        ]
        result = StrategyEvaluator.evaluate(curve, initial_cash=1000000)
        assert "总收益率" in result
        assert "最大回撤" in result
        assert "夏普比率" in result

    def test_evaluate_empty(self):
        result = StrategyEvaluator.evaluate([])
        assert result == {}


class TestHyperOptimizer:
    def test_optimize_returns_best_params(self, sample_ohlcv):
        pipeline = FeaturePipeline()
        features = pipeline.build_features(sample_ohlcv)

        feature_cols = [c for c in features.columns if c != "label"]
        X = features[feature_cols].dropna()
        y = features.loc[X.index, "label"]

        optimizer = HyperOptimizer(n_trials=3, n_splits=2)
        best_params = optimizer.optimize(X, y)

        assert isinstance(best_params, dict)
        assert "num_leaves" in best_params
        assert "learning_rate" in best_params
        assert 15 <= best_params["num_leaves"] <= 63
        assert 0.01 <= best_params["learning_rate"] <= 0.2
