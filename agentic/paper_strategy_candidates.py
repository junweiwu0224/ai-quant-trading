from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from agentic.models import AgenticPaperOrderDraft, PaperStrategyCandidate, PaperStrategyExecution
from agentic.operations import OperationConflict, OperationRecord, normalize_operation_id, operation_request_hash
from agentic.promotion import PromotionDecision
from agentic.portfolio_risk import PortfolioRiskGate, PortfolioRiskLimits
from agentic.repository import AgenticRepository
from engine.models import Direction, OrderType, PaperOrder
from engine.order_manager import OrderManager


class PaperOrderRecoveryRequired(RuntimeError):
    """Paper orders are durable, but the Agentic execution projection needs retry."""

    def __init__(self, operation_id: str, orders: list[PaperOrder], cause: Exception):
        self.operation_id = operation_id
        self.orders = list(orders)
        self.cause = cause
        super().__init__(
            "paper orders were written but Agentic status synchronization failed; "
            "operation %s is recoverable by retrying the same operation_id" % operation_id
        )


class PaperStrategyCandidateService:
    def __init__(self, repository: AgenticRepository, order_manager: OrderManager | None = None):
        self.repository = repository
        self.order_manager = order_manager or OrderManager()

    def enqueue(
        self,
        result: dict,
        sample: dict,
        *,
        operation_id: str | None = None,
        operation_request: dict | None = None,
    ) -> PaperStrategyCandidate:
        promotion = dict(result.get("promotion") or {})
        if promotion.get("promoted") is not True:
            raise ValueError("only promoted candidates can be queued for paper trading")
        decision_payload = promotion.get("decision")
        if isinstance(decision_payload, dict):
            decision = PromotionDecision(
                target=str(decision_payload.get("target") or ""),
                approved=bool(decision_payload.get("approved")),
                policy_version=str(decision_payload.get("policy_version") or ""),
                failed_gates=tuple(decision_payload.get("failed_gates") or ()),
                reasons=tuple(decision_payload.get("reasons") or ()),
            )
            if decision.target != "strategy_candidate" or not decision.approved:
                raise ValueError("promotion decision is not approved for strategy candidate")
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
        operation_id = normalize_operation_id(
            operation_id or "legacy-paper-candidate-enqueue-%s" % candidate_id
        )
        request = dict(operation_request or {})
        if not request:
            request = {
                "candidate_id": candidate_id,
                "sample": dict(sample or {}),
            }
        existing = self._get_operation(operation_id)
        if existing is not None:
            self._assert_operation(
                existing,
                command="strategy.paper_candidate.enqueue",
                aggregate_type="paper_strategy_candidate",
                aggregate_id=existing.aggregate_id,
                request=request,
            )
            return self.repository.get_paper_strategy_candidate(existing.aggregate_id)
        atomic_create = getattr(self.repository, "create_paper_strategy_candidate_operation", None)
        if callable(atomic_create):
            return atomic_create(
                record,
                operation_id=operation_id,
                operation_request=request,
                command="strategy.paper_candidate.enqueue",
            )
        self.repository.save_paper_strategy_candidate(record)
        self._record_operation(
            operation_id,
            command="strategy.paper_candidate.enqueue",
            aggregate_type="paper_strategy_candidate",
            aggregate_id=record.id,
            request=request,
            result={"candidate_id": record.id, "status": record.status},
        )
        return record

    def confirm(
        self,
        candidate_id: str,
        *,
        operation_id: str | None = None,
        confirmed_by: str = "",
    ) -> PaperStrategyCandidate:
        # Direct callers from the pre-operation API remain readable during
        # migration; the Dashboard/API contract always supplies an explicit
        # operation id.
        operation_id = normalize_operation_id(
            operation_id or "legacy-paper-candidate-confirm-%s" % candidate_id
        )
        candidate = self.repository.get_paper_strategy_candidate(candidate_id)
        request = {
            "candidate_id": candidate_id,
            "confirmed_by": str(confirmed_by or "").strip(),
            "to_status": "paper_active",
        }
        if candidate.status != "paper_candidate":
            existing = self._get_operation(operation_id)
            if existing is not None:
                self._assert_operation(
                    existing,
                    command="strategy.paper_candidate.confirm",
                    aggregate_id=candidate_id,
                    request=request,
                )
                if candidate.status == "paper_active":
                    return candidate
            raise ValueError("only paper_candidate records can be confirmed")
        _ensure_candidate_signal_validation(candidate)
        atomic_transition = getattr(self.repository, "transition_paper_strategy_candidate_atomically", None)
        if callable(atomic_transition):
            return atomic_transition(
                candidate_id,
                expected_status="paper_candidate",
                status="paper_active",
                requires_confirmation=False,
                operation_id=operation_id,
                operation_request=request,
                command="strategy.paper_candidate.confirm",
                result={"candidate_id": candidate_id, "status": "paper_active"},
            )
        updated = self.repository.update_paper_strategy_candidate_status(
            candidate_id, status="paper_active", requires_confirmation=False
        )
        self._record_operation(
            operation_id,
            command="strategy.paper_candidate.confirm",
            aggregate_type="paper_strategy_candidate",
            aggregate_id=candidate_id,
            request=request,
            result={"candidate_id": candidate_id, "status": updated.status},
        )
        return updated

    def run_active(
        self,
        candidate_id: str,
        *,
        operation_id: str | None = None,
    ) -> PaperStrategyExecution:
        candidate = self.repository.get_paper_strategy_candidate(candidate_id)
        operation_id = normalize_operation_id(
            operation_id or "legacy-paper-strategy-run-%s" % candidate_id
        )
        sample_codes = tuple(str(code) for code in candidate.sample.get("codes", []))
        request = {
            "candidate_id": candidate_id,
            "candidate_record_id": candidate.id,
            "codes": list(sample_codes),
            "to_status": "paper_intent_pending",
        }
        existing = self._get_operation(operation_id)
        if existing is not None:
            self._assert_operation(
                existing,
                command="strategy.paper_candidate.run",
                aggregate_type="paper_strategy_execution",
                aggregate_id=existing.aggregate_id,
                request=request,
            )
            return self.repository.get_paper_strategy_execution(existing.aggregate_id)
        if candidate.status != "paper_active":
            raise ValueError("only paper_active strategy candidates can be run")
        _ensure_candidate_signal_validation(candidate)
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
        atomic_create = getattr(self.repository, "create_paper_strategy_execution_operation", None)
        if callable(atomic_create):
            return atomic_create(
                execution,
                operation_id=operation_id,
                operation_request=request,
                command="strategy.paper_candidate.run",
            )
        self.repository.save_paper_strategy_execution(execution)
        self._record_operation(
            operation_id,
            command="strategy.paper_candidate.run",
            aggregate_type="paper_strategy_execution",
            aggregate_id=execution.id,
            request=request,
            result={"execution_id": execution.id, "status": execution.status},
        )
        return execution

    def confirm_execution(
        self,
        execution_id: str,
        portfolio: dict | None = None,
        risk_context: dict | None = None,
        *,
        operation_id: str | None = None,
        confirmed_by: str = "",
    ) -> PaperStrategyExecution:
        operation_id = normalize_operation_id(
            operation_id or "legacy-paper-execution-confirm-%s" % execution_id
        )
        execution = self.repository.get_paper_strategy_execution(execution_id)
        request = {
            "execution_id": execution_id,
            "confirmed_by": str(confirmed_by or "").strip(),
            "portfolio": dict(portfolio or {}),
            "risk_context": dict(risk_context or {}),
        }
        if execution.status != "paper_intent_pending":
            existing = self._get_operation(operation_id)
            if existing is not None:
                self._assert_operation(existing, command="strategy.paper_execution.confirm", aggregate_id=execution_id, request=request, aggregate_type="paper_strategy_execution")
                return execution
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
        final_status = "rejected" if not result.allowed else "paper_intent_confirmed"
        reason = "; ".join(result.reasons) if not result.allowed else "risk gate passed; ready for simulated order adapter"
        atomic_record = getattr(self.repository, "record_paper_strategy_execution_operation", None)
        if callable(atomic_record):
            return atomic_record(
                execution_id,
                operation_id=operation_id,
                operation_request=request,
                command="strategy.paper_execution.confirm",
                status=final_status,
                reason=reason,
                requires_confirmation=False,
            )
        updated = self.repository.update_paper_strategy_execution_status(
            execution_id,
            status=final_status,
            reason=reason,
            requires_confirmation=False,
        )
        self._record_operation(
            operation_id,
            command="strategy.paper_execution.confirm",
            aggregate_type="paper_strategy_execution",
            aggregate_id=execution_id,
            request=request,
            result={"execution_id": execution_id, "status": final_status},
        )
        return updated


    def create_order_drafts(
        self,
        execution_id: str,
        volume_per_code: int = 100,
        *,
        operation_id: str | None = None,
    ) -> list[AgenticPaperOrderDraft]:
        execution = self.repository.get_paper_strategy_execution(execution_id)
        volume_per_code = self._validate_volume(volume_per_code)
        operation_id = normalize_operation_id(
            operation_id or "legacy-paper-order-drafts-%s-%s" % (execution_id, volume_per_code)
        )
        request = {
            "execution_id": execution_id,
            "codes": list(execution.codes),
            "volume_per_code": volume_per_code,
            "to_status": "draft_pending",
        }
        existing = self._get_operation(operation_id)
        if existing is not None:
            self._assert_operation(
                existing,
                command="strategy.paper_execution.order_drafts",
                aggregate_type="paper_strategy_execution",
                aggregate_id=execution_id,
                request=request,
            )
            return self.repository.list_agentic_order_drafts_for_execution(execution_id)
        if execution.status != "paper_intent_confirmed":
            raise ValueError("only paper_intent_confirmed executions can create order drafts")
        self._ensure_execution_candidate_signal_validation(execution)
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
            drafts.append(draft)
        atomic_create = getattr(self.repository, "create_paper_order_drafts_operation", None)
        if callable(atomic_create):
            return atomic_create(
                drafts,
                operation_id=operation_id,
                execution_id=execution_id,
                operation_request=request,
                command="strategy.paper_execution.order_drafts",
            )
        for draft in drafts:
            self.repository.save_agentic_order_draft(draft)
        self._record_operation(
            operation_id,
            command="strategy.paper_execution.order_drafts",
            aggregate_type="paper_strategy_execution",
            aggregate_id=execution_id,
            request=request,
            result={"execution_id": execution_id, "draft_ids": [draft.id for draft in drafts]},
        )
        return drafts

    def submit_confirmed_execution_orders(
        self,
        execution_id: str,
        volume_per_code: int = 100,
        *,
        operation_id: str | None = None,
    ) -> list[PaperOrder]:
        execution = self.repository.get_paper_strategy_execution(execution_id)
        volume_per_code = self._validate_volume(volume_per_code)
        explicit_operation_id = operation_id is not None
        operation_id = normalize_operation_id(
            operation_id or "legacy-paper-order-submit-%s-%s" % (execution_id, volume_per_code)
        )
        if not explicit_operation_id and execution.status != "paper_intent_confirmed":
            raise ValueError("only paper_intent_confirmed executions can submit real paper orders")
        request = {
            "execution_id": execution_id,
            "codes": list(execution.codes),
            "volume_per_code": volume_per_code,
            "to_status": "paper_orders_submitted",
        }
        existing = self._get_operation(operation_id)
        if existing is not None:
            self._assert_operation(
                existing,
                command="strategy.paper_execution.paper_orders",
                aggregate_type="paper_strategy_execution",
                aggregate_id=execution_id,
                request=request,
            )
            return self.order_manager.get_orders_by_operation(operation_id)
        if execution.status != "paper_intent_confirmed":
            raise ValueError("only paper_intent_confirmed executions can submit real paper orders")
        self._ensure_execution_candidate_signal_validation(execution)
        orders: list[PaperOrder] = []
        for code in execution.codes:
            # Build the batch in memory first. The legacy one-order write path
            # would commit before the operation-aware batch seam and duplicate rows.
            orders.append(
                PaperOrder(
                    order_id=f"ORD-{uuid4().hex[:8].upper()}",
                    code=str(code),
                    direction=Direction.LONG,
                    order_type=OrderType.MARKET,
                    volume=volume_per_code,
                    strategy_name=f"agentic:{execution.candidate_id}",
                    signal_reason=f"confirmed agentic paper intent {execution.id}",
                )
            )
        recovered_existing_orders = False
        try:
            self.order_manager.get_orders_by_operation(operation_id)
            recovered_existing_orders = True
        except KeyError:
            pass
        try:
            persisted_orders = self.order_manager.create_orders_idempotently(
                orders,
                operation_id=operation_id,
                operation_request_hash=operation_request_hash(request),
            )
        except ValueError as exc:
            if "different paper-order facts" in str(exc):
                raise OperationConflict(str(exc)) from exc
            raise
        try:
            self.repository.record_paper_strategy_execution_operation(
                execution_id,
                operation_id=operation_id,
                operation_request=request,
                command="strategy.paper_execution.paper_orders",
                status="paper_orders_submitted",
                reason=f"submitted {len(persisted_orders)} paper orders from confirmed agentic intent",
                requires_confirmation=False,
                result={
                    "execution_id": execution_id,
                    "status": "paper_orders_submitted",
                    "order_ids": [order.order_id for order in persisted_orders],
                    "order_count": len(persisted_orders),
                    "recovered": recovered_existing_orders,
                },
            )
        except OperationConflict:
            raise
        except Exception as exc:
            raise PaperOrderRecoveryRequired(operation_id, persisted_orders, exc) from exc
        return persisted_orders

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

    def _get_operation(self, operation_id: str) -> OperationRecord | None:
        getter = getattr(self.repository, "get_operation", None)
        if not callable(getter):
            return None
        try:
            return getter(operation_id)
        except KeyError:
            return None

    def _record_operation(self, operation_id: str, *, command: str, aggregate_type: str, aggregate_id: str, request: dict, result: dict) -> OperationRecord:
        recorder = getattr(self.repository, "record_operation", None)
        if not callable(recorder):
            raise TypeError("paper strategy confirmation requires an operation-capable repository")
        return recorder(
            operation_id,
            command=command,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            request=request,
            status="completed",
            result=result,
        )

    @staticmethod
    def _assert_operation(existing: OperationRecord, *, command: str, aggregate_id: str, request: dict, aggregate_type: str = "paper_strategy_candidate") -> None:
        if existing.command != command or existing.aggregate_type != aggregate_type or existing.aggregate_id != aggregate_id or existing.request_hash != operation_request_hash(request):
            raise OperationConflict("operation_id was already used for different command facts")

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
