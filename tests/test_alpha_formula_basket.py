from __future__ import annotations

from datetime import date

import pandas as pd

from alpha.basket import BasketBuilder
from alpha.formula_engine import FormulaEngine


class FakeStorage:
    def __init__(self):
        self._daily = {
            "000001": pd.DataFrame(
                {
                    "code": ["000001"] * 5,
                    "date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"]),
                    "open": [10, 10.2, 10.4, 10.6, 10.8],
                    "high": [10.5, 10.7, 10.9, 11.1, 11.3],
                    "low": [9.8, 10.0, 10.2, 10.4, 10.6],
                    "close": [10, 10.2, 10.4, 10.6, 10.8],
                    "volume": [100000] * 5,
                    "amount": [1000000] * 5,
                }
            )
        }
        self._stocks = pd.DataFrame([
            {"code": "000001", "name": "平安银行", "industry": "银行"},
        ])

    def get_stock_daily(self, code, start_date=None, end_date=None):
        return self._daily.get(code, pd.DataFrame()).copy()

    def get_stock_list(self):
        return self._stocks.copy()

    def get_all_stock_codes(self):
        return ["000001"]


class TestFormulaEngine:
    def test_catalog_exposes_expected_functions(self):
        engine = FormulaEngine(storage=FakeStorage())
        catalog = engine.catalog()
        assert catalog["success"] is True
        assert any(item["name"] == "MA" for item in catalog["functions"])

    def test_evaluate_code_supports_ma_and_cross(self):
        engine = FormulaEngine(storage=FakeStorage())
        result = engine.evaluate_code("000001", "CLOSE > MA(CLOSE, 3)")
        assert result.success is True
        assert result.latest_value is True
        assert len(result.series) == 5

    def test_screen_codes_returns_matches(self):
        engine = FormulaEngine(storage=FakeStorage())
        result = engine.screen_codes("CLOSE > MA(CLOSE, 3)")
        assert result["success"] is True
        assert result["total"] == 1
        assert result["matches"][0]["code"] == "000001"


class TestBasketBuilder:
    def test_build_plan_generates_legs(self):
        builder = BasketBuilder(storage=FakeStorage())
        plan = builder.build_plan([
            {"code": "000001", "probability": 0.8, "name": "平安银行", "industry": "银行"},
        ], initial_cash=100000)
        assert plan.success is True
        assert len(plan.legs) == 1
        assert plan.legs[0].shares > 0
        assert plan.legs[0].code == "000001"

    def test_build_plan_returns_error_for_empty_candidates(self):
        builder = BasketBuilder(storage=FakeStorage())
        plan = builder.build_plan([])
        assert plan.success is False
        assert plan.error == "候选集为空"

    def test_backtest_plan_requires_price_data(self):
        builder = BasketBuilder(storage=FakeStorage())
        result = builder.backtest_plan([
            {"code": "000001", "probability": 0.8, "name": "平安银行", "industry": "银行"},
        ], price_data=None)
        assert result["success"] is False
        assert result["error"] == "缺少价格数据"
