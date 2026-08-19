"""Safe run-flow snapshots for the AI task workbench.

The flow is a read model.  It is derived from task events and report metadata,
and deliberately omits prompts, context contents, credentials, provider error
details, and any executable authority.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


RunFlowStatus = Literal[
    "pending",
    "running",
    "success",
    "failed",
    "degraded",
    "fallback",
    "retry",
    "timeout",
    "cancel_requested",
    "cancelled",
    "skipped",
    "unknown",
]

RunFlowNodeKind = Literal[
    "entry",
    "queue",
    "data_source",
    "analysis",
    "model",
    "artifact",
    "notification",
]

RunFlowEdgeKind = Literal["data", "control", "fallback", "retry"]
RunFlowEventSeverity = Literal["info", "success", "warning", "danger"]


class RunFlowLane(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    order: int


class RunFlowNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    lane: str
    kind: RunFlowNodeKind
    label: str
    status: RunFlowStatus
    provider: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    attempts: int | None = Field(default=None, ge=0)
    message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunFlowEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    kind: RunFlowEdgeKind
    status: RunFlowStatus
    label: str | None = None
    message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunFlowEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    timestamp: str | None = None
    severity: RunFlowEventSeverity
    type: str
    node_id: str | None = None
    title: str
    message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunFlowSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    elapsed_ms: int | None = Field(default=None, ge=0)
    bottleneck_node_id: str | None = None
    failed_attempts: int = Field(default=0, ge=0)
    fallback_count: int = Field(default=0, ge=0)
    retry_count: int = Field(default=0, ge=0)
    model: str | None = None
    data_source_count: int = Field(default=0, ge=0)
    event_count: int = Field(default=0, ge=0)


class RunFlowSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    trace_id: str | None = None
    instrument: str
    market: str | None = None
    status: RunFlowStatus
    summary: RunFlowSummary
    lanes: list[RunFlowLane] = Field(default_factory=list)
    nodes: list[RunFlowNode] = Field(default_factory=list)
    edges: list[RunFlowEdge] = Field(default_factory=list)
    events: list[RunFlowEvent] = Field(default_factory=list)
    generated_at: str
    safety_boundary: dict[str, Any] = Field(default_factory=dict)


_LANES = [
    {"id": "entry", "label": "入口", "order": 1},
    {"id": "data_source", "label": "输入与 Provider", "order": 2},
    {"id": "analysis", "label": "Agent 分析", "order": 3},
    {"id": "artifact", "label": "报告与资格", "order": 4},
]

_FORBIDDEN_KEYS = {
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
    "secret",
    "token",
    "api_key",
    "authorization",
}

_STAGE_LABELS = {
    "agents": "Agent 编排",
    "technical": "技术观点",
    "intelligence": "情报观点",
    "quant": "量化观点",
    "risk": "风险观点",
    "decision": "综合观点",
    "synthesis": "综合报告",
    "deep_research": "深度研究",
    "screening_query": "筛选条件",
    "prediction_interpretation": "预测解读",
    "strategy_generation": "策略草案",
    "backtest_diagnosis": "回测诊断",
    "report_analysis": "研报解读",
    "report": "结构化报告",
}

_EVENT_LABELS = {
    "task_created": "任务已创建",
    "accepted": "任务已接收",
    "task_started": "Worker 开始",
    "thinking": "冻结输入",
    "stage_start": "阶段开始",
    "stage_done": "阶段完成",
    "provider_start": "Provider 调用",
    "provider_done": "Provider 返回",
    "provider_error": "Provider 降级",
    "generating": "生成综合报告",
    "research_plan": "研究计划",
    "research_done": "研究完成",
    "tool_start": "技能开始",
    "tool_done": "技能完成",
    "done": "任务完成",
    "task_completed": "任务完成",
    "error": "任务错误",
    "task_failed": "任务失败",
    "cancelled": "任务取消",
    "task_cancelled": "任务取消",
}


def _text(value: Any, fallback: str = "", limit: int = 240) -> str:
    result = str(value or "").strip()
    return (result[:limit] if result else fallback)


def _safe_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        return None
    if isinstance(value, Mapping):
        return {
            str(key): _safe_value(child, depth=depth + 1)
            for key, child in value.items()
            if str(key).strip().lower() not in _FORBIDDEN_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_safe_value(item, depth=depth + 1) for item in list(value)[:30]]
    if isinstance(value, str):
        return value[:500]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _text(value, limit=240)


def _payload(event: Mapping[str, Any]) -> dict[str, Any]:
    raw = event.get("payload")
    return dict(raw) if isinstance(raw, Mapping) else {}


def _status(task_status: Any) -> RunFlowStatus:
    return {
        "queued": "pending",
        "running": "running",
        "completed": "success",
        "degraded": "degraded",
        "failed": "failed",
        "cancel_requested": "cancel_requested",
        "cancelled": "cancelled",
    }.get(str(task_status or ""), "unknown")  # type: ignore[return-value]


def _parse_time(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _iso(value: Any) -> str | None:
    parsed = _parse_time(value)
    return parsed.isoformat() if parsed else (_text(value) or None)


def _duration_ms(start: Any, end: Any) -> int | None:
    first = _parse_time(start)
    last = _parse_time(end)
    if first is None or last is None:
        return None
    return max(0, round((last - first).total_seconds() * 1000))


def _event_severity(event_type: str, payload: Mapping[str, Any]) -> RunFlowEventSeverity:
    if event_type in {"error", "task_failed"}:
        return "danger"
    if event_type in {"provider_error", "task_cancelled", "cancelled"}:
        return "warning"
    if event_type in {"done", "task_completed", "provider_done", "research_done", "tool_done"}:
        return "success"
    if str(payload.get("status") or "") in {"failed", "degraded"}:
        return "warning"
    return "info"


def _attempts_from_events(events: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for event in events:
        payload = _payload(event)
        stage = _text(payload.get("stage"), "provider")
        candidates: list[Any] = []
        if isinstance(payload.get("attempts"), list):
            candidates.extend(payload["attempts"])
        diagnostic = payload.get("diagnostic")
        if isinstance(diagnostic, Mapping):
            details = diagnostic.get("details")
            if isinstance(details, Mapping) and isinstance(details.get("attempts"), list):
                candidates.extend(details["attempts"])
        for raw in candidates:
            if not isinstance(raw, Mapping):
                continue
            item = {
                "stage": stage,
                "attempt": _text(raw.get("attempt"), str(len(attempts) + 1)),
                "provider": _text(raw.get("provider"), "unknown", 100),
                "model": _text(raw.get("model"), "", 120),
                "relation": _text(raw.get("relation"), "initial", 40),
                "retry_index": raw.get("retry_index") if isinstance(raw.get("retry_index"), int) else 0,
                "fallback_from": _text(raw.get("fallback_from"), "", 100) or None,
                "fallback_to": _text(raw.get("fallback_to"), "", 100) or None,
                "status": _text(raw.get("status"), "unknown", 40),
                "duration_ms": raw.get("duration_ms") if isinstance(raw.get("duration_ms"), int) and raw.get("duration_ms") >= 0 else None,
                "error_code": _text(raw.get("error_code"), "", 80) or None,
                "error_message": _text(raw.get("error_message"), "", 260) or None,
            }
            key = (stage, item["attempt"], item["provider"], item["relation"], item["status"])
            if key not in seen:
                seen.add(key)
                attempts.append(item)
    return attempts


def build_task_run_flow_snapshot(
    task: Mapping[str, Any],
    events: Iterable[Mapping[str, Any]] = (),
    *,
    report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the DSA-style lanes/nodes/edges/events contract for a task."""

    task_id = _text(task.get("id"), "unknown-task", 100)
    task_events = [dict(item) for item in events if isinstance(item, Mapping)]
    flow_status = _status(task.get("status"))
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    flow_events: list[dict[str, Any]] = []

    def node(node_id: str, **values: Any) -> None:
        nodes[node_id] = {"id": node_id, **values}

    def edge(from_node: str, to_node: str, kind: RunFlowEdgeKind, status: RunFlowStatus, *, label: str = "", message: str = "") -> None:
        edges.append({
            "id": f"edge_{len(edges) + 1}_{from_node}_{to_node}",
            "from": from_node,
            "to": to_node,
            "kind": kind,
            "status": status,
            "label": label or None,
            "message": message or None,
        })

    node(
        "request",
        lane="entry",
        kind="entry",
        label="用户请求",
        status="success" if task.get("created_at") else "unknown",
        started_at=_iso(task.get("created_at")),
        ended_at=_iso(task.get("created_at")),
        message=f"{_text(task.get('kind'), 'analysis')} · {_text(task.get('profile'), 'standard')}",
        metadata={"task_id": task_id},
    )
    node(
        "task_queue",
        lane="entry",
        kind="queue",
        label="AI Worker 队列",
        status=flow_status,
        started_at=_iso(task.get("started_at")),
        ended_at=_iso(task.get("completed_at")),
        message="独立 Worker 获取 lease 后执行",
        metadata={"owner_id": _text(task.get("owner_id"), "", 100) or None},
    )
    edge("request", "task_queue", "control", flow_status, label="提交")

    context_status: RunFlowStatus = "success" if task.get("context_hash") else "unknown"
    node(
        "context_pack",
        lane="data_source",
        kind="data_source",
        label="冻结 Context",
        status=context_status,
        message="AI 只读取提交时冻结的输入快照",
        metadata={"context_hash_prefix": _text(task.get("context_hash"), "")[:16] or None},
    )
    edge("task_queue", "context_pack", "data", context_status, label="输入")

    attempts = _attempts_from_events(task_events)
    previous_by_stage: dict[str, str] = {}
    for index, attempt in enumerate(attempts, start=1):
        stage = _text(attempt.get("stage"), "provider", 60)
        provider = _text(attempt.get("provider"), "unknown", 100)
        node_id = f"provider_{index}"
        relation = _text(attempt.get("relation"), "initial", 40)
        raw_status = _text(attempt.get("status"), "unknown", 40)
        node_status: RunFlowStatus = "success" if raw_status == "success" else "fallback" if relation == "fallback" else "retry" if relation == "retry" else "failed" if raw_status == "failed" else "unknown"
        node(
            node_id,
            lane="data_source",
            kind="data_source",
            label=f"{_STAGE_LABELS.get(stage, stage)} · {provider}",
            status=node_status,
            provider=provider,
            duration_ms=attempt.get("duration_ms"),
            attempts=1,
            message=_text(attempt.get("error_message"), "provider 返回成功" if raw_status == "success" else "provider 未能生成结果"),
            metadata={
                "stage": stage,
                "model": attempt.get("model"),
                "attempt": attempt.get("attempt"),
                "retry_index": attempt.get("retry_index"),
                "relation": relation,
                "error_code": attempt.get("error_code"),
                "fallback_from": attempt.get("fallback_from"),
                "fallback_to": attempt.get("fallback_to"),
            },
        )
        previous = previous_by_stage.get(stage)
        if previous:
            transition_kind: RunFlowEdgeKind = "fallback" if relation == "fallback" else "retry" if relation == "retry" else "control"
            edge(previous, node_id, transition_kind, node_status, label="降级" if transition_kind == "fallback" else "重试" if transition_kind == "retry" else "继续")
        else:
            edge("context_pack", node_id, "data", node_status, label="调用")
        previous_by_stage[stage] = node_id

    stage_nodes: dict[str, str] = {}
    for event in task_events:
        event_type = _text(event.get("event_type") or event.get("type"), "event", 80)
        payload = _payload(event)
        stage = _text(payload.get("stage") or payload.get("skill"), "", 60)
        if event_type in {"stage_start", "stage_done", "generating", "research_plan", "tool_start", "tool_done", "research_done"} and stage:
            stage_id = f"stage_{stage.replace('-', '_')}"
            if stage_id not in stage_nodes:
                status_value: RunFlowStatus = "running" if event_type in {"stage_start", "generating", "research_plan", "tool_start"} else "success" if _text(payload.get("status"), "completed") in {"completed", "success"} else "degraded"
                node(stage_id, lane="analysis", kind="model", label=_STAGE_LABELS.get(stage, stage), status=status_value, provider=_text(payload.get("provider"), "", 100) or None, message=_text(payload.get("message") or payload.get("status"), "阶段事件"), metadata={"stage": stage})
                stage_nodes[stage_id] = stage_id
                edge("context_pack", stage_id, "data", status_value, label="分析")
            elif event_type in {"stage_done", "tool_done", "research_done"}:
                nodes[stage_id]["status"] = "success" if _text(payload.get("status"), "completed") in {"completed", "success"} else "degraded"
                nodes[stage_id]["message"] = _text(payload.get("message") or payload.get("status"), nodes[stage_id].get("message", ""))

    report_body = report.get("body") if isinstance(report, Mapping) and isinstance(report.get("body"), Mapping) else {}
    if report_body or task.get("report_id"):
        report_status: RunFlowStatus = "success" if _text(report_body.get("status"), "") in {"complete", "partial"} else "degraded" if _text(report_body.get("status"), "") else flow_status
        node("report", lane="artifact", kind="artifact", label="结构化报告", status=report_status, ended_at=_iso(report.get("created_at") if isinstance(report, Mapping) else None), message="报告是非权威研究 artifact", metadata={"report_id": _text(task.get("report_id"), "", 100) or None})
        anchor = next(reversed(list(stage_nodes.values())), None) or previous_by_stage.get("synthesis") or "context_pack"
        edge(anchor, "report", "data", report_status, label="生成")
    else:
        node("report", lane="artifact", kind="artifact", label="结构化报告", status="pending" if flow_status in {"pending", "running"} else "unknown", message="尚未生成报告")
        edge(next(reversed(list(stage_nodes.values())), None) or "context_pack", "report", "data", nodes["report"]["status"], label="生成")

    node("safety_boundary", lane="artifact", kind="artifact", label="安全边界", status="success", message="AI 输出永不改变确定性决策、风控或自动推送资格", metadata={"authoritative": False, "decision_effect": "none"})
    edge("report", "safety_boundary", "control", "success", label="隔离")
    node("notification", lane="artifact", kind="notification", label="自动推送资格", status="skipped", message="AI 报告不具备自动推送资格；必须由确定性门禁独立判断", metadata={"eligible": False, "reason": "ai_output_is_non_authoritative"})
    edge("safety_boundary", "notification", "control", "skipped", label="不授予")

    for index, event in enumerate(task_events, start=1):
        event_type = _text(event.get("event_type") or event.get("type"), "event", 80)
        payload = _payload(event)
        related = _text(payload.get("stage") or payload.get("skill"), "", 60)
        related_id = f"stage_{related.replace('-', '_')}" if related and f"stage_{related.replace('-', '_')}" in nodes else None
        metadata = {
            key: _safe_value(payload.get(key))
            for key in ("stage", "skill", "provider", "model", "status", "code", "retryable", "fallback_used", "attempts")
            if payload.get(key) is not None
        }
        message = _text(payload.get("message") or payload.get("status") or payload.get("stage") or payload.get("skill"), "已记录")
        flow_events.append({
            "id": _text(event.get("id"), f"event-{index}", 100),
            "timestamp": _iso(event.get("created_at")),
            "severity": _event_severity(event_type, payload),
            "type": event_type,
            "node_id": related_id,
            "title": _EVENT_LABELS.get(event_type, event_type),
            "message": message,
            "metadata": metadata,
        })

    durations = [(node_id, item.get("duration_ms")) for node_id, item in nodes.items() if isinstance(item.get("duration_ms"), int)]
    bottleneck = max(durations, key=lambda item: item[1])[0] if durations else None
    start = _parse_time(task.get("started_at"))
    end = _parse_time(task.get("completed_at"))
    summary = RunFlowSummary(
        elapsed_ms=_duration_ms(start, end),
        bottleneck_node_id=bottleneck,
        failed_attempts=sum(1 for item in attempts if item.get("status") == "failed"),
        fallback_count=sum(1 for item in attempts if item.get("relation") == "fallback"),
        retry_count=sum(1 for item in attempts if item.get("relation") == "retry"),
        model=next((_text(item.get("model"), "", 120) for item in reversed(attempts) if item.get("status") == "success"), None),
        data_source_count=sum(1 for item in nodes.values() if item.get("kind") == "data_source"),
        event_count=len(flow_events),
    )
    snapshot = RunFlowSnapshot(
        task_id=task_id,
        trace_id=task_id,
        instrument=_text(
            report_body.get("instrument")
            or (task.get("request", {}).get("instrument") if isinstance(task.get("request"), Mapping) else None),
            "UNKNOWN",
            100,
        ),
        market=_text(
            report_body.get("market")
            or (task.get("request", {}).get("market") if isinstance(task.get("request"), Mapping) else None),
            "CN",
            16,
        ),
        status=flow_status,
        summary=summary,
        lanes=[RunFlowLane.model_validate(item) for item in _LANES],
        nodes=[RunFlowNode.model_validate(item) for item in nodes.values()],
        edges=[RunFlowEdge.model_validate(item) for item in edges],
        events=[RunFlowEvent.model_validate(item) for item in flow_events],
        generated_at=datetime.now(timezone.utc).isoformat(),
        safety_boundary={"authoritative": False, "decision_effect": "none", "automatic_delivery_eligible": False},
    )
    return snapshot.model_dump(mode="json", by_alias=True)
