"""市场雷达 API

端点：
- GET /api/market/radar       — 综合雷达（涨跌幅/振幅/换手率/量比 TOP 10）
- GET /api/market/sectors     — 板块轮动排名
- GET /api/market/northbound  — 北向资金净流入
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter
from loguru import logger

from data.collector.cache import TTLCache
from data.collector.http_client import fetch_json

router = APIRouter()
_cache = TTLCache(max_size=100)
_TTL_RADAR = 30   # 30 秒缓存
_TTL_SECTOR = 60
_TTL_NORTH = 120


# ── 全市场行情 TOP N ──

def _fetch_all_stocks() -> list[dict]:
    """从东方财富获取全市场股票行情（复用 screener 逻辑）"""
    from alpha.screener import _fetch_market_stocks
    return _fetch_market_stocks()


def _get_top_n(stocks: list[dict], field: str, n: int = 10, desc: bool = True) -> list[dict]:
    """获取指定字段 TOP N"""
    valid = [s for s in stocks if s.get(field) is not None]
    valid.sort(key=lambda s: s[field], reverse=desc)
    return valid[:n]


@router.get("/radar")
async def get_market_radar():
    """市场雷达：涨跌幅/振幅/换手率/量比 TOP 10"""
    cache_key = "market_radar"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached

    try:
        stocks = await asyncio.to_thread(_fetch_all_stocks)
        if not stocks:
            return {"success": False, "error": "无法获取行情数据"}

        def pick(field, n=10, desc=True):
            return [
                {"code": s["code"], "name": s.get("name", ""), "value": round(s[field], 2)}
                for s in _get_top_n(stocks, field, n, desc)
            ]

        result = {
            "success": True,
            "top_gainers": pick("change_pct"),
            "top_losers": pick("change_pct", desc=False),
            "top_amplitude": pick("amplitude"),
            "top_turnover": pick("turnover_rate"),
            "top_volume_ratio": pick("volume_ratio"),
            "total_stocks": len(stocks),
        }
        _cache.set(cache_key, result, _TTL_RADAR)
        return result
    except Exception as e:
        logger.error(f"市场雷达失败: {e}")
        return {"success": False, "error": str(e)}


# ── 板块轮动 ──

def _fetch_sector_ranking(sector_type: str = "industry") -> list[dict]:
    """获取板块涨跌排名

    sector_type: industry(行业) / concept(概念)
    """
    fs_map = {
        "industry": "m:90+t:2",
        "concept": "m:90+t:3",
    }
    fs = fs_map.get(sector_type, fs_map["industry"])
    url = (
        f"https://push2delay.eastmoney.com/api/qt/clist/get"
        f"?pn=1&pz=30&po=1&np=1&fltt=2&invt=2"
        f"&fid=f3&fs={fs}&fields=f2,f3,f12,f14,f104,f105,f128,f136,f140"
    )
    data = fetch_json(url, timeout=10)
    items = ((data.get("data") or {}).get("diff") or [])

    sectors = []
    for item in items:
        sectors.append({
            "code": item.get("f12", ""),
            "name": item.get("f14", ""),
            "change_pct": round(float(item.get("f3", 0)) / 100, 2) if item.get("f3") else 0,
            "up_count": int(item.get("f104", 0)),
            "down_count": int(item.get("f105", 0)),
            "leader": item.get("f140", ""),
            "leader_change": round(float(item.get("f136", 0)) / 100, 2) if item.get("f136") else 0,
        })
    return sectors


@router.get("/sectors")
async def get_sector_ranking(type: str = "industry"):
    """板块轮动排名"""
    cache_key = f"sectors:{type}"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached

    try:
        sectors = await asyncio.to_thread(_fetch_sector_ranking, type)
        result = {"success": True, "sectors": sectors, "type": type}
        _cache.set(cache_key, result, _TTL_SECTOR)
        return result
    except Exception as e:
        logger.error(f"板块排名失败: {e}")
        return {"success": False, "error": str(e), "sectors": []}


# ── 北向资金 ──

def _fetch_northbound() -> dict:
    """获取北向资金净流入数据"""
    url = (
        "https://push2delay.eastmoney.com/api/qt/kamt.rtmin/get"
        "?fields1=f1,f2,f3,f4&fields2=f51,f52,f53,f54,f55,f56"
    )
    data = fetch_json(url, timeout=10)

    s2n = data.get("s2n", [])  # 沪股通+深股通
    if not s2n:
        return {"today_net": 0, "today_sh_net": 0, "today_sz_net": 0, "flow": []}

    flow = []
    for item in s2n[-30:]:  # 最近 30 个时间点
        parts = item.split(",") if isinstance(item, str) else []
        if len(parts) >= 4:
            flow.append({
                "time": parts[0],
                "sh_net": round(float(parts[1]) / 10000, 2) if parts[1] != '-' else 0,
                "sz_net": round(float(parts[2]) / 10000, 2) if parts[2] != '-' else 0,
                "total_net": round(float(parts[3]) / 10000, 2) if parts[3] != '-' else 0,
            })

    # 最新净流入
    today_sh = flow[-1]["sh_net"] if flow else 0
    today_sz = flow[-1]["sz_net"] if flow else 0
    today_total = flow[-1]["total_net"] if flow else 0

    return {
        "today_net": today_total,
        "today_sh_net": today_sh,
        "today_sz_net": today_sz,
        "flow": flow,
    }


@router.get("/northbound")
async def get_northbound():
    """北向资金净流入"""
    cache_key = "northbound"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached

    try:
        data = await asyncio.to_thread(_fetch_northbound)
        result = {"success": True, **data}
        _cache.set(cache_key, result, _TTL_NORTH)
        return result
    except Exception as e:
        logger.error(f"北向资金查询失败: {e}")
        return {"success": False, "error": str(e), "today_net": 0, "flow": []}
