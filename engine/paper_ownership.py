"""Exclusive ownership guard for the legacy Paper runtime.

The guard deliberately delegates lease storage and fencing to
``SQLiteWorkerLease``.  It only adds Paper's account-scoped lease identity and
runtime validity checks around that shared primitive.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from engine.decision_worker import Lease, SQLiteWorkerLease, utc_now


class PaperOwnership:
    """Account-scoped Paper owner backed by the shared SQLite worker lease."""

    def __init__(
        self,
        database: str | Path,
        *,
        account_id: str = "paper-default",
        owner_id: str | None = None,
        ttl_seconds: float = 30.0,
        clock: Callable[[], datetime] = utc_now,
        lease: SQLiteWorkerLease | None = None,
    ) -> None:
        clean_account = str(account_id or "").strip()
        if not clean_account:
            raise ValueError("account_id is required")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.account_id = clean_account
        self.owner_id = owner_id or f"paper-{uuid.uuid4().hex}"
        self.ttl_seconds = float(ttl_seconds)
        self._clock = clock
        self._lease = lease or SQLiteWorkerLease(
            database,
            lease_name=f"execution:paper:{self.account_id}",
        )
        self._owned: Lease | None = None
        self._renew_thread: threading.Thread | None = None
        self._renew_stop = threading.Event()

    @property
    def lease_name(self) -> str:
        return self._lease.lease_name

    @property
    def fence_token(self) -> str:
        return self._owned.fence_token if self._owned else ""

    def acquire(self, *, now: datetime | None = None) -> Lease | None:
        """Acquire this account's Paper lease, returning its fencing lease."""

        acquired = self._lease.acquire(
            self.owner_id,
            ttl_seconds=self.ttl_seconds,
            now=now or self._clock(),
        )
        self._owned = acquired
        return acquired

    def renew(self, *, now: datetime | None = None) -> Lease | None:
        """Renew only the exact owner and fence acquired by this guard."""

        if self._owned is None:
            return None
        renewed = self._lease.renew(
            self.owner_id,
            fence_token=self._owned.fence_token,
            ttl_seconds=self.ttl_seconds,
            now=now or self._clock(),
        )
        self._owned = renewed
        return renewed

    def valid(self, *, now: datetime | None = None) -> bool:
        """Check the durable owner, expiry and fence, not just local state."""

        if self._owned is None:
            return False
        current = now or self._clock()
        stored = self._lease.current()
        return bool(
            stored
            and stored.owner_id == self.owner_id
            and stored.fence_token == self._owned.fence_token
            and stored.expires_at > current
        )

    # ``is_valid`` is an explicit alias for callers that prefer predicate naming.
    is_valid = valid

    def release(self) -> bool:
        """Release this fence only; a reclaimed successor is left untouched."""

        self._stop_renewal()
        if self._owned is None:
            return False
        released = self._lease.release(self.owner_id, fence_token=self._owned.fence_token)
        self._owned = None
        return released

    def start_renewal(
        self,
        on_lost: Callable[[], None] | None = None,
        *,
        interval_seconds: float | None = None,
    ) -> None:
        """Keep a live Paper run fenced and stop it if another owner wins."""

        if self._owned is None:
            raise RuntimeError("Paper lease must be acquired before renewal")
        if self._renew_thread and self._renew_thread.is_alive():
            return
        interval = interval_seconds or max(0.1, self.ttl_seconds / 3)
        self._renew_stop.clear()

        def _renew() -> None:
            while not self._renew_stop.wait(interval):
                if self.renew() is None:
                    if on_lost:
                        on_lost()
                    return

        self._renew_thread = threading.Thread(target=_renew, daemon=True, name="paper-lease-renewal")
        self._renew_thread.start()

    def _stop_renewal(self) -> None:
        self._renew_stop.set()
        thread = self._renew_thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=2)
        self._renew_thread = None

    def close(self) -> None:
        self._stop_renewal()
        self._lease.close()

    def __enter__(self) -> "PaperOwnership":
        if self.acquire() is None:
            raise RuntimeError(f"Paper account is already owned: {self.account_id}")
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback) -> None:
        self.release()
        self.close()


__all__ = ["PaperOwnership"]
