"""市场雷达 API

端点：
- GET /api/market/radar       — 综合雷达（涨跌幅/振幅/换手率/量比 TOP 10）
- GET /api/market/breadth     — 全市场涨跌广度（本地 stock_daily 覆盖池）
- GET /api/market/sectors     — 板块轮动排名
- GET /api/market/heatmap     — 板块热力图数据（行业+概念，含涨跌幅/市值/涨跌家数）
- GET /api/market/northbound  — 北向资金净流入
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from loguru import logger

from data.collector.cache import TTLCache
from data.collector.http_client import fetch_json
from data.signals.engine import build_signal_context
from data.storage.storage import DataStorage

router = APIRouter()
_cache = TTLCache(max_size=100)
_TTL_RADAR = 30   # 30 秒缓存
_TTL_BREADTH = 60
_TTL_SECTOR = 60
_TTL_NORTH = 120
_MIN_LOCAL_INDUSTRY_COVERAGE = 0.5

# 上一次成功数据（休市时回退用）
_last_radar: dict | None = None
_last_breadth: dict | None = None
_last_sectors: dict | None = None
_last_heatmap: dict | None = None
_last_northbound: dict | None = None

_radar_refresh_task: asyncio.Task | None = None

_EASTMONEY_STOCK_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
_EASTMONEY_STOCK_FIELDS = "f2,f3,f5,f6,f7,f8,f9,f12,f14,f15,f16,f17,f20,f21,f23,f100"
_EASTMONEY_FIELD_MAP = {
    "f2": "price",
    "f3": "change_pct",
    "f5": "volume",
    "f6": "amount",
    "f7": "amplitude",
    "f8": "turnover_rate",
    "f9": "pe_ratio",
    "f12": "code",
    "f14": "name",
    "f15": "high",
    "f16": "low",
    "f17": "open",
    "f20": "market_cap",
    "f21": "circulating_cap",
    "f23": "pb_ratio",
    "f100": "industry",
}
_EASTMONEY_RANK_FIELDS = {
    "top_gainers": ("f3", True, "change_pct"),
    "top_losers": ("f3", False, "change_pct"),
    "top_amplitude": ("f7", True, "amplitude"),
    "top_turnover": ("f8", True, "turnover_rate"),
}


def _schedule_radar_refresh() -> None:
    global _radar_refresh_task

    if _radar_refresh_task is not None and not _radar_refresh_task.done():
        return

    async def _refresh() -> None:
        global _last_radar
        try:
            result = await asyncio.to_thread(_fetch_market_radar_snapshot)
            _cache.set("market_radar", result, _TTL_RADAR)
            _last_radar = result
        except Exception as e:
            logger.warning(f"市场雷达后台刷新失败: {e}")

    _radar_refresh_task = asyncio.create_task(_refresh())


# ── 全市场行情 TOP N ──

def _fetch_all_stocks() -> list[dict]:
    """从东方财富获取全市场股票行情（复用 screener 逻辑）"""
    from alpha.screener import _fetch_market_stocks
    return _fetch_market_stocks()


def _parse_eastmoney_stock(item: dict[str, Any]) -> dict[str, Any]:
    stock: dict[str, Any] = {}
    for api_field, biz_field in _EASTMONEY_FIELD_MAP.items():
        raw = item.get(api_field)
        if raw in (None, "-"):
            stock[biz_field] = None
            continue
        if biz_field in {"code", "name", "industry"}:
            stock[biz_field] = str(raw)
            continue
        try:
            value = float(raw)
            if biz_field in {"market_cap", "circulating_cap"}:
                value = round(value / 1e8, 2)
            stock[biz_field] = value
        except (TypeError, ValueError):
            stock[biz_field] = None
    return stock


def _rank_item(stock: dict[str, Any], value_field: str) -> dict[str, Any]:
    raw_value = stock.get(value_field)
    value = round(float(raw_value), 2) if raw_value is not None else None
    return {
        "code": stock.get("code") or "",
        "name": stock.get("name") or "",
        "value": value,
        "price": stock.get("price"),
        "industry": stock.get("industry") or "",
        "source": "eastmoney_full_market_rank",
    }


def _fetch_market_rank(fid: str, *, desc: bool, value_field: str, n: int = 10) -> tuple[list[dict[str, Any]], int]:
    """Fetch one server-side sorted full-market rank page from Eastmoney."""
    url = (
        "https://push2delay.eastmoney.com/api/qt/clist/get"
        f"?pn=1&pz={max(n, 20)}&po={1 if desc else 0}&np=1&fltt=2&invt=2"
        f"&fid={fid}&fs={_EASTMONEY_STOCK_FS}&fields={_EASTMONEY_STOCK_FIELDS}"
    )
    data = fetch_json(url, timeout=8)
    payload = data.get("data") or {}
    rows = payload.get("diff") or []
    total = int(payload.get("total") or 0)
    ranked = []
    for item in rows[:n]:
        if not isinstance(item, dict):
            continue
        stock = _parse_eastmoney_stock(item)
        if stock.get(value_field) is None:
            continue
        ranked.append(_rank_item(stock, value_field))
    return ranked, total


def _fetch_market_radar_snapshot(n: int = 10) -> dict[str, Any]:
    """Build radar from full A-share server-side rankings, not local samples."""
    result_parts: dict[str, list[dict[str, Any]]] = {}
    totals: list[int] = []
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="market-radar-rank") as pool:
        futures = {
            pool.submit(_fetch_market_rank, fid, desc=desc, value_field=value_field, n=n): key
            for key, (fid, desc, value_field) in _EASTMONEY_RANK_FIELDS.items()
        }
        for future in as_completed(futures):
            key = futures[future]
            rows, total = future.result()
            result_parts[key] = rows
            if total:
                totals.append(total)

    missing = [key for key in _EASTMONEY_RANK_FIELDS if not result_parts.get(key)]
    if missing:
        raise RuntimeError(f"全市场雷达榜单缺失: {', '.join(missing)}")

    return {
        "success": True,
        "top_gainers": result_parts["top_gainers"],
        "top_losers": result_parts["top_losers"],
        "top_amplitude": result_parts["top_amplitude"],
        "top_turnover": result_parts["top_turnover"],
        "total_stocks": max(totals) if totals else None,
        "source": "eastmoney_full_market_rank",
        "universe": "all_a",
        "coverage_note": "东方财富全A股延迟快照，按全市场服务端排序",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def _get_top_n(stocks: list[dict], field: str, n: int = 10, desc: bool = True) -> list[dict]:
    """获取指定字段 TOP N"""
    valid = [s for s in stocks if s.get(field) is not None]
    valid.sort(key=lambda s: s[field], reverse=desc)
    return valid[:n]


def _safe_float(value: Any) -> float | None:
    if value in (None, "", "-", "--"):
        return None
    try:
        val = float(value)
        return val if val == val else None
    except Exception:
        return None


def _local_market_stock_rows(limit: int | None = None) -> list[dict[str, Any]]:
    """Use local stock_daily rows when live full-market data is slow/unavailable."""
    rows = DataStorage().get_latest_market_rows(limit=limit)
    stocks: list[dict[str, Any]] = []
    for row in rows:
        close = _safe_float(row.get("close"))
        prev_close = _safe_float(row.get("prev_close"))
        high = _safe_float(row.get("high"))
        low = _safe_float(row.get("low"))
        amount = _safe_float(row.get("amount"))
        volume = _safe_float(row.get("volume"))
        estimated_amount = amount
        if estimated_amount in (None, 0) and volume is not None and close is not None:
            estimated_amount = volume * close * 100
        change_pct = None
        if close is not None and prev_close not in (None, 0):
            change_pct = (close / prev_close - 1) * 100
        amplitude = None
        if high is not None and low is not None and prev_close not in (None, 0):
            amplitude = (high - low) / prev_close * 100
        activity = estimated_amount / 1e8 if estimated_amount not in (None, 0) else None
        stocks.append(
            {
                "code": str(row.get("code") or ""),
                "name": str(row.get("name") or ""),
                "industry": str(row.get("industry") or ""),
                "price": close,
                "change_pct": change_pct,
                "amplitude": amplitude,
                "turnover_rate": activity,
                "activity": activity,
                "volume": volume,
                "amount": estimated_amount,
                "date": str(row.get("date") or ""),
                "prev_date": str(row.get("prev_date") or ""),
                "source": "local_stock_daily",
            }
        )
    return stocks


def _market_pick(
    stocks: list[dict[str, Any]],
    field: str,
    n: int = 10,
    desc: bool = True,
    *,
    value_field: str | None = None,
) -> list[dict[str, Any]]:
    items = []
    for s in _get_top_n(stocks, field, n, desc):
        raw_value = s.get(value_field or field)
        if raw_value is None:
            continue
        items.append(
            {
                "code": s["code"],
                "name": s.get("name", ""),
                "value": round(float(raw_value), 2),
                "price": s.get("price"),
                "date": s.get("date"),
                "source": s.get("source"),
            }
        )
    return items


def _build_radar_result(stocks: list[dict[str, Any]], *, source: str, local: bool = False) -> dict[str, Any]:
    latest_dates = sorted({str(s.get("date") or "") for s in stocks if s.get("date")})
    result = {
        "success": True,
        "top_gainers": _market_pick(stocks, "change_pct"),
        "top_losers": _market_pick(stocks, "change_pct", desc=False),
        "top_amplitude": _market_pick(stocks, "amplitude"),
        "top_turnover": _market_pick(stocks, "turnover_rate"),
        "total_stocks": len(stocks),
        "source": source,
        "universe": "local_stock_daily_coverage_pool" if local else "all_a",
        "latest_date": latest_dates[-1] if latest_dates else None,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    if local:
        result["local_fallback"] = True
        result["stale"] = True
        result["stale_reason"] = "live_market_slow_or_unavailable"
        result["coverage_note"] = "本地 stock_daily 覆盖股票池，非全市场实时排行"
    return result


def _build_local_radar_result() -> dict[str, Any] | None:
    stocks = _local_market_stock_rows()
    if not stocks:
        return None
    return _build_radar_result(stocks, source="local_stock_daily", local=True)


def _with_fast_path(result: dict[str, Any]) -> dict[str, Any]:
    return {
        **result,
        "fast": True,
        "fast_path": True,
        "fast_path_note": "首屏快路径，优先使用本地覆盖池/缓存，不同步等待外部行情源",
    }


def _empty_heatmap_result(
    *,
    source: str,
    reason: str,
    error: str,
    fast: bool = False,
    coverage_note: str | None = None,
) -> dict[str, Any]:
    result = {
        "success": False,
        "error": error,
        "sectors": [],
        "total": 0,
        "fetched": 0,
        "source": source,
        "universe": "eastmoney_industry_boards_all" if source == "eastmoney_sector_board" else "local_stock_daily_coverage_pool",
        "coverage_note": coverage_note or "板块热力源不可用，当前无可用热力数据",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_unavailable": True,
        "stale": True,
        "stale_reason": reason,
    }
    return _with_fast_path(result) if fast else result


def _build_market_breadth_result() -> dict[str, Any]:
    breadth = DataStorage().get_market_breadth()
    return {
        "success": True,
        **breadth,
        "source": "local_stock_daily",
        "universe": "local_stock_info_all_a",
        "coverage_note": "基于本地 stock_daily 全量覆盖池的最新/上一交易日涨跌统计",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


@router.get("/breadth")
async def get_market_breadth():
    """市场情绪广度：本地全量覆盖池上涨/下跌/平盘/涨跌停统计。"""
    global _last_breadth
    cache_key = "market_breadth"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached

    try:
        result = await asyncio.to_thread(_build_market_breadth_result)
        _cache.set(cache_key, result, _TTL_BREADTH)
        _last_breadth = result
        return result
    except Exception as e:
        logger.error(f"市场广度统计失败: {e}")
        if _last_breadth:
            return {**_last_breadth, "stale": True, "stale_reason": "breadth_refresh_failed"}
        return {
            "success": False,
            "error": str(e),
            "source": "local_stock_daily",
            "universe": "local_stock_info_all_a",
            "total_stocks": 0,
            "up_count": 0,
            "down_count": 0,
            "flat_count": 0,
            "limit_up": 0,
            "limit_down": 0,
        }


@router.get("/radar")
async def get_market_radar(fast: bool = False):
    """市场雷达：全A股涨跌幅/振幅/换手率 TOP 10"""
    global _last_radar
    cache_key = "market_radar:fast" if fast else "market_radar"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached

    if fast:
        local_result = await asyncio.to_thread(_build_local_radar_result)
        if local_result:
            result = _with_fast_path(local_result)
            _cache.set(cache_key, result, _TTL_RADAR)
            _last_radar = result
            return result
        if _last_radar:
            result = _with_fast_path({**_last_radar, "stale": True, "stale_reason": "fast_local_coverage_unavailable"})
            _cache.set(cache_key, result, _TTL_RADAR)
            return result
        return {
            "success": False,
            "fast": True,
            "fast_path": True,
            "error": "本地 stock_daily 覆盖池暂无可用数据",
            "source": "local_stock_daily",
            "universe": "local_stock_daily_coverage_pool",
            "coverage_note": "本地 stock_daily 覆盖池暂无可用数据，市场雷达不可计算",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source_unavailable": True,
            "stale": True,
            "stale_reason": "fast_local_coverage_unavailable",
            "total_stocks": 0,
        }

    if _last_radar:
        if _last_radar.get("source") == "eastmoney_full_market_rank":
            _schedule_radar_refresh()
            return {**_last_radar, "stale": True}

    try:
        result = await asyncio.to_thread(_fetch_market_radar_snapshot)
        _cache.set(cache_key, result, _TTL_RADAR)
        _last_radar = result
        return result
    except Exception as e:
        logger.error(f"市场雷达失败: {e}")
        if _last_radar and _last_radar.get("source") == "eastmoney_full_market_rank":
            return {**_last_radar, "stale": True}
        local_result = await asyncio.to_thread(_build_local_radar_result)
        if local_result:
            _cache.set(cache_key, local_result, _TTL_RADAR)
            _last_radar = local_result
            return local_result
        return {
            "success": False,
            "error": f"全市场行情源不可用: {e}",
            "source": "eastmoney_full_market_rank",
            "universe": "all_a",
            "coverage_note": "东方财富全A股延迟快照不可用，且本地 stock_daily 覆盖池暂无可用数据",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source_unavailable": True,
            "stale": True,
            "stale_reason": "live_and_local_market_unavailable",
            "total_stocks": 0,
        }


def _build_local_sector_rows() -> list[dict[str, Any]]:
    return _build_local_sector_snapshot()["sectors"]


def _exchange_board_name(code: str) -> str:
    plain = str(code or "").lower()
    if plain.startswith(("sh", "sz", "bj")):
        plain = plain[2:]
    if plain.startswith(("43", "83", "87", "88", "92")):
        return "北交所"
    if plain.startswith(("688", "689")):
        return "科创板"
    if plain.startswith(("300", "301", "302")):
        return "创业板"
    if plain.startswith(("600", "601", "603", "605")):
        return "沪主板"
    if plain.startswith(("000", "001", "002", "003")):
        return "深主板"
    return "其他A股"


def _build_local_sector_snapshot() -> dict[str, Any]:
    stocks = _local_market_stock_rows()
    total_stocks = len(stocks)
    industry_covered = len([s for s in stocks if str(s.get("industry") or "").strip()])
    industry_coverage_pct = round((industry_covered / total_stocks) * 100, 2) if total_stocks else 0
    grouping = "industry" if total_stocks and industry_coverage_pct >= (_MIN_LOCAL_INDUSTRY_COVERAGE * 100) else "exchange_board"

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for stock in stocks:
        industry = str(stock.get("industry") or "").strip()
        if grouping == "industry":
            name = industry or "未分类"
        else:
            name = _exchange_board_name(str(stock.get("code") or ""))
        groups[name].append(stock)

    sectors = []
    for name, items in groups.items():
        changes = [float(s["change_pct"]) for s in items if s.get("change_pct") is not None]
        if not changes:
            continue
        leader = max(items, key=lambda s: s.get("change_pct") if s.get("change_pct") is not None else -999)
        turnover_amount = round(sum(float(s.get("amount") or 0) for s in items) / 1e8, 2)
        sectors.append(
            {
                "code": name,
                "name": name,
                "change_pct": round(sum(changes) / len(changes), 2),
                "stock_count": len(items),
                "up_count": len([s for s in items if (s.get("change_pct") or 0) > 0]),
                "down_count": len([s for s in items if (s.get("change_pct") or 0) < 0]),
                "leader": leader.get("name") or leader.get("code") or "",
                "leader_code": leader.get("code") or "",
                "leader_change": round(float(leader.get("change_pct") or 0), 2),
                "total_mv": 0,
                "turnover_amount": turnover_amount,
                "main_net_inflow": 0,
                "source": "local_stock_daily",
                "grouping": grouping,
                "weight_basis": "stock_count",
            }
        )
    sectors.sort(key=lambda item: item["change_pct"], reverse=True)
    return {
        "sectors": sectors,
        "grouping": grouping,
        "weight_basis": "stock_count",
        "stock_count": total_stocks,
        "industry_covered": industry_covered,
        "industry_coverage_pct": industry_coverage_pct,
    }


def _local_sector_coverage_note(snapshot: dict[str, Any], kind: str) -> str:
    grouping = snapshot.get("grouping")
    coverage = snapshot.get("industry_coverage_pct", 0)
    if grouping == "industry":
        return f"本地 stock_daily 覆盖股票池行业{kind}，行业覆盖 {coverage}% ，按覆盖股票数权重"
    return f"本地 stock_daily 覆盖股票池交易板块{kind}，stock_info 行业覆盖 {coverage}% ，按覆盖股票数权重"


def _sector_member_group_name(stock: dict[str, Any], grouping: str) -> str:
    if grouping == "industry":
        return str(stock.get("industry") or "").strip() or "未分类"
    return _exchange_board_name(str(stock.get("code") or ""))


def _fmt_amount_yi(value: float | int | None) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value) / 1e8, 2)
    except (TypeError, ValueError):
        return None


def _build_sector_signal_overlap(members: list[dict[str, Any]]) -> dict[str, Any]:
    codes = {str(item.get("code") or "").strip() for item in members if item.get("code")}
    if not codes:
        return {
            "count": 0,
            "items": [],
            "missing_reason": "板块暂无成分股，无法计算 Signal 重叠",
        }
    try:
        signal_context = build_signal_context(top_limit=500)
    except Exception as exc:
        return {
            "count": 0,
            "items": [],
            "missing_reason": f"Signal 覆盖池读取失败: {exc}",
        }

    signal_items = signal_context.get("items") if isinstance(signal_context, dict) else {}
    if not isinstance(signal_items, dict) or not signal_items:
        return {
            "count": 0,
            "items": [],
            "provider": (signal_context or {}).get("provider") if isinstance(signal_context, dict) else "",
            "model_version": (signal_context or {}).get("model_version") if isinstance(signal_context, dict) else "",
            "latest_date": (signal_context or {}).get("latest_date") if isinstance(signal_context, dict) else "",
            "missing_reason": "Signal 覆盖池暂无可用记录",
        }

    name_by_code = {str(item.get("code") or ""): str(item.get("name") or item.get("code") or "") for item in members}
    matched = []
    for code in codes:
        signal = signal_items.get(code)
        if not signal:
            continue
        matched.append({
            "code": code,
            "name": name_by_code.get(code, code),
            "signal_rank": signal.get("signal_rank") or signal.get("qlib_rank"),
            "signal_score": signal.get("signal_score") if signal.get("signal_score") is not None else signal.get("qlib_score"),
            "signal_confidence": signal.get("signal_confidence") or "unverified",
        })
    matched.sort(key=lambda item: item.get("signal_rank") or 10_000)
    payload = {
        "count": len(matched),
        "items": matched[:8],
        "provider": signal_context.get("provider") or "",
        "model_version": signal_context.get("model_version") or "",
        "latest_date": signal_context.get("latest_date") or "",
        "raw_source": signal_context.get("raw_source") or "",
        "coverage_note": f"Signal Top 500 与本板块成分重叠 {len(matched)} 只",
    }
    if not matched:
        payload["missing_reason"] = "Signal Top 500 暂无本板块成分股"
    return payload


def _build_sector_evidence_context(
    *,
    sector_name: str,
    grouping: str,
    members: list[dict[str, Any]],
    display_members: list[dict[str, Any]],
    generated_at: str,
    total_pool: int,
) -> dict[str, Any]:
    changes = [float(item.get("change_pct") or 0) for item in members]
    amounts = [float(item.get("amount") or 0) for item in members if item.get("amount") is not None]
    up_count = len([value for value in changes if value > 0])
    down_count = len([value for value in changes if value < 0])
    flat_count = max(len(members) - up_count - down_count, 0)
    avg_change = round(sum(changes) / len(changes), 2) if changes else 0
    leader = members[0] if members else None
    top_amount_member = max(members, key=lambda item: float(item.get("amount") or 0), default=None)
    total_amount = sum(amounts) if amounts else 0
    signal_overlap = _build_sector_signal_overlap(members)

    return {
        "sector_name": sector_name,
        "grouping": grouping,
        "generated_at": generated_at,
        "universe": "local_stock_daily_coverage_pool",
        "summary": {
            "title": f"{sector_name} 板块证据",
            "member_count": len(members),
            "display_count": len(display_members),
            "source_pool_count": total_pool,
            "avg_change_pct": avg_change,
            "up_count": up_count,
            "down_count": down_count,
            "flat_count": flat_count,
            "leader": leader,
            "direction": "扩散偏强" if up_count > down_count else ("扩散偏弱" if down_count > up_count else "多空均衡"),
        },
        "liquidity": {
            "total_amount": total_amount if amounts else None,
            "total_amount_yi": _fmt_amount_yi(total_amount) if amounts else None,
            "avg_amount_yi": _fmt_amount_yi(total_amount / len(amounts)) if amounts else None,
            "top_amount_member": top_amount_member,
            "coverage_note": "以本地 stock_daily amount 作为量能代理",
            "missing_reason": "" if amounts else "本地 stock_daily 暂无成交额字段",
        },
        "signal_overlap": signal_overlap,
        "news_research": {
            "status": "missing",
            "items": [],
            "missing_reason": "板块级新闻/研报证据尚未接入；当前仅在新闻主题面板做个股/主题映射",
        },
        "related_index": {
            "status": "missing",
            "items": [],
            "missing_reason": "本地覆盖池暂未维护行业/概念关联指数映射",
        },
        "next_actions": [
            {"id": "send_screener", "label": "发送到选股器", "requires": "members"},
            {"id": "open_stock", "label": "打开成分股工作台", "requires": "selected_member"},
            {"id": "draft_backtest", "label": "生成板块篮子回测草案", "requires": "members", "status": "deferred"},
        ],
    }


def _build_local_sector_members(name: str, grouping: str = "industry", limit: int = 30) -> dict[str, Any]:
    sector_name = str(name or "").strip()
    normalized_grouping = "industry" if str(grouping or "").strip() == "industry" else "exchange_board"
    safe_limit = max(1, min(int(limit or 30), 100))
    generated_at = datetime.now().isoformat(timespec="seconds")
    stocks = _local_market_stock_rows()
    total_pool = len(stocks)
    members = [
        stock for stock in stocks
        if _sector_member_group_name(stock, normalized_grouping) == sector_name
    ]
    members.sort(
        key=lambda item: (
            float(item.get("change_pct") if item.get("change_pct") is not None else -999),
            float(item.get("amount") or 0),
        ),
        reverse=True,
    )

    display_members = []
    for stock in members[:safe_limit]:
        change_pct = stock.get("change_pct")
        amount = stock.get("amount")
        display_members.append(
            {
                "code": str(stock.get("code") or ""),
                "name": str(stock.get("name") or stock.get("code") or ""),
                "sector_name": sector_name,
                "grouping": normalized_grouping,
                "industry": str(stock.get("industry") or ""),
                "price": stock.get("price"),
                "change_pct": round(float(change_pct), 2) if change_pct is not None else None,
                "amount": amount,
                "turnover_amount": round(float(amount or 0) / 1e8, 2) if amount is not None else None,
                "date": stock.get("date"),
                "source": "local_stock_daily",
                "rank_reason": f"{sector_name}板块成分股，按涨跌幅和成交额排序",
            }
        )

    up_count = len([s for s in members if (s.get("change_pct") or 0) > 0])
    down_count = len([s for s in members if (s.get("change_pct") or 0) < 0])
    result = {
        "success": bool(sector_name),
        "sector_name": sector_name,
        "grouping": normalized_grouping,
        "source": "local_stock_daily",
        "provider": "market_sector_members",
        "universe": "local_stock_daily_coverage_pool",
        "generated_at": generated_at,
        "timestamp": generated_at,
        "coverage_note": "本地 stock_daily 覆盖池板块成分，按最新交易日涨跌幅和成交额排序",
        "total_count": len(members),
        "effective_count": len(members),
        "display_count": len(display_members),
        "source_pool_count": total_pool,
        "up_count": up_count,
        "down_count": down_count,
        "flat_count": max(len(members) - up_count - down_count, 0),
        "members": display_members,
        "evidence_context": _build_sector_evidence_context(
            sector_name=sector_name,
            grouping=normalized_grouping,
            members=members,
            display_members=display_members,
            generated_at=generated_at,
            total_pool=total_pool,
        ),
        "source_context": {
            "source": "market:sector-heatmap",
            "sourceLabel": "板块",
            "context_type": "sector",
            "sector_name": sector_name,
            "universe": "local_stock_daily_coverage_pool",
            "rank_reason": f"{sector_name}板块成分股，按涨跌幅和成交额排序",
        },
        "stale": True,
        "stale_reason": "local_daily_snapshot",
    }
    if not sector_name:
        result.update(
            {
                "success": False,
                "source_unavailable": True,
                "missing_reason": "sector_name_required",
                "coverage_note": "缺少板块名称，无法生成成分股列表",
            }
        )
    elif not members:
        result.update(
            {
                "source_unavailable": False,
                "missing_reason": f"本地覆盖池暂无{sector_name}成分股",
                "coverage_note": f"本地 stock_daily 覆盖池暂无 {sector_name} 成分股",
            }
        )
    return result


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
            "change_pct": round(float(item.get("f3", 0)), 2) if item.get("f3") else 0,
            "up_count": int(item.get("f104", 0)),
            "down_count": int(item.get("f105", 0)),
            "leader": item.get("f128", "") or item.get("f140", ""),
            "leader_code": item.get("f140", ""),
            "leader_change": round(float(item.get("f136", 0)), 2) if item.get("f136") else 0,
        })
    return sectors


@router.get("/sectors")
async def get_sector_ranking(type: str = "industry", fast: bool = False):
    """板块轮动排名"""
    global _last_sectors
    cache_key = f"sectors:{type}:fast" if fast else f"sectors:{type}"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached

    if fast:
        snapshot = await asyncio.to_thread(_build_local_sector_snapshot)
        sectors = snapshot["sectors"]
        if sectors:
            result = _with_fast_path({
                "success": True,
                "sectors": sectors,
                "type": type,
                "source": "local_stock_daily",
                "local_fallback": True,
                "stale": True,
                "coverage_note": _local_sector_coverage_note(snapshot, "轮动"),
                "grouping": snapshot["grouping"],
                "weight_basis": snapshot["weight_basis"],
                "stock_count": snapshot["stock_count"],
                "industry_covered": snapshot["industry_covered"],
                "industry_coverage_pct": snapshot["industry_coverage_pct"],
            })
            _cache.set(cache_key, result, _TTL_SECTOR)
            _last_sectors = result
            return result
        if _last_sectors:
            result = _with_fast_path({**_last_sectors, "stale": True, "stale_reason": "fast_local_coverage_unavailable"})
            _cache.set(cache_key, result, _TTL_SECTOR)
            return result
        return {"success": False, "fast": True, "fast_path": True, "error": "本地行业覆盖池暂无可用数据", "sectors": []}

    try:
        sectors = await asyncio.to_thread(_fetch_sector_ranking, type)
        result = {"success": True, "sectors": sectors, "type": type}
        _cache.set(cache_key, result, _TTL_SECTOR)
        _last_sectors = result
        return result
    except Exception as e:
        logger.error(f"板块排名失败: {e}")
        if _last_sectors:
            return {**_last_sectors, "stale": True}
        snapshot = await asyncio.to_thread(_build_local_sector_snapshot)
        sectors = snapshot["sectors"]
        if sectors:
            result = {
                "success": True,
                "sectors": sectors,
                "type": type,
                "source": "local_stock_daily",
                "local_fallback": True,
                "stale": True,
                "coverage_note": _local_sector_coverage_note(snapshot, "轮动"),
                "grouping": snapshot["grouping"],
                "weight_basis": snapshot["weight_basis"],
                "stock_count": snapshot["stock_count"],
                "industry_covered": snapshot["industry_covered"],
                "industry_coverage_pct": snapshot["industry_coverage_pct"],
            }
            _cache.set(cache_key, result, _TTL_SECTOR)
            _last_sectors = result
            return result
        return {"success": False, "error": str(e), "sectors": []}


@router.get("/sector-members")
async def get_sector_members(name: str, grouping: str = "industry", limit: int = 30):
    """板块成分股（本地 stock_daily 覆盖池，只读联动数据）"""
    normalized_name = str(name or "").strip()
    normalized_grouping = "industry" if str(grouping or "").strip() == "industry" else "exchange_board"
    safe_limit = max(1, min(int(limit or 30), 100))
    cache_key = f"sector_members:{normalized_grouping}:{normalized_name}:{safe_limit}"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached
    result = await asyncio.to_thread(_build_local_sector_members, normalized_name, normalized_grouping, safe_limit)
    _cache.set(cache_key, result, _TTL_SECTOR)
    return result


# ── 板块热力图 ──

def _normalize_sector_heatmap_item(item: dict[str, Any]) -> dict[str, Any]:
    total_mv = float(item.get("f20", 0) or 0)
    return {
        "code": item.get("f12", ""),
        "name": item.get("f14", ""),
        "change_pct": round(float(item.get("f3", 0) or 0), 2),
        "up_count": int(item.get("f104", 0) or 0),
        "down_count": int(item.get("f105", 0) or 0),
        "leader": item.get("f128", "") or item.get("f140", ""),
        "leader_code": item.get("f140", ""),
        "leader_change": round(float(item.get("f136", 0) or 0), 2) if item.get("f136") else 0,
        "total_mv": round(total_mv / 1e8, 0) if total_mv else 0,  # 亿
        "main_net_inflow": round(float(item.get("f109", 0) or 0) / 1e4, 2),  # 万→亿
        "source": "eastmoney_sector_board",
    }


def _sector_heatmap_summary(sectors: list[dict[str, Any]]) -> dict[str, Any]:
    changes = [float(s.get("change_pct") or 0) for s in sectors]
    return {
        "up_count": len([v for v in changes if v > 0]),
        "down_count": len([v for v in changes if v < 0]),
        "flat_count": len([v for v in changes if v == 0]),
        "avg_change_pct": round(sum(changes) / len(changes), 2) if changes else 0,
    }


def _fetch_sector_heatmap() -> dict[str, Any]:
    """获取完整板块热力图数据（行业板块，含涨跌幅/涨跌家数/总市值）"""
    page_size = 100
    fields = "f2,f3,f12,f14,f104,f105,f109,f110,f111,f128,f136,f140,f20"
    url = (
        "https://push2delay.eastmoney.com/api/qt/clist/get"
        f"?pn=1&pz={page_size}&po=1&np=1&fltt=2&invt=2"
        f"&fid=f3&fs=m:90+t:2&fields={fields}"
    )
    data = fetch_json(url, timeout=10)
    payload = data.get("data") or {}
    items = payload.get("diff") or []
    total = int(payload.get("total") or len(items))

    for page in range(2, (total + page_size - 1) // page_size + 1):
        page_url = (
            "https://push2delay.eastmoney.com/api/qt/clist/get"
            f"?pn={page}&pz={page_size}&po=1&np=1&fltt=2&invt=2"
            f"&fid=f3&fs=m:90+t:2&fields={fields}"
        )
        page_data = fetch_json(page_url, timeout=10)
        page_items = ((page_data.get("data") or {}).get("diff") or [])
        items.extend(page_items)

    sectors = [_normalize_sector_heatmap_item(item) for item in items]
    sectors = [item for item in sectors if item.get("name")]
    summary = _sector_heatmap_summary(sectors)
    return {
        "sectors": sectors,
        "total": total,
        "fetched": len(sectors),
        "source": "eastmoney_sector_board",
        "universe": "eastmoney_industry_boards_all",
        "coverage_note": "东方财富行业板块全量分页快照，热力图按市值权重展示",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        **summary,
    }


@router.get("/heatmap")
async def get_sector_heatmap(fast: bool = False):
    """板块热力图（行业板块涨跌幅色块矩阵）"""
    global _last_heatmap
    cache_key = "sector_heatmap:fast" if fast else "sector_heatmap"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached

    if fast:
        snapshot = await asyncio.to_thread(_build_local_sector_snapshot)
        sectors = snapshot["sectors"]
        if sectors:
            summary = _sector_heatmap_summary(sectors)
            result = _with_fast_path({
                "success": True,
                "sectors": sectors,
                "total": len(sectors),
                "fetched": len(sectors),
                "source": "local_stock_daily",
                "local_fallback": True,
                "stale": True,
                "coverage_note": _local_sector_coverage_note(snapshot, "热力"),
                "grouping": snapshot["grouping"],
                "weight_basis": snapshot["weight_basis"],
                "stock_count": snapshot["stock_count"],
                "industry_covered": snapshot["industry_covered"],
                "industry_coverage_pct": snapshot["industry_coverage_pct"],
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                **summary,
            })
            _cache.set(cache_key, result, _TTL_SECTOR)
            _last_heatmap = result
            return result
        if _last_heatmap:
            result = _with_fast_path({**_last_heatmap, "stale": True, "stale_reason": "fast_local_coverage_unavailable"})
            _cache.set(cache_key, result, _TTL_SECTOR)
            return result
        return _empty_heatmap_result(
            source="local_stock_daily",
            reason="fast_local_coverage_unavailable",
            error="本地行业热力覆盖池暂无可用数据",
            fast=True,
            coverage_note="本地 stock_daily 覆盖池暂无可用行业热力数据",
        )

    try:
        data = await asyncio.to_thread(_fetch_sector_heatmap)
        result = {"success": True, **data}
        _cache.set(cache_key, result, _TTL_SECTOR)
        _last_heatmap = result
        return result
    except Exception as e:
        logger.error(f"板块热力图失败: {e}")
        if _last_heatmap:
            return {**_last_heatmap, "stale": True}
        snapshot = await asyncio.to_thread(_build_local_sector_snapshot)
        sectors = snapshot["sectors"]
        if sectors:
            summary = _sector_heatmap_summary(sectors)
            result = {
                "success": True,
                "sectors": sectors,
                "total": len(sectors),
                "fetched": len(sectors),
                "source": "local_stock_daily",
                "local_fallback": True,
                "stale": True,
                "coverage_note": _local_sector_coverage_note(snapshot, "热力"),
                "grouping": snapshot["grouping"],
                "weight_basis": snapshot["weight_basis"],
                "stock_count": snapshot["stock_count"],
                "industry_covered": snapshot["industry_covered"],
                "industry_coverage_pct": snapshot["industry_coverage_pct"],
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                **summary,
            }
            _cache.set(cache_key, result, _TTL_SECTOR)
            _last_heatmap = result
            return result
        return _empty_heatmap_result(
            source="eastmoney_sector_board",
            reason="heatmap_source_unavailable",
            error=str(e),
            coverage_note="东方财富行业板块热力源不可用，且本地 stock_daily 覆盖池暂无可用行业热力数据",
        )


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
async def get_northbound(fast: bool = False):
    """北向资金净流入"""
    global _last_northbound
    cache_key = "northbound:fast" if fast else "northbound"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached

    if fast:
        if _last_northbound:
            result = _with_fast_path({**_last_northbound, "stale": True})
            _cache.set(cache_key, result, _TTL_NORTH)
            return result
        result = _with_fast_path({
            "success": True,
            "today_net": 0,
            "today_sh_net": 0,
            "today_sz_net": 0,
            "flow": [],
            "source": "eastmoney_northbound",
            "source_unavailable": True,
            "stale": True,
            "stale_reason": "fast_path_skipped_external_source",
        })
        _cache.set(cache_key, result, _TTL_NORTH)
        return result

    try:
        data = await asyncio.to_thread(_fetch_northbound)
        result = {"success": True, **data}
        _cache.set(cache_key, result, _TTL_NORTH)
        # 仅在有实际数据时更新缓存（避免非交易时间覆盖有效数据）
        if data.get("flow"):
            _last_northbound = result
            return result
        if _last_northbound:
            return {**_last_northbound, "stale": True}
        return result
    except Exception as e:
        logger.error(f"北向资金查询失败: {e}")
        if _last_northbound:
            return {**_last_northbound, "stale": True}
        return {
            "success": True,
            "today_net": 0,
            "today_sh_net": 0,
            "today_sz_net": 0,
            "flow": [],
            "source": "eastmoney_northbound",
            "source_unavailable": True,
            "stale": True,
            "stale_reason": "northbound_source_unavailable",
            "error": str(e),
        }


# ── 热点归因 ──

_TTL_HOTSPOT = 120  # 2 分钟缓存
_last_hotspot: dict | None = None


def _empty_hotspot_result(
    error: str = "",
    reason: str = "hotspot_source_unavailable",
    coverage_note: str = "热点归因源不可用，当前无可用热点数据",
) -> dict[str, Any]:
    generated_at = datetime.now().isoformat(timespec="seconds")
    result: dict[str, Any] = {
        "success": True,
        "source": "hotspot_attribution",
        "provider": "hotspot_attribution",
        "generated_at": generated_at,
        "timestamp": generated_at,
        "coverage_note": coverage_note,
        "summary": "暂无热点数据",
        "hot_concepts": [],
        "hot_industries": [],
        "concepts": [],
        "industries": [],
        "fund_flow": [],
        "source_status": {
            "concept": {"ok": False, "count": 0, "message": reason},
            "industry": {"ok": False, "count": 0, "message": reason},
            "fund_flow": {"ok": False, "count": 0, "message": reason},
        },
        "source_unavailable": True,
        "stale": True,
        "stale_reason": reason,
        "partial_errors": [error] if error else [reason],
    }
    if error:
        result["error"] = error
    return result


def _normalize_hotspot_result(data: dict[str, Any]) -> dict[str, Any]:
    generated_at = datetime.now().isoformat(timespec="seconds")
    hot_concepts = data.get("hot_concepts") or data.get("concepts") or []
    hot_industries = data.get("hot_industries") or data.get("industries") or []
    fund_flow = data.get("fund_flow") or []
    partial_errors = list(data.get("partial_errors") or data.get("errors") or [])
    source_status = data.get("source_status") or {}
    source_unavailable = not hot_concepts and not hot_industries and not fund_flow
    if source_unavailable and not partial_errors:
        partial_errors = ["empty_hotspot_source"]

    result: dict[str, Any] = {
        "success": True,
        "source": data.get("source") or "hotspot_attribution",
        "provider": data.get("provider") or "hotspot_attribution",
        "generated_at": data.get("generated_at") or generated_at,
        "timestamp": data.get("timestamp") or data.get("generated_at") or generated_at,
        "coverage_note": data.get("coverage_note") or "热点归因：概念、行业和资金流聚合快照",
        **data,
        "hot_concepts": hot_concepts,
        "hot_industries": hot_industries,
        "concepts": hot_concepts,
        "industries": hot_industries,
        "fund_flow": fund_flow,
    }
    if source_status:
        result["source_status"] = source_status
    if partial_errors:
        result["partial_errors"] = partial_errors
    if source_unavailable:
        result.update(
            {
                "source_unavailable": True,
                "stale": True,
                "stale_reason": "empty_hotspot_source",
                "coverage_note": data.get("coverage_note") or "热点归因源当前无可用记录",
            }
        )
    return result


@router.get("/hotspot")
async def get_hotspot():
    """热点归因分析（概念板块+行业+资金流向）"""
    global _last_hotspot
    cache_key = "hotspot"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached

    try:
        from alpha.hotspot_attribution import get_hotspot_attribution
        data = await get_hotspot_attribution()
        result = _normalize_hotspot_result(data if isinstance(data, dict) else {})
        _cache.set(cache_key, result, _TTL_HOTSPOT)
        _last_hotspot = result
        return result
    except Exception as e:
        logger.error(f"热点归因失败: {e}")
        if _last_hotspot:
            generated_at = datetime.now().isoformat(timespec="seconds")
            partial_errors = list(_last_hotspot.get("partial_errors") or [])
            partial_errors.append(str(e))
            return {
                **_last_hotspot,
                "success": True,
                "source": _last_hotspot.get("source") or "hotspot_attribution",
                "provider": _last_hotspot.get("provider") or "hotspot_attribution",
                "generated_at": _last_hotspot.get("generated_at") or generated_at,
                "timestamp": _last_hotspot.get("timestamp")
                or _last_hotspot.get("generated_at")
                or generated_at,
                "coverage_note": _last_hotspot.get("coverage_note") or "热点归因源异常，展示最近一次缓存",
                "source_unavailable": True,
                "stale": True,
                "stale_reason": "hotspot_source_unavailable",
                "partial_errors": partial_errors,
                "error": str(e),
            }
        return _empty_hotspot_result(str(e))


# ── 市场新闻 ──

_TTL_NEWS = 300  # 5 分钟缓存
_last_news: dict | None = None


@router.get("/news")
async def get_market_news():
    """市场新闻快讯 + 情绪分析"""
    global _last_news
    cache_key = "market_news"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached

    try:
        from alpha.news_collector import fetch_market_news_summary
        data = await fetch_market_news_summary()
        source_errors = data.get("errors") or data.get("partial_errors") or []
        source_names = [item.get("name") for item in data.get("sources", []) if isinstance(item, dict)]
        source_unavailable = not data.get("news") and (not data.get("sources") or bool(source_errors))
        generated_at = datetime.now().isoformat(timespec="seconds")
        result = {
            "success": True,
            "source": "market_news_multi_source",
            "generated_at": generated_at,
            "timestamp": data.get("timestamp") or generated_at,
            "coverage_note": (
                f"多源市场新闻聚合：{', '.join(source_names)}"
                if source_names
                else "多源市场新闻聚合，当前新闻源无可用记录"
            ),
            **data,
        }
        if source_unavailable:
            result.update(
                {
                    "source_unavailable": True,
                    "stale": True,
                    "stale_reason": str(source_errors[0] if source_errors else "empty_news_source"),
                }
            )
        _cache.set(cache_key, result, _TTL_NEWS)
        _last_news = result
        return result
    except Exception as e:
        logger.error(f"市场新闻获取失败: {e}")
        if _last_news:
            return {**_last_news, "stale": True}
        return {
            "success": False,
            "error": str(e),
            "source": "market_news_multi_source",
            "generated_at": (generated_at := datetime.now().isoformat(timespec="seconds")),
            "timestamp": generated_at,
            "coverage_note": "多源市场新闻聚合异常，暂无可用缓存",
            "source_unavailable": True,
            "stale": True,
            "stale_reason": "market_news_source_unavailable",
            "news": [],
            "sources": [],
            "overall_sentiment": 0,
        }
