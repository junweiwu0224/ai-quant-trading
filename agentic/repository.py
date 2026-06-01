from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentic.models import AgenticPaperOrderDraft, PaperStrategyCandidate, PaperStrategyExecution, ResearchJob, TradingSignal, normalize_signal_code
from utils.db import get_connection


class AgenticRepository:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._ensure_schema()

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
            conn.commit()

    def save_signal(self, signal: TradingSignal) -> None:
        normalized_code = normalize_signal_code(signal.code)
        with get_connection(self.db_path) as conn:
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
                (
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
                    _to_json(signal.metadata or {}),
                ),
            )
            conn.commit()

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

    def save_research_job(self, job: ResearchJob) -> None:
        normalized_code = normalize_signal_code(job.code)
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO agentic_research_jobs (
                    id, code, status, roles, final_report, created_at, updated_at, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    code = excluded.code,
                    status = excluded.status,
                    roles = excluded.roles,
                    final_report = excluded.final_report,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    error = excluded.error
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
                ),
            )
            conn.commit()

    def get_research_job(self, job_id: str) -> ResearchJob:
        with get_connection(self.db_path, readonly=True) as conn:
            row = conn.execute(
                """
                SELECT id, code, status, roles, final_report, created_at, updated_at, error
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


def _from_json(value: str | None, default: Any) -> Any:
    if value is None:
        return default
    return json.loads(value)


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
        _from_json(row["metadata"], {}),
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
    )
