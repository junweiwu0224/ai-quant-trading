from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentic.models import TradingSignal, normalize_signal_code
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


def _to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _from_json(value: str | None, default: Any) -> Any:
    if value is None:
        return default
    return json.loads(value)


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
