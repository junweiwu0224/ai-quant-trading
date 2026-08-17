import hashlib
import importlib
import json

import pytest

from dashboard.account_store import AccountStore, normalize_invite_code
from dashboard.app import app
from utils.db import get_connection


@pytest.fixture(autouse=True)
def isolated_account_store(monkeypatch, tmp_path):
    store = AccountStore(tmp_path / "accounts.db")

    import dashboard.account_store as account_store_module
    import dashboard.routers.account as account_router
    import dashboard.session as session_module

    app_module = importlib.import_module("dashboard.app")
    monkeypatch.setattr(account_store_module, "account_store", store)
    monkeypatch.setattr(account_router, "account_store", store)
    monkeypatch.setattr(session_module, "account_store", store)
    monkeypatch.setattr(app_module, "account_store", store)
    yield store


def _register(client, username, invite_code="LOCAL1", password="Playwright123!", **extra):
    payload = {
        "username": username,
        "password": password,
        "invite_code": invite_code,
        "display_name": extra.pop("display_name", username.title()),
        "email": extra.pop("email", None),
        **extra,
    }
    return client.post("/api/account/register", json=payload)


def test_register_bootstraps_workspace_session_and_audit(client, isolated_account_store):
    resp = _register(client, "alice", display_name="Alice")

    assert resp.status_code == 200
    body = resp.json()
    assert body["authenticated"] is True
    assert body["user"]["username"] == "alice"
    assert body["workspace"]["openclaw_workspace_id"].startswith("ocw_")
    assert body["permissions"]["chat"] is True
    assert "quant_session=" in resp.headers["set-cookie"]

    audit_rows = isolated_account_store.list_audit_logs(body["workspace"]["id"], limit=10)
    register_audit = next(row for row in audit_rows if row["action"] == "auth.register")
    assert register_audit["user_id"] == body["user"]["id"]
    assert "invite_code" not in register_audit["metadata"]


def test_account_me_reports_unauthenticated_without_session(client):
    resp = client.get("/api/account/me")

    assert resp.status_code == 200
    assert resp.json() == {"authenticated": False}


def test_invite_and_permission_endpoints_are_admin_only(client):
    admin_resp = _register(client, "admin")
    assert admin_resp.status_code == 200

    admin_invite_resp = client.post(
        "/api/account/invites",
        json={"code": "USER02", "max_uses": 1, "note": "user invite"},
    )
    assert admin_invite_resp.status_code == 200
    user_code = admin_invite_resp.json()["invite"]["code"]

    with client:
        user_resp = _register(client, "regular", invite_code=user_code)
        assert user_resp.status_code == 200
        assert user_resp.json()["permissions"]["admin"] is False

        assert client.get("/api/account/invites").status_code == 403
        assert client.post(
            "/api/account/invites",
            json={"code": "NOPE02", "max_uses": 1, "note": "blocked"},
        ).status_code == 403
        assert client.put(
            "/api/account/permissions",
            json={"permission_key": "chat", "allowed": False},
        ).status_code == 403


def test_invite_codes_store_only_hash_and_remain_lookupable(isolated_account_store):
    invite = isolated_account_store.create_invite_code(None, code="Ab12cD", max_uses=2, note="bootstrap")
    expected_hash = hashlib.sha256(normalize_invite_code("Ab12cD").encode("utf-8")).hexdigest()

    conn = get_connection(isolated_account_store.db_path, readonly=True)
    try:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(invite_codes)").fetchall()}
        row = conn.execute("SELECT * FROM invite_codes WHERE code_hash = ?", (expected_hash,)).fetchone()
    finally:
        conn.close()

    assert "code" not in columns
    assert "code_hash" in columns
    assert row["code_hash"] == expected_hash
    assert row["code_display"] == "AB****"
    assert invite["code"] == "AB12CD"


def test_failed_invite_attempt_is_recorded(isolated_account_store):
    before = isolated_account_store.list_invite_code_usages(limit=10)

    with pytest.raises(ValueError):
        isolated_account_store.create_user("bob", "Password123!", "AAAAAA")

    after = isolated_account_store.list_invite_code_usages(limit=10)
    assert len(after) == len(before) + 1
    latest = after[0]
    assert latest["status"] == "failed"
    assert latest["reason"]
    assert latest["user_id"] is None
    assert latest["code_hash"] == hashlib.sha256(b"AAAAAA").hexdigest()
    assert latest["code_display"] == "AA****"


def test_plaintext_invite_databases_migrate_to_hash_lookup(tmp_path):
    db_path = tmp_path / "legacy.db"
    conn = get_connection(db_path)
    try:
        conn.execute(
            """CREATE TABLE invite_codes (
            code TEXT PRIMARY KEY,
            created_by_user_id TEXT,
            max_uses INTEGER NOT NULL DEFAULT 1,
            used_count INTEGER NOT NULL DEFAULT 0,
            expires_at TEXT,
            disabled INTEGER NOT NULL DEFAULT 0,
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """INSERT INTO invite_codes
            (code, created_by_user_id, max_uses, used_count, expires_at, disabled, note, created_at)
            VALUES ('LEGACY', NULL, 2, 0, NULL, 0, 'legacy', '2026-05-24T00:00:00+00:00')"""
        )
        conn.commit()
    finally:
        conn.close()

    store = AccountStore(db_path)
    bundle = store.create_user("legacyuser", "Password123!", "legacy")

    conn = get_connection(db_path, readonly=True)
    try:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(invite_codes)").fetchall()}
        audit = conn.execute(
            "SELECT metadata_json FROM audit_logs WHERE action = 'auth.register'"
        ).fetchone()
    finally:
        conn.close()

    assert bundle["user"]["username"] == "legacyuser"
    assert "code" not in columns
    assert "code_hash" in columns
    assert "invite_code" not in json.loads(audit["metadata_json"])


def test_disabled_user_session_is_not_authenticated(isolated_account_store):
    bundle = isolated_account_store.create_user("disableduser", "Password123!", "LOCAL1")
    token, _ = isolated_account_store.create_session(bundle["user"]["id"])

    conn = get_connection(isolated_account_store.db_path)
    try:
        conn.execute("UPDATE users SET disabled = 1 WHERE id = ?", (bundle["user"]["id"],))
        conn.commit()
    finally:
        conn.close()

    assert isolated_account_store.get_user_by_session(token) is None


def test_duplicate_invite_code_raises_value_error(isolated_account_store):
    isolated_account_store.create_invite_code(None, code="DUPL01")

    with pytest.raises(ValueError, match="邀请码已存在"):
        isolated_account_store.create_invite_code(None, code="dupl01")


def test_production_does_not_bootstrap_known_default_invite(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("QUANT_DEFAULT_INVITE_CODE", raising=False)

    store = AccountStore(tmp_path / "prod.db")

    assert store.get_invite_code("LOCAL1") is None


def test_session_cookie_is_secure_in_production(monkeypatch):
    import dashboard.session as session_module

    monkeypatch.setenv("APP_ENV", "production")

    assert session_module.session_cookie_options()["secure"] is True
