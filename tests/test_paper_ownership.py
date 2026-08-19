from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dashboard.routers.paper_control import PaperManager, StartRequest
from engine.decision_worker import SQLiteWorkerLease
from engine.paper_ownership import PaperOwnership


UTC = timezone.utc


def test_account_scoped_lease_allows_one_paper_owner(tmp_path: Path) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    first = PaperOwnership(tmp_path / "worker.db", account_id="acct-a", owner_id="owner-a", clock=lambda: now)
    second = PaperOwnership(tmp_path / "worker.db", account_id="acct-a", owner_id="owner-b", clock=lambda: now)
    try:
        acquired = first.acquire()
        assert acquired is not None
        assert first.lease_name == "execution:paper:acct-a"
        assert second.acquire() is None
        assert first.valid()
    finally:
        first.release()
        second.close()
        first.close()


def test_expired_owner_can_be_reclaimed_and_old_fence_is_invalid(tmp_path: Path) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    clock = [now]
    first = PaperOwnership(
        tmp_path / "worker.db", account_id="acct-a", owner_id="owner-a", ttl_seconds=10, clock=lambda: clock[0]
    )
    second = PaperOwnership(
        tmp_path / "worker.db", account_id="acct-a", owner_id="owner-b", ttl_seconds=10, clock=lambda: clock[0]
    )
    try:
        old_lease = first.acquire()
        assert old_lease is not None
        clock[0] = now + timedelta(seconds=11)
        new_lease = second.acquire()
        assert new_lease is not None
        assert new_lease.fence_token != old_lease.fence_token
        assert not first.valid()
        assert first.renew() is None
        assert second.valid()
        assert not first._lease.release(first.owner_id, fence_token=old_lease.fence_token)
    finally:
        first.close()
        second.release()
        second.close()


def test_release_only_removes_current_fenced_owner(tmp_path: Path) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    lease = SQLiteWorkerLease(tmp_path / "worker.db", lease_name="execution:paper:acct-a")
    owner = PaperOwnership(
        tmp_path / "worker.db", account_id="acct-a", owner_id="owner-a", clock=lambda: now, lease=lease
    )
    try:
        assert owner.acquire() is not None
        assert owner.release()
        assert not owner.valid()
        assert lease.current() is None
    finally:
        owner.close()


def test_renewal_database_exception_calls_on_lost_without_thread_failure(tmp_path: Path) -> None:
    class BrokenLease:
        lease_name = "execution:paper:acct-a"

        def acquire(self, *args, **kwargs):
            return type("Lease", (), {"fence_token": "fence"})()

        def renew(self, *args, **kwargs):
            raise OSError("database unavailable")

        def close(self):
            return None

    owner = PaperOwnership(
        tmp_path / "unused.db",
        account_id="acct-a",
        lease=BrokenLease(),
        ttl_seconds=1,
    )
    lost = []
    try:
        assert owner.acquire() is not None
        owner.start_renewal(lambda: lost.append(None), interval_seconds=0.001)
        for _ in range(100):
            if lost:
                break
            import time
            time.sleep(0.005)
        assert lost == [None]
        assert owner.fence_token == ""
    finally:
        owner.close()


def test_start_request_rejects_path_traversal_account_ids() -> None:
    for account_id in (".", "..", "a/b", "a\\b"):
        with pytest.raises(ValueError):
            StartRequest(codes=["000001"], account_id=account_id)


def test_paper_manager_state_directory_is_account_scoped() -> None:
    first = PaperManager._state_dir("acct-a")
    second = PaperManager._state_dir("acct-b")
    assert first != second
    assert first.name == "acct-a"
    assert second.name == "acct-b"


def test_paper_manager_closes_ownership_when_acquire_raises() -> None:
    class BrokenOwnership:
        def __init__(self):
            self.closed = False

        def acquire(self):
            raise OSError("lease db unavailable")

        def close(self):
            self.closed = True

    ownership = BrokenOwnership()
    manager = PaperManager(ownership_factory=lambda *_args, **_kwargs: ownership)
    with pytest.raises(OSError, match="lease db unavailable"):
        manager.start(StartRequest(codes=["000001"]))
    assert ownership.closed


def test_paper_manager_stop_timeout_keeps_thread_and_lease() -> None:
    class FakeEngine:
        def stop(self):
            return None

    class FakeOwnership:
        def __init__(self):
            self.released = False
            self.closed = False

        def release(self):
            self.released = True

        def close(self):
            self.closed = True

    import threading
    import time
    blocker = threading.Event()
    thread = threading.Thread(target=blocker.wait, daemon=True)
    thread.start()
    ownership = FakeOwnership()
    manager = PaperManager()
    manager._thread = thread
    manager._engine = FakeEngine()
    manager._ownership = ownership
    manager._config = {"account_id": "acct-a"}
    manager._thread.join = lambda timeout=None: None  # type: ignore[method-assign]
    try:
        with pytest.raises(RuntimeError, match="仍在停止中"):
            manager.stop()
        assert manager._thread is thread
        assert manager._ownership is ownership
        assert not ownership.released
        with pytest.raises(RuntimeError, match="仍在停止中"):
            manager.start(StartRequest(codes=["000001"], account_id="acct-b"))
    finally:
        blocker.set()
        thread.join(timeout=1)
def test_paper_start_request_rejects_disabled_risk() -> None:
    with pytest.raises(ValueError, match="必须启用风控"):
        StartRequest(codes=["000001"], enable_risk=False)


def test_paper_start_request_defaults_account_and_risk() -> None:
    request = StartRequest(codes=["000001"])
    assert request.account_id == "paper-default"
    assert request.enable_risk is True
