"""AI Runtime control-plane API.

The router only accepts caller-supplied snapshots and persists research
artifacts.  It never calls the decision store, mutates a portfolio, or grants
notification eligibility.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from ai_runtime import AIRuntime
from ai_runtime.models import ProviderChannel
from config.settings import DB_DIR
from dashboard.session import optional_account
from engine.decision_worker import SQLiteWorkerLease


router = APIRouter()
runtime = AIRuntime.from_environment(Path(DB_DIR) / "ai_runtime.db")


def _account_workspace(account: dict[str, Any] | None) -> str:
    return _workspace_id(account)


def _capability_matrix(workspace_id: str | None = None) -> dict[str, Any]:
    """Read provider capabilities without requiring a test adapter to clone every method."""

    method = getattr(runtime._workspace_router(workspace_id), "capability_matrix", None)
    if callable(method):
        value = method()
        return value if isinstance(value, dict) else {}
    return {}


def _workspace_id(account: dict[str, Any] | None) -> str:
    workspace_id = str((account or {}).get("workspace", {}).get("id") or "").strip()
    if workspace_id:
        return workspace_id
    if os.getenv("APP_ENV", "development").lower() == "test":
        return "default"
    raise HTTPException(status_code=401, detail="请先登录")


class AIContextPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    market: str = "CN"
    instrument: str = ""
    symbol: str = ""
    as_of: str = ""
    blocks: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    quality_status: str = ""
    source: str = "provided_snapshot"


class AITaskPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = "analysis"
    profile: str = "standard"
    request: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    snapshot: dict[str, Any] | None = None
    idempotency_key: str = Field(default="", max_length=200)
    run_now: bool = False


class AIChannelPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    protocol: str = "openai_compatible"
    base_url: str = ""
    model: str = ""
    secret_ref: str = ""
    command: list[str] = Field(default_factory=list)
    enabled: bool = True
    priority: int = 100
    retries: int = Field(default=0, ge=0, le=3)
    timeout_seconds: float = Field(default=45.0, gt=0, le=600)
    supports_json: bool = True
    supports_stream: bool = True


class AIChatPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=20000)
    session_id: str = ""
    context: dict[str, Any] = Field(default_factory=dict)
    skills: list[str] = Field(default_factory=list, max_length=20)


class AISessionPayload(BaseModel):
    title: str = Field(default="新对话", max_length=120)
    skills: list[str] = Field(default_factory=list, max_length=20)
    session_id: str = ""


def _task_context(payload: AITaskPayload) -> dict[str, Any]:
    context = dict(payload.context or {})
    if payload.snapshot:
        context = {**payload.snapshot, **context}
    return context


def _inline_allowed() -> bool:
    configured = os.getenv("AI_INLINE_EXECUTION")
    if configured:
        return configured.strip().lower() in {"1", "true", "yes", "on"}
    return os.getenv("APP_ENV", "development").lower() != "production"


async def _submit(payload: AITaskPayload, workspace_id: str) -> dict[str, Any]:
    task, created = runtime.submit_task(
        workspace_id=workspace_id,
        kind=payload.kind,
        request=payload.request,
        context=_task_context(payload),
        profile=payload.profile,
        idempotency_key=payload.idempotency_key,
    )
    if payload.run_now:
        if not _inline_allowed():
            raise HTTPException(status_code=409, detail="生产环境必须由独立 AI Worker 执行任务")
        task = await asyncio.to_thread(runtime.run_task, task["id"], workspace_id=workspace_id)
    return {"task": task, "created": created, "execution": "inline" if payload.run_now else "worker"}


@router.get("/status")
async def ai_status(account: dict[str, Any] | None = Depends(optional_account)):
    workspace_id = _workspace_id(account)
    lease = SQLiteWorkerLease(Path(DB_DIR) / "worker_leases.db", lease_name="ai-worker")
    try:
        worker = lease.readiness()
    finally:
        lease.close()
    return {
        "success": True,
        "runtime": "ready",
        "executor": "pi_agent_worker",
        "providers": runtime.provider_status(workspace_id),
        "capability_matrix": _capability_matrix(workspace_id),
        "worker": worker,
        "worker_enabled": os.getenv("PI_AGENT_WORKER_ENABLED", os.getenv("AI_WORKER_ENABLED", "false")).lower() in {"1", "true", "yes", "on"},
        "decision_effect": "none",
        "degradation_policy": "failed or unavailable AI output remains visible and cannot qualify automatic delivery",
    }


@router.get("/channels")
async def ai_channels(account: dict[str, Any] | None = Depends(optional_account)):
    workspace_id = _workspace_id(account)
    return {"items": runtime.provider_status(workspace_id), "capability_matrix": _capability_matrix(workspace_id)}


@router.post("/channels")
@router.put("/channels/{channel_id}")
async def save_ai_channel(
    payload: AIChannelPayload,
    channel_id: str = "",
    account: dict[str, Any] | None = Depends(optional_account),
):
    workspace_id = _workspace_id(account)
    if channel_id and channel_id != payload.id:
        raise HTTPException(status_code=400, detail="channel_id_mismatch")
    try:
        channel = ProviderChannel.model_validate(payload.model_dump())
    except ValueError as exc:
        # Pydantic messages can contain submitted values; never echo provider
        # configuration back to the browser, especially secret-like input.
        if "secret_ref" in str(exc):
            detail = "secret_ref must use env://NAME"
        else:
            detail = "AI provider configuration is invalid"
        raise HTTPException(status_code=400, detail=detail) from exc
    return {"items": runtime.save_channel(channel, workspace_id=workspace_id)}


@router.get("/models")
async def ai_models(account: dict[str, Any] | None = Depends(optional_account)):
    del account
    models: list[dict[str, Any]] = []
    for channel in runtime.provider_status():
        if channel.get("model"):
            readiness = channel.get("readiness") if isinstance(channel.get("readiness"), dict) else {}
            models.append({"id": channel["model"], "model": channel["model"], "provider": channel["id"], "available": bool(readiness.get("ready")), "primary": len(models) == 0})
    return {"items": models}


@router.get("/skills")
async def ai_skills(account: dict[str, Any] | None = Depends(optional_account)):
    del account
    return {"items": runtime.list_skills()}


@router.post("/tasks")
async def create_ai_task(payload: AITaskPayload, account: dict[str, Any] | None = Depends(optional_account)):
    workspace_id = _workspace_id(account)
    try:
        return await _submit(payload, workspace_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/tasks")
async def list_ai_tasks(
    status: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=200),
    account: dict[str, Any] | None = Depends(optional_account),
):
    return {"items": runtime.repository.list_tasks(_workspace_id(account), limit=limit, status=status or None)}


@router.get("/tasks/{task_id}")
async def get_ai_task(task_id: str, account: dict[str, Any] | None = Depends(optional_account)):
    task = runtime.task(task_id, _workspace_id(account))
    if task is None:
        raise HTTPException(status_code=404, detail="ai_task_not_found")
    if task.get("report_id"):
        task["report"] = runtime.report(task["report_id"], _workspace_id(account))
    return task


@router.post("/tasks/{task_id}/run")
async def run_ai_task(task_id: str, account: dict[str, Any] | None = Depends(optional_account)):
    if not _inline_allowed():
        raise HTTPException(status_code=409, detail="生产环境必须由独立 AI Worker 执行任务")
    workspace_id = _workspace_id(account)
    if runtime.task(task_id, workspace_id) is None:
        raise HTTPException(status_code=404, detail="ai_task_not_found")
    return await asyncio.to_thread(runtime.run_task, task_id, workspace_id=workspace_id)


@router.post("/tasks/{task_id}/cancel")
@router.delete("/tasks/{task_id}")
async def cancel_ai_task(task_id: str, account: dict[str, Any] | None = Depends(optional_account)):
    task = runtime.cancel_task(task_id, _workspace_id(account))
    if task is None:
        raise HTTPException(status_code=404, detail="ai_task_not_found")
    return task


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


async def _task_event_stream(task_id: str, workspace_id: str, after_id: int = 0) -> AsyncIterator[str]:
    cursor = max(0, int(after_id or 0))
    deadline = asyncio.get_running_loop().time() + 45
    while asyncio.get_running_loop().time() < deadline:
        events = runtime.events(task_id, workspace_id, after_id=cursor)
        for event in events:
            cursor = max(cursor, int(event.get("id") or 0))
            yield _sse(event)
        task = runtime.task(task_id, workspace_id)
        if task is None:
            yield _sse({"event_type": "error", "payload": {"code": "ai_task_not_found"}})
            return
        if task.get("status") in {"completed", "degraded", "failed", "cancelled"}:
            yield _sse({"event_type": "done", "payload": {"status": task["status"], "report_id": task.get("report_id")}})
            return
        await asyncio.sleep(0.25)
    yield _sse({"event_type": "timeout", "payload": {"message": "event stream timeout; task remains queryable"}})


@router.get("/tasks/{task_id}/events")
async def ai_task_events(
    task_id: str,
    stream: bool = False,
    after_id: int = Query(default=0, ge=0),
    account: dict[str, Any] | None = Depends(optional_account),
):
    workspace_id = _workspace_id(account)
    if runtime.task(task_id, workspace_id) is None:
        raise HTTPException(status_code=404, detail="ai_task_not_found")
    if stream:
        return StreamingResponse(_task_event_stream(task_id, workspace_id, after_id), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    return {"items": runtime.events(task_id, workspace_id, after_id=after_id)}


@router.get("/tasks/{task_id}/flow")
async def get_ai_task_flow(task_id: str, account: dict[str, Any] | None = Depends(optional_account)):
    flow = runtime.run_flow_snapshot(task_id, _workspace_id(account))
    if flow is None:
        raise HTTPException(status_code=404, detail="ai_task_not_found")
    return flow


@router.get("/reports")
async def list_ai_reports(limit: int = Query(default=50, ge=1, le=200), account: dict[str, Any] | None = Depends(optional_account)):
    return {"items": runtime.reports(_workspace_id(account), limit=limit)}


@router.get("/reports/{report_id}")
async def get_ai_report(report_id: str, account: dict[str, Any] | None = Depends(optional_account)):
    report = runtime.report(report_id, _workspace_id(account))
    if report is None:
        raise HTTPException(status_code=404, detail="ai_report_not_found")
    return report


@router.get("/reports/{report_id}/flow")
async def get_ai_report_flow(report_id: str, account: dict[str, Any] | None = Depends(optional_account)):
    workspace_id = _workspace_id(account)
    report = runtime.report(report_id, workspace_id)
    if report is None:
        raise HTTPException(status_code=404, detail="ai_report_not_found")
    flow = runtime.run_flow_snapshot(str(report.get("task_id") or ""), workspace_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="ai_task_not_found")
    return flow


@router.get("/chat/sessions")
async def list_ai_sessions(limit: int = Query(default=50, ge=1, le=200), account: dict[str, Any] | None = Depends(optional_account)):
    return {"items": runtime.sessions(_workspace_id(account), limit=limit)}


@router.post("/chat/sessions")
async def create_ai_session(payload: AISessionPayload, account: dict[str, Any] | None = Depends(optional_account)):
    return runtime.create_session(_workspace_id(account), title=payload.title, skills=payload.skills, session_id=payload.session_id or None)


@router.get("/chat/sessions/{session_id}")
async def get_ai_session(session_id: str, account: dict[str, Any] | None = Depends(optional_account)):
    session = runtime.session(session_id, _workspace_id(account))
    if session is None:
        raise HTTPException(status_code=404, detail="ai_session_not_found")
    return session


@router.put("/chat/sessions/{session_id}")
async def update_ai_session(session_id: str, payload: AISessionPayload, account: dict[str, Any] | None = Depends(optional_account)):
    if payload.session_id and payload.session_id != session_id:
        raise HTTPException(status_code=400, detail="session_id_mismatch")
    session = runtime.update_session(session_id, _workspace_id(account), title=payload.title, skills=payload.skills)
    if session is None:
        raise HTTPException(status_code=404, detail="ai_session_not_found")
    return session


@router.delete("/chat/sessions/{session_id}")
async def delete_ai_session(session_id: str, account: dict[str, Any] | None = Depends(optional_account)):
    return {"deleted": runtime.repository.delete_session(session_id, _workspace_id(account))}


@router.post("/chat")
async def ai_chat(payload: AIChatPayload, account: dict[str, Any] | None = Depends(optional_account)):
    try:
        return await asyncio.to_thread(runtime.chat, workspace_id=_workspace_id(account), session_id=payload.session_id or None, message=payload.message, context=payload.context, skills=payload.skills)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/chat/stream")
async def ai_chat_stream(payload: AIChatPayload, account: dict[str, Any] | None = Depends(optional_account)):
    workspace_id = _workspace_id(account)
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def progress(event: dict[str, Any]) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, event)

    task = asyncio.create_task(asyncio.to_thread(runtime.chat, workspace_id=workspace_id, session_id=payload.session_id or None, message=payload.message, context=payload.context, skills=payload.skills, progress=progress))

    async def stream() -> AsyncIterator[str]:
        while True:
            if task.done() and queue.empty():
                try:
                    result = task.result()
                except Exception as exc:
                    yield _sse({"type": "error", "message": str(exc)[:500]})
                else:
                    yield _sse({"type": "done", "result": result})
                return
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            if event is not None:
                yield _sse(event)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no-cache"})


async def _skill_endpoint(kind: str, payload: dict[str, Any], account: dict[str, Any] | None) -> dict[str, Any]:
    context = dict(payload.pop("context", {}) or {})
    task_payload = AITaskPayload(kind=kind, profile="research" if kind in {"strategy", "report_analysis"} else "explain", request=payload, context=context, run_now=True)
    return await _submit(task_payload, _workspace_id(account))


@router.post("/research")
async def ai_research(payload: dict[str, Any], account: dict[str, Any] | None = Depends(optional_account)):
    return await _skill_endpoint("research", payload, account)


@router.post("/screening")
async def ai_screening(payload: dict[str, Any], account: dict[str, Any] | None = Depends(optional_account)):
    return await _skill_endpoint("screening", payload, account)


@router.post("/interpret")
async def ai_interpret(payload: dict[str, Any], account: dict[str, Any] | None = Depends(optional_account)):
    return await _skill_endpoint("interpretation", payload, account)


@router.post("/strategy")
async def ai_strategy(payload: dict[str, Any], account: dict[str, Any] | None = Depends(optional_account)):
    return await _skill_endpoint("strategy", payload, account)


@router.post("/diagnose")
async def ai_diagnose(payload: dict[str, Any], account: dict[str, Any] | None = Depends(optional_account)):
    return await _skill_endpoint("diagnosis", payload, account)


@router.post("/reports/analyze")
async def ai_report_analysis(payload: dict[str, Any], account: dict[str, Any] | None = Depends(optional_account)):
    return await _skill_endpoint("report_analysis", payload, account)
