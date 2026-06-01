import asyncio
from types import SimpleNamespace

from agentic.candidate_backtester import StrategyCandidateBacktester
from agentic.sample_selector import BacktestSample
from agentic.strategy_lab import StrategyIterationResult


def test_candidate_backtester_runs_candidates_on_selected_sample_and_ranks_results():
    async def scenario():
        sample = BacktestSample(codes=["000001", "600519"], start_date="2024-01-01", end_date="2024-06-30", trading_days=120)
        seen = []

        class FakeSampleSelector:
            def select(self, min_days=60, max_codes=5):
                assert min_days == 60
                assert max_codes == 2
                return sample

        class FakeRunner:
            async def run_and_evaluate(self, request):
                seen.append((request.dsl.strategy_type, request.codes, request.start_date, request.end_date))
                promoted = request.dsl.strategy_type == "threshold_signal"
                metrics = {"trades": 18 if promoted else 12, "max_drawdown": 0.07 if promoted else 0.08, "sharpe": 1.4 if promoted else 0.9}
                return SimpleNamespace(
                    compiled_request={"strategy": request.dsl.strategy_type},
                    backtest_response={"total_trades": metrics["trades"]},
                    metrics=metrics,
                    promotion=StrategyIterationResult(request.dsl, metrics, promoted, "passed" if promoted else "below gate"),
                )

        results = await StrategyCandidateBacktester(sample_selector=FakeSampleSelector(), runner=FakeRunner()).run(
            limit=2,
            max_codes=2,
        )

        assert results.sample == sample
        assert [item.candidate.id for item in results.results] == ["qlib_threshold_quality", "qlib_ranked_core"]
        assert results.results[0].promotion.promoted is True
        assert all(row[1] == ["000001", "600519"] for row in seen)
        assert all(row[2] == "2024-01-01" and row[3] == "2024-06-30" for row in seen)

    asyncio.run(scenario())


def test_candidate_backtester_returns_serializable_payload():
    async def scenario():
        sample = BacktestSample(codes=["000001"], start_date="2024-01-01", end_date="2024-03-31", trading_days=60)

        class FakeSampleSelector:
            def select(self, min_days=60, max_codes=5):
                return sample

        class FakeRunner:
            async def run_and_evaluate(self, request):
                metrics = {"trades": 10, "max_drawdown": 0.05, "sharpe": 1.2}
                return SimpleNamespace(
                    compiled_request={"strategy": "qlib_signal"},
                    backtest_response={"total_trades": 10},
                    metrics=metrics,
                    promotion=StrategyIterationResult(request.dsl, metrics, True, "passed promotion gate"),
                )

        batch = await StrategyCandidateBacktester(sample_selector=FakeSampleSelector(), runner=FakeRunner()).run(limit=1)
        payload = batch.to_dict()

        assert payload["sample"]["codes"] == ["000001"]
        assert payload["results"][0]["candidate"]["id"] == "qlib_ranked_core"
        assert payload["results"][0]["promotion"]["promoted"] is True
        assert payload["results"][0]["metrics"]["sharpe"] == 1.2

    asyncio.run(scenario())


def test_candidate_backtester_marks_qlib_as_baseline_and_reports_gate_checks():
    async def scenario():
        sample = BacktestSample(codes=["000001"], start_date="2024-01-01", end_date="2024-03-31", trading_days=60)

        class FakeSampleSelector:
            def select(self, min_days=60, max_codes=5):
                return sample

        class FakeRunner:
            async def run_and_evaluate(self, request):
                metrics = {"trades": 10, "max_drawdown": 0.05, "sharpe": 1.2}
                return SimpleNamespace(
                    compiled_request={"strategy": "qlib_signal"},
                    backtest_response={"total_trades": 10},
                    metrics=metrics,
                    promotion=StrategyIterationResult(request.dsl, metrics, True, "passed promotion gate"),
                )

        batch = await StrategyCandidateBacktester(sample_selector=FakeSampleSelector(), runner=FakeRunner()).run(limit=1)
        result = batch.to_dict()["results"][0]

        assert result["candidate"]["signal_role"] == "baseline_factor"
        assert "不是最终裁判" in result["candidate"]["thesis"]
        assert {item["id"] for item in result["gate_checks"]} >= {
            "data_quality",
            "backtest_quality",
            "risk_boundary",
            "qlib_baseline_only",
        }
        assert all(item["passed"] is True for item in result["gate_checks"])

    asyncio.run(scenario())
