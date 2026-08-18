"""Deep, provider-neutral AI runtime for research and explanation artifacts.

The runtime deliberately has a small external interface.  It owns task
execution, role orchestration, validation, persistence, and degradation
diagnostics; callers only provide a frozen input snapshot and select a profile.
No method in this module can create or mutate a deterministic decision.
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .context import build_analysis_context, stable_json
from .models import (
    AIReport,
    AnalysisContext,
    DEFAULT_AGENT_ROLES,
    GenerationError,
    GenerationErrorCode,
    GenerationResult,
    RoleOutput,
    SynthesisOutput,
    TaskStatus,
    ROLE_BRIEFS,
    project_dsa_blocks,
)
from .providers import ProviderRouter, default_channel_from_environment, parse_json_payload
from .repository import AIRuntimeRepository


REPORT_PROFILES: dict[str, dict[str, Any]] = {
    "standard": {"roles": DEFAULT_AGENT_ROLES, "synthesis": True},
    "quick": {"roles": ("technical", "risk"), "synthesis": True},
    "research": {"roles": ("technical", "intelligence", "quant", "risk"), "synthesis": True},
    "explain": {"roles": ("quant", "risk", "decision"), "synthesis": True},
}

SKILLS: tuple[dict[str, Any], ...] = (
    {
        "id": "multi_agent_analysis",
        "name": "多角色研究",
        "description": "并行收集技术、情报、量化和风险观点，再生成结构化解释。",
        "kind": "analysis",
        "profiles": ["quick", "standard", "research", "explain"],
    },
    {
        "id": "deep_research",
        "name": "深度研究",
        "description": "围绕一个冻结快照拆分研究问题，输出来源、未知项和后续核验清单。",
        "kind": "research",
        "profiles": ["research"],
    },
    {
        "id": "screening_query",
        "name": "自然语言选股条件",
        "description": "将自然语言转换为可审阅的筛选条件，不直接运行或下单。",
        "kind": "screening",
        "profiles": ["quick"],
    },
    {
        "id": "prediction_interpretation",
        "name": "预测解读",
        "description": "解释预测值和因子贡献，明确样本、口径和数据限制。",
        "kind": "interpretation",
        "profiles": ["explain"],
    },
    {
        "id": "strategy_generation",
        "name": "策略草案",
        "description": "生成可审阅的策略草案或 DSL 建议，必须经过验证才能进入策略工作流。",
        "kind": "strategy",
        "profiles": ["research"],
    },
    {
        "id": "backtest_diagnosis",
        "name": "回测诊断",
        "description": "从既有回测结果识别数据、成本、过拟合和执行风险。",
        "kind": "diagnosis",
        "profiles": ["explain"],
    },
    {
        "id": "report_analysis",
        "name": "研报解读",
        "description": "将用户提供的研报文本整理为观点、证据、风险和待核验问题。",
        "kind": "report_analysis",
        "profiles": ["research"],
    },
)

_SKILL_BY_KIND = {item["kind"]: item for item in SKILLS}

_FORBIDDEN_FIELDS = {
    "action",
    "actions",
    "order",
    "orders",
    "buy",
    "sell",
    "trade",
    "execute",
    "execution",
    "place_order",
}


class TaskCancelled(Exception):
    """Internal control-flow signal for cooperative task cancellation."""


def _assert_no_forbidden_fields(value: Any) -> None:
    """Reject executable-looking fields at every level of an AI artifact."""

    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).strip().lower() in _FORBIDDEN_FIELDS:
                raise GenerationError(
                    GenerationErrorCode.SCHEMA_VALIDATION_FAILED,
                    "AI artifact contains a forbidden execution field",
                    details={"field": str(key)},
                )
            _assert_no_forbidden_fields(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _assert_no_forbidden_fields(child)


class AIRuntime:
    """Own the complete lifecycle of one workspace's AI research tasks."""

    def __init__(
        self,
        repository: AIRuntimeRepository,
        *,
        channels: Iterable[Any] = (),
        provider_router: ProviderRouter | None = None,
        event_sink: Callable[[dict[str, Any]], None] | None = None,
        role_workers: int = 4,
    ) -> None:
        self.repository = repository
        configured = list(channels)
        if not configured:
            configured = [self._channel_from_dict(item) for item in repository.list_channels()]
        if not configured:
            channel = default_channel_from_environment()
            if channel is not None:
                configured = [channel]
        self.router = provider_router or ProviderRouter(configured, runtime_store=repository)
        attach_store = getattr(self.router, "set_runtime_store", None)
        if callable(attach_store):
            attach_store(repository)
        self.event_sink = event_sink
        self.role_workers = max(1, min(int(role_workers or 4), 8))

    @classmethod
    def from_environment(cls, database: str | Path | None = None) -> "AIRuntime":
        if database is None:
            from config.settings import DB_DIR

            database = Path(DB_DIR) / "ai_runtime.db"
        return cls(AIRuntimeRepository(database))

    @staticmethod
    def _channel_from_dict(value: Mapping[str, Any]) -> Any:
        from .models import ProviderChannel

        return ProviderChannel.model_validate(dict(value))

    def refresh_channels(self, workspace_id: str | None = None) -> list[dict[str, Any]]:
        from .models import ProviderChannel

        channels = [ProviderChannel.model_validate(item) for item in self.repository.list_channels(workspace_id or "default")]
        if not channels:
            default = default_channel_from_environment()
            if default is not None:
                channels = [default]
        channel_router = ProviderRouter(channels, runtime_store=self.repository)
        if not workspace_id or workspace_id == "default":
            self.router = channel_router
        return channel_router.public_status()

    def save_channel(self, channel: Any, workspace_id: str = "default") -> list[dict[str, Any]]:
        payload = channel.model_dump(mode="json") if hasattr(channel, "model_dump") else dict(channel)
        self.repository.save_channel(payload, workspace_id=workspace_id)
        return self.refresh_channels(workspace_id)

    def _workspace_router(self, workspace_id: str | None = None):
        if not workspace_id or workspace_id == "default":
            return self.router
        from .models import ProviderChannel
        channels = [ProviderChannel.model_validate(item) for item in self.repository.list_channels(workspace_id)]
        if not channels:
            return self.router
        return ProviderRouter(channels, runtime_store=self.repository)

    def provider_status(self, workspace_id: str | None = None) -> list[dict[str, Any]]:
        try:
            return self._workspace_router(workspace_id).public_status()
        except GenerationError as exc:
            return [{"id": "runtime", "enabled": False, "error": exc.public_dict()}]

    def list_skills(self) -> list[dict[str, Any]]:
        return [dict(item) for item in SKILLS]

    def submit_task(
        self,
        *,
        workspace_id: str,
        kind: str,
        request: Mapping[str, Any] | None = None,
        context: Mapping[str, Any] | None = None,
        profile: str = "standard",
        idempotency_key: str = "",
    ) -> tuple[dict[str, Any], bool]:
        normalized_kind = str(kind or "analysis").strip().lower()
        if normalized_kind not in {"analysis", "research", "chat", "screening", "interpretation", "strategy", "diagnosis", "report_analysis"}:
            raise ValueError(f"unsupported_ai_task_kind:{normalized_kind}")
        normalized_profile = str(profile or "standard").strip().lower()
        if normalized_profile not in REPORT_PROFILES:
            raise ValueError(f"unsupported_ai_profile:{normalized_profile}")
        payload = dict(request or {})
        if context is not None:
            payload["context"] = dict(context)
        context_model = self._context_for_task(normalized_kind, payload)
        task, created = self.repository.create_task(
            workspace_id=str(workspace_id),
            kind=normalized_kind,
            request=payload,
            context_hash=context_model.context_hash if context_model else "",
            profile=normalized_profile,
            schema_version="ai-task.v1",
            idempotency_key=str(idempotency_key or "").strip(),
        )
        if created:
            self._emit(task["id"], "accepted", {"status": task["status"], "kind": normalized_kind, "profile": normalized_profile})
        return task, created

    def process_pending(
        self,
        *,
        owner_id: str,
        limit: int = 4,
        fence_check: Callable[[], None] | None = None,
        heartbeat: Callable[[dict[str, Any]], None] | None = None,
        lease_ttl_seconds: float = 60.0,
    ) -> list[dict[str, Any]]:
        claimed = self.repository.claim_tasks(owner_id, limit=limit, lease_ttl_seconds=lease_ttl_seconds)
        results: list[dict[str, Any]] = []
        for task in claimed:
            if fence_check is not None:
                fence_check()
            token = task.get("lease_token")
            task_heartbeat = (lambda: self.repository.heartbeat_task(task["id"], owner_id=owner_id, lease_token=token, lease_ttl_seconds=lease_ttl_seconds)) if token else None
            results.append(self.run_task(task["id"], workspace_id=task["workspace_id"], owner_id=owner_id, lease_token=token, fence_check=fence_check, heartbeat=task_heartbeat))
        return results

    def run_task(
        self,
        task_id: str,
        *,
        workspace_id: str,
        owner_id: str | None = None,
        lease_token: str | None = None,
        fence_check: Callable[[], None] | None = None,
        heartbeat: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        task = self.repository.get_task(task_id, workspace_id)
        if task is None:
            raise KeyError("ai_task_not_found")
        if task["status"] in {TaskStatus.COMPLETED.value, TaskStatus.DEGRADED.value, TaskStatus.CANCELLED.value, TaskStatus.FAILED.value}:
            return task
        if task["status"] == TaskStatus.QUEUED.value:
            started_task = self.repository.start_task(task_id, owner_id=owner_id)
            task = started_task or self.repository.get_task(task_id, workspace_id) or task
            if task["status"] in {TaskStatus.COMPLETED.value, TaskStatus.DEGRADED.value, TaskStatus.CANCELLED.value, TaskStatus.FAILED.value}:
                return task
        if task.get("cancel_requested") or task["status"] == TaskStatus.CANCEL_REQUESTED.value:
            return self.repository.complete_task(task_id, status=TaskStatus.CANCELLED.value, error={"code": "cancelled"}) or task
        started = time.monotonic()

        def ensure_active() -> None:
            current = self.repository.get_task(task_id, workspace_id)
            if current is None or current.get("cancel_requested") or current.get("status") in {TaskStatus.CANCEL_REQUESTED.value, TaskStatus.CANCELLED.value}:
                raise TaskCancelled()
            if fence_check is not None:
                fence_check()
            if heartbeat is not None and not heartbeat():
                raise RuntimeError("ai worker task lease heartbeat expired")

        self._emit(task_id, "thinking", {"message": "准备冻结研究输入"})
        try:
            ensure_active()
            context = self._context_for_task(task["kind"], task.get("request") or {})
            if task["kind"] == "chat":
                result = self._run_chat_task(task, context, fence_check=ensure_active)
            else:
                result = self._run_artifact_task(task, context, fence_check=ensure_active)
            ensure_active()
            report = result["report"]
            saved = self.repository.save_report_if_active(
                task_id=task_id,
                workspace_id=workspace_id,
                status=report.status,
                body=report.model_dump(mode="json"),
                context_hash=report.context_hash,
                provenance=report.provenance,
                usage=result.get("usage", {}),
                diagnostics=report.diagnostics,
                owner_id=owner_id,
                lease_token=lease_token,
            )
            if saved is None:
                raise TaskCancelled()
            ensure_active()
            terminal = TaskStatus.COMPLETED.value if report.status in {"complete", "partial"} else TaskStatus.DEGRADED.value
            completed = self.repository.complete_task(task_id, status=terminal, report_id=saved.get("id"), error={"diagnostics": report.diagnostics} if report.diagnostics else None, owner_id=owner_id, lease_token=lease_token) or task
            self._emit(task_id, "done", {"status": terminal, "report_id": saved.get("id"), "duration_s": round(time.monotonic() - started, 3)})
            return completed
        except TaskCancelled:
            cancelled = self.repository.complete_task(task_id, status=TaskStatus.CANCELLED.value, error={"code": "cancelled"}) or task
            self._emit(task_id, "cancelled", {"status": TaskStatus.CANCELLED.value})
            return cancelled
        except GenerationError as exc:
            current = self.repository.get_task(task_id, workspace_id)
            if current is None or current.get("cancel_requested") or current.get("status") in {TaskStatus.CANCEL_REQUESTED.value, TaskStatus.CANCELLED.value}:
                cancelled = self.repository.complete_task(task_id, status=TaskStatus.CANCELLED.value, error={"code": "cancelled"}) or task
                self._emit(task_id, "cancelled", {"status": TaskStatus.CANCELLED.value})
                return cancelled
            ensure_active()
            diagnostic = exc.public_dict()
            self._emit(task_id, "error", diagnostic)
            return self.repository.complete_task(task_id, status=TaskStatus.DEGRADED.value, error=diagnostic) or task
        except RuntimeError as exc:
            # A worker fence failure is a control-flow signal.  Persisting an
            # error after losing ownership would let a stale process publish a
            # terminal artifact, so the owner must reclaim/retry the task.
            if owner_id and fence_check is not None and "lease" in str(exc).lower():
                raise
            self._emit(task_id, "error", {"code": "runtime_error", "message": str(exc)[:500]})
            return self.repository.complete_task(task_id, status=TaskStatus.FAILED.value, error={"code": "runtime_error", "message": str(exc)[:500]}) or task
        except Exception as exc:
            self._emit(task_id, "error", {"code": "runtime_error", "message": str(exc)[:500]})
            return self.repository.complete_task(task_id, status=TaskStatus.FAILED.value, error={"code": "runtime_error", "message": str(exc)[:500]}) or task

    def cancel_task(self, task_id: str, workspace_id: str) -> dict[str, Any] | None:
        return self.repository.request_cancel(task_id, workspace_id)

    def task(self, task_id: str, workspace_id: str) -> dict[str, Any] | None:
        return self.repository.get_task(task_id, workspace_id)

    def events(self, task_id: str, workspace_id: str, *, after_id: int = 0, limit: int = 200) -> list[dict[str, Any]]:
        return self.repository.list_events(task_id, workspace_id, after_id=after_id, limit=limit)

    def reports(self, workspace_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        return self.repository.list_reports(workspace_id, limit=limit)

    def report(self, report_id: str, workspace_id: str) -> dict[str, Any] | None:
        return self.repository.get_report(report_id, workspace_id)

    def run_flow_snapshot(self, task_id: str, workspace_id: str) -> dict[str, Any] | None:
        """Return a sanitized, replayable topology for one AI task."""

        task = self.task(task_id, workspace_id)
        if task is None:
            return None
        report = self.report(str(task.get("report_id") or ""), workspace_id) if task.get("report_id") else None
        from .run_flow import build_task_run_flow_snapshot

        return build_task_run_flow_snapshot(task, self.events(task_id, workspace_id, limit=500), report=report)

    def create_session(
        self,
        workspace_id: str,
        *,
        title: str = "新对话",
        skills: list[str] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        return self.repository.create_session(workspace_id, title=title, skills=skills, session_id=session_id)

    def update_session(
        self,
        session_id: str,
        workspace_id: str,
        *,
        title: str | None = None,
        skills: list[str] | None = None,
    ) -> dict[str, Any] | None:
        return self.repository.update_session(session_id, workspace_id, title=title, skills=skills)

    def sessions(self, workspace_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        return self.repository.list_sessions(workspace_id, limit=limit)

    def session(self, session_id: str, workspace_id: str) -> dict[str, Any] | None:
        return self.repository.get_session(session_id, workspace_id)

    def chat(
        self,
        *,
        workspace_id: str,
        session_id: str | None,
        message: str,
        context: Mapping[str, Any] | None = None,
        skills: list[str] | None = None,
        progress: Callable[[dict[str, Any]], None] | None = None,
        active_check: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        text = str(message or "").strip()
        if not text:
            raise ValueError("ai_message_required")
        selected_skills = [str(item) for item in skills] if skills is not None else None
        session = self.repository.create_session(workspace_id, skills=selected_skills or [], session_id=session_id)
        if session_id and selected_skills is not None:
            session = self.repository.update_session(session["id"], workspace_id, skills=selected_skills) or session
        user_message = self.repository.add_message(session["id"], workspace_id, "user", text, {"skills": selected_skills or session.get("skills", [])})
        self._emit(session["id"], "chat_accepted", {"session_id": session["id"], "message_id": user_message["id"]}, sink=progress, persist=False)
        history = self.repository.get_session(session["id"], workspace_id) or {}
        effective_skills = list(selected_skills if selected_skills is not None else history.get("skills") or [])
        frozen_context = None
        if context:
            try:
                frozen_context = build_analysis_context(dict(context))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid_ai_context:{exc}") from exc
        messages = [{"role": "system", "content": self._chat_system_prompt(effective_skills)}]
        if frozen_context is not None:
            messages.append({"role": "system", "content": "以下是调用方提供的冻结研究上下文 JSON，只能引用其中的事实：\n" + stable_json(frozen_context.model_dump(mode="json"))})
        for item in (history.get("messages") or [])[-12:]:
            messages.append({"role": item["role"], "content": item["content"]})
        try:
            if active_check:
                active_check()
            if progress:
                progress({"type": "thinking", "message": "整理上下文和技能"})
            generated = self.router.generate(messages, json_mode=False)
            if active_check:
                active_check()
            answer = generated.text.strip()
            if not answer:
                raise GenerationError(GenerationErrorCode.EMPTY_OUTPUT, "provider returned empty chat output", provider=generated.provider, model=generated.model)
            assistant = self.repository.add_message(session["id"], workspace_id, "assistant", answer, {"provider": generated.provider, "model": generated.model, "usage": generated.usage.model_dump(mode="json")})
            if progress:
                progress({"type": "done", "message_id": assistant["id"], "provider": generated.provider, "model": generated.model})
            return {"session": self.repository.get_session(session["id"], workspace_id), "message": assistant, "diagnostics": generated.diagnostics}
        except GenerationError as exc:
            diagnostic = exc.public_dict()
            failure = self.repository.add_message(session["id"], workspace_id, "assistant", "[AI 暂不可用] 本次回答没有生成。请检查模型配置后重试。", {"error": diagnostic})
            if progress:
                progress({"type": "error", **diagnostic})
            return {"session": self.repository.get_session(session["id"], workspace_id), "message": failure, "error": diagnostic}

    def _run_chat_task(self, task: Mapping[str, Any], context: AnalysisContext | None, *, fence_check: Callable[[], None] | None) -> dict[str, Any]:
        request = dict(task.get("request") or {})
        result = self.chat(
            workspace_id=str(task["workspace_id"]),
            session_id=str(request.get("session_id") or "") or None,
            message=str(request.get("message") or ""),
            context=context.model_dump(mode="json") if context else request.get("context"),
            skills=list(request.get("skills") or []),
            active_check=fence_check,
        )
        if fence_check is not None:
            fence_check()
        report = self._unavailable_report(context, profile="chat", limitations=["chat_result_is_persisted_in_session; no decision effect"], provenance={"session_id": result.get("session", {}).get("id")})
        return {"report": report, "usage": {}}

    def _run_artifact_task(self, task: Mapping[str, Any], context: AnalysisContext | None, *, fence_check: Callable[[], None] | None) -> dict[str, Any]:
        if context is None:
            return {"report": self._unavailable_report(None, profile=str(task.get("profile") or "standard"), limitations=["analysis_context_required"]), "usage": {}}
        kind = str(task.get("kind") or "analysis")
        if kind == "research":
            return self._run_research(task, context, fence_check=fence_check)
        if kind in {"screening", "interpretation", "strategy", "diagnosis", "report_analysis"}:
            return self._run_skill_artifact(task, context, fence_check=fence_check)
        return self._run_multi_agent(task, context, fence_check=fence_check)

    def _run_multi_agent(self, task: Mapping[str, Any], context: AnalysisContext, *, fence_check: Callable[[], None] | None) -> dict[str, Any]:
        profile = REPORT_PROFILES.get(str(task.get("profile") or "standard"), REPORT_PROFILES["standard"])
        role_names = tuple(profile["roles"])
        opinions: list[RoleOutput] = []
        diagnostics: list[dict[str, Any]] = []
        usage: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        self._emit(task["id"], "stage_start", {"stage": "agents", "roles": list(role_names)})
        # Providers are synchronous adapters.  Running the independent role
        # calls concurrently keeps the UI responsive while ordering the final
        # artifact by the stable role list for replay and comparison.
        def execute(role: str) -> tuple[str, RoleOutput | None, dict[str, Any] | None, GenerationResult | None]:
            try:
                generated = self._generate_role(role, context, task)
                payload = parse_json_payload(generated.text)
                if isinstance(payload, Mapping) and isinstance(payload.get("opinion"), Mapping):
                    payload = payload["opinion"]
                _assert_no_forbidden_fields(payload)
                if not isinstance(payload, Mapping):
                    raise GenerationError(GenerationErrorCode.SCHEMA_VALIDATION_FAILED, "role output must be an object", provider=generated.provider, model=generated.model)
                # RoleOutput has extra=forbid, so a model accidentally emitting
                # action/order fields fails closed instead of becoming a trade.
                output = RoleOutput.model_validate(dict(payload))
                if output.role != role:
                    output = output.model_copy(update={"role": role})
                return role, output, None, generated
            except ValidationError as exc:
                return role, None, {"code": GenerationErrorCode.SCHEMA_VALIDATION_FAILED.value, "role": role, "message": "role output schema validation failed", "details": {"errors": exc.errors(include_url=False)}}, None
            except GenerationError as exc:
                return role, None, {**exc.public_dict(), "role": role}, None
            except Exception as exc:
                return role, None, {"code": "role_runtime_error", "role": role, "message": str(exc)[:500]}, None

        with ThreadPoolExecutor(max_workers=min(self.role_workers, max(1, len(role_names)))) as pool:
            completed = list(pool.map(execute, role_names))
        by_role = {role: (opinion, diagnostic, generated) for role, opinion, diagnostic, generated in completed}
        for role in role_names:
            if fence_check is not None:
                fence_check()
            opinion, diagnostic, generated = by_role[role]
            if opinion is not None:
                opinions.append(opinion)
                self._add_usage(usage, generated)
                self._emit(task["id"], "stage_done", {"stage": role, "status": "completed", "provider": generated.provider if generated else "", "model": generated.model if generated else ""})
            else:
                diagnostics.append(diagnostic or {"code": "role_unavailable", "role": role})
                self._emit(task["id"], "stage_done", {"stage": role, "status": "failed", "diagnostic": diagnostic or {}})

        synthesis = None
        dsa_projection: dict[str, Any] = {}
        if opinions and profile["synthesis"]:
            self._emit(task["id"], "generating", {"stage": "synthesis"})
            try:
                generated = self._generate_synthesis(context, opinions, task)
                raw_synthesis = parse_json_payload(generated.text)
                _assert_no_forbidden_fields(raw_synthesis)
                if not isinstance(raw_synthesis, Mapping):
                    raise GenerationError(GenerationErrorCode.SCHEMA_VALIDATION_FAILED, "synthesis output must be an object", provider=generated.provider, model=generated.model)
                dsa_projection = project_dsa_blocks(raw_synthesis)
                synthesis_payload = raw_synthesis.get("synthesis") if isinstance(raw_synthesis.get("synthesis"), Mapping) else {key: value for key, value in raw_synthesis.items() if key != "dashboard"}
                synthesis = SynthesisOutput.model_validate(synthesis_payload)
                self._add_usage(usage, generated)
            except ValidationError as exc:
                diagnostics.append({"code": GenerationErrorCode.SCHEMA_VALIDATION_FAILED.value, "stage": "synthesis", "message": "synthesis schema validation failed", "details": {"errors": exc.errors(include_url=False)}})
            except GenerationError as exc:
                diagnostics.append({**exc.public_dict(), "stage": "synthesis"})

        if not opinions:
            report = self._unavailable_report(context, profile=str(task.get("profile") or "standard"), limitations=["没有任何角色成功生成观点"], diagnostics=diagnostics)
        else:
            if synthesis is None:
                synthesis = self._deterministic_synthesis(opinions)
            status = "complete" if len(opinions) == len(role_names) and not diagnostics else "partial" if len(opinions) == len(role_names) else "degraded"
            report = AIReport(
                profile=str(task.get("profile") or "standard"),
                status=status,
                market=context.market,
                instrument=context.instrument,
                context_hash=context.context_hash,
                quality_status=context.quality_status,
                opinions=opinions,
                synthesis=synthesis,
                limitations=self._limitations(context, diagnostics),
                provenance=self._provenance(usage, opinions),
                diagnostics=diagnostics,
                **dsa_projection,
            )
        self._emit(task["id"], "stage_done", {"stage": "report", "status": report.status, "opinions": len(opinions)})
        return {"report": report, "usage": usage}

    def _run_research(self, task: Mapping[str, Any], context: AnalysisContext, *, fence_check: Callable[[], None] | None) -> dict[str, Any]:
        request = dict(task.get("request") or {})
        query = str(request.get("query") or request.get("question") or "").strip()
        if not query:
            query = f"请研究 {context.instrument} 在 {context.as_of or '当前快照'} 的主要证据与风险"
        sub_questions = [
            f"{query}：技术和量价证据是什么？",
            f"{query}：情报、公告和情绪证据是否完整？",
            f"{query}：量化样本、成本和可复现性有哪些限制？",
            f"{query}：风险、流动性和需要人工核验的事项是什么？",
        ]
        self._emit(task["id"], "research_plan", {"query": query, "sub_questions": sub_questions})
        payload = {"query": query, "sub_questions": sub_questions, "context": context.model_dump(mode="json"), "requested_sources": request.get("sources") or []}
        try:
            if fence_check is not None:
                fence_check()
            generated = self._generate_json("deep_research", "将研究问题拆解并输出 JSON，字段必须为 summary, findings, sources, unknowns, next_checks；不得返回 action/order/buy/sell。", payload, task_id=str(task["id"]))
            raw = parse_json_payload(generated.text)
            _assert_no_forbidden_fields(raw)
            if not isinstance(raw, Mapping):
                raise GenerationError(GenerationErrorCode.SCHEMA_VALIDATION_FAILED, "research output must be an object", provider=generated.provider, model=generated.model)
            findings = raw.get("findings") if isinstance(raw.get("findings"), list) else []
            sources = raw.get("sources") if isinstance(raw.get("sources"), list) else []
            unknowns = raw.get("unknowns") if isinstance(raw.get("unknowns"), list) else []
            next_checks = raw.get("next_checks") if isinstance(raw.get("next_checks"), list) else []
            dsa_projection = project_dsa_blocks(raw)
            report = AIReport(
                profile="research",
                status="complete",
                market=context.market,
                instrument=context.instrument,
                context_hash=context.context_hash,
                quality_status=context.quality_status,
                synthesis=SynthesisOutput(summary=str(raw.get("summary") or ""), common_evidence=[str(item) for item in findings[:20]], disagreements=[], risks=[str(item) for item in unknowns[:20]], next_checks=[str(item) for item in next_checks[:20]]),
                limitations=self._limitations(context, []),
                provenance={"provider": generated.provider, "model": generated.model, "sources": sources[:50], "query": query, "sub_questions": sub_questions},
                **dsa_projection,
            )
            self._emit(task["id"], "research_done", {"findings": len(findings), "sources": len(sources)})
            return {"report": report, "usage": generated.usage.model_dump(mode="json")}
        except (GenerationError, ValidationError) as exc:
            diagnostic = exc.public_dict() if isinstance(exc, GenerationError) else {"code": GenerationErrorCode.SCHEMA_VALIDATION_FAILED.value, "message": "research output schema validation failed"}
            report = self._unavailable_report(context, profile="research", limitations=["深度研究没有生成完整报告", "来源必须由调用方或工具显式提供，Runtime 不隐藏抓取数据"], diagnostics=[diagnostic], provenance={"query": query, "sub_questions": sub_questions})
            return {"report": report, "usage": {}}

    def _run_skill_artifact(self, task: Mapping[str, Any], context: AnalysisContext, *, fence_check: Callable[[], None] | None) -> dict[str, Any]:
        kind = str(task.get("kind") or "analysis")
        skill = _SKILL_BY_KIND.get(kind, {"name": kind})
        request = dict(task.get("request") or {})
        self._emit(task["id"], "tool_start", {"skill": skill.get("id", kind), "kind": kind})
        prompt = self._skill_prompt(kind)
        payload = {"request": request, "context": context.model_dump(mode="json"), "contract": "research_artifact_only"}
        try:
            if fence_check is not None:
                fence_check()
            generated = self._generate_json(skill.get("id", kind), prompt, payload, task_id=str(task["id"]))
            raw = parse_json_payload(generated.text)
            _assert_no_forbidden_fields(raw)
            summary = str(raw.get("summary") or raw.get("interpretation") or raw.get("diagnosis") or raw.get("content") or "").strip() if isinstance(raw, Mapping) else ""
            if not summary:
                raise GenerationError(GenerationErrorCode.SCHEMA_VALIDATION_FAILED, "AI artifact summary is empty", provider=generated.provider, model=generated.model)
            evidence = raw.get("evidence") if isinstance(raw, Mapping) and isinstance(raw.get("evidence"), list) else []
            risks = raw.get("risks") if isinstance(raw, Mapping) and isinstance(raw.get("risks"), list) else []
            unknowns = raw.get("unknowns") if isinstance(raw, Mapping) and isinstance(raw.get("unknowns"), list) else []
            dsa_projection = project_dsa_blocks(raw if isinstance(raw, Mapping) else {})
            report = AIReport(
                profile=str(task.get("profile") or "explain"),
                status="complete",
                market=context.market,
                instrument=context.instrument,
                context_hash=context.context_hash,
                quality_status=context.quality_status,
                synthesis=SynthesisOutput(summary=summary, common_evidence=[str(item) for item in evidence[:20]], disagreements=[], risks=[str(item) for item in risks[:20]], next_checks=[str(item) for item in unknowns[:20]]),
                limitations=self._limitations(context, []),
                provenance={"skill": skill.get("id", kind), "provider": generated.provider, "model": generated.model, "artifact": dict(raw) if isinstance(raw, Mapping) else {}},
                **dsa_projection,
            )
            self._emit(task["id"], "tool_done", {"skill": skill.get("id", kind), "status": "completed"})
            return {"report": report, "usage": generated.usage.model_dump(mode="json")}
        except GenerationError as exc:
            diagnostic = exc.public_dict()
            self._emit(task["id"], "tool_done", {"skill": skill.get("id", kind), "status": "failed", "diagnostic": diagnostic})
            return {"report": self._unavailable_report(context, profile=str(task.get("profile") or "explain"), limitations=[f"技能 {skill.get('name', kind)} 未生成完整 artifact"], diagnostics=[diagnostic]), "usage": {}}

    def _generate_role(self, role: str, context: AnalysisContext, task: Mapping[str, Any]) -> GenerationResult:
        prompt = f"你是 {role} 研究 Agent。{ROLE_BRIEFS.get(role, '')} 只使用冻结上下文。输出严格 JSON，字段 role, conclusion, evidence, risks, unknowns, confidence。禁止 action, order, buy, sell。"
        payload = {"role": role, "task": task.get("request") or {}, "context": context.model_dump(mode="json")}
        return self._generate_json(role, prompt, payload, task_id=str(task.get("id") or ""))

    def _generate_synthesis(self, context: AnalysisContext, opinions: list[RoleOutput], task: Mapping[str, Any]) -> GenerationResult:
        prompt = "你是研究报告编辑。综合多个角色观点，输出严格 JSON：summary, common_evidence, disagreements, risks, next_checks；可选 dashboard 区块包括 core_conclusion, data_perspective, intelligence, battle_plan, phase_decision, signal_attribution, agent_disagreement_explanation。dashboard 只供人工复核，stop_loss/take_profit/immediate_action 等不得成为执行字段。不得输出 action/order/buy/sell，也不得创造输入中没有的事实。"
        payload = {"task": task.get("request") or {}, "context": context.model_dump(mode="json"), "opinions": [item.model_dump(mode="json") for item in opinions]}
        return self._generate_json("synthesis", prompt, payload, task_id=str(task.get("id") or ""))

    def _generate_json(self, stage: str, system_prompt: str, payload: Mapping[str, Any], *, task_id: str = "") -> GenerationResult:
        self._emit(task_id, "provider_start", {"stage": stage})
        try:
            result = self.router.generate([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": stable_json(payload)},
            ], json_mode=True)
        except GenerationError as exc:
            self._emit(task_id, "provider_error", {"stage": stage, "diagnostic": exc.public_dict()})
            raise
        self._emit(task_id, "provider_done", {
            "stage": stage,
            "provider": result.provider,
            "model": result.model,
            "attempts": result.diagnostics.get("attempts", []) if isinstance(result.diagnostics, Mapping) else [],
            "fallback_used": result.diagnostics.get("fallback_used", False) if isinstance(result.diagnostics, Mapping) else False,
        })
        return result

    def _context_for_task(self, kind: str, request: Mapping[str, Any]) -> AnalysisContext | None:
        raw = request.get("context")
        if not isinstance(raw, Mapping):
            return None
        if not (raw.get("instrument") or raw.get("symbol")):
            if kind in {"research", "screening", "interpretation", "strategy", "diagnosis", "report_analysis"}:
                raw = {**dict(raw), "instrument": "UNSCOPED"}
            else:
                return None
        return build_analysis_context(raw, market=str(raw.get("market") or "CN"), instrument=str(raw.get("instrument") or raw.get("symbol") or ""))

    def _unavailable_report(
        self,
        context: AnalysisContext | None,
        *,
        profile: str,
        limitations: list[str],
        diagnostics: list[dict[str, Any]] | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> AIReport:
        if context is None:
            market, instrument, context_hash, quality = "UNKNOWN", "UNKNOWN", "0" * 64, "missing"
        else:
            market, instrument, context_hash, quality = context.market, context.instrument, context.context_hash, context.quality_status
        return AIReport(
            profile=profile,
            status="unavailable",
            market=market,
            instrument=instrument,
            context_hash=context_hash,
            quality_status=quality,
            limitations=list(limitations),
            provenance=dict(provenance or {}),
            diagnostics=list(diagnostics or []),
        )

    @staticmethod
    def _deterministic_synthesis(opinions: list[RoleOutput]) -> SynthesisOutput:
        common: list[str] = []
        risks: list[str] = []
        unknowns: list[str] = []
        for opinion in opinions:
            common.extend(opinion.evidence[:4])
            risks.extend(opinion.risks[:4])
            unknowns.extend(opinion.unknowns[:4])
        return SynthesisOutput(
            summary="；".join(f"{item.role}: {item.conclusion}" for item in opinions)[:6000],
            common_evidence=list(dict.fromkeys(common))[:20],
            disagreements=[f"不同角色观点需要人工复核：{item.role}" for item in opinions if item.confidence is not None and item.confidence < 0.5][:20],
            risks=list(dict.fromkeys(risks))[:20],
            next_checks=list(dict.fromkeys(unknowns))[:20],
        )

    @staticmethod
    def _limitations(context: AnalysisContext, diagnostics: list[dict[str, Any]]) -> list[str]:
        result = ["AI 输出是研究说明，不是交易指令；不会改变确定性决策或自动推送资格。"]
        if context.quality_status != "available":
            result.append(f"输入快照质量为 {context.quality_status}，结论不可视为完整覆盖。")
        if diagnostics:
            result.append("部分角色或模型调用失败，报告已降级。")
        return result

    @staticmethod
    def _provenance(usage: Mapping[str, Any], opinions: list[RoleOutput]) -> dict[str, Any]:
        return {"roles": [item.role for item in opinions], "usage": dict(usage), "deterministic_input": True}

    @staticmethod
    def _add_usage(target: dict[str, int], generated: GenerationResult | None) -> None:
        if generated is None:
            return
        usage = generated.usage.model_dump(mode="json") if hasattr(generated.usage, "model_dump") else dict(generated.usage or {})
        for key in target:
            target[key] += int(usage.get(key) or 0)

    @staticmethod
    def _skill_prompt(kind: str) -> str:
        return {
            "screening": "把用户的自然语言筛选要求转换为严格 JSON，字段 summary, filters, assumptions, unknowns。filters 只能描述条件，不执行筛选，不返回 action。",
            "interpretation": "解释用户提供的预测和因子结果，严格 JSON 字段 summary, evidence, risks, unknowns, next_checks；不创造预测值。",
            "strategy": "生成可审阅的策略草案，严格 JSON 字段 summary, rules, assumptions, risks, validation_plan；不得输出可直接执行的订单或 action。",
            "diagnosis": "诊断给定回测，严格 JSON 字段 summary, evidence, risks, unknowns, next_checks；不伪造指标。",
            "report_analysis": "解读用户提供的研报，严格 JSON 字段 summary, evidence, risks, unknowns, next_checks；不把评级改写成交易指令。",
        }.get(kind, "输出研究 artifact 的严格 JSON，字段 summary, evidence, risks, unknowns, next_checks；不得输出 action。")

    @staticmethod
    def _chat_system_prompt(skills: list[str]) -> str:
        selected = ", ".join(skills) if skills else "general_quant_research"
        return f"你是 AI Quant 研究助手。当前技能：{selected}。回答必须区分事实、推断和未知；只使用用户或系统明确提供的输入；不要声称已执行交易、推送或获取未提供的数据。AI 输出仅用于研究和解释，不得改变确定性决策。"

    def _emit(self, task_id: str, event_type: str, payload: dict[str, Any], *, sink: Callable[[dict[str, Any]], None] | None = None, persist: bool = True) -> None:
        event = {"task_id": task_id, "event_type": event_type, "payload": payload, "created_at": time.time()}
        if persist and task_id and len(task_id) == 32:
            try:
                self.repository.append_event(task_id, event_type, payload)
            except Exception:
                pass
        callback = sink or self.event_sink
        if callback is not None:
            try:
                callback(event)
            except Exception:
                pass
