"""Small append-oriented SQLite repository for AI artifacts."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def decode(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


class AIRuntimeRepository:
    def __init__(self, database: str | Path) -> None:
        self.database = str(database)
        self._lock = threading.RLock()
        self._memory = self.database == ":memory:"
        self._memory_connection: sqlite3.Connection | None = None
        if not self._memory:
            Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = self._memory_connection if self._memory else sqlite3.connect(self.database, timeout=10)
            if connection is None:
                # FastAPI's TestClient and the worker can access one runtime
                # from different threads.  The repository lock still
                # serializes operations; SQLite must only disable its
                # connection-level thread assertion for the shared memory DB.
                connection = sqlite3.connect(":memory:", timeout=10, check_same_thread=False)
                self._memory_connection = connection
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout=10000")
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                if not self._memory:
                    connection.close()

    def init_db(self) -> None:
        with self._connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS ai_channels (
                    id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL DEFAULT 'default',
                    config_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (workspace_id, id)
                );
                CREATE TABLE IF NOT EXISTS ai_provider_runtime (
                    provider_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    last_error_code TEXT,
                    last_checked_at REAL NOT NULL DEFAULT 0,
                    attempts_json TEXT NOT NULL DEFAULT '[]',
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ai_tasks (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    context_hash TEXT,
                    profile TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    idempotency_key TEXT,
                    owner_id TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    report_id TEXT,
                    error_json TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    lease_owner TEXT,
                    lease_token TEXT,
                    lease_expires_at REAL,
                    UNIQUE(workspace_id, idempotency_key)
                );
                CREATE INDEX IF NOT EXISTS idx_ai_tasks_status ON ai_tasks(status, created_at);
                CREATE TABLE IF NOT EXISTS ai_task_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ai_reports (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    body_json TEXT NOT NULL,
                    context_hash TEXT NOT NULL,
                    provenance_json TEXT NOT NULL,
                    usage_json TEXT NOT NULL,
                    diagnostics_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_ai_reports_workspace ON ai_reports(workspace_id, created_at);
                CREATE TABLE IF NOT EXISTS ai_sessions (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    skills_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ai_messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            channel_columns = {row[1] for row in conn.execute("PRAGMA table_info(ai_channels)").fetchall()}
            if "workspace_id" not in channel_columns:
                conn.execute("ALTER TABLE ai_channels RENAME TO ai_channels_legacy")
                conn.execute("""CREATE TABLE ai_channels (
                    id TEXT NOT NULL, workspace_id TEXT NOT NULL DEFAULT 'default',
                    config_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY (workspace_id, id)
                )""")
                conn.execute("""INSERT INTO ai_channels(id,workspace_id,config_json,created_at,updated_at)
                    SELECT id,'default',config_json,created_at,updated_at FROM ai_channels_legacy""")
                conn.execute("DROP TABLE ai_channels_legacy")
            columns = {row[1] for row in conn.execute("PRAGMA table_info(ai_tasks)").fetchall()}
            for name, definition in {
                "lease_owner": "TEXT",
                "lease_token": "TEXT",
                "lease_expires_at": "REAL",
            }.items():
                if name not in columns:
                    conn.execute(f"ALTER TABLE ai_tasks ADD COLUMN {name} {definition}")

    def close(self) -> None:
        with self._lock:
            if self._memory_connection is not None:
                self._memory_connection.close()
                self._memory_connection = None

    def save_channel(self, config: dict[str, Any], workspace_id: str = "default") -> dict[str, Any]:
        timestamp = now_iso()
        workspace_id = str(workspace_id or "default")
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO ai_channels(id,workspace_id,config_json,created_at,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(workspace_id,id) DO UPDATE SET config_json=excluded.config_json, updated_at=excluded.updated_at",
                (config["id"], workspace_id, encode(config), timestamp, timestamp),
            )
        return config

    def list_channels(self, workspace_id: str = "default") -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute("SELECT config_json FROM ai_channels WHERE workspace_id = ? ORDER BY json_extract(config_json, '$.priority'), id", (str(workspace_id or "default"),)).fetchall()
        return [decode(row[0], {}) for row in rows]

    def get_provider_runtime(self, provider_id: str) -> dict[str, Any] | None:
        """Read the secret-free provider runtime projection shared by all processes."""

        with self._connection() as conn:
            row = conn.execute(
                "SELECT provider_id,status,last_error_code,last_checked_at,attempts_json,updated_at FROM ai_provider_runtime WHERE provider_id=?",
                (provider_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "provider_id": row[0],
            "status": row[1],
            "last_error_code": row[2],
            "last_checked_at": float(row[3] or 0),
            "attempts": decode(row[4], []),
            "updated_at": row[5],
        }

    def save_provider_runtime(
        self,
        provider_id: str,
        *,
        status: str,
        error_code: str | None = None,
        last_checked_at: float = 0,
    ) -> None:
        """Persist provider operability without prompts, responses, or credentials."""

        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO ai_provider_runtime(provider_id,status,last_error_code,last_checked_at,attempts_json,updated_at)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(provider_id) DO UPDATE SET
                    status=excluded.status,
                    last_error_code=excluded.last_error_code,
                    last_checked_at=excluded.last_checked_at,
                    updated_at=excluded.updated_at
                """,
                (provider_id, status, error_code, float(last_checked_at or 0), "[]", now_iso()),
            )

    def append_provider_attempt(self, provider_id: str, attempt: dict[str, Any]) -> None:
        """Append one bounded, already-redacted provider attempt to the projection."""

        with self._connection() as conn:
            row = conn.execute("SELECT attempts_json FROM ai_provider_runtime WHERE provider_id=?", (provider_id,)).fetchone()
            history = decode(row[0], []) if row is not None else []
            if not isinstance(history, list):
                history = []
            history.append(dict(attempt))
            history = history[-12:]
            if row is None:
                conn.execute(
                    "INSERT INTO ai_provider_runtime(provider_id,status,last_error_code,last_checked_at,attempts_json,updated_at) VALUES(?,?,?,?,?,?)",
                    (provider_id, "not_checked", None, 0, encode(history), now_iso()),
                )
            else:
                conn.execute(
                    "UPDATE ai_provider_runtime SET attempts_json=?, updated_at=? WHERE provider_id=?",
                    (encode(history), now_iso(), provider_id),
                )

    def create_task(self, *, workspace_id: str, kind: str, request: dict[str, Any], context_hash: str, profile: str, schema_version: str, idempotency_key: str = "") -> tuple[dict[str, Any], bool]:
        task_id = uuid.uuid4().hex
        timestamp = now_iso()
        try:
            with self._connection() as conn:
                conn.execute(
                    "INSERT INTO ai_tasks(id,workspace_id,kind,status,request_json,context_hash,profile,schema_version,idempotency_key,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (task_id, workspace_id, kind, "queued", encode(request), context_hash, profile, schema_version, idempotency_key or None, timestamp),
                )
                self._insert_event(conn, task_id, "task_created", {"status": "queued"})
        except sqlite3.IntegrityError:
            if not idempotency_key:
                raise
            existing = self.get_task_by_idempotency(workspace_id, idempotency_key)
            if existing is None:
                raise
            return existing, False
        return self.get_task(task_id) or {}, True

    def get_task_by_idempotency(self, workspace_id: str, key: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM ai_tasks WHERE workspace_id=? AND idempotency_key=?", (workspace_id, key)).fetchone()
        return self._task_row(row)

    def get_task(self, task_id: str, workspace_id: str | None = None) -> dict[str, Any] | None:
        sql = "SELECT * FROM ai_tasks WHERE id=?"
        params: list[Any] = [task_id]
        if workspace_id is not None:
            sql += " AND workspace_id=?"
            params.append(workspace_id)
        with self._connection() as conn:
            row = conn.execute(sql, params).fetchone()
        return self._task_row(row)

    def list_tasks(self, workspace_id: str, *, limit: int = 50, status: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM ai_tasks WHERE workspace_id=?"
        params: list[Any] = [workspace_id]
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 200)))
        with self._connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._task_row(row) or {} for row in rows]

    def claim_tasks(self, owner_id: str, *, limit: int = 10, lease_ttl_seconds: float = 60.0) -> list[dict[str, Any]]:
        now = time.time()
        expiry = now + max(1.0, float(lease_ttl_seconds))
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT id FROM ai_tasks WHERE cancel_requested=0 AND (status='queued' OR (status IN ('running','cancel_requested') AND lease_expires_at IS NOT NULL AND lease_expires_at<=?)) ORDER BY created_at LIMIT ?",
                (now, max(1, min(int(limit), 100))),
            ).fetchall()
            claimed: list[dict[str, Any]] = []
            for row in rows:
                token = uuid.uuid4().hex
                updated = conn.execute(
                    "UPDATE ai_tasks SET status='running', owner_id=?, lease_owner=?, lease_token=?, lease_expires_at=?, attempts=attempts+1, started_at=COALESCE(started_at, ?), completed_at=NULL WHERE id=? AND cancel_requested=0 AND (status='queued' OR (status IN ('running','cancel_requested') AND lease_expires_at IS NOT NULL AND lease_expires_at<=?))",
                    (owner_id, owner_id, token, expiry, now_iso(), row[0], now),
                ).rowcount
                if updated:
                    self._insert_event(conn, row[0], "task_started", {"owner_id": owner_id, "reclaimed": True if conn.execute("SELECT attempts FROM ai_tasks WHERE id=?", (row[0],)).fetchone()[0] > 1 else False})
                    claimed.append(self._task_row(conn.execute("SELECT * FROM ai_tasks WHERE id=?", (row[0],)).fetchone()) or {})
        return claimed

    def heartbeat_task(self, task_id: str, *, owner_id: str, lease_token: str, lease_ttl_seconds: float = 60.0) -> bool:
        updated = 0
        with self._connection() as conn:
            updated = conn.execute(
                "UPDATE ai_tasks SET lease_expires_at=? WHERE id=? AND status='running' AND lease_owner=? AND lease_token=? AND lease_expires_at>?",
                (time.time() + max(1.0, float(lease_ttl_seconds)), task_id, owner_id, lease_token, time.time()),
            ).rowcount
        return updated == 1

    def reclaim_expired_tasks(self, *, limit: int = 100) -> int:
        now = time.time()
        with self._connection() as conn:
            rows = conn.execute("SELECT id FROM ai_tasks WHERE status='running' AND lease_expires_at IS NOT NULL AND lease_expires_at<=? LIMIT ?", (now, max(1, min(int(limit), 500)))).fetchall()
            for row in rows:
                self._insert_event(conn, row[0], "task_lease_expired", {})
            return len(rows)

    def start_task(self, task_id: str, *, owner_id: str | None = None) -> dict[str, Any] | None:
        """Atomically transition a queued task to running for inline execution."""

        with self._connection() as conn:
            params: list[Any] = [owner_id, now_iso(), task_id]
            owner_clause = ""
            if owner_id is not None:
                owner_clause = " AND (owner_id IS NULL OR owner_id=?)"
                params.append(owner_id)
            updated = conn.execute(
                f"UPDATE ai_tasks SET status='running', owner_id=COALESCE(owner_id, ?), started_at=COALESCE(started_at, ?) WHERE id=? AND status='queued' AND cancel_requested=0{owner_clause}",
                params,
            ).rowcount
            if updated:
                self._insert_event(conn, task_id, "task_started", {"owner_id": owner_id or "inline"})
        return self.get_task(task_id)

    def request_cancel(self, task_id: str, workspace_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute("SELECT status FROM ai_tasks WHERE id=? AND workspace_id=?", (task_id, workspace_id)).fetchone()
            if row is None:
                return None
            status = str(row[0])
            if status == "queued":
                conn.execute("UPDATE ai_tasks SET status='cancelled', cancel_requested=1, completed_at=? WHERE id=?", (now_iso(), task_id))
                self._insert_event(conn, task_id, "task_cancelled", {"status": "cancelled"})
            elif status == "running":
                conn.execute("UPDATE ai_tasks SET status='cancel_requested', cancel_requested=1 WHERE id=?", (task_id,))
                self._insert_event(conn, task_id, "task_cancel_requested", {"status": "cancel_requested"})
        return self.get_task(task_id, workspace_id)

    def complete_task(self, task_id: str, *, status: str, report_id: str | None = None, error: dict[str, Any] | None = None, owner_id: str | None = None, lease_token: str | None = None) -> dict[str, Any] | None:
        with self._connection() as conn:
            where = "id=?"
            params: list[Any] = [status, report_id, encode(error or {}), now_iso(), task_id]
            if owner_id and lease_token:
                where += " AND lease_owner=? AND lease_token=?"
                params.extend([owner_id, lease_token])
            updated = conn.execute(f"UPDATE ai_tasks SET status=?, report_id=?, error_json=?, completed_at=?, lease_expires_at=NULL WHERE {where}", params).rowcount
            if updated:
                event_type = "task_completed" if status in {"completed", "degraded"} else "task_cancelled" if status == "cancelled" else "task_failed"
                self._insert_event(conn, task_id, event_type, {"status": status, "report_id": report_id, "error": error or {}})
        return self.get_task(task_id)

    def append_event(self, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
        with self._connection() as conn:
            self._insert_event(conn, task_id, event_type, payload)

    def list_events(self, task_id: str, workspace_id: str, *, after_id: int = 0, limit: int = 200) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute("SELECT e.id,e.task_id,e.event_type,e.payload_json,e.created_at FROM ai_task_events e JOIN ai_tasks t ON t.id=e.task_id WHERE e.task_id=? AND t.workspace_id=? AND e.id>? ORDER BY e.id LIMIT ?", (task_id, workspace_id, after_id, max(1, min(limit, 500)))).fetchall()
        return [{"id": row[0], "task_id": row[1], "event_type": row[2], "payload": decode(row[3], {}), "created_at": row[4]} for row in rows]

    def save_report(self, *, task_id: str, workspace_id: str, status: str, body: dict[str, Any], context_hash: str, provenance: dict[str, Any], usage: dict[str, Any], diagnostics: list[dict[str, Any]]) -> dict[str, Any]:
        report_id = uuid.uuid4().hex
        with self._connection() as conn:
            conn.execute("INSERT INTO ai_reports(id,task_id,workspace_id,status,body_json,context_hash,provenance_json,usage_json,diagnostics_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (report_id, task_id, workspace_id, status, encode(body), context_hash, encode(provenance), encode(usage), encode(diagnostics), now_iso()))
        return self.get_report(report_id, workspace_id) or {}

    def save_report_if_active(self, *, task_id: str, workspace_id: str, status: str, body: dict[str, Any], context_hash: str, provenance: dict[str, Any], usage: dict[str, Any], diagnostics: list[dict[str, Any]], owner_id: str | None = None, lease_token: str | None = None) -> dict[str, Any] | None:
        """Persist a report only while the task is still cancellable/running.

        Cancellation is cooperative, so the final insert and task ownership
        check share one SQLite transaction.  A cancelled task cannot publish a
        report between the last Python check and the insert.
        """

        report_id = uuid.uuid4().hex
        timestamp = now_iso()
        with self._connection() as conn:
            active = conn.execute("SELECT status,cancel_requested,lease_owner,lease_token,lease_expires_at FROM ai_tasks WHERE id=? AND workspace_id=?", (task_id, workspace_id)).fetchone()
            if active is None or active[0] != "running" or bool(active[1]) or (owner_id and (active[2] != owner_id or active[3] != lease_token or (active[4] is not None and active[4] <= time.time()))):
                return None
            conn.execute(
                "INSERT INTO ai_reports(id,task_id,workspace_id,status,body_json,context_hash,provenance_json,usage_json,diagnostics_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (report_id, task_id, workspace_id, status, encode(body), context_hash, encode(provenance), encode(usage), encode(diagnostics), timestamp),
            )
            updated = conn.execute("UPDATE ai_tasks SET report_id=? WHERE id=? AND workspace_id=? AND status='running' AND cancel_requested=0", (report_id, task_id, workspace_id)).rowcount
            if updated != 1:
                conn.execute("DELETE FROM ai_reports WHERE id=?", (report_id,))
                return None
            row = conn.execute("SELECT * FROM ai_reports WHERE id=? AND workspace_id=?", (report_id, workspace_id)).fetchone()
        return self._report_row(row)

    def get_report(self, report_id: str, workspace_id: str | None = None) -> dict[str, Any] | None:
        sql = "SELECT * FROM ai_reports WHERE id=?"
        params: list[Any] = [report_id]
        if workspace_id is not None:
            sql += " AND workspace_id=?"
            params.append(workspace_id)
        with self._connection() as conn:
            row = conn.execute(sql, params).fetchone()
        return self._report_row(row)

    def list_reports(self, workspace_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute("SELECT * FROM ai_reports WHERE workspace_id=? ORDER BY created_at DESC LIMIT ?", (workspace_id, max(1, min(int(limit), 200)))).fetchall()
        return [self._report_row(row) or {} for row in rows]

    def create_session(self, workspace_id: str, *, title: str = "新对话", skills: list[str] | None = None, session_id: str | None = None) -> dict[str, Any]:
        sid = session_id or uuid.uuid4().hex
        timestamp = now_iso()
        with self._connection() as conn:
            conn.execute("INSERT OR IGNORE INTO ai_sessions(id,workspace_id,title,skills_json,created_at,updated_at) VALUES(?,?,?,?,?,?)", (sid, workspace_id, title[:120] or "新对话", encode(skills or []), timestamp, timestamp))
        return self.get_session(sid, workspace_id) or {}

    def update_session(self, session_id: str, workspace_id: str, *, title: str | None = None, skills: list[str] | None = None) -> dict[str, Any] | None:
        updates: list[str] = []
        values: list[Any] = []
        if title is not None:
            updates.append("title=?")
            values.append(str(title)[:120] or "新对话")
        if skills is not None:
            updates.append("skills_json=?")
            values.append(encode(skills))
        if updates:
            updates.append("updated_at=?")
            values.append(now_iso())
            values.extend([session_id, workspace_id])
            with self._connection() as conn:
                conn.execute(f"UPDATE ai_sessions SET {', '.join(updates)} WHERE id=? AND workspace_id=?", values)
        return self.get_session(session_id, workspace_id)

    def list_sessions(self, workspace_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute("SELECT s.*, (SELECT COUNT(*) FROM ai_messages m WHERE m.session_id=s.id) AS message_count FROM ai_sessions s WHERE s.workspace_id=? ORDER BY s.updated_at DESC LIMIT ?", (workspace_id, max(1, min(int(limit), 200)))).fetchall()
        return [self._session_row(row) or {} for row in rows]

    def get_session(self, session_id: str, workspace_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM ai_sessions WHERE id=? AND workspace_id=?", (session_id, workspace_id)).fetchone()
            if row is None:
                return None
            session = self._session_row(row) or {}
            messages = conn.execute("SELECT * FROM ai_messages WHERE session_id=? ORDER BY created_at,id", (session_id,)).fetchall()
            session["messages"] = [self._message_row(item) or {} for item in messages]
            return session

    def delete_session(self, session_id: str, workspace_id: str) -> bool:
        with self._connection() as conn:
            if conn.execute("SELECT 1 FROM ai_sessions WHERE id=? AND workspace_id=?", (session_id, workspace_id)).fetchone() is None:
                return False
            conn.execute("DELETE FROM ai_messages WHERE session_id=?", (session_id,))
            return conn.execute("DELETE FROM ai_sessions WHERE id=? AND workspace_id=?", (session_id, workspace_id)).rowcount == 1

    def add_message(self, session_id: str, workspace_id: str, role: str, content: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if role not in {"user", "assistant", "system"}:
            raise ValueError("invalid_ai_message_role")
        with self._connection() as conn:
            if conn.execute("SELECT 1 FROM ai_sessions WHERE id=? AND workspace_id=?", (session_id, workspace_id)).fetchone() is None:
                raise KeyError("ai_session_not_found")
            message_id = uuid.uuid4().hex
            timestamp = now_iso()
            conn.execute("INSERT INTO ai_messages(id,session_id,role,content,metadata_json,created_at) VALUES(?,?,?,?,?,?)", (message_id, session_id, role, content, encode(metadata or {}), timestamp))
            conn.execute("UPDATE ai_sessions SET updated_at=? WHERE id=?", (timestamp, session_id))
            row = conn.execute("SELECT * FROM ai_messages WHERE id=?", (message_id,)).fetchone()
        return self._message_row(row) or {}

    @staticmethod
    def _insert_event(conn: sqlite3.Connection, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
        conn.execute("INSERT INTO ai_task_events(task_id,event_type,payload_json,created_at) VALUES(?,?,?,?)", (task_id, event_type, encode(payload), now_iso()))

    @staticmethod
    def _task_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        value = dict(row)
        value["request"] = decode(value.pop("request_json", None), {})
        value["error"] = decode(value.pop("error_json", None), {})
        value["cancel_requested"] = bool(value.get("cancel_requested"))
        return value

    @staticmethod
    def _report_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        value = dict(row)
        value["body"] = decode(value.pop("body_json", None), {})
        value["provenance"] = decode(value.pop("provenance_json", None), {})
        value["usage"] = decode(value.pop("usage_json", None), {})
        value["diagnostics"] = decode(value.pop("diagnostics_json", None), [])
        return value

    @staticmethod
    def _session_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        value = dict(row)
        value["skills"] = decode(value.pop("skills_json", None), [])
        value["messages"] = []
        return value

    @staticmethod
    def _message_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        value = dict(row)
        value["metadata"] = decode(value.pop("metadata_json", None), {})
        return value
