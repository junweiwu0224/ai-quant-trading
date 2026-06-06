from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from agentic.backtest_compiler import BacktestCompileRequest
from agentic.backtest_runner import AgenticBacktestResult, AgenticBacktestRunner
from agentic.sample_selector import BacktestSample, BacktestSampleSelector
from agentic.strategy_candidates import StrategyCandidate, StrategyCandidateGenerator
from agentic.strategy_lab import StrategyIterationResult


@dataclass(frozen=True)
class CandidateBacktestResult:
    candidate: StrategyCandidate
    compiled_request: dict[str, Any]
    backtest_response: dict[str, Any]
    metrics: dict[str, Any]
    promotion: StrategyIterationResult
    gate_checks: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate.to_dict(),
            "backtest_request": self.compiled_request,
            "backtest": self.backtest_response,
            "metrics": dict(self.metrics),
            "promotion": {
                "promoted": self.promotion.promoted,
                "reason": self.promotion.reason,
                "metrics": dict(self.promotion.metrics),
            },
            "gate_checks": list(self.gate_checks),
        }


@dataclass(frozen=True)
class CandidateBacktestBatch:
    sample: BacktestSample
    results: list[CandidateBacktestResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample": self.sample.to_dict(),
            "results": [result.to_dict() for result in self.results],
        }


class StrategyCandidateBacktester:
    def __init__(
        self,
        candidate_generator: StrategyCandidateGenerator | None = None,
        sample_selector: BacktestSampleSelector | None = None,
        runner: AgenticBacktestRunner | None = None,
    ):
        self.candidate_generator = candidate_generator or StrategyCandidateGenerator()
        self.sample_selector = sample_selector or BacktestSampleSelector()
        self.runner = runner or AgenticBacktestRunner()

    async def run(
        self,
        context: dict[str, Any] | None = None,
        limit: int = 4,
        min_days: int = 60,
        max_codes: int = 5,
        initial_cash: float = 1_000_000,
    ) -> CandidateBacktestBatch:
        sample = self.sample_selector.select(min_days=min_days, max_codes=max_codes)
        candidates = self.candidate_generator.generate(context=context, limit=limit)
        results: list[CandidateBacktestResult] = []
        for candidate in candidates:
            result = await self.runner.run_and_evaluate(
                BacktestCompileRequest(
                    dsl=candidate.dsl,
                    codes=sample.codes,
                    start_date=sample.start_date,
                    end_date=sample.end_date,
                    initial_cash=initial_cash,
                )
            )
            results.append(_attach_candidate(candidate, result))
        return CandidateBacktestBatch(sample=sample, results=sorted(results, key=_rank_key, reverse=True))


def _attach_candidate(candidate: StrategyCandidate, result: AgenticBacktestResult) -> CandidateBacktestResult:
    return CandidateBacktestResult(
        candidate=candidate,
        compiled_request=result.compiled_request,
        backtest_response=result.backtest_response,
        metrics=result.metrics,
        promotion=result.promotion,
        gate_checks=_build_gate_checks(candidate, result.metrics, result.promotion),
    )


def _build_gate_checks(
    candidate: StrategyCandidate,
    metrics: dict[str, Any],
    promotion: StrategyIterationResult,
) -> list[dict[str, Any]]:
    trades = int(_float_metric(metrics.get("trades")))
    drawdown = _float_metric(metrics.get("max_drawdown"))
    sharpe = _float_metric(metrics.get("sharpe"))
    return [
        {
            "id": "data_quality",
            "label": "数据质量",
            "passed": trades >= 10,
            "detail": f"有效交易 {trades} 笔，避免只靠单次信号晋级",
        },
        {
            "id": "backtest_quality",
            "label": "回测表现",
            "passed": bool(promotion.promoted),
            "detail": f"Sharpe {sharpe:g}，晋级结果：{promotion.reason}",
        },
        {
            "id": "risk_boundary",
            "label": "风控边界",
            "passed": drawdown <= 0.15,
            "detail": f"最大回撤 {drawdown:g}，模拟盘前仍需组合风控确认",
        },
        {
            "id": "signal_baseline_only",
            "label": "AI信号仅基线",
            "passed": True,
            "detail": "Signal Engine 分数只提供基线因子，不单独决定是否进入模拟盘",
        },
    ]


def _rank_key(result: CandidateBacktestResult) -> tuple[int, float, float, int]:
    metrics = result.metrics or {}
    promoted = 1 if result.promotion.promoted else 0
    sharpe = _float_metric(metrics.get("sharpe"))
    drawdown = _float_metric(metrics.get("max_drawdown"))
    trades = int(_float_metric(metrics.get("trades")))
    return promoted, sharpe, -drawdown, trades


def _float_metric(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
