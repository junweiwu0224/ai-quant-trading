from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from agentic.models import AgenticPaperOrderDraft, PaperStrategyCandidate, PaperStrategyExecution
from agentic.portfolio_risk import PortfolioRiskGate, PortfolioRiskLimits
from agentic.repository import AgenticRepository
from engine.models import Direction, OrderType, PaperOrder
from engine.order_manager import OrderManager


class PaperStrategyCandidateService:
    def __init__(self, repository: AgenticRepository, order_manager: OrderManager | None = None):
        self.repository = repository
        self.order_manager = order_manager or OrderManager()

    def enqueue(self, result: dict, sample: dict) -> PaperStrategyCandidate:
        promotion = dict(result.get("promotion") or {})
        if promotion.get("promoted") is not True:
            raise ValueError("only promoted candidates can be queued for paper trading")
        gate_checks = result.get("gate_checks")
        _ensure_gate_checks_passed(gate_checks)
        metrics = dict(result.get("metrics") or {})
        metrics["signal_validation"] = _signal_validation_proof_from_gate_checks(gate_checks)
        candidate = dict(result.get("candidate") or {})
        candidate_id = str(candidate.get("id") or "").strip()
        if not candidate_id:
            raise ValueError("candidate.id is required")
        record = PaperStrategyCandidate(
            id=f"paper_strategy_{uuid4().hex}",
            candidate_id=candidate_id,
            name=str(candidate.get("name") or candidate_id),
            dsl=dict(candidate.get("dsl") or {}),
            sample=dict(sample or {}),
            metrics=metrics,
            promotion=promotion,
            status="paper_candidate",
            requires_confirmation=True,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.repository.save_paper_strategy_candidate(record)
        return record

    def confirm(self, candidate_id: str) -> PaperStrategyCandidate:
        candidate = self.repository.get_paper_strategy_candidate(candidate_id)
        if candidate.status != "paper_candidate":
            raise ValueError("only paper_candidate records can be confirmed")
        _ensure_candidate_signal_validation(candidate)
        return self.repository.update_paper_strategy_candidate_status(
            candidate_id,
            status="paper_active",
            requires_confirmation=False,
        )

    def run_active(self, candidate_id: str) -> PaperStrategyExecution:
        candidate = self.repository.get_paper_strategy_candidate(candidate_id)
        if candidate.status != "paper_active":
            raise ValueError("only paper_active strategy candidates can be run")
        _ensure_candidate_signal_validation(candidate)
        sample_codes = tuple(str(code) for code in candidate.sample.get("codes", []))
        execution = PaperStrategyExecution(
            id=f"paper_execution_{uuid4().hex}",
            candidate_record_id=candidate.id,
            candidate_id=candidate.candidate_id,
            name=candidate.name,
            dsl=candidate.dsl,
            codes=sample_codes,
            status="paper_intent_pending",
            reason="manual trigger generated a pending paper strategy intent",
            requires_confirmation=True,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.repository.save_paper_strategy_execution(execution)
        return execution

    def confirm_execution(
        self, execution_id: str, portfolio: dict | None = None, risk_context: dict | None = None
    ) -> PaperStrategyExecution:
        execution = self.repository.get_paper_strategy_execution(execution_id)
        if execution.status != "paper_intent_pending":
            raise ValueError("only paper_intent_pending executions can be confirmed")
        self._ensure_execution_candidate_signal_validation(execution)
        risk_context = dict(risk_context or {})
        limits = PortfolioRiskLimits(
            max_strategy_cash_pct=float(risk_context.get("max_strategy_cash_pct", 0.2)),
            max_position_pct=float(risk_context.get("max_position_pct", 0.1)),
            max_holdings=int(risk_context.get("max_holdings", 10)),
            blacklist=set(risk_context.get("blacklist", [])),
            max_industry_pct=float(risk_context.get("max_industry_pct", 0.35)),
        )
        result = PortfolioRiskGate(limits).evaluate(
            intent={"cash_pct": risk_context.get("cash_pct", 0.1), "codes": list(execution.codes)},
            portfolio=portfolio or {},
            industry_map=risk_context.get("industry_map", {}),
        )
        if not result.allowed:
            return self.repository.update_paper_strategy_execution_status(
                execution_id,
                status="rejected",
                reason="; ".join(result.reasons),
                requires_confirmation=False,
            )
        return self.repository.update_paper_strategy_execution_status(
            execution_id,
            status="paper_intent_confirmed",
            reason="risk gate passed; ready for simulated order adapter",
            requires_confirmation=False,
        )


    def create_order_drafts(self, execution_id: str, volume_per_code: int = 100) -> list[AgenticPaperOrderDraft]:
        execution = self.repository.get_paper_strategy_execution(execution_id)
        if execution.status != "paper_intent_confirmed":
            raise ValueError("only paper_intent_confirmed executions can create order drafts")
        self._ensure_execution_candidate_signal_validation(execution)
        volume_per_code = self._validate_volume(volume_per_code)
        drafts: list[AgenticPaperOrderDraft] = []
        for code in execution.codes:
            draft = AgenticPaperOrderDraft(
                id=f"agentic_order_draft_{uuid4().hex}",
                execution_id=execution.id,
                code=str(code),
                direction="buy",
                order_type="market",
                volume=volume_per_code,
                status="draft_pending",
                strategy_name=f"agentic:{execution.candidate_id}",
                signal_reason=f"confirmed agentic paper intent {execution.id}",
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            self.repository.save_agentic_order_draft(draft)
            drafts.append(draft)
        return drafts

    def submit_confirmed_execution_orders(self, execution_id: str, volume_per_code: int = 100) -> list[PaperOrder]:
        execution = self.repository.get_paper_strategy_execution(execution_id)
        if execution.status != "paper_intent_confirmed":
            raise ValueError("only paper_intent_confirmed executions can submit real paper orders")
        self._ensure_execution_candidate_signal_validation(execution)
        volume_per_code = self._validate_volume(volume_per_code)
        orders: list[PaperOrder] = []
        for code in execution.codes:
            orders.append(
                self.order_manager.create_order(
                    code=str(code),
                    direction=Direction.LONG,
                    order_type=OrderType.MARKET,
                    volume=volume_per_code,
                    strategy_name=f"agentic:{execution.candidate_id}",
                    signal_reason=f"confirmed agentic paper intent {execution.id}",
                )
            )
        self.repository.update_paper_strategy_execution_status(
            execution_id,
            status="paper_orders_submitted",
            reason=f"submitted {len(orders)} paper orders from confirmed agentic intent",
            requires_confirmation=False,
        )
        return orders

    @staticmethod
    def _validate_volume(volume_per_code: int) -> int:
        volume = int(volume_per_code)
        if volume <= 0 or volume % 100 != 0:
            raise ValueError("volume_per_code must be a positive board lot")
        return volume

    def list_executions(self, limit: int = 100) -> list[PaperStrategyExecution]:
        return self.repository.list_paper_strategy_executions(limit=limit)

    def list(self, limit: int = 100) -> list[PaperStrategyCandidate]:
        return self.repository.list_paper_strategy_candidates(limit=limit)

    def _ensure_execution_candidate_signal_validation(self, execution: PaperStrategyExecution) -> None:
        candidate = self.repository.get_paper_strategy_candidate(execution.candidate_record_id)
        _ensure_candidate_signal_validation(candidate)


def _ensure_gate_checks_passed(gate_checks: object) -> None:
    if not isinstance(gate_checks, list):
        raise ValueError("signal validation gate failed: missing gate checks")
    has_signal_validation = False
    for item in gate_checks:
        if not isinstance(item, dict):
            continue
        if item.get("passed") is False:
            label = item.get("label") or item.get("id") or "gate"
            if item.get("id") == "signal_validation":
                raise ValueError(f"signal validation gate failed: {label}")
            raise ValueError(f"gate failed: {label}")
        if item.get("id") == "signal_validation":
            has_signal_validation = item.get("passed") is True
    if has_signal_validation:
        return
    raise ValueError("signal validation gate failed: missing signal validation")


def _signal_validation_proof_from_gate_checks(gate_checks: object) -> dict:
    if not isinstance(gate_checks, list):
        raise ValueError("signal validation gate failed: missing gate checks")
    for item in gate_checks:
        if not isinstance(item, dict) or item.get("id") != "signal_validation":
            continue
        if item.get("passed") is not True:
            raise ValueError("signal validation gate failed: signal validation did not pass")
        proof = {key: item[key] for key in ("label", "detail", "confidence", "sample_days") if key in item}
        proof["passed"] = True
        return proof
    raise ValueError("signal validation gate failed: missing signal validation")


def _ensure_candidate_signal_validation(candidate: PaperStrategyCandidate) -> None:
    proof = _candidate_signal_validation_proof(candidate)
    if not proof:
        raise ValueError("signal validation gate failed: missing persisted signal validation")
    if proof.get("passed") is not True:
        detail = str(proof.get("detail") or proof.get("reason") or "persisted signal validation did not pass")
        raise ValueError(f"signal validation gate failed: {detail}")


def _candidate_signal_validation_proof(candidate: PaperStrategyCandidate) -> dict | None:
    metrics = candidate.metrics if isinstance(candidate.metrics, dict) else {}
    proof = metrics.get("signal_validation")
    if isinstance(proof, dict):
        return proof

    promotion = candidate.promotion if isinstance(candidate.promotion, dict) else {}
    promotion_metrics = promotion.get("metrics")
    if isinstance(promotion_metrics, dict):
        proof = promotion_metrics.get("signal_validation")
        if isinstance(proof, dict):
            return proof
    proof = promotion.get("signal_validation")
    if isinstance(proof, dict):
        return proof
    return None
