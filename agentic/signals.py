from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import uuid
from typing import TYPE_CHECKING, Protocol

from agentic.models import TradingSignal
from agentic.operations import OperationConflict, normalize_operation_id
from agentic.promotion import PromotionContext, PromotionDecision, PromotionPolicy
from agentic.signal_ledger import SignalLedger

if TYPE_CHECKING:
    from agentic.repository import AgenticRepository


class SignalRepository(Protocol):
    """Repository seam needed by SignalService; concrete storage is replaceable."""

    db_path: object

    def save_signal(self, signal: TradingSignal) -> None: ...

    def get_signal(self, signal_id: str) -> TradingSignal: ...

    def list_signals(self, limit: int = 100) -> list[TradingSignal]: ...


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SignalService:
    def __init__(
        self,
        repo: SignalRepository,
        ledger: SignalLedger | None = None,
        promotion_policy: PromotionPolicy | None = None,
    ):
        self.repo = repo
        self.db_path = Path(repo.db_path)  # type: ignore[arg-type]
        self.workspace_id = str(getattr(repo, "workspace_id", "default") or "default")
        if ledger is not None:
            ledger_path = getattr(ledger, "db_path", None)
            if ledger_path is not None and Path(ledger_path).resolve() != self.db_path.resolve():
                raise ValueError("SignalLedger database does not match AgenticRepository database")
            self.ledger = ledger
        else:
            # The ledger must follow the repository selected for this
            # workspace; otherwise signal history/outcomes would remain a
            # shared cross-workspace read/write surface.
            self.ledger = SignalLedger(self.db_path)
        self.promotion_policy = promotion_policy or PromotionPolicy()

    def build(
        self,
        *,
        agent_id: str,
        source: str,
        code: str,
        direction: str,
        confidence: float,
        time_horizon: str,
        entry_reasons: list[str],
        risk_notes: list[str],
        suggested_position: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        expires_at: str | None = None,
        metadata: dict | None = None,
        action: str | None = None,
        score: float | None = None,
        entry_low: float | None = None,
        entry_high: float | None = None,
        target_price: float | None = None,
        invalidation: str = "",
        watch_conditions: list[str] | None = None,
        reason: str = "",
        risk_summary: str = "",
        catalyst_summary: str = "",
        factor_contributions: dict | None = None,
        evidence_snapshot_id: str | None = None,
        research_job_id: str | None = None,
        data_quality: str = "unknown",
        missing_fields: list[str] | None = None,
        source_health: dict | None = None,
        model_metadata: dict | None = None,
    ) -> TradingSignal:
        """Build a validated signal without persisting it.

        Research orchestration uses this seam to persist a signal and its
        research job in one repository transaction. Existing callers should
        continue using :meth:`publish`.
        """

        return TradingSignal(
            f"sig_{uuid.uuid4().hex[:12]}",
            agent_id,
            source,
            code,
            direction,
            confidence,
            time_horizon,
            entry_reasons,
            risk_notes,
            suggested_position,
            stop_loss,
            take_profit,
            "new",
            iso_now(),
            expires_at,
            metadata or {},
            action=action,
            score=score,
            entry_low=entry_low,
            entry_high=entry_high,
            target_price=target_price,
            invalidation=invalidation,
            watch_conditions=watch_conditions or [],
            reason=reason,
            risk_summary=risk_summary,
            catalyst_summary=catalyst_summary,
            factor_contributions=factor_contributions or {},
            evidence_snapshot_id=evidence_snapshot_id,
            research_job_id=research_job_id,
            data_quality=data_quality,
            missing_fields=missing_fields or [],
            source_health=source_health or {},
            model_metadata=model_metadata or {},
        )

    def persist(self, signal: TradingSignal) -> TradingSignal:
        """Persist a previously validated signal through the atomic seam."""

        atomic_publish = getattr(self.repo, "publish_signal_atomically", None)
        if callable(atomic_publish):
            atomic_publish(signal)
        else:
            # Compatibility fallback for legacy repositories/test doubles.
            atomic_publish = None
            self.ledger.append_transition(
                signal.id,
                None,
                signal.status,
                actor="signal-service",
                reason="signal published",
                occurred_at=signal.created_at,
                metadata={"agent_id": signal.agent_id, "source": signal.source},
            )
            self.repo.save_signal(signal)
        return signal

    def publish(
        self,
        *,
        agent_id: str,
        source: str,
        code: str,
        direction: str,
        confidence: float,
        time_horizon: str,
        entry_reasons: list[str],
        risk_notes: list[str],
        suggested_position: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        expires_at: str | None = None,
        metadata: dict | None = None,
        action: str | None = None,
        score: float | None = None,
        entry_low: float | None = None,
        entry_high: float | None = None,
        target_price: float | None = None,
        invalidation: str = "",
        watch_conditions: list[str] | None = None,
        reason: str = "",
        risk_summary: str = "",
        catalyst_summary: str = "",
        factor_contributions: dict | None = None,
        evidence_snapshot_id: str | None = None,
        research_job_id: str | None = None,
        data_quality: str = "unknown",
        missing_fields: list[str] | None = None,
        source_health: dict | None = None,
        model_metadata: dict | None = None,
    ) -> TradingSignal:
        signal = self.build(
            agent_id=agent_id,
            source=source,
            code=code,
            direction=direction,
            confidence=confidence,
            time_horizon=time_horizon,
            entry_reasons=entry_reasons,
            risk_notes=risk_notes,
            suggested_position=suggested_position,
            stop_loss=stop_loss,
            take_profit=take_profit,
            expires_at=expires_at,
            metadata=metadata,
            action=action,
            score=score,
            entry_low=entry_low,
            entry_high=entry_high,
            target_price=target_price,
            invalidation=invalidation,
            watch_conditions=watch_conditions,
            reason=reason,
            risk_summary=risk_summary,
            catalyst_summary=catalyst_summary,
            factor_contributions=factor_contributions,
            evidence_snapshot_id=evidence_snapshot_id,
            research_job_id=research_job_id,
            data_quality=data_quality,
            missing_fields=missing_fields,
            source_health=source_health,
            model_metadata=model_metadata,
        )
        return self.persist(signal)

    def mark_paper_pending(
        self,
        signal_id: str,
        confirmed_by: str,
        *,
        decision: PromotionDecision | None = None,
        approval_operation_id: str | None = None,
        operation_id: str | None = None,
    ) -> TradingSignal:
        """Compatibility adapter for callers migrating to the two-step API."""

        if decision is not None:
            raise ValueError(
                "mark_paper_pending no longer accepts a bare PromotionDecision; "
                "call approve_paper_pending then confirm_paper_pending"
            )
        if approval_operation_id is None:
            raise ValueError("approval_operation_id is required; call approve_paper_pending first")
        return self.confirm_paper_pending(
            signal_id,
            confirmed_by=confirmed_by,
            approval_operation_id=approval_operation_id,
            operation_id=_require_operation_id(operation_id),
        )

    def approve_paper_pending(
        self,
        signal_id: str,
        context: PromotionContext,
        *,
        operation_id: str,
    ) -> PromotionDecision:
        """Evaluate and persist the paper gate without changing signal state."""

        operation_id = _require_operation_id(operation_id)
        request = {
            "signal_id": signal_id,
            "target": "paper_pending",
            "context": context.to_dict(),
            "policy_version": self.promotion_policy.version,
        }
        existing = self._get_persisted_operation(operation_id)
        if existing is not None:
            self._assert_persisted_operation(
                existing,
                signal_id=signal_id,
                command="signal.paper_gate",
                request=request,
            )
            return _decision_from_operation(existing)

        self.repo.get_signal(signal_id)
        decision = self.promotion_policy.evaluate(context, target="paper_pending")
        self._record_operation(
            operation_id,
            command="signal.paper_gate",
            aggregate_id=signal_id,
            request=request,
            result={"signal_id": signal_id, "decision": decision.to_dict()},
        )
        return decision

    def confirm_paper_pending(
        self,
        signal_id: str,
        *,
        confirmed_by: str,
        approval_operation_id: str,
        operation_id: str,
    ) -> TradingSignal:
        """Apply a persisted policy approval after a separate human command."""

        operation_id = _require_operation_id(operation_id)
        approval_operation_id = _require_operation_id(approval_operation_id)
        current = self.repo.get_signal(signal_id)
        approval = self._get_persisted_operation(approval_operation_id)
        if approval is None:
            raise KeyError("operation not found: %s" % approval_operation_id)
        if approval.command != "signal.paper_gate" or approval.aggregate_type != "signal" or approval.aggregate_id != signal_id:
            raise OperationConflict("approval operation does not belong to this signal")
        decision = _decision_from_operation(approval)
        if not decision.approved or decision.target != "paper_pending":
            raise ValueError("paper promotion policy approval is not approved")
        if not str(confirmed_by).strip():
            raise ValueError("confirmed_by is required")

        request = {
            "signal_id": signal_id,
            "to_status": "paper_pending",
            "confirmed_by": confirmed_by,
            "approval_operation_id": approval_operation_id,
            "decision": decision.to_dict(),
        }
        existing = self._get_persisted_operation(operation_id)
        if existing is not None:
            self._assert_persisted_operation(
                existing,
                signal_id=signal_id,
                command="signal.paper_pending.confirm",
                request=request,
            )
            if current.status == "paper_pending":
                return current
            replay = _replayed_operation(current, operation_id, target="paper_pending")
            if replay is not None:
                return replay
            raise ValueError("signal cannot replay paper confirmation from status %s" % current.status)
        if current.status not in {"new", "watching", "backtested"}:
            raise ValueError(f"signal cannot be confirmed from status {current.status}")

        updated = TradingSignal(
            current.id,
            current.agent_id,
            current.source,
            current.code,
            current.direction,
            current.confidence,
            current.time_horizon,
            list(current.entry_reasons),
            list(current.risk_notes),
            current.suggested_position,
            current.stop_loss,
            current.take_profit,
            "paper_pending",
            current.created_at,
            current.expires_at,
            {
                **current.metadata,
                "confirmed_by": confirmed_by,
                "paper_pending_at": iso_now(),
                "promotion": decision.to_dict(),
                "promotion_approval": {
                    "operation_id": approval_operation_id,
                    "decision": decision.to_dict(),
                },
                "operation": {
                    "operation_id": operation_id,
                    "command": "signal.paper_pending.confirm",
                    "target": "paper_pending",
                    "confirmed_by": confirmed_by,
                    "approval_operation_id": approval_operation_id,
                    "request": request,
                },
            },
            action=current.action,
            score=current.score,
            entry_low=current.entry_low,
            entry_high=current.entry_high,
            target_price=current.target_price,
            invalidation=current.invalidation,
            watch_conditions=list(current.watch_conditions),
            reason=current.reason,
            risk_summary=current.risk_summary,
            catalyst_summary=current.catalyst_summary,
            factor_contributions=dict(current.factor_contributions),
            evidence_snapshot_id=current.evidence_snapshot_id,
            research_job_id=current.research_job_id,
            data_quality=current.data_quality,
            missing_fields=list(current.missing_fields),
            source_health=dict(current.source_health),
            model_metadata=dict(current.model_metadata),
        )
        transition_metadata = {
            "confirmed_by": confirmed_by,
            "promotion": decision.to_dict(),
            "approval_operation_id": approval_operation_id,
            "operation_id": operation_id,
            "command": "signal.paper_pending.confirm",
            "request": request,
        }
        atomic_transition = getattr(self.repo, "transition_signal_atomically", None)
        if not callable(atomic_transition):
            raise TypeError("paper confirmation requires an operation-capable repository")
        result = atomic_transition(
            updated,
            expected_status=current.status,
            actor=confirmed_by,
            reason="paper promotion manually confirmed",
            metadata=transition_metadata,
            operation_id=operation_id,
            operation_request=request,
            command="signal.paper_pending.confirm",
        )
        return result if isinstance(result, TradingSignal) else updated

    def list(self, limit: int = 100) -> list[TradingSignal]:
        return self.repo.list_signals(limit=limit)

    def _get_persisted_operation(self, operation_id: str):
        getter = getattr(self.repo, "get_operation", None)
        if not callable(getter):
            return None
        try:
            return getter(operation_id)
        except KeyError:
            return None

    def _record_operation(self, operation_id: str, *, command: str, aggregate_id: str, request: dict, result: dict):
        recorder = getattr(self.repo, "record_operation", None)
        if not callable(recorder):
            raise TypeError("policy approval requires an operation-capable repository")
        return recorder(
            operation_id,
            command=command,
            aggregate_type="signal",
            aggregate_id=aggregate_id,
            request=request,
            status="completed",
            result=result,
        )

    @staticmethod
    def _assert_persisted_operation(operation, *, signal_id: str, command: str, request: dict) -> None:
        if operation.command != command or operation.aggregate_type != "signal" or operation.aggregate_id != signal_id:
            raise OperationConflict("operation_id was already used for different command facts")
        if operation.request != request:
            raise OperationConflict("operation_id was already used with different command facts")


def _decision_from_operation(operation) -> PromotionDecision:
    payload = operation.result.get("decision") if isinstance(operation.result, dict) else None
    if not isinstance(payload, dict):
        raise ValueError("policy approval operation has no decision result")
    return PromotionDecision.from_dict(payload)


def _require_operation_id(operation_id: str | None) -> str:
    return normalize_operation_id(operation_id)


def _operation_from_metadata(metadata: dict | None, operation_id: str) -> dict | None:
    operation = (metadata or {}).get("operation")
    if not isinstance(operation, dict) or operation.get("operation_id") != operation_id:
        return None
    return operation


def _replayed_operation(
    current: TradingSignal,
    operation_id: str,
    *,
    target: str,
    confirmed_by: str | None = None,
    decision: PromotionDecision | None = None,
) -> TradingSignal | None:
    operation = _operation_from_metadata(current.metadata, operation_id)
    if operation is None:
        return None
    return _replay_or_reject(
        operation,
        current,
        operation_id,
        target=target,
        confirmed_by=confirmed_by,
        decision=decision,
    )


def _replay_or_reject(
    operation: dict,
    current: TradingSignal,
    operation_id: str,
    *,
    target: str,
    confirmed_by: str | None = None,
    decision: PromotionDecision | None = None,
) -> TradingSignal:
    if operation.get("target") != target or operation.get("command") != "signal.paper_pending":
        raise ValueError("operation_id was already used for a different signal command")
    if confirmed_by is not None and operation.get("confirmed_by") != confirmed_by:
        raise ValueError("operation_id was already used with different confirmation facts")
    request = operation.get("request")
    if decision is not None and isinstance(request, dict) and request.get("decision") != decision.to_dict():
        raise ValueError("operation_id was already used with different promotion facts")
    return current
