from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from decision.delivery import DecisionDeliveryService
from decision.runtime import DecisionRuntime
from decision.store import DecisionStore
from engine.decision_worker import DecisionWorker, SQLiteWorkerLease, WorkerCallbacks
from engine.events.outbox import SQLiteOutbox


def test_command_queue_is_workspace_scoped_and_idempotent(tmp_path: Path) -> None:
    store = DecisionStore(tmp_path / "decisions.db")
    portfolio = store.create_portfolio("workspace-a", "CN", "组合")

    first = store.enqueue_command(
        "workspace-a",
        "decision.preview",
        {"portfolio_id": portfolio["id"]},
        "request-1",
        portfolio_id=portfolio["id"],
    )
    replay = store.enqueue_command(
        "workspace-a",
        "decision.preview",
        {"portfolio_id": portfolio["id"]},
        "request-1",
        portfolio_id=portfolio["id"],
    )
    assert replay["id"] == first["id"]
    assert replay["status"] == "queued"

    with pytest.raises(ValueError, match="command_idempotency_conflict"):
        store.enqueue_command(
            "workspace-a",
            "decision.analyze",
            {"portfolio_id": portfolio["id"]},
            "request-1",
            portfolio_id=portfolio["id"],
        )
    with pytest.raises(KeyError, match="command_portfolio_not_found"):
        store.enqueue_command(
            "workspace-b",
            "decision.preview",
            {"portfolio_id": portfolio["id"]},
            "request-b",
            portfolio_id=portfolio["id"],
        )

    claimed = store.claim_commands("worker-a", now=datetime(2026, 8, 15, tzinfo=timezone.utc))
    assert [item["id"] for item in claimed] == [first["id"]]
    completed = store.complete_command(first["id"], "worker-a", {"ok": True})
    assert completed["status"] == "completed"
    assert completed["result"] == {"ok": True}
    assert store.claim_commands("worker-b") == []


def test_runtime_command_execution_is_completed_by_worker_owner(tmp_path: Path, monkeypatch) -> None:
    store = DecisionStore(tmp_path / "decisions.db")
    portfolio = store.create_portfolio("workspace-a", "CN", "组合")
    command = store.enqueue_command(
        "workspace-a",
        "decision.analyze",
        {"portfolio_id": portfolio["id"]},
        "request-2",
        portfolio_id=portfolio["id"],
    )
    runtime = DecisionRuntime(store, object())
    monkeypatch.setattr(
        runtime,
        "run",
        lambda *_args, **_kwargs: {"report": {"id": "report-1"}, "decisions": []},
    )

    processed = runtime.process_commands(owner_id="worker-a")

    assert processed[0]["id"] == command["id"]
    assert processed[0]["status"] == "completed"
    assert processed[0]["result"]["report"]["id"] == "report-1"


def test_disabling_auto_push_is_a_worker_command_and_preserves_other_opt_ins(tmp_path: Path, monkeypatch) -> None:
    store = DecisionStore(tmp_path / "decisions.db")
    first = store.create_portfolio("workspace-a", "CN", "第一组")
    second = store.create_portfolio("workspace-a", "CN", "第二组")
    store.set_auto_push("workspace-a", first["id"], True)
    store.set_auto_push("workspace-a", second["id"], True)
    command = store.enqueue_command(
        "workspace-a",
        "decision.disable_auto_push",
        {"portfolio_id": first["id"]},
        "disable-first",
        portfolio_id=first["id"],
    )
    updates: list[tuple[str, dict]] = []

    from dashboard.account_store import account_store

    monkeypatch.setattr(
        account_store,
        "update_workspace_settings",
        lambda workspace_id, settings: updates.append((workspace_id, settings))
        or {"id": workspace_id, "settings": settings},
    )

    processed = DecisionRuntime(store, object()).process_commands(owner_id="worker-a")

    assert processed[0]["id"] == command["id"]
    assert processed[0]["status"] == "completed"
    assert processed[0]["result"]["enabled"] is False
    assert store.get_portfolio("workspace-a", first["id"])["auto_push_enabled"] is False
    assert store.get_portfolio("workspace-a", second["id"])["auto_push_enabled"] is True
    assert updates == [("workspace-a", {"decision_auto_push_enabled": True})]


def test_worker_invokes_command_hook_before_external_dispatch(tmp_path: Path) -> None:
    calls: list[dict] = []
    worker = DecisionWorker(
        SQLiteWorkerLease(tmp_path / "worker.db"),
        SQLiteOutbox(tmp_path / "events.db"),
        callbacks=WorkerCallbacks(
            is_trading_day=lambda _when: False,
            process_commands=lambda **kwargs: calls.append(kwargs) or [{"status": "completed"}],
        ),
        poll_interval_seconds=60,
    )
    try:
        now = datetime(2026, 8, 15, 0, 0, tzinfo=timezone.utc)
        assert worker.acquire(now=now) is True
        tick = worker.tick(now=now)
    finally:
        worker.close()

    assert tick.commands_processed == 1
    assert calls[0]["owner_id"] == worker.owner_id


def test_scheduled_summary_only_lists_real_changes() -> None:
    report = {
        "id": "report-1",
        "decision_run_id": "run-1",
        "report_hash": "hash-1",
        "body": {
            "portfolio_id": "portfolio-1",
            "quality_status": "ok",
            "decisions": [
                {"symbol": "A", "action": "watch", "previous_action": None},
                {"symbol": "B", "action": "hold", "previous_action": "hold"},
                {"symbol": "C", "action": "major_risk", "previous_action": "hold"},
            ],
        },
    }

    event = DecisionDeliveryService._event(report, "scheduled", "/report/share-1")

    assert [item["symbol"] for item in event.payload["changes"]] == ["C"]
    assert event.payload["total_count"] == 3
    assert event.payload["summary"] == "1 个标的发生动作变化"


def test_dashboard_decision_routes_do_not_execute_worker_work() -> None:
    source = Path("dashboard/routers/decisions.py").read_text(encoding="utf-8")

    assert "DecisionRuntime" not in source
    assert "runtime.run" not in source
    assert "runtime.validate" not in source
    assert "delivery.test_target" not in source
    assert "store.set_auto_push" not in source
    assert 'status_code=202' in source
