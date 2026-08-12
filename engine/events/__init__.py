"""Domain events and durable outbox primitives."""

from .models import DomainEvent, FailureKind, OutboxRecord, OutboxStatus
from .outbox import (
    InMemoryOutbox,
    InMemoryOutboxAdapter,
    InMemoryOutboxStore,
    OutboxMessage,
    SQLiteOutbox,
    SQLiteOutboxAdapter,
    SQLiteOutboxStore,
)

__all__ = [
    "DomainEvent",
    "FailureKind",
    "InMemoryOutbox",
    "InMemoryOutboxAdapter",
    "InMemoryOutboxStore",
    "OutboxMessage",
    "OutboxRecord",
    "OutboxStatus",
    "SQLiteOutbox",
    "SQLiteOutboxAdapter",
    "SQLiteOutboxStore",
]
