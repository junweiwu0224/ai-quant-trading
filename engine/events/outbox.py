"""Durable, idempotent event delivery queue."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Union

from .models import DomainEvent, OutboxRecord


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Optional[datetime] = None) -> str:
    return (value or _now()).isoformat(timespec="seconds").replace("+00:00", "Z")


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


OutboxMessage = OutboxRecord


class SQLiteOutbox:
    """SQLite Adapter with claim, acknowledgement, and retry semantics.

    Supplied connections remain owned by their caller. Ordinary writes join
    an existing transaction; claim owns its reservation transaction and
    rejects an already-active external transaction.
    """

    def __init__(
        self,
        database: Union[str, Path, sqlite3.Connection],
        *,
        readonly: bool = False,
    ) -> None:
        self._owns_connection = not isinstance(database, sqlite3.Connection)
        self.readonly = readonly
        self._schema_available = True
        self._database_path: Optional[Path] = None
        if isinstance(database, sqlite3.Connection):
            if readonly:
                raise ValueError("readonly outbox requires a database path")
            self.connection = database
        else:
            database_path = Path(database)
            self._database_path = database_path
            is_memory = str(database_path) == ":memory:"
            if not is_memory and not readonly:
                database_path.parent.mkdir(parents=True, exist_ok=True)
            if readonly:
                if is_memory or not database_path.exists():
                    self.connection = sqlite3.connect(":memory:", timeout=5.0)
                    self._schema_available = False
                else:
                    self.connection = sqlite3.connect(
                        f"file:{database_path}?mode=ro", uri=True, timeout=5.0
                    )
            else:
                self.connection = sqlite3.connect(
                    str(database_path), timeout=5.0, check_same_thread=False
                )
        self._lock = threading.RLock()
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA busy_timeout=5000")
        # Never change journal mode on a caller-supplied connection.
        if self._owns_connection and not readonly and self._database_path is not None:
            if str(self._database_path) != ":memory:":
                try:
                    self.connection.execute("PRAGMA journal_mode=WAL")
                except sqlite3.OperationalError:
                    pass
            self._initialize()
        elif self._owns_connection and readonly:
            self._schema_available = self._table_exists()
        else:
            self._initialize()

    def _table_exists(self) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='outbox_events' LIMIT 1"
        ).fetchone()
        return row is not None

    def _initialize(self) -> None:
        if self.readonly:
            return
        had_external_transaction = self.connection.in_transaction
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS outbox_events (
                event_id TEXT PRIMARY KEY,
                idempotency_key TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                aggregate_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                available_at TEXT NOT NULL,
                locked_by TEXT,
                locked_at TEXT,
                claim_token TEXT,
                last_error TEXT
            )
            """
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_outbox_claim ON outbox_events(status, available_at)"
        )
        columns = {
            row["name"]
            for row in self.connection.execute("PRAGMA table_info(outbox_events)").fetchall()
        }
        if "claim_token" not in columns:
            self.connection.execute("ALTER TABLE outbox_events ADD COLUMN claim_token TEXT")
        if not had_external_transaction:
            self.connection.commit()

    def _assert_writable(self) -> None:
        if self.readonly:
            raise sqlite3.OperationalError("outbox is read-only")

    def publish(self, event: DomainEvent) -> str:
        self._assert_writable()
        with self._lock:
            had_transaction = self.connection.in_transaction
            key = event.idempotency_key or event.event_id
            self.connection.execute(
                """
                INSERT OR IGNORE INTO outbox_events(
                    event_id, idempotency_key, event_type, aggregate_id, payload_json,
                    occurred_at, status, attempts, available_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, ?)
                """,
                (
                    event.event_id,
                    key,
                    event.event_type,
                    event.aggregate_id,
                    _dump(dict(event.payload)),
                    event.occurred_at,
                    _iso(),
                ),
            )
            if not had_transaction:
                self.connection.commit()
            row = self.connection.execute(
                "SELECT event_id FROM outbox_events WHERE idempotency_key = ?", (key,)
            ).fetchone()
            if row is None:
                raise RuntimeError("event was not persisted to outbox")
            return row["event_id"]

    @staticmethod
    def _message_from_row(row: sqlite3.Row) -> OutboxMessage:
        event = DomainEvent(
            event_type=row["event_type"],
            aggregate_id=row["aggregate_id"],
            payload=json.loads(row["payload_json"]),
            event_id=row["event_id"],
            occurred_at=row["occurred_at"],
            idempotency_key=row["idempotency_key"],
        )
        return OutboxMessage(
            event=event,
            status=row["status"],
            attempts=row["attempts"],
            available_at=row["available_at"],
            locked_by=row["locked_by"],
            last_error=row["last_error"],
            claim_token=row["claim_token"],
        )

    def get(self, event_id: str) -> Optional[OutboxMessage]:
        with self._lock:
            if not self._schema_available:
                return None
            row = self.connection.execute(
                "SELECT * FROM outbox_events WHERE event_id = ?", (event_id,)
            ).fetchone()
            return None if row is None else self._message_from_row(row)

    def claim(
        self,
        *,
        consumer: str,
        limit: int = 20,
        now: Optional[datetime] = None,
        event_types: Optional[list[str] | tuple[str, ...] | set[str]] = None,
    ) -> List[OutboxMessage]:
        if limit <= 0:
            raise ValueError("outbox claim limit must be positive")
        self._assert_writable()
        current = _iso(now)
        with self._lock:
            if self.connection.in_transaction:
                raise sqlite3.OperationalError(
                    "active transaction cannot be used for outbox claim"
                )
            try:
                self.connection.execute("BEGIN IMMEDIATE")
                where = ["status = 'pending'", "available_at <= ?"]
                params: list[object] = [current]
                normalized_types = tuple(dict.fromkeys(str(item) for item in (event_types or ()) if str(item)))
                if normalized_types:
                    placeholders = ", ".join("?" for _ in normalized_types)
                    where.append(f"event_type IN ({placeholders})")
                    params.extend(normalized_types)
                params.append(limit)
                rows = self.connection.execute(
                    """
                    SELECT * FROM outbox_events
                    WHERE %s
                    ORDER BY available_at, occurred_at, event_id
                    LIMIT ?
                    """ % " AND ".join(where),
                    params,
                ).fetchall()
                claimed: List[OutboxMessage] = []
                for row in rows:
                    claim_token = uuid.uuid4().hex
                    updated_count = self.connection.execute(
                        """
                        UPDATE outbox_events
                        SET status='in_flight', attempts=attempts + 1,
                            locked_by=?, locked_at=?, claim_token=?
                        WHERE event_id=? AND status='pending'
                        """,
                        (consumer, current, claim_token, row["event_id"]),
                    ).rowcount
                    if updated_count != 1:
                        continue
                    updated = self.connection.execute(
                        "SELECT * FROM outbox_events WHERE event_id = ?", (row["event_id"],)
                    ).fetchone()
                    if updated is not None and updated["status"] == "in_flight" and updated["locked_by"] == consumer:
                        claimed.append(self._message_from_row(updated))
                self.connection.commit()
                return claimed
            except Exception:
                self.connection.rollback()
                raise

    def mark_delivered(self, event_id: str, *, consumer: str, claim_token: str) -> None:
        self._assert_writable()
        if not claim_token:
            raise ValueError("claim_token is required")
        with self._lock:
            had_transaction = self.connection.in_transaction
            try:
                updated = self.connection.execute(
                    """
                    UPDATE outbox_events
                    SET status='delivered', locked_by=NULL, locked_at=NULL,
                        claim_token=NULL, last_error=NULL
                    WHERE event_id=? AND status='in_flight' AND locked_by=? AND claim_token=?
                    """,
                    (event_id, consumer, claim_token),
                ).rowcount
                if not had_transaction:
                    self.connection.commit()
            except Exception:
                if not had_transaction:
                    self.connection.rollback()
                raise
            if updated != 1:
                raise RuntimeError("outbox event is not owned by consumer: %s" % event_id)

    def mark_failed(
        self,
        event_id: str,
        *,
        consumer: str,
        claim_token: str,
        error: str,
        retryable: bool,
        max_attempts: int = 5,
        retry_after: Optional[float] = None,
        now: Optional[datetime] = None,
    ) -> None:
        self._assert_writable()
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if not claim_token:
            raise ValueError("claim_token is required")
        with self._lock:
            row = self.connection.execute(
                "SELECT attempts FROM outbox_events WHERE event_id=? AND status='in_flight' AND locked_by=? AND claim_token=?",
                (event_id, consumer, claim_token),
            ).fetchone()
            if row is None:
                raise RuntimeError("outbox event is not owned by consumer: %s" % event_id)
            attempts = int(row["attempts"])
            should_retry = retryable and attempts < max_attempts
            if should_retry:
                delay = (
                    max(0.0, min(300.0, float(retry_after)))
                    if retry_after is not None
                    else min(300, 2 ** max(0, attempts - 1))
                )
                next_at = _iso((now or _now()) + timedelta(seconds=delay))
                status = "pending"
            else:
                next_at = _iso(now)
                status = "dead"
            had_transaction = self.connection.in_transaction
            try:
                updated = self.connection.execute(
                    """
                    UPDATE outbox_events
                    SET status=?, available_at=?, locked_by=NULL, locked_at=NULL,
                        claim_token=NULL, last_error=?
                    WHERE event_id=? AND status='in_flight' AND locked_by=? AND claim_token=?
                    """,
                    (status, next_at, error, event_id, consumer, claim_token),
                ).rowcount
                if not had_transaction:
                    self.connection.commit()
            except Exception:
                if not had_transaction:
                    self.connection.rollback()
                raise
            if updated != 1:
                raise RuntimeError("outbox event is not owned by consumer: %s" % event_id)

    def reclaim_stale(
        self,
        *,
        older_than_seconds: int = 300,
        now: Optional[datetime] = None,
    ) -> int:
        """Return abandoned in-flight messages to pending after a worker crash."""

        if older_than_seconds < 0:
            raise ValueError("older_than_seconds cannot be negative")
        self._assert_writable()
        cutoff = _iso((now or _now()) - timedelta(seconds=older_than_seconds))
        with self._lock:
            had_transaction = self.connection.in_transaction
            try:
                updated = self.connection.execute(
                    """
                    UPDATE outbox_events
                    SET status='pending', locked_by=NULL, locked_at=NULL, claim_token=NULL
                    WHERE status='in_flight' AND locked_at IS NOT NULL AND locked_at <= ?
                    """,
                    (cutoff,),
                ).rowcount
                if not had_transaction:
                    self.connection.commit()
                return updated
            except Exception:
                if not had_transaction:
                    self.connection.rollback()
                raise

    def close(self) -> None:
        with self._lock:
            if self._owns_connection:
                self.connection.close()


class InMemoryOutboxStore(SQLiteOutbox):
    """SQLite-backed in-memory Adapter with the same outbox Interface."""

    def __init__(self) -> None:
        super().__init__(sqlite3.connect(":memory:"))


SQLiteOutboxStore = SQLiteOutbox
SQLiteOutboxAdapter = SQLiteOutbox
InMemoryOutbox = InMemoryOutboxStore
InMemoryOutboxAdapter = InMemoryOutboxStore
