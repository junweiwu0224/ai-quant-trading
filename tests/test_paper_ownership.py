from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dashboard.routers.paper_control import StartRequest
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


def test_paper_start_request_rejects_disabled_risk() -> None:
    with pytest.raises(ValueError, match="必须启用风控"):
        StartRequest(codes=["000001"], enable_risk=False)


def test_paper_start_request_defaults_account_and_risk() -> None:
    request = StartRequest(codes=["000001"])
    assert request.account_id == "paper-default"
    assert request.enable_risk is True
