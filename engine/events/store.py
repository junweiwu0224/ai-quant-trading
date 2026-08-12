"""Compatibility imports for the canonical outbox seam."""

from __future__ import annotations

from typing import Protocol

from .models import FailureKind, OutboxStatus
from .outbox import (
    InMemoryOutbox,
    InMemoryOutboxAdapter,
    InMemoryOutboxStore,
    OutboxMessage,
    SQLiteOutbox,
    SQLiteOutboxAdapter,
    SQLiteOutboxStore,
)


OutboxRecord = OutboxMessage


class OutboxStore(Protocol):
    def publish(self, event): ...

    def claim(self, *, consumer: str, limit: int = 20, now=None, event_types=None): ...

    def mark_delivered(self, event_id: str, *, consumer: str, claim_token: str) -> None: ...

    def mark_failed(
        self,
        event_id: str,
        *,
        consumer: str,
        claim_token: str,
        error: str,
        retryable: bool,
        max_attempts: int = 5,
        retry_after: float | None = None,
        now=None,
    ) -> None: ...


__all__ = [
    "FailureKind",
    "InMemoryOutbox",
    "InMemoryOutboxAdapter",
    "InMemoryOutboxStore",
    "OutboxMessage",
    "OutboxRecord",
    "OutboxStatus",
    "OutboxStore",
    "SQLiteOutbox",
    "SQLiteOutboxAdapter",
    "SQLiteOutboxStore",
]
