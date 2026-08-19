from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ai_runtime.models import GenerationError, GenerationErrorCode, ProviderChannel
from ai_runtime.providers import PiAgentProvider
from engine.ai_worker import PiAgentWorker, pi_agent_worker_enabled


def test_pi_agent_provider_runs_without_tools_or_project_context(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0, stdout='{"summary":"fixture"}', stderr="")

    monkeypatch.setattr("ai_runtime.providers.subprocess.run", fake_run)
    monkeypatch.setenv("BROKER_TOKEN", "must-not-leak")
    monkeypatch.setenv("OPENAI_API_KEY", "allowed-for-pi")
    provider = PiAgentProvider(
        ProviderChannel(
            id="pi-agent",
            name="Pi Agent",
            protocol="pi_agent",
            model="openai/gpt-4o-mini",
            command=["pi"],
        )
    )

    result = provider.generate([{"role": "system", "content": "return JSON"}], json_mode=True)

    command = captured["command"]
    assert isinstance(command, list)
    assert {"--print", "--no-session", "--no-tools", "--no-extensions", "--no-skills", "--no-prompt-templates", "--no-context-files"} <= set(command)
    assert "--model" in command
    assert result.backend == "pi_agent"
    assert captured["cwd"] != str(Path.cwd())
    environment = captured["env"]
    assert isinstance(environment, dict)
    assert environment["OPENAI_API_KEY"] == "allowed-for-pi"
    assert "BROKER_TOKEN" not in environment
    assert environment["PI_OFFLINE"] == "1"


def test_pi_agent_provider_normalizes_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("pi", 90)

    monkeypatch.setattr("ai_runtime.providers.subprocess.run", fake_run)
    provider = PiAgentProvider(ProviderChannel(id="pi-agent", name="Pi Agent", protocol="pi_agent", command=["pi"]))

    with pytest.raises(GenerationError) as raised:
        provider.generate([{"role": "user", "content": "fixture"}])

    assert raised.value.code is GenerationErrorCode.TIMEOUT


def test_pi_agent_worker_forces_the_pi_router(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("config.settings.DB_DIR", tmp_path)
    monkeypatch.setenv("PI_AGENT_COMMAND", "pi")
    worker = PiAgentWorker.from_environment()
    try:
        assert worker.runtime.force_default_router is True
        assert worker.runtime.provider_status("another-workspace")[0]["protocol"] == "pi_agent"
    finally:
        worker.close()


def test_pi_agent_worker_requires_explicit_enable_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PI_AGENT_WORKER_ENABLED", raising=False)
    assert pi_agent_worker_enabled() is False

    monkeypatch.setenv("PI_AGENT_WORKER_ENABLED", "true")
    assert pi_agent_worker_enabled() is True
    monkeypatch.setenv("PI_AGENT_WORKER_ENABLED", "false")
    assert pi_agent_worker_enabled() is False
