"""Append-only signal history, provenance, and outcome records."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Union

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

def _dump(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, default=str)

def _load(value: str) -> Dict[str, Any]:
    loaded = json.loads(value or "{}")
    return loaded if isinstance(loaded, dict) else {}

VALID_LEDGER_STATUSES = {
    "new",
    "watching",
    "backtested",
    "paper_pending",
    "paper_active",
    "expired",
    "invalidated",
    "closed",
}

ALLOWED_LEDGER_TRANSITIONS = {
    "new": {"watching", "backtested", "paper_pending", "expired", "invalidated", "closed"},
    "watching": {"backtested", "paper_pending", "expired", "invalidated", "closed"},
    "backtested": {"paper_pending", "expired", "invalidated", "closed"},
    "paper_pending": {"paper_active", "expired", "invalidated", "closed"},
    "paper_active": {"expired", "invalidated", "closed"},
    "expired": set(),
    "invalidated": set(),
    "closed": set(),
}

class SignalLedgerConflict(RuntimeError):
    """Raised when a transition was based on a stale current status."""

@dataclass(frozen=True)
class SignalEvent:
    event_id: str
    signal_id: str
    sequence: int
    from_status: Optional[str]
    to_status: str
    occurred_at: str
    actor: str
    reason: str
    evidence_snapshot_id: Optional[str]
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class SignalProvenance:
    provenance_id: str
    signal_id: str
    source_type: str
    source_id: str
    evidence_snapshot_id: Optional[str]
    recorded_at: str
    details: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class SignalOutcome:
    outcome_id: str
    signal_id: str
    observed_at: str
    status: str
    realized_return: Optional[float] = None
    max_drawdown: Optional[float] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

class SignalLedger:
    """SQLite Adapter for signal history and attribution."""

    def __init__(self, database: Union[str, Path, sqlite3.Connection], *, readonly: bool = False) -> None:
        self._owns_connection = not isinstance(database, sqlite3.Connection)
        self.readonly = readonly
        self.db_path: Path | None = None if isinstance(database, sqlite3.Connection) else Path(database)
        empty_readonly = False
        if isinstance(database, sqlite3.Connection):
            self.connection = database
        elif readonly:
            path = Path(database)
            if path.exists():
                self.connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5.0, check_same_thread=False)
            else:
                # A missing audit database is an empty read model, not a
                # reason to create a production file during a GET request.
                self.connection = sqlite3.connect(":memory:", timeout=5.0, check_same_thread=False)
                empty_readonly = True
        else:
            path = Path(database)
            path.parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(str(path), timeout=5.0, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA busy_timeout=5000")
        if not readonly or empty_readonly:
            self._initialize()

    def _assert_writable(self) -> None:
        if self.readonly:
            raise sqlite3.OperationalError("signal ledger is read-only")

    def _initialize(self) -> None:
        had_external_transaction = self.connection.in_transaction
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS signal_events (
                event_id TEXT PRIMARY KEY,
                signal_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                from_status TEXT,
                to_status TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                actor TEXT NOT NULL,
                reason TEXT NOT NULL,
                evidence_snapshot_id TEXT,
                metadata_json TEXT NOT NULL,
                UNIQUE(signal_id, sequence)
            )
            """
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_signal_events_signal ON signal_events(signal_id, sequence)"
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS signal_provenance (
                provenance_id TEXT PRIMARY KEY,
                signal_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                evidence_snapshot_id TEXT,
                recorded_at TEXT NOT NULL,
                details_json TEXT NOT NULL
            )
            """
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_signal_provenance_signal ON signal_provenance(signal_id, recorded_at)"
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS signal_outcomes (
                outcome_id TEXT PRIMARY KEY,
                signal_id TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                status TEXT NOT NULL,
                realized_return REAL,
                max_drawdown REAL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_signal_outcomes_signal ON signal_outcomes(signal_id, observed_at)"
        )
        if not had_external_transaction:
            self.connection.commit()

    def latest_status(self, signal_id: str) -> Optional[str]:
        row = self.connection.execute(
            "SELECT to_status FROM signal_events WHERE signal_id = ? ORDER BY sequence DESC LIMIT 1",
            (signal_id,),
        ).fetchone()
        return None if row is None else row["to_status"]

    def has_history(self, signal_id: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM signal_events WHERE signal_id = ? LIMIT 1",
            (signal_id,),
        ).fetchone()
        return row is not None

    def canonical_signal_exists(self, signal_id: str) -> Optional[bool]:

        """Check the canonical projection without mutating the read model.

        ``None`` means the legacy/in-memory database has no projection table;
        ``False`` is a real orphan in a production database.
        """
        try:
            row = self.connection.execute(
                "SELECT 1 FROM agentic_signals WHERE id = ? LIMIT 1", (signal_id,)
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        return row is not None

    def has_signal_record(self, signal_id: str) -> bool:
        """Compatibility boolean for callers that do not need tri-state semantics."""

        return self.canonical_signal_exists(signal_id) is True

    def ensure_status(

        self,
        signal_id: str,
        current_status: str,
        *,
        actor: str = "projection-migration",
    ) -> Optional[SignalEvent]:
        """Seed history for a pre-ledger signal or reject projection drift."""

        latest = self.latest_status(signal_id)
        if latest is None:
            return self.append_transition(
                signal_id,
                None,
                current_status,
                actor=actor,
                reason="seeded from existing signal projection",
            )
        if latest != current_status:
            raise SignalLedgerConflict(
                "signal %s projection status=%r does not match ledger status=%r"
                % (signal_id, current_status, latest)
            )
        return None

    def append_transition(
        self,
        signal_id: str,
        from_status: Optional[str],
        to_status: str,
        *,
        actor: str = "system",
        reason: str = "",
        evidence_snapshot_id: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        occurred_at: Optional[str] = None,
    ) -> SignalEvent:
        self._assert_writable()
        if to_status not in VALID_LEDGER_STATUSES:
            raise ValueError("unsupported signal status: %s" % to_status)
        if from_status is not None and from_status not in VALID_LEDGER_STATUSES:
            raise ValueError("unsupported signal status: %s" % from_status)
        had_external_transaction = self.connection.in_transaction
        if not had_external_transaction:
            self.connection.execute("BEGIN IMMEDIATE")
        try:
            latest = self.latest_status(signal_id)
            if latest != from_status:
                raise SignalLedgerConflict(
                    "signal %s expected from_status=%r, current status is %r"
                    % (signal_id, from_status, latest)
                )
            if from_status is not None and to_status not in ALLOWED_LEDGER_TRANSITIONS[from_status]:
                raise ValueError("invalid signal transition: %s -> %s" % (from_status, to_status))
            sequence_row = self.connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence FROM signal_events WHERE signal_id = ?",
                (signal_id,),
            ).fetchone()
            sequence = int(sequence_row["next_sequence"])
            event = SignalEvent(
                event_id=uuid.uuid4().hex,
                signal_id=signal_id,
                sequence=sequence,
                from_status=from_status,
                to_status=to_status,
                occurred_at=occurred_at or _now(),
                actor=actor,
                reason=reason,
                evidence_snapshot_id=evidence_snapshot_id,
                metadata=dict(metadata or {}),
            )
            self.connection.execute(
                """
                INSERT INTO signal_events(
                    event_id, signal_id, sequence, from_status, to_status, occurred_at,
                    actor, reason, evidence_snapshot_id, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.signal_id,
                    event.sequence,
                    event.from_status,
                    event.to_status,
                    event.occurred_at,
                    event.actor,
                    event.reason,
                    event.evidence_snapshot_id,
                    _dump(event.metadata),
                ),
            )
            if not had_external_transaction:
                self.connection.commit()
            return event
        except Exception:
            if not had_external_transaction:
                self.connection.rollback()
            raise

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> SignalEvent:
        return SignalEvent(
            event_id=row["event_id"],
            signal_id=row["signal_id"],
            sequence=row["sequence"],
            from_status=row["from_status"],
            to_status=row["to_status"],
            occurred_at=row["occurred_at"],
            actor=row["actor"],
            reason=row["reason"],
            evidence_snapshot_id=row["evidence_snapshot_id"],
            metadata=_load(row["metadata_json"]),
        )

    def timeline(self, signal_id: str) -> List[SignalEvent]:
        rows = self.connection.execute(
            "SELECT * FROM signal_events WHERE signal_id = ? ORDER BY sequence",
            (signal_id,),
        ).fetchall()
        return [self._event_from_row(row) for row in rows]

    def record_provenance(
        self,
        signal_id: str,
        *,
        source_type: str,
        source_id: str,
        evidence_snapshot_id: Optional[str] = None,
        details: Optional[Mapping[str, Any]] = None,
        recorded_at: Optional[str] = None,
    ) -> SignalProvenance:
        self._assert_writable()
        existing = self.connection.execute(
            """
            SELECT * FROM signal_provenance
            WHERE signal_id = ? AND source_type = ? AND source_id = ?
              AND COALESCE(evidence_snapshot_id, '') = COALESCE(?, '')
            ORDER BY recorded_at, provenance_id LIMIT 1
            """,
            (signal_id, source_type, source_id, evidence_snapshot_id),
        ).fetchone()
        if existing is not None:
            return SignalProvenance(
                provenance_id=existing["provenance_id"],
                signal_id=existing["signal_id"],
                source_type=existing["source_type"],
                source_id=existing["source_id"],
                evidence_snapshot_id=existing["evidence_snapshot_id"],
                recorded_at=existing["recorded_at"],
                details=_load(existing["details_json"]),
            )
        provenance = SignalProvenance(
            provenance_id=uuid.uuid4().hex,
            signal_id=signal_id,
            source_type=source_type,
            source_id=source_id,
            evidence_snapshot_id=evidence_snapshot_id,
            recorded_at=recorded_at or _now(),
            details=dict(details or {}),
        )
        self.connection.execute(
            """
            INSERT INTO signal_provenance(
                provenance_id, signal_id, source_type, source_id,
                evidence_snapshot_id, recorded_at, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                provenance.provenance_id,
                provenance.signal_id,
                provenance.source_type,
                provenance.source_id,
                provenance.evidence_snapshot_id,
                provenance.recorded_at,
                _dump(provenance.details),
            ),
        )
        self.connection.commit()
        return provenance

    def provenance(self, signal_id: str) -> List[SignalProvenance]:
        rows = self.connection.execute(
            "SELECT * FROM signal_provenance WHERE signal_id = ? ORDER BY recorded_at, provenance_id",
            (signal_id,),
        ).fetchall()
        return [
            SignalProvenance(
                provenance_id=row["provenance_id"],
                signal_id=row["signal_id"],
                source_type=row["source_type"],
                source_id=row["source_id"],
                evidence_snapshot_id=row["evidence_snapshot_id"],
                recorded_at=row["recorded_at"],
                details=_load(row["details_json"]),
            )
            for row in rows
        ]

    def list_provenance(self, signal_id: str) -> List[SignalProvenance]:
        """Read-only alias used by research/audit consumers."""

        return self.provenance(signal_id)

    def record_outcome(

        self,
        signal_id: str,
        *,
        status: str,
        realized_return: Optional[float] = None,
        max_drawdown: Optional[float] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        observed_at: Optional[str] = None,
    ) -> SignalOutcome:
        self._assert_writable()
        outcome = SignalOutcome(
            outcome_id=uuid.uuid4().hex,
            signal_id=signal_id,
            observed_at=observed_at or _now(),
            status=status,
            realized_return=realized_return,
            max_drawdown=max_drawdown,
            metadata=dict(metadata or {}),
        )
        self.connection.execute(
            """
            INSERT INTO signal_outcomes(
                outcome_id, signal_id, observed_at, status, realized_return,
                max_drawdown, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                outcome.outcome_id,
                outcome.signal_id,
                outcome.observed_at,
                outcome.status,
                outcome.realized_return,
                outcome.max_drawdown,
                _dump(outcome.metadata),
            ),
        )
        self.connection.commit()
        return outcome

    def latest_outcome(self, signal_id: str) -> Optional[SignalOutcome]:
        row = self.connection.execute(
            "SELECT * FROM signal_outcomes WHERE signal_id = ? ORDER BY observed_at DESC, outcome_id DESC LIMIT 1",
            (signal_id,),
        ).fetchone()
        if row is None:
            return None
        return SignalOutcome(
            outcome_id=row["outcome_id"],
            signal_id=row["signal_id"],
            observed_at=row["observed_at"],
            status=row["status"],
            realized_return=row["realized_return"],
            max_drawdown=row["max_drawdown"],
            metadata=_load(row["metadata_json"]),
        )

    def outcomes(self, signal_id: str) -> List[SignalOutcome]:
        rows = self.connection.execute(
            "SELECT * FROM signal_outcomes WHERE signal_id = ? ORDER BY observed_at, outcome_id",
            (signal_id,),
        ).fetchall()
        return [
            SignalOutcome(
                outcome_id=row["outcome_id"],
                signal_id=row["signal_id"],
                observed_at=row["observed_at"],
                status=row["status"],
                realized_return=row["realized_return"],
                max_drawdown=row["max_drawdown"],
                metadata=_load(row["metadata_json"]),
            )
            for row in rows
        ]

    def close(self) -> None:

        if self._owns_connection:
            self.connection.close()
