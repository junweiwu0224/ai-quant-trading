import asyncio

import pytest
from fastapi import HTTPException

from dashboard.account_store import AccountStore
from dashboard.routers import openclaw as openclaw_router


def test_skill_request_storage_round_trip(tmp_path):
    store = AccountStore(tmp_path / "skills.db")
    request = store.create_skill_install_request(
        workspace_id="workspace-1",
        user_id="user-1",
        skill_name="alpha-skill",
        version="1.2.3",
        source="manual",
        reason="need it",
        note="quiet install",
    )

    latest = store.get_latest_skill_install_request("workspace-1", "alpha-skill", status="pending")
    assert latest["id"] == request["id"]
    assert latest["skill_name"] == "alpha-skill"

    updated = store.update_skill_install_request(
        request["id"],
        "workspace-1",
        status="approved",
        decided_by_user_id="approver-1",
        decided_at="2026-05-24T00:00:00+00:00",
    )
    assert updated["status"] == "approved"
    assert updated["decided_by_user_id"] == "approver-1"


def test_chat_skill_install_approve_deny_and_list(monkeypatch):
    account = {
        "user": {"id": "user-1"},
        "workspace": {"id": "workspace-1", "openclaw_workspace_id": "ocw_workspace_1"},
        "permissions": {"chat": True, "manage_skills": True},
    }
    created = []
    updates = []
    audits = []
    skills = []

    monkeypatch.setattr(
        openclaw_router.account_store,
        "create_skill_install_request",
        lambda **kwargs: created.append(kwargs)
        or {
            "id": "req-1",
            "workspace_id": kwargs["workspace_id"],
            "user_id": kwargs["user_id"],
            "skill_name": kwargs["skill_name"],
            "version": kwargs.get("version", ""),
            "source": kwargs.get("source", ""),
            "status": "pending",
            "reason": kwargs.get("reason", ""),
            "note": kwargs.get("note", ""),
            "decided_by_user_id": None,
            "decided_at": None,
        },
    )
    monkeypatch.setattr(
        openclaw_router.account_store,
        "list_skill_install_requests",
        lambda workspace_id, status=None, limit=100: [
            {"id": "req-1", "skill_name": "alpha-skill", "status": "pending"}
        ],
    )
    monkeypatch.setattr(
        openclaw_router.account_store,
        "get_latest_skill_install_request",
        lambda workspace_id, skill_name, status=None: {"id": "req-1", "skill_name": skill_name, "status": "pending"},
    )
    monkeypatch.setattr(
        openclaw_router.account_store,
        "get_skill_install_request",
        lambda request_id, workspace_id=None: {"id": request_id, "skill_name": "alpha-skill", "status": "pending"},
    )
    monkeypatch.setattr(
        openclaw_router.account_store,
        "update_skill_install_request",
        lambda request_id, workspace_id, **kwargs: updates.append((request_id, kwargs))
        or {
            "id": request_id,
            "skill_name": "alpha-skill",
            "status": kwargs["status"],
            "reason": kwargs.get("reason", ""),
            "note": kwargs.get("note", ""),
            "decided_by_user_id": kwargs.get("decided_by_user_id"),
            "decided_at": kwargs.get("decided_at"),
        },
    )
    monkeypatch.setattr(
        openclaw_router.account_store,
        "upsert_skill",
        lambda **kwargs: skills.append(kwargs) or {"id": "skill-1", **kwargs},
    )
    monkeypatch.setattr(
        openclaw_router.account_store,
        "record_audit",
        lambda *args, **kwargs: audits.append((args, kwargs)) or {"id": "audit-1"},
    )

    install = asyncio.run(
        openclaw_router.chat(openclaw_router.ChatRequest(message="/skill install alpha-skill version=1.2.3"), account=account)
    )
    approve = asyncio.run(
        openclaw_router.chat(openclaw_router.ChatRequest(message="/skill approve req-1"), account=account)
    )
    deny = asyncio.run(
        openclaw_router.chat(openclaw_router.ChatRequest(message="!skill deny alpha-skill testing complete"), account=account)
    )
    listing = asyncio.run(
        openclaw_router.chat(openclaw_router.ChatRequest(message="@skill list"), account=account)
    )

    assert install["mode"] == "skill-command"
    assert install["request"]["status"] == "pending"
    assert approve["result"]["status"] == "approved"
    assert skills and skills[0]["name"] == "alpha-skill"
    assert deny["result"]["status"] == "denied"
    assert listing["items"]
    assert audits


def test_chat_skill_command_requires_manage_skills_permission(monkeypatch):
    account = {
        "user": {"id": "user-1"},
        "workspace": {"id": "workspace-1", "openclaw_workspace_id": "ocw_workspace_1"},
        "permissions": {"chat": True, "manage_skills": False},
    }

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            openclaw_router.chat(
                openclaw_router.ChatRequest(message="/skill install alpha-skill"),
                account=account,
            )
        )

    assert exc.value.status_code == 403


def test_status_exposes_recent_skill_command_history(monkeypatch):
    account = {
        "user": {"id": "user-1"},
        "workspace": {"id": "workspace-1", "openclaw_workspace_id": "ocw_workspace_1", "settings": {}},
        "permissions": {"chat": True, "manage_skills": False},
    }

    async def fake_health(workspace_id):
        return {"ok": False}

    monkeypatch.setattr(openclaw_router.openclaw_gateway, "health", fake_health)
    monkeypatch.setattr(
        openclaw_router.account_store,
        "list_skill_install_requests",
        lambda workspace_id, limit=10, status=None: [
            {"id": "req-1", "skill_name": "alpha-skill", "status": "pending"}
        ],
    )

    response = asyncio.run(openclaw_router.status(account=account))

    assert response["skill_command_history"][0]["id"] == "req-1"
    assert response["skill_command_history"][0]["skill_name"] == "alpha-skill"
