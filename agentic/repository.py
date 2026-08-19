from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
from typing import Any

from agentic.models import AgenticPaperOrderDraft, PaperStrategyCandidate, PaperStrategyExecution, ResearchJob, ResearchReport, TradingSignal, normalize_signal_code
from agentic.operations import OperationConflict, OperationRecord, normalize_operation_id, operation_request_hash
from config.settings import DB_DIR
from utils.db import get_connection

DEFAULT_WORKSPACE_ID = "default"
WORKSPACE_ID_MAX_LENGTH = 128

def normalize_workspace_id(workspace_id: str | None) -> str:
    """Return a stable, non-empty workspace key suitable for routing/storage."""

    value = str(workspace_id or "").strip()
    if not value:
        return DEFAULT_WORKSPACE_ID
    if len(value) > WORKSPACE_ID_MAX_LENGTH or any(char in value for char in ("/", "\\", "\x00")):
        raise ValueError("invalid workspace id")
    return value

def _workspace_file_stem(workspace_id: str) -> str:
    normalized = normalize_workspace_id(workspace_id)
    readable = re.sub(r"[^A-Za-z0-9_-]+", "-", normalized).strip("-_") or "workspace"
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"{readable[:64]}-{digest}"

def agentic_db_path(workspace_id: str | None, base_dir: str | Path = DB_DIR) -> Path:
    """Map a workspace to its isolated Agentic SQLite file.

    The legacy default file remains the compatibility database for the
    unauthenticated ``APP_ENV=test`` workspace. Every named workspace gets a
    separate file, so signal projections and all append-only Agentic tables
    cannot be joined across workspace boundaries.
    """

    normalized = normalize_workspace_id(workspace_id)
    root = Path(base_dir)
    if normalized == DEFAULT_WORKSPACE_ID:
        return root / "agentic.db"
    return root / "agentic" / f"{_workspace_file_stem(normalized)}.db"

def paper_db_path(workspace_id: str | None, base_dir: str | Path | None = None) -> Path:
    """Map a workspace to the paper-order SQLite file used by Agentic paper flows."""

    normalized = normalize_workspace_id(workspace_id)
    root = Path(base_dir) if base_dir is not None else Path(DB_DIR).parent
    if normalized == DEFAULT_WORKSPACE_ID:
        return root / "paper_trading.db"
    return root / "paper" / f"{_workspace_file_stem(normalized)}.db"

class AgenticRepository:
    def __init__(self, db_path: str | Path, *, workspace_id: str | None = None):
        self.db_path = Path(db_path)
        self.workspace_id = normalize_workspace_id(workspace_id)
        self._ensure_schema()

    @classmethod
    def for_workspace(
        cls,
        workspace_id: str | None,
        *,
        base_dir: str | Path = DB_DIR,
    ) -> "AgenticRepository":
        normalized = normalize_workspace_id(workspace_id)
        return cls(agentic_db_path(normalized, base_dir), workspace_id=normalized)

    def _ensure_schema(self) -> None:
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agentic_signals (
                    id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    code TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    time_horizon TEXT NOT NULL,
                    entry_reasons TEXT NOT NULL,
                    risk_notes TEXT NOT NULL,
                    suggested_position REAL NOT NULL,
                    stop_loss REAL,
                    take_profit REAL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agentic_research_jobs (
                    id TEXT PRIMARY KEY,
                    code TEXT NOT NULL,
                    status TEXT NOT NULL,
                    roles TEXT NOT NULL,
                    final_report TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    error TEXT
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agentic_paper_strategy_candidates (
                    id TEXT PRIMARY KEY,
                    candidate_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    dsl TEXT NOT NULL,
                    sample TEXT NOT NULL,
                    metrics TEXT NOT NULL,
                    promotion TEXT NOT NULL,
                    status TEXT NOT NULL,
                    requires_confirmation INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agentic_candidate_backtest_results (
                    id TEXT PRIMARY KEY,
                    result TEXT NOT NULL,
                    sample TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agentic_paper_strategy_executions (
                    id TEXT PRIMARY KEY,
                    candidate_record_id TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    dsl TEXT NOT NULL,
                    codes TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    requires_confirmation INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agentic_paper_order_drafts (
                    id TEXT PRIMARY KEY,
                    execution_id TEXT NOT NULL,
                    code TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    volume INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    strategy_name TEXT NOT NULL,
                    signal_reason TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agentic_operations (
                    operation_id TEXT PRIMARY KEY,
                    command TEXT NOT NULL,
                    aggregate_type TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_agentic_operations_aggregate "
                "ON agentic_operations(aggregate_type, aggregate_id, created_at)"
            )
            research_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(agentic_research_jobs)").fetchall()
            }
            for name, definition in (
                ("run_key", "TEXT"),
                ("context_id", "TEXT"),
                ("report_id", "TEXT"),
                ("decision_signal_id", "TEXT"),
                ("context_json", "TEXT NOT NULL DEFAULT '{}'"),
                ("report_json", "TEXT NOT NULL DEFAULT '{}'"),
                ("decision_signal_json", "TEXT NOT NULL DEFAULT '{}'"),
            ):
                if name not in research_columns:
                    conn.execute(f"ALTER TABLE agentic_research_jobs ADD COLUMN {name} {definition}")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_agentic_research_run_key "
                "ON agentic_research_jobs(run_key) WHERE run_key IS NOT NULL"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agentic_daily_briefs (
                    run_key TEXT PRIMARY KEY,
                    snapshot_id TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    watchlist TEXT NOT NULL,
                    evidence_count INTEGER NOT NULL,
                    promotions TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    research_jobs TEXT NOT NULL,
                    report_count INTEGER NOT NULL,
                    markdown TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_agentic_daily_briefs_captured "
                "ON agentic_daily_briefs(captured_at DESC)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agentic_screening_runs (
                    run_id TEXT PRIMARY KEY,
                    strategy_namespace TEXT NOT NULL,
                    strategy_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source TEXT NOT NULL,
                    source_health TEXT NOT NULL,
                    candidates TEXT NOT NULL,
                    total INTEGER NOT NULL,
                    degraded INTEGER NOT NULL,
                    error TEXT NOT NULL,
                    strategy_source TEXT NOT NULL DEFAULT 'legacy',
                    strategy_config TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
                """
            )
            screening_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(agentic_screening_runs)").fetchall()
            }
            for name, definition in (
                ("strategy_source", "TEXT NOT NULL DEFAULT 'legacy'"),
                ("strategy_config", "TEXT NOT NULL DEFAULT '{}'"),
            ):
                if name not in screening_columns:
                    conn.execute(f"ALTER TABLE agentic_screening_runs ADD COLUMN {name} {definition}")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_agentic_screening_runs_created "
                "ON agentic_screening_runs(created_at DESC)"
            )
            conn.commit()

    @staticmethod
    def _signal_values(signal: TradingSignal) -> tuple:
        normalized_code = normalize_signal_code(signal.code)
        metadata = dict(signal.metadata or {})
        decision_payload = getattr(signal, "decision_payload", None)
        if callable(decision_payload):
            metadata["decision_signal"] = decision_payload()
        else:
            direction = str(getattr(signal, "direction", "hold"))
            metadata["decision_signal"] = {
                "action": {"buy": "buy", "sell": "sell", "hold": "hold", "risk": "alert"}.get(direction, "hold"),
                "score": None,
                "confidence": float(getattr(signal, "confidence", 0) or 0),
                "horizon": str(getattr(signal, "time_horizon", "") or ""),
                "stop_loss": getattr(signal, "stop_loss", None),
                "target_price": getattr(signal, "take_profit", None),
                "legacy_direction": direction,
            }
        return (
            signal.id,
            signal.agent_id,
            signal.source,
            normalized_code,
            signal.direction,
            float(signal.confidence),
            signal.time_horizon,
            _to_json(list(signal.entry_reasons)),
            _to_json(list(signal.risk_notes)),
            float(signal.suggested_position),
            signal.stop_loss,
            signal.take_profit,
            signal.status,
            signal.created_at,
            signal.expires_at,
            _to_json(metadata),
        )

    def _save_signal_on_connection(self, conn, signal: TradingSignal) -> None:
        conn.execute(
                """
                INSERT INTO agentic_signals (
                    id, agent_id, source, code, direction, confidence, time_horizon,
                    entry_reasons, risk_notes, suggested_position, stop_loss,
                    take_profit, status, created_at, expires_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    agent_id = excluded.agent_id,
                    source = excluded.source,
                    code = excluded.code,
                    direction = excluded.direction,
                    confidence = excluded.confidence,
                    time_horizon = excluded.time_horizon,
                    entry_reasons = excluded.entry_reasons,
                    risk_notes = excluded.risk_notes,
                    suggested_position = excluded.suggested_position,
                    stop_loss = excluded.stop_loss,
                    take_profit = excluded.take_profit,
                    status = excluded.status,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at,
                    metadata = excluded.metadata
                """,
                self._signal_values(signal),
            )

    def save_signal(self, signal: TradingSignal) -> None:
        with get_connection(self.db_path) as conn:
            self._save_signal_on_connection(conn, signal)
            conn.commit()

    def publish_signal_atomically(
        self,
        signal: TradingSignal,
        *,
        actor: str = "signal-service",
        reason: str = "signal published",
    ) -> None:
        """Persist the canonical projection and first Ledger event together.

        This is the concrete deep write seam used by ``SignalService``. The
        legacy two-adapter fallback remains available for test doubles and
        older repositories, but the production repository no longer leaves a
        Ledger orphan when projection persistence fails.
        """

        from agentic.signal_ledger import SignalLedger

        with get_connection(self.db_path) as conn:
            # Initialize any legacy Ledger tables before claiming the write
            # transaction; SignalLedger then joins the active transaction.
            ledger = SignalLedger(conn)
            conn.execute("BEGIN IMMEDIATE")
            self._save_signal_on_connection(conn, signal)
            ledger.append_transition(
                signal.id,
                None,
                signal.status,
                actor=actor,
                reason=reason,
                occurred_at=signal.created_at,
                metadata={"agent_id": signal.agent_id, "source": signal.source},
            )

    def transition_signal_atomically(
        self,
        updated: TradingSignal,
        *,
        expected_status: str,
        actor: str,
        reason: str,
        metadata: dict | None = None,
        operation_id: str | None = None,
        operation_request: dict | None = None,
        command: str = "signal.transition",
    ) -> TradingSignal:
        """CAS-update a signal and append its Ledger transition atomically."""

        from agentic.signal_ledger import SignalLedger, SignalLedgerConflict

        operation_id = normalize_operation_id(operation_id)
        request = dict(operation_request or {})
        with get_connection(self.db_path) as conn:
            ledger = SignalLedger(conn)
            conn.execute("BEGIN IMMEDIATE")
            existing = self._get_operation_on_connection(conn, operation_id)
            if existing is not None:
                self._assert_operation_matches(
                    existing,
                    command=command,
                    aggregate_type="signal",
                    aggregate_id=updated.id,
                    request=request,
                )
                if existing.status != "completed":
                    raise ValueError("operation is not a completed signal transition: %s" % operation_id)
                restored = conn.execute(
                    "SELECT * FROM agentic_signals WHERE id = ? LIMIT 1", (updated.id,)
                ).fetchone()
                if restored is None:
                    raise RuntimeError("completed operation has no signal projection: %s" % operation_id)
                return _row_to_signal(restored)
            row = conn.execute(
                "SELECT status FROM agentic_signals WHERE id = ? LIMIT 1",
                (updated.id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"signal not found: {updated.id}")
            if row["status"] != expected_status:
                raise SignalLedgerConflict(
                    "signal %s expected projection status=%r, current status is %r"
                    % (updated.id, expected_status, row["status"])
                )

            ledger.ensure_status(updated.id, expected_status)
            assignments = """
                UPDATE agentic_signals SET
                    agent_id=?, source=?, code=?, direction=?, confidence=?, time_horizon=?,
                    entry_reasons=?, risk_notes=?, suggested_position=?, stop_loss=?,
                    take_profit=?, status=?, created_at=?, expires_at=?, metadata=?
                WHERE id=? AND status=?
            """
            values = self._signal_values(updated)
            updated_count = conn.execute(
                assignments,
                (*values[1:], values[0], expected_status),
            ).rowcount
            if updated_count != 1:
                raise SignalLedgerConflict(
                    "signal %s projection changed during transition" % updated.id
                )
            event = ledger.append_transition(
                updated.id,
                expected_status,
                updated.status,
                actor=actor,
                reason=reason,
                metadata=metadata,
            )
            now = _operation_now()
            self._insert_operation_on_connection(
                conn,
                OperationRecord(
                    operation_id=operation_id,
                    command=command,
                    aggregate_type="signal",
                    aggregate_id=updated.id,
                    request=request,
                    request_hash=operation_request_hash(request),
                    status="completed",
                    result={
                        "signal_id": updated.id,
                        "status": updated.status,
                        "ledger_event_id": event.event_id,
                    },
                    created_at=now,
                    completed_at=now,
                ),
            )
            restored = conn.execute(
                "SELECT * FROM agentic_signals WHERE id = ? LIMIT 1", (updated.id,)
            ).fetchone()
            if restored is None:
                raise RuntimeError("signal projection disappeared after transition")
            return _row_to_signal(restored)

    def record_operation(
        self,
        operation_id: str,
        *,
        command: str,
        aggregate_type: str,
        aggregate_id: str,
        request: dict,
        status: str,
        result: dict,
    ) -> OperationRecord:
        """Persist or replay a command result through one idempotent seam."""
        operation_id = normalize_operation_id(operation_id)
        now = _operation_now()
        record = OperationRecord(
            operation_id=operation_id,
            command=command,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            request=request,
            request_hash=operation_request_hash(request),
            status=status,
            result=result,
            created_at=now,
            completed_at=now,
        )
        with get_connection(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = self._get_operation_on_connection(conn, operation_id)
            if existing is not None:
                self._assert_operation_matches(
                    existing,
                    command=command,
                    aggregate_type=aggregate_type,
                    aggregate_id=aggregate_id,
                    request=request,
                )
                return existing
            self._insert_operation_on_connection(conn, record)
            return record

    def get_operation(self, operation_id: str) -> OperationRecord:
        operation_id = normalize_operation_id(operation_id)
        with get_connection(self.db_path, readonly=True) as conn:
            record = self._get_operation_on_connection(conn, operation_id)
        if record is None:
            raise KeyError("operation not found: %s" % operation_id)
        return record

    def list_operations(
        self,
        limit: int = 100,
        *,
        aggregate_type: str | None = None,
        aggregate_id: str | None = None,
    ) -> list[OperationRecord]:
        safe_limit = max(1, min(int(limit), 500))
        clauses: list[str] = []
        params: list[Any] = []
        if aggregate_type:
            clauses.append("aggregate_type = ?")
            params.append(str(aggregate_type))
        if aggregate_id:
            clauses.append("aggregate_id = ?")
            params.append(str(aggregate_id))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with get_connection(self.db_path, readonly=True) as conn:
            rows = conn.execute(
                "SELECT * FROM agentic_operations" + where + " ORDER BY created_at DESC, operation_id DESC LIMIT ?",
                [*params, safe_limit],
            ).fetchall()
        return [self._operation_from_row(row) for row in rows]

    @staticmethod
    def _operation_from_row(row) -> OperationRecord:
        return OperationRecord(
            operation_id=row["operation_id"],
            command=row["command"],
            aggregate_type=row["aggregate_type"],
            aggregate_id=row["aggregate_id"],
            request=_from_json(row["request_json"], {}),
            request_hash=row["request_hash"],
            status=row["status"],
            result=_from_json(row["result_json"], {}),
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )

    @staticmethod
    def _get_operation_on_connection(conn, operation_id: str) -> OperationRecord | None:
        row = conn.execute(
            "SELECT * FROM agentic_operations WHERE operation_id = ? LIMIT 1", (operation_id,)
        ).fetchone()
        if row is None:
            return None
        return OperationRecord(
            operation_id=row["operation_id"],
            command=row["command"],
            aggregate_type=row["aggregate_type"],
            aggregate_id=row["aggregate_id"],
            request=_from_json(row["request_json"], {}),
            request_hash=row["request_hash"],
            status=row["status"],
            result=_from_json(row["result_json"], {}),
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )

    @staticmethod
    def _insert_operation_on_connection(conn, record: OperationRecord) -> None:
        conn.execute(
            """
            INSERT INTO agentic_operations(
                operation_id, command, aggregate_type, aggregate_id,
                request_json, request_hash, status, result_json, created_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.operation_id,
                record.command,
                record.aggregate_type,
                record.aggregate_id,
                _to_json(record.request),
                record.request_hash,
                record.status,
                _to_json(record.result),
                record.created_at,
                record.completed_at,
            ),
        )

    @staticmethod
    def _assert_operation_matches(
        existing: OperationRecord,
        *,
        command: str,
        aggregate_type: str,
        aggregate_id: str,
        request: dict,
    ) -> None:
        if (
            existing.command != command
            or existing.aggregate_type != aggregate_type
            or existing.aggregate_id != aggregate_id
            or existing.request_hash != operation_request_hash(request)
        ):
            raise OperationConflict(
                "operation_id was already used for different command facts: %s"
                % existing.operation_id
            )

    def get_signal(self, signal_id: str) -> TradingSignal:
        with get_connection(self.db_path, readonly=True) as conn:
            row = conn.execute(
                """
                SELECT id, agent_id, source, code, direction, confidence, time_horizon,
                       entry_reasons, risk_notes, suggested_position, stop_loss,
                       take_profit, status, created_at, expires_at, metadata
                FROM agentic_signals
                WHERE id = ?
                """,
                (signal_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"signal not found: {signal_id}")
        return _row_to_signal(row)

    def list_signals(self, limit: int = 100) -> list[TradingSignal]:
        safe_limit = max(1, min(int(limit), 500))
        with get_connection(self.db_path, readonly=True) as conn:
            rows = conn.execute(
                """
                SELECT id, agent_id, source, code, direction, confidence, time_horizon,
                       entry_reasons, risk_notes, suggested_position, stop_loss,
                       take_profit, status, created_at, expires_at, metadata
                FROM agentic_signals
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [_row_to_signal(row) for row in rows]

    def list_outcome_aggregates(
        self,
        *,
        limit: int = 100,
        min_samples: int = 5,
        source: str | None = None,
        profile: str | None = None,
        horizon_days: int | None = None,
        market_phase: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return read-only T+N outcome aggregates by product dimensions.

        Outcome metadata is the source of truth for evaluator dimensions. The
        fallback to signal metadata keeps older outcome records visible without
        changing their stored shape. Ranking is intentionally only assigned to
        groups meeting ``min_samples`` and having directional observations.
        """

        safe_limit = max(1, min(int(limit), 500))
        safe_min_samples = max(1, int(min_samples))
        clauses: list[str] = []
        params: list[Any] = []
        if source:
            clauses.append("s.source = ?")
            params.append(str(source))
        if horizon_days is not None:
            clauses.append("COALESCE(json_extract(o.metadata_json, '$.horizon_days'), 0) = ?")
            params.append(int(horizon_days))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with get_connection(self.db_path, readonly=True) as conn:
            rows = conn.execute(
                """
                SELECT s.id AS signal_id, s.source, s.time_horizon, s.metadata AS signal_metadata,
                       o.status, o.realized_return, o.max_drawdown, o.metadata_json,
                       o.observed_at
                FROM agentic_signals AS s
                JOIN signal_outcomes AS o ON o.signal_id = s.id
                """ + where + " ORDER BY o.observed_at ASC, o.outcome_id ASC",
                params,
            ).fetchall()

        groups: dict[tuple[str, str, int | str, str], dict[str, Any]] = {}
        for row in rows:
            outcome_metadata = _from_json(row["metadata_json"], {})
            signal_metadata = _from_json(row["signal_metadata"], {})
            if not isinstance(outcome_metadata, dict):
                outcome_metadata = {}
            if not isinstance(signal_metadata, dict):
                signal_metadata = {}
            dimensions = _outcome_dimensions(
                row["source"], row["time_horizon"], signal_metadata, outcome_metadata
            )
            if profile and dimensions[1] != str(profile):
                continue
            if market_phase and dimensions[3] != str(market_phase):
                continue
            key = dimensions
            group = groups.setdefault(
                key,
                {
                    "source": dimensions[0],
                    "profile": dimensions[1],
                    "horizon": dimensions[2],
                    "market_phase": dimensions[3],
                    "sample_count": 0,
                    "direction": {"sample_count": 0, "hit_count": 0, "hit_rate": None},
                    "take_profit": {"sample_count": 0, "hit_count": 0, "hit_rate": None},
                    "stop_loss": {"sample_count": 0, "hit_count": 0, "hit_rate": None},
                    "executability": {"sample_count": 0, "hit_count": 0, "hit_rate": None},
                    "realized_return": {"sample_count": 0, "average": None},
                    "max_drawdown": {"sample_count": 0, "average": None},
                },
            )
            _accumulate_outcome_group(group, row, outcome_metadata)

        aggregates = list(groups.values())
        for group in aggregates:
            _finalize_outcome_group(group, safe_min_samples)
        rankable = [item for item in aggregates if item["rankable"]]
        rankable.sort(key=lambda item: (-item["direction"]["hit_rate"], -item["sample_count"], str(item["source"])))
        for rank, item in enumerate(rankable, start=1):
            item["rank"] = rank
        aggregates.sort(key=lambda item: (item["rank"] is None, item["rank"] or 0, str(item["source"])))
        return aggregates[:safe_limit]

    def save_research_job(self, job: ResearchJob) -> None:
        normalized_code = normalize_signal_code(job.code)
        with get_connection(self.db_path) as conn:
            self._save_research_job_on_connection(conn, job, normalized_code=normalized_code)
            conn.commit()

    @staticmethod
    def _save_research_job_on_connection(conn, job: ResearchJob, *, normalized_code: str | None = None) -> None:
        normalized_code = normalized_code or normalize_signal_code(job.code)
        conn.execute(
                """
                INSERT INTO agentic_research_jobs (
                    id, code, status, roles, final_report, created_at, updated_at, error,
                    run_key, context_id, report_id, decision_signal_id,
                    context_json, report_json, decision_signal_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    code = excluded.code,
                    status = excluded.status,
                    roles = excluded.roles,
                    final_report = excluded.final_report,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    error = excluded.error,
                    run_key = excluded.run_key,
                    context_id = excluded.context_id,
                    report_id = excluded.report_id,
                    decision_signal_id = excluded.decision_signal_id,
                    context_json = excluded.context_json,
                    report_json = excluded.report_json,
                    decision_signal_json = excluded.decision_signal_json
                """,
                (
                    job.id,
                    normalized_code,
                    job.status,
                    _to_json(list(job.roles)),
                    _to_json(job.final_report),
                    job.created_at,
                    job.updated_at,
                    job.error,
                    job.run_key,
                    job.context_id,
                    job.report_id,
                    job.decision_signal_id,
                    _to_json(job.context),
                    _to_json(job.report),
                    _to_json(job.decision_signal),
                ),
            )

    def save_research_job_with_signal_atomically(self, job: ResearchJob, signal: TradingSignal) -> None:
        """Persist a research projection, signal projection, and first ledger event together."""

        from agentic.signal_ledger import SignalLedger

        if signal.research_job_id and signal.research_job_id != job.id:
            raise ValueError("signal research_job_id does not match research job")
        with get_connection(self.db_path) as conn:
            ledger = SignalLedger(conn)
            conn.execute("BEGIN IMMEDIATE")
            self._save_signal_on_connection(conn, signal)
            ledger.append_transition(
                signal.id,
                None,
                signal.status,
                actor="research_pipeline",
                reason="research decision signal published",
                occurred_at=signal.created_at,
                metadata={"research_job_id": job.id, "source": signal.source},
            )
            self._save_research_job_on_connection(conn, job)

    def get_research_job_by_run_key(self, run_key: str) -> ResearchJob | None:
        key = str(run_key or "").strip()
        if not key:
            return None
        with get_connection(self.db_path, readonly=True) as conn:
            row = conn.execute(
                """
                SELECT id, code, status, roles, final_report, created_at, updated_at, error,
                       run_key, context_id, report_id, decision_signal_id,
                       context_json, report_json, decision_signal_json
                FROM agentic_research_jobs WHERE run_key = ? LIMIT 1
                """,
                (key,),
            ).fetchone()
        return None if row is None else _row_to_research_job(row)

    def list_research_jobs(
        self,
        limit: int = 50,
        *,
        code: str | None = None,
        status: str | None = None,
    ) -> list[ResearchJob]:
        safe_limit = max(1, min(int(limit), 500))
        clauses: list[str] = []
        params: list[Any] = []
        if code:
            clauses.append("code = ?")
            params.append(normalize_signal_code(code))
        if status:
            clauses.append("status = ?")
            params.append(str(status))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with get_connection(self.db_path, readonly=True) as conn:
            rows = conn.execute(
                """
                SELECT id, code, status, roles, final_report, created_at, updated_at, error,
                       run_key, context_id, report_id, decision_signal_id,
                       context_json, report_json, decision_signal_json
                FROM agentic_research_jobs
                """ + where + " ORDER BY created_at DESC, id DESC LIMIT ?",
                [*params, safe_limit],
            ).fetchall()
        return [_row_to_research_job(row) for row in rows]

    def get_research_report(self, job_id: str) -> ResearchReport:
        job = self.get_research_job(job_id)
        payload = dict(job.report or job.final_report or {})
        return ResearchReport(
            id=job.report_id or f"report_{job.id}",
            research_job_id=job.id,
            stock_code=job.code,
            status=job.status,
            summary=str(payload.get("summary") or payload.get("decision") or ""),
            roles=payload.get("roles") or job.final_report.get("roles") or {},
            decision_signal=job.decision_signal or payload.get("decision_signal") or {},
            evidence_snapshot_id=payload.get("evidence_snapshot_id") or job.context.get("evidence_snapshot_id"),
            data_quality=str(payload.get("data_quality") or job.context.get("data_quality") or "unknown"),
            missing_fields=payload.get("missing_fields") or job.context.get("missing_fields") or (),
            source_health=payload.get("source_health") or job.context.get("source_health") or {},
            model_metadata=payload.get("model_metadata") or job.context.get("model_metadata") or {},
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

    def save_daily_brief(self, brief) -> dict[str, Any]:
        """Persist the daily brief read model after its Outbox event is created."""

        run_key = str(brief.run_key or "").strip()
        if not run_key:
            raise ValueError("daily brief run_key is required")
        promotions = [
            {
                "signal_id": item.signal_id,
                "decision": item.decision.to_dict(),
                "ledger_event_id": item.ledger_event_id,
            }
            for item in (brief.promotions or ())
        ]
        payload = {
            "run_key": run_key,
            "snapshot_id": brief.snapshot_id,
            "captured_at": brief.captured_at,
            "watchlist": list(brief.watchlist),
            "evidence_count": int(brief.evidence_count),
            "promotions": promotions,
            "event_id": brief.event_id,
            "research_jobs": list(brief.research_jobs),
            "report_count": int(brief.report_count),
            "markdown": brief.markdown,
        }
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO agentic_daily_briefs(
                    run_key, snapshot_id, captured_at, watchlist, evidence_count,
                    promotions, event_id, research_jobs, report_count, markdown
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_key) DO UPDATE SET
                    snapshot_id=excluded.snapshot_id,
                    captured_at=excluded.captured_at,
                    watchlist=excluded.watchlist,
                    evidence_count=excluded.evidence_count,
                    promotions=excluded.promotions,
                    event_id=excluded.event_id,
                    research_jobs=excluded.research_jobs,
                    report_count=excluded.report_count,
                    markdown=excluded.markdown
                """,
                (
                    payload["run_key"],
                    payload["snapshot_id"],
                    payload["captured_at"],
                    _to_json(payload["watchlist"]),
                    payload["evidence_count"],
                    _to_json(payload["promotions"]),
                    payload["event_id"],
                    _to_json(payload["research_jobs"]),
                    payload["report_count"],
                    payload["markdown"],
                ),
            )
            conn.commit()
        return payload

    def get_daily_brief(self, run_key: str) -> dict[str, Any] | None:
        key = str(run_key or "").strip()
        if not key:
            return None
        with get_connection(self.db_path, readonly=True) as conn:
            row = conn.execute(
                "SELECT * FROM agentic_daily_briefs WHERE run_key = ? LIMIT 1", (key,)
            ).fetchone()
        return None if row is None else _row_to_daily_brief(row)

    def list_daily_briefs(
        self,
        limit: int = 30,
        *,
        trade_date: str | None = None,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 500))
        clauses: list[str] = []
        params: list[Any] = []
        if trade_date:
            clauses.append("captured_at LIKE ?")
            params.append(str(trade_date).strip() + "%")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with get_connection(self.db_path, readonly=True) as conn:
            rows = conn.execute(
                "SELECT * FROM agentic_daily_briefs" + where
                + " ORDER BY captured_at DESC, run_key DESC LIMIT ?",
                [*params, safe_limit],
            ).fetchall()
        return [_row_to_daily_brief(row) for row in rows]

    def save_screening_run(self, run: dict[str, Any]) -> dict[str, Any]:
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO agentic_screening_runs(
                    run_id, strategy_namespace, strategy_name, status, source,
                    source_health, candidates, total, degraded, error,
                    strategy_source, strategy_config, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run["run_id"], run["strategy_namespace"], run["strategy_name"], run["status"],
                    run["source"], _to_json(run.get("source_health") or {}),
                    _to_json(run.get("candidates") or []), int(run.get("total") or 0),
                    1 if run.get("degraded") else 0, str(run.get("error") or ""),
                    str(run.get("strategy_source") or "legacy"),
                    _to_json(run.get("strategy_config") or {}),
                    _operation_now(),
                ),
            )
            conn.commit()
        return dict(run)

    def list_screening_runs(self, limit: int = 30) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 500))
        with get_connection(self.db_path, readonly=True) as conn:
            rows = conn.execute(
                "SELECT * FROM agentic_screening_runs ORDER BY created_at DESC, run_id DESC LIMIT ?",
                (safe_limit,),
            ).fetchall()
        return [
            {
                "run_id": row["run_id"],
                "strategy_namespace": row["strategy_namespace"],
                "strategy_name": row["strategy_name"],
                "status": row["status"],
                "source": row["source"],
                "source_health": _from_json(row["source_health"], {}),
                "candidates": _from_json(row["candidates"], []),
                "total": int(row["total"] or 0),
                "degraded": bool(row["degraded"]),
                "error": row["error"] or "",
                "strategy_source": row["strategy_source"] if "strategy_source" in row.keys() else "legacy",
                "strategy_config": _from_json(row["strategy_config"], {}) if "strategy_config" in row.keys() else {},
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def get_screening_run(self, run_id: str) -> dict[str, Any] | None:
        """Return one persisted screening run, including candidate actions."""
        key = str(run_id or "").strip()
        if not key:
            return None
        with get_connection(self.db_path, readonly=True) as conn:
            row = conn.execute(
                "SELECT * FROM agentic_screening_runs WHERE run_id = ? LIMIT 1", (key,)
            ).fetchone()
        return None if row is None else _screening_run_from_row(row)

    def list_screening_candidate_history(
        self,
        code: str,
        *,
        limit: int = 30,
        strategy_namespace: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find a code's historical screening appearances without new storage."""
        normalized = normalize_signal_code(code)
        if not normalized:
            return []
        safe_limit = max(1, min(int(limit), 500))
        code_patterns = [
            f'%"code": "{normalized}"%',
            f'%"code": "{normalized}.SH"%',
            f'%"code": "{normalized}.SZ"%',
            f'%"code": "{normalized}.BJ"%',
        ]
        code_clause = "(" + " OR ".join("candidates LIKE ?" for _ in code_patterns) + ")"
        clauses = ["strategy_namespace = ?", code_clause] if strategy_namespace else [code_clause]
        params: list[Any] = [str(strategy_namespace)] if strategy_namespace else []
        params.extend(code_patterns)
        with get_connection(self.db_path, readonly=True) as conn:
            rows = conn.execute(
                "SELECT * FROM agentic_screening_runs WHERE "
                + " AND ".join(clauses)
                + " ORDER BY created_at DESC, run_id DESC LIMIT ?",
                [*params, safe_limit],
            ).fetchall()
        history = []
        for row in rows:
            run = _screening_run_from_row(row)
            history.extend(
                {
                    **candidate,
                    "run_id": run["run_id"],
                    "strategy_namespace": run["strategy_namespace"],
                    "strategy_name": run["strategy_name"],
                    "run_status": run["status"],
                    "run_source_health": run["source_health"],
                    "run_created_at": run["created_at"],
                }
                for candidate in run["candidates"]
                if str(candidate.get("code") or "").strip() and normalize_signal_code(candidate.get("code")) == normalized
            )
        return history[:safe_limit]

    def list_screening_candidate_actions(self, run_id: str, code: str) -> list[dict[str, Any]]:
        """Return the domain actions attached to one candidate occurrence."""
        run = self.get_screening_run(run_id)
        if run is None:
            return []
        normalized = normalize_signal_code(code)
        for candidate in run["candidates"]:
            if str(candidate.get("code") or "").strip() and normalize_signal_code(candidate.get("code")) == normalized:
                return list(candidate.get("next_actions") or candidate.get("actions") or [])
        return []

    def get_research_job(self, job_id: str) -> ResearchJob:
        with get_connection(self.db_path, readonly=True) as conn:
            row = conn.execute(
                """
                SELECT id, code, status, roles, final_report, created_at, updated_at, error,
                       run_key, context_id, report_id, decision_signal_id,
                       context_json, report_json, decision_signal_json
                FROM agentic_research_jobs
                WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"research job not found: {job_id}")
        return _row_to_research_job(row)

    def save_paper_strategy_candidate(self, candidate: PaperStrategyCandidate) -> None:
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO agentic_paper_strategy_candidates (
                    id, candidate_id, name, dsl, sample, metrics, promotion,
                    status, requires_confirmation, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    candidate_id = excluded.candidate_id,
                    name = excluded.name,
                    dsl = excluded.dsl,
                    sample = excluded.sample,
                    metrics = excluded.metrics,
                    promotion = excluded.promotion,
                    status = excluded.status,
                    requires_confirmation = excluded.requires_confirmation,
                    created_at = excluded.created_at
                """,
                (
                    candidate.id,
                    candidate.candidate_id,
                    candidate.name,
                    _to_json(candidate.dsl),
                    _to_json(candidate.sample),
                    _to_json(candidate.metrics),
                    _to_json(candidate.promotion),
                    candidate.status,
                    1 if candidate.requires_confirmation else 0,
                    candidate.created_at,
                ),
            )
            conn.commit()

    def create_paper_strategy_candidate_operation(
        self,
        candidate: PaperStrategyCandidate,
        *,
        operation_id: str,
        operation_request: dict,
        command: str = "strategy.paper_candidate.enqueue",
    ) -> PaperStrategyCandidate:
        """Create a candidate and its command record in one Agentic DB transaction."""

        operation_id = normalize_operation_id(operation_id)
        with get_connection(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = self._get_operation_on_connection(conn, operation_id)
            if existing is not None:
                self._assert_operation_matches(
                    existing,
                    command=command,
                    aggregate_type="paper_strategy_candidate",
                    aggregate_id=existing.aggregate_id,
                    request=operation_request,
                )
                row = conn.execute(
                    "SELECT * FROM agentic_paper_strategy_candidates WHERE id = ? LIMIT 1",
                    (existing.aggregate_id,),
                ).fetchone()
                if row is None:
                    raise RuntimeError("completed candidate operation has no candidate projection: %s" % operation_id)
                return _row_to_paper_strategy_candidate(row)
            self._save_paper_strategy_candidate_on_connection(conn, candidate)
            now = _operation_now()
            self._insert_operation_on_connection(
                conn,
                OperationRecord(
                    operation_id=operation_id,
                    command=command,
                    aggregate_type="paper_strategy_candidate",
                    aggregate_id=candidate.id,
                    request=operation_request,
                    request_hash=operation_request_hash(operation_request),
                    status="completed",
                    result={"candidate_id": candidate.id, "status": candidate.status},
                    created_at=now,
                    completed_at=now,
                ),
            )
            return candidate

    @staticmethod
    def _save_paper_strategy_candidate_on_connection(conn, candidate: PaperStrategyCandidate) -> None:
        conn.execute(
            """
            INSERT INTO agentic_paper_strategy_candidates (
                id, candidate_id, name, dsl, sample, metrics, promotion,
                status, requires_confirmation, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                candidate_id = excluded.candidate_id,
                name = excluded.name,
                dsl = excluded.dsl,
                sample = excluded.sample,
                metrics = excluded.metrics,
                promotion = excluded.promotion,
                status = excluded.status,
                requires_confirmation = excluded.requires_confirmation,
                created_at = excluded.created_at
            """,
            (
                candidate.id,
                candidate.candidate_id,
                candidate.name,
                _to_json(candidate.dsl),
                _to_json(candidate.sample),
                _to_json(candidate.metrics),
                _to_json(candidate.promotion),
                candidate.status,
                1 if candidate.requires_confirmation else 0,
                candidate.created_at,
            ),
        )

    def get_paper_strategy_candidate(self, candidate_id: str) -> PaperStrategyCandidate:
        with get_connection(self.db_path, readonly=True) as conn:
            row = conn.execute(
                """
                SELECT id, candidate_id, name, dsl, sample, metrics, promotion,
                       status, requires_confirmation, created_at
                FROM agentic_paper_strategy_candidates
                WHERE id = ?
                """,
                (candidate_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"paper strategy candidate not found: {candidate_id}")
        return _row_to_paper_strategy_candidate(row)

    def save_candidate_backtest_result(self, result: dict[str, Any], sample: dict[str, Any]) -> str:
        from datetime import datetime, timezone
        from uuid import uuid4

        result_id = f"candidate_result_{uuid4().hex}"
        created_at = datetime.now(timezone.utc).isoformat()
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO agentic_candidate_backtest_results (
                    id, result, sample, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (result_id, _to_json(dict(result or {})), _to_json(dict(sample or {})), created_at),
            )
            conn.commit()
        return result_id

    def get_candidate_backtest_result(self, result_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        with get_connection(self.db_path, readonly=True) as conn:
            row = conn.execute(
                """
                SELECT result, sample
                FROM agentic_candidate_backtest_results
                WHERE id = ?
                """,
                (result_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"candidate backtest result not found: {result_id}")
        return _from_json(row["result"], {}), _from_json(row["sample"], {})

    def update_paper_strategy_candidate_status(
        self, candidate_id: str, status: str, requires_confirmation: bool
    ) -> PaperStrategyCandidate:
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE agentic_paper_strategy_candidates
                SET status = ?, requires_confirmation = ?
                WHERE id = ?
                """,
                (status, 1 if requires_confirmation else 0, candidate_id),
            )
            conn.commit()
        if cursor.rowcount == 0:
            raise KeyError(f"paper strategy candidate not found: {candidate_id}")
        return self.get_paper_strategy_candidate(candidate_id)

    def transition_paper_strategy_candidate_atomically(
        self,
        candidate_id: str,
        *,
        expected_status: str,
        status: str,
        requires_confirmation: bool,
        operation_id: str,
        operation_request: dict,
        command: str,
        result: dict,
    ) -> PaperStrategyCandidate:
        """CAS-update a paper candidate and persist its command in one transaction."""

        operation_id = normalize_operation_id(operation_id)
        with get_connection(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = self._get_operation_on_connection(conn, operation_id)
            if existing is not None:
                self._assert_operation_matches(
                    existing,
                    command=command,
                    aggregate_type="paper_strategy_candidate",
                    aggregate_id=candidate_id,
                    request=operation_request,
                )
                if existing.status != "completed":
                    raise ValueError("operation is not a completed paper candidate transition: %s" % operation_id)
                row = conn.execute(
                    "SELECT * FROM agentic_paper_strategy_candidates WHERE id = ? LIMIT 1",
                    (candidate_id,),
                ).fetchone()
                if row is None:
                    raise KeyError(f"paper strategy candidate not found: {candidate_id}")
                return _row_to_paper_strategy_candidate(row)

            row = conn.execute(
                "SELECT status FROM agentic_paper_strategy_candidates WHERE id = ? LIMIT 1",
                (candidate_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"paper strategy candidate not found: {candidate_id}")
            if row["status"] != expected_status:
                raise ValueError(
                    "paper strategy candidate %s expected status=%r, current status is %r"
                    % (candidate_id, expected_status, row["status"])
                )
            updated = conn.execute(
                "UPDATE agentic_paper_strategy_candidates SET status = ?, requires_confirmation = ? WHERE id = ? AND status = ?",
                (status, 1 if requires_confirmation else 0, candidate_id, expected_status),
            ).rowcount
            if updated != 1:
                raise ValueError("paper strategy candidate changed during transition: %s" % candidate_id)
            now = _operation_now()
            self._insert_operation_on_connection(
                conn,
                OperationRecord(
                    operation_id=operation_id,
                    command=command,
                    aggregate_type="paper_strategy_candidate",
                    aggregate_id=candidate_id,
                    request=operation_request,
                    request_hash=operation_request_hash(operation_request),
                    status="completed",
                    result=result,
                    created_at=now,
                    completed_at=now,
                ),
            )
            restored = conn.execute(
                "SELECT * FROM agentic_paper_strategy_candidates WHERE id = ? LIMIT 1",
                (candidate_id,),
            ).fetchone()
            if restored is None:
                raise RuntimeError("paper strategy candidate disappeared after transition")
            return _row_to_paper_strategy_candidate(restored)

    def save_paper_strategy_execution(self, execution: PaperStrategyExecution) -> None:
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO agentic_paper_strategy_executions (
                    id, candidate_record_id, candidate_id, name, dsl, codes,
                    status, reason, requires_confirmation, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    candidate_record_id = excluded.candidate_record_id,
                    candidate_id = excluded.candidate_id,
                    name = excluded.name,
                    dsl = excluded.dsl,
                    codes = excluded.codes,
                    status = excluded.status,
                    reason = excluded.reason,
                    requires_confirmation = excluded.requires_confirmation,
                    created_at = excluded.created_at
                """,
                (
                    execution.id,
                    execution.candidate_record_id,
                    execution.candidate_id,
                    execution.name,
                    _to_json(execution.dsl),
                    _to_json(list(execution.codes)),
                    execution.status,
                    execution.reason,
                    1 if execution.requires_confirmation else 0,
                    execution.created_at,
                ),
            )
            conn.commit()

    def create_paper_strategy_execution_operation(
        self,
        execution: PaperStrategyExecution,
        *,
        operation_id: str,
        operation_request: dict,
        command: str = "strategy.paper_candidate.run",
    ) -> PaperStrategyExecution:
        """Create an execution intent and command record atomically."""

        operation_id = normalize_operation_id(operation_id)
        with get_connection(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = self._get_operation_on_connection(conn, operation_id)
            if existing is not None:
                self._assert_operation_matches(
                    existing,
                    command=command,
                    aggregate_type="paper_strategy_execution",
                    aggregate_id=existing.aggregate_id,
                    request=operation_request,
                )
                row = conn.execute(
                    "SELECT * FROM agentic_paper_strategy_executions WHERE id = ? LIMIT 1",
                    (existing.aggregate_id,),
                ).fetchone()
                if row is None:
                    raise RuntimeError("completed execution operation has no execution projection: %s" % operation_id)
                return _row_to_paper_strategy_execution(row)
            conn.execute(
                """INSERT INTO agentic_paper_strategy_executions (
                    id, candidate_record_id, candidate_id, name, dsl, codes,
                    status, reason, requires_confirmation, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    execution.id,
                    execution.candidate_record_id,
                    execution.candidate_id,
                    execution.name,
                    _to_json(execution.dsl),
                    _to_json(list(execution.codes)),
                    execution.status,
                    execution.reason,
                    1 if execution.requires_confirmation else 0,
                    execution.created_at,
                ),
            )
            now = _operation_now()
            self._insert_operation_on_connection(
                conn,
                OperationRecord(
                    operation_id=operation_id,
                    command=command,
                    aggregate_type="paper_strategy_execution",
                    aggregate_id=execution.id,
                    request=operation_request,
                    request_hash=operation_request_hash(operation_request),
                    status="completed",
                    result={"execution_id": execution.id, "status": execution.status},
                    created_at=now,
                    completed_at=now,
                ),
            )
            return execution

    def create_paper_order_drafts_operation(
        self,
        drafts: list[AgenticPaperOrderDraft],
        *,
        operation_id: str,
        execution_id: str,
        operation_request: dict,
        command: str = "strategy.paper_execution.order_drafts",
    ) -> list[AgenticPaperOrderDraft]:
        """Persist all order drafts and their operation atomically."""

        operation_id = normalize_operation_id(operation_id)
        with get_connection(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = self._get_operation_on_connection(conn, operation_id)
            if existing is not None:
                self._assert_operation_matches(
                    existing,
                    command=command,
                    aggregate_type="paper_strategy_execution",
                    aggregate_id=execution_id,
                    request=operation_request,
                )
                rows = conn.execute(
                    "SELECT * FROM agentic_paper_order_drafts WHERE execution_id = ? ORDER BY created_at, id",
                    (execution_id,),
                ).fetchall()
                return [_row_to_agentic_order_draft(row) for row in rows]
            for draft in drafts:
                conn.execute(
                    """INSERT INTO agentic_paper_order_drafts (
                        id, execution_id, code, direction, order_type, volume,
                        status, strategy_name, signal_reason, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        draft.id, draft.execution_id, draft.code, draft.direction,
                        draft.order_type, draft.volume, draft.status,
                        draft.strategy_name, draft.signal_reason, draft.created_at,
                    ),
                )
            now = _operation_now()
            self._insert_operation_on_connection(
                conn,
                OperationRecord(
                    operation_id=operation_id,
                    command=command,
                    aggregate_type="paper_strategy_execution",
                    aggregate_id=execution_id,
                    request=operation_request,
                    request_hash=operation_request_hash(operation_request),
                    status="completed",
                    result={"execution_id": execution_id, "draft_ids": [draft.id for draft in drafts]},
                    created_at=now,
                    completed_at=now,
                ),
            )
            return drafts

    def save_agentic_order_draft(self, draft: AgenticPaperOrderDraft) -> None:
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO agentic_paper_order_drafts (
                    id, execution_id, code, direction, order_type, volume,
                    status, strategy_name, signal_reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    execution_id = excluded.execution_id,
                    code = excluded.code,
                    direction = excluded.direction,
                    order_type = excluded.order_type,
                    volume = excluded.volume,
                    status = excluded.status,
                    strategy_name = excluded.strategy_name,
                    signal_reason = excluded.signal_reason,
                    created_at = excluded.created_at
                """,
                (
                    draft.id, draft.execution_id, draft.code, draft.direction,
                    draft.order_type, draft.volume, draft.status, draft.strategy_name,
                    draft.signal_reason, draft.created_at,
                ),
            )
            conn.commit()

    def list_agentic_order_drafts(self, limit: int = 100) -> list[AgenticPaperOrderDraft]:
        safe_limit = max(1, min(int(limit), 500))
        with get_connection(self.db_path, readonly=True) as conn:
            rows = conn.execute(
                """
                SELECT id, execution_id, code, direction, order_type, volume,
                       status, strategy_name, signal_reason, created_at
                FROM agentic_paper_order_drafts
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [_row_to_agentic_order_draft(row) for row in rows]

    def list_agentic_order_drafts_for_execution(self, execution_id: str) -> list[AgenticPaperOrderDraft]:
        with get_connection(self.db_path, readonly=True) as conn:
            rows = conn.execute(
                """
                SELECT id, execution_id, code, direction, order_type, volume,
                       status, strategy_name, signal_reason, created_at
                FROM agentic_paper_order_drafts
                WHERE execution_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (execution_id,),
            ).fetchall()
        return [_row_to_agentic_order_draft(row) for row in rows]

    def get_paper_strategy_execution(self, execution_id: str) -> PaperStrategyExecution:
        with get_connection(self.db_path, readonly=True) as conn:
            row = conn.execute(
                """
                SELECT id, candidate_record_id, candidate_id, name, dsl, codes,
                       status, reason, requires_confirmation, created_at
                FROM agentic_paper_strategy_executions
                WHERE id = ?
                """,
                (execution_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"paper strategy execution not found: {execution_id}")
        return _row_to_paper_strategy_execution(row)

    def update_paper_strategy_execution_status(
        self, execution_id: str, status: str, reason: str, requires_confirmation: bool
    ) -> PaperStrategyExecution:
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE agentic_paper_strategy_executions
                SET status = ?, reason = ?, requires_confirmation = ?
                WHERE id = ?
                """,
                (status, reason, 1 if requires_confirmation else 0, execution_id),
            )
            conn.commit()
        if cursor.rowcount == 0:
            raise KeyError(f"paper strategy execution not found: {execution_id}")
        return self.get_paper_strategy_execution(execution_id)

    def record_paper_strategy_execution_operation(
        self,
        execution_id: str,
        *,
        operation_id: str,
        operation_request: dict,
        command: str,
        status: str,
        reason: str,
        requires_confirmation: bool,
        result: dict | None = None,
    ) -> PaperStrategyExecution:
        """Compatibility seam for recording execution commands during migration."""

        operation_id = normalize_operation_id(operation_id)
        with get_connection(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = self._get_operation_on_connection(conn, operation_id)
            if existing is not None:
                self._assert_operation_matches(
                    existing,
                    command=command,
                    aggregate_type="paper_strategy_execution",
                    aggregate_id=execution_id,
                    request=operation_request,
                )
                return self.get_paper_strategy_execution(execution_id)
            updated = conn.execute(
                "UPDATE agentic_paper_strategy_executions SET status = ?, reason = ?, requires_confirmation = ? WHERE id = ?",
                (status, reason, 1 if requires_confirmation else 0, execution_id),
            ).rowcount
            if updated != 1:
                raise KeyError(f"paper strategy execution not found: {execution_id}")
            now = _operation_now()
            self._insert_operation_on_connection(
                conn,
                OperationRecord(
                    operation_id=operation_id,
                    command=command,
                    aggregate_type="paper_strategy_execution",
                    aggregate_id=execution_id,
                    request=operation_request,
                    request_hash=operation_request_hash(operation_request),
                    status="completed",
                    result=dict(result or {"execution_id": execution_id, "status": status}),
                    created_at=now,
                    completed_at=now,
                ),
            )
        return self.get_paper_strategy_execution(execution_id)

    def list_paper_strategy_executions(self, limit: int = 100) -> list[PaperStrategyExecution]:
        safe_limit = max(1, min(int(limit), 500))
        with get_connection(self.db_path, readonly=True) as conn:
            rows = conn.execute(
                """
                SELECT id, candidate_record_id, candidate_id, name, dsl, codes,
                       status, reason, requires_confirmation, created_at
                FROM agentic_paper_strategy_executions
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [_row_to_paper_strategy_execution(row) for row in rows]

    def list_paper_strategy_candidates(self, limit: int = 100) -> list[PaperStrategyCandidate]:
        safe_limit = max(1, min(int(limit), 500))
        with get_connection(self.db_path, readonly=True) as conn:
            rows = conn.execute(
                """
                SELECT id, candidate_id, name, dsl, sample, metrics, promotion,
                       status, requires_confirmation, created_at
                FROM agentic_paper_strategy_candidates
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [_row_to_paper_strategy_candidate(row) for row in rows]

def _to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)

def _operation_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def _from_json(value: str | None, default: Any) -> Any:
    if value is None:
        return default
    return json.loads(value)

def _outcome_dimensions(
    source: str,
    time_horizon: str,
    signal_metadata: dict[str, Any],
    outcome_metadata: dict[str, Any],
) -> tuple[str, str, int | str, str]:
    decision = signal_metadata.get("decision_signal") if isinstance(signal_metadata.get("decision_signal"), dict) else {}
    model = signal_metadata.get("model_metadata") if isinstance(signal_metadata.get("model_metadata"), dict) else {}
    profile = (
        outcome_metadata.get("profile")
        or signal_metadata.get("profile")
        or signal_metadata.get("strategy_profile")
        or decision.get("profile")
        or decision.get("strategy_profile")
        or model.get("profile")
        or model.get("strategy_profile")
        or "unknown"
    )
    raw_horizon = outcome_metadata.get("horizon_days")
    try:
        horizon: int | str = int(raw_horizon) if raw_horizon is not None else str(time_horizon or "unknown")
    except (TypeError, ValueError):
        horizon = str(raw_horizon or time_horizon or "unknown")
    research_context = signal_metadata.get("research_context")
    context_phase = research_context.get("market_phase") if isinstance(research_context, dict) else None
    market_phase = (
        outcome_metadata.get("market_phase")
        or signal_metadata.get("market_phase")
        or context_phase
        or decision.get("market_phase")
        or model.get("market_phase")
        or "unknown"
    )
    return str(source or "unknown"), str(profile), horizon, str(market_phase)

def _accumulate_outcome_group(group: dict[str, Any], row: Any, metadata: dict[str, Any]) -> None:
    group["sample_count"] += 1
    for metric, key in (
        ("direction", "direction_hit"),
        ("take_profit", "take_profit_hit"),
        ("stop_loss", "stop_loss_hit"),
        ("executability", "executable"),
    ):
        value = metadata.get(key)
        if value is not None:
            group[metric]["sample_count"] += 1
            group[metric]["hit_count"] += int(bool(value))
    if row["realized_return"] is not None:
        result = group["realized_return"]
        result["sample_count"] += 1
        result["average"] = (result["average"] or 0.0) + float(row["realized_return"])
    if row["max_drawdown"] is not None:
        result = group["max_drawdown"]
        result["sample_count"] += 1
        result["average"] = (result["average"] or 0.0) + float(row["max_drawdown"])

def _finalize_outcome_group(group: dict[str, Any], min_samples: int) -> None:
    for metric in ("direction", "take_profit", "stop_loss", "executability"):
        result = group[metric]
        result["hit_rate"] = (
            result["hit_count"] / result["sample_count"] if result["sample_count"] else None
        )
    for metric in ("realized_return", "max_drawdown"):
        result = group[metric]
        if result["sample_count"]:
            result["average"] = result["average"] / result["sample_count"]
    direction_sample = group["direction"]["sample_count"]
    group["rankable"] = group["sample_count"] >= min_samples and direction_sample >= min_samples
    group["rank"] = None
    group["ranking_status"] = "ranked" if group["rankable"] else "insufficient_sample"

def _row_to_agentic_order_draft(row: Any) -> AgenticPaperOrderDraft:
    return AgenticPaperOrderDraft(
        id=row["id"],
        execution_id=row["execution_id"],
        code=row["code"],
        direction=row["direction"],
        order_type=row["order_type"],
        volume=row["volume"],
        status=row["status"],
        strategy_name=row["strategy_name"],
        signal_reason=row["signal_reason"],
        created_at=row["created_at"],
    )

def _row_to_paper_strategy_execution(row: Any) -> PaperStrategyExecution:
    return PaperStrategyExecution(
        id=row["id"],
        candidate_record_id=row["candidate_record_id"],
        candidate_id=row["candidate_id"],
        name=row["name"],
        dsl=_from_json(row["dsl"], {}),
        codes=_from_json(row["codes"], []),
        status=row["status"],
        reason=row["reason"],
        requires_confirmation=bool(row["requires_confirmation"]),
        created_at=row["created_at"],
    )

def _row_to_paper_strategy_candidate(row: Any) -> PaperStrategyCandidate:
    return PaperStrategyCandidate(
        id=row["id"],
        candidate_id=row["candidate_id"],
        name=row["name"],
        dsl=_from_json(row["dsl"], {}),
        sample=_from_json(row["sample"], {}),
        metrics=_from_json(row["metrics"], {}),
        promotion=_from_json(row["promotion"], {}),
        status=row["status"],
        requires_confirmation=bool(row["requires_confirmation"]),
        created_at=row["created_at"],
    )

def _row_to_signal(row: Any) -> TradingSignal:
    metadata = _from_json(row["metadata"], {})
    decision = metadata.get("decision_signal") if isinstance(metadata.get("decision_signal"), dict) else {}
    return TradingSignal(
        row["id"],
        row["agent_id"],
        row["source"],
        row["code"],
        row["direction"],
        row["confidence"],
        row["time_horizon"],
        _from_json(row["entry_reasons"], []),
        _from_json(row["risk_notes"], []),
        row["suggested_position"],
        row["stop_loss"],
        row["take_profit"],
        row["status"],
        row["created_at"],
        row["expires_at"],
        metadata,
        action=decision.get("action"),
        score=decision.get("score"),
        entry_low=decision.get("entry_low"),
        entry_high=decision.get("entry_high"),
        target_price=decision.get("target_price"),
        invalidation=decision.get("invalidation") or "",
        watch_conditions=decision.get("watch_conditions") or (),
        reason=decision.get("reason") or "",
        risk_summary=decision.get("risk_summary") or "",
        catalyst_summary=decision.get("catalyst_summary") or "",
        factor_contributions=decision.get("factor_contributions") or {},
        evidence_snapshot_id=decision.get("evidence_snapshot_id"),
        research_job_id=decision.get("research_job_id"),
        data_quality=decision.get("data_quality") or "unknown",
        missing_fields=decision.get("missing_fields") or (),
        source_health=decision.get("source_health") or {},
        model_metadata=decision.get("model_metadata") or {},
    )

def _row_to_research_job(row: Any) -> ResearchJob:
    return ResearchJob(
        row["id"],
        row["code"],
        row["status"],
        _from_json(row["roles"], []),
        _from_json(row["final_report"], {}),
        row["created_at"],
        row["updated_at"],
        row["error"],
        row["run_key"] if "run_key" in row.keys() else None,
        row["context_id"] if "context_id" in row.keys() else None,
        row["report_id"] if "report_id" in row.keys() else None,
        row["decision_signal_id"] if "decision_signal_id" in row.keys() else None,
        _from_json(row["context_json"], {}) if "context_json" in row.keys() else {},
        _from_json(row["report_json"], {}) if "report_json" in row.keys() else {},
        _from_json(row["decision_signal_json"], {}) if "decision_signal_json" in row.keys() else {},
    )

def _row_to_daily_brief(row: Any) -> dict[str, Any]:
    return {
        "run_key": row["run_key"],
        "snapshot_id": row["snapshot_id"],
        "captured_at": row["captured_at"],
        "watchlist": _from_json(row["watchlist"], []),
        "evidence_count": int(row["evidence_count"] or 0),
        "promotions": _from_json(row["promotions"], []),
        "event_id": row["event_id"],
        "research_jobs": _from_json(row["research_jobs"], []),
        "report_count": int(row["report_count"] or 0),
        "markdown": row["markdown"] or "",
    }

def _screening_run_from_row(row: Any) -> dict[str, Any]:
    return {
        "run_id": row["run_id"],
        "strategy_namespace": row["strategy_namespace"],
        "strategy_name": row["strategy_name"],
        "status": row["status"],
        "source": row["source"],
        "source_health": _from_json(row["source_health"], {}),
        "candidates": _from_json(row["candidates"], []),
        "total": int(row["total"] or 0),
        "degraded": bool(row["degraded"]),
        "error": row["error"] or "",
        "strategy_source": row["strategy_source"] if "strategy_source" in row.keys() else "legacy",
        "strategy_config": _from_json(row["strategy_config"], {}) if "strategy_config" in row.keys() else {},
        "created_at": row["created_at"],
    }
