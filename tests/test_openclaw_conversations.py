import importlib

import pytest

from dashboard.account_store import AccountStore
from data.storage.storage import DataStorage


@pytest.fixture(autouse=True)
def isolated_stores(monkeypatch, tmp_path):
    account_store = AccountStore(tmp_path / "accounts.db")
    conversation_store = DataStorage(f"sqlite:///{tmp_path / 'conversations.db'}")

    import dashboard.account_store as account_store_module
    import dashboard.routers.account as account_router
    import dashboard.routers.openclaw as openclaw_router
    import dashboard.session as session_module

    app_module = importlib.import_module("dashboard.app")

    monkeypatch.setattr(account_store_module, "account_store", account_store)
    monkeypatch.setattr(account_router, "account_store", account_store)
    monkeypatch.setattr(openclaw_router, "conversation_store", conversation_store)
    monkeypatch.setattr(session_module, "account_store", account_store)
    monkeypatch.setattr(app_module, "account_store", account_store)
    yield account_store, conversation_store


def test_openclaw_conversations_are_surface_scoped(client, isolated_stores):
    account_store, conversation_store = isolated_stores
    bundle = account_store.create_user("alice", "Password123!", "LOCAL1")
    token, _ = account_store.create_session(bundle["user"]["id"])
    client.cookies.set("quant_session", token)

    conversation_store.save_conversation(
        "llm-1",
        "Generic LLM",
        [{"role": "user", "content": "generic"}],
        workspace_id=bundle["workspace"]["id"],
        surface="llm",
    )

    resp = client.post(
        "/api/openclaw/conversations",
        json={
            "id": "oc-1",
            "title": "OpenClaw",
            "messages": [{"role": "user", "content": "openclaw"}],
        },
    )
    assert resp.status_code == 200

    openclaw_rows = client.get("/api/openclaw/conversations").json()["items"]
    llm_rows = conversation_store.list_conversations(
        workspace_id=bundle["workspace"]["id"],
        surface="llm",
    )

    assert [row["id"] for row in openclaw_rows] == ["oc-1"]
    assert [row["id"] for row in llm_rows] == ["llm-1"]
    assert client.get("/api/openclaw/conversations/llm-1").status_code == 404
