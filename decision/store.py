"""SQLite persistence for reproducible decision artifacts.

The store is deliberately small and append-oriented.  Mutable configuration is
represented by new versions; runs, reports, AI commentary and deliveries are
never updated in place.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import secrets
import sqlite3
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

from data.markets import InstrumentNormalizationError, get_market_adapter


_PROTECTED_REF_PATTERN = re.compile(r"^env://[A-Za-z_][A-Za-z0-9_]*$")


def normalize_protected_ref(value: Any, *, field: str, required: bool) -> str:
    """Accept only environment-variable references, never credential values."""

    text = str(value or "").strip()
    if not text:
        if required:
            raise ValueError(f"{field}_required")
        return ""
    if _PROTECTED_REF_PATTERN.fullmatch(text) is None:
        raise ValueError(f"{field}_must_use_env_reference")
    return text


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat(timespec="seconds")


def stable_json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_hash(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


_SCHEDULE_DATE_RE = re.compile(r"(?P<slot>[^:]+):(?P<trade_date>\d{4}-\d{2}-\d{2})$")


def scheduled_run_context(run: Mapping[str, Any]) -> dict[str, str | None]:
    """Extract the persisted scheduling business key from a run.

    Scheduled runs created by the Worker use ``...:<slot>:<trade_date>`` as
    their stable key.  Keeping this parsing at the storage/report boundary
    makes report and delivery code use the same conservative interpretation;
    malformed legacy keys simply produce an empty context.
    """

    def value(key: str) -> Any:
        if isinstance(run, Mapping):
            return run.get(key)
        try:
            return run[key]  # type: ignore[index]
        except (KeyError, IndexError, TypeError):
            return None

    trigger = str(value("trigger") or "")
    slot = trigger.removeprefix("scheduled_prepare:") if trigger.startswith("scheduled_prepare:") else ""
    match = _SCHEDULE_DATE_RE.search(str(value("run_key") or ""))
    trade_date = match.group("trade_date") if match else ""
    if not slot and match:
        slot = match.group("slot")
    return {"schedule_slot": slot or None, "trade_date": trade_date or None}


def report_fingerprint(body: Mapping[str, Any]) -> dict[str, Any]:
    """Return the deterministic facts that define a report.

    Storage identifiers and wall-clock timestamps are audit metadata, not
    decision facts.  Excluding them lets an isolated restore replay the same
    frozen input without changing the report hash.
    """

    decision_fields = (
        "membership_id",
        "symbol",
        "action",
        "previous_action",
        "score",
        "valid",
        "stale",
        "risk_veto",
        "confirmed",
        "confirming_bar_end",
        "reason_codes",
        "contributions",
    )
    fingerprint = {
        key: body.get(key)
        for key in (
            "report_type",
            "portfolio_id",
            "portfolio_version_id",
            "input_hash",
            "version_hash",
            "source",
            "quality_status",
            "data_quality",
            "trigger",
            "run_key",
            "schedule_slot",
            "trade_date",
        )
    } | {
        "decisions": [
            {key: item.get(key) for key in decision_fields}
            for item in (body.get("decisions") or [])
            if isinstance(item, Mapping)
        ]
    }
    for key in ("market", "market_capabilities", "strategy_weights", "eligibility"):
        if key in body:
            fingerprint[key] = body.get(key)
    validation = body.get("validation")
    if isinstance(validation, Mapping):
        fingerprint["validation"] = {
            "status": validation.get("status"),
            "validation_hash": validation.get("validation_hash"),
            "result": validation.get("result"),
        }
    evidence = body.get("evidence")
    if isinstance(evidence, Mapping):
        # The snapshot id is a storage reference, not a decision fact.
        # The immutable snapshot and provider hashes are decision facts.  The
        # local collection timestamp is audit metadata and must not make a
        # deterministic replay hash depend on wall-clock time.
        fingerprint["evidence"] = {
            key: value
            for key, value in evidence.items()
            if key not in {"snapshot_id", "collected_at"}
        }
    return fingerprint


def _canonical_market(value: str) -> str:
    """Resolve aliases once at the storage boundary."""

    return get_market_adapter(value).code.value


def _canonical_instrument(market: str, value: str) -> tuple[str, str]:
    """Return a stable identity and a provider-compatible display symbol.

    Existing A-share storage uses the six-digit display code, while the new
    decision domain needs an exchange-qualified identity for uniqueness.  A
    small synthetic-symbol fallback is retained for local fixtures and legacy
    rows; real market-shaped identifiers always use the adapter normalizer.
    """

    raw = str(value or "").strip()
    if not raw:
        raise ValueError("instrument_symbol_required")
    adapter = get_market_adapter(market)
    try:
        canonical = adapter.normalize_instrument(raw)
    except InstrumentNormalizationError:
        canonical = raw.upper()
    display = canonical.split(".", 1)[1] if "." in canonical else canonical
    return canonical, display


class DecisionStore:
    """Thread/process safe enough for the single-machine SQLite deployment."""

    def __init__(self, database: str | Path):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.database), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        with self._connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS decision_portfolios (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    market TEXT NOT NULL,
                    name TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    auto_push_enabled INTEGER NOT NULL DEFAULT 0,
                    current_version_id TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_decision_portfolios_workspace ON decision_portfolios(workspace_id, market);

                CREATE TABLE IF NOT EXISTS decision_memberships (
                    id TEXT PRIMARY KEY,
                    portfolio_id TEXT NOT NULL REFERENCES decision_portfolios(id),
                    instrument_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    UNIQUE(portfolio_id, instrument_id)
                );

                CREATE TABLE IF NOT EXISTS decision_versions (
                    id TEXT PRIMARY KEY,
                    portfolio_id TEXT NOT NULL REFERENCES decision_portfolios(id),
                    version_no INTEGER NOT NULL,
                    config_json TEXT NOT NULL,
                    config_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(portfolio_id, version_no),
                    UNIQUE(portfolio_id, config_hash)
                );

                CREATE TABLE IF NOT EXISTS decision_snapshots (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    portfolio_version_id TEXT NOT NULL REFERENCES decision_versions(id),
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    source TEXT NOT NULL,
                    quality_status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(portfolio_version_id, payload_hash)
                );

                CREATE TABLE IF NOT EXISTS decision_runs (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    portfolio_id TEXT NOT NULL REFERENCES decision_portfolios(id),
                    portfolio_version_id TEXT NOT NULL REFERENCES decision_versions(id),
                    snapshot_id TEXT NOT NULL REFERENCES decision_snapshots(id),
                    run_key TEXT NOT NULL UNIQUE,
                    trigger TEXT NOT NULL,
                    report_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS decisions (
                    id TEXT PRIMARY KEY,
                    decision_run_id TEXT NOT NULL REFERENCES decision_runs(id),
                    membership_id TEXT NOT NULL REFERENCES decision_memberships(id),
                    symbol TEXT NOT NULL,
                    action TEXT NOT NULL,
                    previous_action TEXT,
                    score REAL,
                    valid INTEGER NOT NULL,
                    stale INTEGER NOT NULL DEFAULT 0,
                    risk_veto INTEGER NOT NULL DEFAULT 0,
                    confirmed INTEGER NOT NULL DEFAULT 0,
                    confirming_bar_end TEXT,
                    reason_codes_json TEXT NOT NULL,
                    contributions_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(decision_run_id, membership_id)
                );
                CREATE INDEX IF NOT EXISTS idx_decisions_membership ON decisions(membership_id, created_at);

                CREATE TABLE IF NOT EXISTS decision_member_states (
                    membership_id TEXT PRIMARY KEY REFERENCES decision_memberships(id),
                    last_valid_action TEXT,
                    last_valid_trade_date TEXT,
                    invalid_since_trade_date TEXT,
                    current_action TEXT,
                    quality_status TEXT NOT NULL DEFAULT 'unknown',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS decision_state_events (
                    id TEXT PRIMARY KEY,
                    portfolio_id TEXT NOT NULL REFERENCES decision_portfolios(id),
                    membership_id TEXT NOT NULL REFERENCES decision_memberships(id),
                    action TEXT NOT NULL,
                    confirming_bar_end TEXT NOT NULL,
                    portfolio_version_id TEXT NOT NULL REFERENCES decision_versions(id),
                    decision_id TEXT NOT NULL REFERENCES decisions(id),
                    event_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(portfolio_id, membership_id, action, confirming_bar_end, portfolio_version_id)
                );
                CREATE INDEX IF NOT EXISTS idx_decision_state_events_member
                    ON decision_state_events(membership_id, confirming_bar_end);

                CREATE TABLE IF NOT EXISTS decision_reports (
                    id TEXT PRIMARY KEY,
                    decision_run_id TEXT NOT NULL REFERENCES decision_runs(id),
                    report_type TEXT NOT NULL,
                    body_json TEXT NOT NULL,
                    report_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(decision_run_id, report_type)
                );

                CREATE TABLE IF NOT EXISTS ai_commentary (
                    id TEXT PRIMARY KEY,
                    report_id TEXT NOT NULL REFERENCES decision_reports(id),
                    model TEXT NOT NULL,
                    prompt_hash TEXT NOT NULL,
                    input_hash TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS notification_targets (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    label TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    test_status TEXT NOT NULL DEFAULT 'untested',
                    last_tested_at TEXT,
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_notification_targets_workspace ON notification_targets(workspace_id, channel);

                CREATE TABLE IF NOT EXISTS notification_routes (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    portfolio_id TEXT NOT NULL REFERENCES decision_portfolios(id),
                    target_id TEXT NOT NULL REFERENCES notification_targets(id),
                    event_type TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    UNIQUE(portfolio_id, target_id, event_type)
                );

                CREATE TABLE IF NOT EXISTS delivery_attempts (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    report_id TEXT NOT NULL REFERENCES decision_reports(id),
                    target_id TEXT NOT NULL REFERENCES notification_targets(id),
                    idempotency_key TEXT NOT NULL,
                    attempt_no INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL,
                    error TEXT NOT NULL DEFAULT '',
                    response_summary TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    UNIQUE(idempotency_key, target_id, attempt_no)
                );

                CREATE UNIQUE INDEX IF NOT EXISTS uq_delivery_success
                    ON delivery_attempts(idempotency_key, target_id)
                    WHERE status='delivered';

                CREATE TABLE IF NOT EXISTS delivery_claims (
                    idempotency_key TEXT NOT NULL,
                    target_id TEXT NOT NULL REFERENCES notification_targets(id),
                    workspace_id TEXT NOT NULL,
                    report_id TEXT NOT NULL REFERENCES decision_reports(id),
                    owner_id TEXT NOT NULL,
                    fence_token TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    lease_until TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(idempotency_key, target_id)
                );

                CREATE TABLE IF NOT EXISTS report_share_links (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    report_id TEXT NOT NULL REFERENCES decision_reports(id),
                    token_hash TEXT NOT NULL UNIQUE,
                    expires_at TEXT NOT NULL,
                    revoked INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS decision_eligibility (
                    portfolio_version_id TEXT PRIMARY KEY REFERENCES decision_versions(id),
                    preview_ok INTEGER NOT NULL DEFAULT 0,
                    validation_ok INTEGER NOT NULL DEFAULT 0,
                    health_ok INTEGER NOT NULL DEFAULT 0,
                    adapter_ok INTEGER NOT NULL DEFAULT 0,
                    target_ok INTEGER NOT NULL DEFAULT 0,
                    reasons_json TEXT NOT NULL,
                    checked_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS decision_validations (
                    portfolio_version_id TEXT PRIMARY KEY REFERENCES decision_versions(id),
                    validation_json TEXT NOT NULL,
                    validation_hash TEXT NOT NULL,
                    checked_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS decision_validation_evidence (
                    id TEXT PRIMARY KEY,
                    portfolio_version_id TEXT NOT NULL REFERENCES decision_versions(id),
                    validation_json TEXT NOT NULL,
                    validation_hash TEXT NOT NULL,
                    checked_at TEXT NOT NULL,
                    UNIQUE(portfolio_version_id, validation_hash)
                );
                CREATE INDEX IF NOT EXISTS idx_decision_validation_evidence_version
                    ON decision_validation_evidence(portfolio_version_id, checked_at);

                CREATE TABLE IF NOT EXISTS decision_commands (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    portfolio_id TEXT,
                    command_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    owner_id TEXT,
                    lease_until TEXT,
                    attempt_no INTEGER NOT NULL DEFAULT 0,
                    result_json TEXT,
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    UNIQUE(workspace_id, idempotency_key)
                );
                CREATE INDEX IF NOT EXISTS idx_decision_commands_claim
                    ON decision_commands(status, lease_until, created_at);
                CREATE INDEX IF NOT EXISTS idx_decision_commands_workspace
                    ON decision_commands(workspace_id, created_at);
                """
            )
            self._migrate_schema(conn)

    @staticmethod
    def _migrate_schema(conn: sqlite3.Connection) -> None:
        """Upgrade the first local schema without discarding audit rows."""

        portfolio_columns = {row[1] for row in conn.execute("PRAGMA table_info(decision_portfolios)").fetchall()}
        if "auto_push_enabled" not in portfolio_columns:
            conn.execute("ALTER TABLE decision_portfolios ADD COLUMN auto_push_enabled INTEGER NOT NULL DEFAULT 0")

        decision_columns = {row[1] for row in conn.execute("PRAGMA table_info(decisions)").fetchall()}
        if "previous_action" not in decision_columns:
            conn.execute("ALTER TABLE decisions ADD COLUMN previous_action TEXT")
        if "confirmed" not in decision_columns:
            conn.execute("ALTER TABLE decisions ADD COLUMN confirmed INTEGER NOT NULL DEFAULT 0")
        if "confirming_bar_end" not in decision_columns:
            conn.execute("ALTER TABLE decisions ADD COLUMN confirming_bar_end TEXT")

        delivery_columns = {row[1] for row in conn.execute("PRAGMA table_info(delivery_attempts)").fetchall()}
        if delivery_columns and "attempt_no" not in delivery_columns:
            conn.execute("ALTER TABLE delivery_attempts RENAME TO delivery_attempts_legacy")
            conn.execute(
                """
                CREATE TABLE delivery_attempts (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    report_id TEXT NOT NULL REFERENCES decision_reports(id),
                    target_id TEXT NOT NULL REFERENCES notification_targets(id),
                    idempotency_key TEXT NOT NULL,
                    attempt_no INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL,
                    error TEXT NOT NULL DEFAULT '',
                    response_summary TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    UNIQUE(idempotency_key, target_id, attempt_no)
                )
                """
            )
            conn.execute(
                """
                INSERT INTO delivery_attempts(
                    id, workspace_id, report_id, target_id, idempotency_key,
                    attempt_no, status, error, response_summary, created_at
                )
                SELECT id, workspace_id, report_id, target_id, idempotency_key,
                       1, status, error, response_summary, created_at
                FROM delivery_attempts_legacy
                """
            )
            conn.execute("DROP TABLE delivery_attempts_legacy")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_delivery_success ON delivery_attempts(idempotency_key, target_id) WHERE status='delivered'"
        )
        eligibility_columns = {row[1] for row in conn.execute("PRAGMA table_info(decision_eligibility)").fetchall()}
        if eligibility_columns and "target_ok" not in eligibility_columns:
            conn.execute("ALTER TABLE decision_eligibility ADD COLUMN target_ok INTEGER NOT NULL DEFAULT 0")

        delivery_claim_columns = {row[1] for row in conn.execute("PRAGMA table_info(delivery_claims)").fetchall()}
        if delivery_claim_columns and "fence_token" not in delivery_claim_columns:
            conn.execute("ALTER TABLE delivery_claims ADD COLUMN fence_token TEXT NOT NULL DEFAULT ''")

        # Preserve validation rows written by the first schema while making the
        # evidence history append-only.  The current pointer remains for old
        # callers; the evidence table is the audit record.
        conn.execute(
            """
            INSERT OR IGNORE INTO decision_validation_evidence(
                id, portfolio_version_id, validation_json, validation_hash, checked_at
            )
            SELECT lower(hex(randomblob(16))), portfolio_version_id,
                   validation_json, validation_hash, checked_at
            FROM decision_validations
            """
        )

    @staticmethod
    def _decode(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        value = dict(row)
        for key in tuple(value):
            if key.endswith("_json"):
                try:
                    value[key[:-5]] = json.loads(value.pop(key))
                except (TypeError, json.JSONDecodeError):
                    value[key[:-5]] = {}
        for key in ("enabled", "auto_push_enabled", "valid", "stale", "risk_veto", "confirmed", "revoked", "preview_ok", "validation_ok", "health_ok", "adapter_ok", "target_ok"):
            if key in value:
                value[key] = bool(value[key])
        return value

    def _attach_report_context(self, conn: sqlite3.Connection, report: dict[str, Any]) -> dict[str, Any]:
        """Project append-only AI and delivery facts beside a frozen report."""

        report_id = str(report.get("report_id") or report.get("id") or "")
        if not report_id:
            return report
        report["ai_commentary"] = [
            self._decode(row) or {}
            for row in conn.execute(
                "SELECT id, report_id, model, prompt_hash, input_hash, content, created_at FROM ai_commentary WHERE report_id=? ORDER BY created_at, id",
                (report_id,),
            ).fetchall()
        ]
        report["delivery_attempts"] = [
            self._decode(row) or {}
            for row in conn.execute(
                """
                SELECT d.id, d.report_id, d.target_id, t.channel AS channel,
                       d.attempt_no, d.status, d.error, d.response_summary, d.created_at
                FROM delivery_attempts d
                LEFT JOIN notification_targets t ON t.id=d.target_id
                WHERE d.report_id=?
                ORDER BY d.created_at DESC, d.attempt_no DESC
                LIMIT 100
                """,
                (report_id,),
            ).fetchall()
        ]
        report["ai_commentary_status"] = "available" if report["ai_commentary"] else "not_available"
        return report

    def enqueue_command(
        self,
        workspace_id: str,
        command_type: str,
        payload: Mapping[str, Any] | None,
        idempotency_key: str,
        *,
        portfolio_id: str | None = None,
    ) -> dict[str, Any]:
        """Persist a control-plane request for the single Worker owner.

        The command row is the durable seam between HTTP and execution.  A
        retry with the same workspace-scoped key returns the original command,
        while a different payload is rejected instead of silently reusing it.
        """

        allowed = {
            "decision.preview",
            "decision.analyze",
            "decision.validate",
            "decision.enable_auto_push",
            "decision.disable_auto_push",
            "notification.test_target",
        }
        if command_type not in allowed:
            raise ValueError("unsupported_decision_command")
        clean_key = str(idempotency_key or "").strip()
        if not clean_key:
            raise ValueError("command_idempotency_key_required")
        body = dict(payload or {})
        body_json = stable_json(body)
        command_id = str(uuid.uuid4())
        now = iso_now()
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM decision_commands WHERE workspace_id=? AND idempotency_key=?",
                (workspace_id, clean_key),
            ).fetchone()
            if existing is not None:
                if existing["command_type"] != command_type or existing["payload_json"] != body_json:
                    raise ValueError("command_idempotency_conflict")
                return self._decode(existing) or {}
            if portfolio_id:
                portfolio = conn.execute(
                    "SELECT id FROM decision_portfolios WHERE id=? AND workspace_id=?",
                    (portfolio_id, workspace_id),
                ).fetchone()
                if portfolio is None:
                    raise KeyError("command_portfolio_not_found")
            target_id = body.get("target_id")
            if target_id:
                target = conn.execute(
                    "SELECT id FROM notification_targets WHERE id=? AND workspace_id=?",
                    (str(target_id), workspace_id),
                ).fetchone()
                if target is None:
                    raise KeyError("command_target_not_found")
            conn.execute(
                """
                INSERT INTO decision_commands(
                    id, workspace_id, portfolio_id, command_type, payload_json,
                    idempotency_key, status, created_at
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (command_id, workspace_id, portfolio_id, command_type, body_json, clean_key, "queued", now),
            )
            return self._decode(conn.execute("SELECT * FROM decision_commands WHERE id=?", (command_id,)).fetchone()) or {}

    def get_command(self, workspace_id: str, command_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            return self._decode(
                conn.execute(
                    "SELECT * FROM decision_commands WHERE workspace_id=? AND id=?",
                    (workspace_id, command_id),
                ).fetchone()
            )

    def list_commands(self, workspace_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM decision_commands WHERE workspace_id=? ORDER BY created_at DESC LIMIT ?",
                (workspace_id, max(1, min(int(limit), 200))),
            ).fetchall()
            return [self._decode(row) or {} for row in rows]

    def claim_commands(
        self,
        owner_id: str,
        *,
        limit: int = 20,
        lease_seconds: int = 300,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Claim queued commands, recovering only expired Worker leases."""

        if not owner_id:
            raise ValueError("command_owner_id_required")
        current = now or utc_now()
        now_text = current.isoformat(timespec="seconds")
        lease_until = (current + timedelta(seconds=max(1, lease_seconds))).isoformat(timespec="seconds")
        claimed: list[dict[str, Any]] = []
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """
                SELECT id FROM decision_commands
                WHERE status='queued'
                   OR (status='running' AND lease_until IS NOT NULL AND lease_until<=?)
                ORDER BY created_at
                LIMIT ?
                """,
                (now_text, max(1, min(int(limit), 100))),
            ).fetchall()
            for row in rows:
                updated = conn.execute(
                    """
                    UPDATE decision_commands
                    SET status='running', owner_id=?, lease_until=?,
                        attempt_no=attempt_no+1, started_at=COALESCE(started_at, ?)
                    WHERE id=? AND (
                        status='queued'
                        OR (status='running' AND lease_until IS NOT NULL AND lease_until<=?)
                    )
                    """,
                    (owner_id, lease_until, now_text, row["id"], now_text),
                ).rowcount
                if updated == 1:
                    claimed_row = conn.execute("SELECT * FROM decision_commands WHERE id=?", (row["id"],)).fetchone()
                    decoded = self._decode(claimed_row)
                    if decoded:
                        claimed.append(decoded)
        return claimed

    def complete_command(
        self,
        command_id: str,
        owner_id: str,
        result: Mapping[str, Any] | None = None,
        *,
        status: str = "completed",
    ) -> dict[str, Any]:
        if status not in {"completed", "rejected"}:
            raise ValueError("invalid_command_completion_status")
        with self._connection() as conn:
            updated = conn.execute(
                """
                UPDATE decision_commands
                SET status=?, result_json=?, error='', lease_until=NULL, completed_at=?
                WHERE id=? AND owner_id=? AND status='running'
                """,
                (status, stable_json(result or {}), iso_now(), command_id, owner_id),
            ).rowcount
            if updated != 1:
                raise RuntimeError("decision_command_not_owned")
            return self._decode(conn.execute("SELECT * FROM decision_commands WHERE id=?", (command_id,)).fetchone()) or {}

    def renew_command(
        self,
        command_id: str,
        owner_id: str,
        *,
        lease_seconds: int = 300,
        now: datetime | None = None,
    ) -> bool:
        """Extend a running command lease only for its current owner."""

        current = now or utc_now()
        lease_until = current + timedelta(seconds=max(1, int(lease_seconds)))
        with self._connection() as conn:
            updated = conn.execute(
                """
                UPDATE decision_commands
                SET lease_until=?
                WHERE id=? AND owner_id=? AND status='running'
                """,
                (lease_until.isoformat(timespec="seconds"), command_id, owner_id),
            ).rowcount
            return updated == 1

    def fail_command(self, command_id: str, owner_id: str, error: str) -> dict[str, Any]:
        with self._connection() as conn:
            updated = conn.execute(
                """
                UPDATE decision_commands
                SET status='failed', error=?, lease_until=NULL, completed_at=?
                WHERE id=? AND owner_id=? AND status='running'
                """,
                (str(error or "command_failed")[:2000], iso_now(), command_id, owner_id),
            ).rowcount
            if updated != 1:
                raise RuntimeError("decision_command_not_owned")
            return self._decode(conn.execute("SELECT * FROM decision_commands WHERE id=?", (command_id,)).fetchone()) or {}

    def create_portfolio(self, workspace_id: str, market: str, name: str) -> dict[str, Any]:
        market_code = _canonical_market(market)
        portfolio_id = str(uuid.uuid4())
        with self._connection() as conn:
            conn.execute("INSERT INTO decision_portfolios(id,workspace_id,market,name,created_at) VALUES(?,?,?,?,?)", (portfolio_id, workspace_id, market_code, name.strip() or "未命名组合", iso_now()))
        return self.get_portfolio(workspace_id, portfolio_id) or {}

    def list_portfolios(self, workspace_id: str, market: str | None = None) -> list[dict[str, Any]]:
        with self._connection() as conn:
            sql = "SELECT * FROM decision_portfolios WHERE workspace_id=?"
            params: list[Any] = [workspace_id]
            if market:
                sql += " AND market=?"
                params.append(_canonical_market(market))
            rows = conn.execute(sql + " ORDER BY created_at", params).fetchall()
            return [self._decode(row) or {} for row in rows]

    def list_portfolios_for_worker(
        self,
        workspace_automation_enabled: Callable[[str], bool] | None = None,
    ) -> list[dict[str, Any]]:
        """Return portfolios eligible for the current worker cycle.

        Portfolio-level opt-in is intentionally insufficient.  The workspace
        settings database is the authority for the Worker and auto-push
        switches, so a missing provider is fail-closed rather than treating a
        stale portfolio flag as permission to run.
        """

        if workspace_automation_enabled is None:
            return []
        with self._connection() as conn:
            rows = conn.execute("SELECT * FROM decision_portfolios WHERE enabled=1 AND auto_push_enabled=1 ORDER BY workspace_id, created_at").fetchall()
        portfolios: list[dict[str, Any]] = []
        for row in rows:
            try:
                enabled = bool(workspace_automation_enabled(str(row["workspace_id"])))
            except Exception:
                enabled = False
            if enabled:
                portfolios.append(self._decode(row) or {})
        return portfolios

    def get_portfolio(self, workspace_id: str, portfolio_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM decision_portfolios WHERE id=? AND workspace_id=?", (portfolio_id, workspace_id)).fetchone()
            return self._decode(row)

    def set_auto_push(self, workspace_id: str, portfolio_id: str, enabled: bool) -> dict[str, Any] | None:
        with self._connection() as conn:
            conn.execute(
                "UPDATE decision_portfolios SET auto_push_enabled=? WHERE id=? AND workspace_id=?",
                (int(bool(enabled)), portfolio_id, workspace_id),
            )
            return self._decode(conn.execute("SELECT * FROM decision_portfolios WHERE id=? AND workspace_id=?", (portfolio_id, workspace_id)).fetchone())

    def get_portfolio_any(self, portfolio_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            return self._decode(conn.execute("SELECT * FROM decision_portfolios WHERE id=?", (portfolio_id,)).fetchone())

    def list_members(self, workspace_id: str, portfolio_id: str) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute("SELECT m.* FROM decision_memberships m JOIN decision_portfolios p ON p.id=m.portfolio_id WHERE p.id=? AND p.workspace_id=? ORDER BY m.created_at", (portfolio_id, workspace_id)).fetchall()
            return [self._decode(row) or {} for row in rows]

    def add_member(self, workspace_id: str, portfolio_id: str, symbol: str, name: str = "") -> dict[str, Any]:
        portfolio = self.get_portfolio(workspace_id, portfolio_id)
        if not portfolio:
            raise KeyError("portfolio_not_found")
        instrument_id, display_symbol = _canonical_instrument(str(portfolio["market"]), symbol)
        member_id = str(uuid.uuid4())
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM decision_memberships WHERE portfolio_id=? AND instrument_id=?",
                (portfolio_id, instrument_id),
            ).fetchone()
            # Accept an old pre-normalization row on read so a migration does
            # not create a second membership for the same visible symbol.
            if row is None and display_symbol != str(symbol).strip():
                row = conn.execute(
                    "SELECT * FROM decision_memberships WHERE portfolio_id=? AND instrument_id=?",
                    (portfolio_id, str(symbol).strip()),
                ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO decision_memberships(id,portfolio_id,instrument_id,symbol,name,created_at) VALUES(?,?,?,?,?,?)",
                    (member_id, portfolio_id, instrument_id, display_symbol, name.strip(), iso_now()),
                )
                row = conn.execute(
                    "SELECT * FROM decision_memberships WHERE portfolio_id=? AND instrument_id=?",
                    (portfolio_id, instrument_id),
                ).fetchone()
            elif not bool(row["enabled"]):
                # Re-adding a historical member re-enables the same immutable
                # identity instead of creating a second row that would split
                # the audit trail.
                conn.execute(
                    "UPDATE decision_memberships SET enabled=1, name=? WHERE id=?",
                    (name.strip() or row["name"], row["id"]),
                )
                row = conn.execute("SELECT * FROM decision_memberships WHERE id=?", (row["id"],)).fetchone()
            return self._decode(row) or {}

    def remove_member(self, workspace_id: str, portfolio_id: str, symbol: str) -> bool:
        portfolio = self.get_portfolio(workspace_id, portfolio_id)
        if not portfolio:
            return False
        instrument_id, display_symbol = _canonical_instrument(str(portfolio["market"]), symbol)
        with self._connection() as conn:
            deleted = conn.execute(
                "UPDATE decision_memberships SET enabled=0 WHERE portfolio_id=? AND instrument_id=? AND enabled=1",
                (portfolio_id, instrument_id),
            ).rowcount
            if deleted == 0 and display_symbol != str(symbol).strip():
                deleted = conn.execute(
                    "UPDATE decision_memberships SET enabled=0 WHERE portfolio_id=? AND instrument_id=? AND enabled=1",
                    (portfolio_id, str(symbol).strip()),
                ).rowcount
            return deleted == 1

    def create_version(self, workspace_id: str, portfolio_id: str, config: Mapping[str, Any]) -> dict[str, Any]:
        portfolio = self.get_portfolio(workspace_id, portfolio_id)
        if not portfolio:
            raise KeyError("portfolio_not_found")
        strategies = [item for item in (config.get("strategies") or []) if isinstance(item, Mapping)]
        if not strategies:
            strategies = [
                {"strategy_name": "momentum", "version": "builtin-v1", "weight": 0.4, "enabled": True},
                {"strategy_name": "trend", "version": "builtin-v1", "weight": 0.35, "enabled": True},
                {"strategy_name": "mean_reversion", "version": "builtin-v1", "weight": 0.25, "enabled": True},
                {"strategy_name": "drawdown_risk", "version": "builtin-v1", "weight": 0, "enabled": True, "is_risk_veto": True},
            ]
        def nonnegative_weight(value: Any, *, required: bool) -> float:
            if isinstance(value, bool) or value is None or str(value).strip() == "":
                if required:
                    raise ValueError("strategy_weight_required")
                return 0.0
            try:
                number = float(value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("strategy_weight_invalid") from exc
            if number < 0 or not math.isfinite(number):
                raise ValueError("strategy_weight_invalid")
            return number

        names: set[str] = set()
        normalized_input: list[dict[str, Any]] = []
        for item in strategies:
            copy = dict(item)
            name = str(copy.get("strategy_name") or copy.get("name") or "").strip()
            if not name:
                raise ValueError("strategy_name_required")
            if name in names:
                raise ValueError("duplicate_strategy_name")
            names.add(name)
            copy["strategy_name"] = name
            if not isinstance(copy.get("enabled", True), bool):
                raise ValueError("strategy_enabled_invalid")
            risk_veto = bool(copy.get("is_risk_veto", False))
            copy["is_risk_veto"] = risk_veto
            copy["weight"] = nonnegative_weight(copy.get("weight"), required=not risk_veto)
            normalized_input.append(copy)

        normal = [item for item in normalized_input if item.get("enabled", True) and not item.get("is_risk_veto")]
        total = sum(float(item["weight"]) for item in normal)
        if total <= 0:
            raise ValueError("at_least_one_weighted_strategy_required")
        normalized = []
        for item in normalized_input:
            copy = dict(item)
            if not copy.get("is_risk_veto"):
                copy["weight"] = round(float(copy["weight"]) / total, 10)
            else:
                copy["weight"] = 0.0
            normalized.append(copy)
        for key in ("thresholds", "validation", "risk_rules"):
            if config.get(key) is not None and not isinstance(config.get(key), Mapping):
                raise ValueError(f"{key}_must_be_mapping")
        frozen = {"strategies": normalized, "thresholds": dict(config.get("thresholds") or {}), "validation": dict(config.get("validation") or {}), "risk_rules": dict(config.get("risk_rules") or {})}
        cfg_hash = content_hash(frozen)
        version_id = str(uuid.uuid4())
        with self._connection() as conn:
            # MAX(version_no)+1 is only safe while the allocation and insert
            # are serialized.  SQLite's immediate transaction is the local
            # single-writer seam for this immutable version sequence.
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute("SELECT * FROM decision_versions WHERE portfolio_id=? AND config_hash=?", (portfolio_id, cfg_hash)).fetchone()
            if existing:
                return self._decode(existing) or {}
            number = (conn.execute("SELECT COALESCE(MAX(version_no),0)+1 AS n FROM decision_versions WHERE portfolio_id=?", (portfolio_id,)).fetchone()["n"])
            conn.execute("INSERT INTO decision_versions(id,portfolio_id,version_no,config_json,config_hash,created_at) VALUES(?,?,?,?,?,?)", (version_id, portfolio_id, number, stable_json(frozen), cfg_hash, iso_now()))
            conn.execute("UPDATE decision_portfolios SET current_version_id=? WHERE id=?", (version_id, portfolio_id))
            row = conn.execute("SELECT * FROM decision_versions WHERE id=?", (version_id,)).fetchone()
            return self._decode(row) or {}

    def get_version(self, workspace_id: str, version_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute("SELECT v.* FROM decision_versions v JOIN decision_portfolios p ON p.id=v.portfolio_id WHERE v.id=? AND p.workspace_id=?", (version_id, workspace_id)).fetchone()
            return self._decode(row)

    def get_current_version(self, workspace_id: str, portfolio_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute("SELECT v.* FROM decision_versions v JOIN decision_portfolios p ON p.current_version_id=v.id WHERE p.id=? AND p.workspace_id=?", (portfolio_id, workspace_id)).fetchone()
            return self._decode(row)

    @staticmethod
    def _require_snapshot_version(conn: sqlite3.Connection, workspace_id: str, version_id: str) -> sqlite3.Row:
        row = conn.execute(
            """
            SELECT v.id, v.portfolio_id, p.workspace_id
            FROM decision_versions v
            JOIN decision_portfolios p ON p.id=v.portfolio_id
            WHERE v.id=? AND p.workspace_id=?
            """,
            (version_id, workspace_id),
        ).fetchone()
        if row is None:
            raise KeyError("portfolio_version_not_found")
        return row

    @staticmethod
    def _require_delivery_references(
        conn: sqlite3.Connection,
        workspace_id: str,
        report_id: str,
        target_id: str,
    ) -> tuple[sqlite3.Row, sqlite3.Row]:
        report = conn.execute(
            """
            SELECT r.id, run.workspace_id, run.portfolio_id
            FROM decision_reports r
            JOIN decision_runs run ON run.id=r.decision_run_id
            WHERE r.id=?
            """,
            (report_id,),
        ).fetchone()
        if report is None:
            raise KeyError("report_not_found")
        target = conn.execute(
            "SELECT id, workspace_id FROM notification_targets WHERE id=?",
            (target_id,),
        ).fetchone()
        if target is None:
            raise KeyError("notification_target_not_found")
        if report["workspace_id"] != workspace_id or target["workspace_id"] != workspace_id:
            raise ValueError("delivery_reference_workspace_mismatch")
        return report, target

    def create_snapshot(self, workspace_id: str, version_id: str, payload: Mapping[str, Any], source: str, quality_status: str) -> dict[str, Any]:
        snapshot_id = str(uuid.uuid4())
        payload_hash = content_hash(payload)
        with self._connection() as conn:
            self._require_snapshot_version(conn, workspace_id, version_id)
            existing = conn.execute("SELECT * FROM decision_snapshots WHERE portfolio_version_id=? AND payload_hash=?", (version_id, payload_hash)).fetchone()
            if existing:
                if existing["source"] != source or existing["quality_status"] != quality_status:
                    raise RuntimeError("decision_snapshot_immutable_conflict")
                return self._decode(existing) or {}
            conn.execute("INSERT INTO decision_snapshots(id,workspace_id,portfolio_version_id,payload_json,payload_hash,source,quality_status,created_at) VALUES(?,?,?,?,?,?,?,?)", (snapshot_id, workspace_id, version_id, stable_json(payload), payload_hash, source, quality_status, iso_now()))
            return self._decode(conn.execute("SELECT * FROM decision_snapshots WHERE id=?", (snapshot_id,)).fetchone()) or {}

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            return self._decode(conn.execute("SELECT * FROM decision_snapshots WHERE id=?", (snapshot_id,)).fetchone())

    def create_run(self, workspace_id: str, portfolio_id: str, version_id: str, snapshot_id: str, run_key: str, trigger: str, report_type: str) -> dict[str, Any]:
        run_key = str(run_key or "").strip()
        if not run_key:
            raise ValueError("decision_run_key_required")
        if not str(trigger or "").strip() or not str(report_type or "").strip():
            raise ValueError("decision_run_type_required")
        run_id = str(uuid.uuid4())
        with self._connection() as conn:
            portfolio = conn.execute("SELECT id FROM decision_portfolios WHERE id=? AND workspace_id=?", (portfolio_id, workspace_id)).fetchone()
            if portfolio is None:
                raise KeyError("portfolio_not_found")
            version = conn.execute("SELECT id, portfolio_id FROM decision_versions WHERE id=?", (version_id,)).fetchone()
            if version is None:
                raise KeyError("portfolio_version_not_found")
            snapshot = conn.execute("SELECT id, workspace_id, portfolio_version_id FROM decision_snapshots WHERE id=?", (snapshot_id,)).fetchone()
            if snapshot is None:
                raise KeyError("decision_snapshot_not_found")
            if version["portfolio_id"] != portfolio_id or snapshot["workspace_id"] != workspace_id or snapshot["portfolio_version_id"] != version_id:
                raise ValueError("decision_run_reference_mismatch")
            conn.execute("INSERT OR IGNORE INTO decision_runs(id,workspace_id,portfolio_id,portfolio_version_id,snapshot_id,run_key,trigger,report_type,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (run_id, workspace_id, portfolio_id, version_id, snapshot_id, run_key, trigger, report_type, "running", iso_now()))
            row = conn.execute("SELECT * FROM decision_runs WHERE run_key=?", (run_key,)).fetchone()
            if row is None:
                raise RuntimeError("decision_run_not_persisted")
            if (
                row["workspace_id"] != workspace_id
                or row["portfolio_id"] != portfolio_id
                or row["portfolio_version_id"] != version_id
                or row["snapshot_id"] != snapshot_id
                or row["trigger"] != trigger
                or row["report_type"] != report_type
            ):
                raise ValueError("decision_run_key_conflict")
            return self._decode(row) or {}

    def get_run_by_key(self, workspace_id: str, run_key: str) -> dict[str, Any] | None:
        """Return one immutable run identity before rebuilding its inputs.

        Worker retries must look up the durable run first.  Reconstructing a
        snapshot before this lookup can observe a different member state after
        a crash and turn one command into a different decision.  The key is
        deliberately scoped by workspace at this API boundary even though
        older databases retain a global uniqueness constraint.
        """

        clean_key = str(run_key or "").strip()
        if not clean_key:
            return None
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM decision_runs WHERE workspace_id=? AND run_key=?",
                (workspace_id, clean_key),
            ).fetchone()
            return self._decode(row)

    def complete_run(self, run_id: str, status: str = "completed") -> None:
        with self._connection() as conn:
            conn.execute("UPDATE decision_runs SET status=? WHERE id=? AND status='running'", (status, run_id))

    def get_run(self, workspace_id: str, run_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM decision_runs WHERE id=? AND workspace_id=?",
                (run_id, workspace_id),
            ).fetchone()
            return self._decode(row)

    def latest_decision(
        self,
        membership_id: str,
        *,
        before_run_id: str | None = None,
        automatic_only: bool = False,
    ) -> dict[str, Any] | None:
        with self._connection() as conn:
            sql = "SELECT d.* FROM decisions d JOIN decision_runs r ON r.id=d.decision_run_id WHERE d.membership_id=? AND r.status='completed'"
            params: list[Any] = [membership_id]
            if before_run_id:
                sql += " AND r.id<>?"
                params.append(before_run_id)
            if automatic_only:
                sql += " AND r.trigger NOT IN ('manual', 'preview')"
            row = conn.execute(sql + " ORDER BY d.created_at DESC LIMIT 1", params).fetchone()
            return self._decode(row)

    def get_member_state(self, membership_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM decision_member_states WHERE membership_id=?",
                (membership_id,),
            ).fetchone()
            return self._decode(row)

    def update_member_state(
        self,
        membership_id: str,
        *,
        action: str,
        valid: bool,
        stale: bool,
        quality_status: str,
        trade_date: str | None,
    ) -> dict[str, Any]:
        """Persist the member quality lifecycle beside immutable decisions.

        The latest valid action is intentionally separate from the latest row:
        a transient invalid feed must not erase the action that a user last
        received.  ``invalid_since_trade_date`` is the boundary used to turn a
        pending invalid state into ``decision_invalid`` on the next trading
        day.
        """

        clean_action = str(action or "decision_invalid")
        clean_quality = str(quality_status or "unknown")
        clean_date = str(trade_date or "") or None
        with self._connection() as conn:
            existing = conn.execute(
                "SELECT * FROM decision_member_states WHERE membership_id=?",
                (membership_id,),
            ).fetchone()
            last_valid_action = existing["last_valid_action"] if existing else None
            last_valid_trade_date = existing["last_valid_trade_date"] if existing else None
            invalid_since = existing["invalid_since_trade_date"] if existing else None
            if clean_quality == "invalid":
                invalid_since = invalid_since or clean_date
            else:
                invalid_since = None
            if valid and not stale and clean_quality != "invalid" and clean_action not in {"stale", "decision_invalid"}:
                last_valid_action = clean_action
                last_valid_trade_date = clean_date or last_valid_trade_date
            conn.execute(
                """
                INSERT INTO decision_member_states(
                    membership_id, last_valid_action, last_valid_trade_date,
                    invalid_since_trade_date, current_action, quality_status,
                    updated_at
                ) VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(membership_id) DO UPDATE SET
                    last_valid_action=excluded.last_valid_action,
                    last_valid_trade_date=excluded.last_valid_trade_date,
                    invalid_since_trade_date=excluded.invalid_since_trade_date,
                    current_action=excluded.current_action,
                    quality_status=excluded.quality_status,
                    updated_at=excluded.updated_at
                """,
                (
                    membership_id,
                    last_valid_action,
                    last_valid_trade_date,
                    invalid_since,
                    clean_action,
                    clean_quality,
                    iso_now(),
                ),
            )
            return self._decode(
                conn.execute(
                    "SELECT * FROM decision_member_states WHERE membership_id=?",
                    (membership_id,),
                ).fetchone()
            ) or {}

    def record_state_event(
        self,
        *,
        portfolio_id: str,
        membership_id: str,
        action: str,
        confirming_bar_end: str,
        portfolio_version_id: str,
        decision_id: str,
        event_type: str,
    ) -> bool:
        """Insert a state event once for its full immutable identity."""

        if not str(confirming_bar_end or "").strip():
            return False
        with self._connection() as conn:
            decision = conn.execute(
                """
                SELECT d.id, d.membership_id, r.portfolio_id, r.portfolio_version_id, r.workspace_id
                FROM decisions d
                JOIN decision_runs r ON r.id=d.decision_run_id
                WHERE d.id=?
                """,
                (decision_id,),
            ).fetchone()
            membership = conn.execute(
                "SELECT id, portfolio_id FROM decision_memberships WHERE id=?",
                (membership_id,),
            ).fetchone()
            portfolio = conn.execute(
                "SELECT id, workspace_id FROM decision_portfolios WHERE id=?",
                (portfolio_id,),
            ).fetchone()
            version = conn.execute(
                "SELECT id, portfolio_id FROM decision_versions WHERE id=?",
                (portfolio_version_id,),
            ).fetchone()
            if (
                decision is None
                or membership is None
                or portfolio is None
                or version is None
                or decision["membership_id"] != membership_id
                or decision["portfolio_id"] != portfolio_id
                or decision["portfolio_version_id"] != portfolio_version_id
                or membership["portfolio_id"] != portfolio_id
                or version["portfolio_id"] != portfolio_id
                or decision["workspace_id"] != portfolio["workspace_id"]
            ):
                raise ValueError("decision_state_event_reference_mismatch")
            inserted = conn.execute(
                """
                INSERT OR IGNORE INTO decision_state_events(
                    id, portfolio_id, membership_id, action, confirming_bar_end,
                    portfolio_version_id, decision_id, event_type, created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    str(uuid.uuid4()),
                    portfolio_id,
                    membership_id,
                    str(action),
                    str(confirming_bar_end),
                    portfolio_version_id,
                    decision_id,
                    str(event_type),
                    iso_now(),
                ),
            ).rowcount
            return inserted == 1

    def record_decision(self, run_id: str, membership_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        decision_id = str(uuid.uuid4())
        payload_hash = content_hash(payload)
        with self._connection() as conn:
            run = conn.execute("SELECT id, workspace_id, portfolio_id, status FROM decision_runs WHERE id=?", (run_id,)).fetchone()
            if run is None:
                raise KeyError("decision_run_not_found")
            if run["status"] != "running":
                raise RuntimeError("decision_run_not_writable")
            membership = conn.execute(
                """
                SELECT m.id, m.portfolio_id, m.symbol, p.workspace_id
                FROM decision_memberships m
                JOIN decision_portfolios p ON p.id=m.portfolio_id
                WHERE m.id=?
                """,
                (membership_id,),
            ).fetchone()
            if membership is None:
                raise KeyError("portfolio_membership_not_found")
            if membership["portfolio_id"] != run["portfolio_id"] or membership["workspace_id"] != run["workspace_id"]:
                raise ValueError("decision_membership_run_mismatch")
            symbol = str(payload.get("symbol") or membership["symbol"])
            if symbol != membership["symbol"]:
                raise ValueError("decision_symbol_membership_mismatch")
            existing = conn.execute(
                "SELECT * FROM decisions WHERE decision_run_id=? AND membership_id=?",
                (run_id, membership_id),
            ).fetchone()
            if existing is not None:
                if existing["payload_hash"] != payload_hash:
                    raise RuntimeError("decision_immutable_conflict")
                return self._decode(existing) or {}
            conn.execute("INSERT INTO decisions(id,decision_run_id,membership_id,symbol,action,previous_action,score,valid,stale,risk_veto,confirmed,confirming_bar_end,reason_codes_json,contributions_json,payload_hash,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (decision_id, run_id, membership_id, symbol, payload.get("action", "decision_invalid"), payload.get("previous_action"), payload.get("score"), int(bool(payload.get("valid"))), int(bool(payload.get("stale"))), int(bool(payload.get("risk_veto"))), int(bool(payload.get("confirmed"))), payload.get("confirming_bar_end"), stable_json(payload.get("reason_codes") or []), stable_json(payload.get("contributions") or []), payload_hash, iso_now()))
            return self._decode(conn.execute("SELECT * FROM decisions WHERE decision_run_id=? AND membership_id=?", (run_id, membership_id)).fetchone()) or {}

    def list_decisions(self, run_id: str) -> list[dict[str, Any]]:
        with self._connection() as conn:
            return [self._decode(row) or {} for row in conn.execute("SELECT * FROM decisions WHERE decision_run_id=? ORDER BY symbol", (run_id,)).fetchall()]

    def create_report(self, run: Mapping[str, Any], snapshot: Mapping[str, Any], version: Mapping[str, Any], decisions: list[Mapping[str, Any]], report_type: str | None = None) -> dict[str, Any]:
        report_type = report_type or str(run.get("report_type") or "decision")
        report_id = str(uuid.uuid4())
        with self._connection() as conn:
            # The unique report key is an immutable idempotency boundary.  A
            # deferred transaction would allow two writers to both pass the
            # existence check and make one caller fail with a raw IntegrityError.
            conn.execute("BEGIN IMMEDIATE")
            run_row = conn.execute("SELECT * FROM decision_runs WHERE id=?", (run.get("id"),)).fetchone()
            portfolio_row = conn.execute("SELECT id, workspace_id FROM decision_portfolios WHERE id=?", (run.get("portfolio_id"),)).fetchone()
            version_row = conn.execute("SELECT * FROM decision_versions WHERE id=?", (version.get("id"),)).fetchone()
            snapshot_row = conn.execute("SELECT * FROM decision_snapshots WHERE id=?", (snapshot.get("id"),)).fetchone()
            if run_row is None or portfolio_row is None or version_row is None or snapshot_row is None:
                raise ValueError("decision_report_reference_not_found")
            if any(run.get(key) != run_row[key] for key in ("id", "workspace_id", "portfolio_id", "portfolio_version_id", "snapshot_id", "trigger")):
                raise ValueError("decision_report_run_reference_mismatch")
            if run_row["report_type"] != report_type:
                raise ValueError("decision_report_type_mismatch")
            if portfolio_row["workspace_id"] != run_row["workspace_id"] or portfolio_row["id"] != run_row["portfolio_id"]:
                raise ValueError("decision_report_portfolio_reference_mismatch")
            if version_row["portfolio_id"] != run_row["portfolio_id"]:
                raise ValueError("decision_report_version_reference_mismatch")
            if snapshot_row["workspace_id"] != run_row["workspace_id"] or snapshot_row["portfolio_version_id"] != run_row["portfolio_version_id"] or snapshot_row["id"] != run_row["snapshot_id"]:
                raise ValueError("decision_report_snapshot_reference_mismatch")
            if any(version.get(key) != version_row[key] for key in ("id", "portfolio_id", "config_hash")):
                raise ValueError("decision_report_version_reference_mismatch")
            if any(snapshot.get(key) != snapshot_row[key] for key in ("id", "workspace_id", "portfolio_version_id", "payload_hash", "source", "quality_status")):
                raise ValueError("decision_report_snapshot_reference_mismatch")
            try:
                canonical_payload = json.loads(snapshot_row["payload_json"])
                canonical_config = json.loads(version_row["config_json"])
            except (TypeError, json.JSONDecodeError) as exc:
                raise ValueError("decision_report_reference_corrupt") from exc
            if not isinstance(canonical_payload, Mapping) or content_hash(canonical_payload) != snapshot_row["payload_hash"]:
                raise ValueError("decision_report_snapshot_hash_mismatch")
            if not isinstance(canonical_config, Mapping) or content_hash(canonical_config) != version_row["config_hash"]:
                raise ValueError("decision_report_version_hash_mismatch")

            validation_projection: dict[str, Any] = {
                "status": "not_run",
                "validation_hash": None,
                "evidence_id": None,
                "result": None,
            }
            validation_row = conn.execute(
                "SELECT validation_json, validation_hash FROM decision_validations WHERE portfolio_version_id=?",
                (version_row["id"],),
            ).fetchone()
            if validation_row is not None:
                try:
                    validation_result = json.loads(validation_row["validation_json"])
                except (TypeError, json.JSONDecodeError) as exc:
                    raise ValueError("decision_report_validation_corrupt") from exc
                if not isinstance(validation_result, Mapping):
                    raise ValueError("decision_report_validation_corrupt")
                evidence_row = conn.execute(
                    "SELECT id FROM decision_validation_evidence WHERE portfolio_version_id=? AND validation_hash=?",
                    (version_row["id"], validation_row["validation_hash"]),
                ).fetchone()
                validation_projection = {
                    "status": "passed" if bool(validation_result.get("passed")) else "failed",
                    "validation_hash": validation_row["validation_hash"],
                    "evidence_id": str(evidence_row["id"]) if evidence_row else None,
                    "result": dict(validation_result),
                }

            eligibility_projection: dict[str, Any] = {
                "status": "not_checked",
                "checks": {},
                "reasons": [],
            }
            eligibility_row = conn.execute(
                "SELECT preview_ok, validation_ok, health_ok, adapter_ok, target_ok, reasons_json FROM decision_eligibility WHERE portfolio_version_id=?",
                (version_row["id"],),
            ).fetchone()
            if eligibility_row is not None:
                checks = {
                    "preview_ok": bool(eligibility_row["preview_ok"]),
                    "validation_ok": bool(eligibility_row["validation_ok"]),
                    "health_ok": bool(eligibility_row["health_ok"]),
                    "adapter_ok": bool(eligibility_row["adapter_ok"]),
                    "target_ok": bool(eligibility_row["target_ok"]),
                }
                try:
                    reasons = json.loads(eligibility_row["reasons_json"])
                except (TypeError, json.JSONDecodeError):
                    reasons = []
                eligibility_projection = {
                    "status": "eligible" if all(checks.values()) and not reasons else "blocked",
                    "checks": checks,
                    "reasons": [str(reason) for reason in reasons] if isinstance(reasons, list) else [],
                }

            snapshot_members = canonical_payload.get("members")
            if not isinstance(snapshot_members, list):
                raise ValueError("decision_report_snapshot_membership_missing")
            snapshot_members_by_id: dict[str, str] = {}
            for member in snapshot_members:
                if not isinstance(member, Mapping):
                    raise ValueError("decision_report_snapshot_membership_invalid")
                membership_id = str(member.get("membership_id") or "")
                symbol = str(member.get("symbol") or "")
                if not membership_id or not symbol or membership_id in snapshot_members_by_id:
                    raise ValueError("decision_report_snapshot_membership_invalid")
                snapshot_members_by_id[membership_id] = symbol

            stored_rows = conn.execute("SELECT * FROM decisions WHERE decision_run_id=? ORDER BY symbol", (run_row["id"],)).fetchall()
            supplied_ids = [str(item.get("id") or "") for item in decisions]
            if any(not item_id for item_id in supplied_ids) or len(set(supplied_ids)) != len(supplied_ids):
                raise ValueError("decision_report_decision_reference_invalid")
            stored_ids = [str(row["id"]) for row in stored_rows]
            if len(supplied_ids) != len(stored_ids) or set(supplied_ids) != set(stored_ids):
                raise ValueError("decision_report_decisions_incomplete")
            stored_by_id = {str(row["id"]): row for row in stored_rows}
            stored_members_by_id = {str(row["membership_id"]): str(row["symbol"]) for row in stored_rows}
            if stored_members_by_id != snapshot_members_by_id:
                raise ValueError("decision_report_snapshot_membership_mismatch")
            for item in decisions:
                row = stored_by_id[str(item["id"])]
                canonical = self._decode(row) or {}
                for key in (
                    "decision_run_id",
                    "membership_id",
                    "symbol",
                    "action",
                    "previous_action",
                    "score",
                    "valid",
                    "stale",
                    "risk_veto",
                    "confirmed",
                    "confirming_bar_end",
                    "reason_codes",
                    "contributions",
                    "payload_hash",
                ):
                    if key in item and item[key] != canonical.get(key):
                        raise ValueError("decision_report_decision_reference_mismatch")

            quality_keys = (
                "provider",
                "provider_status",
                "updated_at",
                "captured_at",
                "coverage_pct",
                "field_sources",
                "provider_health",
                "provider_evidence",
                "stale",
                "fallback_reason",
                "adapter",
            )
            data_quality = {key: canonical_payload[key] for key in quality_keys if key in canonical_payload}
            canonical_decisions = [self._decode(row) or {} for row in stored_rows]
            configured_strategies = canonical_config.get("strategies") if isinstance(canonical_config.get("strategies"), list) else []
            strategy_weights = [
                {
                    "strategy_name": item.get("strategy_name"),
                    "version": item.get("version"),
                    "weight": item.get("weight"),
                    "enabled": item.get("enabled", True),
                }
                for item in configured_strategies
                if isinstance(item, Mapping)
            ]
            provider_evidence = canonical_payload.get("provider_evidence")
            if not isinstance(provider_evidence, Mapping):
                provider_evidence = {}
            schedule_context = scheduled_run_context(run_row)
            evidence = {
                "snapshot_id": snapshot_row["id"],
                "source": snapshot_row["source"],
                "payload_hash": snapshot_row["payload_hash"],
                "provider": canonical_payload.get("provider"),
                "provider_status": canonical_payload.get("provider_status"),
                "request_hash": provider_evidence.get("request_hash"),
                "response_hash": provider_evidence.get("response_hash"),
                "collected_at": provider_evidence.get("collected_at") or snapshot_row["created_at"],
                "provider_evidence": dict(provider_evidence),
                "member_count": len(snapshot_members),
                "members": [
                    {
                        "membership_id": member.get("membership_id"),
                        "symbol": member.get("symbol"),
                        "latest_bar": member.get("latest_bar"),
                        "coverage": member.get("coverage"),
                        "coverage_pct": member.get("coverage_pct"),
                        "quality_status": member.get("quality_status"),
                    }
                    for member in snapshot_members
                ],
            }
            body = {
                "report_type": report_type,
                "run_id": run_row["id"],
                "portfolio_id": run_row["portfolio_id"],
                "portfolio_version_id": run_row["portfolio_version_id"],
                "input_hash": snapshot_row["payload_hash"],
                "version_hash": version_row["config_hash"],
                "source": snapshot_row["source"],
                "quality_status": snapshot_row["quality_status"],
                "data_quality": data_quality,
                "market": canonical_payload.get("market"),
                "market_capabilities": canonical_payload.get("adapter") if isinstance(canonical_payload.get("adapter"), Mapping) else {},
                "strategy_weights": strategy_weights,
                "evidence": evidence,
                "validation": validation_projection,
                "eligibility": eligibility_projection,
                "trigger": run_row["trigger"],
                "run_key": run_row["run_key"],
                "schedule_slot": schedule_context["schedule_slot"],
                "trade_date": schedule_context["trade_date"],
                "created_at": iso_now(),
                "decisions": canonical_decisions,
            }
            report_hash = content_hash(report_fingerprint(body))
            existing = conn.execute(
                "SELECT * FROM decision_reports WHERE decision_run_id=? AND report_type=?",
                (run["id"], report_type),
            ).fetchone()
            if existing is not None:
                if existing["report_hash"] != report_hash:
                    raise RuntimeError("decision_report_immutable_conflict")
                return self._attach_report_context(conn, self._decode(existing) or {})
            conn.execute("INSERT INTO decision_reports(id,decision_run_id,report_type,body_json,report_hash,created_at) VALUES(?,?,?,?,?,?)", (report_id, run["id"], report_type, stable_json(body), report_hash, iso_now()))
            row = conn.execute("SELECT * FROM decision_reports WHERE decision_run_id=? AND report_type=?", (run["id"], report_type)).fetchone()
            return self._attach_report_context(conn, self._decode(row) or {})

    def get_report(self, workspace_id: str, report_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute("SELECT r.* FROM decision_reports r JOIN decision_runs run ON run.id=r.decision_run_id WHERE r.id=? AND run.workspace_id=?", (report_id, workspace_id)).fetchone()
            return self._attach_report_context(conn, self._decode(row) or {}) if row else None

    def list_reports(self, workspace_id: str, portfolio_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        with self._connection() as conn:
            sql = "SELECT r.* FROM decision_reports r JOIN decision_runs run ON run.id=r.decision_run_id WHERE run.workspace_id=?"
            params: list[Any] = [workspace_id]
            if portfolio_id:
                sql += " AND run.portfolio_id=?"
                params.append(portfolio_id)
            rows = conn.execute(sql + " ORDER BY r.created_at DESC LIMIT ?", (*params, max(1, min(limit, 200)))).fetchall()
            return [self._attach_report_context(conn, self._decode(row) or {}) for row in rows]

    def latest_report(
        self,
        workspace_id: str,
        portfolio_id: str,
        report_type: str,
        *,
        portfolio_version_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Return the latest completed report for one immutable version.

        Eligibility must inspect the newest preview for the current version,
        rather than finding any older passing preview in a bounded report list.
        """

        sql = """
            SELECT r.*
            FROM decision_reports r
            JOIN decision_runs run ON run.id=r.decision_run_id
            WHERE run.workspace_id=?
              AND run.portfolio_id=?
              AND run.status='completed'
              AND r.report_type=?
        """
        params: list[Any] = [workspace_id, portfolio_id, report_type]
        if portfolio_version_id:
            sql += " AND run.portfolio_version_id=?"
            params.append(portfolio_version_id)
        sql += " ORDER BY r.created_at DESC LIMIT 1"
        with self._connection() as conn:
            row = conn.execute(sql, params).fetchone()
            return self._attach_report_context(conn, self._decode(row) or {}) if row else None

    def list_prepared_reports(
        self,
        workspace_id: str,
        slot: str,
        trade_date: str,
        *,
        portfolio_id: str | None = None,
        portfolio_version_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return only the immutable reports prepared for one delivery slot."""

        trigger = f"scheduled_prepare:{slot}"
        with self._connection() as conn:
            sql = """
                SELECT r.*
                FROM decision_reports r
                JOIN decision_runs run ON run.id=r.decision_run_id
                WHERE run.workspace_id=? AND run.trigger=?
                  AND run.report_type='prepared'
                  AND run.run_key LIKE ?
            """
            params: list[Any] = [workspace_id, trigger, f"prepared:%:{slot}:{trade_date}"]
            if portfolio_id:
                sql += " AND run.portfolio_id=?"
                params.append(portfolio_id)
            if portfolio_version_id:
                sql += " AND run.portfolio_version_id=?"
                params.append(portfolio_version_id)
            rows = conn.execute(sql + " ORDER BY r.created_at", params).fetchall()
            return [self._decode(row) or {} for row in rows]

    def add_ai_commentary(self, workspace_id: str, report_id: str, model: str, prompt: str, input_hash: str, content: str) -> dict[str, Any]:
        if not self.get_report(workspace_id, report_id):
            raise KeyError("report_not_found")
        item_id = str(uuid.uuid4())
        with self._connection() as conn:
            conn.execute("INSERT INTO ai_commentary(id,report_id,model,prompt_hash,input_hash,content,created_at) VALUES(?,?,?,?,?,?,?)", (item_id, report_id, model, content_hash(prompt), input_hash, content, iso_now()))
            row = conn.execute("SELECT * FROM ai_commentary WHERE id=?", (item_id,)).fetchone()
            return self._decode(row) or {}

    def issue_share_link(self, workspace_id: str, report_id: str, ttl_days: int = 7) -> tuple[str, dict[str, Any]]:
        if not self.get_report(workspace_id, report_id):
            raise KeyError("report_not_found")
        raw = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw.encode()).hexdigest()
        link_id = str(uuid.uuid4())
        expires = utc_now() + timedelta(days=max(1, min(ttl_days, 30)))
        with self._connection() as conn:
            conn.execute("INSERT INTO report_share_links(id,workspace_id,report_id,token_hash,expires_at,created_at) VALUES(?,?,?,?,?,?)", (link_id, workspace_id, report_id, token_hash, expires.isoformat(timespec="seconds"), iso_now()))
            row = conn.execute("SELECT * FROM report_share_links WHERE id=?", (link_id,)).fetchone()
        return raw, self._decode(row) or {}

    def resolve_share(self, token: str) -> dict[str, Any] | None:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self._connection() as conn:
            row = conn.execute("SELECT l.*, r.body_json, r.report_hash FROM report_share_links l JOIN decision_reports r ON r.id=l.report_id WHERE l.token_hash=?", (token_hash,)).fetchone()
            if row is None or row["revoked"] or datetime.fromisoformat(row["expires_at"]) <= utc_now():
                return None
            value = self._attach_report_context(conn, self._decode(row) or {})
            value["body"] = json.loads(row["body_json"])
            return value

    def revoke_share(self, workspace_id: str, link_id: str) -> bool:
        with self._connection() as conn:
            return conn.execute("UPDATE report_share_links SET revoked=1 WHERE id=? AND workspace_id=?", (link_id, workspace_id)).rowcount == 1

    def create_target(self, workspace_id: str, channel: str, label: str, config: Mapping[str, Any]) -> dict[str, Any]:
        allowed_keys = {"secret_ref", "endpoint_ref"}
        if any(str(key) not in allowed_keys for key in config):
            raise ValueError("notification_config_field_not_allowed")
        normalized_config = {
            "secret_ref": normalize_protected_ref(config.get("secret_ref"), field="secret_ref", required=True),
            "endpoint_ref": normalize_protected_ref(config.get("endpoint_ref"), field="endpoint_ref", required=False),
        }
        target_id = str(uuid.uuid4())
        with self._connection() as conn:
            conn.execute("INSERT INTO notification_targets(id,workspace_id,channel,label,config_json,created_at) VALUES(?,?,?,?,?,?)", (target_id, workspace_id, channel, label.strip() or channel, stable_json(normalized_config), iso_now()))
            return self._decode(conn.execute("SELECT * FROM notification_targets WHERE id=?", (target_id,)).fetchone()) or {}

    def list_targets(self, workspace_id: str) -> list[dict[str, Any]]:
        with self._connection() as conn:
            return [self._decode(row) or {} for row in conn.execute("SELECT * FROM notification_targets WHERE workspace_id=? ORDER BY created_at", (workspace_id,)).fetchall()]

    def get_target(self, workspace_id: str, target_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            return self._decode(conn.execute("SELECT * FROM notification_targets WHERE workspace_id=? AND id=?", (workspace_id, target_id)).fetchone())

    def mark_target_test(self, workspace_id: str, target_id: str, status: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            conn.execute("UPDATE notification_targets SET test_status=?, last_tested_at=? WHERE id=? AND workspace_id=?", (status, iso_now(), target_id, workspace_id))
            return self._decode(conn.execute("SELECT * FROM notification_targets WHERE id=? AND workspace_id=?", (target_id, workspace_id)).fetchone())

    def create_route(self, workspace_id: str, portfolio_id: str, target_id: str, event_type: str) -> dict[str, Any]:
        route_id = str(uuid.uuid4())
        with self._connection() as conn:
            portfolio = conn.execute("SELECT id, workspace_id FROM decision_portfolios WHERE id=?", (portfolio_id,)).fetchone()
            if portfolio is None:
                raise KeyError("portfolio_not_found")
            target = conn.execute("SELECT id, workspace_id FROM notification_targets WHERE id=?", (target_id,)).fetchone()
            if target is None:
                raise KeyError("notification_target_not_found")
            if portfolio["workspace_id"] != workspace_id or target["workspace_id"] != workspace_id:
                raise ValueError("notification_route_workspace_mismatch")
            conn.execute("INSERT OR IGNORE INTO notification_routes(id,workspace_id,portfolio_id,target_id,event_type,created_at) VALUES(?,?,?,?,?,?)", (route_id, workspace_id, portfolio_id, target_id, event_type, iso_now()))
            return self._decode(conn.execute("SELECT * FROM notification_routes WHERE workspace_id=? AND portfolio_id=? AND target_id=? AND event_type=?", (workspace_id, portfolio_id, target_id, event_type)).fetchone()) or {}

    def list_routes(self, workspace_id: str, portfolio_id: str | None = None) -> list[dict[str, Any]]:
        with self._connection() as conn:
            sql = "SELECT r.* FROM notification_routes r JOIN decision_portfolios p ON p.id=r.portfolio_id WHERE r.workspace_id=?"
            params: list[Any] = [workspace_id]
            if portfolio_id:
                sql += " AND r.portfolio_id=?"
                params.append(portfolio_id)
            return [self._decode(row) or {} for row in conn.execute(sql + " ORDER BY r.created_at", params).fetchall()]

    def claim_delivery(
        self,
        workspace_id: str,
        report_id: str,
        target_id: str,
        idempotency_key: str,
        owner_id: str,
        *,
        lease_seconds: int = 300,
        fence_token: str = "",
    ) -> dict[str, Any]:
        """Claim one outbound key before making an external request."""

        now = utc_now()
        lease_until = now + timedelta(seconds=max(1, lease_seconds))
        with self._connection() as conn:
            # The read/lease decision must be one serialized transaction.  A
            # deferred transaction lets two workers both observe an expired
            # claim and then lets the second UPSERT replace the first owner.
            conn.execute("BEGIN IMMEDIATE")
            self._require_delivery_references(conn, workspace_id, report_id, target_id)
            delivered = conn.execute(
                "SELECT * FROM delivery_attempts WHERE idempotency_key=? AND target_id=? AND status='delivered' LIMIT 1",
                (idempotency_key, target_id),
            ).fetchone()
            if delivered:
                return {"claimed": False, "reason": "already_delivered", "attempt": self._decode(delivered)}
            row = conn.execute(
                "SELECT * FROM delivery_claims WHERE idempotency_key=? AND target_id=?",
                (idempotency_key, target_id),
            ).fetchone()
            same_fence = (
                row is not None
                and row["owner_id"] == owner_id
                and (not fence_token or str(row["fence_token"] or "") == fence_token)
            )
            # ``dispatching`` is a durable write-ahead state for external I/O.
            # It is intentionally never reclaimed by time: after a process
            # crash the provider may already have accepted the request, so an
            # automatic retry could create a duplicate successful send.
            if row and row["status"] in {"sending", "dispatching"}:
                return {
                    "claimed": False,
                    # Keep the existing API reason stable for callers while
                    # exposing the stronger durable state to operators.
                    "reason": "claimed_by_self" if same_fence else "claimed",
                    "status": "dispatching",
                    "claim_status": "dispatching",
                    "claim": self._decode(row),
                }
            if row and row["status"] in {"unknown", "dead"}:
                return {
                    "claimed": False,
                    "reason": str(row["status"]),
                    "status": str(row["status"]),
                    "claim": self._decode(row),
                }
            conn.execute(
                """
                INSERT INTO delivery_claims(
                    idempotency_key,target_id,workspace_id,report_id,owner_id,fence_token,status,lease_until,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(idempotency_key,target_id) DO UPDATE SET
                    workspace_id=excluded.workspace_id,
                    report_id=excluded.report_id,
                    owner_id=excluded.owner_id,
                    fence_token=excluded.fence_token,
                    status='dispatching',
                    lease_until=excluded.lease_until,
                    updated_at=excluded.updated_at
                """,
                (idempotency_key, target_id, workspace_id, report_id, owner_id, fence_token, "dispatching", lease_until.isoformat(timespec="seconds"), now.isoformat(timespec="seconds")),
            )
            return {
                "claimed": True,
                "owner_id": owner_id,
                "fence_token": fence_token,
                "lease_until": lease_until.isoformat(timespec="seconds"),
            }

    def complete_delivery_claim(
        self,
        idempotency_key: str,
        target_id: str,
        owner_id: str,
        status: str,
        *,
        fence_token: str = "",
    ) -> bool:
        if status not in {"delivered", "available", "dead", "unknown"}:
            raise ValueError("invalid_delivery_claim_status")
        with self._connection() as conn:
            return conn.execute(
                """
                UPDATE delivery_claims SET status=?, lease_until=?, updated_at=?
                WHERE idempotency_key=? AND target_id=? AND owner_id=?
                  AND (fence_token=? OR ?='')
                """,
                (status, iso_now(), iso_now(), idempotency_key, target_id, owner_id, fence_token, fence_token),
            ).rowcount == 1

    def mark_delivery_claim_unknown(
        self,
        idempotency_key: str,
        target_id: str,
        owner_id: str,
        *,
        fence_token: str = "",
    ) -> bool:
        """Freeze an ambiguous provider outcome for manual review.

        This operation only changes the durable claim state.  It deliberately
        does not create a synthetic "delivered" attempt and cannot make the
        key available to an automatic retry.
        """

        with self._connection() as conn:
            return conn.execute(
                """
                UPDATE delivery_claims SET status='unknown', lease_until=?, updated_at=?
                WHERE idempotency_key=? AND target_id=? AND owner_id=?
                  AND status IN ('dispatching', 'sending')
                  AND (fence_token=? OR ?='')
                """,
                (iso_now(), iso_now(), idempotency_key, target_id, owner_id, fence_token, fence_token),
            ).rowcount == 1

    def record_delivery_attempt(
        self,
        workspace_id: str,
        report_id: str,
        target_id: str,
        idempotency_key: str,
        status: str,
        *,
        error: str = "",
        response_summary: str = "",
        claim_owner_id: str | None = None,
        fence_token: str = "",
    ) -> dict[str, Any]:
        attempt_id = str(uuid.uuid4())
        with self._connection() as conn:
            # MAX(attempt_no)+1 is safe only while writers are serialized.
            # Keep the allocation and insert in one immediate transaction so
            # concurrent retry workers cannot collide on the unique key.
            conn.execute("BEGIN IMMEDIATE")
            self._require_delivery_references(conn, workspace_id, report_id, target_id)
            if claim_owner_id is not None:
                claim = conn.execute(
                    "SELECT owner_id, fence_token, status, lease_until FROM delivery_claims WHERE idempotency_key=? AND target_id=?",
                    (idempotency_key, target_id),
                ).fetchone()
                if (
                    claim is None
                    or claim["owner_id"] != claim_owner_id
                    or claim["status"] not in {"dispatching", "sending"}
                    or str(claim["fence_token"] or "") != str(fence_token or "")
                    or datetime.fromisoformat(claim["lease_until"]) <= utc_now()
                ):
                    raise RuntimeError("delivery_claim_fence_lost")
            delivered = conn.execute("SELECT * FROM delivery_attempts WHERE idempotency_key=? AND target_id=? AND status='delivered' LIMIT 1", (idempotency_key, target_id)).fetchone()
            if delivered:
                return self._decode(delivered) or {}
            next_attempt = conn.execute("SELECT COALESCE(MAX(attempt_no),0)+1 AS n FROM delivery_attempts WHERE idempotency_key=? AND target_id=?", (idempotency_key, target_id)).fetchone()["n"]
            conn.execute("INSERT INTO delivery_attempts(id,workspace_id,report_id,target_id,idempotency_key,attempt_no,status,error,response_summary,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (attempt_id, workspace_id, report_id, target_id, idempotency_key, next_attempt, status, error[:1000], response_summary[:2000], iso_now()))
            if status in {"failed", "dead"}:
                conn.execute("UPDATE notification_targets SET failure_count=failure_count+1 WHERE id=? AND workspace_id=?", (target_id, workspace_id))
            row = conn.execute("SELECT * FROM delivery_attempts WHERE id=?", (attempt_id,)).fetchone()
            return self._decode(row) or {}

    def list_delivery_attempts(self, workspace_id: str, report_id: str | None = None) -> list[dict[str, Any]]:
        with self._connection() as conn:
            sql = "SELECT * FROM delivery_attempts WHERE workspace_id=?"
            params: list[Any] = [workspace_id]
            if report_id:
                sql += " AND report_id=?"
                params.append(report_id)
            rows = conn.execute(sql + " ORDER BY created_at DESC", params).fetchall()
            return [self._decode(row) or {} for row in rows]

    def list_delivery_claims(self, workspace_id: str, report_id: str | None = None) -> list[dict[str, Any]]:
        """Expose dispatching/unknown claims so operators can review ambiguity."""

        with self._connection() as conn:
            sql = "SELECT * FROM delivery_claims WHERE workspace_id=?"
            params: list[Any] = [workspace_id]
            if report_id:
                sql += " AND report_id=?"
                params.append(report_id)
            rows = conn.execute(sql + " ORDER BY updated_at DESC", params).fetchall()
            return [self._decode(row) or {} for row in rows]

    def save_eligibility(self, version_id: str, checks: Mapping[str, Any], reasons: list[str]) -> dict[str, Any]:
        with self._connection() as conn:
            conn.execute("INSERT INTO decision_eligibility(portfolio_version_id,preview_ok,validation_ok,health_ok,adapter_ok,target_ok,reasons_json,checked_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(portfolio_version_id) DO UPDATE SET preview_ok=excluded.preview_ok,validation_ok=excluded.validation_ok,health_ok=excluded.health_ok,adapter_ok=excluded.adapter_ok,target_ok=excluded.target_ok,reasons_json=excluded.reasons_json,checked_at=excluded.checked_at", (version_id, int(bool(checks.get("preview_ok"))), int(bool(checks.get("validation_ok"))), int(bool(checks.get("health_ok"))), int(bool(checks.get("adapter_ok"))), int(bool(checks.get("target_ok"))), stable_json(reasons), iso_now()))
            return self._decode(conn.execute("SELECT * FROM decision_eligibility WHERE portfolio_version_id=?", (version_id,)).fetchone()) or {}

    def get_eligibility(self, version_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            return self._decode(conn.execute("SELECT * FROM decision_eligibility WHERE portfolio_version_id=?", (version_id,)).fetchone())

    def save_validation(self, version_id: str, result: Mapping[str, Any]) -> dict[str, Any]:
        """Persist the complete validation evidence for a frozen version.

        Eligibility is a current aggregate of several checks; the validation
        result itself is a separate immutable input/output artifact so a
        restored workspace can inspect exactly which history and execution
        contract produced the gate.
        """

        payload = dict(result)
        validation_hash = content_hash(payload)
        evidence_id = str(uuid.uuid4())
        checked_at = iso_now()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO decision_validation_evidence(
                    id, portfolio_version_id, validation_json, validation_hash, checked_at
                ) VALUES(?,?,?,?,?)
                """,
                (evidence_id, version_id, stable_json(payload), validation_hash, checked_at),
            )
            evidence = conn.execute(
                """
                SELECT * FROM decision_validation_evidence
                WHERE portfolio_version_id=? AND validation_hash=?
                """,
                (version_id, validation_hash),
            ).fetchone()
            conn.execute(
                """
                INSERT INTO decision_validations(
                    portfolio_version_id, validation_json, validation_hash, checked_at
                ) VALUES(?,?,?,?)
                ON CONFLICT(portfolio_version_id) DO UPDATE SET
                    validation_json=excluded.validation_json,
                    validation_hash=excluded.validation_hash,
                    checked_at=excluded.checked_at
                """,
                (version_id, stable_json(payload), validation_hash, checked_at),
            )
            current = self._decode(
                conn.execute(
                    "SELECT * FROM decision_validations WHERE portfolio_version_id=?",
                    (version_id,),
                ).fetchone()
            ) or {}
            if evidence is not None:
                current["evidence_id"] = str(evidence["id"])
            return current

    def get_validation(self, version_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            return self._decode(
                conn.execute(
                    "SELECT * FROM decision_validations WHERE portfolio_version_id=?",
                    (version_id,),
                ).fetchone()
            )

    def list_validations(self, version_id: str) -> list[dict[str, Any]]:
        """Return every immutable validation evidence record for a version."""

        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM decision_validation_evidence
                WHERE portfolio_version_id=?
                ORDER BY checked_at, id
                """,
                (version_id,),
            ).fetchall()
            return [self._decode(row) or {} for row in rows]


__all__ = ["DecisionStore", "content_hash", "report_fingerprint", "stable_json"]
