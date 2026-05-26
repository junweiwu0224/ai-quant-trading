"""热点归因分析模块。

使用项目已有的东方财富 HTTP 数据源，避免情报页自动加载时触发
AKShare/同花顺接口内部的原生 JS 引擎崩溃。
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from urllib.parse import quote

from loguru import logger

from data.collector.http_client import fetch_json


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value in (None, "-"):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default: int = 0) -> int:
    try:
        if value in (None, "-"):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _fetch_board_ranking(board_type: str, top_n: int) -> list[dict]:
    """从东方财富获取行业/概念板块涨跌排名。"""
    fs_map = {
        "concept": "m:90+t:3",
        "industry": "m:90+t:2",
    }
    fs = fs_map.get(board_type, fs_map["concept"])
    url = (
        "https://push2delay.eastmoney.com/api/qt/clist/get"
        f"?pn=1&pz={max(top_n, 1)}&po=1&np=1&fltt=2&invt=2"
        f"&fid=f3&fs={fs}&fields=f2,f3,f12,f14,f104,f105,f128,f136,f140,f20"
    )
    data = fetch_json(url, timeout=10)
    items = ((data.get("data") or {}).get("diff") or [])

    records: list[dict] = []
    for item in items[:top_n]:
        records.append({
            "code": str(item.get("f12", "") or ""),
            "name": str(item.get("f14", "") or ""),
            "change_pct": round(_safe_float(item.get("f3")), 2),
            "leader": str(item.get("f140", "") or item.get("f128", "") or ""),
            "leader_change": round(_safe_float(item.get("f136")), 2),
            "stock_count": _safe_int(item.get("f104")) + _safe_int(item.get("f105")),
            "up_count": _safe_int(item.get("f104")),
            "down_count": _safe_int(item.get("f105")),
            "total_mv": round(_safe_float(item.get("f20")) / 1e8, 0),
        })
    return records


def _fetch_sector_fund_flow(top_n: int) -> list[dict]:
    """从东方财富资金流接口获取行业主力净流入。"""
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get"
        f"?pn=1&pz={max(top_n, 1)}&po=1&np=1&fltt=2&invt=2"
        "&fid=f62&fs=m:90+t:2&fields=f12,f14,f3,f62,f184"
    )
    data = fetch_json(url, timeout=10)
    items = ((data.get("data") or {}).get("diff") or [])

    records: list[dict] = []
    for item in items[:top_n]:
        records.append({
            "code": str(item.get("f12", "") or ""),
            "name": str(item.get("f14", "") or ""),
            "change_pct": round(_safe_float(item.get("f3")), 2),
            "main_net_inflow": round(_safe_float(item.get("f62")) / 1e8, 2),
            "main_net_inflow_pct": round(_safe_float(item.get("f184")), 2),
        })
    return records


async def get_hot_concepts(top_n: int = 20) -> list[dict]:
    """获取当前热门概念板块排名。"""
    try:
        return await asyncio.to_thread(_fetch_board_ranking, "concept", top_n)
    except Exception as e:
        logger.warning(f"获取热门概念失败: {e}")
        return []


async def get_hot_industries(top_n: int = 20) -> list[dict]:
    """获取当前热门行业板块排名。"""
    try:
        return await asyncio.to_thread(_fetch_board_ranking, "industry", top_n)
    except Exception as e:
        logger.warning(f"获取热门行业失败: {e}")
        return []


async def get_sector_fund_flow(top_n: int = 20) -> list[dict]:
    """获取行业板块资金流向排名。"""
    try:
        return await asyncio.to_thread(_fetch_sector_fund_flow, top_n)
    except Exception as e:
        logger.warning(f"获取行业资金流失败: {e}")
        return []


async def get_concept_for_stock(code: str) -> list[str]:
    """获取个股所属概念列表。"""
    normalized = str(code).strip()
    if len(normalized) != 6 or not normalized.isdigit():
        return []

    try:
        market = "SH" if normalized.startswith(("6", "9")) else "SZ"
        secucode = quote(f"{normalized}.{market}", safe="")
        url = (
            "https://datacenter.eastmoney.com/securities/api/data/v1/get"
            "?reportName=RPT_F10_CORETHEME_BOARDTYPE"
            "&columns=SECURITY_CODE%2CBOARD_NAME%2CBOARD_TYPE"
            f"&filter=(SECURITY_CODE%3D%22{secucode}%22)"
            "&pageNumber=1&pageSize=50&source=HSF10&client=PC"
        )

        def fetch() -> list[str]:
            data = fetch_json(url, timeout=10, headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://emweb.securities.eastmoney.com/",
            })
            rows = ((data.get("result") or {}).get("data") or [])
            concepts = [str(row.get("BOARD_NAME", "") or "") for row in rows]
            return [name for name in concepts if name]

        return await asyncio.to_thread(fetch)
    except Exception as e:
        logger.warning(f"获取个股概念失败({code}): {e}")
        return []


async def get_hotspot_attribution() -> dict:
    """综合热点归因分析。"""
    concepts, industries, flow = await asyncio.gather(
        get_hot_concepts(10),
        get_hot_industries(10),
        get_sector_fund_flow(10),
        return_exceptions=True,
    )

    if isinstance(concepts, Exception):
        logger.warning(f"热点概念获取失败: {concepts}")
        concepts = []
    if isinstance(industries, Exception):
        logger.warning(f"热门行业获取失败: {industries}")
        industries = []
    if isinstance(flow, Exception):
        logger.warning(f"资金流向获取失败: {flow}")
        flow = []

    top3 = [f"{c['name']}({c['change_pct']:+.1f}%)" for c in (concepts or [])[:3]]
    summary = f"今日热点：{'、'.join(top3)}" if top3 else "暂无热点数据"

    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "hot_concepts": concepts or [],
        "hot_industries": industries or [],
        "fund_flow": flow or [],
        "summary": summary,
    }
