"""Immutable research and execution qualification facts for V2 Phase 3.

The repository is intentionally small and SQLite-native. Facts are append-only:
reusing an identifier with different content is rejected, and execution runs
validate every referenced hash again immediately before authorization.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from engine.execution_protocol import Environment
from utils.db import get_connection


class ResearchFactError(ValueError):
    """Base error for invalid or incomplete frozen facts."""


class FactConflictError(ResearchFactError):
    """Raised when an immutable identifier is reused with changed content."""


class ExecutionRunBlockedError(ResearchFactError):
    """Raised when a run cannot be created or authorized fail-closed."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _dt(value: datetime | str, field: str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ResearchFactError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchFactError(f"{field} must be non-empty")
    return value.strip()


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Mapping):
        return {str(k): _json_value(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_value(item) for item in value]
    if hasattr(value, "value"):
        return _json_value(value.value)
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(_json_value(value), ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS research_scope_snapshots (
            scope_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            environment TEXT NOT NULL CHECK (environment = 'paper'),
            kind TEXT NOT NULL,
            members_json TEXT NOT NULL,
            weights_json TEXT,
            market_context_json TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            content_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS research_data_snapshots (
            data_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            environment TEXT NOT NULL CHECK (environment = 'paper'),
            data_version TEXT NOT NULL,
            time_range_start TEXT NOT NULL,
            time_range_end TEXT NOT NULL,
            instruments_json TEXT NOT NULL,
            row_count INTEGER NOT NULL CHECK (row_count >= 0),
            checksum TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            freshness_seconds INTEGER NOT NULL CHECK (freshness_seconds > 0),
            content_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS research_strategy_versions (
            strategy_version_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            environment TEXT NOT NULL CHECK (environment = 'paper'),
            strategy_id TEXT NOT NULL,
            version_hash TEXT NOT NULL,
            code_snapshot TEXT NOT NULL,
            parameters_json TEXT NOT NULL,
            dependencies_json TEXT NOT NULL,
            authority TEXT NOT NULL CHECK (authority IN ('human', 'deterministic')),
            ai_only INTEGER NOT NULL CHECK (ai_only IN (0, 1)),
            captured_at TEXT NOT NULL,
            content_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            UNIQUE (strategy_id, version_hash, workspace_id, account_id, environment)
        );
        CREATE TABLE IF NOT EXISTS research_validation_runs (
            validation_run_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            environment TEXT NOT NULL CHECK (environment = 'paper'),
            scope_snapshot_id TEXT NOT NULL REFERENCES research_scope_snapshots(scope_id),
            scope_hash TEXT NOT NULL,
            data_snapshot_id TEXT NOT NULL REFERENCES research_data_snapshots(data_id),
            data_hash TEXT NOT NULL,
            strategy_version_id TEXT NOT NULL REFERENCES research_strategy_versions(strategy_version_id),
            strategy_hash TEXT NOT NULL,
            metrics_json TEXT NOT NULL,
            mode TEXT NOT NULL CHECK (mode IN ('exploratory', 'executable')),
            completed_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            content_hash TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS research_qualifications (
            qualification_id TEXT PRIMARY KEY,
            validation_run_id TEXT NOT NULL REFERENCES research_validation_runs(validation_run_id),
            validation_hash TEXT NOT NULL,
            passed INTEGER NOT NULL CHECK (passed IN (0, 1)),
            reason TEXT NOT NULL,
            qualified_until TEXT NOT NULL,
            invalidated_at TEXT,
            invalidation_reason TEXT,
            created_at TEXT NOT NULL,
            content_hash TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS research_approvals (
            approval_id TEXT PRIMARY KEY,
            qualification_id TEXT NOT NULL REFERENCES research_qualifications(qualification_id),
            approved_by TEXT NOT NULL,
            authority TEXT NOT NULL CHECK (authority IN ('human', 'service')),
            approved_at TEXT NOT NULL,
            expires_at TEXT,
            comments TEXT NOT NULL,
            created_at TEXT NOT NULL,
            content_hash TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS execution_runs (
            execution_run_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            environment TEXT NOT NULL CHECK (environment = 'paper'),
            scope_snapshot_id TEXT NOT NULL,
            scope_hash TEXT NOT NULL,
            data_snapshot_id TEXT NOT NULL,
            data_hash TEXT NOT NULL,
            strategy_version_id TEXT NOT NULL,
            strategy_hash TEXT NOT NULL,
            validation_run_id TEXT NOT NULL,
            qualification_id TEXT NOT NULL,
            approval_id TEXT,
            risk_policy_version TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('created', 'ready', 'running', 'blocked', 'halted', 'completed')),
            created_at TEXT NOT NULL,
            content_hash TEXT NOT NULL UNIQUE,
            FOREIGN KEY (scope_snapshot_id) REFERENCES research_scope_snapshots(scope_id),
            FOREIGN KEY (data_snapshot_id) REFERENCES research_data_snapshots(data_id),
            FOREIGN KEY (strategy_version_id) REFERENCES research_strategy_versions(strategy_version_id),
            FOREIGN KEY (validation_run_id) REFERENCES research_validation_runs(validation_run_id),
            FOREIGN KEY (qualification_id) REFERENCES research_qualifications(qualification_id),
            FOREIGN KEY (approval_id) REFERENCES research_approvals(approval_id)
        );
        CREATE TABLE IF NOT EXISTS research_audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            aggregate_type TEXT NOT NULL,
            aggregate_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_execution_runs_account ON execution_runs(workspace_id, account_id, environment);
        CREATE INDEX IF NOT EXISTS idx_research_audit_aggregate ON research_audit_events(aggregate_type, aggregate_id);
        """
    )


@dataclass(frozen=True, slots=True)
class ScopeSnapshot:
    scope_id: str
    workspace_id: str
    account_id: str
    environment: Environment
    kind: str
    members: tuple[str, ...]
    weights: tuple[float, ...] | None
    market_context: Mapping[str, Any]
    captured_at: datetime
    content_hash: str

    @classmethod
    def create(
        cls,
        scope_id: str,
        kind: str,
        members: list[str] | tuple[str, ...],
        *,
        workspace_id: str = "default",
        account_id: str = "*",
        environment: Environment | str = Environment.PAPER,
        weights: list[float] | tuple[float, ...] | None = None,
        market_context: Mapping[str, Any] | str | None = None,
        captured_at: datetime | None = None,
    ) -> "ScopeSnapshot":
        env = Environment(str(environment).lower()) if not isinstance(environment, Environment) else environment
        if env is not Environment.PAPER:
            raise ExecutionRunBlockedError("Live research snapshots are disabled in V2")
        scope_id, workspace_id, account_id, kind = (_text(scope_id, "scope_id"), _text(workspace_id, "workspace_id"), _text(account_id, "account_id"), _text(kind, "kind"))
        members_tuple = tuple(_text(member, "member") for member in members)
        if not members_tuple:
            raise ResearchFactError("members must not be empty")
        weights_tuple = tuple(float(item) for item in weights) if weights is not None else None
        if weights_tuple is not None and (len(weights_tuple) != len(members_tuple) or any(item < 0 for item in weights_tuple)):
            raise ResearchFactError("weights must match members and be non-negative")
        captured = _dt(captured_at or _utc_now(), "captured_at")
        context = {"value": market_context} if isinstance(market_context, str) else dict(market_context or {})
        hashed = content_hash({"scope_id": scope_id, "workspace_id": workspace_id, "account_id": account_id, "environment": env.value, "kind": kind, "members": members_tuple, "weights": weights_tuple, "market_context": context})
        return cls(scope_id, workspace_id, account_id, env, kind, members_tuple, weights_tuple, context, captured, hashed)


@dataclass(frozen=True, slots=True)
class DataSnapshot:
    data_id: str
    workspace_id: str
    account_id: str
    environment: Environment
    data_version: str
    time_range_start: datetime
    time_range_end: datetime
    instruments: tuple[str, ...]
    row_count: int
    checksum: str
    captured_at: datetime
    freshness_seconds: int
    content_hash: str

    @classmethod
    def create(
        cls,
        data_id: str,
        data_version: str,
        time_range_start: datetime,
        time_range_end: datetime,
        instruments: list[str] | tuple[str, ...],
        row_count: int,
        checksum: str,
        *,
        workspace_id: str = "default",
        account_id: str = "*",
        environment: Environment | str = Environment.PAPER,
        captured_at: datetime | None = None,
        freshness_seconds: int = 86400,
    ) -> "DataSnapshot":
        env = Environment(str(environment).lower()) if not isinstance(environment, Environment) else environment
        if env is not Environment.PAPER:
            raise ExecutionRunBlockedError("Live data snapshots are disabled in V2")
        data_id, workspace_id, account_id = _text(data_id, "data_id"), _text(workspace_id, "workspace_id"), _text(account_id, "account_id")
        instruments_tuple = tuple(_text(item, "instrument") for item in instruments)
        if not instruments_tuple or row_count < 0 or freshness_seconds <= 0:
            raise ResearchFactError("invalid data snapshot coverage or freshness")
        start, end, captured = _dt(time_range_start, "time_range_start"), _dt(time_range_end, "time_range_end"), _dt(captured_at or _utc_now(), "captured_at")
        data_version, checksum = _text(data_version, "data_version"), _text(checksum, "checksum")
        hashed = content_hash({"data_id": data_id, "workspace_id": workspace_id, "account_id": account_id, "environment": env.value, "data_version": data_version, "time_range_start": start, "time_range_end": end, "instruments": instruments_tuple, "row_count": row_count, "checksum": checksum})
        return cls(data_id, workspace_id, account_id, env, data_version, start, end, instruments_tuple, int(row_count), checksum, captured, int(freshness_seconds), hashed)

    def is_fresh(self, now: datetime | None = None) -> bool:
        current = _dt(now or _utc_now(), "now")
        age = (current - self.captured_at).total_seconds()
        return 0 <= age <= self.freshness_seconds


@dataclass(frozen=True, slots=True)
class StrategyVersion:
    strategy_version_id: str
    workspace_id: str
    account_id: str
    environment: Environment
    strategy_id: str
    version_hash: str
    code_snapshot: str
    parameters: Mapping[str, Any]
    dependencies: tuple[str, ...]
    authority: str
    ai_only: bool
    captured_at: datetime
    content_hash: str

    @classmethod
    def create(
        cls,
        strategy_id: str,
        code_snapshot: str,
        parameters: Mapping[str, Any] | None = None,
        dependencies: list[str] | tuple[str, ...] = (),
        *,
        strategy_version_id: str | None = None,
        workspace_id: str = "default",
        account_id: str = "*",
        environment: Environment | str = Environment.PAPER,
        authority: str = "human",
        ai_only: bool = False,
        captured_at: datetime | None = None,
    ) -> "StrategyVersion":
        env = Environment(str(environment).lower()) if not isinstance(environment, Environment) else environment
        if env is not Environment.PAPER:
            raise ExecutionRunBlockedError("Live strategy versions are disabled in V2")
        strategy_id, workspace_id, account_id = _text(strategy_id, "strategy_id"), _text(workspace_id, "workspace_id"), _text(account_id, "account_id")
        code_snapshot = _text(code_snapshot, "code_snapshot")
        if authority not in {"human", "deterministic"}:
            raise ResearchFactError("unsupported strategy authority")
        params = dict(parameters or {})
        deps = tuple(_text(item, "dependency") for item in dependencies)
        captured = _dt(captured_at or _utc_now(), "captured_at")
        hashed = content_hash({"strategy_id": strategy_id, "workspace_id": workspace_id, "account_id": account_id, "environment": env.value, "code_snapshot": code_snapshot, "parameters": params, "dependencies": deps, "authority": authority, "ai_only": bool(ai_only)})
        version_hash = hashed[:16]
        version_id = strategy_version_id or f"{strategy_id}:{version_hash}"
        return cls(version_id, workspace_id, account_id, env, strategy_id, version_hash, code_snapshot, params, deps, authority, bool(ai_only), captured, hashed)


@dataclass(frozen=True, slots=True)
class ValidationRun:
    validation_run_id: str
    workspace_id: str
    account_id: str
    environment: Environment
    scope_snapshot_id: str
    scope_hash: str
    data_snapshot_id: str
    data_hash: str
    strategy_version_id: str
    strategy_hash: str
    metrics: Mapping[str, Any]
    mode: str
    completed_at: datetime
    content_hash: str

    @classmethod
    def create(
        cls,
        validation_run_id: str,
        *,
        scope: ScopeSnapshot,
        data: DataSnapshot,
        strategy: StrategyVersion,
        metrics: Mapping[str, Any] | None = None,
        mode: str = "executable",
        completed_at: datetime | None = None,
    ) -> "ValidationRun":
        if mode not in {"exploratory", "executable"}:
            raise ResearchFactError("mode must be exploratory or executable")
        if not (scope.environment is data.environment is strategy.environment is Environment.PAPER):
            raise ExecutionRunBlockedError("validation environment must be paper")
        if (scope.workspace_id, data.workspace_id, strategy.workspace_id) != (scope.workspace_id,) * 3:
            raise ExecutionRunBlockedError("frozen references must share workspace")
        if scope.account_id not in {"*", strategy.account_id} and strategy.account_id != "*":
            raise ExecutionRunBlockedError("frozen references cross account boundary")
        completed = _dt(completed_at or _utc_now(), "completed_at")
        hashed = content_hash({"validation_run_id": validation_run_id, "workspace_id": scope.workspace_id, "account_id": strategy.account_id, "environment": "paper", "scope_id": scope.scope_id, "scope_hash": scope.content_hash, "data_id": data.data_id, "data_hash": data.content_hash, "strategy_id": strategy.strategy_version_id, "strategy_hash": strategy.content_hash, "metrics": dict(metrics or {}), "mode": mode, "completed_at": completed})
        return cls(_text(validation_run_id, "validation_run_id"), scope.workspace_id, strategy.account_id, Environment.PAPER, scope.scope_id, scope.content_hash, data.data_id, data.content_hash, strategy.strategy_version_id, strategy.content_hash, dict(metrics or {}), mode, completed, hashed)


@dataclass(frozen=True, slots=True)
class Qualification:
    qualification_id: str
    validation_run_id: str
    validation_hash: str
    passed: bool
    reason: str
    qualified_until: datetime
    content_hash: str

    @classmethod
    def create(cls, qualification_id: str, *, validation: ValidationRun, passed: bool, reason: str = "", qualified_until: datetime | None = None) -> "Qualification":
        until = _dt(qualified_until or (_utc_now() + timedelta(days=30) if passed else _utc_now()), "qualified_until")
        hashed = content_hash({"qualification_id": qualification_id, "validation_run_id": validation.validation_run_id, "validation_hash": validation.content_hash, "passed": bool(passed), "reason": reason, "qualified_until": until})
        return cls(_text(qualification_id, "qualification_id"), validation.validation_run_id, validation.content_hash, bool(passed), reason, until, hashed)

    def is_valid(self, now: datetime | None = None) -> bool:
        return self.passed and self.qualified_until > _dt(now or _utc_now(), "now")


@dataclass(frozen=True, slots=True)
class Approval:
    approval_id: str
    qualification_id: str
    approved_by: str
    authority: str
    approved_at: datetime
    expires_at: datetime | None
    comments: str
    content_hash: str

    @classmethod
    def create(cls, approval_id: str, *, qualification_id: str, approved_by: str, authority: str = "human", approved_at: datetime | None = None, expires_at: datetime | None = None, comments: str = "") -> "Approval":
        if authority not in {"human", "service"}:
            raise ResearchFactError("unsupported approval authority")
        approved = _dt(approved_at or _utc_now(), "approved_at")
        expires = _dt(expires_at, "expires_at") if expires_at else None
        hashed = content_hash({"approval_id": approval_id, "qualification_id": qualification_id, "approved_by": approved_by, "authority": authority, "approved_at": approved, "expires_at": expires, "comments": comments})
        return cls(_text(approval_id, "approval_id"), _text(qualification_id, "qualification_id"), _text(approved_by, "approved_by"), authority, approved, expires, comments, hashed)

    def is_valid(self, now: datetime | None = None) -> bool:
        current = _dt(now or _utc_now(), "now")
        return self.expires_at is None or self.expires_at > current


@dataclass(frozen=True, slots=True)
class ExecutionRun:
    execution_run_id: str
    workspace_id: str
    account_id: str
    environment: Environment
    scope_snapshot_id: str
    scope_hash: str
    data_snapshot_id: str
    data_hash: str
    strategy_version_id: str
    strategy_hash: str
    validation_run_id: str
    qualification_id: str
    approval_id: str | None
    risk_policy_version: str
    status: str
    created_at: datetime
    content_hash: str


def _audit(connection: sqlite3.Connection, aggregate_type: str, aggregate_id: str, event_type: str, payload: Mapping[str, Any]) -> None:
    connection.execute("INSERT INTO research_audit_events(aggregate_type, aggregate_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)", (aggregate_type, aggregate_id, event_type, canonical_json(payload), _utc_now().isoformat()))


class ResearchFactsStore:
    """SQLite repository for immutable research, qualification and run facts."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        with get_connection(self.db_path) as connection:
            _schema(connection)
            connection.commit()

    def _insert_fact(self, table: str, key_column: str, key: str, values: Mapping[str, Any], expected_hash: str, aggregate_type: str) -> None:
        with get_connection(self.db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(f"SELECT content_hash FROM {table} WHERE {key_column} = ?", (key,)).fetchone()
            if row:
                if row["content_hash"] != expected_hash:
                    connection.rollback()
                    raise FactConflictError(f"immutable fact changed: {table}/{key}")
                connection.commit()
                return
            columns = list(values)
            placeholders = ",".join("?" for _ in columns)
            connection.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})", tuple(values[column] for column in columns))
            _audit(connection, aggregate_type, key, "created", values)
            connection.commit()

    def save_scope(self, fact: ScopeSnapshot) -> ScopeSnapshot:
        self._insert_fact("research_scope_snapshots", "scope_id", fact.scope_id, {"scope_id": fact.scope_id, "workspace_id": fact.workspace_id, "account_id": fact.account_id, "environment": fact.environment.value, "kind": fact.kind, "members_json": canonical_json(fact.members), "weights_json": canonical_json(fact.weights) if fact.weights is not None else None, "market_context_json": canonical_json(fact.market_context), "captured_at": fact.captured_at.isoformat(), "content_hash": fact.content_hash, "created_at": _utc_now().isoformat()}, fact.content_hash, "ScopeSnapshot")
        return fact

    def save_data(self, fact: DataSnapshot) -> DataSnapshot:
        self._insert_fact("research_data_snapshots", "data_id", fact.data_id, {"data_id": fact.data_id, "workspace_id": fact.workspace_id, "account_id": fact.account_id, "environment": fact.environment.value, "data_version": fact.data_version, "time_range_start": fact.time_range_start.isoformat(), "time_range_end": fact.time_range_end.isoformat(), "instruments_json": canonical_json(fact.instruments), "row_count": fact.row_count, "checksum": fact.checksum, "captured_at": fact.captured_at.isoformat(), "freshness_seconds": fact.freshness_seconds, "content_hash": fact.content_hash, "created_at": _utc_now().isoformat()}, fact.content_hash, "DataSnapshot")
        return fact

    def save_strategy(self, fact: StrategyVersion) -> StrategyVersion:
        self._insert_fact("research_strategy_versions", "strategy_version_id", fact.strategy_version_id, {"strategy_version_id": fact.strategy_version_id, "workspace_id": fact.workspace_id, "account_id": fact.account_id, "environment": fact.environment.value, "strategy_id": fact.strategy_id, "version_hash": fact.version_hash, "code_snapshot": fact.code_snapshot, "parameters_json": canonical_json(fact.parameters), "dependencies_json": canonical_json(fact.dependencies), "authority": fact.authority, "ai_only": int(fact.ai_only), "captured_at": fact.captured_at.isoformat(), "content_hash": fact.content_hash, "created_at": _utc_now().isoformat()}, fact.content_hash, "StrategyVersion")
        return fact

    def save_validation(self, fact: ValidationRun) -> ValidationRun:
        self._insert_fact("research_validation_runs", "validation_run_id", fact.validation_run_id, {"validation_run_id": fact.validation_run_id, "workspace_id": fact.workspace_id, "account_id": fact.account_id, "environment": fact.environment.value, "scope_snapshot_id": fact.scope_snapshot_id, "scope_hash": fact.scope_hash, "data_snapshot_id": fact.data_snapshot_id, "data_hash": fact.data_hash, "strategy_version_id": fact.strategy_version_id, "strategy_hash": fact.strategy_hash, "metrics_json": canonical_json(fact.metrics), "mode": fact.mode, "completed_at": fact.completed_at.isoformat(), "created_at": _utc_now().isoformat(), "content_hash": fact.content_hash}, fact.content_hash, "ValidationRun")
        return fact

    def save_qualification(self, fact: Qualification) -> Qualification:
        self._insert_fact("research_qualifications", "qualification_id", fact.qualification_id, {"qualification_id": fact.qualification_id, "validation_run_id": fact.validation_run_id, "validation_hash": fact.validation_hash, "passed": int(fact.passed), "reason": fact.reason, "qualified_until": fact.qualified_until.isoformat(), "created_at": _utc_now().isoformat(), "content_hash": fact.content_hash}, fact.content_hash, "Qualification")
        return fact

    def save_approval(self, fact: Approval) -> Approval:
        self._insert_fact("research_approvals", "approval_id", fact.approval_id, {"approval_id": fact.approval_id, "qualification_id": fact.qualification_id, "approved_by": fact.approved_by, "authority": fact.authority, "approved_at": fact.approved_at.isoformat(), "expires_at": fact.expires_at.isoformat() if fact.expires_at else None, "comments": fact.comments, "created_at": _utc_now().isoformat(), "content_hash": fact.content_hash}, fact.content_hash, "Approval")
        return fact

    def create_execution_run(self, *, execution_run_id: str, workspace_id: str, account_id: str, environment: Environment | str, scope_snapshot_id: str, data_snapshot_id: str, strategy_version_id: str, validation_run_id: str, qualification_id: str, approval_id: str | None = None, risk_policy_version: str = "risk-v3", now: datetime | None = None, require_approval: bool = True) -> ExecutionRun:
        env = Environment(str(environment).lower()) if not isinstance(environment, Environment) else environment
        if env is not Environment.PAPER:
            raise ExecutionRunBlockedError("Live ExecutionRun creation is disabled in V2")
        current = _dt(now or _utc_now(), "now")
        workspace_id, account_id = _text(workspace_id, "workspace_id"), _text(account_id, "account_id")
        with get_connection(self.db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            scope = connection.execute("SELECT * FROM research_scope_snapshots WHERE scope_id = ?", (scope_snapshot_id,)).fetchone()
            data = connection.execute("SELECT * FROM research_data_snapshots WHERE data_id = ?", (data_snapshot_id,)).fetchone()
            strategy = connection.execute("SELECT * FROM research_strategy_versions WHERE strategy_version_id = ?", (strategy_version_id,)).fetchone()
            validation = connection.execute("SELECT * FROM research_validation_runs WHERE validation_run_id = ?", (validation_run_id,)).fetchone()
            qualification = connection.execute("SELECT * FROM research_qualifications WHERE qualification_id = ?", (qualification_id,)).fetchone()
            approval = connection.execute("SELECT * FROM research_approvals WHERE approval_id = ?", (approval_id,)).fetchone() if approval_id else None
            missing = [name for name, value in (("scope", scope), ("data", data), ("strategy", strategy), ("validation", validation), ("qualification", qualification)) if value is None]
            if missing:
                connection.rollback()
                raise ExecutionRunBlockedError(f"missing frozen references: {', '.join(missing)}")
            if any(row["environment"] != "paper" for row in (scope, data, strategy, validation)) or scope["workspace_id"] != workspace_id or data["workspace_id"] != workspace_id or strategy["workspace_id"] != workspace_id or validation["workspace_id"] != workspace_id:
                connection.rollback()
                raise ExecutionRunBlockedError("frozen references cross workspace or environment boundary")
            if strategy["ai_only"] or strategy["authority"] not in {"human", "deterministic"}:
                connection.rollback()
                raise ExecutionRunBlockedError("AI-only strategy artifacts cannot authorize execution")
            actual_data_hash = content_hash({"data_id": data["data_id"], "workspace_id": data["workspace_id"], "account_id": data["account_id"], "environment": data["environment"], "data_version": data["data_version"], "time_range_start": data["time_range_start"], "time_range_end": data["time_range_end"], "instruments": json.loads(data["instruments_json"]), "row_count": data["row_count"], "checksum": data["checksum"]})
            if actual_data_hash != data["content_hash"]:
                connection.rollback()
                raise ExecutionRunBlockedError("data snapshot hash mismatch")
            if validation["scope_hash"] != scope["content_hash"] or validation["data_hash"] != data["content_hash"] or validation["strategy_hash"] != strategy["content_hash"]:
                connection.rollback()
                raise ExecutionRunBlockedError("validation references no longer match frozen hashes")
            if validation["scope_snapshot_id"] != scope_snapshot_id or validation["data_snapshot_id"] != data_snapshot_id or validation["strategy_version_id"] != strategy_version_id or validation["account_id"] not in {account_id, "*", strategy["account_id"]}:
                connection.rollback()
                raise ExecutionRunBlockedError("validation chain identity mismatch")
            captured = _dt(data["captured_at"], "data.captured_at")
            if (current - captured).total_seconds() < 0 or (current - captured).total_seconds() > data["freshness_seconds"]:
                connection.rollback()
                raise ExecutionRunBlockedError("data snapshot is stale")
            if not bool(qualification["passed"]) or _dt(qualification["qualified_until"], "qualified_until") <= current or qualification["validation_run_id"] != validation_run_id or qualification["validation_hash"] != validation["content_hash"]:
                connection.rollback()
                raise ExecutionRunBlockedError("qualification is invalid or expired")
            if validation["mode"] != "executable":
                connection.rollback()
                raise ExecutionRunBlockedError("exploratory validation cannot authorize execution")
            if require_approval:
                if approval is None or approval["qualification_id"] != qualification_id or _dt(approval["approved_at"], "approved_at") > current or (approval["expires_at"] and _dt(approval["expires_at"], "approval.expires_at") <= current) or approval["authority"] != "human":
                    connection.rollback()
                    raise ExecutionRunBlockedError("valid human approval is required")
            run_hash = content_hash({"execution_run_id": execution_run_id, "workspace_id": workspace_id, "account_id": account_id, "environment": "paper", "scope_snapshot_id": scope_snapshot_id, "scope_hash": scope["content_hash"], "data_snapshot_id": data_snapshot_id, "data_hash": data["content_hash"], "strategy_version_id": strategy_version_id, "strategy_hash": strategy["content_hash"], "validation_run_id": validation_run_id, "qualification_id": qualification_id, "approval_id": approval_id, "risk_policy_version": risk_policy_version})
            existing = connection.execute("SELECT content_hash FROM execution_runs WHERE execution_run_id = ?", (execution_run_id,)).fetchone()
            if existing:
                if existing["content_hash"] != run_hash:
                    connection.rollback()
                    raise FactConflictError("execution run identifier reused with changed references")
                connection.commit()
                return self.get_execution_run(execution_run_id)
            connection.execute("INSERT INTO execution_runs(execution_run_id, workspace_id, account_id, environment, scope_snapshot_id, scope_hash, data_snapshot_id, data_hash, strategy_version_id, strategy_hash, validation_run_id, qualification_id, approval_id, risk_policy_version, status, created_at, content_hash) VALUES (?, ?, ?, 'paper', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready', ?, ?)", (execution_run_id, workspace_id, account_id, scope_snapshot_id, scope["content_hash"], data_snapshot_id, data["content_hash"], strategy_version_id, strategy["content_hash"], validation_run_id, qualification_id, approval_id, _text(risk_policy_version, "risk_policy_version"), current.isoformat(), run_hash))
            _audit(connection, "ExecutionRun", execution_run_id, "created", {"workspace_id": workspace_id, "account_id": account_id, "content_hash": run_hash})
            connection.commit()
        return self.get_execution_run(execution_run_id)

    def get_execution_run(self, execution_run_id: str) -> ExecutionRun | None:
        with get_connection(self.db_path) as connection:
            row = connection.execute("SELECT * FROM execution_runs WHERE execution_run_id = ?", (execution_run_id,)).fetchone()
        if row is None:
            return None
        return ExecutionRun(row["execution_run_id"], row["workspace_id"], row["account_id"], Environment.PAPER, row["scope_snapshot_id"], row["scope_hash"], row["data_snapshot_id"], row["data_hash"], row["strategy_version_id"], row["strategy_hash"], row["validation_run_id"], row["qualification_id"], row["approval_id"], row["risk_policy_version"], row["status"], _dt(row["created_at"], "created_at"), row["content_hash"])

    def validate_execution_run(self, execution_run_id: str, *, now: datetime | None = None) -> ExecutionRun:
        run = self.get_execution_run(execution_run_id)
        if run is None:
            raise ExecutionRunBlockedError(f"execution run not found: {execution_run_id}")
        with get_connection(self.db_path) as connection:
            scope = connection.execute("SELECT content_hash FROM research_scope_snapshots WHERE scope_id = ?", (run.scope_snapshot_id,)).fetchone()
            data = connection.execute("SELECT data_id, workspace_id, account_id, environment, data_version, time_range_start, time_range_end, instruments_json, row_count, checksum, content_hash, captured_at, freshness_seconds FROM research_data_snapshots WHERE data_id = ?", (run.data_snapshot_id,)).fetchone()
            strategy = connection.execute("SELECT content_hash, ai_only FROM research_strategy_versions WHERE strategy_version_id = ?", (run.strategy_version_id,)).fetchone()
            validation = connection.execute("SELECT content_hash, scope_hash, data_hash, strategy_hash, mode FROM research_validation_runs WHERE validation_run_id = ?", (run.validation_run_id,)).fetchone()
            qualification = connection.execute("SELECT * FROM research_qualifications WHERE qualification_id = ?", (run.qualification_id,)).fetchone()
            if not all((scope, data, strategy, validation, qualification)):
                raise ExecutionRunBlockedError("execution run frozen references are invalidated")
            actual_data_hash = content_hash({"data_id": data["data_id"], "workspace_id": data["workspace_id"], "account_id": data["account_id"], "environment": data["environment"], "data_version": data["data_version"], "time_range_start": data["time_range_start"], "time_range_end": data["time_range_end"], "instruments": json.loads(data["instruments_json"]), "row_count": data["row_count"], "checksum": data["checksum"]})
            if actual_data_hash != data["content_hash"]:
                raise ExecutionRunBlockedError("execution run data snapshot hash mismatch")
            if scope["content_hash"] != run.scope_hash or data["content_hash"] != run.data_hash or strategy["content_hash"] != run.strategy_hash or strategy["ai_only"] or validation["scope_hash"] != run.scope_hash or validation["data_hash"] != run.data_hash or validation["strategy_hash"] != run.strategy_hash or validation["mode"] != "executable" or qualification["validation_hash"] != validation["content_hash"] or not bool(qualification["passed"]):
                raise ExecutionRunBlockedError("execution run frozen references are invalidated")
            current = _dt(now or _utc_now(), "now")
            age = (current - _dt(data["captured_at"], "data.captured_at")).total_seconds()
            if age < 0 or age > data["freshness_seconds"] or _dt(qualification["qualified_until"], "qualified_until") <= current:
                raise ExecutionRunBlockedError("execution run data or qualification is stale")
        return run

    def ensure_paper_run(self, *, account_id: str, workspace_id: str = "default", strategy_id: str = "paper", codes: list[str] | tuple[str, ...] = (), initial_cash: float = 50000.0, execution_run_id: str | None = None) -> ExecutionRun:
        """Create or return a deterministic, auditable local paper run."""
        if execution_run_id:
            existing = self.get_execution_run(execution_run_id)
            if existing is not None:
                self.validate_execution_run(execution_run_id)
                return existing
        run_id = execution_run_id or f"paper-{account_id}-{uuid.uuid4().hex[:12]}"
        if execution_run_id is None:
            with get_connection(self.db_path) as connection:
                existing_row = connection.execute(
                    "SELECT execution_run_id FROM execution_runs WHERE workspace_id = ? AND account_id = ? AND environment = 'paper' ORDER BY created_at DESC LIMIT 1",
                    (workspace_id, account_id),
                ).fetchone()
            if existing_row is not None:
                existing_run = self.get_execution_run(existing_row["execution_run_id"])
                if existing_run is not None:
                    return self.validate_execution_run(existing_run.execution_run_id)
        now = _utc_now()
        scope = ScopeSnapshot.create(f"scope-{run_id}", "universe", tuple(codes) or ("*",), workspace_id=workspace_id, account_id=account_id, captured_at=now)
        data = DataSnapshot.create(f"data-{run_id}", "paper-runtime-v3", now - timedelta(days=1), now, tuple(codes) or ("*",), 0, f"runtime:{run_id}", workspace_id=workspace_id, account_id=account_id, captured_at=now)
        strategy = StrategyVersion.create(strategy_id, f"paper-strategy:{strategy_id}", {"codes": list(codes), "initial_cash": initial_cash}, strategy_version_id=f"strategy-{run_id}", workspace_id=workspace_id, account_id=account_id, captured_at=now)
        validation = ValidationRun.create(f"validation-{run_id}", scope=scope, data=data, strategy=strategy, metrics={"bootstrap": True}, completed_at=now)
        qualification = Qualification.create(f"qualification-{run_id}", validation=validation, passed=True, reason="paper owner bootstrap", qualified_until=now + timedelta(days=1))
        approval = Approval.create(f"approval-{run_id}", qualification_id=qualification.qualification_id, approved_by="paper-owner-bootstrap", authority="human", approved_at=now, comments="Local paper simulation bootstrap")
        for fact in (scope, data, strategy, validation, qualification, approval):
            getattr(self, {ScopeSnapshot: "save_scope", DataSnapshot: "save_data", StrategyVersion: "save_strategy", ValidationRun: "save_validation", Qualification: "save_qualification", Approval: "save_approval"}[type(fact)])(fact)
        run = self.create_execution_run(execution_run_id=run_id, workspace_id=workspace_id, account_id=account_id, environment=Environment.PAPER, scope_snapshot_id=scope.scope_id, data_snapshot_id=data.data_id, strategy_version_id=strategy.strategy_version_id, validation_run_id=validation.validation_run_id, qualification_id=qualification.qualification_id, approval_id=approval.approval_id)
        with get_connection(self.db_path) as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS paper_accounts (account_id TEXT NOT NULL, workspace_id TEXT NOT NULL, environment TEXT NOT NULL CHECK(environment='paper'), initial_cash REAL NOT NULL, fence_token TEXT NOT NULL DEFAULT '1', PRIMARY KEY(workspace_id, account_id, environment))")
            connection.execute("INSERT OR IGNORE INTO paper_accounts(account_id, workspace_id, environment, initial_cash, fence_token) VALUES (?, ?, 'paper', ?, '1')", (account_id, workspace_id, float(initial_cash)))
            connection.commit()
        return run


__all__ = ["Approval", "DataSnapshot", "ExecutionRun", "ExecutionRunBlockedError", "FactConflictError", "Qualification", "ResearchFactError", "ResearchFactsStore", "ScopeSnapshot", "StrategyVersion", "ValidationRun", "canonical_json", "content_hash"]
