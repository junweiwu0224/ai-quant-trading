from __future__ import annotations

from ai_runtime.repository import AIRuntimeRepository
from ai_runtime.models import ProviderChannel
from ai_runtime.providers import ProviderRouter


def test_provider_readiness_does_not_treat_secret_presence_as_verified(monkeypatch) -> None:
    monkeypatch.setenv("FIXTURE_PROVIDER_KEY", "configured-but-not-proven")
    router = ProviderRouter(
        [
            ProviderChannel(
                id="fixture",
                name="Fixture",
                model="fixture-model",
                secret_ref="env://FIXTURE_PROVIDER_KEY",
            )
        ]
    )

    initial = router.public_status()[0]
    assert initial["secret_available"] is True
    assert initial["readiness"]["configured"] is True
    assert initial["readiness"]["overall"] == "configured_unverified"
    assert initial["readiness"]["ready"] is False

    router._set_runtime_state("fixture", status="failed", error_code="http_error")
    failed = router.public_status()[0]["readiness"]
    assert failed["overall"] == "configured_recent_failure"
    assert failed["ready"] is False

    router._set_runtime_state("fixture", status="verified")
    verified = router.public_status()[0]["readiness"]
    assert verified["overall"] == "verified"
    assert verified["runtime_verified"] is True
    assert verified["ready"] is True


def test_provider_readiness_and_attempts_survive_a_new_process_router(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FIXTURE_PROVIDER_KEY", "configured-but-not-proven")
    database = tmp_path / "ai-runtime.db"
    channel = ProviderChannel(
        id="fixture",
        name="Fixture",
        model="fixture-model",
        secret_ref="env://FIXTURE_PROVIDER_KEY",
    )

    worker_store = AIRuntimeRepository(database)
    worker_router = ProviderRouter([channel], runtime_store=worker_store)
    worker_router._set_runtime_state("fixture", status="verified")
    worker_router._record_attempt_history([{
        "attempt": 1,
        "provider": "fixture",
        "model": "fixture-model",
        "relation": "initial",
        "status": "success",
        "duration_ms": 12,
    }])
    worker_store.close()

    dashboard_store = AIRuntimeRepository(database)
    dashboard_router = ProviderRouter([channel], runtime_store=dashboard_store)
    status = dashboard_router.public_status()[0]

    assert status["readiness"]["overall"] == "verified"
    assert status["readiness"]["ready"] is True
    assert status["attempts"][0]["provider"] == "fixture"
    assert status["attempts"][0]["status"] == "success"
    dashboard_store.close()
