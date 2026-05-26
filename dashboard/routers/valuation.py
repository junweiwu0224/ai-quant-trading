"""Valuation data center routes."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from dashboard.session import current_account, optional_account
from data.services.valuation_service import ValuationService
from data.storage.storage import DataStorage

router = APIRouter()
valuation_service = ValuationService()


@router.get("/health")
async def valuation_health(account: dict | None = Depends(optional_account)):
    storage = DataStorage()
    quality_summary = storage.get_data_quality_summary()
    source_health = storage.get_data_source_health()
    try:
        from dashboard.routers.datahub import _load_qlib_health, _load_shadow_summary

        qlib_health = _load_qlib_health()
        shadow = _load_shadow_summary()
    except Exception:
        qlib_health = {"status": "offline", "cache_age_hours": None, "cache_age_label": "未知"}
        shadow = {"date": None, "total_checks": 0, "total_diffs": 0, "codes_with_diffs": 0}

    watchlist_count = 0
    valuation_covered = 0
    if account:
        watchlist = storage.get_watchlist(account["workspace"]["id"])
        watchlist_count = len(watchlist)
        if watchlist:
            try:
                center = valuation_service.build_center(watchlist, limit=min(len(watchlist), 30))
                valuation_covered = len([item for item in center.get("items", []) if item.get("report_count", 0) > 0])
            except Exception:
                valuation_covered = 0

    return {
        "success": True,
        "source_health": source_health,
        "quality_summary": quality_summary,
        "coverage": {
            "watchlist_count": watchlist_count,
            "valuation_covered": valuation_covered,
            "valuation_coverage_pct": round(valuation_covered / watchlist_count * 100, 1) if watchlist_count else None,
            "quote_records": storage.get_data_quality_summary("quote").get("total", 0),
            "valuation_records": storage.get_data_quality_summary("valuation").get("total", 0),
        },
        "shadow": shadow,
        "qlib": qlib_health,
    }


@router.get("/stock/{code}")
async def stock_valuation(
    code: str,
    report_limit: int = Query(8, ge=1, le=20),
    account: dict = Depends(current_account),
):
    try:
        snapshot = await asyncio.to_thread(valuation_service.build_snapshot, code, report_limit)
        return {"success": True, "data": snapshot}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/center")
async def valuation_center(
    scope: str = Query("watchlist"),
    codes: str = Query("", description="逗号分隔股票代码"),
    limit: int = Query(30, ge=1, le=80),
    max_wait_sec: float | None = Query(None, ge=0, le=30),
    max_peg: float | None = Query(None),
    min_growth: float | None = Query(None),
    min_upside: float | None = Query(None),
    min_reports: int = Query(0, ge=0, le=50),
    bucket: str = Query(""),
    industry: str = Query(""),
    account: dict = Depends(current_account),
):
    code_list = _resolve_scope_codes(scope, codes, account)
    result = await asyncio.to_thread(
        valuation_service.build_filtered_center,
        code_list,
        limit=limit,
        max_peg=max_peg,
        min_growth=min_growth,
        min_upside=min_upside,
        min_reports=min_reports,
        bucket=bucket,
        industry=industry,
    )
    return {
        "success": True,
        "scope": scope,
        **result,
    }


@router.get("/industries")
async def valuation_industries(
    scope: str = Query("watchlist"),
    codes: str = Query("", description="逗号分隔股票代码"),
    limit: int = Query(80, ge=1, le=120),
    account: dict = Depends(current_account),
):
    code_list = _resolve_scope_codes(scope, codes, account)
    result = await asyncio.to_thread(valuation_service.build_industry_summary, code_list, limit)
    return {"success": True, "scope": scope, **result}


@router.get("/peers/{code}")
async def valuation_peers(
    code: str,
    limit: int = Query(12, ge=3, le=30),
    account: dict = Depends(current_account),
):
    try:
        result = await asyncio.to_thread(valuation_service.build_peer_comparison, code, limit)
        return {"success": True, **result}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _resolve_scope_codes(scope: str, codes: str, account: dict) -> list[str]:
    from data.storage.storage import DataStorage

    storage = DataStorage()
    if scope == "watchlist":
        return storage.get_watchlist(account["workspace"]["id"])
    if scope == "codes":
        return [code.strip() for code in codes.split(",") if code.strip()]
    return storage.get_all_stock_codes()
