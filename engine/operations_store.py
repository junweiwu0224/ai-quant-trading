"""Small SQLite-backed command/task/attempt store for V2 operations.

This module owns task lifecycle state only. Payloads are request metadata; task
and attempt state remains represented by typed SQLite columns.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from collections.abc import Callable, Iterable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


class OperationsStoreError(RuntimeError):
    """Base error for operations-store failures."""


class IdempotencyConflictError(OperationsStoreError):
    """Raised when a key is reused for a different command."""


class TaskNotClaimableError(OperationsStoreError):
    """Raised when a task has no available lease to claim."""


class LeaseLostError(OperationsStoreError):
    """Raised when an owner no longer holds the current attempt fence."""


@dataclass(frozen=True)
class Command:
    id: str
    idempotency_key: str
    kind: str
    payload: dict[str, Any]
    created_at: float


@dataclass(frozen=True)
class Task:
    id: str
    command_id: str
    status: str
    created_at: float
    updated_at: float


@dataclass(frozen=True)
class Attempt:
    id: str
    task_id: str
    owner_id: str
    lease_token: str
    fence: int
    status: str
    leased_until: float
    started_at: float
    finished_at: float | None
    error: str | None


@dataclass(frozen=True)
class CommandAcceptance:
    command: Command
    task: Task


_SCHEMA = """
CREATE TABLE IF NOT EXISTS commands (
    id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE CHECK (length(trim(idempotency_key)) > 0),
    kind TEXT NOT NULL CHECK (length(trim(kind)) > 0),
    payload_json TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    command_id TEXT NOT NULL UNIQUE REFERENCES commands(id),
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS task_attempts (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    owner_id TEXT NOT NULL CHECK (length(trim(owner_id)) > 0),
    lease_token TEXT NOT NULL CHECK (length(trim(lease_token)) > 0),
    fence INTEGER NOT NULL CHECK (fence > 0),
    status TEXT NOT NULL CHECK (status IN ('running', 'reclaimed', 'succeeded', 'failed')),
    leased_until REAL NOT NULL,
    started_at REAL NOT NULL,
    finished_at REAL,
    error TEXT,
    UNIQUE (task_id, fence)
);
CREATE INDEX IF NOT EXISTS idx_tasks_claimable ON tasks(status, created_at, id);
CREATE INDEX IF NOT EXISTS idx_attempts_task_fence ON task_attempts(task_id, fence DESC);
"""


class OperationsStore:
    """Durable command inbox and task-attempt lease store.

    ``now`` returns a Unix timestamp. Injecting it makes lease expiry
    deterministic in tests and lets workers use a consistent clock source.
    ``id_factory`` receives a short entity prefix and returns a unique ID.
    """

    def __init__(
        self,
        database: str | Path,
        *,
        now: Callable[[], float] | None = None,
        id_factory: Callable[[str], str] | None = None,
        lease_seconds: float = 30.0,
        busy_timeout_ms: int = 5000,
    ) -> None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        if busy_timeout_ms < 0:
            raise ValueError("busy_timeout_ms must not be negative")
        self._now = now or time.time
        self._id_factory = id_factory or (lambda prefix: f"{prefix}_{uuid.uuid4().hex}")
        self.lease_seconds = float(lease_seconds)
        database_path = Path(database)
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(
            str(database_path),
            timeout=busy_timeout_ms / 1000,
            isolation_level=None,
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.executescript(_SCHEMA)

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> OperationsStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @contextmanager
    def _write_transaction(self) -> Iterator[sqlite3.Connection]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield self.connection
        except BaseException:
            self.connection.rollback()
            raise
        else:
            self.connection.commit()

    def accept_command(
        self,
        *,
        idempotency_key: str,
        kind: str,
        payload: Mapping[str, Any] | None = None,
    ) -> CommandAcceptance:
        """Accept a command once and return its stable command/task pair."""
        key = idempotency_key.strip()
        command_kind = kind.strip()
        if not key:
            raise ValueError("idempotency_key must not be empty")
        if not command_kind:
            raise ValueError("kind must not be empty")
        command_payload = dict(payload or {})
        payload_json = json.dumps(command_payload, sort_keys=True, separators=(",", ":"))
        now = self._timestamp()

        with self._write_transaction() as connection:
            row = connection.execute(
                "SELECT * FROM commands WHERE idempotency_key = ?", (key,)
            ).fetchone()
            if row is not None:
                if row["kind"] != command_kind or row["payload_json"] != payload_json:
                    raise IdempotencyConflictError(
                        f"idempotency key already belongs to command {row['id']}"
                    )
                task_row = connection.execute(
                    "SELECT * FROM tasks WHERE command_id = ?", (row["id"],)
                ).fetchone()
                assert task_row is not None
                return CommandAcceptance(self._command_from_row(row), self._task_from_row(task_row))

            command_id = self._new_id("cmd")
            task_id = self._new_id("task")
            connection.execute(
                "INSERT INTO commands(id, idempotency_key, kind, payload_json, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (command_id, key, command_kind, payload_json, now),
            )
            connection.execute(
                "INSERT INTO tasks(id, command_id, status, created_at, updated_at) "
                "VALUES (?, ?, 'queued', ?, ?)",
                (task_id, command_id, now, now),
            )
            command_row = connection.execute(
                "SELECT * FROM commands WHERE id = ?", (command_id,)
            ).fetchone()
            task_row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            assert command_row is not None and task_row is not None
            return CommandAcceptance(self._command_from_row(command_row), self._task_from_row(task_row))

    submit_command = accept_command

    def claim_task(
        self,
        owner_id: str,
        *,
        task_id: str | None = None,
        lease_seconds: float | None = None,
        allowed_kinds: Iterable[str] | None = None,
    ) -> Attempt:
        """Claim a queued task or reclaim one whose current lease expired."""
        owner = owner_id.strip()
        if not owner:
            raise ValueError("owner_id must not be empty")
        duration = self.lease_seconds if lease_seconds is None else float(lease_seconds)
        if duration <= 0:
            raise ValueError("lease_seconds must be positive")
        normalized_kinds = self._normalize_allowed_kinds(allowed_kinds)
        now = self._timestamp()

        with self._write_transaction() as connection:
            # Sample after BEGIN IMMEDIATE: waiting for the write lock must not
            # make a lease decision with a stale clock value.
            now = self._timestamp()
            if task_id is None:
                if normalized_kinds is None:
                    task_row = connection.execute(
                        "SELECT * FROM tasks WHERE status = 'queued' OR "
                        "(status = 'running' AND EXISTS ("
                        "SELECT 1 FROM task_attempts a WHERE a.task_id = tasks.id "
                        "AND a.fence = (SELECT MAX(fence) FROM task_attempts WHERE task_id = tasks.id) "
                        "AND a.status = 'running' AND a.leased_until <= ?)) "
                        "ORDER BY created_at, id LIMIT 1",
                        (now,),
                    ).fetchone()
                else:
                    if not normalized_kinds:
                        task_row = connection.execute(
                            "SELECT tasks.* FROM tasks "
                            "JOIN commands ON commands.id = tasks.command_id "
                            "WHERE 0"
                        ).fetchone()
                    else:
                        placeholders = ", ".join("?" for _ in normalized_kinds)
                        task_row = connection.execute(
                            "SELECT tasks.* FROM tasks "
                            "JOIN commands ON commands.id = tasks.command_id "
                            "WHERE (tasks.status = 'queued' OR "
                            "(tasks.status = 'running' AND EXISTS ("
                            "SELECT 1 FROM task_attempts a WHERE a.task_id = tasks.id "
                            "AND a.fence = (SELECT MAX(fence) FROM task_attempts WHERE task_id = tasks.id) "
                            "AND a.status = 'running' AND a.leased_until <= ?))) "
                            f"AND commands.kind IN ({placeholders}) "
                            "ORDER BY tasks.created_at, tasks.id LIMIT 1",
                            (now, *normalized_kinds),
                        ).fetchone()
            else:
                if normalized_kinds is None:
                    task_row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
                else:
                    if not normalized_kinds:
                        task_row = connection.execute(
                            "SELECT tasks.* FROM tasks "
                            "JOIN commands ON commands.id = tasks.command_id "
                            "WHERE 0 AND tasks.id = ?",
                            (task_id,),
                        ).fetchone()
                    else:
                        placeholders = ", ".join("?" for _ in normalized_kinds)
                        task_row = connection.execute(
                            "SELECT tasks.* FROM tasks "
                            "JOIN commands ON commands.id = tasks.command_id "
                            "WHERE tasks.id = ? "
                            f"AND commands.kind IN ({placeholders})",
                            (task_id, *normalized_kinds),
                        ).fetchone()
            if task_row is None:
                raise TaskNotClaimableError("no claimable task")
            if task_row["status"] in ("succeeded", "failed"):
                raise TaskNotClaimableError(f"task {task_row['id']} is terminal")

            latest = connection.execute(
                "SELECT * FROM task_attempts WHERE task_id = ? ORDER BY fence DESC LIMIT 1",
                (task_row["id"],),
            ).fetchone()
            if latest is not None:
                if latest["status"] == "running" and latest["leased_until"] > now:
                    raise TaskNotClaimableError(f"task {task_row['id']} is leased")
                if latest["status"] == "running":
                    connection.execute(
                        "UPDATE task_attempts SET status = 'reclaimed', finished_at = ?, "
                        "error = 'lease_expired' WHERE id = ?",
                        (now, latest["id"]),
                    )
                fence = int(latest["fence"]) + 1
            else:
                fence = 1

            attempt_id = self._new_id("attempt")
            lease_token = self._new_id("lease")
            connection.execute(
                "INSERT INTO task_attempts("
                "id, task_id, owner_id, lease_token, fence, status, leased_until, started_at) "
                "VALUES (?, ?, ?, ?, ?, 'running', ?, ?)",
                (attempt_id, task_row["id"], owner, lease_token, fence, now + duration, now),
            )
            connection.execute(
                "UPDATE tasks SET status = 'running', updated_at = ? WHERE id = ?",
                (now, task_row["id"]),
            )
            row = connection.execute("SELECT * FROM task_attempts WHERE id = ?", (attempt_id,)).fetchone()
            assert row is not None
            return self._attempt_from_row(row)

    def claim_attempt(
        self,
        owner_id: str,
        *,
        task_id: str | None = None,
        lease_seconds: float | None = None,
        allowed_kinds: Iterable[str] | None = None,
    ) -> Attempt:
        """Alias with terminology matching the task-ledger architecture."""
        return self.claim_task(
            owner_id,
            task_id=task_id,
            lease_seconds=lease_seconds,
            allowed_kinds=allowed_kinds,
        )

    @staticmethod
    def _normalize_allowed_kinds(allowed_kinds: Iterable[str] | None) -> tuple[str, ...] | None:
        if allowed_kinds is None:
            return None
        if isinstance(allowed_kinds, str):
            raise ValueError("allowed_kinds must be an iterable of strings, not a single string")
        normalized: list[str] = []
        seen: set[str] = set()
        for kind in allowed_kinds:
            if not isinstance(kind, str):
                raise ValueError("allowed_kinds values must be strings")
            normalized_kind = kind.strip()
            if not normalized_kind:
                raise ValueError("allowed_kinds values must not be blank")
            if normalized_kind not in seen:
                seen.add(normalized_kind)
                normalized.append(normalized_kind)
        return tuple(normalized)

    def renew_attempt(
        self,
        attempt_id: str,
        owner_id: str,
        lease_token: str,
        fence: int,
        *,
        lease_seconds: float | None = None,
    ) -> Attempt:
        """Extend a still-valid lease while preserving its fence."""
        duration = self.lease_seconds if lease_seconds is None else float(lease_seconds)
        if duration <= 0:
            raise ValueError("lease_seconds must be positive")
        with self._write_transaction() as connection:
            now = self._timestamp()
            row = self._current_attempt(connection, attempt_id)
            self._assert_fence(row, owner_id, lease_token, fence, now)
            connection.execute(
                "UPDATE task_attempts SET leased_until = ? WHERE id = ?",
                (now + duration, attempt_id),
            )
            updated = connection.execute("SELECT * FROM task_attempts WHERE id = ?", (attempt_id,)).fetchone()
            assert updated is not None
            return self._attempt_from_row(updated)

    def succeed_attempt(
        self, attempt_id: str, owner_id: str, lease_token: str, fence: int
    ) -> Attempt:
        return self._finish_attempt(attempt_id, owner_id, lease_token, fence, "succeeded", None)

    def fail_attempt(
        self, attempt_id: str, owner_id: str, lease_token: str, fence: int, error: str
    ) -> Attempt:
        message = error.strip()
        if not message:
            raise ValueError("error must not be empty")
        return self._finish_attempt(attempt_id, owner_id, lease_token, fence, "failed", message)

    def _finish_attempt(
        self,
        attempt_id: str,
        owner_id: str,
        lease_token: str,
        fence: int,
        status: str,
        error: str | None,
    ) -> Attempt:
        with self._write_transaction() as connection:
            now = self._timestamp()
            row = self._current_attempt(connection, attempt_id)
            self._assert_fence(row, owner_id, lease_token, fence, now)
            task_id = row["task_id"]
            connection.execute(
                "UPDATE task_attempts SET status = ?, finished_at = ?, error = ?, leased_until = ? "
                "WHERE id = ?",
                (status, now, error, now, attempt_id),
            )
            connection.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, task_id),
            )
            finished = connection.execute(
                "SELECT * FROM task_attempts WHERE id = ?", (attempt_id,)
            ).fetchone()
            assert finished is not None
            return self._attempt_from_row(finished)

    def get_command(self, command_id: str) -> Command | None:
        row = self.connection.execute("SELECT * FROM commands WHERE id = ?", (command_id,)).fetchone()
        return None if row is None else self._command_from_row(row)

    def get_task(self, task_id: str) -> Task | None:
        row = self.connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return None if row is None else self._task_from_row(row)

    def get_attempt(self, attempt_id: str) -> Attempt | None:
        row = self.connection.execute("SELECT * FROM task_attempts WHERE id = ?", (attempt_id,)).fetchone()
        return None if row is None else self._attempt_from_row(row)

    def _current_attempt(self, connection: sqlite3.Connection, attempt_id: str) -> sqlite3.Row:
        row = connection.execute("SELECT * FROM task_attempts WHERE id = ?", (attempt_id,)).fetchone()
        if row is None:
            raise LeaseLostError(f"attempt {attempt_id} does not exist")
        latest = connection.execute(
            "SELECT id FROM task_attempts WHERE task_id = ? ORDER BY fence DESC LIMIT 1",
            (row["task_id"],),
        ).fetchone()
        if latest is None or latest["id"] != attempt_id:
            raise LeaseLostError(f"attempt {attempt_id} is no longer current")
        return row

    @staticmethod
    def _assert_fence(
        row: sqlite3.Row,
        owner_id: str,
        lease_token: str,
        fence: int,
        now: float,
    ) -> None:
        if (
            row["status"] != "running"
            or row["owner_id"] != owner_id
            or row["lease_token"] != lease_token
            or int(row["fence"]) != int(fence)
            or row["leased_until"] <= now
        ):
            raise LeaseLostError(f"attempt {row['id']} fence is no longer valid")

    def _timestamp(self) -> float:
        value = self._now()
        return float(value.timestamp() if hasattr(value, "timestamp") else value)

    def _new_id(self, prefix: str) -> str:
        value = self._id_factory(prefix)
        if not value:
            raise ValueError("id_factory must return non-empty IDs")
        return str(value)

    @staticmethod
    def _command_from_row(row: sqlite3.Row) -> Command:
        return Command(
            id=row["id"],
            idempotency_key=row["idempotency_key"],
            kind=row["kind"],
            payload=json.loads(row["payload_json"]),
            created_at=float(row["created_at"]),
        )

    @staticmethod
    def _task_from_row(row: sqlite3.Row) -> Task:
        return Task(
            id=row["id"],
            command_id=row["command_id"],
            status=row["status"],
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
        )

    @staticmethod
    def _attempt_from_row(row: sqlite3.Row) -> Attempt:
        return Attempt(
            id=row["id"],
            task_id=row["task_id"],
            owner_id=row["owner_id"],
            lease_token=row["lease_token"],
            fence=int(row["fence"]),
            status=row["status"],
            leased_until=float(row["leased_until"]),
            started_at=float(row["started_at"]),
            finished_at=None if row["finished_at"] is None else float(row["finished_at"]),
            error=row["error"],
        )


__all__ = [
    "Attempt",
    "Command",
    "CommandAcceptance",
    "IdempotencyConflictError",
    "LeaseLostError",
    "OperationsStore",
    "OperationsStoreError",
    "Task",
    "TaskNotClaimableError",
]
