"""Serializable domain event records."""

from __future__ import annotations

import uuid
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Optional


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class DomainEvent:
    event_type: str
    aggregate_id: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    occurred_at: str = field(default_factory=utc_now)
    idempotency_key: Optional[str] = None

    @classmethod
    def create(
        cls,
        event_type: str,
        aggregate_id: str,
        payload: Mapping[str, Any],
        *,
        idempotency_key: Optional[str] = None,
        occurred_at: Optional[str] = None,
    ) -> "DomainEvent":
        return cls(
            event_type=event_type,
            aggregate_id=aggregate_id,
            payload=dict(payload),
            idempotency_key=idempotency_key,
            occurred_at=occurred_at or utc_now(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "aggregate_id": self.aggregate_id,
            "occurred_at": self.occurred_at,
            "idempotency_key": self.idempotency_key,
            "payload": dict(self.payload),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, default=str)


class OutboxStatus(str, Enum):
    PENDING = "pending"
    IN_FLIGHT = "in_flight"
    DELIVERED = "delivered"
    DEAD = "dead"


class FailureKind(str, Enum):
    RETRYABLE = "retryable"
    PERMANENT = "permanent"


@dataclass(frozen=True)
class OutboxRecord:
    event: DomainEvent
    status: str
    attempts: int
    available_at: str
    locked_by: Optional[str] = None
    last_error: Optional[str] = None
    claim_token: Optional[str] = None
