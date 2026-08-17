from __future__ import annotations

import json
from typing import Any

from ai_runtime import AIRuntime
from ai_runtime.models import GenerationResult
from ai_runtime.repository import AIRuntimeRepository
from dashboard.routers import ai as ai_router


class APIProviderRouter:
    """Provider double used by API tests; it exposes no credential value."""

    def __init__(self) -> None:
        self.calls: list[list[dict[str, str]]] = []

    def public_status(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "fixture-provider",
                "name": "Fixture provider",
                "protocol": "openai_compatible",
                "base_url": "http://fixture.invalid/v1",
                "model": "fixture-model",
                "secret_ref": "env://AI_FIXTURE_SECRET",
                "secret_available": True,
                "config_error": "",
                "enabled": True,
                "priority": 1,
                "supports_json": True,
                "supports_stream": True,
            }
        ]

    def generate(self, messages: list[dict[str, str]], *, json_mode: bool = True) -> GenerationResult:
        self.calls.append(messages)
        if json_mode:
            return GenerationResult(text="not-json fixture output", provider="fixture-provider", model="fixture-model")
        return GenerationResult(text="fixture chat answer", provider="fixture-provider", model="fixture-model")


def _install_runtime(monkeypatch, tmp_path) -> APIProviderRouter:
    provider = APIProviderRouter()
    monkeypatch.setattr(
        ai_router,
        "runtime",
        AIRuntime(AIRuntimeRepository(tmp_path / "api-ai-runtime.db"), provider_router=provider),
    )
    monkeypatch.setattr(ai_router, "DB_DIR", tmp_path / "dashboard-db")
    return provider


def _context() -> dict[str, Any]:
    return {
        "market": "CN",
        "instrument": "600000",
        "as_of": "2026-08-14T07:00:00Z",
        "blocks": {"quote": {"status": "available", "close": 12.34}},
        "evidence": [{"source": "api-fixture", "claim": "input"}],
        "quality_status": "available",
    }


def test_ai_status_channels_models_and_skills_are_queryable_without_external_calls(client, monkeypatch, tmp_path) -> None:
    _install_runtime(monkeypatch, tmp_path)

    status = client.get("/api/ai/status")
    channels = client.get("/api/ai/channels")
    models = client.get("/api/ai/models")
    skills = client.get("/api/ai/skills")

    assert status.status_code == 200, status.text
    assert status.json()["success"] is True
    assert status.json()["decision_effect"] == "none"
    assert channels.status_code == 200
    assert channels.json()["items"][0]["id"] == "fixture-provider"
    assert models.status_code == 200
    assert models.json()["items"][0]["model"] == "fixture-model"
    skill_ids = {item["id"] for item in skills.json()["items"]}
    assert {"multi_agent_analysis", "deep_research", "screening_query", "strategy_generation"} <= skill_ids


def test_ai_channel_api_only_handles_secret_references_and_never_echoes_secret(client, monkeypatch, tmp_path) -> None:
    _install_runtime(monkeypatch, tmp_path)
    secret = "fixture-super-secret-value"
    monkeypatch.setenv("AI_FIXTURE_SECRET", secret)

    response = client.post(
        "/api/ai/channels",
        json={
            "id": "configured-fixture",
            "name": "Configured fixture",
            "protocol": "openai_compatible",
            "base_url": "http://fixture.invalid/v1",
            "model": "fixture-model",
            "secret_ref": "env://AI_FIXTURE_SECRET",
        },
    )

    assert response.status_code == 200, response.text
    assert secret not in response.text
    assert response.json()["items"][0]["secret_ref"] == "env://AI_FIXTURE_SECRET"
    assert response.json()["items"][0]["secret_available"] is True

    raw_secret = client.post(
        "/api/ai/channels",
        json={
            "id": "unsafe-fixture",
            "name": "Unsafe fixture",
            "secret_ref": secret,
        },
    )
    assert raw_secret.status_code in {400, 422}
    assert secret not in raw_secret.text


def test_ai_task_api_supports_idempotency_run_and_event_history(client, monkeypatch, tmp_path) -> None:
    _install_runtime(monkeypatch, tmp_path)
    payload = {
        "kind": "analysis",
        "profile": "quick",
        "request": {"question": "fixture"},
        "context": _context(),
        "idempotency_key": "api-task-fixture-1",
    }

    created = client.post("/api/ai/tasks", json=payload)
    replay = client.post("/api/ai/tasks", json=payload)
    assert created.status_code == 200, created.text
    assert replay.status_code == 200, replay.text
    assert created.json()["created"] is True
    assert replay.json()["created"] is False
    task_id = created.json()["task"]["id"]
    assert replay.json()["task"]["id"] == task_id

    run = client.post(f"/api/ai/tasks/{task_id}/run")
    assert run.status_code == 200, run.text
    assert run.json()["status"] in {"completed", "degraded"}

    events = client.get(f"/api/ai/tasks/{task_id}/events")
    assert events.status_code == 200
    event_types = [item["event_type"] for item in events.json()["items"]]
    assert "task_created" in event_types
    assert "accepted" in event_types
    assert "task_started" in event_types
    assert "thinking" in event_types

    detail = client.get(f"/api/ai/tasks/{task_id}")
    assert detail.status_code == 200
    assert detail.json()["id"] == task_id

    flow = client.get(f"/api/ai/tasks/{task_id}/flow")
    assert flow.status_code == 200, flow.text
    assert flow.json()["task_id"] == task_id
    assert flow.json()["safety_boundary"]["automatic_delivery_eligible"] is False
    report_id = detail.json().get("report_id")
    if report_id:
        report_flow = client.get(f"/api/ai/reports/{report_id}/flow")
        assert report_flow.status_code == 200, report_flow.text
        assert report_flow.json()["task_id"] == task_id


def test_ai_cancel_api_marks_queued_task_cancelled_and_records_event(client, monkeypatch, tmp_path) -> None:
    _install_runtime(monkeypatch, tmp_path)
    created = client.post(
        "/api/ai/tasks",
        json={"kind": "analysis", "profile": "quick", "request": {}, "idempotency_key": "cancel-fixture-1"},
    )
    task_id = created.json()["task"]["id"]

    cancelled = client.post(f"/api/ai/tasks/{task_id}/cancel")
    events = client.get(f"/api/ai/tasks/{task_id}/events")

    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert "task_cancelled" in [item["event_type"] for item in events.json()["items"]]


def test_ai_chat_session_and_stream_are_available_through_api(client, monkeypatch, tmp_path) -> None:
    provider = _install_runtime(monkeypatch, tmp_path)
    chat = client.post(
        "/api/ai/chat",
        json={"message": "解释输入", "context": _context(), "skills": ["deep_research"]},
    )
    assert chat.status_code == 200, chat.text
    assert chat.json()["message"]["content"] == "fixture chat answer"
    assert chat.json()["session"]["skills"] == ["deep_research"]
    session_id = chat.json()["session"]["id"]
    assert any("2026-08-14T07:00:00Z" in message["content"] for message in provider.calls[-1] if message["role"] == "system")

    streamed = client.post(
        "/api/ai/chat/stream",
        json={"session_id": session_id, "message": "再次解释", "context": _context(), "skills": ["deep_research"]},
    )
    assert streamed.status_code == 200, streamed.text
    assert "data:" in streamed.text
    assert '"type": "done"' in streamed.text

    stored = client.get(f"/api/ai/chat/sessions/{session_id}")
    assert stored.status_code == 200
    assert len(stored.json()["messages"]) == 4


def test_ai_skill_endpoint_returns_a_task_without_executing_external_provider(client, monkeypatch, tmp_path) -> None:
    _install_runtime(monkeypatch, tmp_path)
    response = client.post("/api/ai/screening", json={"query": "close above moving average", "context": _context()})

    assert response.status_code == 200, response.text
    assert response.json()["execution"] == "inline"
    assert response.json()["task"]["status"] in {"completed", "degraded"}
