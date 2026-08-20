"""Read-only Paper API model sourced from SQLite facts and projections."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sqlite3

from engine.paper_projection import ensure_projection_schema, list_reconciliations
from engine.paper_runtime import PaperRuntimeStore
from utils.db import get_connection


def _latest_run(db_path: str | Path, account_id: str, workspace_id: str = "default") -> dict[str, Any] | None:
    with get_connection(db_path) as connection:
        try:
            row = connection.execute("SELECT * FROM execution_runs WHERE account_id = ? AND workspace_id = ? AND environment = 'paper' ORDER BY created_at DESC LIMIT 1", (account_id, workspace_id)).fetchone()
        except sqlite3.OperationalError:
            row = None
    return dict(row) if row else None


def status(db_path: str | Path, account_id: str = "paper-default", workspace_id: str = "default") -> dict[str, Any]:
    ensure_projection_schema(db_path)
    runtime = PaperRuntimeStore(db_path).get(account_id)
    run = _latest_run(db_path, account_id, workspace_id)
    with get_connection(db_path) as connection:
        reconciliation_rows = connection.execute(
            "SELECT * FROM paper_reconciliations WHERE account_id = ? AND workspace_id = ? "
            "AND environment = 'paper' AND status IN ('open', 'acknowledged', 'blocked') "
            "ORDER BY created_at DESC",
            (account_id, workspace_id),
        ).fetchall()
    reconciliations = [dict(row) for row in reconciliation_rows]
    runtime_status = runtime.status if runtime else "stopped"
    run_status = run["status"] if run else "stopped"
    effective_status = runtime_status if runtime else run_status
    blocked = bool(reconciliations) or effective_status in {
        "blocked", "reconciling", "reconciliation_blocked", "failed", "halted", "halt_requested"
    }
    return {
        "running": bool(runtime and runtime.status in {"starting", "running", "paused", "halt_requested"} and not blocked),
        "status": effective_status,
        "runtime_status": runtime_status,
        "execution_run_id": runtime.run_id if runtime else (run["execution_run_id"] if run else None),
        "account_id": account_id,
        "workspace_id": workspace_id,
        "environment": "paper",
        "reconciliation_required": blocked,
        "reconciliations": reconciliations,
        "source": "paper_ledger",
        "ready": bool(run and run_status in {"ready", "running"} and not blocked),
    }


def positions(db_path: str | Path, account_id: str = "paper-default", workspace_id: str = "default", execution_run_id: str | None = None) -> list[dict[str, Any]]:
    ensure_projection_schema(db_path)
    run = _latest_run(db_path, account_id, workspace_id) if execution_run_id is None else None
    run_id = execution_run_id or (run["execution_run_id"] if run else None)
    if not run_id:
        return []
    with get_connection(db_path) as connection:
        rows = connection.execute("SELECT * FROM paper_positions_v2 WHERE account_id = ? AND workspace_id = ? AND environment = 'paper' AND execution_run_id = ? ORDER BY updated_at DESC", (account_id, workspace_id, run_id)).fetchall()
    return [dict(row) for row in rows]


def trades(db_path: str | Path, account_id: str = "paper-default", workspace_id: str = "default", execution_run_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    ensure_projection_schema(db_path)
    run = _latest_run(db_path, account_id, workspace_id) if execution_run_id is None else None
    run_id = execution_run_id or (run["execution_run_id"] if run else None)
    if not run_id:
        return []
    with get_connection(db_path) as connection:
        rows = connection.execute("SELECT * FROM paper_trades_v2 WHERE account_id = ? AND workspace_id = ? AND environment = 'paper' AND execution_run_id = ? ORDER BY created_at DESC, ledger_id DESC LIMIT ?", (account_id, workspace_id, run_id, max(1, min(int(limit), 1000)))).fetchall()
    return [dict(row) for row in rows]


def equity(db_path: str | Path, account_id: str = "paper-default", workspace_id: str = "default", execution_run_id: str | None = None) -> list[dict[str, Any]]:
    ensure_projection_schema(db_path)
    run = _latest_run(db_path, account_id, workspace_id) if execution_run_id is None else None
    run_id = execution_run_id or (run["execution_run_id"] if run else None)
    if not run_id:
        return []
    with get_connection(db_path) as connection:
        rows = connection.execute("SELECT * FROM paper_equity_curve_v2 WHERE account_id = ? AND workspace_id = ? AND environment = 'paper' AND execution_run_id = ? ORDER BY timestamp", (account_id, workspace_id, run_id)).fetchall()
    return [dict(row) for row in rows]


def snapshot(db_path: str | Path, account_id: str = "paper-default", workspace_id: str = "default") -> dict[str, Any]:
    run = _latest_run(db_path, account_id, workspace_id)
    if not run:
        return {"cash": 0.0, "positions": [], "equity": 0.0, "execution_run_id": None, "source": "paper_ledger", "reconciliation_required": False}
    with get_connection(db_path) as connection:
        checkpoint = connection.execute("SELECT * FROM paper_projection_checkpoints WHERE projection_name = 'paper' AND account_id = ? AND workspace_id = ? AND execution_run_id = ?", (account_id, workspace_id, run["execution_run_id"])).fetchone()
        curve = connection.execute("SELECT * FROM paper_equity_curve_v2 WHERE account_id = ? AND workspace_id = ? AND execution_run_id = ? ORDER BY timestamp DESC LIMIT 1", (account_id, workspace_id, run["execution_run_id"])).fetchone()
        account = connection.execute("SELECT initial_cash FROM paper_accounts WHERE account_id = ? AND workspace_id = ? AND environment = 'paper'", (account_id, workspace_id)).fetchone()
        open_reconciliation = connection.execute("SELECT 1 FROM paper_reconciliations WHERE account_id = ? AND workspace_id = ? AND environment = 'paper' AND status IN ('open', 'acknowledged', 'blocked') LIMIT 1", (account_id, workspace_id)).fetchone()
    position_rows = positions(db_path, account_id, workspace_id, run["execution_run_id"])
    latest = dict(curve) if curve else {}
    initial_cash = float(account["initial_cash"]) if account else 0.0
    projection_ready = checkpoint is not None and checkpoint["status"] == "ready"
    cash = latest.get("cash", initial_cash)
    equity = latest.get("equity", cash)
    return {
        "cash": cash,
        "equity": equity,
        "market_value": latest.get("market_value", 0.0),
        "positions": position_rows,
        "execution_run_id": run["execution_run_id"],
        "source": "paper_ledger",
        "projection_version": checkpoint["content_hash"] if checkpoint else None,
        "reconciliation_required": bool(open_reconciliation) or not projection_ready,
        "updated_at": latest.get("timestamp"),
    }


__all__ = ["status", "positions", "trades", "equity", "snapshot"]
