from __future__ import annotations

import sqlite3

import pytest

from engine.operations_store import (
    IdempotencyConflictError,
    LeaseLostError,
    OperationsStore,
    TaskNotClaimableError,
)


class Clock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def make_store(tmp_path, clock: Clock | None = None) -> OperationsStore:
    return OperationsStore(tmp_path / "operations.db", now=clock or Clock())


def test_sqlite_is_configured_for_durable_operations(tmp_path):
    store = make_store(tmp_path)
    assert store.connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert store.connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    assert store.connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    store.close()


def test_store_creates_nested_database_parent_and_pragmas(tmp_path):
    database = tmp_path / "nested" / "operations.db"
    store = OperationsStore(database)
    try:
        assert database.exists()
        assert store.connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert store.connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert store.connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        store.close()


def test_lease_checks_sample_clock_after_write_transaction_starts(tmp_path):
    class SamplingClock:
        def __init__(self):
            self.values = iter((100.0, 100.0, 106.0, 112.0))

        def __call__(self):
            return next(self.values)

    store = OperationsStore(tmp_path / "operations.db", now=SamplingClock(), lease_seconds=5)
    accepted = store.accept_command(idempotency_key="resample", kind="paper.execute")
    attempt = store.claim_task("worker", task_id=accepted.task.id)
    assert attempt.started_at == 106.0
    with pytest.raises(LeaseLostError):
        store.succeed_attempt(attempt.id, attempt.owner_id, attempt.lease_token, attempt.fence)
    store.close()


def test_command_acceptance_is_idempotent_and_queues_one_task(tmp_path):
    store = make_store(tmp_path)
    first = store.accept_command(
        idempotency_key="order-1",
        kind="paper.execute",
        payload={"symbol": "600000.SH", "side": "buy"},
    )
    replay = store.accept_command(
        idempotency_key="order-1",
        kind="paper.execute",
        payload={"side": "buy", "symbol": "600000.SH"},
    )

    assert replay == first
    assert first.command.id != first.task.id
    assert first.task.command_id == first.command.id
    assert first.task.status == "queued"
    assert store.connection.execute("SELECT COUNT(*) FROM commands").fetchone()[0] == 1
    assert store.connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 1

    with pytest.raises(IdempotencyConflictError):
        store.accept_command(idempotency_key="order-1", kind="different", payload={})

    with pytest.raises(ValueError, match="idempotency_key"):
        store.accept_command(idempotency_key="  ", kind="paper.execute")



def test_filtered_claim_selects_oldest_eligible_task_and_leaves_unrelated_queued(tmp_path):
    store = make_store(tmp_path)
    unrelated = store.accept_command(idempotency_key="decision", kind="decision.execute")
    eligible = store.accept_command(idempotency_key="paper", kind="paper.execute")
    allowed_kinds = [" paper.execute ", "paper.execute"]

    attempt = store.claim_task("paper-worker", allowed_kinds=allowed_kinds)

    assert attempt.task_id == eligible.task.id
    assert allowed_kinds == [" paper.execute ", "paper.execute"]
    assert store.get_task(unrelated.task.id).status == "queued"
    assert store.connection.execute("SELECT COUNT(*) FROM task_attempts").fetchone()[0] == 1


def test_filtered_claim_skips_expired_unrelated_task_and_claims_oldest_eligible(tmp_path):
    clock = Clock()
    store = make_store(tmp_path, clock)
    unrelated = store.accept_command(idempotency_key="expired-decision", kind="decision.execute")
    unrelated_attempt = store.claim_task(
        "decision-worker", task_id=unrelated.task.id, lease_seconds=5
    )
    clock.advance(5)
    oldest_eligible = store.accept_command(idempotency_key="paper-old", kind="paper.execute")
    clock.advance(1)
    newest_eligible = store.accept_command(idempotency_key="paper-new", kind="paper.execute")

    attempt = store.claim_attempt("paper-worker", allowed_kinds={"paper.execute"})

    assert attempt.task_id == oldest_eligible.task.id
    assert attempt.task_id != newest_eligible.task.id
    assert store.get_task(unrelated.task.id).status == "running"
    assert store.get_attempt(unrelated_attempt.id).status == "running"


def test_explicit_filtered_claim_of_excluded_task_does_not_mutate_state(tmp_path):
    store = make_store(tmp_path)
    excluded = store.accept_command(idempotency_key="excluded", kind="decision.execute")
    task_before = store.get_task(excluded.task.id)

    with pytest.raises(TaskNotClaimableError):
        store.claim_attempt(
            "paper-worker", task_id=excluded.task.id, allowed_kinds=["paper.execute"]
        )

    assert store.get_task(excluded.task.id) == task_before
    assert store.connection.execute("SELECT COUNT(*) FROM task_attempts").fetchone()[0] == 0


def test_empty_allowed_kinds_claim_nothing_and_blank_values_are_rejected(tmp_path):
    store = make_store(tmp_path)
    accepted = store.accept_command(idempotency_key="paper", kind="paper.execute")

    with pytest.raises(TaskNotClaimableError):
        store.claim_task("worker", allowed_kinds=[])
    with pytest.raises(ValueError, match="blank"):
        store.claim_task("worker", allowed_kinds=["paper.execute", " "])

    assert store.get_task(accepted.task.id).status == "queued"
    assert store.connection.execute("SELECT COUNT(*) FROM task_attempts").fetchone()[0] == 0


def test_claim_without_kind_filter_remains_backward_compatible(tmp_path):
    store = make_store(tmp_path)
    accepted = store.accept_command(idempotency_key="decision", kind="decision.execute")

    attempt = store.claim_task("worker")

    assert attempt.task_id == accepted.task.id
    assert store.get_task(accepted.task.id).status == "running"


def test_attempt_lifecycle_writes_success_and_failure_terminal_states(tmp_path):
    clock = Clock()
    store = make_store(tmp_path, clock)
    success = store.accept_command(idempotency_key="success", kind="paper.execute")
    success_attempt = store.claim_attempt("worker-a", task_id=success.task.id)
    completed = store.succeed_attempt(
        success_attempt.id,
        success_attempt.owner_id,
        success_attempt.lease_token,
        success_attempt.fence,
    )
    assert completed.status == "succeeded"
    assert store.get_task(success.task.id).status == "succeeded"

    failed = store.accept_command(idempotency_key="failure", kind="paper.execute")
    failed_attempt = store.claim_task("worker-b", task_id=failed.task.id)
    completed = store.fail_attempt(
        failed_attempt.id,
        failed_attempt.owner_id,
        failed_attempt.lease_token,
        failed_attempt.fence,
        "adapter rejected order",
    )
    assert completed.status == "failed"
    assert completed.error == "adapter rejected order"
    assert store.get_task(failed.task.id).status == "failed"


def test_expired_lease_reclaims_with_new_fence_and_old_owner_cannot_finish(tmp_path):
    clock = Clock()
    store = make_store(tmp_path, clock)
    accepted = store.accept_command(idempotency_key="reclaim", kind="paper.execute")
    old = store.claim_task("worker-old", task_id=accepted.task.id, lease_seconds=10)

    with pytest.raises(TaskNotClaimableError):
        store.claim_task("worker-new", task_id=accepted.task.id)

    clock.advance(10)
    new = store.claim_attempt("worker-new", task_id=accepted.task.id)
    assert new.fence == old.fence + 1
    assert store.get_attempt(old.id).status == "reclaimed"
    assert store.get_task(accepted.task.id).status == "running"

    with pytest.raises(LeaseLostError):
        store.succeed_attempt(old.id, old.owner_id, old.lease_token, old.fence)
    with pytest.raises(LeaseLostError):
        store.fail_attempt(old.id, old.owner_id, old.lease_token, old.fence, "late failure")

    completed = store.succeed_attempt(new.id, new.owner_id, new.lease_token, new.fence)
    assert completed.status == "succeeded"
    assert store.get_task(accepted.task.id).status == "succeeded"


def test_expired_current_lease_cannot_write_terminal_state_until_reclaimed(tmp_path):
    clock = Clock()
    store = make_store(tmp_path, clock)
    accepted = store.submit_command(idempotency_key="expired", kind="paper.execute")
    attempt = store.claim_attempt("worker", task_id=accepted.task.id, lease_seconds=5)
    clock.advance(5)

    with pytest.raises(LeaseLostError):
        store.succeed_attempt(attempt.id, attempt.owner_id, attempt.lease_token, attempt.fence)
    assert store.get_task(accepted.task.id).status == "running"


def test_foreign_key_rejects_orphan_rows(tmp_path):
    store = make_store(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        store.connection.execute(
            "INSERT INTO tasks(id, command_id, status, created_at, updated_at) "
            "VALUES ('orphan', 'missing', 'queued', 1, 1)"
        )


def test_normalize_allowed_kinds_rejects_single_string(tmp_path: Path) -> None:
    """Test that _normalize_allowed_kinds rejects a single string instead of iterating characters."""
    store = OperationsStore(database=tmp_path / "test.db")
    with pytest.raises(ValueError, match="allowed_kinds must be an iterable of strings, not a single string"):
        store._normalize_allowed_kinds("paper.start")
