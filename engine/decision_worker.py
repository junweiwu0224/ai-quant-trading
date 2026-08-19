"""Single-owner runtime for scheduled decision work and durable delivery."""

from __future__ import annotations

import os
import socket
import sqlite3
import threading

import uuid
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler

from loguru import logger

from engine.events.outbox import SQLiteOutbox
from engine.notifications.dispatcher import NotificationDispatcher


SHANGHAI = ZoneInfo("Asia/Shanghai")
PREPARATION_SLOTS: tuple[tuple[str, int, int], ...] = (
    ("morning", 8, 30),
    ("midday", 12, 0),
)
DELIVERY_SLOTS: tuple[tuple[str, int, int], ...] = (
    ("morning", 9, 0),
    ("midday", 12, 30),
)
DAILY_BACKUP_SLOTS: tuple[tuple[str, int, int], ...] = (("daily_backup", 2, 0),)
MONTHLY_RECOVERY_DRILL_SLOTS: tuple[tuple[str, int, int], ...] = (("monthly_recovery_drill", 3, 0),)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def feature_enabled(name: str, *, default: bool = False) -> bool:
    """Return a conservative boolean environment switch."""

    raw = os.getenv(name, "")
    if not raw:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class WorkerCallbacks:
    """Injectable runtime hooks; defaults deliberately have no external effects."""

    is_trading_day: Callable[[datetime], bool] = lambda _when: True
    prepare: Callable[..., Any] = lambda **_kwargs: None
    send_prepared: Callable[..., Any] = lambda **_kwargs: None
    poll_completed_bars: Callable[..., Any] = lambda **_kwargs: None
    process_commands: Callable[..., Any] = lambda **_kwargs: ()
    # A context is (stable key, local wall clock).  The optional hook lets a
    # runtime schedule markets in their own time zones while old callers keep
    # the single Shanghai schedule through ``is_trading_day``.
    schedule_contexts: Callable[[datetime], Iterable[tuple[str, datetime]]] | None = None
    prepare_for_context: Callable[..., Any] | None = None
    send_for_context: Callable[..., Any] | None = None
    poll_for_context: Callable[..., Any] | None = None
    daily_backup: Callable[..., Any] | None = None
    monthly_recovery_drill: Callable[..., Any] | None = None


@dataclass(frozen=True)
class Lease:
    name: str
    owner_id: str
    expires_at: datetime
    fence_token: str = ""


class SQLiteWorkerLease:
    """Database-backed lease shared by all local worker processes.

    A lease is only valid while the stored owner and expiry still match.  The
    UPSERT intentionally lets a replacement process recover a stale lease,
    but never take a live one.
    """

    def __init__(self, database: str | Path, *, lease_name: str = "decision-worker") -> None:
        self.database = Path(database)
        self.lease_name = lease_name
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.database), timeout=5.0, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA busy_timeout=5000")
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS worker_leases (
                lease_name TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                fence_token TEXT NOT NULL DEFAULT ''
            )
            """
        )
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(worker_leases)").fetchall()}
        if "fence_token" not in columns:
            self.connection.execute("ALTER TABLE worker_leases ADD COLUMN fence_token TEXT NOT NULL DEFAULT ''")
            self.connection.commit()
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS worker_heartbeats (
                worker_name TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                fence_token TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                last_heartbeat TEXT NOT NULL,
                last_success TEXT,
                last_error TEXT,
                draining INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS worker_slot_completions (
                slot_key TEXT PRIMARY KEY,
                completed_at TEXT NOT NULL
            )
            """
        )
        heartbeat_columns = {row[1] for row in self.connection.execute("PRAGMA table_info(worker_heartbeats)").fetchall()}
        if "fence_token" not in heartbeat_columns:
            self.connection.execute("ALTER TABLE worker_heartbeats ADD COLUMN fence_token TEXT NOT NULL DEFAULT ''")
        self.connection.commit()
        self._lock = threading.RLock()

    def acquire(self, owner_id: str, *, ttl_seconds: float = 30.0, now: datetime | None = None) -> Lease | None:
        if not owner_id:
            raise ValueError("owner_id is required")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        current = now or utc_now()
        expiry = current + timedelta(seconds=ttl_seconds)
        fence_token = uuid.uuid4().hex
        with self._lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                row = self.connection.execute(
                    "SELECT owner_id, expires_at FROM worker_leases WHERE lease_name=?", (self.lease_name,)
                ).fetchone()
                if row is not None and row[0] != owner_id and _parse_iso(row[1]) > current:
                    self.connection.rollback()
                    return None
                self.connection.execute(
                    """
                    INSERT INTO worker_leases(lease_name, owner_id, expires_at, updated_at, fence_token)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(lease_name) DO UPDATE SET
                        owner_id=excluded.owner_id,
                        expires_at=excluded.expires_at,
                        updated_at=excluded.updated_at,
                        fence_token=excluded.fence_token
                    """,
                    (self.lease_name, owner_id, _iso(expiry), _iso(current), fence_token),
                )
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                raise
        return Lease(name=self.lease_name, owner_id=owner_id, expires_at=expiry, fence_token=fence_token)

    def renew(
        self,
        owner_id: str,
        *,
        fence_token: str = "",
        ttl_seconds: float = 30.0,
        now: datetime | None = None,
    ) -> Lease | None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        current = now or utc_now()
        expiry = current + timedelta(seconds=ttl_seconds)
        with self._lock:
            updated = self.connection.execute(
                """
                UPDATE worker_leases
                SET expires_at=?, updated_at=?
                WHERE lease_name=? AND owner_id=? AND expires_at>? AND (fence_token=? OR ?='')
                """,
                (_iso(expiry), _iso(current), self.lease_name, owner_id, _iso(current), fence_token, fence_token),
            ).rowcount
            self.connection.commit()
        if updated != 1:
            return None
        return Lease(name=self.lease_name, owner_id=owner_id, expires_at=expiry, fence_token=fence_token)

    def release(self, owner_id: str, *, fence_token: str = "") -> bool:
        with self._lock:
            deleted = self.connection.execute(
                "DELETE FROM worker_leases WHERE lease_name=? AND owner_id=? AND (fence_token=? OR ?='')",
                (self.lease_name, owner_id, fence_token, fence_token),
            ).rowcount
            self.connection.commit()
        return deleted == 1

    def current(self) -> Lease | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT owner_id, expires_at, fence_token FROM worker_leases WHERE lease_name=?", (self.lease_name,)
            ).fetchone()
        if row is None:
            return None
        return Lease(name=self.lease_name, owner_id=row[0], expires_at=_parse_iso(row[1]), fence_token=str(row[2] or ""))

    def close(self) -> None:
        with self._lock:
            self.connection.close()

    def heartbeat(
        self,
        owner_id: str,
        *,
        fence_token: str = "",
        status: str = "ready",
        last_success: datetime | None = None,
        error: str = "",
        draining: bool = False,
        now: datetime | None = None,
    ) -> bool:
        current_dt = now or utc_now()
        current = _iso(current_dt)
        with self._lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                lease = self.connection.execute(
                    "SELECT owner_id, expires_at, fence_token FROM worker_leases WHERE lease_name=?",
                    (self.lease_name,),
                ).fetchone()
                if (
                    lease is None
                    or lease["owner_id"] != owner_id
                    or _parse_iso(lease["expires_at"]) <= current_dt
                    or (lease["fence_token"] and lease["fence_token"] != fence_token)
                ):
                    self.connection.rollback()
                    return False
                self.connection.execute(
                    """
                    INSERT INTO worker_heartbeats(
                        worker_name, owner_id, fence_token, status, last_heartbeat, last_success,
                        last_error, draining
                    ) VALUES(?,?,?,?,?,?,?,?)
                    ON CONFLICT(worker_name) DO UPDATE SET
                        owner_id=excluded.owner_id,
                        fence_token=excluded.fence_token,
                        status=excluded.status,
                        last_heartbeat=excluded.last_heartbeat,
                        last_success=COALESCE(excluded.last_success, worker_heartbeats.last_success),
                        last_error=excluded.last_error,
                        draining=excluded.draining
                    """,
                    (
                        self.lease_name,
                        owner_id,
                        fence_token,
                        status,
                        current,
                        _iso(last_success) if last_success else None,
                        str(error or "")[:1000],
                        int(bool(draining)),
                    ),
                )
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                raise
        return True

    def readiness(self, *, max_age_seconds: float = 90.0, now: datetime | None = None) -> dict[str, Any]:
        current = now or utc_now()
        with self._lock:
            row = self.connection.execute(
                """
                SELECT h.*, l.owner_id AS lease_owner_id, l.expires_at AS lease_expires_at,
                       l.fence_token AS lease_fence_token
                FROM worker_heartbeats h
                LEFT JOIN worker_leases l ON l.lease_name=h.worker_name
                WHERE h.worker_name=?
                """,
                (self.lease_name,),
            ).fetchone()
        if row is None:
            return {"ready": False, "status": "missing_heartbeat", "worker_name": self.lease_name}
        heartbeat_at = _parse_iso(row["last_heartbeat"])
        age = max(0.0, (current - heartbeat_at).total_seconds())
        lease_matches = (
            row["lease_owner_id"] == row["owner_id"]
            and row["lease_fence_token"] == row["fence_token"]
            and row["lease_expires_at"] is not None
            and _parse_iso(row["lease_expires_at"]) > current
        )
        ready = row["status"] in {"ready", "running"} and not bool(row["draining"]) and age <= max_age_seconds and lease_matches
        return {
            "ready": ready,
            "status": row["status"],
            "worker_name": self.lease_name,
            "owner_id": row["owner_id"],
            "fence_token": row["fence_token"],
            "last_heartbeat": row["last_heartbeat"],
            "last_success": row["last_success"],
            "last_error": row["last_error"] or "",
            "age_seconds": age,
            "draining": bool(row["draining"]),
            "lease_owner_id": row["lease_owner_id"],
            "lease_expires_at": row["lease_expires_at"],
            "lease_matches": lease_matches,
        }

    def slot_completed(self, slot_key: str) -> bool:
        """Return whether a scheduled slot already completed durably."""

        clean_key = str(slot_key or "").strip()
        if not clean_key:
            return False
        with self._lock:
            row = self.connection.execute(
                "SELECT 1 FROM worker_slot_completions WHERE slot_key=?",
                (clean_key,),
            ).fetchone()
        return row is not None

    def mark_slot_completed(self, slot_key: str, *, now: datetime | None = None) -> bool:
        """Record a successful slot callback idempotently."""

        clean_key = str(slot_key or "").strip()
        if not clean_key:
            raise ValueError("worker slot key is required")
        with self._lock:
            inserted = self.connection.execute(
                "INSERT OR IGNORE INTO worker_slot_completions(slot_key, completed_at) VALUES(?,?)",
                (clean_key, _iso(now or utc_now())),
            ).rowcount
            self.connection.commit()
        return inserted == 1


@dataclass(frozen=True)
class WorkerTick:
    prepared_slots: tuple[str, ...] = ()
    sent_slots: tuple[str, ...] = ()
    dispatched: int = 0
    bars_polled: bool = False
    backup_completed: bool = False
    recovery_drill_completed: bool = False
    commands_processed: int = 0
    skipped: bool = False


class _WorkerBackupBarrier:
    """Coordinate a backup with every Worker-owned write operation.

    The backup manager calls ``pause``/``wait_for_safe_point``/``resume``
    itself.  The Worker also acquires the same barrier around the journal-mode
    transition so SQLite sidecars cannot be changed before the barrier is
    active.  Pause ownership is re-entrant because those two layers are
    intentionally nested.
    """

    def __init__(self, worker: "DecisionWorker") -> None:
        self.worker = worker
        self.paused = False
        self._acquisitions = 0

    def pause(self) -> None:
        owner = threading.get_ident()
        with self.worker._operation_condition:
            while self.worker._backup_paused and self.worker._backup_owner != owner:
                self.worker._operation_condition.wait()
            if not self.worker._backup_paused:
                self.worker._backup_owner = owner
                self.worker._backup_depth = 0
                self.worker._backup_paused = True
            self.worker._backup_depth += 1
            self._acquisitions += 1
            self.paused = True

    def wait_for_safe_point(self) -> None:
        with self.worker._operation_condition:
            while self.worker._active_operations:
                self.worker._operation_condition.wait()

    def resume(self) -> None:
        with self.worker._operation_condition:
            if self._acquisitions <= 0:
                raise RuntimeError("worker backup barrier is not paused")
            self._acquisitions -= 1
            self.worker._backup_depth -= 1
            if self.worker._backup_depth <= 0:
                self.worker._backup_depth = 0
                self.worker._backup_owner = None
                self.worker._backup_paused = False
                self.worker._operation_condition.notify_all()
            self.paused = self._acquisitions > 0


@dataclass
class DecisionWorker:
    """Own scheduling, decision callbacks and outbox delivery for one process."""

    lease: SQLiteWorkerLease
    outbox: SQLiteOutbox
    callbacks: WorkerCallbacks = field(default_factory=WorkerCallbacks)
    dispatchers: tuple[NotificationDispatcher, ...] = ()
    owner_id: str = field(default_factory=lambda: f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex}")
    lease_ttl_seconds: float = 30.0
    poll_interval_seconds: float = 5.0
    bar_poll_interval_seconds: float = 30.0
    misfire_grace_seconds: float = 2 * 60 * 60
    daily_backup: Callable[..., Any] | None = None
    monthly_recovery_drill: Callable[..., Any] | None = None
    _scheduler: BackgroundScheduler = field(init=False, repr=False)
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _last_bar_poll: datetime | None = field(default=None, init=False, repr=False)
    _owns_lease: bool = field(default=False, init=False, repr=False)
    _fence_token: str = field(default="", init=False, repr=False)
    _fence_check_now: datetime | None = field(default=None, init=False, repr=False)
    _backup_paused: bool = field(default=False, init=False, repr=False)
    _backup_owner: int | None = field(default=None, init=False, repr=False)
    _backup_depth: int = field(default=0, init=False, repr=False)
    _operation_condition: threading.Condition = field(
        default_factory=lambda: threading.Condition(threading.RLock()),
        init=False,
        repr=False,
    )
    _active_operations: int = field(default=0, init=False, repr=False)
    _processed_slots: set[str] = field(default_factory=set, init=False, repr=False)
    _renewal_stop: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _renewal_thread: threading.Thread | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.lease_ttl_seconds <= 0:
            raise ValueError("lease_ttl_seconds must be positive")
        if self.poll_interval_seconds <= 0 or self.bar_poll_interval_seconds <= 0:
            raise ValueError("poll intervals must be positive")
        self._scheduler = BackgroundScheduler(timezone=SHANGHAI)
        if self.daily_backup is None:
            self.daily_backup = self.callbacks.daily_backup
        if self.monthly_recovery_drill is None:
            self.monthly_recovery_drill = self.callbacks.monthly_recovery_drill

    @contextmanager
    def _worker_operation(self) -> Iterator[None]:
        """Block new Worker-owned writes while a coordinated backup is active."""

        owner = threading.get_ident()
        with self._operation_condition:
            while self._backup_paused and self._backup_owner != owner:
                self._operation_condition.wait()
            self._active_operations += 1
        try:
            yield
        finally:
            with self._operation_condition:
                self._active_operations -= 1
                if self._active_operations < 0:
                    self._active_operations = 0
                    raise RuntimeError("worker operation counter underflow")
                self._operation_condition.notify_all()

    def _heartbeat(
        self,
        *,
        status: str,
        last_success: datetime | None = None,
        error: str = "",
        draining: bool = False,
        now: datetime | None = None,
    ) -> bool:
        # Lease renewal and health writes remain live while the backup captures
        # the lease database. The backup manager uses a controlled Worker path
        # for this file so a long backup cannot fence out its owner.
        return self.lease.heartbeat(
            self.owner_id,
            fence_token=self._fence_token,
            status=status,
            last_success=last_success,
            error=error,
            draining=draining,
            now=now,
        )

    @classmethod
    def from_environment(cls) -> "DecisionWorker":
        """Build the sole scheduling owner and connect its decision runtime."""

        from config.settings import DB_DIR
        from decision.delivery import DecisionDeliveryService, DecisionOutboxDispatcher
        from decision.runtime import DecisionRuntime

        outbox = SQLiteOutbox(DB_DIR / "events.db")
        runtime = DecisionRuntime.from_environment()
        runtime.outbox = outbox
        worker = cls(
            lease=SQLiteWorkerLease(DB_DIR / "worker_leases.db"),
            outbox=outbox,
            callbacks=runtime.worker_callbacks(),
        )
        runtime.bind_worker(
            worker.owner_id,
            worker._assert_fence,
            lambda: worker.fence_token,
        )
        decision_delivery = DecisionDeliveryService(
            runtime.store,
            outbox=outbox,
            owner_id=worker.owner_id,
            worker_owned=True,
            eligibility_check=runtime.eligibility,
            fence_token_provider=lambda: worker.fence_token,
            fence_check=worker._assert_fence,
        )
        # Only the decision report consumer is registered here.  Legacy alert
        # and daily-brief consumers belong to the retired Dashboard scheduler;
        # registering them beside the new worker would bypass the decision
        # external-delivery gate and create two owners for unrelated events.
        worker.dispatchers = (DecisionOutboxDispatcher(outbox, decision_delivery),)
        worker.daily_backup = worker._run_daily_backup
        worker.monthly_recovery_drill = worker._run_monthly_recovery_drill
        return worker

    def _run_daily_backup(self, *, scheduled_for: datetime) -> dict[str, Any]:
        """Create one durable local backup at the worker's daily safe point."""

        from backup.manager import BackupManager
        from config import settings

        db_dir = Path(settings.DB_DIR)
        backup_root = Path(os.getenv("DECISION_BACKUP_DIR", str(db_dir.parent / "backups" / "daily")))
        day = scheduled_for.astimezone(SHANGHAI).date().isoformat()
        output = backup_root / day
        configured = [
            Path(raw).expanduser()
            for raw in os.getenv("DECISION_BACKUP_DATABASES", "").split(os.pathsep)
            if raw.strip()
        ]
        databases_by_key: dict[str, Path] = {}
        lease_database = Path(self.lease.database).resolve()

        def add_database(path: Path) -> None:
            resolved = path.resolve()
            if path.is_file():
                databases_by_key[str(resolved)] = path

        for path in sorted(db_dir.glob("*.db")):
            add_database(path)
        # Lease state is part of the recovery set even when a deployment keeps
        # the lease database outside the normal data directory.
        add_database(lease_database)
        # The default account database lives beside the decision/data stores;
        # a custom external account path must be explicitly configured so test
        # and isolated workspaces never read the developer's real database.
        account_path = Path(settings.ACCOUNT_DB_PATH)
        if os.getenv("ACCOUNT_DB_PATH") or account_path.parent.resolve() == db_dir.resolve():
            add_database(account_path)
        default_db_dir = Path(settings.PROJECT_ROOT) / "data" / "db"
        paper_path = Path(settings.PROJECT_ROOT) / "data" / "paper_trading.db"
        if db_dir.resolve() == default_db_dir.resolve() and paper_path.is_file():
            add_database(paper_path)
        for path in configured:
            add_database(path)
        databases = tuple(databases_by_key.values())
        artifact_dirs = tuple(
            Path(raw).expanduser()
            for raw in os.getenv("DECISION_ARTIFACT_DIRS", "").split(os.pathsep)
            if raw.strip()
        )
        if not databases:
            return {"status": "skipped", "reason": "no_local_databases", "output_dir": str(output), "date": day}
        barrier = _WorkerBackupBarrier(self)
        fence_check: Callable[[], None] | None = None
        if self._owns_lease:
            fence_check = lambda: self._assert_fence(now=utc_now())
            fence_check()

        # Acquire the in-process barrier before touching source databases.
        # BackupManager re-enters it and also takes SQLite write locks so
        # control-plane writers which do not share this condition are fenced.
        barrier.pause()
        try:
            barrier.wait_for_safe_point()
            with self._backup_journal_mode(databases):
                result = BackupManager(
                    barrier,
                    fence_check=fence_check,
                    _live_database_paths=(lease_database,),
                ).backup(
                    output,
                    databases,
                    artifact_dirs,
                    metadata={
                        "trigger": "decision_worker_daily",
                        "worker_owner_id": self.owner_id,
                        "scheduled_for": _iso(scheduled_for),
                        "artifact_dirs_configured": [str(path) for path in artifact_dirs],
                        "database_paths_discovered": [str(path) for path in databases],
                    },
                )
        finally:
            barrier.resume()
        if fence_check is not None:
            fence_check()
        return {"status": "created", "output_dir": str(output), "date": day, "manifest": result}

    @contextmanager
    def _backup_journal_mode(self, databases: tuple[Path, ...]) -> Iterator[None]:
        """Keep journal configuration stable while SQLite online backup runs.

        Online backup includes committed WAL content and produces a standalone
        destination database.  Changing source journal modes here would add a
        cross-file write that Dashboard connections cannot coordinate with.
        """

        del databases
        yield

    def _run_monthly_recovery_drill(self, *, scheduled_for: datetime) -> dict[str, Any]:
        """Verify, restore, and replay the latest daily backup using local files."""

        from backup.manager import BackupManager
        from config import settings

        db_dir = Path(settings.DB_DIR)
        backup_root = Path(os.getenv("DECISION_BACKUP_DIR", str(db_dir.parent / "backups" / "daily")))
        recovery_root = Path(
            os.getenv("DECISION_RECOVERY_DRILL_DIR")
            or os.getenv("DECISION_RECOVERY_DIR")
            or str(backup_root.parent / "monthly-recovery")
        )
        replay_decision_id = (
            os.getenv("DECISION_RECOVERY_REPLAY_DECISION_ID")
            or os.getenv("DECISION_RECOVERY_DRILL_DECISION_ID")
            or ""
        ).strip() or None
        fence_check: Callable[[], None] | None = None
        if self._owns_lease:
            fence_check = lambda: self._assert_fence(now=utc_now())
            fence_check()
        result = BackupManager(fence_check=fence_check).run_recovery_drill(
            backup_root,
            recovery_root,
            replay_decision_id=replay_decision_id,
            scheduled_for=scheduled_for,
        )
        if fence_check is not None:
            fence_check()
        return result

    @property
    def draining(self) -> bool:
        return self._stop_event.is_set()

    @property
    def owns_lease(self) -> bool:
        return self._owns_lease

    @property
    def fence_token(self) -> str:
        """Current lease fence exposed only for Worker-owned adapters."""

        return self._fence_token

    def acquire(self, *, now: datetime | None = None) -> bool:
        with self._worker_operation():
            acquired = self.lease.acquire(self.owner_id, ttl_seconds=self.lease_ttl_seconds, now=now)
            self._owns_lease = acquired is not None
            self._fence_token = acquired.fence_token if acquired is not None else ""
            if self._owns_lease:
                if not self.lease.heartbeat(self.owner_id, fence_token=self._fence_token, status="ready", now=now):
                    self._owns_lease = False
                    self._fence_token = ""
                elif now is None:
                    self._start_lease_renewal()
        return self._owns_lease

    def _start_lease_renewal(self) -> None:
        """Keep ownership alive while a synchronous callback runs.

        Decision callbacks may perform network or historical-data work for much
        longer than the normal lease TTL.  A scheduler tick cannot renew from
        inside such a callback, so a small daemon thread renews and heartbeats
        the same fenced lease.  Explicit-clock test ticks intentionally skip
        this thread so their synthetic timestamps remain deterministic.
        """

        if self._renewal_thread is not None and self._renewal_thread.is_alive():
            return
        self._renewal_stop.clear()
        interval = max(0.01, self.lease_ttl_seconds / 3.0)

        def renew_loop() -> None:
            while not self._renewal_stop.wait(interval):
                if not self._owns_lease:
                    return
                try:
                    if not self.renew():
                        self._owns_lease = False
                        self._fence_token = ""
                        self._stop_event.set()
                        return
                    current = utc_now()
                    if not self._heartbeat(
                        status="running",
                        now=current,
                    ):
                        self._owns_lease = False
                        self._fence_token = ""
                        self._stop_event.set()
                        return
                except Exception:
                    self._owns_lease = False
                    self._fence_token = ""
                    self._stop_event.set()
                    logger.exception("Decision worker lease renewal failed")
                    return

        self._renewal_thread = threading.Thread(
            target=renew_loop,
            name="decision-worker-lease-renewal",
            daemon=True,
        )
        self._renewal_thread.start()

    def renew(self, *, now: datetime | None = None) -> bool:
        # Lease maintenance must continue while the decision-write barrier is
        # paused so a long backup cannot expire the Worker ownership lease.
        if not self._owns_lease:
            return False
        renewed = self.lease.renew(
            self.owner_id,
            fence_token=self._fence_token,
            ttl_seconds=self.lease_ttl_seconds,
            now=now,
        )
        self._owns_lease = renewed is not None
        if renewed is None:
            self._fence_token = ""
        return self._owns_lease

    def _slots_due(
        self,
        slots: Iterable[tuple[str, int, int]],
        now: datetime,
        *,
        local: datetime | None = None,
        context_key: str = "default",
    ) -> tuple[str, ...]:
        local = local or now.astimezone(SHANGHAI)
        due: list[str] = []
        for name, hour, minute in slots:
            scheduled = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
            key = "%s:%s:%s:%s" % (context_key, scheduled.date().isoformat(), name, hour * 60 + minute)
            age = (local - scheduled).total_seconds()
            if (
                0 <= age <= self.misfire_grace_seconds
                and key not in self._processed_slots
                and not self.lease.slot_completed(key)
            ):
                due.append(name)
        # Keep the in-memory guard bounded during a long-running process.
        if len(self._processed_slots) > 128:
            self._processed_slots = set(sorted(self._processed_slots)[-64:])
        return tuple(due)

    def _remember_slot(
        self,
        slot: str,
        slots: Iterable[tuple[str, int, int]],
        now: datetime,
        *,
        local: datetime | None = None,
        context_key: str = "default",
    ) -> None:
        local = local or now.astimezone(SHANGHAI)
        for name, hour, minute in slots:
            if name == slot:
                key = "%s:%s:%s:%s" % (context_key, local.date().isoformat(), name, hour * 60 + minute)
                self._processed_slots.add(key)
                self.lease.mark_slot_completed(key, now=now)
                return

    def _assert_fence(self, *, now: datetime | None = None) -> None:
        """Stop before any side effect once another worker has fenced us out."""

        if not self._owns_lease or not self._fence_token:
            raise RuntimeError("decision worker lease is not owned")
        current = self.lease.current()
        check_now = now or self._fence_check_now or utc_now()
        if (
            current is None
            or current.owner_id != self.owner_id
            or current.fence_token != self._fence_token
            or current.expires_at <= check_now
        ):
            self._owns_lease = False
            self._fence_token = ""
            raise RuntimeError("decision worker lease fence token is no longer valid")

    def _dispatch_outbox(self, *, now: datetime) -> int:
        with self._worker_operation():
            self._assert_fence()
            self.outbox.reclaim_stale(older_than_seconds=int(max(1, self.lease_ttl_seconds * 2)), now=now)
            dispatched = 0
            for dispatcher in self.dispatchers:
                self._assert_fence()
                dispatched += len(dispatcher.dispatch(limit=50, now=now))
            self._assert_fence()
            return dispatched

    def _process_commands(self, *, now: datetime) -> int:
        with self._worker_operation():
            self._assert_fence()
            processed = self.callbacks.process_commands(
                owner_id=self.owner_id,
                limit=20,
                now=now,
                fence_check=self._assert_fence,
            )
            self._assert_fence()
            if isinstance(processed, int):
                return max(0, processed)
            try:
                return len(processed)
            except TypeError:
                return 0

    def tick(self, *, now: datetime | None = None) -> WorkerTick:
        """Run one safe unit of work; callers may use this for deterministic tests."""

        current = now or utc_now()
        self._fence_check_now = current
        if not self.renew(now=current):
            self._heartbeat(status="lost_lease", draining=True, now=current)
            self._fence_check_now = None
            return WorkerTick(skipped=True)

        if not self._heartbeat(status="running", now=current):
            self._owns_lease = False
            self._fence_token = ""
            self._fence_check_now = None
            return WorkerTick(skipped=True)

        commands_processed = self._process_commands(now=current)

        contexts = (
            tuple(self.callbacks.schedule_contexts(current))
            if self.callbacks.schedule_contexts is not None
            else (("default", current.astimezone(SHANGHAI)),)
        )
        prepared_slots: list[str] = []
        sent_slots: list[str] = []
        for context_key, local in contexts:
            self._assert_fence()
            if not self.callbacks.is_trading_day(local):
                continue
            for slot in self._slots_due(PREPARATION_SLOTS, current, local=local, context_key=context_key):
                with self._worker_operation():
                    self._assert_fence()
                    if self.callbacks.prepare_for_context is not None:
                        self.callbacks.prepare_for_context(market=context_key, slot=slot, scheduled_for=local)
                    else:
                        self.callbacks.prepare(slot=slot, scheduled_for=local)
                    self._assert_fence()
                self._remember_slot(slot, PREPARATION_SLOTS, current, local=local, context_key=context_key)
                prepared_slots.append(slot if context_key == "default" else "%s:%s" % (context_key, slot))
            for slot in self._slots_due(DELIVERY_SLOTS, current, local=local, context_key=context_key):
                with self._worker_operation():
                    self._assert_fence()
                    if self.callbacks.send_for_context is not None:
                        self.callbacks.send_for_context(market=context_key, slot=slot, scheduled_for=local)
                    else:
                        self.callbacks.send_prepared(slot=slot, scheduled_for=local)
                    self._assert_fence()
                self._remember_slot(slot, DELIVERY_SLOTS, current, local=local, context_key=context_key)
                sent_slots.append(slot if context_key == "default" else "%s:%s" % (context_key, slot))

        bars_polled = False
        if self.callbacks.schedule_contexts is None:
            contexts_for_poll = (("default", current.astimezone(SHANGHAI)),)
        else:
            contexts_for_poll = contexts
        if self._last_bar_poll is None or (current - self._last_bar_poll).total_seconds() >= self.bar_poll_interval_seconds:
            for _context_key, local in contexts_for_poll:
                self._assert_fence()
                if self.callbacks.is_trading_day(local):
                    with self._worker_operation():
                        self._assert_fence()
                        if self.callbacks.poll_for_context is not None:
                            self.callbacks.poll_for_context(market=_context_key, observed_at=local)
                        else:
                            self.callbacks.poll_completed_bars(observed_at=local)
                        self._assert_fence()
                    bars_polled = True
            if bars_polled:
                self._last_bar_poll = current

        backup_completed = False
        backup_local = current.astimezone(SHANGHAI)
        for slot in self._slots_due(DAILY_BACKUP_SLOTS, current, local=backup_local, context_key="backup"):
            if self.daily_backup is not None:
                self._assert_fence()
                self.daily_backup(scheduled_for=backup_local)
                self._assert_fence()
                backup_completed = True
            self._remember_slot(slot, DAILY_BACKUP_SLOTS, current, local=backup_local, context_key="backup")

        recovery_drill_completed = False
        if backup_local.day == 1:
            for slot in self._slots_due(
                MONTHLY_RECOVERY_DRILL_SLOTS,
                current,
                local=backup_local,
                context_key="recovery",
            ):
                if self.monthly_recovery_drill is not None:
                    self._assert_fence()
                    self.monthly_recovery_drill(scheduled_for=backup_local)
                    self._assert_fence()
                    recovery_drill_completed = True
                self._remember_slot(
                    slot,
                    MONTHLY_RECOVERY_DRILL_SLOTS,
                    current,
                    local=backup_local,
                    context_key="recovery",
                )

        safe_point_now = current if now is not None else utc_now()
        if not self.renew(now=safe_point_now):
            self._heartbeat(status="lost_lease", draining=True, now=safe_point_now)
            self._fence_check_now = None
            return WorkerTick(skipped=True)
        dispatched = self._dispatch_outbox(now=safe_point_now)
        if not self._heartbeat(status="ready", last_success=safe_point_now, now=safe_point_now):
            self._owns_lease = False
            self._fence_token = ""
            self._fence_check_now = None
            return WorkerTick(skipped=True)
        self._fence_check_now = None
        return WorkerTick(
            prepared_slots=tuple(prepared_slots),
            sent_slots=tuple(sent_slots),
            dispatched=dispatched,
            bars_polled=bars_polled,
            backup_completed=backup_completed,
            recovery_drill_completed=recovery_drill_completed,
            commands_processed=commands_processed,
        )

    def _scheduled_tick(self) -> None:
        try:
            result = self.tick()
            if result.skipped:
                logger.warning("Decision worker lost its lease; entering drain mode")
                self.request_stop()
        except Exception as exc:  # Worker must remain available for retry/recovery.
            try:
                self._heartbeat(status="error", error=str(exc), now=utc_now())
            except Exception:
                logger.debug("unable to persist worker error heartbeat")
            logger.exception("Decision worker tick failed: {}", exc)

    def start(self) -> bool:
        if not self.acquire():
            logger.warning("Decision worker lease is held by another process; refusing to start")
            return False
        self._scheduler.add_job(
            self._scheduled_tick,
            trigger="interval",
            seconds=self.poll_interval_seconds,
            id="decision-worker-tick",
            max_instances=1,
            coalesce=True,
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info("Decision worker started with owner_id={}", self.owner_id)
        return True

    def request_stop(self) -> None:
        self._stop_event.set()
        if self._owns_lease:
            try:
                self._heartbeat(status="draining", draining=True)
            except Exception:
                logger.debug("unable to persist worker draining heartbeat")

    def run_forever(self) -> None:
        if not self.start():
            raise RuntimeError("decision worker lease is already held")
        try:
            self._scheduled_tick()
            while not self._stop_event.wait(timeout=min(self.poll_interval_seconds, 1.0)):
                pass
        finally:
            self.close()

    def readiness(self, *, max_age_seconds: float = 90.0, now: datetime | None = None) -> dict[str, Any]:
        state = self.lease.readiness(max_age_seconds=max_age_seconds, now=now)
        state["owns_lease"] = self.owns_lease
        state["draining"] = self.draining
        return state

    def close(self) -> None:
        self.request_stop()
        self._renewal_stop.set()
        if self._renewal_thread is not None and self._renewal_thread is not threading.current_thread():
            self._renewal_thread.join(timeout=max(1.0, self.lease_ttl_seconds))
        self._renewal_thread = None
        if self._scheduler.running:
            # Drain a running tick before releasing the lease or closing the
            # outbox.  Releasing first would let a replacement worker race a
            # still-running callback that no longer owns the fence.
            self._scheduler.shutdown(wait=True)
        if self._owns_lease:
            with self._worker_operation():
                self.lease.release(self.owner_id, fence_token=self._fence_token)
        self._owns_lease = False
        self._fence_token = ""
        self.outbox.close()
        self.lease.close()


__all__ = [
    "DAILY_BACKUP_SLOTS",
    "DELIVERY_SLOTS",
    "MONTHLY_RECOVERY_DRILL_SLOTS",
    "PREPARATION_SLOTS",
    "DecisionWorker",
    "Lease",
    "SQLiteWorkerLease",
    "WorkerCallbacks",
    "WorkerTick",
    "feature_enabled",
]
