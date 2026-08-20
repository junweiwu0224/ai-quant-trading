from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from engine.operations_store import OperationsStore
from engine.research_facts import ResearchFactsStore


def test_v2_context_is_paper_fail_closed_and_scoped(monkeypatch, tmp_path: Path):
    db = tmp_path / "paper.db"
    ops = tmp_path / "operations.db"
    ResearchFactsStore(db).ensure_paper_run(account_id="acct-a", workspace_id="ws-a", codes=["000001"])
    store = OperationsStore(ops)
    try:
        store.accept_command(idempotency_key="a", kind="paper_start", payload={"account_id": "acct-a", "workspace_id": "ws-a"})
        store.accept_command(idempotency_key="b", kind="paper_start", payload={"account_id": "acct-b", "workspace_id": "ws-b"})
    finally:
        store.close()

    from dashboard.routers import v2_context

    monkeypatch.setattr(v2_context, "DB_DIR", tmp_path)
    monkeypatch.setattr(v2_context, "PaperConfig", lambda: type("Config", (), {"db_path": str(db)})())
    payload = asyncio.run(v2_context._build_context("acct-a", "ws-a"))
    assert payload["environment"] == "paper"
    assert payload["live_enabled"] is False
    assert payload["source"] == "sqlite"
    assert payload["workspace_id"] == "ws-a"
    assert payload["account_id"] == "acct-a"
    assert len(payload["tasks"]) == 1
    assert payload["tasks"][0]["kind"] == "paper_start"
    assert payload["execution_run"]["id"]
    assert payload["ai_authority"] == "non_authoritative"


def test_v2_context_auth_scope_rejects_cross_workspace(monkeypatch):
    from dashboard.routers import v2_context
    from fastapi import HTTPException

    account = {"workspace": {"id": "owned-workspace", "settings": {}}}
    with pytest.raises(HTTPException) as error:
        asyncio.run(v2_context.get_v2_context(account_id="paper-default", workspace_id="other-workspace", account=account))
    assert error.value.status_code == 403


def test_v2_context_named_workspace_without_bound_account_is_unbound(tmp_path: Path, monkeypatch):
    from dashboard.routers import v2_context

    db = tmp_path / "missing.db"
    monkeypatch.setattr(v2_context, "DB_DIR", tmp_path)
    monkeypatch.setattr(v2_context, "PaperConfig", lambda: type("Config", (), {"db_path": str(db)})())
    payload = asyncio.run(v2_context._build_context("", "named-workspace"))
    assert payload["execution_run"]["readiness"] == "unbound"
    assert payload["account_id"] == ""
    assert payload["tasks"] == []


def test_v2_context_without_database_is_unbound(tmp_path: Path, monkeypatch):
    from dashboard.routers import v2_context

    db = tmp_path / "missing.db"
    monkeypatch.setattr(v2_context, "DB_DIR", tmp_path)
    monkeypatch.setattr(v2_context, "PaperConfig", lambda: type("Config", (), {"db_path": str(db)})())
    payload = asyncio.run(v2_context._build_context("missing", "workspace"))
    assert payload["execution_run"]["readiness"] == "unbound"
    assert payload["execution_run"]["id"] is None
    assert payload["environment"] == "paper"
    assert payload["live_enabled"] is False
