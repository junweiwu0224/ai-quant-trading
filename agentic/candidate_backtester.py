from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from agentic.backtest_compiler import BacktestCompileRequest
from agentic.backtest_runner import AgenticBacktestResult, AgenticBacktestRunner
from agentic.sample_selector import BacktestSample, BacktestSampleSelector
from agentic.signal_validation import SignalValidationGate, evaluate_signal_validation
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
        signal_validation = evaluate_signal_validation((context or {}).get("signal_validation"))
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
            results.append(_attach_candidate(candidate, result, signal_validation))
        return CandidateBacktestBatch(sample=sample, results=sorted(results, key=_rank_key, reverse=True))


def _attach_candidate(
    candidate: StrategyCandidate,
    result: AgenticBacktestResult,
    signal_validation: SignalValidationGate,
) -> CandidateBacktestResult:
    promotion = _apply_signal_validation_gate(result.promotion, signal_validation)
    return CandidateBacktestResult(
        candidate=candidate,
        compiled_request=result.compiled_request,
        backtest_response=result.backtest_response,
        metrics=result.metrics,
        promotion=promotion,
        gate_checks=_build_gate_checks(candidate, result.metrics, promotion, signal_validation),
    )


def _build_gate_checks(
    candidate: StrategyCandidate,
    metrics: dict[str, Any],
    promotion: StrategyIterationResult,
    signal_validation: SignalValidationGate,
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
            "detail": f"Sharpe {sharpe:g}，晋级结果：{_promotion_reason_label(promotion.reason)}",
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
        signal_validation.to_gate_check(),
    ]


def _apply_signal_validation_gate(
    promotion: StrategyIterationResult,
    signal_validation: SignalValidationGate,
) -> StrategyIterationResult:
    if signal_validation.passed or not promotion.promoted:
        return promotion
    metrics = dict(promotion.metrics)
    metrics["signal_validation"] = {
        "confidence": signal_validation.confidence,
        "sample_days": signal_validation.sample_days,
        "passed": False,
    }
    return StrategyIterationResult(
        promotion.dsl,
        metrics,
        False,
        signal_validation.reason,
    )


def _promotion_reason_label(reason: str) -> str:
    return {
        "passed promotion gate": "通过晋级门槛",
        "AI signal is not validated": "AI 信号未验证",
        "AI signal validation sample is insufficient": "AI 验证样本不足",
        "insufficient trades": "交易次数不足",
        "sharpe below threshold": "Sharpe 未达标",
        "max drawdown exceeded": "最大回撤超限",
    }.get(reason, reason or "-")


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
