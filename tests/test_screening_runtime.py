from alpha.screening_runtime import ScreeningRuntime


class FakeScreener:
    def __init__(self):
        self.calls = 0

    def screen(self, **kwargs):
        self.calls += 1
        if self.calls > 1:
            raise RuntimeError("source down")
        return {"total": 2, "stocks": [{"code": "600002", "change_pct": 1}, {"code": "600001", "change_pct": 1}]}


def test_screening_runtime_stable_sorts_and_reuses_last_good_cache():
    clock = iter([100.0, 100.0, 101.0])
    runtime = ScreeningRuntime(FakeScreener(), cache_ttl=10, now=lambda: next(clock))

    first = runtime.run(strategy_name="default")
    stale = runtime.run(strategy_name="default")

    assert [item["code"] for item in first.candidates] == ["600001", "600002"]
    assert stale.status == "stale_cache"
    assert stale.degraded is True
    assert stale.source_health["stale"] is True


def test_screening_runtime_keeps_screening_namespace_separate():
    runtime = ScreeningRuntime(FakeScreener())
    try:
        runtime.run(strategy_name="single_stock", namespace="analysis")
    except ValueError as exc:
        assert "single-stock analysis" in str(exc)
    else:
        raise AssertionError("analysis namespace must not use screening runtime")


class StrategyScreener:
    def screen(self, **kwargs):
        return {
            "total": 3,
            "stocks": [
                {"code": "600003", "pe_ratio": 18, "amplitude": 8, "change_pct": 4, "turnover_rate": 2},
                {"code": "600002", "pe_ratio": 8, "amplitude": 2, "change_pct": 2, "turnover_rate": 4},
                {"code": "600001", "pe_ratio": 25, "amplitude": 1, "change_pct": 5, "turnover_rate": 5},
            ],
        }


def test_screening_runtime_resolves_builtin_strategy_in_screening_namespace():
    runtime = ScreeningRuntime(StrategyScreener())
    run = runtime.run(strategy_name="低估蓝筹")

    assert run.strategy_source == "builtin"
    assert run.strategy_namespace == "screening"
    assert run.strategy_config["hard_filters"]


def test_screening_runtime_applies_strategy_hard_filters_scores_and_actions():
    runtime = ScreeningRuntime(StrategyScreener(), now=lambda: 200.0)
    run = runtime.run(
        strategy_name="risk-aware",
        strategy={
            "namespace": "screening",
            "hard_filters": [{"field": "pe_ratio", "op": "lte", "value": 20}],
            "factors": [{"field": "change_pct", "weight": 1, "direction": "higher"}],
            "risk_adjustment": {"fields": {"amplitude": 1}},
        },
    )

    assert [item["code"] for item in run.candidates] == ["600002", "600003"]
    assert run.candidates[0]["factor_score"] == 0.0
    assert run.candidates[0]["risk_penalty"] == 0.0
    assert run.candidates[1]["risk_penalty"] == 100.0
    assert run.candidates[0]["risk_adjusted_score"] == run.candidates[1]["risk_adjusted_score"]
    assert run.candidates[0]["source_context"]["run_id"] == run.run_id
    assert {action["id"] for action in run.candidates[0]["next_actions"]} >= {
        "research", "draft_backtest", "paper_candidate"
    }


def test_screening_runtime_loads_yaml_namespace_and_degrades_optional_llm():
    runtime = ScreeningRuntime(StrategyScreener(), now=lambda: 201.0)
    run = runtime.run(
        strategy_name="yaml-strategy",
        strategy_yaml="""
namespace: screening
name: yaml-strategy
hard_filters:
  - field: change_pct
    op: gte
    value: 4
factors:
  - field: change_pct
    weight: 1
    direction: higher
llm_rerank: true
""",
    )

    assert run.strategy_source == "yaml"
    assert [item["code"] for item in run.candidates] == ["600001", "600003"]
    assert run.degraded is True
    assert run.source_health["llm_rerank"] == "unavailable"


def test_screening_runtime_keeps_deterministic_order_when_llm_rerank_fails():
    def broken_reranker(items, config):
        raise RuntimeError("llm unavailable")

    runtime = ScreeningRuntime(StrategyScreener(), llm_reranker=broken_reranker, now=lambda: 202.0)
    run = runtime.run(
        strategy_name="rerank",
        strategy={
            "hard_filters": [{"field": "change_pct", "op": "gte", "value": 2}],
            "factors": [{"field": "change_pct", "weight": 1}],
            "llm_rerank": True,
        },
    )

    assert [item["code"] for item in run.candidates] == ["600001", "600003", "600002"]
    assert run.degraded is True
    assert "llm unavailable" in run.source_health["llm_error"]


class MissingNumericScreener:
    def screen(self, **kwargs):
        return {
            "total": 4,
            "stocks": [
                {"code": "600004", "pe_ratio": None, "change_pct": 10},
                {"code": "600003", "pe_ratio": "nan", "change_pct": 9},
                {"code": "600002", "pe_ratio": 8, "change_pct": None},
                {"code": "600001", "pe_ratio": 12, "change_pct": 7},
            ],
        }


def test_screening_runtime_does_not_fill_missing_numeric_hard_filter_values():
    runtime = ScreeningRuntime(MissingNumericScreener())

    run = runtime.run(
        strategy_name="missing-safe",
        strategy={
            "hard_filters": [{"field": "pe_ratio", "op": "gt", "value": 0}],
            "factors": [{"field": "change_pct", "weight": 1}],
        },
    )

    assert [item["code"] for item in run.candidates] == ["600001"]


def test_screening_runtime_places_missing_default_sort_values_last():
    runtime = ScreeningRuntime(MissingNumericScreener())

    run = runtime.run(strategy_name="stable-order")

    assert [item["code"] for item in run.candidates] == ["600004", "600003", "600001", "600002"]


def test_screening_runtime_exposes_factor_quality_exclusions_instead_of_scoring_missing_as_zero():
    runtime = ScreeningRuntime(MissingNumericScreener())

    run = runtime.run(
        strategy_name="factor-quality",
        strategy={
            "hard_filters": [{"field": "pe_ratio", "op": "gt", "value": 0}],
            "factors": [{"field": "change_pct", "weight": 1}],
        },
    )

    excluded = run.source_health["excluded_candidates"]["missing_numeric_fields"]
    assert excluded == [{"code": "600002", "fields": ["change_pct"], "reason": "missing_numeric_factor"}]
    assert run.source_health["data_quality"] == "partial"
    assert run.source_health["status"] == "degraded"
    assert run.degraded is True
    assert all("factor_score" in item for item in run.candidates)
