"""Independent Pi Agent worker for queued AI research tasks.

This process owns the AI task lease but never owns decision, order, or
notification state.  ``ai_runtime`` keeps task orchestration and audit;
Pi only generates non-authoritative research artifacts from frozen input.
"""

from __future__ import annotations

import os
import socket
import threading

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from ai_runtime import AIRuntime
from ai_runtime.models import ProviderChannel
from ai_runtime.repository import AIRuntimeRepository
from engine.decision_worker import SQLiteWorkerLease, feature_enabled, utc_now


@dataclass
class PiAgentWorker:
    runtime: AIRuntime
    lease: SQLiteWorkerLease
    owner_id: str = field(default_factory=lambda: f"{socket.gethostname()}:{os.getpid()}:pi-agent:{uuid.uuid4().hex}")
    lease_ttl_seconds: float = 30.0
    poll_interval_seconds: float = 2.0
    batch_size: int = 4
    _owns_lease: bool = field(default=False, init=False, repr=False)
    _fence_token: str = field(default="", init=False, repr=False)
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False, repr=False)

    @classmethod
    def from_environment(cls) -> "PiAgentWorker":
        from config.settings import DB_DIR

        database = Path(DB_DIR) / "ai_runtime.db"
        command = [item for item in os.getenv("PI_AGENT_COMMAND", "pi").split() if item] or ["pi"]
        channel = ProviderChannel(
            id="pi-agent",
            name="Pi Agent",
            protocol="pi_agent",
            model=os.getenv("PI_AGENT_MODEL", ""),
            command=command,
            timeout_seconds=float(os.getenv("PI_AGENT_TIMEOUT_SECONDS", "90")),
            supports_stream=False,
        )
        return cls(
            runtime=AIRuntime(AIRuntimeRepository(database), channels=[channel], force_default_router=True),
            # Keep this persisted lease key stable across worker implementation changes.
            lease=SQLiteWorkerLease(Path(DB_DIR) / "worker_leases.db", lease_name="ai-worker"),
            lease_ttl_seconds=float(os.getenv("PI_AGENT_WORKER_LEASE_TTL_SECONDS", "30")),
            poll_interval_seconds=float(os.getenv("PI_AGENT_WORKER_POLL_INTERVAL_SECONDS", "2")),
            batch_size=max(1, min(int(os.getenv("PI_AGENT_WORKER_BATCH_SIZE", "4")), 20)),
        )

    @property
    def owns_lease(self) -> bool:
        return self._owns_lease

    @property
    def fence_token(self) -> str:
        return self._fence_token

    def acquire(self) -> bool:
        acquired = self.lease.acquire(self.owner_id, ttl_seconds=self.lease_ttl_seconds)
        self._owns_lease = acquired is not None
        self._fence_token = acquired.fence_token if acquired is not None else ""
        if self._owns_lease and not self.lease.heartbeat(self.owner_id, fence_token=self._fence_token, status="ready"):
            self._owns_lease = False
            self._fence_token = ""
        return self._owns_lease

    def renew(self) -> bool:
        if not self._owns_lease:
            return False
        renewed = self.lease.renew(self.owner_id, fence_token=self._fence_token, ttl_seconds=self.lease_ttl_seconds)
        self._owns_lease = renewed is not None
        if not self._owns_lease:
            self._fence_token = ""
        return self._owns_lease

    def _assert_fence(self) -> None:
        if not self._owns_lease or not self._fence_token:
            raise RuntimeError("ai worker lease is not owned")
        current = self.lease.current()
        if current is None or current.owner_id != self.owner_id or current.fence_token != self._fence_token or current.expires_at <= utc_now():
            self._owns_lease = False
            self._fence_token = ""
            raise RuntimeError("ai worker lease fence token is no longer valid")

    def tick(self) -> list[dict[str, Any]]:
        if not self.renew():
            return []
        self._assert_fence()
        self.lease.heartbeat(self.owner_id, fence_token=self._fence_token, status="running")
        results = self.runtime.process_pending(owner_id=self.owner_id, limit=self.batch_size, lease_ttl_seconds=self.lease_ttl_seconds, fence_check=self._assert_fence)
        self._assert_fence()
        self.lease.heartbeat(self.owner_id, fence_token=self._fence_token, status="ready", last_success=utc_now())
        return results

    def readiness(self, *, max_age_seconds: float = 90.0) -> dict[str, Any]:
        state = self.lease.readiness(max_age_seconds=max_age_seconds)
        state["owns_lease"] = self._owns_lease
        return state

    def request_stop(self) -> None:
        self._stop_event.set()
        if self._owns_lease:
            try:
                self.lease.heartbeat(self.owner_id, fence_token=self._fence_token, status="draining", draining=True)
            except Exception:
                logger.debug("unable to persist AI worker draining heartbeat")

    def run_forever(self) -> None:
        if not self.acquire():
            raise RuntimeError("AI worker lease is already held")
        try:
            while not self._stop_event.is_set():
                try:
                    self.tick()
                except Exception as exc:
                    logger.exception("AI worker tick failed: {}", exc)
                    if self._owns_lease:
                        self.lease.heartbeat(self.owner_id, fence_token=self._fence_token, status="error", error=str(exc)[:1000])
                self._stop_event.wait(timeout=max(0.25, self.poll_interval_seconds))
        finally:
            self.close()

    def close(self) -> None:
        if self._owns_lease:
            try:
                self.lease.release(self.owner_id, fence_token=self._fence_token)
            except Exception:
                logger.debug("unable to release AI worker lease")
        self._owns_lease = False
        self._fence_token = ""
        self.lease.close()
        self.runtime.repository.close()


def pi_agent_worker_enabled() -> bool:
    return feature_enabled("PI_AGENT_WORKER_ENABLED", default=False)

