"""User, workspace, permission, audit, and OpenClaw metadata storage."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from config.settings import ACCOUNT_DB_PATH
from utils.db import get_connection


INVITE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
INVITE_CODE_LEN = 6
SESSION_DAYS = 14

DEFAULT_PERMISSIONS = {
    "chat": True,
    "read_market": True,
    "read_portfolio": True,
    "write_watchlist": True,
    "write_paper_trade": True,
    "manage_skills": True,
    "manage_workspace": True,
    "admin": False,
}

ADMIN_PERMISSIONS = {key: True for key in DEFAULT_PERMISSIONS}
DEFAULT_WORKSPACE_SETTINGS = {
    "native_panel_mode": "iframe",
    "tool_confirmations": {
        "write_paper_trade": True,
        "manage_skills": True,
        "write_watchlist": True,
    },
    "openclaw_setup_completed": False,
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def normalize_invite_code(code: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", code or "").upper()
    return cleaned[:INVITE_CODE_LEN]


def generate_invite_code() -> str:
    return "".join(secrets.choice(INVITE_CHARS) for _ in range(INVITE_CODE_LEN))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    iterations = 240_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, iterations, salt_hex, digest_hex = stored_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_invite_code(code: str) -> str:
    return hashlib.sha256(normalize_invite_code(code).encode("utf-8")).hexdigest()


def mask_invite_code(code: str) -> str:
    normalized = normalize_invite_code(code)
    return f"{normalized[:2]}****" if normalized else "****"


def safe_json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


class AccountStore:
    """SQLite-backed account store kept separate from market data storage."""

    def __init__(self, db_path: str | Path = ACCOUNT_DB_PATH):
        self.db_path = Path(db_path)
        self.init_db()

    def _conn(self):
        return get_connection(self.db_path)

    def init_db(self) -> None:
        conn = self._conn()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    email TEXT UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    avatar_color TEXT NOT NULL DEFAULT '#2f6fed',
                    created_at TEXT NOT NULL,
                    last_login_at TEXT,
                    disabled INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS invite_codes (
                    code_hash TEXT PRIMARY KEY,
                    code_display TEXT NOT NULL DEFAULT '',
                    created_by_user_id TEXT,
                    max_uses INTEGER NOT NULL DEFAULT 1,
                    used_count INTEGER NOT NULL DEFAULT 0,
                    expires_at TEXT,
                    disabled INTEGER NOT NULL DEFAULT 0,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS invite_code_usages (
                    id TEXT PRIMARY KEY,
                    code_hash TEXT NOT NULL,
                    code_display TEXT NOT NULL DEFAULT '',
                    user_id TEXT,
                    status TEXT NOT NULL DEFAULT 'success',
                    reason TEXT NOT NULL DEFAULT '',
                    used_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS user_sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    last_seen_at TEXT,
                    user_agent TEXT,
                    ip_address TEXT,
                    revoked INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS user_workspaces (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    slug TEXT NOT NULL UNIQUE,
                    openclaw_workspace_id TEXT NOT NULL,
                    settings_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS workspace_permissions (
                    workspace_id TEXT NOT NULL,
                    permission_key TEXT NOT NULL,
                    allowed INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (workspace_id, permission_key)
                );

                CREATE TABLE IF NOT EXISTS audit_logs (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    workspace_id TEXT,
                    action TEXT NOT NULL,
                    target_type TEXT NOT NULL DEFAULT '',
                    target_id TEXT NOT NULL DEFAULT '',
                    tool_name TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'ok',
                    reason TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS research_memories (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    code TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    source TEXT NOT NULL DEFAULT 'manual',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS daily_reports (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE (workspace_id, trade_date)
                );

                CREATE TABLE IF NOT EXISTS openclaw_skill_records (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    version TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'installed',
                    source TEXT NOT NULL DEFAULT '',
                    permissions_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (workspace_id, name)
                );

                CREATE TABLE IF NOT EXISTS skill_install_requests (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    skill_name TEXT NOT NULL,
                    version TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    reason TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '',
                    decided_by_user_id TEXT,
                    decided_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_audit_logs_workspace_created
                    ON audit_logs(workspace_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_research_memories_workspace_updated
                    ON research_memories(workspace_id, updated_at DESC);
                """
            )
            self._migrate_invite_schema(conn)
            self._migrate_skill_request_schema(conn)
            conn.commit()
            self._bootstrap_invite_code(conn)
        finally:
            conn.close()

    def _table_columns(self, conn, table: str) -> set[str]:
        return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}

    def _migrate_invite_schema(self, conn) -> None:
        invite_columns = self._table_columns(conn, "invite_codes")
        if "code" in invite_columns or "code_hash" not in invite_columns:
            rows = conn.execute("SELECT * FROM invite_codes").fetchall()
            conn.execute("DROP TABLE invite_codes")
            conn.execute(
                """
                CREATE TABLE invite_codes (
                    code_hash TEXT PRIMARY KEY,
                    code_display TEXT NOT NULL DEFAULT '',
                    created_by_user_id TEXT,
                    max_uses INTEGER NOT NULL DEFAULT 1,
                    used_count INTEGER NOT NULL DEFAULT 0,
                    expires_at TEXT,
                    disabled INTEGER NOT NULL DEFAULT 0,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
                """
            )
            for row in rows:
                raw = dict(row)
                code = normalize_invite_code(raw.get("code", ""))
                if len(code) != INVITE_CODE_LEN:
                    continue
                conn.execute(
                    """INSERT OR IGNORE INTO invite_codes
                    (code_hash, code_display, created_by_user_id, max_uses, used_count,
                     expires_at, disabled, note, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        hash_invite_code(code),
                        mask_invite_code(code),
                        raw.get("created_by_user_id"),
                        raw.get("max_uses", 1),
                        raw.get("used_count", 0),
                        raw.get("expires_at"),
                        raw.get("disabled", 0),
                        raw.get("note", ""),
                        raw.get("created_at") or iso_now(),
                    ),
                )
        else:
            if "code_display" not in invite_columns:
                conn.execute("ALTER TABLE invite_codes ADD COLUMN code_display TEXT NOT NULL DEFAULT ''")

        usage_columns = self._table_columns(conn, "invite_code_usages")
        if "code" in usage_columns or "code_hash" not in usage_columns:
            rows = conn.execute("SELECT * FROM invite_code_usages").fetchall()
            conn.execute("DROP TABLE invite_code_usages")
            conn.execute(
                """
                CREATE TABLE invite_code_usages (
                    id TEXT PRIMARY KEY,
                    code_hash TEXT NOT NULL,
                    code_display TEXT NOT NULL DEFAULT '',
                    user_id TEXT,
                    status TEXT NOT NULL DEFAULT 'success',
                    reason TEXT NOT NULL DEFAULT '',
                    used_at TEXT NOT NULL
                )
                """
            )
            for row in rows:
                raw = dict(row)
                code = normalize_invite_code(raw.get("code", ""))
                if len(code) != INVITE_CODE_LEN:
                    continue
                conn.execute(
                    """INSERT OR IGNORE INTO invite_code_usages
                    (id, code_hash, code_display, user_id, status, reason, used_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        raw.get("id") or str(uuid.uuid4()),
                        hash_invite_code(code),
                        mask_invite_code(code),
                        raw.get("user_id"),
                        raw.get("status") or "success",
                        raw.get("reason") or "",
                        raw.get("used_at") or iso_now(),
                    ),
                )
        else:
            if "code_display" not in usage_columns:
                conn.execute("ALTER TABLE invite_code_usages ADD COLUMN code_display TEXT NOT NULL DEFAULT ''")
            if "status" not in usage_columns:
                conn.execute("ALTER TABLE invite_code_usages ADD COLUMN status TEXT NOT NULL DEFAULT 'success'")
            if "reason" not in usage_columns:
                conn.execute("ALTER TABLE invite_code_usages ADD COLUMN reason TEXT NOT NULL DEFAULT ''")

    def _migrate_skill_request_schema(self, conn) -> None:
        columns = self._table_columns(conn, "skill_install_requests")
        if not columns:
            return
        for column, ddl in {
            "version": "ALTER TABLE skill_install_requests ADD COLUMN version TEXT NOT NULL DEFAULT ''",
            "source": "ALTER TABLE skill_install_requests ADD COLUMN source TEXT NOT NULL DEFAULT ''",
            "status": "ALTER TABLE skill_install_requests ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'",
            "reason": "ALTER TABLE skill_install_requests ADD COLUMN reason TEXT NOT NULL DEFAULT ''",
            "note": "ALTER TABLE skill_install_requests ADD COLUMN note TEXT NOT NULL DEFAULT ''",
            "decided_by_user_id": "ALTER TABLE skill_install_requests ADD COLUMN decided_by_user_id TEXT",
            "decided_at": "ALTER TABLE skill_install_requests ADD COLUMN decided_at TEXT",
            "created_at": "ALTER TABLE skill_install_requests ADD COLUMN created_at TEXT NOT NULL DEFAULT ''",
            "updated_at": "ALTER TABLE skill_install_requests ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''",
        }.items():
            if column not in columns:
                conn.execute(ddl)

    def _bootstrap_invite_code(self, conn) -> None:
        row = conn.execute("SELECT COUNT(*) FROM invite_codes").fetchone()
        if row and row[0] > 0:
            return

        configured = normalize_invite_code(os.getenv("QUANT_DEFAULT_INVITE_CODE", ""))
        if len(configured) == INVITE_CODE_LEN:
            code = configured
        elif os.getenv("APP_ENV", "development").lower() == "production":
            logger.warning("生产环境未配置有效 QUANT_DEFAULT_INVITE_CODE，跳过默认邀请码创建")
            return
        else:
            code = "LOCAL1"
        conn.execute(
            """INSERT OR IGNORE INTO invite_codes
            (code_hash, code_display, created_by_user_id, max_uses, used_count, expires_at, disabled, note, created_at)
            VALUES (?, ?, NULL, ?, 0, NULL, 0, ?, ?)""",
            (hash_invite_code(code), mask_invite_code(code), 1000, "local bootstrap invite", iso_now()),
        )
        conn.commit()
        logger.info(f"已创建本地注册邀请码: {mask_invite_code(code)}")

    def _row_to_user(self, row) -> dict | None:
        if not row:
            return None
        return {
            "id": row["id"],
            "username": row["username"],
            "display_name": row["display_name"],
            "email": row["email"] or "",
            "role": row["role"],
            "avatar_color": row["avatar_color"],
            "created_at": row["created_at"],
            "last_login_at": row["last_login_at"],
            "disabled": bool(row["disabled"]),
        }

    def _row_to_workspace(self, row) -> dict | None:
        if not row:
            return None
        settings = self._normalize_workspace_settings(safe_json_loads(row["settings_json"], {}))
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "name": row["name"],
            "slug": row["slug"],
            "openclaw_workspace_id": row["openclaw_workspace_id"],
            "settings": settings,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _normalize_workspace_settings(self, settings: dict[str, Any] | None) -> dict[str, Any]:
        source = dict(settings or {})
        merged = {
            **DEFAULT_WORKSPACE_SETTINGS,
            **source,
        }
        confirmations = {
            **DEFAULT_WORKSPACE_SETTINGS["tool_confirmations"],
            **(merged.get("tool_confirmations") or {}),
        }
        merged["tool_confirmations"] = confirmations
        if "openclaw_setup_completed" in source:
            merged["openclaw_setup_completed"] = bool(source.get("openclaw_setup_completed"))
        else:
            merged["openclaw_setup_completed"] = bool(source)
        return merged

    def _user_count(self, conn) -> int:
        return int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])

    def _create_workspace(self, conn, user_id: str, username: str, is_admin: bool = False) -> dict:
        workspace_id = str(uuid.uuid4())
        slug = f"{re.sub(r'[^a-z0-9-]+', '-', username.lower()).strip('-')}-{workspace_id[:8]}"
        now = iso_now()
        openclaw_workspace_id = f"ocw_{workspace_id.replace('-', '')[:20]}"
        conn.execute(
            """INSERT INTO user_workspaces
            (id, user_id, name, slug, openclaw_workspace_id, settings_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                workspace_id,
                user_id,
                "我的龙虾工作区",
                slug,
                openclaw_workspace_id,
                json.dumps(self._normalize_workspace_settings(DEFAULT_WORKSPACE_SETTINGS), ensure_ascii=False),
                now,
                now,
            ),
        )
        permissions = ADMIN_PERMISSIONS if is_admin else DEFAULT_PERMISSIONS
        for key, allowed in permissions.items():
            conn.execute(
                """INSERT OR REPLACE INTO workspace_permissions
                (workspace_id, permission_key, allowed, updated_at)
                VALUES (?, ?, ?, ?)""",
                (workspace_id, key, int(bool(allowed)), now),
            )
        return self._row_to_workspace(
            conn.execute("SELECT * FROM user_workspaces WHERE id = ?", (workspace_id,)).fetchone()
        )

    def create_invite_code(
        self,
        created_by_user_id: str | None,
        code: str | None = None,
        max_uses: int = 1,
        note: str = "",
        expires_at: str | None = None,
    ) -> dict:
        normalized = normalize_invite_code(code or generate_invite_code())
        if len(normalized) != INVITE_CODE_LEN:
            raise ValueError("邀请码必须是 6 个字符")
        max_uses = max(1, int(max_uses or 1))
        code_hash = hash_invite_code(normalized)
        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO invite_codes
                (code_hash, code_display, created_by_user_id, max_uses, used_count, expires_at, disabled, note, created_at)
                VALUES (?, ?, ?, ?, 0, ?, 0, ?, ?)""",
                (code_hash, mask_invite_code(normalized), created_by_user_id, max_uses, expires_at, note or "", iso_now()),
            )
            conn.commit()
            invite = self.get_invite_code(normalized) or {}
            invite["code"] = normalized
            return invite
        except sqlite3.IntegrityError as exc:
            if "invite_codes" in str(exc) or "code_hash" in str(exc):
                raise ValueError("邀请码已存在") from None
            raise
        finally:
            conn.close()

    def get_invite_code(self, code: str) -> dict | None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM invite_codes WHERE code_hash = ?",
                (hash_invite_code(code),),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_invite_codes(self, limit: int = 100) -> list[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM invite_codes ORDER BY created_at DESC LIMIT ?",
                (max(1, min(int(limit), 300)),),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def list_invite_code_usages(self, limit: int = 100) -> list[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                """SELECT status, reason, user_id, code_hash, code_display, used_at
                FROM invite_code_usages
                ORDER BY used_at DESC
                LIMIT ?""",
                (max(1, min(int(limit), 300)),),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def _record_invite_usage(
        self,
        conn,
        code_hash: str,
        code_display: str,
        user_id: str | None,
        status: str,
        reason: str,
        used_at: str | None = None,
    ) -> None:
        conn.execute(
            """INSERT INTO invite_code_usages
            (id, code_hash, code_display, user_id, status, reason, used_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                code_hash,
                code_display,
                user_id,
                status,
                reason or "",
                used_at or iso_now(),
            ),
        )

    def create_user(
        self,
        username: str,
        password: str,
        invite_code: str,
        display_name: str | None = None,
        email: str | None = None,
    ) -> dict:
        username = re.sub(r"\s+", "", username or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_\-.]{3,32}", username):
            raise ValueError("用户名需要 3-32 位，只能包含字母、数字、下划线、点和横线")
        if len(password or "") < 8:
            raise ValueError("密码至少需要 8 位")

        code = normalize_invite_code(invite_code)
        code_hash = hash_invite_code(code)
        code_display = mask_invite_code(code)
        if len(code) != INVITE_CODE_LEN:
            conn = self._conn()
            try:
                self._record_invite_usage(conn, code_hash, code_display, None, "failed", "invalid format")
                conn.commit()
            finally:
                conn.close()
            raise ValueError("邀请码必须是 6 个字符")

        conn = self._conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            invite = conn.execute("SELECT * FROM invite_codes WHERE code_hash = ?", (code_hash,)).fetchone()
            failure_reason = ""
            if not invite:
                failure_reason = "invalid"
            elif invite["disabled"]:
                failure_reason = "disabled"
            if failure_reason:
                self._record_invite_usage(conn, code_hash, code_display, None, "failed", failure_reason)
                conn.commit()
                raise ValueError("邀请码无效")
            if invite["expires_at"]:
                if datetime.fromisoformat(invite["expires_at"]) < utc_now():
                    self._record_invite_usage(conn, code_hash, code_display, None, "failed", "expired")
                    conn.commit()
                    raise ValueError("邀请码已过期")
            if invite["used_count"] >= invite["max_uses"]:
                self._record_invite_usage(conn, code_hash, code_display, None, "failed", "exhausted")
                conn.commit()
                raise ValueError("邀请码已被用完")

            existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
            if existing:
                self._record_invite_usage(conn, code_hash, code_display, None, "failed", "username exists")
                conn.commit()
                raise ValueError("用户名已存在")
            if email:
                existing_email = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
                if existing_email:
                    self._record_invite_usage(conn, code_hash, code_display, None, "failed", "email exists")
                    conn.commit()
                    raise ValueError("邮箱已被使用")

            is_first_user = self._user_count(conn) == 0
            user_id = str(uuid.uuid4())
            now = iso_now()
            conn.execute(
                """INSERT INTO users
                (id, username, display_name, email, password_hash, role, avatar_color, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    username,
                    display_name or username,
                    email or None,
                    hash_password(password),
                    "admin" if is_first_user else "user",
                    self._avatar_color(username),
                    now,
                ),
            )
            conn.execute(
                "UPDATE invite_codes SET used_count = used_count + 1 WHERE code_hash = ?",
                (code_hash,),
            )
            conn.execute(
                "UPDATE invite_codes SET disabled = 1 WHERE code_hash = ? AND used_count >= max_uses",
                (code_hash,),
            )
            self._record_invite_usage(conn, code_hash, code_display, user_id, "success", "", now)
            workspace = self._create_workspace(conn, user_id, username, is_admin=is_first_user)
            conn.execute(
                """INSERT INTO audit_logs
                (id, user_id, workspace_id, action, target_type, target_id, status, reason, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()),
                    user_id,
                    workspace["id"],
                    "auth.register",
                    "user",
                    user_id,
                    "ok",
                    "invite registration",
                    json.dumps({"invite_code_hash": code_hash, "first_user": is_first_user}, ensure_ascii=False),
                    now,
                ),
            )
            conn.commit()
            return self.get_user_bundle(user_id) or {}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _avatar_color(self, username: str) -> str:
        palette = ["#2f6fed", "#009b72", "#b15c00", "#8a4fff", "#d13f3f", "#1677a3"]
        digest = hashlib.sha256(username.encode("utf-8")).digest()
        return palette[digest[0] % len(palette)]

    def get_user_by_username(self, username: str) -> dict | None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ?",
                (username,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_user_by_id(self, user_id: str) -> dict | None:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return self._row_to_user(row)
        finally:
            conn.close()

    def authenticate(self, username: str, password: str) -> dict | None:
        raw_user = self.get_user_by_username(username)
        if not raw_user or raw_user["disabled"]:
            return None
        if not verify_password(password, raw_user["password_hash"]):
            return None
        conn = self._conn()
        try:
            conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (iso_now(), raw_user["id"]))
            conn.commit()
        finally:
            conn.close()
        return self.get_user_bundle(raw_user["id"])

    def create_session(self, user_id: str, user_agent: str = "", ip_address: str = "") -> tuple[str, dict]:
        token = secrets.token_urlsafe(36)
        now = utc_now()
        expires = now + timedelta(days=SESSION_DAYS)
        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO user_sessions
                (token_hash, user_id, created_at, expires_at, last_seen_at, user_agent, ip_address, revoked)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)""",
                (
                    hash_session_token(token),
                    user_id,
                    now.isoformat(),
                    expires.isoformat(),
                    now.isoformat(),
                    user_agent[:300],
                    ip_address[:80],
                ),
            )
            conn.commit()
            return token, {"expires_at": expires.isoformat()}
        finally:
            conn.close()

    def get_user_by_session(self, token: str) -> dict | None:
        if not token:
            return None
        token_hash = hash_session_token(token)
        conn = self._conn()
        try:
            row = conn.execute(
                """SELECT s.user_id, s.expires_at, s.revoked, u.disabled
                FROM user_sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = ?""",
                (token_hash,),
            ).fetchone()
            if not row or row["revoked"]:
                return None
            if row["disabled"]:
                conn.execute("UPDATE user_sessions SET revoked = 1 WHERE token_hash = ?", (token_hash,))
                conn.commit()
                return None
            try:
                if datetime.fromisoformat(row["expires_at"]) < utc_now():
                    return None
            except Exception:
                return None
            conn.execute(
                "UPDATE user_sessions SET last_seen_at = ? WHERE token_hash = ?",
                (iso_now(), token_hash),
            )
            conn.commit()
            return self.get_user_bundle(row["user_id"])
        finally:
            conn.close()

    def revoke_session(self, token: str) -> None:
        if not token:
            return
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE user_sessions SET revoked = 1 WHERE token_hash = ?",
                (hash_session_token(token),),
            )
            conn.commit()
        finally:
            conn.close()

    def get_user_bundle(self, user_id: str) -> dict | None:
        user = self.get_user_by_id(user_id)
        if not user:
            return None
        workspace = self.ensure_workspace(user["id"], user["username"], user["role"] == "admin")
        if user["role"] == "admin":
            self._ensure_admin_permissions(workspace["id"])
        return {
            "user": user,
            "workspace": workspace,
            "permissions": self.get_permissions(workspace["id"]),
        }

    def _ensure_admin_permissions(self, workspace_id: str) -> None:
        conn = self._conn()
        try:
            now = iso_now()
            for key in DEFAULT_PERMISSIONS:
                conn.execute(
                    """INSERT OR REPLACE INTO workspace_permissions
                    (workspace_id, permission_key, allowed, updated_at)
                    VALUES (?, ?, 1, ?)""",
                    (workspace_id, key, now),
                )
            conn.commit()
        finally:
            conn.close()

    def ensure_workspace(self, user_id: str, username: str = "user", is_admin: bool = False) -> dict:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM user_workspaces WHERE user_id = ? ORDER BY created_at ASC LIMIT 1",
                (user_id,),
            ).fetchone()
            if row:
                return self._row_to_workspace(row)
            workspace = self._create_workspace(conn, user_id, username, is_admin)
            conn.commit()
            return workspace
        finally:
            conn.close()

    def get_permissions(self, workspace_id: str) -> dict[str, bool]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT permission_key, allowed FROM workspace_permissions WHERE workspace_id = ?",
                (workspace_id,),
            ).fetchall()
            permissions = dict(DEFAULT_PERMISSIONS)
            for row in rows:
                permissions[row["permission_key"]] = bool(row["allowed"])
            return permissions
        finally:
            conn.close()

    def set_permission(self, workspace_id: str, key: str, allowed: bool) -> dict[str, bool]:
        if key not in DEFAULT_PERMISSIONS:
            raise ValueError("未知权限")
        conn = self._conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO workspace_permissions
                (workspace_id, permission_key, allowed, updated_at)
                VALUES (?, ?, ?, ?)""",
                (workspace_id, key, int(bool(allowed)), iso_now()),
            )
            conn.commit()
            return self.get_permissions(workspace_id)
        finally:
            conn.close()

    def update_workspace_settings(self, workspace_id: str, settings: dict[str, Any]) -> dict:
        current = self.get_workspace(workspace_id)
        if not current:
            raise ValueError("工作区不存在")
        merged = self._normalize_workspace_settings({**current.get("settings", {}), **(settings or {})})
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE user_workspaces SET settings_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(merged, ensure_ascii=False), iso_now(), workspace_id),
            )
            conn.commit()
            return self.get_workspace(workspace_id) or {}
        finally:
            conn.close()

    def update_workspace_name(self, workspace_id: str, name: str) -> dict:
        clean_name = re.sub(r"\s+", " ", (name or "")).strip()
        if not clean_name:
            raise ValueError("工作区名称不能为空")
        current = self.get_workspace(workspace_id)
        if not current:
            raise ValueError("工作区不存在")
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE user_workspaces SET name = ?, updated_at = ? WHERE id = ?",
                (clean_name[:80], iso_now(), workspace_id),
            )
            conn.commit()
            return self.get_workspace(workspace_id) or current
        finally:
            conn.close()

    def get_workspace(self, workspace_id: str) -> dict | None:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM user_workspaces WHERE id = ?", (workspace_id,)).fetchone()
            return self._row_to_workspace(row)
        finally:
            conn.close()

    def get_workspace_by_openclaw_workspace_id(self, openclaw_workspace_id: str) -> dict | None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM user_workspaces WHERE openclaw_workspace_id = ?",
                (openclaw_workspace_id,),
            ).fetchone()
            return self._row_to_workspace(row)
        finally:
            conn.close()

    def get_user_bundle_by_openclaw_workspace_id(self, openclaw_workspace_id: str) -> dict | None:
        workspace = self.get_workspace_by_openclaw_workspace_id(openclaw_workspace_id)
        if not workspace:
            return None
        user = self.get_user_by_id(workspace["user_id"])
        if not user or user.get("disabled"):
            return None
        if user["role"] == "admin":
            self._ensure_admin_permissions(workspace["id"])
        return {
            "user": user,
            "workspace": workspace,
            "permissions": self.get_permissions(workspace["id"]),
        }

    def record_audit(
        self,
        action: str,
        user_id: str | None = None,
        workspace_id: str | None = None,
        target_type: str = "",
        target_id: str = "",
        tool_name: str = "",
        status: str = "ok",
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        entry_id = str(uuid.uuid4())
        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO audit_logs
                (id, user_id, workspace_id, action, target_type, target_id, tool_name, status, reason, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry_id,
                    user_id,
                    workspace_id,
                    action,
                    target_type,
                    target_id,
                    tool_name,
                    status,
                    reason or "",
                    json.dumps(metadata or {}, ensure_ascii=False),
                    iso_now(),
                ),
            )
            conn.commit()
            return {"id": entry_id, "status": status}
        finally:
            conn.close()

    def list_audit_logs(self, workspace_id: str, limit: int = 100) -> list[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                """SELECT * FROM audit_logs
                WHERE workspace_id = ?
                ORDER BY created_at DESC
                LIMIT ?""",
                (workspace_id, max(1, min(int(limit), 300))),
            ).fetchall()
            return [
                {
                    **dict(row),
                    "metadata": safe_json_loads(row["metadata_json"], {}),
                }
                for row in rows
            ]
        finally:
            conn.close()

    def create_memory(
        self,
        user_id: str,
        workspace_id: str,
        title: str,
        content: str,
        code: str = "",
        tags: list[str] | None = None,
        source: str = "manual",
    ) -> dict:
        memory_id = str(uuid.uuid4())
        now = iso_now()
        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO research_memories
                (id, user_id, workspace_id, code, title, content, tags_json, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    memory_id,
                    user_id,
                    workspace_id,
                    code or "",
                    title.strip()[:160] or "研究记忆",
                    content.strip(),
                    json.dumps(tags or [], ensure_ascii=False),
                    source or "manual",
                    now,
                    now,
                ),
            )
            conn.commit()
            return self.get_memory(memory_id) or {}
        finally:
            conn.close()

    def get_memory(self, memory_id: str) -> dict | None:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM research_memories WHERE id = ?", (memory_id,)).fetchone()
            if not row:
                return None
            item = dict(row)
            item["tags"] = safe_json_loads(item.pop("tags_json"), [])
            return item
        finally:
            conn.close()

    def list_memories(self, workspace_id: str, query: str = "", limit: int = 50) -> list[dict]:
        query = (query or "").strip()
        conn = self._conn()
        try:
            if query:
                like = f"%{query}%"
                rows = conn.execute(
                    """SELECT * FROM research_memories
                    WHERE workspace_id = ?
                    AND (title LIKE ? OR content LIKE ? OR code LIKE ? OR tags_json LIKE ?)
                    ORDER BY updated_at DESC
                    LIMIT ?""",
                    (workspace_id, like, like, like, like, max(1, min(int(limit), 200))),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM research_memories
                    WHERE workspace_id = ?
                    ORDER BY updated_at DESC
                    LIMIT ?""",
                    (workspace_id, max(1, min(int(limit), 200))),
                ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["tags"] = safe_json_loads(item.pop("tags_json"), [])
                result.append(item)
            return result
        finally:
            conn.close()

    def delete_memory(self, workspace_id: str, memory_id: str) -> bool:
        conn = self._conn()
        try:
            cur = conn.execute(
                "DELETE FROM research_memories WHERE workspace_id = ? AND id = ?",
                (workspace_id, memory_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def save_daily_report(
        self,
        user_id: str,
        workspace_id: str,
        trade_date: str,
        title: str,
        content: dict[str, Any],
    ) -> dict:
        report_id = str(uuid.uuid4())
        now = iso_now()
        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO daily_reports
                (id, user_id, workspace_id, trade_date, title, content_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(workspace_id, trade_date) DO UPDATE SET
                    title=excluded.title,
                    content_json=excluded.content_json,
                    created_at=excluded.created_at""",
                (
                    report_id,
                    user_id,
                    workspace_id,
                    trade_date,
                    title,
                    json.dumps(content, ensure_ascii=False),
                    now,
                ),
            )
            conn.commit()
            return self.get_daily_report(workspace_id, trade_date) or {}
        finally:
            conn.close()

    def get_daily_report(self, workspace_id: str, trade_date: str) -> dict | None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM daily_reports WHERE workspace_id = ? AND trade_date = ?",
                (workspace_id, trade_date),
            ).fetchone()
            if not row:
                return None
            item = dict(row)
            item["content"] = safe_json_loads(item.pop("content_json"), {})
            return item
        finally:
            conn.close()

    def list_daily_reports(self, workspace_id: str, limit: int = 30) -> list[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                """SELECT * FROM daily_reports
                WHERE workspace_id = ?
                ORDER BY trade_date DESC
                LIMIT ?""",
                (workspace_id, max(1, min(int(limit), 120))),
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["content"] = safe_json_loads(item.pop("content_json"), {})
                result.append(item)
            return result
        finally:
            conn.close()

    def upsert_skill(
        self,
        workspace_id: str,
        name: str,
        version: str = "",
        status: str = "installed",
        source: str = "",
        permissions: list[str] | None = None,
    ) -> dict:
        skill_id = str(uuid.uuid4())
        now = iso_now()
        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO openclaw_skill_records
                (id, workspace_id, name, version, status, source, permissions_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(workspace_id, name) DO UPDATE SET
                    version=excluded.version,
                    status=excluded.status,
                    source=excluded.source,
                    permissions_json=excluded.permissions_json,
                    updated_at=excluded.updated_at""",
                (
                    skill_id,
                    workspace_id,
                    name.strip(),
                    version or "",
                    status or "installed",
                    source or "",
                    json.dumps(permissions or [], ensure_ascii=False),
                    now,
                    now,
                ),
            )
            conn.commit()
            return self.get_skill(workspace_id, name) or {}
        finally:
            conn.close()

    def get_skill(self, workspace_id: str, name: str) -> dict | None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM openclaw_skill_records WHERE workspace_id = ? AND name = ?",
                (workspace_id, name),
            ).fetchone()
            if not row:
                return None
            item = dict(row)
            item["permissions"] = safe_json_loads(item.pop("permissions_json"), [])
            return item
        finally:
            conn.close()

    def list_skills(self, workspace_id: str) -> list[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM openclaw_skill_records WHERE workspace_id = ? ORDER BY updated_at DESC",
                (workspace_id,),
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["permissions"] = safe_json_loads(item.pop("permissions_json"), [])
                result.append(item)
            return result
        finally:
            conn.close()

    def _row_to_skill_request(self, row) -> dict | None:
        if not row:
            return None
        return dict(row)

    def create_skill_install_request(
        self,
        workspace_id: str,
        user_id: str,
        skill_name: str,
        version: str = "",
        source: str = "",
        reason: str = "",
        note: str = "",
        status: str = "pending",
        decided_by_user_id: str | None = None,
        decided_at: str | None = None,
    ) -> dict:
        request_id = str(uuid.uuid4())
        now = iso_now()
        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO skill_install_requests
                (id, workspace_id, user_id, skill_name, version, source, status, reason, note,
                 decided_by_user_id, decided_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    request_id,
                    workspace_id,
                    user_id,
                    skill_name.strip(),
                    version or "",
                    source or "",
                    status or "pending",
                    reason or "",
                    note or "",
                    decided_by_user_id,
                    decided_at,
                    now,
                    now,
                ),
            )
            conn.commit()
            return self.get_skill_install_request(request_id) or {}
        finally:
            conn.close()

    def get_skill_install_request(self, request_id: str, workspace_id: str | None = None) -> dict | None:
        conn = self._conn()
        try:
            if workspace_id:
                row = conn.execute(
                    "SELECT * FROM skill_install_requests WHERE id = ? AND workspace_id = ?",
                    (request_id, workspace_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM skill_install_requests WHERE id = ?",
                    (request_id,),
                ).fetchone()
            return self._row_to_skill_request(row)
        finally:
            conn.close()

    def get_latest_skill_install_request(
        self,
        workspace_id: str,
        skill_name: str,
        status: str | None = None,
    ) -> dict | None:
        conn = self._conn()
        try:
            params: list[Any] = [workspace_id, skill_name.strip()]
            status_clause = ""
            if status:
                status_clause = " AND status = ?"
                params.append(status)
            row = conn.execute(
                f"""SELECT * FROM skill_install_requests
                WHERE workspace_id = ? AND skill_name = ?{status_clause}
                ORDER BY created_at DESC
                LIMIT 1""",
                tuple(params),
            ).fetchone()
            return self._row_to_skill_request(row)
        finally:
            conn.close()

    def list_skill_install_requests(
        self,
        workspace_id: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        conn = self._conn()
        try:
            params: list[Any] = [workspace_id]
            where = "workspace_id = ?"
            if status:
                where += " AND status = ?"
                params.append(status)
            rows = conn.execute(
                f"""SELECT * FROM skill_install_requests
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT ?""",
                (*params, max(1, min(int(limit), 300))),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def update_skill_install_request(
        self,
        request_id: str,
        workspace_id: str,
        **updates: Any,
    ) -> dict | None:
        current = self.get_skill_install_request(request_id, workspace_id=workspace_id)
        if not current:
            return None
        allowed = {
            "skill_name",
            "version",
            "source",
            "status",
            "reason",
            "note",
            "decided_by_user_id",
            "decided_at",
        }
        changes = {key: updates[key] for key in allowed if key in updates}
        if not changes:
            return current
        merged = {**current, **changes, "updated_at": iso_now()}
        conn = self._conn()
        try:
            conn.execute(
                """UPDATE skill_install_requests SET
                skill_name = ?,
                version = ?,
                source = ?,
                status = ?,
                reason = ?,
                note = ?,
                decided_by_user_id = ?,
                decided_at = ?,
                updated_at = ?
                WHERE id = ? AND workspace_id = ?""",
                (
                    merged["skill_name"],
                    merged["version"],
                    merged["source"],
                    merged["status"],
                    merged["reason"],
                    merged["note"],
                    merged["decided_by_user_id"],
                    merged["decided_at"],
                    merged["updated_at"],
                    request_id,
                    workspace_id,
                ),
            )
            conn.commit()
            return self.get_skill_install_request(request_id, workspace_id=workspace_id)
        finally:
            conn.close()


account_store = AccountStore()
