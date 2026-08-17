from __future__ import annotations

import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import config.settings as settings
from backup.manager import BackupManager
from decision.store import DecisionStore
from engine.decision_worker import (
    SHANGHAI,
    DecisionWorker,
    SQLiteWorkerLease,
    _WorkerBackupBarrier,
)
from engine.events.outbox import SQLiteOutbox


def _worker(tmp_path: Path) -> DecisionWorker:
    return DecisionWorker(
        SQLiteWorkerLease(tmp_path / "worker.db"),
        SQLiteOutbox(tmp_path / "events.db"),
        poll_interval_seconds=60,
    )


def test_backup_barrier_drains_active_operations_and_blocks_new_ones(tmp_path: Path) -> None:
    worker = _worker(tmp_path)
    barrier = _WorkerBackupBarrier(worker)
    active_started = threading.Event()
    release_active = threading.Event()
    new_started = threading.Event()

    def active_operation() -> None:
        with worker._worker_operation():
            active_started.set()
            assert release_active.wait(timeout=2)

    def new_operation() -> None:
        with worker._worker_operation():
            new_started.set()

    active_thread = threading.Thread(target=active_operation)
    active_thread.start()
    assert active_started.wait(timeout=2)

    try:
        barrier.pause()
        blocked_thread = threading.Thread(target=new_operation)
        blocked_thread.start()

        assert not new_started.wait(timeout=0.05)
        release_active.set()
        active_thread.join(timeout=2)
        barrier.wait_for_safe_point()
        assert not new_started.is_set()

        barrier.resume()
        blocked_thread.join(timeout=2)
        assert new_started.is_set()
    finally:
        release_active.set()
        barrier.resume() if barrier.paused else None
        active_thread.join(timeout=2)
        if "blocked_thread" in locals():
            blocked_thread.join(timeout=2)
        worker.close()


def test_worker_daily_backup_releases_barrier_when_journal_setup_fails(tmp_path: Path, monkeypatch) -> None:
    database_dir = tmp_path / "db"
    database_dir.mkdir()
    source = database_dir / "decisions.db"
    connection = sqlite3.connect(source)
    connection.execute("CREATE TABLE marker(value TEXT)")
    connection.commit()
    connection.close()

    monkeypatch.setattr(settings, "DB_DIR", database_dir)
    monkeypatch.setenv("DECISION_BACKUP_DIR", str(tmp_path / "backup"))
    monkeypatch.delenv("DECISION_ARTIFACT_DIRS", raising=False)

    worker = _worker(tmp_path)

    def fail_before_journal_mode(_databases):
        raise RuntimeError("journal setup failed")

    monkeypatch.setattr(worker, "_backup_journal_mode", fail_before_journal_mode)
    try:
        with pytest.raises(RuntimeError, match="journal setup failed"):
            worker._run_daily_backup(scheduled_for=datetime.now(timezone.utc))
        assert worker._backup_paused is False
        assert worker._backup_owner is None
        assert worker._backup_depth == 0
        assert worker._active_operations == 0
    finally:
        worker.close()


def test_backup_barrier_is_reentrant_until_the_outer_backup_finishes(tmp_path: Path) -> None:
    worker = _worker(tmp_path)
    barrier = _WorkerBackupBarrier(worker)
    try:
        barrier.pause()
        barrier.pause()
        assert worker._backup_paused is True
        assert worker._backup_depth == 2

        barrier.resume()
        assert worker._backup_paused is True
        assert worker._backup_depth == 1

        barrier.resume()
        assert worker._backup_paused is False
        assert worker._backup_owner is None
        assert worker._backup_depth == 0
    finally:
        while barrier.paused:
            barrier.resume()
        worker.close()


def test_backup_longer_than_lease_ttl_keeps_renewal_and_heartbeat_alive(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_dir = tmp_path / "db"
    backup_root = tmp_path / "backups"
    monkeypatch.setattr(settings, "DB_DIR", database_dir)
    monkeypatch.setenv("DECISION_BACKUP_DIR", str(backup_root))
    monkeypatch.delenv("DECISION_ARTIFACT_DIRS", raising=False)

    DecisionStore(database_dir / "decisions.db")
    lease = SQLiteWorkerLease(database_dir / "worker_leases.db")
    worker = DecisionWorker(
        lease,
        SQLiteOutbox(database_dir / "events.db"),
        lease_ttl_seconds=0.15,
        poll_interval_seconds=60,
    )
    original_backup = BackupManager._sqlite_backup

    def slow_backup(source: Path, destination: Path):
        time.sleep(0.2)
        return original_backup(source, destination)

    monkeypatch.setattr(BackupManager, "_sqlite_backup", staticmethod(slow_backup))
    try:
        assert worker.acquire() is True
        original_token = worker.fence_token
        result = worker._run_daily_backup(
            scheduled_for=datetime(2026, 8, 15, 2, tzinfo=timezone.utc),
        )

        current = lease.current()
        assert result["status"] == "created"
        assert current is not None
        assert current.owner_id == worker.owner_id
        assert current.fence_token == original_token
        assert current.expires_at > datetime.now(timezone.utc)
        assert lease.readiness(max_age_seconds=1)["lease_matches"] is True
    finally:
        worker.close()


def test_worker_backup_aborts_when_fence_is_lost_after_copy(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_dir = tmp_path / "db"
    backup_root = tmp_path / "backups"
    monkeypatch.setattr(settings, "DB_DIR", database_dir)
    monkeypatch.setenv("DECISION_BACKUP_DIR", str(backup_root))
    monkeypatch.delenv("DECISION_ARTIFACT_DIRS", raising=False)

    DecisionStore(database_dir / "decisions.db")
    lease = SQLiteWorkerLease(database_dir / "worker_leases.db")
    worker = DecisionWorker(
        lease,
        SQLiteOutbox(database_dir / "events.db"),
        poll_interval_seconds=60,
    )
    original_backup = BackupManager._sqlite_backup
    stolen = False

    def copy_then_steal_fence(source: Path, destination: Path):
        nonlocal stolen
        result = original_backup(source, destination)
        if not stolen:
            stolen = True
            replacement_expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
            connection = sqlite3.connect(lease.database)
            try:
                connection.execute(
                    """
                    UPDATE worker_leases
                    SET owner_id=?, fence_token=?, expires_at=?, updated_at=?
                    WHERE lease_name=?
                    """,
                    (
                        "replacement-worker",
                        "replacement-fence",
                        replacement_expiry.isoformat(),
                        datetime.now(timezone.utc).isoformat(),
                        lease.lease_name,
                    ),
                )
                connection.commit()
            finally:
                connection.close()
        return result

    monkeypatch.setattr(BackupManager, "_sqlite_backup", staticmethod(copy_then_steal_fence))
    try:
        assert worker.acquire(now=datetime.now(timezone.utc)) is True
        with pytest.raises(RuntimeError, match="fence token is no longer valid"):
            worker._run_daily_backup(
                scheduled_for=datetime(2026, 8, 15, 2, tzinfo=timezone.utc),
            )
        assert worker.owns_lease is False
        assert worker._backup_paused is False
        assert worker._active_operations == 0
        assert not (backup_root / "2026-08-15" / "manifest.json").exists()
    finally:
        worker.close()


def test_monthly_recovery_drill_is_scheduled_only_on_first_day(tmp_path: Path) -> None:
    calls: list[datetime] = []
    worker = DecisionWorker(
        SQLiteWorkerLease(tmp_path / "worker.db"),
        SQLiteOutbox(tmp_path / "events.db"),
        monthly_recovery_drill=lambda *, scheduled_for: calls.append(scheduled_for),
        poll_interval_seconds=60,
    )
    local = datetime(2026, 9, 1, 3, 0, tzinfo=SHANGHAI)
    current = local.astimezone(timezone.utc)
    try:
        assert worker.acquire(now=current) is True
        result = worker.tick(now=current)
        assert result.recovery_drill_completed is True
        assert calls == [local]
    finally:
        worker.close()
