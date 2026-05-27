"""Data source health, coverage and decision matrix routes."""
from __future__ import annotations

import math
import statistics
import time
from collections import defaultdict
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query

from dashboard.session import current_account, optional_account
from data.providers.astock_data_adapter import normalize_stock_code
from data.qlib.candidates import fallback_seed_codes
from data.storage.storage import DataStorage

router = APIRouter()


def _plain_code(code: Any) -> str:
    normalized = normalize_stock_code(str(code or ""))
    return normalized or ""


def _dedupe_codes(codes: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for code in codes:
        normalized = _plain_code(code)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _safe_float(value: Any) -> float | None:
    if value in (None, "", "-", "--"):
        return None
    try:
        val = float(value)
        return val if math.isfinite(val) else None
    except Exception:
        return None


def _age_label(hours: float | None) -> str:
    if hours is None:
        return "未知"
    if hours < 1:
        return f"{round(hours * 60)}分钟"
    if hours < 48:
        return f"{round(hours, 1)}小时"
    return f"{round(hours / 24, 1)}天"


def _load_qlib_health() -> dict[str, Any]:
    try:
        from dashboard.routers.qlib import PRED_CACHE_FILE, _load_sync_status

        if not PRED_CACHE_FILE.exists():
            return {
                "status": "offline",
                "cache_age_hours": None,
                "cache_age_label": "无缓存",
                "sync_status": _load_sync_status(),
            }
        age_hours = (time.time() - PRED_CACHE_FILE.stat().st_mtime) / 3600
        if age_hours < 24:
            status = "online"
        elif age_hours < 72:
            status = "stale"
        else:
            status = "offline"
        return {
            "status": status,
            "cache_age_hours": round(age_hours, 1),
            "cache_age_label": _age_label(age_hours),
            "sync_status": _load_sync_status(),
        }
    except Exception:
        return {
            "status": "offline",
            "cache_age_hours": None,
            "cache_age_label": "未知",
            "sync_status": {},
        }


def _load_shadow_summary() -> dict[str, Any]:
    try:
        from data.collector.shadow_validator import get_shadow_stats

        stats = get_shadow_stats()
        return {
            "date": stats.get("date"),
            "total_checks": stats.get("total_checks", 0),
            "total_diffs": stats.get("total_diffs", 0),
            "codes_with_diffs": stats.get("codes_with_diffs", 0),
            "consistency_rate": stats.get("consistency_rate"),
        }
    except Exception:
        return {
            "date": None,
            "total_checks": 0,
            "total_diffs": 0,
            "codes_with_diffs": 0,
            "consistency_rate": None,
        }


def _load_qlib_context(top_limit: int = 300) -> dict[str, Any]:
    """Read local qlib prediction cache and build per-code rank/consistency."""
    try:
        from dashboard.routers.qlib import _load_predictions

        cache = _load_predictions()
    except Exception:
        cache = {}

    if not cache:
        return {"latest_date": None, "total": 0, "items": {}, "ordered_codes": []}

    latest_date = max(cache.keys())
    latest_preds = cache.get(latest_date) or {}
    if not isinstance(latest_preds, dict) or not latest_preds:
        return {"latest_date": latest_date, "total": 0, "items": {}, "ordered_codes": []}

    sorted_latest = sorted(
        ((_plain_code(code), _safe_float(score)) for code, score in latest_preds.items()),
        key=lambda item: item[1] if item[1] is not None else -1e9,
        reverse=True,
    )
    sorted_latest = [(code, score) for code, score in sorted_latest if code and score is not None]
    top_codes = {code for code, _ in sorted_latest[:top_limit]}

    history: dict[str, list[float]] = defaultdict(list)
    for day, preds in cache.items():
        if day == latest_date or not isinstance(preds, dict):
            continue
        for raw_code, raw_score in preds.items():
            code = _plain_code(raw_code)
            score = _safe_float(raw_score)
            if code in top_codes and score is not None:
                history[code].append(score)

    items: dict[str, dict[str, Any]] = {}
    ordered_codes: list[str] = []
    for rank, (code, score) in enumerate(sorted_latest, start=1):
        if code in items:
            continue
        hist = history.get(code, [])
        hist_std = None
        ic_adj = None
        if len(hist) >= 3:
            try:
                hist_std = statistics.pstdev(hist)
                if hist_std > 0:
                    ic_adj = round(float(score) / hist_std, 4)
            except Exception:
                hist_std = None
                ic_adj = None
        items[code] = {
            "qlib_rank": rank,
            "qlib_score": round(float(score), 6),
            "qlib_ic_adj": ic_adj,
            "qlib_diamond": bool(ic_adj is not None and ic_adj > 2),
            "qlib_appearances": len(hist),
        }
        ordered_codes.append(code)

    return {
        "latest_date": latest_date,
        "total": len(sorted_latest),
        "items": items,
        "ordered_codes": ordered_codes,
    }


def _score_decision(item: dict[str, Any], qlib: dict[str, Any] | None) -> dict[str, Any]:
    peg = _safe_float(item.get("peg_next_year"))
    growth = _safe_float(item.get("growth_next_year_pct"))
    upside = _safe_float(item.get("upside_pct"))
    change_pct = _safe_float(item.get("change_pct"))
    volume_ratio = _safe_float(item.get("volume_ratio"))
    quote_age_sec = _safe_float(item.get("quote_age_sec"))
    report_count = int(item.get("report_count") or 0)
    qlib_rank = int((qlib or {}).get("qlib_rank") or 0)
    qlib_diamond = bool((qlib or {}).get("qlib_diamond"))

    score = 50
    reasons: list[str] = []
    risks: list[str] = []

    if peg is not None:
        if peg <= 1:
            score += 25
            reasons.append("PEG≤1")
        elif peg <= 1.5:
            score += 15
            reasons.append("PEG合理")
        elif peg <= 2:
            score += 8
            reasons.append("估值可接受")
        elif peg >= 3:
            score -= 15
            risks.append("PEG偏贵")
    else:
        score -= 8
        risks.append("PEG缺失")

    if growth is not None:
        if growth >= 30:
            score += 15
            reasons.append("高增长")
        elif growth >= 15:
            score += 8
            reasons.append("增长稳健")
        elif growth <= 0:
            score -= 15
            risks.append("增长为负")
    else:
        score -= 6
        risks.append("增速缺失")

    if upside is not None:
        if upside >= 20:
            score += 12
            reasons.append("目标价空间大")
        elif upside >= 10:
            score += 6
            reasons.append("仍有空间")
        elif upside <= -10:
            score -= 8
            risks.append("目标价倒挂")

    if qlib_rank:
        if qlib_rank <= 10:
            score += 18
            reasons.append("AI前10")
        elif qlib_rank <= 50:
            score += 10
            reasons.append("AI候选池")
        elif qlib_rank <= 100:
            score += 5
            reasons.append("AI覆盖")
    else:
        risks.append("AI未覆盖")

    if qlib_diamond:
        score += 8
        reasons.append("AI一致性高")

    if report_count >= 5:
        score += 5
        reasons.append("研报覆盖充分")
    elif report_count == 0:
        score -= 10
        risks.append("无研报预测")

    if change_pct is not None:
        if change_pct >= 8:
            risks.append("短线涨幅过热")
        elif change_pct <= -6:
            risks.append("短线破位压力")

    if volume_ratio is not None and volume_ratio >= 2.5:
        reasons.append("量能放大")
        if change_pct is not None and change_pct < 0:
            risks.append("放量下跌")

    if quote_age_sec is not None and quote_age_sec > 900:
        risks.append("行情缓存偏旧")

    score = max(0, min(100, round(score)))
    if score >= 78:
        label = "重点研究"
    elif score >= 62:
        label = "可跟踪"
    elif score >= 45:
        label = "观察"
    else:
        label = "暂缓"

    risk_score = min(100, len(risks) * 18 + (15 if report_count == 0 else 0) + (12 if not qlib_rank else 0))
    if risk_score >= 60:
        risk_level = "高"
    elif risk_score >= 30:
        risk_level = "中"
    else:
        risk_level = "低"

    actions = _build_next_actions(score, peg, growth, upside, qlib_rank, risks)

    return {
        "decision_score": score,
        "decision_label": label,
        "reason_tags": reasons[:5],
        "risk_tags": risks[:5],
        "risk_level": risk_level,
        "next_actions": actions[:4],
        "primary_action": actions[0] if actions else "查看详情",
    }


def _build_next_actions(
    score: int,
    peg: float | None,
    growth: float | None,
    upside: float | None,
    qlib_rank: int,
    risks: list[str],
) -> list[str]:
    actions: list[str] = []
    risk_set = set(risks)

    if score >= 78:
        actions.append("进重点池")
        actions.append("打开估值详情")
        if "短线涨幅过热" in risk_set:
            actions.append("等待回踩")
        else:
            actions.append("模拟小仓验证")
    elif score >= 62:
        actions.append("加入自选跟踪")
        actions.append("补看同业估值")
        if qlib_rank:
            actions.append("问龙虾生成交易计划")
    elif score >= 45:
        actions.append("继续观察")
        actions.append("补齐缺失数据")
    else:
        actions.append("暂缓")
        actions.append("只保留监控")

    if peg is None:
        actions.append("补PEG口径")
    elif peg <= 1 and growth is not None and growth > 0:
        actions.append("查业绩持续性")

    if upside is not None and upside < 0:
        actions.append("核对目标价")

    if not qlib_rank:
        actions.append("等待AI覆盖")

    deduped: list[str] = []
    for action in actions:
        if action not in deduped:
            deduped.append(action)
    return deduped


def _stock_info_map(storage: DataStorage) -> dict[str, dict[str, str]]:
    stock_list = storage.get_stock_list()
    if stock_list.empty:
        return {}
    return {
        _plain_code(row.get("code")): {
            "name": str(row.get("name") or ""),
            "industry": str(row.get("industry") or ""),
        }
        for _, row in stock_list.iterrows()
        if _plain_code(row.get("code"))
    }


def _fallback_seed_codes(storage: DataStorage, limit: int) -> list[str]:
    return fallback_seed_codes(storage, limit)


def _attach_snapshot_metadata(storage: DataStorage, code: str, item: dict[str, Any]) -> dict[str, Any]:
    latest_snapshot = storage.get_latest_data_snapshot(code, "valuation")
    if not latest_snapshot:
        return item
    payload = latest_snapshot.get("payload") or {}
    if isinstance(payload, dict):
        for key in ("source", "source_version", "quality_status", "snapshot_at", "payload_hash"):
            item.pop(key, None)
        for key, value in payload.items():
            item.setdefault(key, value)
    item.update(
        {
            "source": latest_snapshot.get("source"),
            "source_version": latest_snapshot.get("source_version"),
            "quality_status": latest_snapshot.get("quality_status"),
            "snapshot_at": latest_snapshot.get("created_at"),
            "payload_hash": latest_snapshot.get("payload_hash"),
        }
    )
    return item


@router.get("/health")
async def datahub_health(account: dict | None = Depends(optional_account)):
    storage = DataStorage()
    stock_count = len(storage.get_all_stock_codes())
    watchlist = storage.get_watchlist(account["workspace"]["id"]) if account else []
    qlib_health = _load_qlib_health()
    shadow = _load_shadow_summary()
    quality_summary = storage.get_data_quality_summary()
    source_health = storage.get_data_source_health()

    quote_health = {
        "running": False,
        "subscriptions": 0,
        "cache_count": 0,
        "last_update_age_sec": None,
    }
    try:
        from data.collector.quote_service import get_quote_service

        quote_service = get_quote_service()
        last_update = quote_service.last_update_time
        quote_health = {
            "running": quote_service.is_running,
            "subscriptions": quote_service.subscription_count,
            "cache_count": quote_service.cache_count,
            "last_update_age_sec": round(time.time() - last_update, 1) if last_update else None,
        }
    except Exception:
        pass

    valuation_covered = 0
    if watchlist:
        try:
            from data.services.valuation_service import ValuationService

            center = ValuationService(storage=storage).build_center(watchlist, limit=min(len(watchlist), 30))
            valuation_covered = len([item for item in center.get("items", []) if item.get("report_count", 0) > 0])
        except Exception:
            valuation_covered = 0

    return {
        "success": True,
        "stock_count": stock_count,
        "watchlist_count": len(watchlist),
        "source_health": source_health,
        "quality_summary": quality_summary,
        "quote": quote_health,
        "valuation": {
            "covered": valuation_covered,
            "coverage_pct": round(valuation_covered / len(watchlist) * 100, 1) if watchlist else None,
            "quality": storage.get_data_quality_summary("valuation"),
        },
        "quote_quality": storage.get_data_quality_summary("quote"),
        "qlib": qlib_health,
        "shadow": shadow,
        "providers": {
            "market": "mootdx + eastmoney + tencent fallback",
            "valuation": "eastmoney analyst consensus adapter",
            "ml": "qlib prediction cache",
        },
    }


@router.get("/decision-matrix")
async def decision_matrix(
    scope: str = Query("watchlist", pattern="^(watchlist|codes|qlib)$"),
    codes: str = Query("", description="逗号分隔股票代码"),
    limit: int = Query(30, ge=1, le=80),
    fast: bool = Query(False, description="跳过外部估值源，快速返回行情/AI预览"),
    force_fallback: bool = Query(False, description="强制使用默认候选池"),
    account: dict = Depends(current_account),
):
    """Merge valuation, qlib prediction and quote health into one research table."""

    storage = DataStorage()
    qlib_ctx = _load_qlib_context(top_limit=max(200, limit * 3))
    qlib_health = _load_qlib_health()
    shadow = _load_shadow_summary()
    source_health = storage.get_data_source_health()
    quality_summary = storage.get_data_quality_summary()
    qlib_items: dict[str, dict[str, Any]] = qlib_ctx["items"]

    used_fallback = False
    fallback_reason = ""
    if force_fallback:
        selected_codes = _fallback_seed_codes(storage, limit)
        used_fallback = bool(selected_codes)
        fallback_reason = "forced_default"
    elif scope == "watchlist":
        selected_codes = storage.get_watchlist(account["workspace"]["id"])
    elif scope == "qlib":
        selected_codes = qlib_ctx["ordered_codes"][:limit]
    else:
        selected_codes = [item.strip() for item in codes.split(",") if item.strip()]
    selected_codes = _dedupe_codes(selected_codes)[:limit]
    if not selected_codes and scope in {"watchlist", "qlib"}:
        selected_codes = _fallback_seed_codes(storage, limit)
        used_fallback = bool(selected_codes)
        fallback_reason = "watchlist_empty" if scope == "watchlist" else "qlib_empty"

    stock_map = _stock_info_map(storage)
    valuation_items: list[dict[str, Any]] = []
    valuation_error = ""
    if not fast:
        try:
            from data.services.valuation_service import ValuationService

            center = ValuationService(storage=storage).build_center(selected_codes, limit=limit)
            valuation_items = center.get("items", []) if isinstance(center, dict) else []
        except Exception as exc:
            valuation_error = str(exc)
            valuation_items = []

    valuation_by_code = {_plain_code(item.get("code")): item for item in valuation_items if _plain_code(item.get("code"))}
    matrix_items: list[dict[str, Any]] = []

    try:
        from data.collector.quote_service import get_quote_service

        quote_service = get_quote_service()
    except Exception:
        quote_service = None

    for code in selected_codes:
        plain = _plain_code(code)
        if not plain:
            continue
        qlib = qlib_items.get(plain)
        item = dict(valuation_by_code.get(plain) or {})
        info = stock_map.get(plain, {})
        quote_payload: dict[str, Any] = {}
        if quote_service:
            try:
                quote = quote_service.get_quote(plain) or quote_service.get_or_fetch_quote(plain)
                if quote:
                    quote_payload = {
                        "price": _safe_float(getattr(quote, "price", None)),
                        "change_pct": _safe_float(getattr(quote, "change_pct", None)),
                        "turnover_rate": _safe_float(getattr(quote, "turnover_rate", None)),
                        "volume_ratio": _safe_float(getattr(quote, "volume_ratio", None)),
                        "quote_age_sec": round(time.time() - getattr(quote, "timestamp", time.time()), 1),
                    }
                    if not item.get("name"):
                        item["name"] = getattr(quote, "name", "") or info.get("name") or plain
                    if not item.get("industry"):
                        item["industry"] = getattr(quote, "industry", "") or info.get("industry", "")
            except Exception:
                quote_payload = {}

        if not item:
            item = {
                "code": plain,
                "name": info.get("name") or plain,
                "industry": info.get("industry") or "",
                "report_count": 0,
            }
        else:
            item["code"] = plain
            item["name"] = item.get("name") or info.get("name") or plain
            item["industry"] = item.get("industry") or info.get("industry") or ""

        item = _attach_snapshot_metadata(storage, plain, item)
        item.update(quote_payload)
        if qlib:
            item.update(qlib)
        else:
            item.update({
                "qlib_rank": None,
                "qlib_score": None,
                "qlib_ic_adj": None,
                "qlib_diamond": False,
                "qlib_appearances": 0,
            })
        item.update(_score_decision(item, qlib))
        matrix_items.append(item)

    matrix_items.sort(
        key=lambda item: (
            -int(item.get("decision_score") or 0),
            int(item.get("qlib_rank") or 999999),
            _safe_float(item.get("peg_next_year")) if _safe_float(item.get("peg_next_year")) is not None else 999999,
        )
    )
    for rank, item in enumerate(matrix_items, start=1):
        item["matrix_rank"] = rank

    total = len(matrix_items)
    covered_valuation = len([item for item in matrix_items if int(item.get("report_count") or 0) > 0])
    covered_qlib = len([item for item in matrix_items if item.get("qlib_rank")])
    high_score = len([item for item in matrix_items if int(item.get("decision_score") or 0) >= 78])
    cheap = len([
        item for item in matrix_items
        if _safe_float(item.get("peg_next_year")) is not None and _safe_float(item.get("peg_next_year")) <= 1
    ])
    qlib_top = len([
        item for item in matrix_items
        if item.get("qlib_rank") and int(item.get("qlib_rank") or 0) <= 50
    ])
    high_risk = len([item for item in matrix_items if item.get("risk_level") == "高"])
    actionable = len([
        item for item in matrix_items
        if item.get("primary_action") in ("进重点池", "加入自选跟踪", "打开估值详情", "模拟小仓验证")
    ])

    return {
        "success": True,
        "scope": scope,
        "items": matrix_items,
        "summary": {
            "total": total,
            "valuation_coverage_pct": round(covered_valuation / total * 100, 1) if total else None,
            "qlib_coverage_pct": round(covered_qlib / total * 100, 1) if total else None,
            "high_score": high_score,
            "peg_le_1": cheap,
            "qlib_top_50": qlib_top,
            "qlib_date": qlib_ctx.get("latest_date"),
            "qlib_status": qlib_health.get("status"),
            "qlib_cache_age_hours": qlib_health.get("cache_age_hours"),
            "qlib_cache_age_label": qlib_health.get("cache_age_label"),
            "qlib_sync_status": qlib_health.get("sync_status") or {},
            "high_risk": high_risk,
            "actionable": actionable,
            "shadow": shadow,
            "source_health": source_health,
            "quality_summary": quality_summary,
            "used_fallback": used_fallback,
            "fallback_reason": fallback_reason,
            "fast_mode": fast,
            "valuation_error": valuation_error,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        },
    }
