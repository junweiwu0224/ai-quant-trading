"""One promotion gate for paper and live eligibility decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class PromotionContext:
    evidence_count: int = 0
    provenance_complete: bool = False
    backtest_passed: bool = False
    risk_approved: bool = False
    paper_observations: int = 0
    paper_return: Optional[float] = None
    max_drawdown: Optional[float] = None
    manual_approval: bool = False
    signal_validation_passed: bool = False
    min_trades: int = 0
    sharpe: Optional[float] = None


@dataclass(frozen=True)
class PromotionDecision:
    target: str
    approved: bool
    policy_version: str
    failed_gates: Tuple[str, ...] = ()
    reasons: Tuple[str, ...] = ()


class PromotionPolicy:
    """Deep policy module: submit facts, receive an auditable decision."""

    version = "promotion-v1"

    def __init__(
        self,
        *,
        min_evidence: int = 1,
        min_trades: int = 10,
        min_sharpe: float = 0.7,
        min_paper_observations: int = 20,
        min_paper_return: float = 0.0,
        max_drawdown: float = 0.15,
        require_manual_approval: bool = True,
    ) -> None:
        if min_evidence < 1:
            raise ValueError("min_evidence must be positive")
        if min_trades < 1:
            raise ValueError("min_trades must be positive")
        if min_paper_observations < 1:
            raise ValueError("min_paper_observations must be positive")
        if max_drawdown < 0:
            raise ValueError("max_drawdown cannot be negative")
        self.min_evidence = min_evidence
        self.min_trades = min_trades
        self.min_sharpe = min_sharpe
        self.min_paper_observations = min_paper_observations
        self.min_paper_return = min_paper_return
        self.max_drawdown = max_drawdown
        self.require_manual_approval = require_manual_approval

    def evaluate(self, context: PromotionContext, *, target: str) -> PromotionDecision:
        if target not in {"strategy_candidate", "paper_pending", "live_eligible"}:
            raise ValueError("unsupported promotion target: %s" % target)
        failures: List[str] = []
        reasons: List[str] = []

        if target in {"paper_pending", "live_eligible"}:
            if context.evidence_count < self.min_evidence:
                failures.append("evidence")
                reasons.append("at least %d evidence item(s) are required" % self.min_evidence)
            if not context.provenance_complete:
                failures.append("provenance")
                reasons.append("evidence provenance is incomplete")
            if not context.signal_validation_passed:
                failures.append("signal_validation")
                reasons.append("signal validation gate has not passed")
        if context.min_trades > 0 and context.min_trades < self.min_trades:
            failures.append("data_quality")
            reasons.append("backtest trade sample is below the minimum")
        if context.sharpe is not None and context.sharpe < self.min_sharpe:
            failures.append("sharpe")
            reasons.append("sharpe is below the minimum")
        if not context.backtest_passed:
            failures.append("backtest")
            reasons.append("backtest gate has not passed")
        if not context.risk_approved:
            failures.append("risk")
            reasons.append("risk gate has not passed")

        if target == "live_eligible":
            if context.paper_observations < self.min_paper_observations:
                failures.append("paper_observations")
                reasons.append("paper observations are below the configured minimum")
            if context.paper_return is None or context.paper_return < self.min_paper_return:
                failures.append("paper_return")
                reasons.append("paper return is below the configured minimum")
            if context.max_drawdown is None or context.max_drawdown > self.max_drawdown:
                failures.append("max_drawdown")
                reasons.append("paper drawdown exceeds the configured maximum or is missing")
            if self.require_manual_approval and not context.manual_approval:
                failures.append("manual_approval")
                reasons.append("manual approval is required before live eligibility")

        return PromotionDecision(
            target=target,
            approved=not failures,
            policy_version=self.version,
            failed_gates=tuple(failures),
            reasons=tuple(reasons),
        )
