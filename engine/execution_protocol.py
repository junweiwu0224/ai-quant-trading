"""Immutable execution command protocol shared by Paper and Live workers.

This module contains domain contracts only.  It does not submit orders, talk to
brokers, or perform the final risk check.  The execution Worker must apply the
latest account state and final RiskGate immediately before an adapter call; an
API pre-check is never an authoritative risk decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Iterable


class Environment(str, Enum):
    """Execution environment supported by the protocol.

    Live is represented so that callers can preserve an explicit context, but
    this V2 contract remains fail-closed and cannot create a live intent.
    """

    PAPER = "paper"
    LIVE = "live"


class Side(str, Enum):
    """Side of an order intent, independent from the legacy Direction enum."""

    BUY = "buy"
    SELL = "sell"


class RiskDecisionStatus(str, Enum):
    """Outcome of one final, batch-level RiskGate evaluation."""

    APPROVED = "approved"
    PARTIALLY_APPROVED = "partially_approved"
    # Short spelling is useful to adapters while retaining one wire value.
    PARTIAL = "partially_approved"
    REJECTED = "rejected"


class _NonEmptyTextMixin:
    @staticmethod
    def _text(value: str, field_name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must be a non-empty string")
        return value.strip()


def _as_environment(value: Environment | str) -> Environment:
    if isinstance(value, Environment):
        return value
    try:
        return Environment(str(value).strip().lower())
    except ValueError as exc:
        raise ValueError(f"unsupported environment: {value!r}") from exc


def _as_side(value: Side | str) -> Side:
    if isinstance(value, Side):
        return value
    try:
        return Side(str(value).strip().lower())
    except ValueError as exc:
        raise ValueError(f"unsupported side: {value!r}") from exc


def _as_decimal(value: Decimal | int | float | str, field_name: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive number")
    try:
        quantity = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field_name} must be a valid number") from exc
    if not quantity.is_finite() or quantity <= 0:
        raise ValueError(f"{field_name} must be positive and finite")
    return quantity


def _as_tuple(values: Iterable[str], field_name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{field_name} must be an iterable of strings")
    result = tuple(_NonEmptyTextMixin._text(value, field_name) for value in values)
    return result


@dataclass(frozen=True, slots=True)
class OrderIntent(_NonEmptyTextMixin):
    """An immutable request for a quantity of one instrument to be executed.

    ``allow_live`` is intentionally retained as an explicit fail-closed guard
    for future versioning.  V2 has no live execution capability, so even an
    explicit opt-in is rejected until a separately approved live protocol
    exists.
    """

    execution_run_id: str
    account_id: str
    environment: Environment | str
    instrument: str
    side: Side | str
    quantity: Decimal | int | float | str
    idempotency_key: str
    allow_live: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "execution_run_id", self._text(self.execution_run_id, "execution_run_id"))
        object.__setattr__(self, "account_id", self._text(self.account_id, "account_id"))
        object.__setattr__(self, "instrument", self._text(self.instrument, "instrument"))
        object.__setattr__(self, "idempotency_key", self._text(self.idempotency_key, "idempotency_key"))
        environment = _as_environment(self.environment)
        object.__setattr__(self, "environment", environment)
        object.__setattr__(self, "side", _as_side(self.side))
        object.__setattr__(self, "quantity", _as_decimal(self.quantity, "quantity"))
        if not isinstance(self.allow_live, bool):
            raise ValueError("allow_live must be a boolean")
        if environment is Environment.LIVE:
            raise ValueError("live execution is disabled in V2 (fail closed)")


@dataclass(frozen=True, slots=True)
class OrderIntentBatch(_NonEmptyTextMixin):
    """Immutable, replay-stable collection of intents for one risk decision."""

    batch_id: str
    intents: tuple[OrderIntent, ...] | Iterable[OrderIntent]

    def __post_init__(self) -> None:
        object.__setattr__(self, "batch_id", self._text(self.batch_id, "batch_id"))
        intents = tuple(self.intents)
        if not intents:
            raise ValueError("OrderIntentBatch must contain at least one intent")
        if any(not isinstance(intent, OrderIntent) for intent in intents):
            raise TypeError("intents must contain only OrderIntent instances")
        idempotency_keys = [intent.idempotency_key for intent in intents]
        if len(idempotency_keys) != len(set(idempotency_keys)):
            raise ValueError("idempotency_key values must be unique within a batch")
        contexts = {
            (intent.execution_run_id, intent.account_id, intent.environment)
            for intent in intents
        }
        if len(contexts) != 1:
            raise ValueError(
                "all intents in a batch must share execution_run_id, account_id, and environment"
            )
        object.__setattr__(self, "intents", intents)

    @property
    def idempotency_keys(self) -> tuple[str, ...]:
        """Stable intent keys preserved in their original batch order."""

        return tuple(intent.idempotency_key for intent in self.intents)


@dataclass(frozen=True, slots=True)
class RiskDecision(_NonEmptyTextMixin):
    """Immutable outcome emitted by the execution Worker's final RiskGate.

    ``approved_intent_keys`` and ``rejected_intent_keys`` identify the subset
    when a batch is partially approved.  This object must be created from the
    latest account/ledger state by the Worker, not treated as an API pre-check.
    """

    decision_id: str
    batch_id: str
    policy_version: str
    evaluated_at: datetime
    status: RiskDecisionStatus | str
    evaluated_intent_keys: tuple[str, ...] | Iterable[str]
    reasons: tuple[str, ...] | Iterable[str] = ()
    approved_intent_keys: tuple[str, ...] | Iterable[str] = ()
    rejected_intent_keys: tuple[str, ...] | Iterable[str] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_id", self._text(self.decision_id, "decision_id"))
        object.__setattr__(self, "batch_id", self._text(self.batch_id, "batch_id"))
        object.__setattr__(self, "policy_version", self._text(self.policy_version, "policy_version"))
        if not isinstance(self.evaluated_at, datetime):
            raise TypeError("evaluated_at must be a datetime")
        try:
            status = self.status if isinstance(self.status, RiskDecisionStatus) else RiskDecisionStatus(str(self.status).strip().lower())
        except ValueError as exc:
            raise ValueError(f"unsupported risk decision status: {self.status!r}") from exc
        object.__setattr__(self, "status", status)
        evaluated = _as_tuple(self.evaluated_intent_keys, "evaluated_intent_key")
        if not evaluated:
            raise ValueError("RiskDecision must identify evaluated intents")
        if len(evaluated) != len(set(evaluated)):
            raise ValueError("evaluated_intent_keys must be unique")
        approved = _as_tuple(self.approved_intent_keys, "approved_intent_key")
        rejected = _as_tuple(self.rejected_intent_keys, "rejected_intent_key")
        evaluated_set = set(evaluated)
        approved_set = set(approved)
        rejected_set = set(rejected)
        if approved_set & rejected_set:
            raise ValueError("an intent cannot be both approved and rejected")
        if not approved_set <= evaluated_set or not rejected_set <= evaluated_set:
            raise ValueError("approved/rejected intents must belong to the evaluated batch")
        if approved_set | rejected_set != evaluated_set:
            raise ValueError("approved and rejected intents must cover all evaluated intents")
        if status is RiskDecisionStatus.APPROVED and (
            approved_set != evaluated_set or rejected_set
        ):
            raise ValueError("approved decision must approve every evaluated intent")
        if status is RiskDecisionStatus.PARTIALLY_APPROVED and (
            not approved_set or not rejected_set
        ):
            raise ValueError("partial approval must contain both approved and rejected intents")
        if status is RiskDecisionStatus.REJECTED and (
            bool(approved_set) or rejected_set != evaluated_set
        ):
            raise ValueError("rejected decision must reject every evaluated intent")
        object.__setattr__(self, "evaluated_intent_keys", evaluated)
        object.__setattr__(self, "approved_intent_keys", approved)
        object.__setattr__(self, "rejected_intent_keys", rejected)

    @classmethod
    def from_batch(
        cls,
        batch: OrderIntentBatch,
        *,
        decision_id: str,
        policy_version: str,
        evaluated_at: datetime,
        status: RiskDecisionStatus | str,
        approved_intent_keys: Iterable[str] = (),
        rejected_intent_keys: Iterable[str] = (),
        reasons: Iterable[str] = (),
    ) -> "RiskDecision":
        """Create a closed decision whose keys are checked against ``batch``."""
        if not isinstance(batch, OrderIntentBatch):
            raise TypeError("batch must be an OrderIntentBatch")
        evaluated = batch.idempotency_keys
        approved = tuple(approved_intent_keys)
        rejected = tuple(rejected_intent_keys)
        if not set(approved) <= set(evaluated) or not set(rejected) <= set(evaluated):
            raise ValueError("decision keys must belong to the OrderIntentBatch")
        return cls(
            decision_id=decision_id,
            batch_id=batch.batch_id,
            policy_version=policy_version,
            evaluated_at=evaluated_at,
            status=status,
            evaluated_intent_keys=evaluated,
            reasons=reasons,
            approved_intent_keys=approved,
            rejected_intent_keys=rejected,
        )


@dataclass(frozen=True, slots=True, init=False)
class ExecutionPermit(_NonEmptyTextMixin):
    """Short-lived immutable authorization handed from RiskGate to an adapter.

    A permit is only constructible from an approved or partially approved
    ``RiskDecision``.  It carries the worker fence and intent idempotency keys
    so an adapter can reject stale or replayed execution attempts.
    """

    permit_id: str
    decision_id: str
    batch_id: str
    expires_at: datetime
    fence_token: str
    idempotency_keys: tuple[str, ...] | Iterable[str]

    def __init__(
        self,
        *,
        decision: RiskDecision,
        permit_id: str,
        expires_at: datetime,
        fence_token: str,
    ) -> None:
        if not isinstance(decision, RiskDecision):
            raise TypeError("decision must be a RiskDecision")
        if decision.status is RiskDecisionStatus.REJECTED:
            raise ValueError("a rejected RiskDecision cannot create an ExecutionPermit")
        keys = decision.approved_intent_keys
        if set(keys) | set(decision.rejected_intent_keys) != set(decision.evaluated_intent_keys):
            raise ValueError("RiskDecision coverage must be closed before creating a permit")
        if decision.status is RiskDecisionStatus.APPROVED and set(keys) != set(decision.evaluated_intent_keys):
            raise ValueError("approved RiskDecision must cover every evaluated intent")
        object.__setattr__(self, "permit_id", self._text(permit_id, "permit_id"))
        object.__setattr__(self, "decision_id", decision.decision_id)
        object.__setattr__(self, "batch_id", decision.batch_id)
        object.__setattr__(self, "expires_at", expires_at)
        object.__setattr__(self, "fence_token", self._text(fence_token, "fence_token"))
        object.__setattr__(self, "idempotency_keys", keys)
        self.__post_init__()

    @classmethod
    def from_risk_decision(
        cls,
        decision: RiskDecision,
        *,
        permit_id: str,
        expires_at: datetime,
        fence_token: str,
    ) -> "ExecutionPermit":
        return cls(
            decision=decision,
            permit_id=permit_id,
            expires_at=expires_at,
            fence_token=fence_token,
        )

    # Concise alias for callers that already use the domain term "decision".
    from_decision = from_risk_decision

    def __post_init__(self) -> None:
        object.__setattr__(self, "permit_id", self._text(self.permit_id, "permit_id"))
        object.__setattr__(self, "decision_id", self._text(self.decision_id, "decision_id"))
        object.__setattr__(self, "batch_id", self._text(self.batch_id, "batch_id"))
        object.__setattr__(self, "fence_token", self._text(self.fence_token, "fence_token"))
        if not isinstance(self.expires_at, datetime):
            raise TypeError("expires_at must be a datetime")
        keys = _as_tuple(self.idempotency_keys, "idempotency_key")
        if not keys:
            raise ValueError("ExecutionPermit must contain at least one idempotency key")
        if len(keys) != len(set(keys)):
            raise ValueError("idempotency_keys must be unique")
        object.__setattr__(self, "idempotency_keys", keys)


__all__ = [
    "Environment",
    "ExecutionPermit",
    "OrderIntent",
    "OrderIntentBatch",
    "RiskDecision",
    "RiskDecisionStatus",
    "Side",
]
