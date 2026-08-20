from __future__ import annotations

import sqlite3
from pathlib import Path

from backup.manager import BackupManager
from engine.paper_projection import ensure_projection_schema
from engine.research_facts import ResearchFactsStore


def _paper_db(path: Path) -> str:
    store = ResearchFactsStore(path)
    run = store.ensure_paper_run(account_id="a", workspace_id="w", codes=["000001"])
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS paper_ledger (id INTEGER PRIMARY KEY AUTOINCREMENT, trade_id TEXT UNIQUE NOT NULL, execution_run_id TEXT NOT NULL, account_id TEXT NOT NULL, workspace_id TEXT NOT NULL, environment TEXT NOT NULL, order_intent_key TEXT NOT NULL, idempotency_key TEXT NOT NULL, instrument TEXT NOT NULL, side TEXT NOT NULL, filled_price REAL NOT NULL, filled_volume INTEGER NOT NULL, commission REAL NOT NULL DEFAULT 0, stamp_tax REAL NOT NULL DEFAULT 0, filled_at TEXT NOT NULL)")
        connection.execute("INSERT INTO paper_ledger(trade_id, execution_run_id, account_id, workspace_id, environment, order_intent_key, idempotency_key, instrument, side, filled_price, filled_volume, filled_at) VALUES (?, ?, ?, ?, 'paper', ?, ?, ?, 'buy', 10, 100, '2026-01-01T10:00:00+00:00')", ("trade-1", run.execution_run_id, "a", "w", "key-1", "key-1", "000001"))
        connection.commit()
    ensure_projection_schema(path)
    return run.execution_run_id


def test_backup_verify_restore_marks_paper_reconciliation(tmp_path: Path):
    source = tmp_path / "paper.db"
    _paper_db(source)
    backup_dir = tmp_path / "backup"
    manager = BackupManager()
    manifest = manager.backup(backup_dir, [source])
    assert manifest["databases"]
    verification = manager.restore(backup_dir, verify_only=True)
    paper = verification["databases"][0]
    assert paper["paper_database"] is True
    assert paper["paper_ledger_count"] == 1
    target = tmp_path / "restore"
    restored = manager.restore(backup_dir, target)
    assert restored["databases"][0]["restored_paper_runs_requiring_reconciliation"] == 1
    restored_db = next(target.glob("databases/*.db"))
    with sqlite3.connect(restored_db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM paper_reconciliations WHERE status = 'open'").fetchone()[0] == 1
        assert connection.execute("SELECT status FROM execution_runs").fetchone()[0] == "reconciling"


def test_verify_only_does_not_create_target(tmp_path: Path):
    source = tmp_path / "paper.db"
    _paper_db(source)
    backup_dir = tmp_path / "backup"
    BackupManager().backup(backup_dir, [source])
    target = tmp_path / "never-created"
    BackupManager().restore(backup_dir, target, verify_only=True)
    assert not target.exists()
