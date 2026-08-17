"""Provider adapters and structured-generation utilities."""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from collections.abc import Iterable, Mapping
from typing import Any, Protocol

import httpx

from .models import (
    GenerationError,
    GenerationErrorCode,
    GenerationResult,
    GenerationUsage,
    ProviderChannel,
)


_ENV_REF = re.compile(r"^env://([A-Za-z_][A-Za-z0-9_]*)$")


def resolve_secret_ref(secret_ref: str) -> str:
    """Resolve only an env reference; raw credentials are never accepted."""

    value = str(secret_ref or "").strip()
    if not value:
        return ""
    match = _ENV_REF.fullmatch(value)
    if not match:
        raise GenerationError(GenerationErrorCode.UNSAFE_CONFIG, "secret_ref must use env://NAME", details={"field": "secret_ref"})
    return os.getenv(match.group(1), "")


def _redact_error(text: str) -> str:
    return re.sub(r"(?i)(authorization|api[_-]?key|token|secret)\s*[:=]\s*[^\s,;]+", r"\1=[redacted]", text)[:1000]


def parse_json_payload(text: str) -> Any:
    raw = str(text or "").strip()
    if not raw:
        raise GenerationError(GenerationErrorCode.EMPTY_OUTPUT, "provider returned empty output")
    if "```" in raw:
        match = re.search(r"```(?:json)?\s*(.*?)```", raw, flags=re.IGNORECASE | re.DOTALL)
        if match:
            raw = match.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = min((index for index in (raw.find("{"), raw.find("[")) if index >= 0), default=-1)
        end = max(raw.rfind("}"), raw.rfind("]"))
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except json.JSONDecodeError as exc:
                raise GenerationError(GenerationErrorCode.INVALID_JSON, "provider returned invalid JSON", details={"preview": raw[:240]}) from exc
        raise GenerationError(GenerationErrorCode.INVALID_JSON, "provider returned invalid JSON", details={"preview": raw[:240]})


class ProviderAdapter(Protocol):
    channel: ProviderChannel

    def generate(self, messages: list[dict[str, str]], *, json_mode: bool = True) -> GenerationResult: ...


class OpenAICompatibleProvider:
    def __init__(self, channel: ProviderChannel) -> None:
        self.channel = channel

    def _endpoint(self) -> str:
        base = (self.channel.base_url.strip() or "https://api.openai.com/v1").rstrip("/")
        if not base:
            raise GenerationError(GenerationErrorCode.BACKEND_NOT_CONFIGURED, "provider base_url is not configured", provider=self.channel.id)
        if base.endswith("/chat/completions"):
            return base
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    def generate(self, messages: list[dict[str, str]], *, json_mode: bool = True) -> GenerationResult:
        secret = resolve_secret_ref(self.channel.secret_ref)
        if not secret:
            raise GenerationError(
                GenerationErrorCode.BACKEND_NOT_CONFIGURED,
                "provider secret is not available in the environment",
                provider=self.channel.id,
                model=self.channel.model,
                details={"secret_ref": self.channel.secret_ref or None},
            )
        if not self.channel.model:
            raise GenerationError(GenerationErrorCode.BACKEND_NOT_CONFIGURED, "provider model is not configured", provider=self.channel.id)
        headers = {"Authorization": f"Bearer {secret}", "Content-Type": "application/json"}
        body: dict[str, Any] = {"model": self.channel.model, "messages": messages, "temperature": 0.2}
        if json_mode and self.channel.supports_json:
            body["response_format"] = {"type": "json_object"}
        try:
            response = httpx.post(self._endpoint(), headers=headers, json=body, timeout=self.channel.timeout_seconds)
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise GenerationError(GenerationErrorCode.TIMEOUT, "provider request timed out", provider=self.channel.id, model=self.channel.model, retryable=True) from exc
        except httpx.HTTPStatusError as exc:
            raise GenerationError(GenerationErrorCode.HTTP_ERROR, f"provider request failed ({exc.response.status_code})", provider=self.channel.id, model=self.channel.model, retryable=exc.response.status_code >= 500, details={"status": exc.response.status_code}) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise GenerationError(GenerationErrorCode.HTTP_ERROR, _redact_error(str(exc)), provider=self.channel.id, model=self.channel.model, retryable=True) from exc
        choices = payload.get("choices") if isinstance(payload, Mapping) else None
        text = ""
        if isinstance(choices, list) and choices and isinstance(choices[0], Mapping):
            message = choices[0].get("message")
            if isinstance(message, Mapping):
                text = str(message.get("content") or "")
        if not text:
            raise GenerationError(GenerationErrorCode.EMPTY_OUTPUT, "provider response contained no message", provider=self.channel.id, model=self.channel.model)
        raw_usage = payload.get("usage") if isinstance(payload, Mapping) else {}
        usage = GenerationUsage(
            prompt_tokens=raw_usage.get("prompt_tokens") if isinstance(raw_usage, Mapping) else None,
            completion_tokens=raw_usage.get("completion_tokens") if isinstance(raw_usage, Mapping) else None,
            total_tokens=raw_usage.get("total_tokens") if isinstance(raw_usage, Mapping) else None,
        )
        return GenerationResult(text=text, provider=self.channel.id, model=self.channel.model, usage=usage, diagnostics={"endpoint": self._endpoint()})


class LiteLLMProvider:
    """Reference-project compatible provider for multiple vendor protocols.

    LiteLLM is imported lazily so a deployment that only uses an OpenAI
    compatible endpoint does not pay the import cost, while configured
    Gemini/Anthropic/DeepSeek style model names still work when the optional
    dependency is installed.
    """

    def __init__(self, channel: ProviderChannel) -> None:
        self.channel = channel

    def generate(self, messages: list[dict[str, str]], *, json_mode: bool = True) -> GenerationResult:
        if not self.channel.model:
            raise GenerationError(GenerationErrorCode.BACKEND_NOT_CONFIGURED, "provider model is not configured", provider=self.channel.id)
        secret = resolve_secret_ref(self.channel.secret_ref)
        if self.channel.secret_ref and not secret:
            raise GenerationError(
                GenerationErrorCode.BACKEND_NOT_CONFIGURED,
                "provider secret is not available in the environment",
                provider=self.channel.id,
                model=self.channel.model,
                details={"secret_ref": self.channel.secret_ref},
            )
        try:
            import litellm  # type: ignore[import-not-found]
        except ImportError as exc:
            raise GenerationError(
                GenerationErrorCode.BACKEND_NOT_INSTALLED,
                "LiteLLM backend is not installed",
                provider=self.channel.id,
                model=self.channel.model,
            ) from exc

        kwargs: dict[str, Any] = {
            "model": self.channel.model,
            "messages": messages,
            "temperature": 0.2,
            "timeout": self.channel.timeout_seconds,
            "drop_params": True,
        }
        if secret:
            kwargs["api_key"] = secret
        if self.channel.base_url:
            kwargs["api_base"] = self.channel.base_url
        if json_mode and self.channel.supports_json:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            response = litellm.completion(**kwargs)
        except Exception as exc:  # LiteLLM exposes provider-specific exception types.
            text = _redact_error(str(exc))
            retryable = "timeout" in text.lower() or "temporarily" in text.lower() or "429" in text
            code = GenerationErrorCode.TIMEOUT if "timeout" in text.lower() else GenerationErrorCode.HTTP_ERROR
            raise GenerationError(code, text or "LiteLLM request failed", provider=self.channel.id, model=self.channel.model, retryable=retryable) from exc

        choices = response.get("choices") if isinstance(response, Mapping) else getattr(response, "choices", None)
        text = ""
        if isinstance(choices, list) and choices:
            first = choices[0]
            message = first.get("message") if isinstance(first, Mapping) else getattr(first, "message", None)
            content = message.get("content") if isinstance(message, Mapping) else getattr(message, "content", None)
            if isinstance(content, list):
                text = "".join(str(part.get("text") or "") if isinstance(part, Mapping) else str(part) for part in content)
            else:
                text = str(content or "")
        if not text.strip():
            raise GenerationError(GenerationErrorCode.EMPTY_OUTPUT, "provider response contained no message", provider=self.channel.id, model=self.channel.model)
        raw_usage = response.get("usage") if isinstance(response, Mapping) else getattr(response, "usage", None)
        def usage_value(name: str) -> int | None:
            value = raw_usage.get(name) if isinstance(raw_usage, Mapping) else getattr(raw_usage, name, None)
            try:
                return int(value) if value is not None else None
            except (TypeError, ValueError):
                return None
        return GenerationResult(
            text=text.strip(),
            provider=self.channel.id,
            model=self.channel.model,
            backend="litellm",
            usage=GenerationUsage(prompt_tokens=usage_value("prompt_tokens"), completion_tokens=usage_value("completion_tokens"), total_tokens=usage_value("total_tokens")),
            diagnostics={"protocol": "litellm"},
        )


class LocalCliProvider:
    """Optional non-interactive local backend, matching the reference project."""

    def __init__(self, channel: ProviderChannel) -> None:
        self.channel = channel

    def generate(self, messages: list[dict[str, str]], *, json_mode: bool = True) -> GenerationResult:
        if not self.channel.command:
            raise GenerationError(GenerationErrorCode.BACKEND_NOT_CONFIGURED, "local CLI command is not configured", provider=self.channel.id)
        prompt = "\n\n".join(f"{item['role']}: {item['content']}" for item in messages)
        try:
            completed = subprocess.run(
                [*self.channel.command, prompt],
                capture_output=True,
                text=True,
                timeout=self.channel.timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise GenerationError(GenerationErrorCode.COMMAND_NOT_FOUND, "local CLI command was not found", provider=self.channel.id) from exc
        except subprocess.TimeoutExpired as exc:
            raise GenerationError(GenerationErrorCode.TIMEOUT, "local CLI timed out", provider=self.channel.id, retryable=True) from exc
        if completed.returncode != 0:
            raise GenerationError(GenerationErrorCode.NON_ZERO_EXIT, "local CLI failed", provider=self.channel.id, details={"returncode": completed.returncode, "stderr": _redact_error(completed.stderr)})
        text = completed.stdout.strip()
        if not text:
            raise GenerationError(GenerationErrorCode.EMPTY_OUTPUT, "local CLI returned empty output", provider=self.channel.id)
        return GenerationResult(text=text, provider=self.channel.id, model=self.channel.model or self.channel.id, backend="local_cli")


def adapter_for(channel: ProviderChannel) -> ProviderAdapter:
    if channel.protocol == "litellm":
        return LiteLLMProvider(channel)
    if channel.protocol == "local_cli":
        return LocalCliProvider(channel)
    return OpenAICompatibleProvider(channel)


class ProviderRouter:
    """Try channels in priority order and preserve the complete attempt graph."""

    def __init__(self, channels: Iterable[ProviderChannel] = (), *, runtime_store: Any | None = None) -> None:
        self.channels = sorted(list(channels), key=lambda item: (item.priority, item.id))
        self._runtime_store = runtime_store
        self._runtime_state: dict[str, dict[str, Any]] = {}
        self._attempt_history: dict[str, list[dict[str, Any]]] = {}
        self._state_lock = threading.Lock()

    def set_runtime_store(self, runtime_store: Any | None) -> None:
        """Attach the shared runtime projection to an existing test or app router."""

        self._runtime_store = runtime_store

    def _stored_runtime_state(self, provider_id: str) -> dict[str, Any]:
        with self._state_lock:
            local = dict(self._runtime_state.get(provider_id, {}))
        store = self._runtime_store
        getter = getattr(store, "get_provider_runtime", None) if store is not None else None
        if not callable(getter):
            return local
        try:
            persisted = getter(provider_id)
        except Exception:
            # A control-plane read must not make an otherwise inspectable
            # provider disappear when the optional projection is unavailable.
            return local
        if not isinstance(persisted, Mapping):
            return local
        local_checked = float(local.get("last_checked_at") or 0)
        persisted_checked = float(persisted.get("last_checked_at") or 0)
        if persisted_checked >= local_checked:
            return dict(persisted)
        return local

    def _channel_readiness(self, channel: ProviderChannel) -> dict[str, Any]:
        configuration = "ready"
        config_error = ""
        credential = "not_required" if channel.protocol == "local_cli" else "missing"
        try:
            secret_available = bool(resolve_secret_ref(channel.secret_ref)) if channel.secret_ref else channel.protocol == "local_cli"
        except GenerationError as exc:
            secret_available = False
            configuration = "invalid"
            config_error = str(exc)
        if channel.protocol == "local_cli":
            if not channel.command:
                configuration = "missing"
                config_error = "local CLI command is not configured"
        elif not channel.model:
            configuration = "missing"
            config_error = "provider model is not configured"
        elif channel.secret_ref:
            credential = "available" if secret_available else "missing"
        if configuration == "ready" and channel.protocol != "local_cli" and not secret_available:
            credential = "missing"
        runtime = self._stored_runtime_state(channel.id)
        configured = channel.enabled and configuration == "ready" and credential in {"available", "not_required"}
        runtime_status = runtime.get("status", "not_checked")
        runtime_verified = runtime_status == "verified"
        ready = configured and runtime_verified
        if not channel.enabled:
            overall = "disabled"
        elif not configured:
            overall = "needs_configuration"
        elif runtime_status == "failed":
            overall = "configured_recent_failure"
        elif runtime_verified:
            overall = "verified"
        else:
            overall = "configured_unverified"
        return {
            "configuration": configuration,
            "credential": credential,
            "configured": configured,
            "runtime": runtime_status,
            "runtime_verified": runtime_verified,
            "overall": overall,
            "last_error_code": runtime.get("last_error_code"),
            "last_checked_at": runtime.get("last_checked_at"),
            "ready": ready,
            "error": config_error,
        }

    @staticmethod
    def _capabilities(channel: ProviderChannel) -> dict[str, Any]:
        structured = bool(channel.supports_json)
        return {
            "chat": True,
            "structured_json": structured,
            "stream": bool(channel.supports_stream),
            "structured_report": structured,
            "provider_trace": channel.protocol in {"litellm", "openai_compatible"},
            "decision_effect": "none",
            "human_review_only": True,
        }

    def public_status(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for channel in self.channels:
            readiness = self._channel_readiness(channel)
            secret_available = readiness["credential"] in {"available", "not_required"}
            items.append({
                "id": channel.id,
                "name": channel.name,
                "protocol": channel.protocol,
                "base_url": channel.base_url,
                "model": channel.model,
                "secret_ref": channel.secret_ref,
                "secret_available": secret_available,
                "config_error": readiness["error"],
                "enabled": channel.enabled,
                "priority": channel.priority,
                "retries": channel.retries,
                "supports_json": channel.supports_json,
                "supports_stream": channel.supports_stream,
                "capabilities": self._capabilities(channel),
                "readiness": readiness,
                "attempts": self.attempt_history(channel.id),
            })
        return items

    def capability_matrix(self) -> dict[str, Any]:
        return {
            channel.id: {
                "provider": channel.name,
                "protocol": channel.protocol,
                "capabilities": self._capabilities(channel),
                "readiness": self._channel_readiness(channel),
                "attempts": self.attempt_history(channel.id),
            }
            for channel in self.channels
        }

    def _set_runtime_state(self, provider_id: str, *, status: str, error_code: str | None = None) -> None:
        checked_at = time.time()
        with self._state_lock:
            self._runtime_state[provider_id] = {
                "status": status,
                "last_error_code": error_code,
                "last_checked_at": checked_at,
            }
        store = self._runtime_store
        saver = getattr(store, "save_provider_runtime", None) if store is not None else None
        if callable(saver):
            try:
                saver(provider_id, status=status, error_code=error_code, last_checked_at=checked_at)
            except Exception:
                # Provider execution already has a terminal result.  A
                # control-plane projection failure must not turn it into a
                # second provider failure.
                pass

    def _record_attempt_history(self, attempts: Iterable[Mapping[str, Any]]) -> None:
        """Keep a bounded, secret-free attempt trail for the control plane.

        The persisted task event is the durable audit record.  This short
        in-memory trail is deliberately only a provider-operability aid: it
        lets the settings page explain readiness and recent retry/fallback
        behaviour without exposing prompts, response bodies, or credentials.
        """

        now = time.time()
        safe_fields = (
            "attempt",
            "provider",
            "model",
            "relation",
            "retry_index",
            "fallback_from",
            "fallback_to",
            "status",
            "duration_ms",
            "error_code",
            "error_message",
            "retryable",
        )
        with self._state_lock:
            for raw in attempts:
                provider_id = str(raw.get("provider") or "").strip()
                if not provider_id:
                    continue
                item = {key: raw.get(key) for key in safe_fields if raw.get(key) is not None}
                item["recorded_at"] = now
                history = self._attempt_history.setdefault(provider_id, [])
                history.append(item)
                del history[:-12]
                store = self._runtime_store
                appender = getattr(store, "append_provider_attempt", None) if store is not None else None
                if callable(appender):
                    try:
                        appender(provider_id, {**item, "recorded_at": now})
                    except Exception:
                        pass

    def attempt_history(self, provider_id: str = "") -> list[dict[str, Any]]:
        """Return a read-only copy of recent secret-free provider attempts."""

        if provider_id:
            state = self._stored_runtime_state(provider_id)
            persisted = state.get("attempts") if isinstance(state, Mapping) else None
            if isinstance(persisted, list):
                return [dict(item) for item in persisted if isinstance(item, Mapping)]
        with self._state_lock:
            if provider_id:
                return [dict(item) for item in self._attempt_history.get(provider_id, [])]
            return [
                dict(item)
                for items in self._attempt_history.values()
                for item in items
            ]

    def generate(self, messages: list[dict[str, str]], *, json_mode: bool = True) -> GenerationResult:
        channels = [channel for channel in self.channels if channel.enabled]
        if not channels:
            raise GenerationError(GenerationErrorCode.BACKEND_NOT_CONFIGURED, "no enabled AI provider is configured")
        attempts: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        previous_failure: dict[str, Any] | None = None
        for channel_index, channel in enumerate(channels):
            retry_limit = max(0, min(int(channel.retries or 0), 3))
            for retry_index in range(retry_limit + 1):
                started = time.perf_counter()
                relation = "initial" if previous_failure is None else "retry" if previous_failure.get("provider") == channel.id else "fallback"
                attempt: dict[str, Any] = {
                    "attempt": len(attempts) + 1,
                    "provider": channel.id,
                    "model": channel.model,
                    "relation": relation,
                    "retry_index": retry_index,
                    "fallback_from": previous_failure.get("provider") if relation == "fallback" and previous_failure else None,
                    "fallback_to": channel.id if relation == "fallback" else None,
                    "status": "running",
                }
                try:
                    result = adapter_for(channel).generate(messages, json_mode=json_mode)
                    attempt.update({
                        "status": "success",
                        "duration_ms": round((time.perf_counter() - started) * 1000),
                    })
                    attempts.append(attempt)
                    self._record_attempt_history([attempt])
                    self._set_runtime_state(channel.id, status="verified")
                    diagnostics = dict(result.diagnostics or {})
                    diagnostics.update({
                        "attempts": attempts,
                        "selected_provider": result.provider,
                        "selected_model": result.model,
                        "fallback_used": any(item.get("relation") == "fallback" for item in attempts),
                        "fallback_count": sum(1 for item in attempts if item.get("relation") == "fallback"),
                        "retry_count": sum(1 for item in attempts if item.get("relation") == "retry"),
                    })
                    return result.model_copy(update={"diagnostics": diagnostics})
                except GenerationError as exc:
                    public = exc.public_dict()
                    message = _redact_error(str(exc))
                    attempt.update({
                        "status": "failed",
                        "duration_ms": round((time.perf_counter() - started) * 1000),
                        "error_code": exc.code.value,
                        "error_message": message,
                        "retryable": bool(exc.retryable),
                    })
                    attempts.append(attempt)
                    failures.append({
                        "code": exc.code.value,
                        "message": message,
                        "provider": channel.id,
                        "model": channel.model,
                        "retryable": bool(exc.retryable),
                    })
                    self._set_runtime_state(channel.id, status="failed", error_code=exc.code.value)
                    previous_failure = attempt
                    self._record_attempt_history([attempt])
                    if not exc.retryable or retry_index >= retry_limit:
                        break
                except Exception as exc:  # Adapter boundaries must fail closed.
                    normalized = GenerationError(
                        GenerationErrorCode.UNKNOWN,
                        _redact_error(str(exc)) or "provider adapter failed",
                        provider=channel.id,
                        model=channel.model,
                    )
                    attempt.update({
                        "status": "failed",
                        "duration_ms": round((time.perf_counter() - started) * 1000),
                        "error_code": normalized.code.value,
                        "error_message": str(normalized),
                        "retryable": False,
                    })
                    attempts.append(attempt)
                    failures.append({"code": normalized.code.value, "message": str(normalized), "provider": channel.id, "model": channel.model, "retryable": False})
                    self._set_runtime_state(channel.id, status="failed", error_code=normalized.code.value)
                    previous_failure = attempt
                    self._record_attempt_history([attempt])
                    break
        raise GenerationError(
            GenerationErrorCode.UNKNOWN,
            "all configured AI providers failed",
            retryable=True,
            details={
                "providers": failures,
                "attempts": attempts,
                "fallback_count": sum(1 for item in attempts if item.get("relation") == "fallback"),
                "retry_count": sum(1 for item in attempts if item.get("relation") == "retry"),
            },
        )


def default_channel_from_environment() -> ProviderChannel | None:
    protocol = (os.getenv("AI_LLM_PROTOCOL") or "openai_compatible").strip().lower()
    if protocol not in {"openai_compatible", "litellm", "local_cli"}:
        protocol = "openai_compatible"
    base_url = os.getenv("AI_LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or ""
    model = os.getenv("AI_LLM_MODEL") or os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
    secret_ref = os.getenv("AI_LLM_SECRET_REF") or ("env://OPENAI_API_KEY" if os.getenv("OPENAI_API_KEY") else "")
    command = [item for item in (os.getenv("AI_LLM_COMMAND") or "").split() if item]
    if not base_url and not secret_ref and not command:
        return None
    return ProviderChannel(id="env-default", name="Environment provider", protocol=protocol, base_url=base_url, model=model, secret_ref=secret_ref, command=command)
