"""Unified Signal Engine API."""
from __future__ import annotations

from fastapi import APIRouter, Query

from config.settings import DB_PATH, QLIB_PRED_CACHE
from data.signals.engine import DEFAULT_PROVIDER, get_signal_records, load_prediction_history
from data.signals.validation import validate_signal_provider
from dashboard.routers.qlib import _enrich_with_stock_info

router = APIRouter()


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
        return {"success": False, "signals": [], "predictions": [], **meta}
    rows = _enrich_records(records)
    return {
        "success": True,
        "signals": rows,
        "predictions": rows,
        "date": records[0].date if records else meta.get("latest_date"),
        "total": meta.get("total") or 0,
        "provider": meta.get("provider") or DEFAULT_PROVIDER,
        "model_version": meta.get("model_version") or "",
        "raw_source": meta.get("raw_source") or "legacy_qlib",
        "generated_at": meta.get("generated_at"),
    }


@router.get("/health")
async def signal_health(provider: str = Query(DEFAULT_PROVIDER)):
    predictions, meta = load_prediction_history(provider=provider, cache_path=QLIB_PRED_CACHE)
    validation = validate_signal_provider(
        provider=provider,
        db_path=DB_PATH,
        cache_path=QLIB_PRED_CACHE,
        top_n=50,
    )
    status = "online" if predictions else "offline"
    return {
        "success": True,
        "status": status,
        "provider": meta.get("provider") or provider,
        "model_version": meta.get("model_version") or "",
        "latest_date": meta.get("latest_date"),
        "total": meta.get("total") or 0,
        "raw_source": meta.get("raw_source") or "legacy_qlib",
        "validation": validation.to_dict(),
    }


@router.get("/validation")
async def signal_validation(
    provider: str = Query(DEFAULT_PROVIDER),
    top_n: int = Query(50, ge=1, le=500),
):
    summary = validate_signal_provider(
        provider=provider,
        db_path=DB_PATH,
        cache_path=QLIB_PRED_CACHE,
        top_n=top_n,
    )
    return {"success": True, **summary.to_dict()}


@router.post("/train")
async def train_signal_model():
    """触发 AI 信号模型刷新。"""
    from dashboard.routers.qlib import qlib_train

    return await qlib_train()


@router.get("/train/status")
async def signal_train_status():
    """查询 AI 信号模型刷新状态。"""
    from dashboard.routers.qlib import qlib_train_status

    return await qlib_train_status()
