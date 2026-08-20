"""Durable read-only projection of Paper runtime state.

PaperRuntimeStore is deliberately separate from execution facts.  It stores a
rebuildable account-scoped projection and never writes orders, fills, or ledger
records.
"""

from __future__ import annotations

import json
import math
import sqlite3
import time
import types
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import Any, Iterator

# normalize_account_id removed in V2 commandization


PAPER_RUNTIME_STATUSES = frozenset(
    {"starting", "running", "stopping", "stopped", "failed", "reconciliation_required"}
)
_RUNTIME_TABLE = "paper_runtime"


class PaperRuntimeValidationError(ValueError):
    """Raised when a Paper runtime projection value is invalid."""


class PaperRuntimeConflictError(RuntimeError):
    """Raised when a create or compare-and-swap update cannot be applied."""


@dataclass(frozen=True)
class PaperRuntimeRecord:
    """An immutable snapshot of one account's Paper runtime projection."""

    account_id: str
    run_id: str
    status: str
    config: Mapping[str, Any]
    owner_id: str
    ownership_fence: str
    last_task_id: str | None
    error: str | None
    version: int
    updated_at: float


_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {_RUNTIME_TABLE} (
    account_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('starting', 'running', 'stopping', 'stopped', 'failed', 'reconciliation_required')),
    config_json TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    ownership_fence TEXT NOT NULL,
    last_task_id TEXT,
    error TEXT,
    version INTEGER NOT NULL CHECK (version > 0),
    updated_at REAL NOT NULL
)
"""


class PaperRuntimeStore:
    """Short-connection SQLite store for the Paper runtime read model."""

    def __init__(
        self,
        database: str | Path,
        *,
        now: Any = time.time,
        busy_timeout_ms: int = 5000,
    ) -> None:
        if isinstance(busy_timeout_ms, bool) or not isinstance(busy_timeout_ms, int) or busy_timeout_ms < 0:
            raise ValueError("busy_timeout_ms must be a non-negative integer")
        if not isinstance(database, (str, PathLike)):
            raise ValueError("database path is required")
        database_text = str(database)
        if not database_text.strip() or database_text == ":memory:":
            raise ValueError("database must be a filesystem path")
        self.database = Path(database_text)
        if self.database.exists() and not self.database.is_file():
            raise ValueError("database path must be a file")
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._now = now
        self._busy_timeout_ms = busy_timeout_ms
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            str(self.database),
            timeout=self._busy_timeout_ms / 1000,
            isolation_level=None,
        )
        try:
            connection.row_factory = sqlite3.Row
            connection.execute(f"PRAGMA busy_timeout={self._busy_timeout_ms}")
            connection.execute("PRAGMA journal_mode=WAL")
            return connection
        except BaseException:
            connection.close()
            raise

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(_SCHEMA)
            except BaseException:
                connection.rollback()
                raise
            else:
                connection.commit()

    def get(self, account_id: str) -> PaperRuntimeRecord | None:
        account = self._account_id(account_id)
        with self._connection() as connection:
            row = connection.execute(
                f"SELECT * FROM {_RUNTIME_TABLE} WHERE account_id = ?", (account,)
            ).fetchone()
        return None if row is None else self._record_from_row(row)

    def list(self) -> list[PaperRuntimeRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM {_RUNTIME_TABLE} ORDER BY account_id"
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def create(
        self,
        *,
        account_id: str,
        run_id: str,
        status: str,
        config: Mapping[str, Any],
        owner_id: str,
        ownership_fence: str,
        last_task_id: str | None = None,
        error: str | None = None,
    ) -> PaperRuntimeRecord:
        account = self._account_id(account_id)
        run = self._required_text(run_id, "run_id")
        state = self._status(status)
        config_json = self._config_json(config)
        owner = self._required_text(owner_id, "owner_id")
        fence = self._required_text(ownership_fence, "ownership_fence")
        task = self._optional_text(last_task_id, "last_task_id")
        failure = self._optional_text(error, "error")
        updated_at = self._timestamp()

        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    f"SELECT 1 FROM {_RUNTIME_TABLE} WHERE account_id = ?", (account,)
                ).fetchone()
                if existing is not None:
                    raise PaperRuntimeConflictError(f"Paper runtime already exists: {account}")
                connection.execute(
                    f"INSERT INTO {_RUNTIME_TABLE} "
                    "(account_id, run_id, status, config_json, owner_id, ownership_fence, "
                    "last_task_id, error, version, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (account, run, state, config_json, owner, fence, task, failure, 1, updated_at),
                )
                row = connection.execute(
                    f"SELECT * FROM {_RUNTIME_TABLE} WHERE account_id = ?", (account,)
                ).fetchone()
                assert row is not None
            except BaseException:
                connection.rollback()
                raise
            else:
                connection.commit()
        return self._record_from_row(row)

    def update(
        self,
        account_id: str,
        expected_version: int,
        expected_ownership_fence: str | None = None,
        changed: Mapping[str, Any] | None = None,
        **changed_fields: Any,
    ) -> PaperRuntimeRecord:
        """Apply a compare-and-swap update and increment the projection version.
        
        If expected_ownership_fence is provided, the WHERE clause will include it
        to prevent stale owner writes after lease reclaim.
        """
        account = self._account_id(account_id)
        if isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 1:
            raise PaperRuntimeValidationError("expected_version must be a positive integer")
        if changed is not None and not isinstance(changed, Mapping):
            raise PaperRuntimeValidationError("changed fields must be an object")
        updates = dict(changed or {})
        overlap = set(updates).intersection(changed_fields)
        if overlap:
            raise PaperRuntimeValidationError(f"duplicate changed field: {next(iter(overlap))}")
        updates.update(changed_fields)
        allowed = {"run_id", "status", "config", "owner_id", "ownership_fence", "last_task_id", "error"}
        unknown = set(updates) - allowed
        if unknown:
            raise PaperRuntimeValidationError(f"unsupported changed field: {next(iter(unknown))}")
        if not updates:
            raise PaperRuntimeValidationError("at least one changed field is required")

        normalized: dict[str, Any] = {}
        for field, value in updates.items():
            if field == "status":
                normalized[field] = self._status(value)
            elif field == "config":
                normalized["config_json"] = self._config_json(value)
            elif field in {"run_id", "owner_id", "ownership_fence"}:
                normalized[field] = self._required_text(value, field)
            else:
                normalized[field] = self._optional_text(value, field)

        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                current = connection.execute(
                    f"SELECT * FROM {_RUNTIME_TABLE} WHERE account_id = ?", (account,)
                ).fetchone()
                if current is None or current["version"] != expected_version:
                    raise PaperRuntimeConflictError(
                        f"Paper runtime version conflict: {account} expected {expected_version}"
                    )
                assignments = [f"{field} = ?" for field in normalized]
                values = list(normalized.values())
                assignments.extend(("version = version + 1", "updated_at = ?"))
                values.append(self._timestamp())
                where_clause = "WHERE account_id = ? AND version = ?"
                where_values = [account, expected_version]
                # Include ownership_fence in WHERE if caller provides expected value
                if expected_ownership_fence is not None:
                    where_clause += " AND ownership_fence = ?"
                    where_values.append(expected_ownership_fence)
                values.extend(where_values)
                result = connection.execute(
                    f"UPDATE {_RUNTIME_TABLE} SET {', '.join(assignments)} {where_clause}",
                    values,
                )
                if result.rowcount != 1:
                    raise PaperRuntimeConflictError(
                        f"Paper runtime version conflict: {account} expected {expected_version}"
                    )
                row = connection.execute(
                    f"SELECT * FROM {_RUNTIME_TABLE} WHERE account_id = ?", (account,)
                ).fetchone()
                assert row is not None
            except BaseException:
                connection.rollback()
                raise
            else:
                connection.commit()
        return self._record_from_row(row)

    def _timestamp(self) -> float:
        value = self._now()
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise PaperRuntimeValidationError("updated_at must be a finite number")
        return float(value)

    @staticmethod
    def _account_id(value: str) -> str:
        """Validate and normalize account_id."""
        if not isinstance(value, str) or not value.strip():
            raise PaperRuntimeValidationError("account_id must be a non-empty string")
        normalized = value.strip()
        if "/" in normalized or "\\" in normalized or normalized.startswith("."):
            raise PaperRuntimeValidationError("account_id contains invalid path characters")
        return normalized

    @staticmethod
    def _required_text(value: Any, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise PaperRuntimeValidationError(f"{field} must be a non-empty string")
        return value.strip()

    @classmethod
    def _optional_text(cls, value: Any, field: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise PaperRuntimeValidationError(f"{field} must be a string or null")
        return value

    @staticmethod
    def _status(value: Any) -> str:
        if not isinstance(value, str) or value not in PAPER_RUNTIME_STATUSES:
            raise PaperRuntimeValidationError(
                f"status must be one of: {', '.join(sorted(PAPER_RUNTIME_STATUSES))}"
            )
        return value

    @staticmethod
    def _config_json(value: Any) -> str:
        if not isinstance(value, Mapping):
            raise PaperRuntimeValidationError("config must be a JSON object")

        def validate_json(item: Any, path: str) -> Any:
            if item is None or isinstance(item, (str, bool, int)):
                return item
            if isinstance(item, float):
                if not math.isfinite(item):
                    raise PaperRuntimeValidationError("config must contain only valid JSON data")
                return item
            if isinstance(item, Mapping):
                result: dict[str, Any] = {}
                for key, child in item.items():
                    if not isinstance(key, str):
                        raise PaperRuntimeValidationError(f"config key at {path} must be a string")
                    result[key] = validate_json(child, f"{path}.{key}")
                return result
            if isinstance(item, list):
                return [validate_json(child, f"{path}[]") for child in item]
            raise PaperRuntimeValidationError("config must contain only valid JSON data")

        normalized = validate_json(value, "config")
        try:
            encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            decoded = json.loads(encoded)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise PaperRuntimeValidationError("config must contain only valid JSON data") from exc
        if not isinstance(decoded, dict):
            raise PaperRuntimeValidationError("config must be a JSON object")
        return encoded

    @classmethod
    def _record_from_row(cls, row: sqlite3.Row) -> PaperRuntimeRecord:
        encoded_config = row["config_json"]
        if not isinstance(encoded_config, str):
            raise PaperRuntimeValidationError("stored config must be text")
        try:
            config = json.loads(encoded_config)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise PaperRuntimeValidationError("stored config is invalid JSON") from exc
        if not isinstance(config, dict):
            raise PaperRuntimeValidationError("stored config must be a JSON object")
        # Strict validation: reject NaN/Infinity in stored config
        try:
            json.dumps(config, allow_nan=False)
        except ValueError as exc:
            raise PaperRuntimeValidationError("stored config contains NaN or Infinity") from exc
        account = cls._account_id(row["account_id"])
        run = cls._required_text(row["run_id"], "run_id")
        status = cls._status(row["status"])
        owner = cls._required_text(row["owner_id"], "owner_id")
        fence = cls._required_text(row["ownership_fence"], "ownership_fence")
        task = cls._optional_text(row["last_task_id"], "last_task_id")
        error = cls._optional_text(row["error"], "error")
        version = row["version"]
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise PaperRuntimeValidationError("stored version must be a positive integer")
        updated_at = row["updated_at"]
        if isinstance(updated_at, bool) or not isinstance(updated_at, (int, float)) or not math.isfinite(float(updated_at)):
            raise PaperRuntimeValidationError("stored updated_at must be a finite number")
        return PaperRuntimeRecord(
            account_id=account,
            run_id=run,
            status=status,
            config=types.MappingProxyType(config),
            owner_id=owner,
            ownership_fence=fence,
            last_task_id=task,
            error=error,
            version=version,
            updated_at=float(updated_at),
        )


__all__ = [
    "PAPER_RUNTIME_STATUSES",
    "PaperRuntimeConflictError",
    "PaperRuntimeRecord",
    "PaperRuntimeStore",
    "PaperRuntimeValidationError",
]
