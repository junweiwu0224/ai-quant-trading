def test_agentic_agents_endpoint_lists_builtin_agents(client):
    resp = client.get("/api/agentic/agents")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert any(item["id"] == "qlib_agent" for item in body["agents"])


def test_agentic_signals_endpoint_returns_list(client, monkeypatch, tmp_path):
    from dashboard.routers import agentic as agentic_router
    from agentic.repository import AgenticRepository
    from agentic.signals import SignalService

    monkeypatch.setattr(agentic_router, "signal_service", SignalService(AgenticRepository(tmp_path / "agentic.db")))

    resp = client.get("/api/agentic/signals")

    assert resp.status_code == 200
    assert resp.json() == {"success": True, "signals": []}


def test_agentic_health_reports_core_components(client):
    resp = client.get("/api/agentic/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["components"]["registry"] == "online"
    assert body["components"]["signals"] == "online"
