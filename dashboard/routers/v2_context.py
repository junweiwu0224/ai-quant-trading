"""Durable V2 context read model for the Vue workspaces."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from config.settings import DB_DIR
from dashboard.session import current_account
from engine.models import PaperConfig
from engine.operations_store import OperationsStore
from engine.paper_read_model import status as paper_status
from engine.paper_projection import ensure_projection_schema
from engine.paper_runtime import PaperRuntimeStore

router = APIRouter()


def _task_rows(account_id: str, workspace_id: str) -> list[dict[str, Any]]:
    """Return only commands belonging to the requested durable scope."""
    store = OperationsStore(DB_DIR / "operations.db")
    try:
        rows = store.connection.execute(
            "SELECT t.id, t.command_id, t.status, t.created_at, t.updated_at, "
            "c.kind, c.payload_json FROM tasks t JOIN commands c ON c.id = t.command_id "
            "ORDER BY t.updated_at DESC LIMIT 100"
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except (TypeError, ValueError):
                continue
            intent = (payload.get("batch_dict") or {}).get("intents") or [{}]
            intent_context = intent[0] if isinstance(intent[0], dict) else {}
            task_account = payload.get("account_id") or intent_context.get("account_id")
            task_workspace = payload.get("workspace_id") or "default"
            if task_account != account_id or task_workspace != workspace_id:
                continue
            result.append({
                "id": row["id"],
                "command_id": row["command_id"],
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "kind": row["kind"],
            })
            if len(result) >= 20:
                break
        return result
    finally:
        store.close()


def _paper_account_id(account: dict[str, Any], workspace_id: str) -> str:
    workspace = account.get("workspace") or {}
    settings = workspace.get("settings") or {}
    configured = settings.get("paper_account_id")
    if configured:
        return str(configured)
    # Keep the existing default account for the default/test workspace. Named
    # workspaces are fail-closed until their Paper account is explicitly bound.
    return "paper-default" if workspace_id == "default" else ""


async def _build_context(account_id: str, workspace_id: str) -> dict[str, Any]:
    db_path = str(PaperConfig().db_path)
    ensure_projection_schema(db_path)
    paper = paper_status(db_path, account_id, workspace_id) if account_id else {
        "execution_run_id": None,
        "status": "unknown",
        "running": False,
        "reconciliation_required": True,
        "reconciliations": [],
        "account_id": account_id,
        "workspace_id": workspace_id,
        "environment": "paper",
        "source": "sqlite",
    }
    runtime = PaperRuntimeStore(db_path).get(account_id) if account_id else None
    tasks = _task_rows(account_id, workspace_id) if account_id else []
    reconciliation = paper.get("reconciliations", [])
    execution_status = paper.get("status") or "unknown"
    if not account_id:
        readiness = "unbound"
    elif reconciliation or paper.get("reconciliation_required"):
        readiness = "reconciliation_required"
    elif execution_status in {"blocked", "failed", "halted", "halt_requested", "reconciling", "reconciliation_blocked"}:
        readiness = execution_status
    elif not paper.get("execution_run_id"):
        readiness = "unbound"
    else:
        readiness = "ready"
    return {
        "schema_version": "v2-context-1",
        "workspace_id": workspace_id,
        "account_id": account_id,
        "environment": "paper",
        "live_enabled": False,
        "paper": paper,
        "execution_run": {"id": paper.get("execution_run_id"), "status": execution_status, "readiness": readiness},
        "runtime": {"status": runtime.status if runtime else "unknown", "owner_id": runtime.owner_id if runtime else None, "updated_at": runtime.updated_at if runtime else None},
        "tasks": tasks,
        "reconciliations": reconciliation,
        "ai_authority": "non_authoritative",
        "source": "sqlite",
    }


@router.get("/context")
async def get_v2_context(
    account_id: str = "paper-default",
    workspace_id: str = "default",
    account: dict[str, Any] = Depends(current_account),
) -> dict[str, Any]:
    """Return durable context scoped to the authenticated workspace only."""
    owned_workspace = str((account.get("workspace") or {}).get("id") or "")
    if workspace_id != "default" and workspace_id != owned_workspace:
        raise HTTPException(status_code=403, detail="workspace context is outside the current account")
    resolved_workspace = owned_workspace or workspace_id
    expected_account = _paper_account_id(account, resolved_workspace)
    if account_id not in {"paper-default", expected_account}:
        raise HTTPException(status_code=403, detail="paper account context is outside the current workspace")
    return await _build_context(expected_account, resolved_workspace)


__all__ = ["router", "get_v2_context", "_build_context"]
