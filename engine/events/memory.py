"""Compatibility import for the in-memory outbox adapter."""

from .outbox import InMemoryOutboxStore

InMemoryOutboxAdapter = InMemoryOutboxStore

__all__ = ["InMemoryOutboxAdapter", "InMemoryOutboxStore"]
