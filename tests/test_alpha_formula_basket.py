from __future__ import annotations

import asyncio
from datetime import date

import pandas as pd

from alpha.basket import BasketBuilder
from alpha.formula_engine import FormulaEngine
from dashboard.routers.alpha import BasketBacktestRequest, basket_backtest


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

    def test_audit_backtest_draft_reports_manual_only_event_samples(self):
        builder = BasketBuilder(storage=FakeStorage())
        price_data = {"000001": FakeStorage().get_stock_daily("000001")}

        audit = builder.audit_backtest_draft(
            [{"code": "000001", "probability": 0.8, "name": "平安银行", "industry": "银行"}],
            price_data,
            {
                "draft_type": "event_group_backtest_draft",
                "requires_confirmation": False,
                "execution_status": "executed",
                "allowed_actions": ["run_live_trade"],
                "conditions": {
                    "event_date": "2024-01-03",
                    "entry_rule": "次一交易日开盘",
                    "exit_rule": "持有期观察",
                    "holding_periods": [1, 3, 999, "bad"],
                },
            },
        )

        assert audit["available"] is True
        assert audit["manual_only"] is True
        assert audit["conditions_applied_to_backtest"] is False
        assert audit["requires_confirmation"] is True
        assert audit["execution_status"] == "not_executed"
        assert audit["allowed_actions"] == ["view", "edit", "run_backtest_after_confirmation"]
        assert "entry_rule" in audit["unsupported_execution_keys"]
        assert audit["sample_status"] == "ready"
        assert audit["holding_periods"] == [1, 3]
        assert audit["coverage_ratio"] == 1
        stats = audit["event_statistics"]
        assert stats["status"] == "ready"
        assert stats["method"] == "next_bar_open_to_holding_close"
        assert stats["unit"] == "percent"
        assert stats["ready_sample_count"] == 1
        assert stats["missing_sample_count"] == 0
        assert stats["by_holding_period"]["1"]["sample_count"] == 1
        assert 0 <= stats["by_holding_period"]["1"]["win_rate"] <= 1
        assert stats["by_holding_period"]["3"]["mean_return_pct"] is not None
        assert stats["cost_model"]["calculation_status"] == "computed"
        assert stats["cost_model"]["estimated_round_trip_cost_pct"] > 0
        assert stats["benchmark"]["calculation_status"] == "not_computed"
        assert stats["benchmark"]["reason"] == "benchmark_not_requested"
        assert stats["by_holding_period"]["1"]["mean_cost_pct"] == stats["cost_model"]["estimated_round_trip_cost_pct"]
        assert stats["by_holding_period"]["1"]["mean_net_return_pct"] < stats["by_holding_period"]["1"]["mean_return_pct"]
        assert stats["by_holding_period"]["1"]["significance_status"] == "insufficient_sample"
        assert stats["best_period"]["period"] in [1, 3]
        assert audit["event_study"] == stats
        assert audit["samples"][0]["entry_date"] == "2024-01-04"
        assert audit["samples"][0]["holding_returns"]["1"] is not None
        assert audit["samples"][0]["holding_net_returns"]["1"] is not None
        assert audit["samples"][0]["holding_excess_returns"]["1"] is None
        assert "不会改变本次篮子回测规则" in audit["note"]

    def test_audit_backtest_draft_calculates_net_excess_return_with_inline_benchmark(self):
        builder = BasketBuilder(storage=FakeStorage())
        storage = FakeStorage()
        price_data = {
            "000001": storage.get_stock_daily("000001"),
            "000300": pd.DataFrame(
                {
                    "code": ["000300"] * 5,
                    "date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"]),
                    "open": [100, 100, 100, 100, 100],
                    "high": [100, 101, 102, 103, 104],
                    "low": [99, 99, 100, 101, 102],
                    "close": [100, 100, 101, 102, 103],
                    "volume": [100000] * 5,
                    "amount": [1000000] * 5,
                }
            ),
        }

        audit = builder.audit_backtest_draft(
            [{"code": "000001", "probability": 0.8}],
            price_data,
            {
                "conditions": {
                    "event_date": "2024-01-03",
                    "benchmark": "沪深300",
                    "cost_model": {"commission": 0.0002, "slippage": 0.0005, "stamp_tax": 0.001},
                    "holding_periods": [1, 3],
                },
            },
        )

        stats = audit["event_statistics"]
        one_day = stats["by_holding_period"]["1"]
        three_day = stats["by_holding_period"]["3"]
        assert stats["benchmark"]["available"] is True
        assert stats["benchmark"]["code"] == "000300"
        assert stats["benchmark"]["data_source"] == "price_data"
        assert stats["cost_model"]["source"] == "draft_conditions"
        assert stats["cost_model"]["estimated_round_trip_cost_pct"] == 0.24
        assert one_day["mean_return_pct"] == 0
        assert one_day["mean_net_return_pct"] == -0.24
        assert one_day["mean_benchmark_return_pct"] == 0
        assert one_day["mean_excess_return_pct"] == -0.24
        assert three_day["mean_benchmark_return_pct"] == 1.9802
        assert three_day["mean_excess_return_pct"] is not None
        assert audit["samples"][0]["holding_benchmark_returns"]["3"] == 1.9802
        assert audit["samples"][0]["holding_excess_returns"]["1"] == -0.24

    def test_audit_backtest_draft_reports_missing_samples_without_faking_result(self):
        builder = BasketBuilder(storage=FakeStorage())

        audit = builder.audit_backtest_draft(
            [{"code": "000001", "probability": 0.8}],
            {"000001": FakeStorage().get_stock_daily("000001")},
            {"conditions": {"event_date": "2025-01-01", "holding_periods": [5]}},
        )

        assert audit["available"] is False
        assert audit["sample_status"] == "no_sample"
        assert audit["sample_count"] == 0
        assert audit["coverage_ratio"] == 0
        assert audit["event_statistics"]["status"] == "no_sample"
        assert audit["event_statistics"]["ready_sample_count"] == 0
        assert audit["event_statistics"]["by_holding_period"]["5"]["sample_count"] == 0
        assert audit["missing_samples"][0]["reason"] == "event_date_out_of_range"
        assert audit["warnings"]

    def test_audit_backtest_draft_requires_event_date_for_event_statistics(self):
        builder = BasketBuilder(storage=FakeStorage())

        audit = builder.audit_backtest_draft(
            [{"code": "000001", "probability": 0.8}],
            {"000001": FakeStorage().get_stock_daily("000001")},
            {"conditions": {"holding_periods": [1, 3]}},
        )

        assert audit["sample_status"] == "no_sample"
        assert audit["event_statistics"]["available"] is False
        assert audit["event_statistics"]["ready_sample_count"] == 0
        assert audit["event_statistics"]["by_holding_period"]["1"]["sample_count"] == 0
        assert "草案缺少 event_date" in " ".join(audit["warnings"])

    def test_audit_backtest_draft_reports_partial_event_statistics(self):
        builder = BasketBuilder(storage=FakeStorage())

        audit = builder.audit_backtest_draft(
            [{"code": "000001", "probability": 0.8}, {"code": "000002", "probability": 0.7}],
            {"000001": FakeStorage().get_stock_daily("000001")},
            {"conditions": {"event_date": "2024-01-03", "holding_periods": [1, 3]}},
        )

        assert audit["sample_status"] == "partial"
        assert audit["candidate_count"] == 2
        assert audit["sample_count"] == 1
        assert audit["event_statistics"]["ready_sample_count"] == 1
        assert audit["event_statistics"]["missing_sample_count"] == 1
        assert audit["event_statistics"]["coverage_ratio"] == 0.5
        assert audit["missing_samples"] == [{"code": "000002", "reason": "missing_price_data"}]

    def test_backtest_plan_returns_clear_error_for_empty_price_frames(self):
        builder = BasketBuilder(storage=FakeStorage())

        result = builder.backtest_plan(
            [{"code": "000001", "probability": 0.8}],
            price_data={"000001": pd.DataFrame()},
        )

        assert result["success"] is False
        assert result["error"] == "无可用价格数据"


def test_basket_backtest_route_attaches_manual_only_draft_audit_with_inline_price_data():
    price_rows = FakeStorage().get_stock_daily("000001").to_dict("records")

    result = asyncio.run(basket_backtest(BasketBacktestRequest(
        candidates=[{"code": "000001", "probability": 0.8, "name": "平安银行"}],
        initial_cash=100000,
        rebalance_days=1,
        price_data={"000001": price_rows},
        backtest_draft={
            "draft_type": "event_group_backtest_draft",
            "requires_confirmation": False,
            "execution_status": "executed",
            "allowed_actions": ["run_live_trade"],
            "conditions": {
                "event_date": "2024-01-03",
                "entry_rule": "次一交易日开盘",
                "exit_rule": "持有期观察",
                "benchmark": "沪深300",
                "holding_periods": [1, 3],
            },
        },
    )))

    assert result["success"] is True
    assert "equity_curve" in result
    audit = result["draft_audit"]
    assert audit["manual_only"] is True
    assert audit["requires_confirmation"] is True
    assert audit["execution_status"] == "not_executed"
    assert audit["allowed_actions"] == ["view", "edit", "run_backtest_after_confirmation"]
    assert audit["conditions_applied_to_backtest"] is False
    assert audit["event_statistics"]["by_holding_period"]["1"]["sample_count"] == 1
    assert audit["event_statistics"]["methodology"].startswith("按草案 event_date")
    assert audit["event_statistics"]["benchmark"]["available"] is False
    assert audit["event_statistics"]["benchmark"]["reason"] == "missing_benchmark_price_data"
    assert audit["event_statistics"]["by_holding_period"]["1"]["mean_net_return_pct"] is not None
    assert audit["event_statistics"]["by_holding_period"]["1"]["mean_excess_return_pct"] is None
    assert "entry_rule" in audit["unsupported_execution_keys"]
    assert "benchmark" in audit["unsupported_execution_keys"]
    assert "run_live_trade" not in str(audit)
    assert "不会改变本次篮子回测规则" in audit["note"]


def test_basket_backtest_route_prefers_top_level_draft_conditions_for_audit():
    price_rows = FakeStorage().get_stock_daily("000001").to_dict("records")

    result = asyncio.run(basket_backtest(BasketBacktestRequest(
        candidates=[{"code": "000001", "probability": 0.8}],
        price_data={"000001": price_rows},
        backtest_draft={"conditions": {"event_date": "2025-01-01", "holding_periods": [99]}},
        draft_conditions={"event_date": "2024-01-03", "holding_periods": [1]},
    )))

    assert result["success"] is True
    assert result["draft_audit"]["event_date"] == "2024-01-03"
    assert result["draft_audit"]["holding_periods"] == [1]
    assert result["draft_audit"]["sample_status"] == "ready"
