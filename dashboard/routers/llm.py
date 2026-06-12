"""AI 助手 API — OpenAI 兼容大模型接入

端点：
- POST /api/llm/chat         — 通用对话（流式 SSE）
- POST /api/llm/generate-filters — 自然语言 → 选股条件
- POST /api/llm/interpret    — AI 预测结果解读
"""
from __future__ import annotations

import json
import hashlib
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel

from alpha import nl_strategy
from dashboard.session import optional_account

router = APIRouter()


def _safe_float(v, default=None):
    """将值安全转换为浮点数，失败返回 default"""
    if v is None or v == "" or v == "-":
        return default
    try:
        return round(float(v), 2)
    except (ValueError, TypeError):
        return default


# ── 请求模型 ──


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


class GenerateFiltersRequest(BaseModel):
    description: str


class InterpretRequest(BaseModel):
    stock_code: str
    stock_name: str = ""
    prediction: dict = {}
    shap_values: list[dict] = []


# ── 端点 ──


@router.post("/chat")
async def llm_chat(req: ChatRequest):
    """通用量化对话（流式 SSE 响应）"""

    async def event_stream():
        try:
            history = [{"role": m.role, "content": m.content} for m in req.history]
            stream = await nl_strategy.chat(req.message, history=history)
            async for token in stream:
                yield f"data: {json.dumps({'content': token}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"LLM 对话异常: {e}")
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/generate-filters")
async def llm_generate_filters(req: GenerateFiltersRequest):
    """自然语言 → 选股条件 JSON"""
    try:
        filters = await nl_strategy.generate_filters(req.description)
        return {"success": True, "filters": filters}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"生成选股条件异常: {e}")
        return {"success": False, "error": "AI 生成失败，请稍后重试"}


@router.post("/interpret")
async def llm_interpret(req: InterpretRequest):
    """AI 预测结果自然语言解读"""
    try:
        text = await nl_strategy.interpret_prediction(
            stock_code=req.stock_code,
            stock_name=req.stock_name,
            prediction=req.prediction,
            shap_values=req.shap_values if req.shap_values else None,
        )
        return {"success": True, "interpretation": text}
    except Exception as e:
        logger.error(f"AI 解读异常: {e}")
        return {"success": False, "error": "AI 解读失败，请稍后重试"}


# ── 策略代码生成 + 回测诊断 ──


class GenerateStrategyRequest(BaseModel):
    description: str


class DiagnoseBacktestRequest(BaseModel):
    result: dict


@router.post("/generate-strategy")
async def generate_strategy(req: GenerateStrategyRequest):
    """自然语言 → 策略代码"""
    if not req.description.strip():
        raise HTTPException(400, "策略描述不能为空")
    try:
        code = await nl_strategy.generate_strategy_code(req.description)
        return {"success": True, "code": code}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"策略生成异常: {e}")
        return {"success": False, "error": "AI 生成失败，请稍后重试"}


@router.post("/diagnose-backtest")
async def diagnose_backtest(req: DiagnoseBacktestRequest):
    """回测结果 → AI 诊断报告"""
    if not req.result:
        raise HTTPException(400, "回测结果不能为空")
    try:
        report = await nl_strategy.diagnose_backtest(req.result)
        return {"success": True, "report": report}
    except Exception as e:
        logger.error(f"回测诊断异常: {e}")
        return {"success": False, "error": "AI 诊断失败，请稍后重试"}


# ── 问财自然语言查询 ──

class IwencaiRequest(BaseModel):
    query: str
    cookie: str = ""
    raw_query: str | None = None
    intent_type: str | None = None
    selected_bucket: str | None = None
    request_generation: int | None = None
    source_context: dict[str, Any] | None = None


IWENCAI_SOURCE_CONTEXT_ALLOWLIST = {
    "source",
    "sourceLabel",
    "context_type",
    "concept",
    "sector_name",
    "sector_code",
    "grouping",
    "universe",
    "raw_query",
    "query",
    "action",
    "result_pool_id",
    "rank_reason",
    "result_total",
    "candidate_codes",
    "selected_bucket",
    "intent_type",
    "parsed_conditions",
    "condition_hit_count",
    "data_as_of",
    "cache_status",
    "provider",
    "provider_status",
    "source_type",
    "response_type",
    "retry_after_seconds",
    "local_wait_seconds",
    "request_generation",
    "data_status",
    "stock_code",
    "stock_name",
    "code",
    "name",
    "route",
    "bucket",
}

IWENCAI_SENSITIVE_CONTEXT_KEYS = re.compile(
    r"(cookie|token|secret|password|passwd|authorization|header|session|api[_-]?key|invite)",
    flags=re.I,
)
IWENCAI_SENSITIVE_TEXT = re.compile(
    r"(?i)\b(cookie|token|secret|password|passwd|authorization|session|api[_-]?key|invite)\s*[:=]\s*[^,\s;]+|Bearer\s+[A-Za-z0-9._~+/=-]+"
)

IWENCAI_DEGRADED_SOURCE_TYPES = {
    "stale_cache",
    "unsupported_field",
    "schema_drift",
    "offline_fallback",
}


@router.post("/iwencai")
async def iwencai_query(req: IwencaiRequest):
    """问财自然语言股票查询"""
    if not req.query.strip():
        raise HTTPException(400, "查询语句不能为空")
    try:
        from alpha import iwencai_client

        provider_result = None
        if hasattr(iwencai_client, "query_iwencai_with_status"):
            provider_result = await iwencai_client.query_iwencai_with_status(req.query, cookie=req.cookie)
            df = _iwencai_result_value(provider_result, "data")
        else:
            df = await iwencai_client.query_iwencai(req.query, cookie=req.cookie)

        provider_state = _build_iwencai_provider_state(provider_result, df)
        if provider_state["task_status"] == "failed":
            return _build_iwencai_task_response(
                req,
                [],
                total=0,
                success=False,
                status="failed",
                error=provider_state["error"],
                failure_type=provider_state["failure_type"],
                source_status_override=provider_state["source_status"],
            )

        degraded_status = "degraded_data" if provider_state["task_status"] == "degraded" else None
        if df.empty:
            return _build_iwencai_task_response(
                req,
                [],
                total=0,
                success=True,
                status=degraded_status or "no_match",
                error=provider_state["error"] if degraded_status else "",
                failure_type=provider_state["failure_type"] if degraded_status else "no_match",
                source_status_override=provider_state["source_status"],
            )

        # DataFrame → list[dict]
        records = df.head(50).to_dict(orient="records")
        # 清理 NaN
        for r in records:
            for k, v in r.items():
                if v is None or (isinstance(v, float) and v != v):
                    r[k] = ""
        return _build_iwencai_task_response(
            req,
            records,
            total=len(df),
            success=True,
            status=degraded_status,
            error=provider_state["error"] if degraded_status else "",
            failure_type=provider_state["failure_type"] if degraded_status else "",
            source_status_override=provider_state["source_status"],
        )
    except Exception as e:
        logger.error(f"问财查询异常: {type(e).__name__}")
        return _build_iwencai_task_response(
            req,
            [],
            total=0,
            success=False,
            status="failed",
            error="问财查询失败，请稍后重试",
            failure_type="request_failed",
            source_status_override={
                "provider": "iwencai",
                "status": "failed",
                "type": "request_failed",
                "provider_status": "request_failed",
                "data_as_of": datetime.now(timezone.utc).isoformat(),
                "cache_status": "live_request",
                "reason": "问财查询失败，请稍后重试",
            },
        )


def _iwencai_result_value(result: Any, key: str, default: Any = None) -> Any:
    if result is None:
        return default
    if isinstance(result, dict):
        return result.get(key, default)
    return getattr(result, key, default)


def _build_iwencai_provider_state(provider_result: Any, df: Any) -> dict[str, Any]:
    provider = str(_iwencai_result_value(provider_result, "provider", "iwencai") or "iwencai")
    provider_status = str(_iwencai_result_value(provider_result, "provider_status", "ok") or "ok")
    failure_type = str(_iwencai_result_value(provider_result, "failure_type", "") or "")
    failure_reason = str(_iwencai_result_value(provider_result, "failure_reason", "") or "")
    data_as_of = str(
        _iwencai_result_value(provider_result, "data_as_of", "")
        or datetime.now(timezone.utc).isoformat()
    )
    cache_status = str(_iwencai_result_value(provider_result, "cache_status", "live_request") or "live_request")
    response_type = str(_iwencai_result_value(provider_result, "response_type", "") or "")
    schema_signature = str(_iwencai_result_value(provider_result, "schema_signature", "") or "")
    local_wait_seconds = _iwencai_result_value(provider_result, "local_wait_seconds", 0.0)
    retry_after_seconds = _iwencai_result_value(provider_result, "retry_after_seconds", None)

    status_map = {
        "ok": "ok",
        "provider_unavailable": "unavailable",
        "request_failed": "failed",
        "rate_limited": "rate_limited",
        "invalid_provider_response": "invalid_response",
        "invalid_response": "invalid_response",
        "schema_drift": "degraded_data",
    }
    source_status_value = status_map.get(provider_status, provider_status or "ok")
    normalized_failure_type = failure_type or (
        "provider_unavailable" if provider_status == "provider_unavailable"
        else "rate_limited" if provider_status == "rate_limited"
        else "invalid_provider_response" if provider_status in {"invalid_provider_response", "invalid_response"}
        else "schema_drift" if provider_status == "schema_drift"
        else "stale_cache" if cache_status == "stale_cache"
        else "request_failed" if provider_status != "ok"
        else ""
    )
    default_reason = {
        "provider_unavailable": "问财源不可用，请检查依赖或凭证后重试",
        "request_failed": "问财查询失败，请稍后重试",
        "rate_limited": "问财源限流或访问频率受限，请稍后重试",
        "invalid_provider_response": "问财返回格式异常，无法稳定解析为候选池",
        "invalid_response": "问财返回格式异常，无法稳定解析为候选池",
        "schema_drift": "问财返回字段结构变化，条件证据需重新适配",
    }.get(provider_status, "")
    if not default_reason:
        default_reason = {
            "stale_cache": "当前结果来自旧缓存或数据日期偏旧",
            "unsupported_field": "部分字段暂未接入或缺少可验证数据源",
            "offline_fallback": "外部源不可用，当前使用本地或缓存降级结果",
        }.get(normalized_failure_type, "")
    reason = failure_reason or default_reason
    degraded_type = (
        normalized_failure_type
        if normalized_failure_type in IWENCAI_DEGRADED_SOURCE_TYPES
        else ""
    )
    if cache_status == "stale_cache":
        degraded_type = "stale_cache"
        normalized_failure_type = normalized_failure_type or "stale_cache"
        source_status_value = "stale_cache"
        reason = reason or "当前结果来自旧缓存或数据日期偏旧"
    elif degraded_type and source_status_value == "ok":
        source_status_value = "degraded_data"

    source_status = {
        "provider": provider,
        "status": source_status_value,
        "provider_status": provider_status,
        "type": normalized_failure_type,
        "data_as_of": data_as_of,
        "cache_status": cache_status,
        "reason": reason,
    }
    if response_type:
        source_status["response_type"] = response_type
    if schema_signature:
        source_status["schema_signature"] = schema_signature
    if local_wait_seconds not in (None, "", 0, 0.0):
        source_status["local_wait_seconds"] = local_wait_seconds
    if retry_after_seconds not in (None, ""):
        source_status["retry_after_seconds"] = retry_after_seconds

    if degraded_type:
        source_status["status"] = "stale_cache" if degraded_type == "stale_cache" else "degraded_data"
        source_status["type"] = degraded_type
        source_status["reason"] = reason

    if provider_status != "ok" and not degraded_type:
        return {
            "task_status": "failed",
            "failure_type": normalized_failure_type or "request_failed",
            "error": reason or "问财查询失败，请稍后重试",
            "source_status": source_status,
        }

    if df is None or not hasattr(df, "empty") or not hasattr(df, "head"):
        source_status.update({
            "status": "invalid_response",
            "provider_status": "invalid_provider_response",
            "type": "invalid_provider_response",
            "reason": "问财返回格式异常，无法稳定解析为候选池",
            "response_type": type(df).__name__,
        })
        return {
            "task_status": "failed",
            "failure_type": "invalid_provider_response",
            "error": "问财返回格式异常，无法稳定解析为候选池",
            "source_status": source_status,
        }

    return {
        "task_status": "degraded" if degraded_type else "ok",
        "failure_type": normalized_failure_type,
        "error": reason,
        "source_status": source_status,
    }


def _normalize_iwencai_request_generation(*values: Any) -> int | None:
    for value in values:
        try:
            generation = int(value)
        except (TypeError, ValueError):
            continue
        if generation > 0:
            return min(generation, 1_000_000_000)
    return None


def _build_iwencai_task_response(
    req: IwencaiRequest,
    records: list[dict[str, Any]],
    *,
    total: int,
    success: bool,
    status: str | None = None,
    error: str = "",
    failure_type: str = "",
    source_status_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    query = req.query.strip()
    selected_bucket = req.selected_bucket or "candidates"
    computed_status = status or ("result_ready" if records else "no_match")
    issue = _build_iwencai_issue(computed_status, error=error, failure_type=failure_type)
    source_status = {
        "provider": "iwencai",
        "status": "ok" if success else "failed",
        "data_as_of": datetime.now(timezone.utc).isoformat(),
        "cache_status": "live_request",
        "reason": issue["reason"] if computed_status != "result_ready" else "",
    }
    if source_status_override:
        source_status.update({
            key: value
            for key, value in source_status_override.items()
            if value is not None
        })
    if computed_status != "result_ready" and not source_status.get("reason"):
        source_status["reason"] = issue["reason"]
    if issue["type"] and not source_status.get("type"):
        source_status["type"] = issue["type"]
    parsed_conditions = _parse_iwencai_conditions(query, records, source_status)
    computed_status, source_status = _apply_iwencai_evidence_gate(
        computed_status,
        parsed_conditions,
        source_status,
    )
    issue = _build_iwencai_issue(computed_status, error=error, failure_type=failure_type or source_status.get("type", ""))
    if computed_status != "result_ready" and not source_status.get("reason"):
        source_status["reason"] = issue["reason"]
    if issue["type"] and not source_status.get("type"):
        source_status["type"] = issue["type"]
    result_pool_id = _iwencai_result_pool_id(query, total, source_status)
    intent = _infer_iwencai_intent(query, req.intent_type, parsed_conditions, records)
    normalized_candidates = [
        _normalize_iwencai_candidate(row, idx, parsed_conditions, source_status, result_pool_id, query)
        for idx, row in enumerate(records)
    ]
    normalized_candidates = [item for item in normalized_candidates if item]
    _attach_iwencai_candidate_provenance(records, normalized_candidates)
    computed_status, source_status = _apply_iwencai_candidate_evidence_gate(
        computed_status,
        normalized_candidates,
        source_status,
    )
    issue = _build_iwencai_issue(computed_status, error=error, failure_type=failure_type or source_status.get("type", ""))
    buckets = _build_iwencai_buckets(normalized_candidates, records, total, parsed_conditions)
    if not any(bucket["id"] == selected_bucket for bucket in buckets):
        selected_bucket = "candidates"
    actions = _build_iwencai_actions(computed_status, bool(normalized_candidates))
    source_context = _build_iwencai_source_context(
        req,
        query,
        intent,
        parsed_conditions,
        selected_bucket,
        total,
        source_status,
        issue,
        result_pool_id,
    )
    response = {
        "success": success,
        "schema_version": "iwencai_task_router_v1",
        "query": query,
        "raw_query": req.raw_query or query,
        "data": records,
        "total": total,
        "status": computed_status,
        "intent": intent,
        "parsed_conditions": parsed_conditions,
        "buckets": buckets,
        "selected_bucket": selected_bucket,
        "actions": actions,
        "source_context": source_context,
        "source_status": source_status,
        "issue": issue,
        "failure_type": issue["type"],
        "failure_reason": issue["reason"],
        "next_action": issue["next_action"],
    }
    if error:
        response["error"] = error
    if not records and success:
        response["message"] = "无匹配结果"
    return response


def _apply_iwencai_evidence_gate(
    status: str,
    parsed_conditions: list[dict[str, Any]],
    source_status: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    if status != "result_ready" or not parsed_conditions:
        return status, source_status
    if all(item.get("hit_count_status") == "verified" for item in parsed_conditions):
        return status, source_status

    next_source_status = dict(source_status)
    next_source_status.setdefault("provider_status", "ok")
    next_source_status["status"] = "partial_source_failure"
    next_source_status["type"] = "partial_source_failure"
    next_source_status["partial_source_failure"] = True
    next_source_status["reason"] = "部分条件缺少可验证的 provider 字段证据"
    return "partial_result", next_source_status


def _apply_iwencai_candidate_evidence_gate(
    status: str,
    candidates: list[dict[str, Any]],
    source_status: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    if status != "result_ready" or not candidates:
        return status, source_status
    if all(
        (candidate.get("candidate_provenance") or {}).get("validation_status") == "verified"
        for candidate in candidates
    ):
        return status, source_status

    next_source_status = dict(source_status)
    next_source_status.setdefault("provider_status", "ok")
    next_source_status["status"] = "partial_source_failure"
    next_source_status["type"] = "partial_source_failure"
    next_source_status["partial_source_failure"] = True
    next_source_status["candidate_provenance_status"] = "partial"
    next_source_status["reason"] = "部分候选缺少行级可验证证据"
    return "partial_result", next_source_status


def _sanitize_iwencai_source_context(context: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(context, dict):
        return {}
    safe: dict[str, Any] = {}
    for key, value in context.items():
        if key not in IWENCAI_SOURCE_CONTEXT_ALLOWLIST:
            continue
        if IWENCAI_SENSITIVE_CONTEXT_KEYS.search(str(key)):
            continue
        safe_value = _sanitize_iwencai_context_value(value)
        if safe_value is not None:
            safe[key] = safe_value
    return safe


def _sanitize_iwencai_context_value(value: Any, depth: int = 0) -> Any:
    if isinstance(value, str):
        return IWENCAI_SENSITIVE_TEXT.sub("[redacted]", value)
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, list):
        return [
            item
            for item in (_sanitize_iwencai_context_value(item, depth + 1) for item in value[:100])
            if item is not None
        ]
    if isinstance(value, dict) and depth < 2:
        safe: dict[str, Any] = {}
        for key, item in value.items():
            if IWENCAI_SENSITIVE_CONTEXT_KEYS.search(str(key)):
                continue
            safe_item = _sanitize_iwencai_context_value(item, depth + 1)
            if safe_item is not None:
                safe[str(key)] = safe_item
        return safe
    return IWENCAI_SENSITIVE_TEXT.sub("[redacted]", str(value))[:500]


def _infer_iwencai_intent(
    query: str,
    requested_intent: str | None,
    parsed_conditions: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    if requested_intent:
        intent_type = requested_intent
        reason = "沿用入口预路由意图"
    elif re.fullmatch(r"(?:sh|sz|bj)?\d{6}(?:\.(?:SH|SZ|BJ))?", query.strip(), flags=re.I):
        intent_type = "stock_lookup"
        reason = "明确股票代码查询"
    elif parsed_conditions:
        intent_type = "natural_language_screener"
        reason = "后端解析出自然语言选股条件"
    elif any(token in query for token in ("板块", "概念", "行业", "为什么", "资金", "新闻")) and records:
        intent_type = "market_topic"
        reason = "市场主题或归因问题"
    else:
        intent_type = "market_question"
        reason = "市场问句或泛化查询"
    confidence = 0.86 if parsed_conditions else (0.75 if records else 0.52)
    return {"type": intent_type, "confidence": confidence, "reason": reason}


def _parse_iwencai_conditions(
    query: str,
    records: list[dict[str, Any]],
    source_status: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rules: list[tuple[str, str, str, str, str]] = [
        (r"高股息率|高股息|股息率高|高分红|分红高", "股息率", "rank", "高", "latest"),
        (r"低估值|估值低|低PE|PE低|低PB|PB低|低市盈率|市盈率低|低市净率|市净率低", "估值", "screen", "低", "latest"),
        (r"近?\d+(?:日|天)?(?:持续)?放量|放量|量比高|成交量放大|成交量放量", "成交量", "volume_up", "放量", ""),
        (r"近?\d+(?:日|天)?主力净流入|主力净流入|净流入|资金流入", "资金流", "inflow", "净流入", ""),
        (r"ROE大于\d+%?|高ROE|净资产收益率", "ROE", "gte", "", "latest"),
        (r"突破\d+日新高|突破新高", "价格趋势", "breakout", "突破新高", ""),
        (r"剔除ST|非ST|排除ST", "风险标签", "exclude", "ST", "latest"),
    ]
    conditions: list[dict[str, Any]] = []
    occupied: list[tuple[int, int]] = []
    for pattern, field, op, value, default_window in rules:
        for match in re.finditer(pattern, query, flags=re.I):
            start, end = match.span()
            if any(start < old_end and end > old_start for old_start, old_end in occupied):
                continue
            raw = match.group(0)
            window_match = re.search(r"近?(\d+)(?:日|天)?", raw)
            window = f"{window_match.group(1)}d" if window_match else default_window
            evidence = _condition_evidence(records, field, raw, source_status)
            hit_count = evidence["hit_count"]
            conditions.append({
                "raw_text": raw,
                "field": field,
                "op": op,
                "value": value or raw,
                "window": window,
                "hit_count": hit_count,
                "hit_count_status": evidence["hit_count_status"],
                "missing_reason": evidence["missing_reason"],
                "evidence_level": evidence["evidence_level"],
                "source_field": evidence["source_field"],
                "source_fields": evidence["source_fields"],
                "status": evidence["condition_status"],
                "unavailable_reason": evidence["missing_reason"],
                "evidence": evidence,
                "source": "backend_parser",
            })
            occupied.append((start, end))
    conditions.sort(key=lambda item: query.find(item["raw_text"]))
    return conditions[:8]


def _condition_evidence(
    records: list[dict[str, Any]],
    field: str,
    raw_text: str,
    source_status: dict[str, Any] | None,
) -> dict[str, Any]:
    provider = str((source_status or {}).get("provider") or "iwencai")
    source_state = str((source_status or {}).get("status") or "ok")
    provider_status = str((source_status or {}).get("provider_status") or "ok")
    sample_size = len(records)
    base: dict[str, Any] = {
        "field": field,
        "normalized_field": field,
        "source_field": "",
        "source_fields": [],
        "hit_count": None,
        "hit_count_status": "missing_source_field",
        "missing_reason": "结果字段中缺少可验证该条件的来源字段",
        "evidence_level": "none",
        "condition_status": "degraded_data",
        "sample_size": sample_size,
        "provider": provider,
        "provider_status": provider_status,
    }
    if source_state not in {"ok", ""} or provider_status not in {"ok", ""}:
        reason = str((source_status or {}).get("reason") or "问财源不可用，无法验证条件命中数")
        source_type = str((source_status or {}).get("type") or "")
        if source_type in IWENCAI_DEGRADED_SOURCE_TYPES:
            return {
                **base,
                "hit_count_status": source_type,
                "missing_reason": reason,
                "condition_status": "degraded_data",
                "evidence_level": "source_status",
            }
        return {
            **base,
            "hit_count_status": "source_unavailable",
            "missing_reason": reason,
            "condition_status": "failed",
            "evidence_level": "source_status",
        }
    if not records:
        return {
            **base,
            "hit_count": 0,
            "hit_count_status": "provider_empty_result",
            "missing_reason": "",
            "condition_status": "no_match",
            "evidence_level": "provider_empty_result",
        }

    matched_fields = _matching_iwencai_source_fields(records, field, raw_text)
    if not matched_fields:
        return base

    field_names = [item["name"] for item in matched_fields]
    hit_count = 0
    for row in records:
        if any(_row_has_condition_evidence(row, item, raw_text) for item in matched_fields):
            hit_count += 1

    field_match = any(item["match_type"] == "field_alias" for item in matched_fields)
    evidence_level = "provider_field" if field_match else "row_value_match"
    hit_status = "verified" if hit_count > 0 else "missing_value"
    missing_reason = "" if hit_count > 0 else "来源字段存在，但候选行缺少可验证的非空取值"
    return {
        **base,
        "source_field": field_names[0],
        "source_fields": field_names,
        "hit_count": hit_count,
        "hit_count_status": hit_status,
        "missing_reason": missing_reason,
        "condition_status": "ready" if hit_count > 0 else "degraded_data",
        "evidence_level": evidence_level,
    }


def _matching_iwencai_source_fields(
    records: list[dict[str, Any]],
    field: str,
    raw_text: str,
) -> list[dict[str, str]]:
    aliases = {
        "股息率": ("股息", "分红", "现金分红"),
        "估值": ("估值", "PE", "PB", "市盈率", "市净率", "PETTM", "PBMRQ"),
        "成交量": ("放量", "量比", "成交量", "逐日放量", "成交额", "换手"),
        "资金流": ("主力", "净流入", "DDE", "资金"),
        "ROE": ("ROE", "净资产收益率"),
        "价格趋势": ("新高", "突破", "涨幅", "最高"),
        "风险标签": ("ST", "风险", "特别处理"),
    }.get(field, (field,))
    seen: set[str] = set()
    matches: list[dict[str, str]] = []
    all_keys = [str(key) for row in records for key in row.keys()]
    for key in all_keys:
        if key in seen:
            continue
        normalized_key = re.sub(r"[\s_\-（）()\[\]]+", "", key).upper()
        if any(str(alias).upper() in normalized_key for alias in aliases):
            seen.add(key)
            matches.append({"name": key, "match_type": "field_alias"})
    if matches:
        return matches[:6]

    for key in all_keys:
        if key in seen:
            continue
        if any(raw_text and raw_text in str(row.get(key) or "") for row in records):
            seen.add(key)
            matches.append({"name": key, "match_type": "row_value"})
    return matches[:6]


def _row_has_condition_evidence(row: dict[str, Any], source_field: dict[str, str], raw_text: str) -> bool:
    value = row.get(source_field["name"])
    if value in (None, ""):
        return False
    text = str(value)
    if source_field["match_type"] == "row_value":
        return bool(raw_text and raw_text in text)
    return True


def _normalize_iwencai_candidate(
    row: dict[str, Any],
    index: int,
    parsed_conditions: list[dict[str, Any]] | None = None,
    source_status: dict[str, Any] | None = None,
    result_pool_id: str = "",
    query: str = "",
) -> dict[str, Any] | None:
    code = _normalize_stock_code(_pick_iwencai_field(row, ["股票代码", "代码", "code", "CODE", "证券代码"]))
    raw_code = _pick_iwencai_field(row, ["股票代码", "代码", "code", "CODE", "证券代码"]) or code
    name = _pick_iwencai_field(row, ["股票简称", "股票名称", "名称", "name", "SECURITY_NAME_ABBR"])
    if not code and not name:
        return None
    candidate = {
        "code": code,
        "raw_code": str(raw_code or ""),
        "name": str(name or code or "--"),
        "rank": index + 1,
        "price": _pick_iwencai_field(row, ["最新价", "最新价格", "现价", "price"]),
        "change_pct": _pick_iwencai_field(row, ["最新涨跌幅", "涨跌幅", "change_pct"]),
        "industry": _pick_iwencai_field(row, ["所属同花顺行业", "所属行业", "行业"]),
        "concept": _pick_iwencai_field(row, ["所属概念", "概念", "题材概念"]),
        "rank_reason": "问财后端候选池排序",
        "row": row,
    }
    provenance = _build_iwencai_candidate_provenance(
        row,
        candidate,
        index,
        parsed_conditions or [],
        source_status or {},
        result_pool_id,
        query,
    )
    candidate["candidate_provenance"] = provenance
    row["candidate_provenance"] = provenance
    return candidate


def _iwencai_result_pool_id(query: str, total: int, source_status: dict[str, Any] | None = None) -> str:
    source_status = source_status or {}
    digest_source = "|".join([
        query,
        str(total),
        str(source_status.get("provider") or "iwencai"),
        str(source_status.get("data_as_of") or ""),
        str(source_status.get("cache_status") or ""),
    ])
    pool_digest = hashlib.sha1(digest_source.encode("utf-8")).hexdigest()[:12]
    return f"iwencai:{pool_digest}"


def _attach_iwencai_candidate_provenance(
    records: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> None:
    for record, candidate in zip(records, candidates):
        provenance = candidate.get("candidate_provenance")
        if isinstance(provenance, dict):
            record["candidate_provenance"] = provenance
            candidate["row"]["candidate_provenance"] = provenance


def _build_iwencai_candidate_provenance(
    row: dict[str, Any],
    candidate: dict[str, Any],
    index: int,
    parsed_conditions: list[dict[str, Any]],
    source_status: dict[str, Any],
    result_pool_id: str,
    query: str,
) -> dict[str, Any]:
    matched_conditions: list[dict[str, Any]] = []
    missing_conditions: list[dict[str, Any]] = []
    source_fields: list[dict[str, str]] = []
    seen_fields: set[str] = set()

    for condition in parsed_conditions:
        raw_text = str(condition.get("raw_text") or condition.get("field") or "").strip()
        field = str(condition.get("field") or raw_text).strip()
        condition_source_fields = [
            str(item)
            for item in condition.get("source_fields") or []
            if str(item or "").strip()
        ]
        if not condition_source_fields and condition.get("source_field"):
            condition_source_fields = [str(condition.get("source_field"))]
        hit_status = str(condition.get("hit_count_status") or "")
        evidence_level = str(condition.get("evidence_level") or "")
        if hit_status != "verified" or not condition_source_fields:
            missing_conditions.append({
                "raw_text": raw_text,
                "field": field,
                "hit_count_status": hit_status or "missing_source_field",
                "missing_reason": condition.get("missing_reason")
                    or condition.get("unavailable_reason")
                    or "该条件缺少可验证的 provider 字段证据",
            })
            continue

        matched_field = ""
        matched_value = ""
        for source_field in condition_source_fields:
            value = row.get(source_field)
            if value in (None, ""):
                continue
            value_text = str(value)
            if evidence_level == "row_value_match" and raw_text and raw_text not in value_text:
                continue
            matched_field = source_field
            matched_value = _safe_iwencai_field_value(value)
            break

        if matched_field:
            matched_conditions.append({
                "raw_text": raw_text,
                "field": field,
                "source_field": matched_field,
                "value": matched_value,
                "evidence_level": evidence_level or "provider_field",
                "hit_count_status": hit_status,
            })
            if matched_field not in seen_fields:
                seen_fields.add(matched_field)
                source_fields.append({
                    "field": matched_field,
                    "value": matched_value,
                    "condition": raw_text,
                })
        else:
            missing_conditions.append({
                "raw_text": raw_text,
                "field": field,
                "hit_count_status": "missing_row_value",
                "source_fields": condition_source_fields,
                "missing_reason": "该候选行缺少可验证的条件字段取值",
            })

    if not parsed_conditions:
        identity_fields = _iwencai_identity_source_fields(row)
        for item in identity_fields:
            if item["field"] not in seen_fields:
                seen_fields.add(item["field"])
                source_fields.append(item)
        matched_conditions.append({
            "raw_text": query,
            "field": "provider_row",
            "source_field": source_fields[0]["field"] if source_fields else "",
            "value": source_fields[0]["value"] if source_fields else "",
            "evidence_level": "provider_row",
            "hit_count_status": "verified",
        })

    if missing_conditions and matched_conditions:
        validation_status = "partial"
        evidence_level = "partial_provider_field"
    elif missing_conditions:
        validation_status = "unverified"
        evidence_level = "none"
    else:
        validation_status = "verified"
        evidence_level = "provider_field" if parsed_conditions else "provider_row"

    row_id_digest = hashlib.sha1(
        f"{result_pool_id}:{candidate.get('code') or candidate.get('raw_code')}:{index}".encode("utf-8")
    ).hexdigest()[:12]
    warnings = [item.get("missing_reason") for item in missing_conditions if item.get("missing_reason")]
    return {
        "result_pool_id": result_pool_id,
        "row_id": f"{result_pool_id}:row:{row_id_digest}",
        "code": candidate.get("code") or "",
        "name": candidate.get("name") or "",
        "rank": index + 1,
        "source": "iwencai",
        "provider": source_status.get("provider") or "iwencai",
        "provider_status": source_status.get("provider_status") or "ok",
        "data_as_of": source_status.get("data_as_of") or "",
        "cache_status": source_status.get("cache_status") or "",
        "query": query,
        "matched_conditions": matched_conditions,
        "missing_conditions": missing_conditions,
        "source_fields": source_fields[:12],
        "raw_field_map": _safe_iwencai_row_field_map(row, source_fields),
        "evidence_level": evidence_level,
        "validation_status": validation_status,
        "warnings": warnings[:6],
        "missing_reason": "；".join(dict.fromkeys(warnings))[:240],
    }


def _iwencai_identity_source_fields(row: dict[str, Any]) -> list[dict[str, str]]:
    fields = []
    for key in ("股票代码", "代码", "证券代码", "股票简称", "股票名称", "名称"):
        value = row.get(key)
        if value not in (None, ""):
            fields.append({"field": key, "value": _safe_iwencai_field_value(value), "condition": "provider_row"})
    return fields[:4]


def _safe_iwencai_row_field_map(row: dict[str, Any], source_fields: list[dict[str, str]]) -> dict[str, str]:
    wanted = {
        "股票代码", "代码", "证券代码", "股票简称", "股票名称", "名称",
        "最新价", "最新价格", "现价", "最新涨跌幅", "涨跌幅",
        "所属同花顺行业", "所属行业", "行业", "所属概念", "概念", "题材概念",
    }
    wanted.update(item["field"] for item in source_fields if item.get("field"))
    safe: dict[str, str] = {}
    for key, value in row.items():
        key_text = str(key)
        if key_text == "candidate_provenance":
            continue
        if key_text not in wanted:
            continue
        if IWENCAI_SENSITIVE_CONTEXT_KEYS.search(key_text):
            continue
        safe[key_text] = _safe_iwencai_field_value(value)
        if len(safe) >= 20:
            break
    return safe


def _safe_iwencai_field_value(value: Any) -> str:
    safe = _sanitize_iwencai_context_value(value)
    if isinstance(safe, (dict, list)):
        safe = json.dumps(safe, ensure_ascii=False)
    return str(safe if safe is not None else "")[:120]


def _normalize_stock_code(value: Any) -> str:
    raw = str(value or "").strip()
    match = re.match(r"^(\d{6})(?:\.(?:SH|SZ|BJ))?$", raw, flags=re.I)
    if match:
        return match.group(1)
    match = re.match(r"^(?:sh|sz|bj)(\d{6})$", raw, flags=re.I)
    if match:
        return match.group(1)
    match = re.search(r"\b(\d{6})\b", raw)
    return match.group(1) if match else ""


def _pick_iwencai_field(row: dict[str, Any], names: list[str]) -> Any:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    normalized_names = [re.sub(r"\[[^\]]+\]|\s+", "", name).upper() for name in names]
    for key, value in row.items():
        if value in (None, ""):
            continue
        normalized_key = re.sub(r"\[[^\]]+\]|\s+", "", str(key)).upper()
        if any(name and name in normalized_key for name in normalized_names):
            return value
    return ""


def _build_iwencai_buckets(
    candidates: list[dict[str, Any]],
    records: list[dict[str, Any]],
    total: int,
    parsed_conditions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidate_bucket = {
        "id": "candidates",
        "name": "候选股票",
        "type": "stock_pool",
        "status": "result_ready" if candidates else "no_match",
        "count": total,
        "items": candidates,
        "description": "后端问财候选池；保留 legacy data 兼容字段。",
    }
    themes = _extract_theme_bucket(candidates, records)
    evidence_bucket = {
        "id": "evidence",
        "name": "条件证据",
        "type": "conditions",
        "status": "result_ready" if parsed_conditions else "degraded_data",
        "count": len(parsed_conditions),
        "items": parsed_conditions,
        "description": "后端解析出的条件、命中数和不可用原因。",
    }
    return [candidate_bucket, themes, evidence_bucket]


def _extract_theme_bucket(candidates: list[dict[str, Any]], records: list[dict[str, Any]]) -> dict[str, Any]:
    labels: list[str] = []
    for item, row in zip(candidates, records):
        industry = str(item.get("industry") or "")
        concept = str(item.get("concept") or "")
        labels.extend([part.strip() for part in re.split(r"[-;；,，/]", industry) if part.strip()])
        labels.extend([part.strip() for part in re.split(r"[;；,，/]", concept) if part.strip()])
    counter = Counter(labels)
    items = [
        {"name": name, "description": f"{count} 只候选涉及该主题", "count": count}
        for name, count in counter.most_common(8)
    ]
    return {
        "id": "themes",
        "name": "板块主题",
        "type": "themes",
        "status": "result_ready" if items else "degraded_data",
        "count": len(items),
        "items": items,
        "description": "由后端根据候选行业/概念字段聚合；缺字段时显示降级。",
    }


def _build_iwencai_actions(status: str, has_candidates: bool) -> list[dict[str, Any]]:
    base = [
        {"id": "open_stock", "label": "打开个股", "scope": "row", "enabled": has_candidates, "requires_confirmation": False},
        {"id": "analyze", "label": "AI解释", "scope": "pool", "enabled": True, "requires_confirmation": False},
        {"id": "ask_ai", "label": "追问AI", "scope": "pool", "enabled": True, "requires_confirmation": False},
    ]
    blocked = status in {"failed", "no_match", "needs_disambiguation", "requires_confirmation", "partial_result", "degraded_data"} or not has_candidates
    if not blocked:
        base.extend([
            {"id": "send_screener", "label": "发送至选股器", "scope": "pool", "enabled": True, "requires_confirmation": False},
            {"id": "create_basket", "label": "生成篮子", "scope": "pool", "enabled": True, "requires_confirmation": True},
            {"id": "draft_backtest", "label": "生成回测草案", "scope": "pool", "enabled": True, "requires_confirmation": True},
        ])
    return base


def _build_iwencai_issue(status: str, *, error: str = "", failure_type: str = "") -> dict[str, str]:
    if status == "result_ready":
        return {"type": "", "label": "", "reason": "", "next_action": ""}
    issue_map = {
        "no_match": ("no_match", "无匹配", "没有找到匹配结果，建议放宽条件或切换分桶", "删除最窄条件，或先查看相关板块/主题"),
        "failed": ("request_failed", "请求失败", error or "请求失败，已保留原始问句和来源上下文", "重试、改写条件，或改用股票/板块入口继续"),
        "partial_result": ("partial_source_failure", "部分结果", "只返回部分结果，缺失证据已保留为空态或降级分桶", "先打开候选股验证，再决定是否生成篮子"),
        "degraded_data": ("degraded_data", "数据降级", error or "部分字段或来源不可用，结果为降级视图", "查看缺失原因，必要时只使用已验证字段"),
    }
    issue_type, label, reason, next_action = issue_map.get(
        status,
        (failure_type or status, status, error or "状态需要用户确认或澄清", "检查来源上下文后继续"),
    )
    return {"type": failure_type or issue_type, "label": label, "reason": reason, "next_action": next_action}


def _build_iwencai_source_context(
    req: IwencaiRequest,
    query: str,
    intent: dict[str, Any],
    parsed_conditions: list[dict[str, Any]],
    selected_bucket: str,
    total: int,
    source_status: dict[str, Any],
    issue: dict[str, str],
    result_pool_id: str,
) -> dict[str, Any]:
    incoming = _sanitize_iwencai_source_context(req.source_context)
    request_generation = _normalize_iwencai_request_generation(
        req.request_generation,
        incoming.get("request_generation"),
    )
    condition_hit_count = {
        item["raw_text"]: item.get("hit_count")
        for item in parsed_conditions
        if item.get("raw_text")
    }
    condition_evidence = {
        item["raw_text"]: {
            "hit_count": item.get("hit_count"),
            "hit_count_status": item.get("hit_count_status"),
            "missing_reason": item.get("missing_reason") or item.get("unavailable_reason") or "",
            "evidence_level": item.get("evidence_level") or "",
            "source_field": item.get("source_field") or "",
            "source_fields": item.get("source_fields") or [],
        }
        for item in parsed_conditions
        if item.get("raw_text")
    }
    source_context = {
        **incoming,
        "origin_context": incoming,
        "origin_result_pool_id": incoming.get("result_pool_id") or "",
        "source": incoming.get("source") or "iwencai",
        "sourceLabel": incoming.get("sourceLabel") or "问财",
        "context_type": "iwencai",
        "raw_query": req.raw_query or incoming.get("raw_query") or query,
        "query": query,
        "intent_type": intent["type"],
        "selected_bucket": selected_bucket,
        "result_pool_id": result_pool_id,
        "result_total": total,
        "parsed_conditions": parsed_conditions,
        "condition_hit_count": condition_hit_count,
        "condition_evidence": condition_evidence,
        "provider": source_status["provider"],
        "data_as_of": source_status["data_as_of"],
        "cache_status": source_status["cache_status"],
        "data_status": source_status["status"],
        "provider_status": source_status.get("provider_status") or "",
        "source_type": source_status.get("type") or "",
        "response_type": source_status.get("response_type") or "",
        "schema_signature": source_status.get("schema_signature") or "",
        "retry_after_seconds": source_status.get("retry_after_seconds") or "",
        "local_wait_seconds": source_status.get("local_wait_seconds") or "",
        "failure_type": issue["type"],
        "status_reason": issue["reason"],
        "next_action": issue["next_action"],
        "rank_reason": f"问财条件: {' / '.join(item['raw_text'] for item in parsed_conditions) or query}",
    }
    if request_generation is not None:
        source_context["request_generation"] = request_generation
    return source_context


# ── 研报整合 + LLM 解读 ──

class ReportAnalyzeRequest(BaseModel):
    title: str
    content: str
    stock_code: str = ""
    stock_name: str = ""


@router.get("/reports/{code}")
async def get_stock_reports(code: str, page: int = 1, page_size: int = 10):
    """获取个股研报列表（东方财富）"""
    import re
    if not re.match(r'^\d{6}$', code):
        raise HTTPException(400, "股票代码必须为6位数字")
    import time
    import asyncio
    from data.collector.http_client import fetch_json

    try:
        url = (
            f"https://reportapi.eastmoney.com/report/list"
            f"?industryCode=*&pageSize={page_size}&industry=*&rating=*&ratingChange=*&beginTime=2024-01-01"
            f"&endTime=&pageNo={page}&fields=&qType=0&orgCode=&code={code}"
            f"&rcode=&p={page}&pageNum={page}&pageSize={page_size}"
            f"&_={int(time.time() * 1000)}"
        )
        data = await asyncio.to_thread(fetch_json, url, None, 10.0, {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://data.eastmoney.com",
        })

        reports = []
        for item in (data.get("data") or [])[:page_size]:
            reports.append({
                "title": item.get("title", ""),
                "org": item.get("orgSName", ""),
                "author": item.get("researcher", ""),
                "date": (item.get("publishDate", ""))[:10],
                "rating": item.get("emRatingName", ""),
                "target_price": _safe_float(item.get("predictThisYearPe")),
                "summary": item.get("content", "")[:200] if item.get("content") else "",
                "url": f"https://data.eastmoney.com/report/zw/stock.jshtml?encodeUrl={item.get('encodeUrl', '')}",
            })

        return {
            "success": True,
            "code": code,
            "reports": reports,
            "total": data.get("totalHits", 0),
            "page": page,
        }
    except Exception as e:
        logger.error(f"获取研报失败 {code}: {e}")
        return {"success": False, "error": "获取研报失败，请稍后重试", "reports": []}


@router.post("/reports/analyze")
async def analyze_report(req: ReportAnalyzeRequest):
    """用 LLM 解读研报内容"""
    try:
        stock_info = f"（{req.stock_code} {req.stock_name}）" if req.stock_code else ""
        prompt = f"""请用简洁中文解读以下研报{stock_info}，输出格式：
1. 核心观点（2-3句话）
2. 评级与目标价
3. 关键风险点
4. 投资建议

研报标题：{req.title}
研报内容：
{req.content[:3000]}"""

        result = await nl_strategy.chat(prompt)
        text = ""
        async for token in result:
            text += token
        return {"success": True, "analysis": text}
    except Exception as e:
        logger.error(f"研报解读异常: {e}")
        return {"success": False, "error": "AI 解读失败，请稍后重试"}


# ── 对话持久化 ──

class ConversationSaveRequest(BaseModel):
    id: str
    title: str = "新对话"
    messages: list[ChatMessage] = []


@router.get("/conversations")
async def list_conversations(account: dict | None = Depends(optional_account)):
    """获取对话列表"""
    from data.storage.storage import DataStorage
    storage = DataStorage()
    workspace_id = account["workspace"]["id"] if account else ""
    return storage.list_conversations(workspace_id=workspace_id)


@router.get("/conversations/{conv_id}")
async def get_conversation(conv_id: str, account: dict | None = Depends(optional_account)):
    """获取单个对话"""
    from data.storage.storage import DataStorage
    storage = DataStorage()
    workspace_id = account["workspace"]["id"] if account else ""
    conv = storage.get_conversation(conv_id, workspace_id=workspace_id)
    if not conv:
        return {"success": False, "error": "对话不存在"}
    return {"success": True, "data": conv}


@router.post("/conversations")
async def save_conversation(req: ConversationSaveRequest, account: dict | None = Depends(optional_account)):
    """保存对话"""
    from data.storage.storage import DataStorage
    storage = DataStorage()
    workspace_id = account["workspace"]["id"] if account else ""
    msgs = [{"role": m.role, "content": m.content} for m in req.messages]
    storage.save_conversation(req.id, req.title, msgs, workspace_id=workspace_id)
    return {"success": True}


@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: str, account: dict | None = Depends(optional_account)):
    """删除对话"""
    from data.storage.storage import DataStorage
    storage = DataStorage()
    workspace_id = account["workspace"]["id"] if account else ""
    ok = storage.delete_conversation(conv_id, workspace_id=workspace_id)
    return {"success": ok}
