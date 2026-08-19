from __future__ import annotations

from datetime import timedelta

import pytest

from ai_runtime import AIRuntime
from ai_runtime.providers import ProviderRouter
from ai_runtime.repository import AIRuntimeRepository
from engine.ai_worker import PiAgentWorker
from engine.decision_worker import SQLiteWorkerLease, utc_now


def _runtime(tmp_path) -> AIRuntime:
    return AIRuntime(AIRuntimeRepository(tmp_path / "pi-agent-worker-runtime.db"), provider_router=ProviderRouter([]))


def test_pi_agent_worker_acquires_an_exclusive_lease(tmp_path) -> None:
    runtime_one = _runtime(tmp_path)
    runtime_two = AIRuntime(AIRuntimeRepository(tmp_path / "pi-agent-worker-runtime.db"), provider_router=ProviderRouter([]))
    worker_one = PiAgentWorker(runtime_one, SQLiteWorkerLease(tmp_path / "worker-leases.db"), owner_id="pi-owner-a")
    worker_two = PiAgentWorker(runtime_two, SQLiteWorkerLease(tmp_path / "worker-leases.db"), owner_id="pi-owner-b")
    try:
        assert worker_one.acquire() is True
        assert worker_two.acquire() is False
        assert worker_one.owns_lease is True
        assert worker_one.fence_token

        worker_one.close()
        assert worker_two.acquire() is True
    finally:
        worker_one.close()
        worker_two.close()


def test_pi_agent_worker_tick_claims_and_completes_a_queued_task(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    task, _ = runtime.submit_task(
        workspace_id="workspace-1",
        kind="analysis",
        profile="quick",
        request={"question": "fixture"},
    )
    worker = PiAgentWorker(
        runtime,
        SQLiteWorkerLease(tmp_path / "worker-leases.db"),
        owner_id="pi-owner",
        batch_size=1,
    )
    try:
        assert worker.acquire() is True
        results = worker.tick()
        stored = runtime.task(task["id"], "workspace-1")
        events = runtime.events(task["id"], "workspace-1")

        assert len(results) == 1
        assert stored is not None
        assert stored["status"] == "degraded"
        assert stored["report_id"]
        assert "task_started" in [event["event_type"] for event in events]
    finally:
        worker.close()


def test_pi_agent_worker_rejects_a_reclaimed_fence_before_publishing_work(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    primary_lease = SQLiteWorkerLease(tmp_path / "worker-leases.db", lease_name="ai-worker")
    replacement_lease = SQLiteWorkerLease(tmp_path / "worker-leases.db", lease_name="ai-worker")
    worker = PiAgentWorker(runtime, primary_lease, owner_id="pi-owner-a", lease_ttl_seconds=30)
    try:
        assert worker.acquire() is True
        replacement = replacement_lease.acquire(
            "pi-owner-b",
            ttl_seconds=30,
            now=utc_now() + timedelta(seconds=31),
        )
        assert replacement is not None
        assert replacement.fence_token != worker.fence_token

        with pytest.raises(RuntimeError, match="fence token"):
            worker._assert_fence()
        assert worker.owns_lease is False
        assert worker.fence_token == ""
    finally:
        worker.close()
        replacement_lease.close()


def test_pi_agent_worker_tick_aborts_when_lease_is_reclaimed_during_processing(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    replacement_lease = SQLiteWorkerLease(tmp_path / "worker-leases.db", lease_name="ai-worker")
    worker = PiAgentWorker(
        runtime,
        SQLiteWorkerLease(tmp_path / "worker-leases.db", lease_name="ai-worker"),
        owner_id="pi-owner-a",
        lease_ttl_seconds=30,
    )

    def steal_fence(**_kwargs):
        replacement = replacement_lease.acquire(
            "pi-owner-b",
            ttl_seconds=30,
            now=utc_now() + timedelta(seconds=31),
        )
        assert replacement is not None
        return []

    try:
        assert worker.acquire() is True
        runtime.process_pending = steal_fence  # type: ignore[method-assign]
        with pytest.raises(RuntimeError, match="fence token"):
            worker.tick()
        assert worker.owns_lease is False
    finally:
        worker.close()
        replacement_lease.close()
