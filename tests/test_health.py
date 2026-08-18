"""Unauthenticated liveness and readiness probe contracts."""

import pytest

pytestmark = pytest.mark.unit


def test_health_is_public_and_reports_liveness(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "dashboard"}


def test_readiness_is_public_and_reports_dependency_state(client):
    response = client.get("/readiness")

    assert response.status_code in {200, 503}
    payload = response.json()
    assert payload["service"] == "dashboard"
    assert payload["status"] in {"ready", "degraded", "unavailable"}
    assert "dependencies" in payload
    assert "database" in payload["dependencies"]
    assert "quote_service" in payload["dependencies"]
    assert "qlib" in payload["dependencies"]
    for worker_name in ("decision_worker", "ai_worker"):
        worker = payload["dependencies"].get(worker_name)
        if worker:
            assert "owner_id" not in worker
            assert "fence_token" not in worker
            assert "lease_owner_id" not in worker
    for worker_name in ("decision_worker", "ai_worker"):
        worker = payload["dependencies"].get(worker_name)
        if worker:
            assert "owner_id" not in worker
            assert "fence_token" not in worker
            assert "lease_owner_id" not in worker
