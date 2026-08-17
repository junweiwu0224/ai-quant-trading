from dataclasses import replace

from dashboard.app import app
from dashboard.session import optional_account


def _account(workspace_id: str) -> dict:
    return {"user": {"id": f"user-{workspace_id}"}, "workspace": {"id": workspace_id}}


def _signal_payload() -> dict:
    return {
        "agent_id": "workspace-fixture",
        "source": "workspace-fixture",
        "code": "600000",
        "direction": "buy",
        "confidence": 0.8,
        "time_horizon": "3d",
        "entry_reasons": ["workspace evidence"],
        "risk_notes": ["workspace risk"],
        "suggested_position": 0.1,
    }


def test_agentic_workspace_services_use_independent_database_paths(tmp_path, monkeypatch):
    from dashboard.routers import agentic as agentic_router

    monkeypatch.setattr(agentic_router, "DB_DIR", tmp_path / "db")
    services_a = agentic_router._agentic_services(_account("workspace-a"))
    services_b = agentic_router._agentic_services(_account("workspace-b"))

    assert services_a["repository"].db_path != services_b["repository"].db_path
    assert services_a["paper_service"].order_manager.db_path != services_b["paper_service"].order_manager.db_path
    assert services_a["signal_service"].db_path == services_a["repository"].db_path
    assert services_b["signal_service"].db_path == services_b["repository"].db_path
    assert services_a["signal_service"].ledger.db_path == services_a["repository"].db_path
    assert services_b["signal_service"].ledger.db_path == services_b["repository"].db_path
    assert services_a["signal_service"].ledger.db_path != services_b["signal_service"].ledger.db_path


def test_agentic_router_isolates_workspace_reads_writes_and_triggers(client, tmp_path, monkeypatch):
    from agentic.models import PaperStrategyCandidate
    from dashboard.routers import agentic as agentic_router

    monkeypatch.setattr(agentic_router, "DB_DIR", tmp_path / "db")
    account_a = _account("workspace-a")
    account_b = _account("workspace-b")
    services_a = agentic_router._agentic_services(account_a)
    services_b = agentic_router._agentic_services(account_b)

    signal_a = services_a["signal_service"].publish(**_signal_payload())
    services_a["signal_service"].ledger.record_provenance(
        signal_a.id,
        source_type="research",
        source_id="workspace-a-source",
    )
    services_a["signal_service"].ledger.record_outcome(
        signal_a.id,
        status="hit",
        realized_return=0.12,
        observed_at="2026-08-15T08:00:00+00:00",
        metadata={"horizon_days": 3, "profile": "workspace-a"},
    )
    operation_a = services_a["repository"].record_operation(
        "workspace-shared-operation",
        command="workspace.fixture",
        aggregate_type="signal",
        aggregate_id=signal_a.id,
        request={"workspace": "workspace-a"},
        status="completed",
        result={"owner": "workspace-a"},
    )
    candidate_a = PaperStrategyCandidate(
        id="workspace-paper-candidate",
        candidate_id="workspace-strategy",
        name="Workspace strategy",
        dsl={"strategy_type": "ranked_rotation"},
        sample={"codes": ["600000"]},
        metrics={"trades": 10},
        promotion={"promoted": True},
        status="paper_candidate",
        requires_confirmation=True,
        created_at="2026-08-15T08:00:00+00:00",
    )
    services_a["repository"].save_paper_strategy_candidate(candidate_a)

    current_account = {"value": account_a}
    monkeypatch.setitem(
        app.dependency_overrides,
        optional_account,
        lambda: current_account["value"],
    )

    assert client.get("/api/agentic/signals").json()["signals"][0]["id"] == signal_a.id
    assert client.get("/api/agentic/strategy/paper-candidates").json()["candidates"][0]["id"] == candidate_a.id
    assert client.get("/api/agentic/operations/workspace-shared-operation").json()["operation"]["operation_id"] == operation_a.operation_id

    current_account["value"] = account_b

    assert client.get("/api/agentic/signals").json()["signals"] == []
    assert client.get(f"/api/agentic/signals/{signal_a.id}/provenance").status_code == 404
    assert client.get(f"/api/agentic/signals/{signal_a.id}/outcome").status_code == 404
    assert client.post(f"/api/agentic/signals/{signal_a.id}/outcome?horizon_days=3").status_code == 404
    assert client.get("/api/agentic/outcomes/aggregate?min_samples=1").json()["aggregates"] == []
    assert client.get("/api/agentic/operations/workspace-shared-operation").status_code == 404
    assert client.get("/api/agentic/strategy/paper-candidates").json()["candidates"] == []
    assert (
        client.post(
            f"/api/agentic/strategy/paper-candidates/{candidate_a.id}/confirm",
            json={"operation_id": "workspace-b-confirm", "confirmed_by": "workspace-b"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/agentic/strategy/paper-candidates/{candidate_a.id}/run",
            json={"operation_id": "workspace-b-run"},
        ).status_code
        == 404
    )

    # Reusing an aggregate id in B creates only B's projection; A remains unchanged.
    services_b["repository"].save_signal(replace(signal_a, metadata={"owner": "workspace-b"}))
    services_b["repository"].record_operation(
        operation_a.operation_id,
        command="workspace.fixture",
        aggregate_type="signal",
        aggregate_id=signal_a.id,
        request={"workspace": "workspace-b"},
        status="completed",
        result={"owner": "workspace-b"},
    )
    assert services_a["repository"].get_signal(signal_a.id).metadata.get("owner") != "workspace-b"
    assert services_a["repository"].get_operation(operation_a.operation_id).result == {"owner": "workspace-a"}
    assert services_b["repository"].get_signal(signal_a.id).metadata["owner"] == "workspace-b"
    assert services_b["repository"].get_operation(operation_a.operation_id).result == {"owner": "workspace-b"}
