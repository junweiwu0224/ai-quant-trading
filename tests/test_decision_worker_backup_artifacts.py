from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import config.settings as settings
from backup.manager import BackupManager
from decision.store import DecisionStore
from engine.decision_worker import DecisionWorker, SQLiteWorkerLease
from engine.events.outbox import SQLiteOutbox


def test_compose_worker_paths_match_the_container_mounts() -> None:
    compose = (Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text(encoding="utf-8")
    worker = compose.split("\n  worker:\n", 1)[1].split("\n  cloudflared:\n", 1)[0]

    assert "./backup:/app/backup" not in worker
    assert "DECISION_BACKUP_DIR=/app/data/backups/daily" in worker
    assert "DECISION_RECOVERY_DRILL_DIR=/app/data/backups/monthly-recovery" in worker
    assert "DECISION_ARTIFACT_DIRS=/app/data/decision-artifacts" in worker


def test_worker_daily_backup_reads_artifact_dirs_and_restores_temporary_payloads(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_dir = tmp_path / "db"
    backup_root = tmp_path / "daily-backups"
    artifact_dir = tmp_path / "decision-artifacts"
    artifact_file = artifact_dir / "reports" / "daily.json"
    artifact_file.parent.mkdir(parents=True)
    artifact_payload = b'{"status":"ready","source":"fixture"}\n'
    artifact_file.write_bytes(artifact_payload)

    monkeypatch.setattr(settings, "DB_DIR", database_dir)
    monkeypatch.setenv("DECISION_BACKUP_DIR", str(backup_root))
    monkeypatch.setenv("DECISION_ARTIFACT_DIRS", os.pathsep.join((str(artifact_dir),)))

    DecisionStore(database_dir / "decisions.db")
    lease = SQLiteWorkerLease(database_dir / "worker_leases.db")
    outbox = SQLiteOutbox(database_dir / "events.db")
    worker = DecisionWorker(lease, outbox, poll_interval_seconds=60)
    try:
        result = worker._run_daily_backup(
            scheduled_for=datetime(2026, 8, 15, 2, tzinfo=timezone.utc),
        )
    finally:
        worker.close()

    connection = sqlite3.connect(database_dir / "events.db")
    try:
        assert connection.execute("PRAGMA journal_mode").fetchone() == ("wal",)
    finally:
        connection.close()

    assert result["status"] == "created"
    backup_dir = backup_root / "2026-08-15"
    manifest_path = backup_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["metadata"]["artifact_dirs_configured"] == [str(artifact_dir)]
    assert [item["name"] for item in manifest["databases"]] == [
        "decisions.db",
        "events.db",
        "worker_leases.db",
    ]
    assert len(manifest["artifacts"]) == 1

    artifact = manifest["artifacts"][0]
    assert artifact["source"] == str(artifact_dir)
    assert artifact["file_count"] == 1
    artifact_file_record = artifact["files"][0]
    assert artifact_file_record["relative_path"] == "reports/daily.json"
    assert (backup_dir / artifact_file_record["path"]).read_bytes() == artifact_payload

    manager = BackupManager()
    verify_target = tmp_path / "verify-only-target"
    verification = manager.restore(backup_dir, verify_target, verify_only=True)
    assert verification["status"] == "verified"
    assert verification["verify_only"] is True
    assert verification["files_verified"] == manifest["file_count"]
    assert verification["artifacts"][0]["file_count"] == 1
    assert not verify_target.exists()

    restore_target = tmp_path / "restored"
    restored = manager.restore(backup_dir, restore_target)
    assert restored["status"] == "restored"

    restored_artifact_dir = Path(restored["artifacts"][0]["path"])
    assert restored_artifact_dir == restore_target / Path(artifact["restore_root"])
    assert (restored_artifact_dir / "reports" / "daily.json").read_bytes() == artifact_payload

    decisions_database = next(item for item in manifest["databases"] if item["name"] == "decisions.db")
    restored_database = restore_target / Path(decisions_database["restore_path"])
    connection = sqlite3.connect(restored_database)
    try:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='decision_runs'"
        ).fetchone() == ("decision_runs",)
    finally:
        connection.close()

    lease_database = next(item for item in manifest["databases"] if item["name"] == "worker_leases.db")
    restored_lease_database = restore_target / Path(lease_database["restore_path"])
    connection = sqlite3.connect(restored_lease_database)
    try:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='worker_leases'"
        ).fetchone() == ("worker_leases",)
    finally:
        connection.close()
