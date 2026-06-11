"""Unified Signal Engine API."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query

from config.settings import DB_PATH, QLIB_PRED_CACHE
from data.signals.engine import DEFAULT_PROVIDER, get_signal_records, load_prediction_history
from data.signals.validation import validate_signal_provider
from dashboard.routers.qlib import _enrich_with_stock_info

router = APIRouter()
SIGNAL_API_META = {
    "runtime_boundary": "signals",
    "raw_source_role": "legacy_cache",
}


def _light_validation(provider: str, meta: dict) -> dict:
    return {
        "provider": meta.get("provider") or provider or DEFAULT_PROVIDER,
        "model_version": meta.get("model_version") or "",
        "confidence": "unverified",
        "sample_days": 0,
        "status": "fast_mode",
        "message": "fast health skips historical validation; signal is treated as unverified until validation endpoint completes",
        "penalty_applied": True,
        "metrics": {},
    }


def _enrich_records(records):
    codes = [record.code for record in records]
    info_map = _enrich_with_stock_info(codes)
    rows = []
    for record in records:
        row = record.to_dict(legacy_keys=True)
        info = info_map.get(record.code, {})
        row.update(
            {
                "name": info.get("name", record.code),
                "industry": info.get("industry", "--"),
                "sector": info.get("sector", ""),
                "industry_source": info.get("industry_source", "missing"),
                "price": info.get("price"),
                "volume": info.get("volume"),
                "amount": info.get("amount"),
            }
        )
        rows.append(row)
    return rows


@router.get("/top")
async def top_signals(
    provider: str = Query(DEFAULT_PROVIDER),
    top_n: int = Query(50, ge=1, le=500, alias="limit"),
    date: str = Query(""),
):
    records, meta = get_signal_records(
        provider=provider,
        top_n=top_n,
        date=date or None,
        cache_path=QLIB_PRED_CACHE,
    )
    if meta.get("error"):
        return {
            "success": False,
            "signals": [],
            "predictions": [],
            "primary_collection": "signals",
            "legacy_aliases": {"predictions": "signals"},
            **SIGNAL_API_META,
            **meta,
        }
    rows = _enrich_records(records)
    return {
        "success": True,
        "signals": rows,
        "predictions": rows,
        "primary_collection": "signals",
        "legacy_aliases": {"predictions": "signals"},
        **SIGNAL_API_META,
        "date": records[0].date if records else meta.get("latest_date"),
        "total": meta.get("total") or 0,
        "provider": meta.get("provider") or DEFAULT_PROVIDER,
        "model_version": meta.get("model_version") or "",
        "raw_source": meta.get("raw_source") or "legacy_qlib",
        "generated_at": meta.get("generated_at"),
    }


@router.get("/health")
async def signal_health(
    provider: str = Query(DEFAULT_PROVIDER),
    fast: bool = Query(False, description="只返回缓存状态，不同步计算历史验证"),
):
    predictions, meta = load_prediction_history(provider=provider, cache_path=QLIB_PRED_CACHE)
    validation = None
    if not fast:
        validation = validate_signal_provider(
            provider=provider,
            db_path=DB_PATH,
            cache_path=QLIB_PRED_CACHE,
            top_n=50,
        )
    status = "online" if predictions else "offline"
    payload = {
        "success": True,
        "status": status,
        "primary_collection": "signals",
        "legacy_aliases": {"predictions": "signals"},
        "legacy_adapters": {"qlib": "/api/qlib/health"},
        **SIGNAL_API_META,
        "provider": meta.get("provider") or provider,
        "model_version": meta.get("model_version") or "",
        "latest_date": meta.get("latest_date"),
        "total": meta.get("total") or 0,
        "raw_source": meta.get("raw_source") or "legacy_qlib",
        "fast_mode": fast,
    }
    payload["validation"] = validation.to_dict() if validation is not None else _light_validation(provider, meta)
    return payload


@router.get("/validation")
async def signal_validation(
    provider: str = Query(DEFAULT_PROVIDER),
    top_n: int = Query(50, ge=1, le=500),
):
    summary = await asyncio.to_thread(
        validate_signal_provider,
        provider=provider,
        db_path=DB_PATH,
        cache_path=QLIB_PRED_CACHE,
        top_n=top_n,
    )
    return {"success": True, **summary.to_dict()}


@router.get("/consistency")
async def signal_consistency(
    provider: str = Query(DEFAULT_PROVIDER),
    top_n: int = Query(50, ge=1, le=500),
):
    """查询 AI 信号一致性，保留 legacy qlib 计算作为兼容实现。"""
    from dashboard.routers.qlib import get_consistency

    payload = await get_consistency(top_n=top_n)
    if not isinstance(payload, dict):
        return payload

    response = dict(payload)
    response.setdefault("provider", provider or DEFAULT_PROVIDER)
    response.setdefault("raw_source", "legacy_qlib")
    response.setdefault("legacy_adapter", "/api/qlib/consistency")
    items = response.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            item.setdefault("signal_provider", response["provider"])
            item.setdefault("signal_score", item.get("score"))
            item.setdefault("signal_consistency", item.get("ic_adj"))
            item.setdefault("signal_appearances", item.get("appearances"))
    return response


@router.post("/train")
async def train_signal_model():
    """触发 AI 信号模型刷新。"""
    from dashboard.routers.qlib import qlib_train

    payload = await qlib_train()
    if not isinstance(payload, dict):
        return payload
    return {
        **payload,
        "primary_action": "refresh_signals",
        "legacy_adapter": "/api/qlib/train",
        "adapter_for": "signals",
    }


@router.get("/train/status")
async def signal_train_status():
    """查询 AI 信号模型刷新状态。"""
    from dashboard.routers.qlib import qlib_train_status

    payload = await qlib_train_status()
    if not isinstance(payload, dict):
        return payload
    return {
        **payload,
        "primary_action": "refresh_signals_status",
        "legacy_adapter": "/api/qlib/train/status",
        "adapter_for": "signals",
    }
