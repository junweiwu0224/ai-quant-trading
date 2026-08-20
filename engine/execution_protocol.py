"""Immutable execution command protocol shared by Paper and Live workers.

This module contains domain contracts only.  It does not submit orders, talk to
brokers, or perform the final risk check.  The execution Worker must apply the
latest account state and final RiskGate immediately before an adapter call; an
API pre-check is never an authoritative risk decision.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
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


def _as_utc_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    return value.astimezone(timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


_RISK_DECISION_TOKEN = object()


def _protocol_json(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_protocol_json(item) for item in value]
    if isinstance(value, list):
        return [_protocol_json(item) for item in value]
    if isinstance(value, dict):
        return {key: _protocol_json(item) for key, item in value.items()}
    return value


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
    emergency: bool = False

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
        if not isinstance(self.emergency, bool):
            raise ValueError("emergency must be a boolean")
        if environment is Environment.LIVE:
            raise ValueError("live execution is disabled in V2 (fail closed)")

    def to_dict(self) -> dict:
        return _protocol_json(asdict(self))

    @classmethod
    def from_dict(cls, value: dict) -> "OrderIntent":
        return cls(**dict(value))


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

    @property
    def execution_run_id(self) -> str:
        return self.intents[0].execution_run_id

    @property
    def account_id(self) -> str:
        return self.intents[0].account_id

    @property
    def environment(self) -> Environment:
        return self.intents[0].environment

    def to_dict(self) -> dict:
        return {"batch_id": self.batch_id, "intents": [intent.to_dict() for intent in self.intents]}

    @classmethod
    def from_dict(cls, value: dict) -> "OrderIntentBatch":
        return cls(batch_id=value["batch_id"], intents=tuple(OrderIntent.from_dict(item) for item in value["intents"]))


@dataclass(frozen=True, slots=True, init=False)
class RiskDecision(_NonEmptyTextMixin):
    """Immutable outcome emitted by the execution Worker's final RiskGate.

    ``approved_intent_keys`` and ``rejected_intent_keys`` identify the subset
    when a batch is partially approved.  This object must be created from the
    latest account/ledger state by the Worker, not treated as an API pre-check.
    """

    decision_id: str
    batch_id: str
    execution_run_id: str
    account_id: str
    environment: Environment | str
    policy_version: str
    evaluated_at: datetime
    status: RiskDecisionStatus | str
    evaluated_intent_keys: tuple[str, ...] | Iterable[str]
    reasons: tuple[str, ...] | Iterable[str] = ()
    approved_intent_keys: tuple[str, ...] | Iterable[str] = ()
    rejected_intent_keys: tuple[str, ...] | Iterable[str] = ()

    def __init__(
        self,
        *,
        decision_id: str,
        batch_id: str,
        execution_run_id: str,
        account_id: str,
        environment: Environment | str,
        policy_version: str,
        evaluated_at: datetime,
        status: RiskDecisionStatus | str,
        evaluated_intent_keys: tuple[str, ...] | Iterable[str],
        reasons: tuple[str, ...] | Iterable[str] = (),
        approved_intent_keys: tuple[str, ...] | Iterable[str] = (),
        rejected_intent_keys: tuple[str, ...] | Iterable[str] = (),
        _construction_token: object | None = None,
    ) -> None:
        if _construction_token is not _RISK_DECISION_TOKEN:
            raise TypeError("RiskDecision must be created from an OrderIntentBatch")
        object.__setattr__(self, "decision_id", decision_id)
        object.__setattr__(self, "batch_id", batch_id)
        object.__setattr__(self, "execution_run_id", execution_run_id)
        object.__setattr__(self, "account_id", account_id)
        object.__setattr__(self, "environment", environment)
        object.__setattr__(self, "policy_version", policy_version)
        object.__setattr__(self, "evaluated_at", evaluated_at)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "evaluated_intent_keys", evaluated_intent_keys)
        object.__setattr__(self, "reasons", reasons)
        object.__setattr__(self, "approved_intent_keys", approved_intent_keys)
        object.__setattr__(self, "rejected_intent_keys", rejected_intent_keys)
        self.__post_init__()

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_id", self._text(self.decision_id, "decision_id"))
        object.__setattr__(self, "batch_id", self._text(self.batch_id, "batch_id"))
        object.__setattr__(self, "execution_run_id", self._text(self.execution_run_id, "execution_run_id"))
        object.__setattr__(self, "account_id", self._text(self.account_id, "account_id"))
        environment = _as_environment(self.environment)
        if environment is not Environment.PAPER:
            raise ValueError("RiskDecision can only authorize the paper environment in V2")
        object.__setattr__(self, "environment", environment)
        object.__setattr__(self, "policy_version", self._text(self.policy_version, "policy_version"))
        object.__setattr__(self, "evaluated_at", _as_utc_datetime(self.evaluated_at, "evaluated_at"))
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

    def to_dict(self) -> dict:
        return _protocol_json({
            "decision_id": self.decision_id,
            "batch_id": self.batch_id,
            "execution_run_id": self.execution_run_id,
            "account_id": self.account_id,
            "environment": self.environment,
            "policy_version": self.policy_version,
            "evaluated_at": self.evaluated_at,
            "status": self.status,
            "evaluated_intent_keys": self.evaluated_intent_keys,
            "reasons": self.reasons,
            "approved_intent_keys": self.approved_intent_keys,
            "rejected_intent_keys": self.rejected_intent_keys,
        })

    @classmethod
    def from_dict(cls, value: dict) -> "RiskDecision":
        return cls(
            decision_id=value["decision_id"], batch_id=value["batch_id"],
            execution_run_id=value["execution_run_id"], account_id=value["account_id"],
            environment=value["environment"], policy_version=value.get("policy_version", "serialized"),
            evaluated_at=datetime.fromisoformat(value["evaluated_at"]), status=value["status"],
            evaluated_intent_keys=tuple(value["evaluated_intent_keys"]),
            reasons=tuple(value.get("reasons", ())),
            approved_intent_keys=tuple(value.get("approved_intent_keys", ())),
            rejected_intent_keys=tuple(value.get("rejected_intent_keys", ())),
            _construction_token=_RISK_DECISION_TOKEN,
        )

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
            execution_run_id=batch.execution_run_id,
            account_id=batch.account_id,
            environment=batch.environment,
            policy_version=policy_version,
            evaluated_at=evaluated_at,
            status=status,
            evaluated_intent_keys=evaluated,
            reasons=reasons,
            approved_intent_keys=approved,
            rejected_intent_keys=rejected,
            _construction_token=_RISK_DECISION_TOKEN,
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
    execution_run_id: str
    account_id: str
    environment: Environment | str
    expires_at: datetime
    fence_token: str
    evaluated_intent_keys: tuple[str, ...] | Iterable[str]
    idempotency_keys: tuple[str, ...] | Iterable[str]

    def __init__(
        self,
        *,
        decision: RiskDecision,
        permit_id: str,
        expires_at: datetime,
        fence_token: str,
        now: datetime | None = None,
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
        current = _as_utc_datetime(now if now is not None else _utc_now(), "now")
        expiry = _as_utc_datetime(expires_at, "expires_at")
        if expiry <= current:
            raise ValueError("expires_at must be later than now")
        object.__setattr__(self, "permit_id", self._text(permit_id, "permit_id"))
        object.__setattr__(self, "decision_id", decision.decision_id)
        object.__setattr__(self, "batch_id", decision.batch_id)
        object.__setattr__(self, "execution_run_id", decision.execution_run_id)
        object.__setattr__(self, "account_id", decision.account_id)
        object.__setattr__(self, "environment", decision.environment)
        object.__setattr__(self, "expires_at", expiry)
        object.__setattr__(self, "fence_token", self._text(fence_token, "fence_token"))
        object.__setattr__(self, "evaluated_intent_keys", decision.evaluated_intent_keys)
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
        now: datetime | None = None,
    ) -> "ExecutionPermit":
        return cls(
            decision=decision,
            permit_id=permit_id,
            expires_at=expires_at,
            fence_token=fence_token,
            now=now,
        )

    # Concise alias for callers that already use the domain term "decision".
    from_decision = from_risk_decision

    def __post_init__(self) -> None:
        object.__setattr__(self, "permit_id", self._text(self.permit_id, "permit_id"))
        object.__setattr__(self, "decision_id", self._text(self.decision_id, "decision_id"))
        object.__setattr__(self, "batch_id", self._text(self.batch_id, "batch_id"))
        object.__setattr__(self, "execution_run_id", self._text(self.execution_run_id, "execution_run_id"))
        object.__setattr__(self, "account_id", self._text(self.account_id, "account_id"))
        environment = _as_environment(self.environment)
        if environment is not Environment.PAPER:
            raise ValueError("ExecutionPermit can only authorize the paper environment in V2")
        object.__setattr__(self, "environment", environment)
        object.__setattr__(self, "fence_token", self._text(self.fence_token, "fence_token"))
        if not isinstance(self.expires_at, datetime):
            raise TypeError("expires_at must be a datetime")
        object.__setattr__(self, "expires_at", _as_utc_datetime(self.expires_at, "expires_at"))
        evaluated = _as_tuple(self.evaluated_intent_keys, "evaluated_intent_key")
        if not evaluated:
            raise ValueError("ExecutionPermit must contain evaluated intent keys")
        object.__setattr__(self, "evaluated_intent_keys", evaluated)
        keys = _as_tuple(self.idempotency_keys, "idempotency_key")
        if not keys:
            raise ValueError("ExecutionPermit must contain at least one idempotency key")
        if len(keys) != len(set(keys)):
            raise ValueError("idempotency_keys must be unique")
        if not set(keys) <= set(evaluated):
            raise ValueError("idempotency_keys must belong to evaluated_intent_keys")
        object.__setattr__(self, "idempotency_keys", keys)

    def to_dict(self) -> dict:
        return _protocol_json({
            "permit_id": self.permit_id,
            "decision_id": self.decision_id,
            "batch_id": self.batch_id,
            "execution_run_id": self.execution_run_id,
            "account_id": self.account_id,
            "environment": self.environment,
            "expires_at": self.expires_at,
            "fence_token": self.fence_token,
            "evaluated_intent_keys": self.evaluated_intent_keys,
            "idempotency_keys": self.idempotency_keys,
        })

    @classmethod
    def from_dict(cls, value: dict) -> "ExecutionPermit":
        decision = RiskDecision(
            decision_id=value["decision_id"], batch_id=value["batch_id"],
            execution_run_id=value["execution_run_id"], account_id=value["account_id"],
            environment=value["environment"], policy_version=value.get("policy_version", "serialized"),
            evaluated_at=datetime.fromisoformat(value.get("evaluated_at", value["expires_at"])),
            status=value.get("status", RiskDecisionStatus.APPROVED),
            evaluated_intent_keys=tuple(value["evaluated_intent_keys"]),
            approved_intent_keys=tuple(value["idempotency_keys"]),
            rejected_intent_keys=tuple(key for key in value["evaluated_intent_keys"] if key not in value["idempotency_keys"]),
            _construction_token=_RISK_DECISION_TOKEN,
        )
        return cls.from_decision(
            decision, permit_id=value["permit_id"], expires_at=datetime.fromisoformat(value["expires_at"]),
            fence_token=value["fence_token"], now=datetime.now(timezone.utc) - __import__("datetime").timedelta(seconds=1),
        )

    def is_valid(self, *, now: datetime | None = None) -> bool:
        """Return whether this permit is still usable at the supplied UTC time."""
        current = _as_utc_datetime(now if now is not None else _utc_now(), "now")
        return self.expires_at > current


__all__ = [
    "Environment",
    "ExecutionPermit",
    "OrderIntent",
    "OrderIntentBatch",
    "RiskDecision",
    "RiskDecisionStatus",
    "Side",
]
