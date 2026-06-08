import asyncio

from agentic.backtest_compiler import BacktestCompileRequest
from agentic.backtest_runner import AgenticBacktestRunner
from agentic.strategy_dsl import StrategyDSL


def test_runner_compiles_runs_and_evaluates_promotion():
    calls = []

    async def fake_run_backtest(request):
        calls.append(request)
        return {
            "total_trades": 18,
            "max_drawdown": 0.08,
            "sharpe_ratio": 1.1,
            "annual_return": 0.22,
            "total_return": 0.18,
        }

    dsl = StrategyDSL("ranked_rotation", "qlib_top", "qlib_score", [{"close_above_ma": 20}], "daily", 5, 0.05, 0.12, 10)
    runner = AgenticBacktestRunner(run_backtest=fake_run_backtest)

    result = asyncio.run(
        runner.run_and_evaluate(
            BacktestCompileRequest(dsl, ["605066.SH", "000001"], "2024-01-01", "2024-12-31", 50000)
        )
    )

    assert calls[0].strategy == "signal_strategy"
    assert calls[0].codes == ["605066", "000001"]
    assert result.compiled_request["params"]["mode"] == "ranking"
    assert result.metrics["trades"] == 18
    assert result.promotion.promoted is True
    assert result.promotion.reason == "passed promotion gate"


def test_runner_rejects_failed_backtest_response():
    async def fake_run_backtest(request):
        return {"error": "no data"}

    dsl = StrategyDSL("ranked_rotation", "qlib_top", "qlib_score", [], "daily", 5, 0.05, None, 10)
    runner = AgenticBacktestRunner(run_backtest=fake_run_backtest)

    result = asyncio.run(
        runner.run_and_evaluate(
            BacktestCompileRequest(dsl, ["605066"], "2024-01-01", "2024-12-31", 50000)
        )
    )

    assert result.promotion.promoted is False
    assert result.promotion.reason == "backtest error: no data"
