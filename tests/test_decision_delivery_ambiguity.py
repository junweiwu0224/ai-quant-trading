from __future__ import annotations

from pathlib import Path

import decision.delivery as delivery_module
from decision.delivery import DecisionDeliveryService
from decision.store import DecisionStore
from engine.events.models import DomainEvent
from engine.notifications.models import DeliveryResult


def _fixture(tmp_path: Path):
    store = DecisionStore(tmp_path / "decisions.db")
    portfolio = store.create_portfolio("workspace", "CN", "投递语义")
    version = store.create_version(
        "workspace",
        portfolio["id"],
        {"strategies": [{"strategy_name": "a", "weight": 1}]},
    )
    member = store.add_member("workspace", portfolio["id"], "A")
    snapshot = store.create_snapshot(
        "workspace",
        version["id"],
        {"members": [{"membership_id": member["id"], "symbol": "A"}]},
        "fixture",
        "ok",
    )
    run = store.create_run(
        "workspace",
        portfolio["id"],
        version["id"],
        snapshot["id"],
        "delivery-run",
        "scheduled_prepare:morning",
        "prepared",
    )
    decision = store.record_decision(
        run["id"],
        member["id"],
        {"symbol": "A", "action": "buy_candidate", "valid": True, "confirmed": True},
    )
    report = store.create_report(run, snapshot, version, [decision], "prepared")
    store.complete_run(run["id"])
    target = store.create_target(
        "workspace",
        "wecom_robot",
        "目标",
        {"secret_ref": "env://TARGET", "endpoint_ref": "env://ENDPOINT"},
    )
    store.mark_target_test("workspace", target["id"], "passed")
    store.create_route("workspace", portfolio["id"], target["id"], "scheduled")
    event = DomainEvent.create(
        "decision.report.scheduled",
        portfolio["id"],
        {"changes": [{"symbol": "A", "action": "buy_candidate"}]},
        idempotency_key="delivery-ambiguous-event",
    )
    return store, report, target, event


def test_provider_timeout_becomes_unknown_and_is_never_reclaimed(
    tmp_path: Path, monkeypatch
) -> None:
    store, report, target, event = _fixture(tmp_path)
    monkeypatch.setenv("DECISION_EXTERNAL_DELIVERY_ENABLED", "true")
    calls = {"count": 0}

    class TimeoutAdapter:
        def send(self, _event):
            calls["count"] += 1
            raise TimeoutError("provider response timed out")

    service = DecisionDeliveryService(store, owner_id="worker-a", worker_owned=True)
    service._adapter = lambda _target: TimeoutAdapter()

    first = service._deliver_event("workspace", report["id"], event)
    claims = store.list_delivery_claims("workspace", report["id"])
    second = service._deliver_event("workspace", report["id"], event)

    assert first[0]["status"] == "unknown"
    assert claims[0]["status"] == "unknown"
    assert second[0]["reason"] == "unknown"
    assert calls["count"] == 1
    assert store.list_delivery_attempts("workspace", report["id"])[0]["status"] == "unknown"


def test_permanent_provider_rejection_closes_claim_as_dead(
    tmp_path: Path, monkeypatch
) -> None:
    store, report, target, event = _fixture(tmp_path)
    monkeypatch.setenv("DECISION_EXTERNAL_DELIVERY_ENABLED", "true")

    class RejectingAdapter:
        def send(self, _event):
            return DeliveryResult(delivered=False, retryable=False, error="rejected")

    service = DecisionDeliveryService(store, owner_id="worker-a", worker_owned=True)
    service._adapter = lambda _target: RejectingAdapter()

    result = service._deliver_event("workspace", report["id"], event)

    assert result[0]["status"] == "failed"
    assert store.list_delivery_claims("workspace", report["id"])[0]["status"] == "dead"


def test_real_channel_adapter_timeout_is_unknown_and_not_retried(
    tmp_path: Path, monkeypatch
) -> None:
    store, report, _target, event = _fixture(tmp_path)
    monkeypatch.setenv("DECISION_EXTERNAL_DELIVERY_ENABLED", "true")
    monkeypatch.setenv("TARGET", "test-token")
    monkeypatch.setenv("ENDPOINT", "https://example.invalid/wecom")
    calls = {"count": 0}

    def timeout_transport(*_args, **_kwargs):
        calls["count"] += 1
        raise TimeoutError("provider response timed out")

    monkeypatch.setattr(delivery_module, "_transport", timeout_transport)
    service = DecisionDeliveryService(store, owner_id="worker-real", worker_owned=True)

    first = service._deliver_event("workspace", report["id"], event)
    second = service._deliver_event("workspace", report["id"], event)

    assert first[0]["status"] == "unknown"
    assert second[0]["reason"] == "unknown"
    assert calls["count"] == 1
    assert store.list_delivery_claims("workspace", report["id"])[0]["status"] == "unknown"
