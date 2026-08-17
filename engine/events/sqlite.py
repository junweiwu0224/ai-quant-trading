"""Compatibility import for the SQLite outbox implementation."""

from .outbox import SQLiteOutboxStore

SQLiteOutboxImplementation = SQLiteOutboxStore

__all__ = ["SQLiteOutboxImplementation", "SQLiteOutboxStore"]
