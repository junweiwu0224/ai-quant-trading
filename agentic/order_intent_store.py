"""Durable Adapter for paper-only order intents."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import List, Optional, Union

from .order_intent import PaperOrderIntent


class SQLiteOrderIntentStore:
    """Persist intent state without introducing a broker or live-order seam."""

    def __init__(self, database: Union[str, Path, sqlite3.Connection]) -> None:
        self._owns_connection = not isinstance(database, sqlite3.Connection)
        self.connection = database if isinstance(database, sqlite3.Connection) else sqlite3.connect(str(database))
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_order_intents (
                intent_id TEXT PRIMARY KEY,
                signal_id TEXT NOT NULL,
                code TEXT NOT NULL,
                direction TEXT NOT NULL,
                order_type TEXT NOT NULL,
                volume INTEGER NOT NULL,
                status TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                paper_only INTEGER NOT NULL,
                confirmed_by TEXT,
                metadata_json TEXT NOT NULL
            )
            """
        )
        self.connection.commit()

    def save(self, intent: PaperOrderIntent) -> PaperOrderIntent:
        if not intent.paper_only:
            raise ValueError("only paper intents can be persisted")
        self.connection.execute(
            """
            INSERT INTO paper_order_intents(
                intent_id, signal_id, code, direction, order_type, volume,
                status, reason, created_at, paper_only, confirmed_by, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(intent_id) DO UPDATE SET
                signal_id=excluded.signal_id, code=excluded.code,
                direction=excluded.direction, order_type=excluded.order_type,
                volume=excluded.volume, status=excluded.status,
                reason=excluded.reason, created_at=excluded.created_at,
                paper_only=excluded.paper_only, confirmed_by=excluded.confirmed_by,
                metadata_json=excluded.metadata_json
            """,
            (
                intent.id,
                intent.signal_id,
                intent.code,
                intent.direction,
                intent.order_type,
                intent.volume,
                intent.status,
                intent.reason,
                intent.created_at,
                int(intent.paper_only),
                intent.confirmed_by,
                json.dumps(dict(intent.metadata), ensure_ascii=False, sort_keys=True, default=str),
            ),
        )
        self.connection.commit()
        return intent

    @staticmethod
    def _from_row(row: sqlite3.Row) -> PaperOrderIntent:
        return PaperOrderIntent(
            id=row["intent_id"],
            signal_id=row["signal_id"],
            code=row["code"],
            direction=row["direction"],
            order_type=row["order_type"],
            volume=row["volume"],
            status=row["status"],
            reason=row["reason"],
            created_at=row["created_at"],
            paper_only=bool(row["paper_only"]),
            confirmed_by=row["confirmed_by"],
            metadata=json.loads(row["metadata_json"] or "{}"),
        )

    def get(self, intent_id: str) -> Optional[PaperOrderIntent]:
        row = self.connection.execute(
            "SELECT * FROM paper_order_intents WHERE intent_id = ?", (intent_id,)
        ).fetchone()
        return None if row is None else self._from_row(row)

    def list(self, limit: int = 100) -> List[PaperOrderIntent]:
        safe_limit = max(1, min(int(limit), 500))
        rows = self.connection.execute(
            "SELECT * FROM paper_order_intents ORDER BY created_at DESC, intent_id DESC LIMIT ?",
            (safe_limit,),
        ).fetchall()
        return [self._from_row(row) for row in rows]

    def close(self) -> None:
        if self._owns_connection:
            self.connection.close()
