"""System tools exposed to OpenClaw under platform permissions."""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from fastapi import HTTPException
from loguru import logger

from dashboard.account_store import account_store
from data.storage.storage import DataStorage, _normalize_storage_code
from engine.models import Direction, OrderType, PaperConfig
from engine.order_manager import OrderManager
from engine.performance_analyzer import PerformanceAnalyzer
from utils.db import get_connection

storage = DataStorage()
paper_config = PaperConfig()
order_manager = OrderManager(paper_config.db_path)
performance_analyzer = PerformanceAnalyzer(paper_config.db_path)


SYSTEM_TOOLS = [
    {
        "name": "quant.watchlist.add",
        "label": "加入自选股",
        "permission": "write_watchlist",
        "description": "把指定 A 股股票加入当前用户自选股。",
        "schema": {"code": "6 位股票代码"},
        "confirm": False,
    },
    {
        "name": "quant.watchlist.remove",
        "label": "移出自选股",
        "permission": "write_watchlist",
        "description": "从当前用户自选股移除股票。",
        "schema": {"code": "6 位股票代码"},
        "confirm": False,
    },
    {
        "name": "quant.watchlist.list",
        "label": "查看自选股",
        "permission": "read_market",
        "description": "读取当前自选股及行情摘要。",
        "schema": {},
        "confirm": False,
    },
    {
        "name": "quant.stock.open",
        "label": "打开股票详情",
        "permission": "read_market",
        "description": "返回前端可跳转的股票详情链接和基础信息。",
        "schema": {"code": "6 位股票代码"},
        "confirm": False,
    },
    {
        "name": "quant.paper.order",
        "label": "模拟盘下单",
        "permission": "write_paper_trade",
        "description": "创建模拟盘订单。仅模拟盘，不连接实盘。",
        "schema": {
            "code": "6 位股票代码",
            "direction": "buy 或 sell",
            "volume": "股数，A 股应为 100 的整数倍",
            "order_type": "market 或 limit",
            "price": "限价单价格，可选",
            "reason": "下单原因，可选",
        },
        "confirm": True,
    },
    {
        "name": "quant.paper.close_position",
        "label": "模拟盘平仓",
        "permission": "write_paper_trade",
        "description": "创建模拟盘平仓卖出订单。",
        "schema": {"code": "6 位股票代码", "volume": "可选，不填则全平"},
        "confirm": True,
    },
    {
        "name": "quant.paper.summary",
        "label": "模拟盘摘要",
        "permission": "read_portfolio",
        "description": "读取模拟盘绩效、持仓和近期订单摘要。",
        "schema": {},
        "confirm": False,
    },
    {
        "name": "quant.valuation.peg",
        "label": "PEG 估值快照",
        "permission": "read_market",
        "description": "读取单只 A 股的机构预测、成长、PEG、目标价和研报摘要。",
        "schema": {"code": "6 位股票代码", "report_limit": "研报数量，可选"},
        "confirm": False,
    },
    {
        "name": "quant.data.snapshot",
        "label": "数据底座快照",
        "permission": "read_market",
        "description": "读取当前工作区的数据覆盖率、行情缓存、估值覆盖和数据源状态。",
        "schema": {},
        "confirm": False,
    },
    {
        "name": "quant.signals.top",
        "label": "AI 信号 Top",
        "permission": "read_market",
        "description": "读取 Signal Engine 最新全市场候选 Top 股票。",
        "schema": {"top_n": "返回数量，可选"},
        "confirm": False,
    },
    {
        "name": "quant.qlib.top",
        "label": "AI 信号 Top",
        "permission": "read_market",
        "description": "兼容旧调用，读取 Signal Engine 最新候选 Top 股票。",
        "schema": {"top_n": "返回数量，可选"},
        "confirm": False,
    },
    {
        "name": "quant.iwencai.evidence.review",
        "label": "问财证据审查",
        "permission": "read_market",
        "description": "只读审查后端生成的 iWencai provider_evidence，用于判断证据、降级和写入门禁状态。",
        "schema": {"provider_evidence": "后端 /api/llm/iwencai 返回的 provider_evidence，可选 source_context.provider_evidence"},
        "confirm": False,
    },
    {
        "name": "quant.report.generate_daily",
        "label": "生成模拟盘收益日报",
        "permission": "read_portfolio",
        "description": "生成并保存某日模拟盘收益日报。",
        "schema": {"trade_date": "YYYY-MM-DD，可选，默认今天"},
        "confirm": False,
    },
    {
        "name": "quant.report.open",
        "label": "查看模拟盘收益日报",
        "permission": "read_portfolio",
        "description": "打开当前工作区指定日期的模拟盘收益日报。",
        "schema": {"trade_date": "YYYY-MM-DD"},
        "confirm": False,
    },
    {
        "name": "quant.skill.record",
        "label": "记录 Skill",
        "permission": "manage_skills",
        "description": "记录当前工作区已安装或待安装的 OpenClaw Skill，用于权限审计。",
        "schema": {"name": "Skill 名称", "version": "版本，可选", "source": "来源，可选"},
        "confirm": True,
    },
]


TOOL_MAP = {tool["name"]: tool for tool in SYSTEM_TOOLS}


def require_tool_permission(account: dict, tool: dict) -> None:
    permission = tool.get("permission", "")
    if permission and not (account.get("permissions") or {}).get(permission):
        raise HTTPException(status_code=403, detail=f"缺少工具权限: {permission}")


def normalize_code_or_400(code: str) -> str:
    _, plain_code = _normalize_storage_code(code)
    if not plain_code:
        raise HTTPException(status_code=400, detail="股票代码格式非法")
    return plain_code


async def invoke_system_tool(account: dict, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    tool = TOOL_MAP.get(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail="系统工具不存在")
    require_tool_permission(account, tool)

    user_id = account["user"]["id"]
    workspace_id = account["workspace"]["id"]
    arguments = {
        **(arguments or {}),
        "workspace_id": workspace_id,
        "user_id": user_id,
        "sessionKey": account["workspace"]["openclaw_workspace_id"],
    }
    status = "ok"
    reason = ""
    result: dict[str, Any]

    try:
        if tool_name == "quant.watchlist.add":
            result = _watchlist_add(arguments)
        elif tool_name == "quant.watchlist.remove":
            result = _watchlist_remove(arguments)
        elif tool_name == "quant.watchlist.list":
            result = {"items": storage.get_watchlist_with_info(workspace_id)}
        elif tool_name == "quant.stock.open":
            result = _stock_open(arguments)
        elif tool_name == "quant.paper.order":
            result = _paper_order(arguments)
        elif tool_name == "quant.paper.close_position":
            result = _paper_close_position(arguments)
        elif tool_name == "quant.paper.summary":
            result = _paper_summary()
        elif tool_name == "quant.valuation.peg":
            result = _valuation_peg(arguments)
        elif tool_name == "quant.data.snapshot":
            result = _data_snapshot(arguments)
        elif tool_name in {"quant.signals.top", "quant.qlib.top"}:
            result = _signals_top(arguments)
        elif tool_name == "quant.iwencai.evidence.review":
            result = _iwencai_evidence_review(arguments)
        elif tool_name == "quant.report.generate_daily":
            result = _generate_daily_report(account, arguments)
        elif tool_name == "quant.report.open":
            result = _open_daily_report(account, arguments)
        elif tool_name == "quant.skill.record":
            result = _skill_record(account, arguments)
        else:
            raise HTTPException(status_code=404, detail="系统工具不存在")
    except HTTPException as exc:
        status = "denied" if exc.status_code in (401, 403) else "error"
        reason = str(exc.detail)
        account_store.record_audit(
            "openclaw.system_tool.invoke",
            user_id=user_id,
            workspace_id=workspace_id,
            target_type="tool",
            target_id=tool_name,
            tool_name=tool_name,
            status=status,
            reason=reason,
            metadata={"arguments": _redact_arguments(arguments)},
        )
        raise
    except Exception as exc:
        logger.exception(f"OpenClaw 系统工具调用失败: {tool_name}")
        status = "error"
        reason = str(exc)
        account_store.record_audit(
            "openclaw.system_tool.invoke",
            user_id=user_id,
            workspace_id=workspace_id,
            target_type="tool",
            target_id=tool_name,
            tool_name=tool_name,
            status=status,
            reason=reason,
            metadata={"arguments": _redact_arguments(arguments)},
        )
        raise HTTPException(status_code=500, detail="工具调用失败")

    account_store.record_audit(
        "openclaw.system_tool.invoke",
        user_id=user_id,
        workspace_id=workspace_id,
        target_type="tool",
        target_id=tool_name,
        tool_name=tool_name,
        status=status,
        reason=reason,
        metadata={"arguments": _redact_arguments(arguments), "result_preview": _preview(result)},
    )
    _auto_record_research_memory(account, tool_name, arguments, result)
    return {
        "success": True,
        "tool": tool_name,
        "permission": tool["permission"],
        "result": result,
    }


def _watchlist_add(arguments: dict[str, Any]) -> dict[str, Any]:
    code = normalize_code_or_400(str(arguments.get("code") or ""))
    workspace_id = str(arguments.get("workspace_id") or arguments.get("sessionKey") or "")
    added = storage.add_to_watchlist(code, workspace_id)
    return {
        "code": code,
        "added": added,
        "message": "添加成功" if added else "已在自选股中",
    }


def _watchlist_remove(arguments: dict[str, Any]) -> dict[str, Any]:
    code = normalize_code_or_400(str(arguments.get("code") or ""))
    workspace_id = str(arguments.get("workspace_id") or arguments.get("sessionKey") or "")
    removed = storage.remove_from_watchlist(code, workspace_id)
    return {"code": code, "removed": removed}


def _stock_open(arguments: dict[str, Any]) -> dict[str, Any]:
    code = normalize_code_or_400(str(arguments.get("code") or ""))
    stock_list = storage.get_stock_list()
    name = ""
    if not stock_list.empty:
        matched = stock_list[stock_list["code"].astype(str).str.replace(r"^(sh|sz)", "", regex=True) == code]
        if not matched.empty:
            name = str(matched.iloc[0].get("name") or "")
    return {
        "code": code,
        "name": name,
        "tab": "stock",
        "hash": f"#stock",
        "query": {"code": code},
        "frontend_action": {"type": "open_stock_detail", "code": code},
    }


def _paper_order(arguments: dict[str, Any]) -> dict[str, Any]:
    code = normalize_code_or_400(str(arguments.get("code") or ""))
    direction = Direction.from_value(str(arguments.get("direction") or "buy"))
    order_type = OrderType(str(arguments.get("order_type") or "market"))
    volume = int(arguments.get("volume") or 0)
    price = arguments.get("price")
    if volume <= 0 or volume % 100 != 0:
        raise HTTPException(status_code=400, detail="模拟盘下单数量必须是 100 的正整数倍")
    if order_type != OrderType.MARKET and price is None:
        raise HTTPException(status_code=400, detail="非市价单需要价格")
    order = order_manager.create_order(
        code=code,
        direction=direction,
        order_type=order_type,
        volume=volume,
        price=float(price) if price not in (None, "") else None,
        strategy_name="openclaw",
        signal_reason=str(arguments.get("reason") or "OpenClaw 模拟盘指令"),
    )
    return {"order": order.to_dict(), "message": "模拟盘订单已创建"}


def _paper_close_position(arguments: dict[str, Any]) -> dict[str, Any]:
    code = normalize_code_or_400(str(arguments.get("code") or ""))
    requested = arguments.get("volume")
    conn = get_connection(paper_config.db_path)
    try:
        row = conn.execute("SELECT * FROM paper_positions WHERE code = ?", (code,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"持仓不存在: {code}")
        close_volume = int(requested or row["volume"])
        if close_volume <= 0 or close_volume > row["volume"]:
            raise HTTPException(status_code=400, detail="平仓数量不合法")
    finally:
        conn.close()
    order = order_manager.create_order(
        code=code,
        direction=Direction.SHORT,
        order_type=OrderType.MARKET,
        volume=close_volume,
        strategy_name="openclaw",
        signal_reason=str(arguments.get("reason") or "OpenClaw 模拟盘平仓"),
    )
    return {"order": order.to_dict(), "message": "模拟盘平仓订单已创建"}


def _paper_summary() -> dict[str, Any]:
    metrics = performance_analyzer.calculate_metrics(initial_cash=paper_config.initial_cash)
    conn = get_connection(paper_config.db_path, readonly=True)
    try:
        positions = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM paper_positions ORDER BY market_value DESC LIMIT 20"
            ).fetchall()
        ]
        orders = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM paper_orders ORDER BY created_at DESC LIMIT 10"
            ).fetchall()
        ]
    finally:
        conn.close()
    return {
        "metrics": metrics.to_dict(),
        "positions": positions,
        "recent_orders": orders,
    }


def _valuation_peg(arguments: dict[str, Any]) -> dict[str, Any]:
    from data.services.valuation_service import ValuationService

    code = normalize_code_or_400(str(arguments.get("code") or ""))
    report_limit = int(arguments.get("report_limit") or 8)
    return ValuationService(storage=storage).build_snapshot(code, report_limit=max(1, min(report_limit, 20)))


def _data_snapshot(arguments: dict[str, Any]) -> dict[str, Any]:
    import time

    workspace_id = str(arguments.get("workspace_id") or "")
    watchlist = storage.get_watchlist(workspace_id)
    quote = {
        "running": False,
        "subscriptions": 0,
        "cache_count": 0,
        "last_update_age_sec": None,
    }
    try:
        from data.collector.quote_service import get_quote_service

        quote_service = get_quote_service()
        last_update = quote_service.last_update_time
        quote = {
            "running": quote_service.is_running,
            "subscriptions": quote_service.subscription_count,
            "cache_count": quote_service.cache_count,
            "last_update_age_sec": round(time.time() - last_update, 1) if last_update else None,
        }
    except Exception:
        pass
    return {
        "stock_count": len(storage.get_all_stock_codes()),
        "watchlist_count": len(watchlist),
        "quote": quote,
        "providers": {
            "market": "mootdx + eastmoney + tencent fallback",
            "valuation": "eastmoney analyst consensus adapter",
            "ml": "Signal Engine local_momentum cache",
        },
    }


def _signals_top(arguments: dict[str, Any]) -> dict[str, Any]:
    from dashboard.routers.qlib import PRED_CACHE_FILE, _enrich_with_stock_info
    from data.signals.engine import get_signal_records

    top_n = max(1, min(int(arguments.get("top_n") or 10), 50))
    records, meta = get_signal_records(top_n=top_n, cache_path=PRED_CACHE_FILE)
    if not records:
        return {
            "predictions": [],
            "date": meta.get("latest_date"),
            "total": meta.get("total") or 0,
            "provider": meta.get("provider") or "local_momentum",
            "model_version": meta.get("model_version") or "",
        }
    codes = [record.code for record in records]
    info_map = _enrich_with_stock_info(codes)
    predictions = []
    for record in records:
        info = info_map.get(record.code, {})
        predictions.append({
            "code": record.code,
            "raw_code": record.code,
            "name": info.get("name", record.code),
            "score": round(float(record.score), 6),
            "rank": record.rank,
            "provider": record.provider,
            "model_version": record.model_version,
            "confidence": record.confidence,
            "industry": info.get("industry", "--"),
            "price": info.get("price"),
        })
    return {
        "predictions": predictions,
        "date": meta.get("latest_date"),
        "total": meta.get("total") or len(records),
        "provider": meta.get("provider") or "local_momentum",
        "model_version": meta.get("model_version") or "",
    }


def _qlib_top(arguments: dict[str, Any]) -> dict[str, Any]:
    return _signals_top(arguments)


IWENCAI_EVIDENCE_SCHEMA_VERSION = "iwencai_provider_evidence_v1"
IWENCAI_REVIEW_SCHEMA_VERSION = "iwencai_evidence_review_v1"
SECRET_KEY_RE = re.compile(
    r"(password|passwd|token|secret|cookie|authorization|api[_-]?key|apikey|headers?|session|invite|credential)",
    re.IGNORECASE,
)
SECRET_TEXT_RE = re.compile(
    r"(?i)(bearer\s+[A-Za-z0-9._~+/=-]{8,}|"
    r"(?:api[_-]?key|token|secret|password|cookie|authorization|invite[_-]?code)\s*[:=]\s*(?:bearer\s+)?[^,;\s}]+)"
)


def _iwencai_evidence_review(arguments: dict[str, Any]) -> dict[str, Any]:
    evidence = _extract_iwencai_provider_evidence(arguments)
    if not evidence:
        return {
            "schema_version": IWENCAI_REVIEW_SCHEMA_VERSION,
            "input_trust": "caller_supplied_not_live_provider",
            "review_status": "missing_evidence",
            "evidence_status": {"present": False, "schema_version": ""},
            "write_action_gate": _iwencai_review_write_gate({}, reason="missing_provider_evidence"),
            "recommended_safe_next_actions": [
                "先通过后端 /api/llm/iwencai 获取 provider_evidence。",
                "在证据缺失时仅保留只读解释，不生成篮子、回测草案或写入自选。",
            ],
            "notes": ["该工具不调用真实 provider，不替代生产凭证或实时 schema 验证。"],
        }

    safe_evidence = _redact_value(evidence)
    schema_version = str(safe_evidence.get("schema_version") or "")
    if schema_version and schema_version != IWENCAI_EVIDENCE_SCHEMA_VERSION:
        return {
            "schema_version": IWENCAI_REVIEW_SCHEMA_VERSION,
            "input_trust": "caller_supplied_not_live_provider",
            "review_status": "unsupported_schema",
            "evidence_status": {
                "present": True,
                "schema_version": schema_version,
                "expected_schema_version": IWENCAI_EVIDENCE_SCHEMA_VERSION,
            },
            "write_action_gate": _iwencai_review_write_gate(safe_evidence, reason="unsupported_schema"),
            "recommended_safe_next_actions": [
                "要求上游重新提供后端生成的 iwencai_provider_evidence_v1。",
                "保持只读，不把未知证据结构继续传递给写入或回测链路。",
            ],
            "notes": ["该工具只审查紧凑 evidence 摘要，不信任原始 provider payload。"],
        }

    summary_status = str(safe_evidence.get("summary_status") or "unknown")
    field_coverage = str(safe_evidence.get("field_coverage_status") or "unknown")
    candidate_validation = _coerce_dict(safe_evidence.get("candidate_validation"))
    condition_counts = _coerce_dict(safe_evidence.get("condition_status_counts"))
    degradation = _coerce_dict(safe_evidence.get("degradation"))
    review_status = _iwencai_review_status(summary_status, field_coverage, candidate_validation, degradation)

    return {
        "schema_version": IWENCAI_REVIEW_SCHEMA_VERSION,
        "input_trust": "caller_supplied_not_live_provider",
        "review_status": review_status,
        "evidence_status": {
            "present": True,
            "schema_version": schema_version or IWENCAI_EVIDENCE_SCHEMA_VERSION,
            "summary_status": summary_status,
            "provider": safe_evidence.get("provider") or "iwencai",
            "provider_status": safe_evidence.get("provider_status") or "",
            "data_status": safe_evidence.get("data_status") or "",
            "data_as_of": safe_evidence.get("data_as_of") or "",
            "cache_status": safe_evidence.get("cache_status") or "",
            "result_pool_id": safe_evidence.get("result_pool_id") or "",
            "reported_total": _safe_int(safe_evidence.get("reported_total")),
            "candidate_count": _safe_int(safe_evidence.get("candidate_count")),
            "field_coverage_status": field_coverage,
        },
        "condition_validation": {
            "status_counts": condition_counts,
            "samples": _iwencai_condition_samples(safe_evidence),
        },
        "candidate_validation": {
            "verified": _safe_int(candidate_validation.get("verified")),
            "partial": _safe_int(candidate_validation.get("partial")),
            "unverified": _safe_int(candidate_validation.get("unverified")),
            "missing": _safe_int(candidate_validation.get("missing")),
            "actionable": _safe_int(candidate_validation.get("actionable")),
        },
        "degradation": {
            "type": degradation.get("type") or "",
            "reason": degradation.get("reason") or "",
            "next_action": degradation.get("next_action") or "",
            "cache_status": degradation.get("cache_status") or safe_evidence.get("cache_status") or "",
            "retry_after_seconds": degradation.get("retry_after_seconds") or "",
            "local_wait_seconds": degradation.get("local_wait_seconds") or "",
            "response_type": degradation.get("response_type") or "",
            "schema_signature": degradation.get("schema_signature") or "",
        },
        "write_action_gate": _iwencai_review_write_gate(safe_evidence, reason="read_only_review_tool"),
        "recommended_safe_next_actions": _iwencai_recommended_actions(
            review_status,
            summary_status,
            safe_evidence,
            candidate_validation,
            degradation,
        ),
        "notes": [
            "该工具只消费调用方传入的 provider_evidence 摘要，不发起真实 iWencai、OpenClaw、LLM、回测或交易调用。",
            "任何自选、篮子、回测或交易动作仍必须走独立工具、权限和确认链。",
        ],
    }


def _extract_iwencai_provider_evidence(arguments: dict[str, Any]) -> dict[str, Any]:
    for key in ("provider_evidence", "evidence"):
        value = arguments.get(key)
        if isinstance(value, dict):
            return value
    for key in ("source_context", "context", "iwencai"):
        value = arguments.get(key)
        if isinstance(value, dict) and isinstance(value.get("provider_evidence"), dict):
            return value["provider_evidence"]
    return {}


def _coerce_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _iwencai_review_status(
    summary_status: str,
    field_coverage: str,
    candidate_validation: dict[str, Any],
    degradation: dict[str, Any],
) -> str:
    if summary_status in {"failed", "error"}:
        return "failed_review"
    if summary_status in {"empty", "no_match"}:
        return "empty_review"
    if summary_status == "degraded" or degradation.get("type"):
        return "degraded_review"
    if summary_status == "partial" or field_coverage == "partial" or _safe_int(candidate_validation.get("partial")):
        return "partial_review"
    if summary_status == "verified" and field_coverage in {"verified", "no_conditions"}:
        return "verified_read_only"
    return "needs_review"


def _iwencai_condition_samples(evidence: dict[str, Any], limit: int = 6) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    conditions = evidence.get("condition_evidence")
    if not isinstance(conditions, list):
        return samples
    for item in conditions[:limit]:
        if not isinstance(item, dict):
            continue
        samples.append(
            {
                "raw_text": item.get("raw_text") or "",
                "field": item.get("field") or "",
                "hit_count": item.get("hit_count"),
                "hit_count_status": item.get("hit_count_status") or item.get("status") or "",
                "evidence_level": item.get("evidence_level") or "",
                "source_field": item.get("source_field") or "",
                "missing_reason": item.get("missing_reason") or "",
            }
        )
    return samples


def _iwencai_review_write_gate(evidence: dict[str, Any], *, reason: str) -> dict[str, Any]:
    enabled = evidence.get("enabled_write_actions")
    blocked = evidence.get("blocked_write_actions")
    return {
        "allowed_by_review_tool": False,
        "reason": reason,
        "evidence_allows_write_actions": bool(evidence.get("write_actions_allowed")),
        "enabled_write_actions": enabled if isinstance(enabled, list) else [],
        "blocked_write_actions": blocked if isinstance(blocked, list) else [],
        "requires_separate_tool_and_confirmation": bool(evidence.get("write_actions_allowed")),
    }


def _iwencai_recommended_actions(
    review_status: str,
    summary_status: str,
    evidence: dict[str, Any],
    candidate_validation: dict[str, Any],
    degradation: dict[str, Any],
) -> list[str]:
    if review_status == "failed_review":
        return [
            "保持只读解释，展示 provider 失败原因。",
            "等待限流/网络/凭证问题恢复后重新获取 provider_evidence。",
        ]
    if review_status == "empty_review":
        return [
            "提示用户调整自然语言条件或缩小歧义。",
            "不要生成篮子、回测草案或写入自选。",
        ]
    if review_status == "degraded_review":
        action = str(degradation.get("next_action") or "").strip()
        base = ["保持只读解释，并把降级原因展示给用户。"]
        if action:
            base.append(f"建议下一步：{action}")
        base.append("刷新到 verified/partial 证据前，不继续写入或执行回测。")
        return base
    if review_status == "partial_review":
        return [
            "可以继续只读解释、打开个股或人工复核候选池。",
            "字段覆盖或候选验证不完整时，不自动生成篮子或回测草案。",
        ]
    if review_status == "verified_read_only":
        actionable = _safe_int(candidate_validation.get("actionable"))
        if actionable > 0 or _safe_int(evidence.get("candidate_count")) > 0:
            return [
                "可以继续只读解释、打开个股详情或把证据交给人工复核。",
                "若要生成篮子或回测草案，必须通过独立写入/草案入口和确认链执行。",
            ]
        return ["证据结构已验证，但候选池为空；继续只读解释或调整问句。"]
    return [
        f"当前 evidence summary_status={summary_status or 'unknown'}，需要人工复核。",
        "在复核完成前保持只读，不触发写入、回测或交易链路。",
    ]


def _generate_daily_report(account: dict, arguments: dict[str, Any]) -> dict[str, Any]:
    from config.datetime_utils import today_beijing

    trade_date = str(arguments.get("trade_date") or today_beijing())
    summary = _paper_summary()
    trades = _trades_for_date(trade_date)
    metrics = summary["metrics"]
    positions = summary["positions"]
    title = f"{trade_date} 模拟盘收益日报"
    content = {
        "trade_date": trade_date,
        "summary": {
            "total_equity": metrics.get("total_equity"),
            "daily_return": metrics.get("daily_return"),
            "cumulative_return": metrics.get("cumulative_return"),
            "max_drawdown": metrics.get("max_drawdown"),
            "win_rate": metrics.get("win_rate"),
            "total_trades": metrics.get("total_trades"),
        },
        "positions": positions,
        "trades": trades,
        "review": _build_report_review(metrics, positions, trades),
    }
    report = account_store.save_daily_report(
        user_id=account["user"]["id"],
        workspace_id=account["workspace"]["id"],
        trade_date=trade_date,
        title=title,
        content=content,
    )
    return {"report": report}


def _open_daily_report(account: dict, arguments: dict[str, Any]) -> dict[str, Any]:
    trade_date = str(arguments.get("trade_date") or "").strip()
    if not trade_date:
        raise HTTPException(status_code=400, detail="请提供 trade_date")
    report = account_store.get_daily_report(account["workspace"]["id"], trade_date)
    if not report:
        raise HTTPException(status_code=404, detail=f"日报不存在: {trade_date}")
    return {"report": report}


def _trades_for_date(trade_date: str) -> list[dict[str, Any]]:
    conn = get_connection(paper_config.db_path, readonly=True)
    try:
        rows = conn.execute(
            """SELECT * FROM paper_trades
            WHERE substr(created_at, 1, 10) = ?
            ORDER BY created_at DESC""",
            (trade_date,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _build_report_review(metrics: dict[str, Any], positions: list[dict[str, Any]], trades: list[dict[str, Any]]) -> list[str]:
    lines = []
    daily_return = metrics.get("daily_return") or 0
    lines.append(f"当日收益率 {daily_return:.2%}，累计收益率 {(metrics.get('cumulative_return') or 0):.2%}。")
    if positions:
        top = positions[0]
        lines.append(f"最大持仓为 {top.get('code')}，市值 {top.get('market_value', 0):.2f}。")
    else:
        lines.append("当前无持仓，适合复盘空仓原因和下一交易日观察列表。")
    if trades:
        lines.append(f"当日有 {len(trades)} 笔成交，需要重点复盘信号来源、滑点和仓位占比。")
    else:
        lines.append("当日没有成交，重点检查策略是否过于保守或条件未触发。")
    return lines


def _skill_record(account: dict, arguments: dict[str, Any]) -> dict[str, Any]:
    name = str(arguments.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Skill 名称不能为空")
    skill = account_store.upsert_skill(
        workspace_id=account["workspace"]["id"],
        name=name,
        version=str(arguments.get("version") or ""),
        status=str(arguments.get("status") or "installed"),
        source=str(arguments.get("source") or "openclaw"),
        permissions=list(arguments.get("permissions") or []),
    )
    return {"skill": skill}


def _auto_record_research_memory(
    account: dict,
    tool_name: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
) -> None:
    code = str(arguments.get("code") or result.get("code") or result.get("order", {}).get("code") or "").strip()
    reason = str(arguments.get("reason") or "").strip()
    specs = {
        "quant.watchlist.add": {
            "title": "加入自选",
            "tags": ["watchlist", "关注"],
            "content": "通过龙虾加入自选。",
        },
        "quant.watchlist.remove": {
            "title": "移出自选",
            "tags": ["watchlist", "复盘"],
            "content": "通过龙虾移出自选。",
        },
        "quant.stock.open": {
            "title": "打开详情",
            "tags": ["stock_detail", "研究"],
            "content": "通过龙虾打开股票详情。",
        },
        "quant.paper.order": {
            "title": "模拟盘下单",
            "tags": ["paper_trade", "交易原因"],
            "content": "通过龙虾创建模拟盘订单。",
        },
        "quant.paper.close_position": {
            "title": "模拟盘平仓",
            "tags": ["paper_trade", "平仓原因"],
            "content": "通过龙虾创建模拟盘平仓订单。",
        },
        "quant.report.generate_daily": {
            "title": "生成收益日报",
            "tags": ["daily_report", "复盘"],
            "content": "通过龙虾生成模拟盘收益日报。",
        },
        "quant.report.open": {
            "title": "查看收益日报",
            "tags": ["daily_report", "复盘"],
            "content": "通过龙虾查看模拟盘收益日报。",
        },
    }
    spec = specs.get(tool_name)
    if not spec:
        return

    details = [spec["content"]]
    if reason:
        details.append(f"原因：{reason}")
    if tool_name == "quant.paper.order":
        order = result.get("order") or {}
        details.append(
            "订单："
            f"{order.get('direction') or arguments.get('direction') or '--'} "
            f"{order.get('volume') or arguments.get('volume') or '--'} 股，"
            f"{order.get('order_type') or arguments.get('order_type') or '--'}。"
        )
    if tool_name == "quant.report.generate_daily":
        report = result.get("report") or {}
        details.append(f"日期：{report.get('trade_date') or arguments.get('trade_date') or '默认交易日'}")
    if tool_name == "quant.report.open":
        report = result.get("report") or {}
        details.append(f"日期：{report.get('trade_date') or arguments.get('trade_date') or '默认交易日'}")

    title_code = f" {code}" if code else ""
    try:
        account_store.create_memory(
            user_id=account["user"]["id"],
            workspace_id=account["workspace"]["id"],
            title=f"{spec['title']}{title_code}",
            content="\n".join(details),
            code=code,
            tags=spec["tags"],
            source="openclaw:auto",
        )
    except Exception:
        logger.exception(f"自动记录 OpenClaw 研究记忆失败: {tool_name}")


def _redact_value(value: Any, key: str = "", depth: int = 0) -> Any:
    if key and SECRET_KEY_RE.search(key):
        return "***"
    if depth > 8:
        return "[truncated]"
    if isinstance(value, dict):
        return {str(item_key): _redact_value(item_value, str(item_key), depth + 1) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_redact_value(item, "", depth + 1) for item in value[:100]]
    if isinstance(value, tuple):
        return [_redact_value(item, "", depth + 1) for item in value[:100]]
    if isinstance(value, str):
        return SECRET_TEXT_RE.sub("***", value)
    return value


def _redact_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    redacted = _redact_value(arguments or {})
    return redacted if isinstance(redacted, dict) else {}


def _preview(result: dict[str, Any]) -> dict[str, Any]:
    text = str(result)
    return {"text": text[:500], "truncated": len(text) > 500}
