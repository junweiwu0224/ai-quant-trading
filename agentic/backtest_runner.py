from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from agentic.backtest_compiler import BacktestCompileRequest, BacktestCompiler, extract_promotion_metrics
from agentic.strategy_lab import StrategyIterationResult, StrategyLab

RunBacktestCallable = Callable[[Any], dict[str, Any] | Any | Awaitable[dict[str, Any] | Any]]


@dataclass(frozen=True)
class AgenticBacktestResult:
    compiled_request: dict[str, Any]
    backtest_response: dict[str, Any]
    metrics: dict[str, Any]
    promotion: StrategyIterationResult


class AgenticBacktestRunner:
    def __init__(
        self,
        compiler: BacktestCompiler | None = None,
        strategy_lab: StrategyLab | None = None,
        run_backtest: RunBacktestCallable | None = None,
    ):
        self.compiler = compiler or BacktestCompiler()
        self.strategy_lab = strategy_lab or StrategyLab()
        self._run_backtest = run_backtest

    async def run_and_evaluate(self, request: BacktestCompileRequest) -> AgenticBacktestResult:
        compiled = self.compiler.compile(request)
        response = await self._execute(compiled)
        if response.get("error"):
            promotion = StrategyIterationResult(request.dsl, {}, False, f"backtest error: {response['error']}")
            return AgenticBacktestResult(compiled, response, {}, promotion)
        metrics = extract_promotion_metrics(response)
        promotion = self.strategy_lab.evaluate_iteration(request.dsl, metrics)
        return AgenticBacktestResult(compiled, response, metrics, promotion)

    async def _execute(self, compiled_request: dict[str, Any]) -> dict[str, Any]:
        runner = self._run_backtest or _default_run_backtest
        backtest_request = _build_backtest_request(compiled_request)
        result = runner(backtest_request)
        if inspect.isawaitable(result):
            result = await result
        return _to_plain_dict(result)


def _build_backtest_request(compiled_request: dict[str, Any]):
    from dashboard.routers.backtest import BacktestRequest

    public_metadata = {"agentic", "legacy_strategy", "strategy_display_name"}
    payload = {key: value for key, value in compiled_request.items() if key not in public_metadata}
    return BacktestRequest(**payload)


async def _default_run_backtest(backtest_request):
    from dashboard.routers.backtest import run_backtest

    return await run_backtest(backtest_request)


def _to_plain_dict(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    if hasattr(result, "model_dump"):
        return result.model_dump()
    if hasattr(result, "dict"):
        return result.dict()
    raise TypeError(f"unsupported backtest result type: {type(result)!r}")
