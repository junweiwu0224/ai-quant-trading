from __future__ import annotations

import builtins
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from ai_runtime import AIRuntime
from ai_runtime.context import build_analysis_context
from ai_runtime.models import (
    GenerationError,
    GenerationErrorCode,
    GenerationResult,
    ProviderChannel,
)
from ai_runtime.providers import LiteLLMProvider, ProviderRouter
from ai_runtime.repository import AIRuntimeRepository
from ai_runtime.run_flow import build_task_run_flow_snapshot
from ai_runtime.models import project_dsa_blocks


def _context_payload() -> dict[str, Any]:
    return {
        "market": "CN",
        "instrument": "600000",
        "as_of": "2026-08-14T07:00:00Z",
        "blocks": {
            "quote": {"status": "available", "close": 12.34, "volume": 1000},
            "factors": {"status": "available", "momentum_20d": 0.61},
        },
        "evidence": [{"source": "fixture", "claim": "frozen input"}],
        "quality_status": "available",
        "source": "test_snapshot",
    }


class ScriptedProviderRouter:
    """A deterministic provider seam; it never reaches an external LLM."""

    def __init__(
        self,
        *,
        forbidden_field: str = "",
        on_generate: Any | None = None,
    ) -> None:
        self.forbidden_field = forbidden_field
        self.on_generate = on_generate
        self.calls: list[list[dict[str, str]]] = []
        self._lock = threading.Lock()

    def public_status(self) -> list[dict[str, Any]]:
        return []

    def generate(self, messages: list[dict[str, str]], *, json_mode: bool = True) -> GenerationResult:
        with self._lock:
            self.calls.append(messages)
        if self.on_generate is not None:
            self.on_generate(messages)

        if not json_mode:
            return GenerationResult(text="fixture chat answer", provider="fixture", model="fixture-model")

        system = messages[0]["content"]
        role = next(
            (
                candidate
                for candidate in ("technical", "intelligence", "quant", "risk", "decision")
                if f"你是 {candidate} 研究 Agent" in system
            ),
            "technical",
        )
        if "研究 Agent" in system:
            payload: dict[str, Any] = {
                "role": role,
                "conclusion": f"{role} fixture conclusion",
                "evidence": ["fixture evidence"],
                "risks": ["fixture risk"],
                "unknowns": ["fixture unknown"],
                "confidence": 0.8,
            }
            if self.forbidden_field:
                payload[self.forbidden_field] = "buy"
        elif "报告编辑" in system:
            payload = {
                "summary": "fixture synthesis",
                "common_evidence": ["fixture evidence"],
                "disagreements": [],
                "risks": ["fixture risk"],
                "next_checks": ["fixture check"],
            }
        elif "深度研究" in system or "研究问题" in system:
            payload = {
                "summary": "fixture research",
                "findings": ["fixture finding"],
                "sources": ["fixture source"],
                "unknowns": ["fixture unknown"],
                "next_checks": ["fixture check"],
            }
        else:
            payload = {
                "summary": "fixture artifact",
                "evidence": ["fixture evidence"],
                "risks": ["fixture risk"],
                "unknowns": ["fixture unknown"],
                "next_checks": ["fixture check"],
            }
        return GenerationResult(text=json.dumps(payload, ensure_ascii=False), provider="fixture", model="fixture-model")


def _runtime(tmp_path, router: Any | None = None) -> AIRuntime:
    return AIRuntime(
        AIRuntimeRepository(tmp_path / "ai-runtime.db"),
        provider_router=router if router is not None else ProviderRouter([]),
    )


def test_memory_repository_is_safe_across_worker_threads() -> None:
    repository = AIRuntimeRepository(":memory:")
    try:
        session = repository.create_session("workspace-1", title="thread fixture")

        def add_message(index: int) -> dict[str, Any]:
            return repository.add_message(session["id"], "workspace-1", "user", f"message-{index}")

        with ThreadPoolExecutor(max_workers=4) as executor:
            messages = list(executor.map(add_message, range(8)))

        stored = repository.get_session(session["id"], "workspace-1")
        assert stored is not None
        assert {item["content"] for item in stored["messages"]} == {f"message-{index}" for index in range(8)}
        assert len(messages) == 8
    finally:
        repository.close()


def test_analysis_context_hash_is_canonical_and_changes_when_input_changes() -> None:
    payload = _context_payload()
    reordered = {
        "source": payload["source"],
        "evidence": payload["evidence"],
        "blocks": payload["blocks"],
        "as_of": payload["as_of"],
        "instrument": payload["instrument"],
        "market": payload["market"],
        "quality_status": payload["quality_status"],
    }

    first = build_analysis_context(payload)
    second = build_analysis_context(reordered)
    changed = build_analysis_context({**payload, "blocks": {**payload["blocks"], "quote": {"status": "available", "close": 12.35}}})

    assert first.context_hash == second.context_hash
    assert len(first.context_hash) == 64
    assert first.context_hash != changed.context_hash
    with pytest.raises((TypeError, ValueError)):
        first.market = "US"  # type: ignore[misc]


def test_provider_router_falls_back_in_priority_order(monkeypatch: pytest.MonkeyPatch) -> None:
    channels = [
        ProviderChannel(id="primary", name="Primary", priority=1, model="primary-model", secret_ref="env://PRIMARY_KEY"),
        ProviderChannel(id="fallback", name="Fallback", priority=2, model="fallback-model", secret_ref="env://FALLBACK_KEY"),
    ]

    class FailingAdapter:
        def __init__(self, channel: ProviderChannel) -> None:
            self.channel = channel

        def generate(self, _messages, *, json_mode: bool = True) -> GenerationResult:
            del json_mode
            raise GenerationError(GenerationErrorCode.HTTP_ERROR, "fixture primary failure", provider=self.channel.id)

    class WorkingAdapter:
        def __init__(self, channel: ProviderChannel) -> None:
            self.channel = channel

        def generate(self, _messages, *, json_mode: bool = True) -> GenerationResult:
            del json_mode
            return GenerationResult(text="fallback output", provider=self.channel.id, model=self.channel.model)

    monkeypatch.setattr(
        "ai_runtime.providers.adapter_for",
        lambda channel: FailingAdapter(channel) if channel.id == "primary" else WorkingAdapter(channel),
    )
    result = ProviderRouter(channels).generate([{"role": "user", "content": "fixture"}], json_mode=False)

    assert result.provider == "fallback"
    assert result.text == "fallback output"


def test_litellm_without_model_is_reported_as_unconfigured() -> None:
    channel = ProviderChannel(id="litellm", name="LiteLLM", protocol="litellm")

    with pytest.raises(GenerationError) as raised:
        LiteLLMProvider(channel).generate([])

    assert raised.value.code is GenerationErrorCode.BACKEND_NOT_CONFIGURED


def test_litellm_missing_optional_dependency_is_reported_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__

    def deny_litellm(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "litellm":
            raise ImportError("fixture: LiteLLM is not installed")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", deny_litellm)
    channel = ProviderChannel(id="litellm", name="LiteLLM", protocol="litellm", model="openai/gpt-4o-mini")

    with pytest.raises(GenerationError) as raised:
        LiteLLMProvider(channel).generate([])

    assert raised.value.code is GenerationErrorCode.BACKEND_NOT_INSTALLED


def test_runtime_with_no_provider_persists_an_unavailable_report(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    task, created = runtime.submit_task(
        workspace_id="workspace-1",
        kind="analysis",
        profile="quick",
        context=_context_payload(),
    )

    result = runtime.run_task(task["id"], workspace_id="workspace-1")
    report = runtime.reports("workspace-1")[0]

    assert created is True
    assert result["status"] == "degraded"
    assert report["body"]["status"] == "unavailable"
    assert report["body"]["opinions"] == []
    assert report["body"]["diagnostics"]


def test_task_submission_is_idempotent_and_emits_one_acceptance(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    first, first_created = runtime.submit_task(
        workspace_id="workspace-1",
        kind="research",
        profile="research",
        request={"query": "fixture query"},
        context=_context_payload(),
        idempotency_key="research-fixture-1",
    )
    replay, replay_created = runtime.submit_task(
        workspace_id="workspace-1",
        kind="research",
        profile="research",
        request={"query": "fixture query"},
        context=_context_payload(),
        idempotency_key="research-fixture-1",
    )

    assert first_created is True
    assert replay_created is False
    assert replay["id"] == first["id"]
    accepted = [event for event in runtime.events(first["id"], "workspace-1") if event["event_type"] == "accepted"]
    assert len(accepted) == 1


def test_inline_run_emits_task_started_before_processing(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    task, _ = runtime.submit_task(workspace_id="workspace-1", kind="analysis", profile="quick")

    runtime.run_task(task["id"], workspace_id="workspace-1")
    event_types = [event["event_type"] for event in runtime.events(task["id"], "workspace-1")]

    assert "task_created" in event_types
    assert "accepted" in event_types
    assert "task_started" in event_types
    assert event_types.index("task_started") < event_types.index("thinking")


@pytest.mark.parametrize("forbidden_field", ["action", "order"])
def test_role_artifact_rejects_executable_fields(tmp_path, forbidden_field: str) -> None:
    runtime = _runtime(tmp_path, ScriptedProviderRouter(forbidden_field=forbidden_field))
    task, _ = runtime.submit_task(
        workspace_id="workspace-1",
        kind="analysis",
        profile="quick",
        context=_context_payload(),
    )

    result = runtime.run_task(task["id"], workspace_id="workspace-1")
    report = runtime.reports("workspace-1")[0]

    assert result["status"] == "degraded"
    assert report["body"]["status"] == "unavailable"
    assert report["body"]["opinions"] == []
    assert all(item["code"] == GenerationErrorCode.SCHEMA_VALIDATION_FAILED.value for item in report["body"]["diagnostics"])


def test_cancellation_does_not_publish_a_final_report(tmp_path) -> None:
    cancelled = threading.Event()
    cancel_lock = threading.Lock()
    runtime: AIRuntime

    def cancel_once(_messages: list[dict[str, str]]) -> None:
        with cancel_lock:
            if cancelled.is_set():
                return
            cancelled.set()
        runtime.cancel_task(task["id"], "workspace-1")

    router = ScriptedProviderRouter(on_generate=cancel_once)
    runtime = _runtime(tmp_path, router)
    task, _ = runtime.submit_task(
        workspace_id="workspace-1",
        kind="analysis",
        profile="quick",
        context=_context_payload(),
    )

    result = runtime.run_task(task["id"], workspace_id="workspace-1")

    assert result["status"] == "cancelled"
    assert runtime.reports("workspace-1") == []
    assert any(event["event_type"] == "cancelled" for event in runtime.events(task["id"], "workspace-1"))


def test_chat_injects_frozen_context_and_updates_existing_session_skills(tmp_path) -> None:
    router = ScriptedProviderRouter()
    runtime = _runtime(tmp_path, router)
    session = runtime.create_session("workspace-1", skills=["old_skill"])

    result = runtime.chat(
        workspace_id="workspace-1",
        session_id=session["id"],
        message="解释这个冻结快照",
        context=_context_payload(),
        skills=["deep_research"],
    )

    stored = runtime.session(session["id"], "workspace-1")
    assert result["message"]["role"] == "assistant"
    assert stored is not None
    assert stored["skills"] == ["deep_research"]
    assert len(stored["messages"]) == 2
    sent = router.calls[-1]
    assert "deep_research" in sent[0]["content"]
    assert any(message["role"] == "system" and "2026-08-14T07:00:00Z" in message["content"] for message in sent)
    assert any(message["role"] == "system" and "只使用用户或系统明确提供的输入" in message["content"] for message in sent)


def test_dsa_dashboard_projection_is_nested_safe_and_human_review_only() -> None:
    projected = project_dsa_blocks(
        {
            "dashboard": {
                "core_conclusion": {
                    "one_sentence": "趋势证据偏强，但需要复核数据新鲜度",
                    "position_advice": {"no_position": "等待回踩", "has_position": "观察量能"},
                    "action": "buy",
                },
                "phase_decision": {
                    "immediate_action": "等待下一检查点",
                    "watch_conditions": ["量能确认"],
                },
                "signal_attribution": {
                    "technical_indicators": 40,
                    "news_sentiment": 20,
                    "fundamentals": 20,
                    "market_conditions": 20,
                },
                "unknown_block": {"should_not": "persist"},
            }
        }
    )

    assert set(projected) == {"core_conclusion", "phase_decision", "signal_attribution"}
    assert projected["core_conclusion"]["review_only"] is True
    assert projected["core_conclusion"]["authority"] == "human_review_only"
    assert "action" not in projected["core_conclusion"]
    assert projected["phase_decision"]["immediate_action"] == "等待下一检查点"
    attribution = projected["signal_attribution"]
    assert sum(attribution[field] for field in ("technical_indicators", "news_sentiment", "fundamentals", "market_conditions")) == 100


def test_run_flow_uses_report_instrument_fallback_and_separates_retry_from_fallback() -> None:
    snapshot = build_task_run_flow_snapshot(
        {
            "id": "task-flow-fixture",
            "kind": "analysis",
            "profile": "standard",
            "status": "completed",
            "context_hash": "a" * 64,
            "created_at": "2026-08-14T07:00:00Z",
            "completed_at": "2026-08-14T07:00:02Z",
            "request": {"market": "CN"},
        },
        [
            {
                "event_type": "provider_done",
                "payload": {
                    "stage": "technical",
                    "attempts": [
                        {"attempt": 1, "provider": "primary", "model": "p1", "relation": "initial", "status": "failed", "error_code": "timeout"},
                        {"attempt": 2, "provider": "primary", "model": "p1", "relation": "retry", "retry_index": 1, "status": "failed", "error_code": "timeout"},
                        {"attempt": 3, "provider": "fallback", "model": "p2", "relation": "fallback", "fallback_from": "primary", "fallback_to": "fallback", "status": "success"},
                    ],
                },
                "created_at": "2026-08-14T07:00:01Z",
            }
        ],
        report={"body": {"instrument": "600519", "market": "CN", "status": "partial"}, "created_at": "2026-08-14T07:00:02Z"},
    )

    assert snapshot["instrument"] == "600519"
    assert snapshot["summary"]["retry_count"] == 1
    assert snapshot["summary"]["fallback_count"] == 1
    assert snapshot["summary"]["retry_count"] != snapshot["summary"]["fallback_count"] + 1
    assert any(node["provider"] == "fallback" and node["status"] == "success" for node in snapshot["nodes"])
    assert snapshot["safety_boundary"]["automatic_delivery_eligible"] is False


def test_provider_router_exposes_retry_fallback_history_without_secret_values(monkeypatch) -> None:
    channels = [
        ProviderChannel(id="primary", name="Primary", priority=1, model="p1", secret_ref="env://PRIMARY_KEY", retries=1),
        ProviderChannel(id="fallback", name="Fallback", priority=2, model="p2", secret_ref="env://FALLBACK_KEY"),
    ]
    calls: dict[str, int] = {"primary": 0}

    class FixtureAdapter:
        def __init__(self, channel: ProviderChannel) -> None:
            self.channel = channel

        def generate(self, _messages, *, json_mode: bool = True) -> GenerationResult:
            del json_mode
            if self.channel.id == "primary":
                calls["primary"] += 1
                raise GenerationError(GenerationErrorCode.TIMEOUT, "fixture timeout", provider="primary", retryable=True)
            return GenerationResult(text="fallback", provider="fallback", model="p2")

    monkeypatch.setattr("ai_runtime.providers.adapter_for", FixtureAdapter)
    router = ProviderRouter(channels)
    result = router.generate([{"role": "user", "content": "fixture"}], json_mode=False)

    assert calls["primary"] == 2
    assert result.diagnostics["retry_count"] == 1
    assert result.diagnostics["fallback_count"] == 1
    status = router.public_status()
    primary = next(item for item in status if item["id"] == "primary")
    assert any(item["relation"] == "retry" for item in primary["attempts"])
    assert all("PRIMARY_KEY" not in json.dumps(item) for item in primary["attempts"])
