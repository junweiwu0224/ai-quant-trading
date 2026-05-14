"""股票详情 API — K 线、资金流向、分时"""
import asyncio
import json
import time
from datetime import datetime

from urllib.request import Request, urlopen

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from config.datetime_utils import now_beijing_str

from data.collector.cache import TTLCache
from data.collector.http_client import code_to_secid, fetch_json, fetch_kline as _fetch_kline_shared

router = APIRouter()

# ── TTL 缓存 ──
_cache = TTLCache(max_size=500)

_TTL_QUOTE = 5
_TTL_KLINE = 60
_TTL_FINANCIAL = 300
_TTL_BOARD = 600

_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com"}


async def _fetch_async(url: str) -> dict:
    """异步包装的 HTTP 请求"""
    return await asyncio.to_thread(fetch_json, url, None, 10.0, _HEADERS)


@router.post("/sync-all")
async def sync_all_stocks():
    """同步全量A股列表到数据库"""
    try:
        from data.collector import StockCollector
        from data.storage.storage import DataStorage

        collector = StockCollector()
        storage = DataStorage()

        # 获取全量A股列表
        df = collector.get_stock_list()
        if df.empty:
            raise HTTPException(500, "获取股票列表失败")

        # 保存到数据库
        count = storage.save_stock_info(df)
        return {"message": "同步成功", "count": count}
    except Exception as e:
        logger.error(f"同步股票列表失败: {e}")
        raise HTTPException(500, f"同步失败: {e}")


_stock_list_cache: dict = {"df": None, "ts": 0}


def _normalize_search_query(q: str) -> str:
    return q.strip() if isinstance(q, str) else ""


def _stock_search_rank(record: dict, query: str, index: int) -> tuple:
    code = str(record.get("code") or "").strip()
    name = str(record.get("name") or "").strip()
    normalized_query = query.lower()
    normalized_code = code.lower()
    normalized_name = name.lower()

    exact_code = 0 if normalized_query and normalized_code == normalized_query else 1
    code_prefix = 0 if normalized_query and normalized_code.startswith(normalized_query) else 1
    exact_name = 0 if normalized_query and normalized_name == normalized_query else 1
    name_contains = 0 if normalized_query and normalized_query in normalized_name else 1
    code_contains = 0 if normalized_query and normalized_query in normalized_code else 1

    return (exact_code, code_prefix, exact_name, name_contains, code_contains, index)


@router.get("/search")
async def search_stocks(
    q: str = Query("", description="搜索关键词"),
    limit: int = Query(50, ge=1, le=6000, description="返回数量限制"),
):
    """搜索股票（支持全量列表，带内存缓存）"""
    import time
    query = _normalize_search_query(q)
    try:
        now = time.time()
        source = "cache" if _stock_list_cache["df"] is not None and now - _stock_list_cache["ts"] <= 300 else "storage"
        if source == "storage":
            from data.storage.storage import DataStorage
            storage = DataStorage()
            df = storage.get_stock_list()
            _stock_list_cache["df"] = df
            _stock_list_cache["ts"] = now
        else:
            df = _stock_list_cache["df"]

        if df.empty:
            return {
                "success": True,
                "query": query,
                "source": source,
                "degraded": False,
                "results": [],
            }

        records = df.to_dict("records")
        if query:
            lowered = query.lower()
            records = [
                record for record in records
                if lowered in str(record.get("code") or "").lower()
                or lowered in str(record.get("name") or "").lower()
            ]
            records = sorted(
                enumerate(records),
                key=lambda item: _stock_search_rank(item[1], query, item[0]),
            )
            results = [record for _, record in records[:limit]]
        else:
            results = records[:limit]

        return {
            "success": True,
            "query": query,
            "source": source,
            "degraded": False,
            "results": results,
        }
    except Exception as e:
        logger.error(f"搜索股票失败: {e}")
        return {
            "success": False,
            "query": query,
            "source": "storage",
            "degraded": True,
            "results": [],
            "error": "搜索股票失败",
        }


def _validate_code(code: str) -> str:
    """校验股票代码：6位数字"""
    code = code.strip()
    if not code.isdigit() or len(code) != 6:
        raise HTTPException(400, f"无效的股票代码: {code}，需要6位数字")
    return code


def _fmt_cap(v: float) -> str:
    """格式化市值"""
    if not v or v == 0:
        return "--"
    if v >= 1e12:
        return f"{v/1e12:.2f}万亿"
    if v >= 1e8:
        return f"{v/1e8:.2f}亿"
    if v >= 1e4:
        return f"{v/1e4:.2f}万"
    return f"{v:.2f}"


def _calc_volume_ratio(quote) -> float | None:
    """计算量比：当前成交量 / 5日均量"""
    if quote.volume_ratio:
        return round(quote.volume_ratio, 2)
    if quote.avg_volume_5d and quote.avg_volume_5d > 0 and quote.volume:
        return round(quote.volume / quote.avg_volume_5d, 2)
    return None


@router.get("/kline/{code}")
async def get_kline(code: str, period: str = "daily", count: int = 120):
    """获取 K 线数据（push2his 优先，腾讯回退）"""
    code = _validate_code(code)
    cache_key = f"kline:{code}:{period}:{count}"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached

    # 使用共享 K 线模块
    raw = await asyncio.to_thread(_fetch_kline_shared, code, count, period)
    if not raw:
        result = {"code": code, "name": "", "period": period, "klines": []}
        _cache.set(cache_key, result, _TTL_KLINE)
        return result

    parsed = []
    for parts in raw["klines_raw"]:
        if len(parts) >= 6:
            o, c, h, l = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
            vol = float(parts[5])
            parsed.append({
                "date": parts[0],
                "open": o,
                "close": c,
                "high": h,
                "low": l,
                "volume": vol,
                "amount": float(parts[6]) if len(parts) >= 7 else 0,
                "amplitude": float(parts[7]) if len(parts) > 7 and parts[7] != '-' else 0,
                "change_pct": float(parts[8]) if len(parts) > 8 and parts[8] != '-' else 0,
                "change": float(parts[9]) if len(parts) > 9 and parts[9] != '-' else 0,
                "turnover": float(parts[10]) if len(parts) >= 11 else 0,
            })

    result = {"code": code, "name": raw.get("name", ""), "period": period, "klines": parsed}
    _cache.set(cache_key, result, _TTL_KLINE)
    return result


@router.get("/timeline/{code}")
async def get_timeline(code: str):
    """获取今日分时数据"""
    code = _validate_code(code)
    cache_key = f"timeline:{code}"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached

    secid = code_to_secid(code)
    url = (
        f"https://push2delay.eastmoney.com/api/qt/stock/trends2/get"
        f"?secid={secid}"
        f"&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13"
        f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58"
        f"&_={int(time.time()*1000)}"
    )
    try:
        data = await _fetch_async(url)
        d = (data.get("data") or {})
        trends = d.get("trends", [])
        pre_close = d.get("preClose", 0)

        parsed = []
        for t in trends:
            parts = t.split(",")
            if len(parts) >= 6:
                parsed.append({
                    "time": parts[0],
                    "open": float(parts[1]),
                    "close": float(parts[2]),
                    "high": float(parts[3]),
                    "low": float(parts[4]),
                    "volume": float(parts[5]) / 100,  # 股→手
                    "amount": float(parts[6]) if len(parts) > 6 else 0,
                    "avg_price": float(parts[7]) if len(parts) > 7 else 0,
                })

        result = {"code": code, "pre_close": pre_close, "trends": parsed}
        _cache.set(cache_key, result, _TTL_QUOTE)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"分时数据获取失败: {e}")
        raise HTTPException(502, f"分时数据获取失败: {e}")


@router.get("/timeline-multi/{code}")
async def get_timeline_multi(code: str, days: int = 5):
    """获取多日分时叠加数据（今日分时 + 前几日K线）"""
    code = _validate_code(code)
    cache_key = f"timeline-multi:{code}:{days}"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached

    try:
        # 获取今日分时数据
        secid = code_to_secid(code)
        timeline_url = (
            f"https://push2delay.eastmoney.com/api/qt/stock/trends2/get"
            f"?secid={secid}"
            f"&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13"
            f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58"
            f"&_={int(time.time()*1000)}"
        )

        # 获取日K线（前几日）
        raw = await asyncio.to_thread(_fetch_kline_shared, code, days + 1, "daily")

        today_data = None
        pre_closes: dict[str, float] = {}

        # 解析今日分时
        try:
            tdata = await _fetch_async(timeline_url)
            td = (tdata.get("data") or {})
            trends = td.get("trends", [])
            today_pre_close = td.get("preClose", 0)
            if trends:
                today_bars = []
                for t in trends:
                    parts = t.split(",")
                    if len(parts) >= 6:
                        today_bars.append({
                            "time": parts[0],
                            "open": float(parts[1]),
                            "close": float(parts[2]),
                            "high": float(parts[3]),
                            "low": float(parts[4]),
                            "volume": float(parts[5]) / 100,  # 股→手
                            "amount": float(parts[6]) if len(parts) > 6 else 0,
                            "avg_price": float(parts[7]) if len(parts) > 7 else 0,
                        })
                today_date = today_bars[0]["time"].split(" ")[0] if today_bars else ""
                today_data = {"date": today_date, "bars": today_bars, "pre_close": today_pre_close}
        except Exception as e:
            logger.warning(f"今日分时获取失败: {e}")

        # 解析日K线（前几日）
        prev_days = []
        if raw and raw.get("klines_raw"):
            klines = raw["klines_raw"]
            # 排除今天（如果日K线包含今天）
            if today_data:
                klines = [k for k in klines if k[0] != today_data["date"]]
            # 取最近 days-1 天
            for k in klines[-(days - 1):]:
                if len(k) >= 6:
                    prev_days.append({
                        "date": k[0],
                        "open": float(k[1]),
                        "close": float(k[2]),
                        "high": float(k[3]),
                        "low": float(k[4]),
                        "volume": float(k[5]),
                    })

        # 构建 pre_closes（前一天收盘价）
        all_days_data = prev_days + ([today_data] if today_data else [])
        for i, d in enumerate(all_days_data):
            if i > 0:
                pre_closes[d["date"]] = all_days_data[i - 1]["close"]

        result = {"code": code, "days": all_days_data, "pre_closes": pre_closes}
        _cache.set(cache_key, result, _TTL_QUOTE)
        return result
    except Exception as e:
        logger.error(f"多日分时数据获取失败: {e}")
        raise HTTPException(502, f"多日分时数据获取失败: {e}")


@router.get("/capital-flow/{code}")
async def get_capital_flow(code: str, days: int = 20):
    """获取资金流向（日级别）"""
    code = _validate_code(code)
    cache_key = f"capital:{code}:{days}"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached

    secid = code_to_secid(code)
    url = (
        f"https://push2delay.eastmoney.com/api/qt/stock/fflow/daykline/get"
        f"?secid={secid}"
        f"&fields1=f1,f2,f3,f7"
        f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65"
        f"&lmt={days}"
        f"&_={int(time.time()*1000)}"
    )
    try:
        data = await _fetch_async(url)
        if not data:
            return {"code": code, "flow": []}
        inner = data.get("data") or {}
        klines = inner.get("klines") or []

        parsed = []
        for k in klines:
            parts = k.split(",")
            if len(parts) >= 6:
                parsed.append({
                    "date": parts[0],
                    "main_net": float(parts[1]),
                    "small_net": float(parts[2]),
                    "medium_net": float(parts[3]),
                    "big_net": float(parts[4]),
                    "super_net": float(parts[5]),
                })

        result = {"code": code, "flow": parsed}
        _cache.set(cache_key, result, _TTL_KLINE)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"资金流向获取失败: {e}")
        raise HTTPException(502, "资金流向服务不可用")


@router.get("/order-book/{code}")
async def get_order_book(code: str):
    """获取五档盘口"""
    code = _validate_code(code)
    cache_key = f"orderbook:{code}"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached

    secid = code_to_secid(code)
    url = (
        f"https://push2delay.eastmoney.com/api/qt/stock/get"
        f"?secid={secid}"
        f"&fields=f31,f32,f33,f34,f35,f36,f37,f38,f39,f40,f19,f20,f17,f18,f15,f16,f13,f14,f11,f12"
        f"&_={int(time.time()*1000)}"
    )
    try:
        data = await _fetch_async(url)
        d = (data.get("data") or {})

        def price_fmt(v):
            if v is None or v == "-": return 0
            return float(v) / 100

        bids = []
        for pk, vk in [(11,12),(13,14),(15,16),(17,18),(19,20)]:
            bids.append({"price": price_fmt(d.get(f"f{pk}")), "volume": int(d.get(f"f{vk}", 0) or 0)})
        asks = []
        for pk, vk in [(31,32),(33,34),(35,36),(37,38),(39,40)]:
            asks.append({"price": price_fmt(d.get(f"f{pk}")), "volume": int(d.get(f"f{vk}", 0) or 0)})

        result = {"code": code, "bids": bids, "asks": asks}
        _cache.set(cache_key, result, _TTL_QUOTE)
        return result
    except Exception as e:
        logger.warning(f"盘口数据获取失败 (push2 stock/get 暂不可用): {e}")
        # 返回空盘口数据（优雅降级，不缓存错误结果以便下次重试）
        empty = [{"price": 0, "volume": 0} for _ in range(5)]
        return {"code": code, "bids": empty, "asks": empty}


@router.get("/detail/{code}")
async def get_stock_detail(code: str):
    """获取股票完整详情（聚合接口）"""
    code = _validate_code(code)
    from data.collector.quote_service import get_quote_service, _fetch_financial_data, QuoteData

    service = get_quote_service()
    quote = service.get_quote(code)

    if not quote:
        from data.collector.quote_service import _fetch_single_quote
        quote = await asyncio.to_thread(_fetch_single_quote, code)
        if not quote:
            raise HTTPException(404, f"股票 {code} 数据获取失败")

    # 补充财务指标：优先用后台预缓存，回退到 on-demand（带 30 分钟 TTL）
    if not quote.eps and not quote.high_52w:
        fin = service.get_financial_data(code)
        if not fin:
            fin = await asyncio.to_thread(_fetch_financial_data, code)
        if fin:
            quote = QuoteData(
                **{**quote.__dict__,
                   "high_52w": fin.get("high_52w", quote.high_52w),
                   "low_52w": fin.get("low_52w", quote.low_52w),
                   "avg_volume_5d": fin.get("avg_volume_5d", quote.avg_volume_5d),
                   "avg_volume_10d": fin.get("avg_volume_10d", quote.avg_volume_10d),
                   "eps": fin.get("eps", quote.eps),
                   "bps": fin.get("bps", quote.bps),
                   "revenue": fin.get("revenue", quote.revenue),
                   "revenue_growth": fin.get("revenue_growth", quote.revenue_growth),
                   "net_profit": fin.get("net_profit", quote.net_profit),
                   "net_profit_growth": fin.get("net_profit_growth", quote.net_profit_growth),
                   "gross_margin": fin.get("gross_margin", quote.gross_margin),
                   "net_margin": fin.get("net_margin", quote.net_margin),
                   "roe": fin.get("roe", quote.roe),
                   "debt_ratio": fin.get("debt_ratio", quote.debt_ratio),
                   "total_shares": fin.get("total_shares", quote.total_shares),
                   "circulating_shares": fin.get("circulating_shares", quote.circulating_shares),
                   "pe_ttm": fin.get("pe_ttm", quote.pe_ttm),
                   "ps_ratio": fin.get("ps_ratio", quote.ps_ratio),
                   "dividend_yield": fin.get("dividend_yield", quote.dividend_yield),
                }
            )

    return {
        "code": quote.code,
        "name": quote.name,
        "price": quote.price,
        "open": quote.open,
        "high": quote.high,
        "low": quote.low,
        "pre_close": quote.pre_close,
        "change_pct": quote.change_pct,
        "change": round(quote.price - quote.pre_close, 2) if quote.pre_close else None,
        "volume": quote.volume,
        "amount": quote.amount,
        "industry": quote.industry,
        "sector": quote.sector,
        "concepts": [c.strip() for c in quote.concepts.split(",") if c.strip()] if quote.concepts else [],
        "market_cap": _fmt_cap(quote.market_cap),
        "circulating_cap": _fmt_cap(quote.circulating_cap),
        "pe_ratio": round(quote.pe_ratio, 2) or None,
        "pb_ratio": round(quote.pb_ratio, 2) or None,
        "turnover_rate": round(quote.turnover_rate, 2) or None,
        "amplitude": round(quote.amplitude, 2) or None,
        "volume_ratio": _calc_volume_ratio(quote),
        # 新增专业字段（0 值返回 null 让前端显示 "--"）
        "high_52w": round(quote.high_52w, 2) or None,
        "low_52w": round(quote.low_52w, 2) or None,
        "avg_volume_5d": round(quote.avg_volume_5d, 0) or None,
        "avg_volume_10d": round(quote.avg_volume_10d, 0) or None,
        "eps": round(quote.eps, 2) or None,
        "bps": round(quote.bps, 2) or None,
        "revenue": _fmt_cap(quote.revenue),
        "revenue_growth": round(quote.revenue_growth, 2) or None,
        "net_profit": _fmt_cap(quote.net_profit),
        "net_profit_growth": round(quote.net_profit_growth, 2) or None,
        "gross_margin": round(quote.gross_margin, 2) or None,
        "net_margin": round(quote.net_margin, 2) or None,
        "roe": round(quote.roe, 2) or None,
        "debt_ratio": round(quote.debt_ratio, 2) or None,
        "total_shares": _fmt_cap(quote.total_shares),
        "circulating_shares": _fmt_cap(quote.circulating_shares),
        "pe_ttm": round(quote.pe_ttm, 2) or None,
        "ps_ratio": round(quote.ps_ratio, 2) or None,
        "dividend_yield": round(quote.dividend_yield, 2) or None,
        "limit_up": round(quote.limit_up, 2) or None,
        "limit_down": round(quote.limit_down, 2) or None,
        "outer_volume": round(quote.outer_volume, 0) or None,
        "inner_volume": round(quote.inner_volume, 0) or None,
    }


@router.get("/profit-trend/{code}")
async def get_profit_trend(code: str):
    """获取近8季度营收和净利润趋势"""
    code = _validate_code(code)
    cache_key = f"profit:{code}"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached
    try:
        url = (
            f"https://datacenter.eastmoney.com/securities/api/data/get"
            f"?type=RPT_F10_FINANCE_MAINFINADATA"
            f"&sty=REPORT_DATE,TOTALOPERATEREVE,PARENTNETPROFIT"
            f"&filter=(SECURITY_CODE=%22{code}%22)"
            f"&p=1&ps=8&sr=-1&st=REPORT_DATE"
            f"&_={int(time.time() * 1000)}"
        )
        data = await _fetch_async(url)

        if not data.get("result") or not data["result"].get("data"):
            return {"code": code, "trends": []}

        items = data["result"]["data"]
        trends = []
        for item in items:
            report_date = item.get("REPORT_DATE", "")
            if report_date:
                # 提取年份和季度
                year = report_date[:4]
                month = int(report_date[5:7]) if len(report_date) > 7 else 0
                quarter = f"Q{(month - 1) // 3 + 1}" if month else ""
                label = f"{year}{quarter}"
            else:
                label = ""

            trends.append({
                "date": label,
                "revenue": round(float(item.get("TOTALOPERATEREVE", 0) or 0) / 1e8, 2),  # 转为亿
                "net_profit": round(float(item.get("PARENTNETPROFIT", 0) or 0) / 1e8, 2),  # 转为亿
            })

        # 反转为时间正序
        trends.reverse()
        result = {"code": code, "trends": trends}
        _cache.set(cache_key, result, _TTL_FINANCIAL)
        return result
    except Exception as e:
        logger.error(f"获取 {code} 利润趋势失败: {e}")
        return {"code": code, "trends": []}


@router.get("/shareholders/{code}")
async def get_shareholders(code: str):
    """获取十大流通股东"""
    code = _validate_code(code)
    cache_key = f"shareholders:{code}"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached
    try:
        url = (
            f"https://datacenter.eastmoney.com/securities/api/data/get"
            f"?type=RPT_F10_EH_FREEHOLDERS"
            f"&sty=END_DATE,HOLDER_NAME,HOLD_NUM,HOLD_RATIO,HOLD_NUM_CHANGE,CHANGE_RATIO"
            f"&filter=(SECURITY_CODE=%22{code}%22)"
            f"&p=1&ps=10&sr=-1&st=END_DATE"
            f"&_={int(time.time() * 1000)}"
        )
        data = await _fetch_async(url)

        if not data.get("result") or not data["result"].get("data"):
            return {"code": code, "shareholders": []}

        items = data["result"]["data"]
        shareholders = []
        for item in items:
            end_date = item.get("END_DATE", "")
            if end_date:
                end_date = end_date[:10]  # 只取日期部分

            # HOLD_NUM_CHANGE 可能是字符串如"不变"
            change_str = item.get("HOLD_NUM_CHANGE", "")
            if change_str and change_str != "不变":
                try:
                    change = round(float(change_str) / 1e4, 2)
                except (ValueError, TypeError):
                    change = 0.0
            else:
                change = 0.0

            shareholders.append({
                "date": end_date,
                "name": item.get("HOLDER_NAME", ""),
                "shares": round(float(item.get("HOLD_NUM", 0) or 0) / 1e4, 2),  # 转为万股
                "ratio": round(float(item.get("HOLD_RATIO", 0) or 0), 2),
                "change": change,
                "change_pct": round(float(item.get("CHANGE_RATIO", 0) or 0), 2),
            })

        result = {"code": code, "shareholders": shareholders}
        _cache.set(cache_key, result, _TTL_FINANCIAL)
        return result
    except Exception as e:
        logger.error(f"获取 {code} 股东数据失败: {e}")
        return {"code": code, "shareholders": []}


@router.get("/dividends/{code}")
async def get_dividends(code: str):
    """获取分红历史"""
    code = _validate_code(code)
    cache_key = f"dividends:{code}"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached
    try:
        url = (
            f"https://datacenter.eastmoney.com/securities/api/data/v1/get"
            f"?reportName=RPT_SHAREBONUS_DET"
            f"&columns=REPORT_DATE,PRETAX_BONUS_RMB,ASSIGN_PROGRESS,IMPL_PLAN_PROFILE,PLAN_NOTICE_DATE"
            f"&filter=(SECURITY_CODE=%22{code}%22)"
            f"&pageNumber=1&pageSize=20&sortTypes=-1&sortColumns=REPORT_DATE"
            f"&_={int(time.time() * 1000)}"
        )
        data = await _fetch_async(url)

        if not data.get("result") or not data["result"].get("data"):
            return {"code": code, "dividends": []}

        items = data["result"]["data"]
        dividends = []
        for item in items:
            report_date = item.get("REPORT_DATE", "")
            if report_date:
                report_date = report_date[:10]

            notice_date = item.get("PLAN_NOTICE_DATE", "")
            if notice_date:
                notice_date = notice_date[:10]

            bonus = item.get("PRETAX_BONUS_RMB")
            bonus_str = f"10派{bonus}元" if bonus else "--"

            dividends.append({
                "report_date": report_date,
                "bonus": bonus_str,
                "progress": item.get("ASSIGN_PROGRESS", ""),
                "plan": item.get("IMPL_PLAN_PROFILE", ""),
                "notice_date": notice_date,
            })

        result = {"code": code, "dividends": dividends}
        _cache.set(cache_key, result, _TTL_FINANCIAL)
        return result
    except Exception as e:
        logger.error(f"获取 {code} 分红数据失败: {e}")
        return {"code": code, "dividends": []}


@router.get("/announcements/{code}")
async def get_announcements(code: str):
    """获取最近公告"""
    code = _validate_code(code)
    cache_key = f"announcements:{code}"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached
    try:
        url = (
            f"https://np-anotice-stock.eastmoney.com/api/security/ann"
            f"?sr=-1&page_size=20&page_index=1&ann_type=A"
            f"&stock_list={code}&f_node=0&s_node=0"
        )
        def _fetch_ann():
            req = Request(url, headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://data.eastmoney.com",
            })
            with urlopen(req, timeout=5) as resp:
                return json.loads(resp.read())
        data = await asyncio.to_thread(_fetch_ann)

        ann_list = (data.get("data") or {}).get("list", [])
        announcements = []
        for ann in ann_list:
            notice_date = ann.get("notice_date", "")
            if notice_date:
                notice_date = notice_date[:10]

            # 构建公告链接
            art_code = ann.get("art_code", "")
            ann_url = f"https://data.eastmoney.com/notices/detail/{code}/{art_code}.html"

            announcements.append({
                "title": ann.get("title", ""),
                "date": notice_date,
                "url": ann_url,
                "type": ann.get("columns", [{}])[0].get("column_name", "") if ann.get("columns") else "",
            })

        result = {"code": code, "announcements": announcements}
        _cache.set(cache_key, result, _TTL_FINANCIAL)
        return result
    except Exception as e:
        logger.error(f"获取 {code} 公告失败: {e}")
        return {"code": code, "announcements": []}


@router.get("/industry-comparison/{code}")
async def get_industry_comparison(code: str):
    """获取同行业对比数据"""
    code = _validate_code(code)
    cache_key = f"industry:{code}"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached
    try:
        from data.collector.quote_service import _fetch_single_quote

        quote = await asyncio.to_thread(_fetch_single_quote, code)
        if not quote:
            return {"code": code, "industry": "", "stocks": []}

        industry = quote.industry or ""

        # 2. 查找该股票所属的行业板块代码
        # 通过板块列表 API 按名称匹配行业（分页搜索）
        board_code = ""
        board_name = ""

        if industry:
            try:
                # 分页搜索行业板块（每页100，最多5页=500个板块）
                for pn in range(1, 6):
                    board_list_url = (
                        f"https://push2delay.eastmoney.com/api/qt/clist/get"
                        f"?pn={pn}&pz=100&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281"
                        f"&fltt=2&invt=2&fid=f3&fs=m:90+t:2"
                        f"&fields=f12,f14"
                        f"&_={int(time.time() * 1000)}"
                    )
                    board_data = await _fetch_async(board_list_url)
                    board_list = (board_data.get("data") or {}).get("diff", [])
                    if not board_list:
                        break

                    candidates = []
                    for board in board_list:
                        bk_name = board.get("f14", "")
                        bk_code = board.get("f12", "")
                        if not bk_code or not bk_name:
                            continue
                        # 精确匹配优先
                        if bk_name == industry:
                            board_code = bk_code
                            board_name = bk_name
                            break
                        # 模糊匹配
                        if industry in bk_name or bk_name in industry:
                            candidates.append((bk_code, bk_name))

                    if board_code:
                        break
                    if candidates and not board_code:
                        board_code, board_name = candidates[0]
                        break
                    if len(board_list) < 100:
                        break
            except Exception as e:
                logger.warning(f"获取板块列表失败: {e}")

        # 3. 如果找到了板块，获取成分股
        stocks = []
        if board_code:
            comp_url = (
                f"https://push2delay.eastmoney.com/api/qt/clist/get"
                f"?pn=1&pz=20&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281"
                f"&fltt=2&invt=2&fid=f20&fs=b:{board_code}+f:!50"
                f"&fields=f12,f14,f2,f3,f9,f23,f37,f20"
                f"&_={int(time.time() * 1000)}"
            )
            try:
                comp_data = await _fetch_async(comp_url)
                comp_list = (comp_data.get("data") or {}).get("diff", [])

                for item in comp_list:
                    s_code = item.get("f12", "")
                    if not s_code:
                        continue
                    # fltt=2 时值已经是正确单位（元、%），无需再除
                    stocks.append({
                        "code": s_code,
                        "name": item.get("f14", ""),
                        "price": round(float(item.get("f2", 0) or 0), 2),
                        "change_pct": round(float(item.get("f3", 0) or 0), 2),
                        "pe_ratio": round(float(item.get("f9", 0) or 0), 2),
                        "pb_ratio": round(float(item.get("f23", 0) or 0), 2),
                        "roe": round(float(item.get("f37", 0) or 0), 2),
                        "market_cap": float(item.get("f20", 0) or 0),
                    })
            except Exception as e:
                logger.debug(f"获取板块成分股失败: {e}")

        # 4. 如果没找到板块或成分股为空，回退到只返回当前股票
        if not stocks:
            stocks = [{
                "code": quote.code,
                "name": quote.name,
                "price": quote.price,
                "change_pct": round(quote.change_pct, 2),
                "pe_ratio": round(quote.pe_ratio, 2),
                "pb_ratio": round(quote.pb_ratio, 2),
                "roe": round(quote.roe, 2),
                "market_cap": quote.market_cap,
            }]

        # 5. 确保当前股票在列表中
        has_current = any(s["code"] == code for s in stocks)
        if not has_current:
            stocks.insert(0, {
                "code": quote.code,
                "name": quote.name,
                "price": quote.price,
                "change_pct": round(quote.change_pct, 2),
                "pe_ratio": round(quote.pe_ratio, 2),
                "pb_ratio": round(quote.pb_ratio, 2),
                "roe": round(quote.roe, 2),
                "market_cap": quote.market_cap,
            })

        display_industry = board_name or industry
        result = {"code": code, "industry": display_industry, "board_code": board_code, "stocks": stocks}
        _cache.set(cache_key, result, _TTL_BOARD)
        return result
    except Exception as e:
        logger.error(f"获取 {code} 行业对比失败: {e}")
        return {"code": code, "industry": "", "stocks": []}


@router.get("/northbound/{code}")
async def get_northbound(code: str):
    """获取北向资金持仓数据"""
    code = _validate_code(code)
    cache_key = f"northbound:{code}"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached
    try:
        url = (
            f"https://datacenter.eastmoney.com/securities/api/data/get"
            f"?type=RPT_MUTUAL_STOCK_NORTHSTA"
            f"&sty=ALL"
            f"&filter=(SECURITY_CODE=%22{code}%22)(INTERVAL_TYPE=%221%22)"
            f"&p=1&ps=30&sr=-1&st=TRADE_DATE"
            f"&_={int(time.time() * 1000)}"
        )
        data = await _fetch_async(url)

        items = []
        api_result = data.get("result", {})
        if api_result and api_result.get("data"):
            for row in api_result["data"]:
                items.append({
                    "date": str(row.get("TRADE_DATE", ""))[:10],
                    "hold_shares": float(row.get("HOLD_SHARES", 0) or 0),
                    "hold_ratio": round(float(row.get("FREE_SHARES_RATIO", 0) or 0), 4),
                    "a_ratio": round(float(row.get("A_SHARES_RATIO", 0) or 0), 4),
                    "change_shares": float(row.get("ADD_SHARES_REPAIR", 0) or 0),
                    "change_ratio": round(float(row.get("ADD_SHARES_AMP", 0) or 0), 4),
                    "market_cap": float(row.get("HOLD_MARKET_CAP", 0) or 0),
                })

        latest = items[0] if items else {}

        result = {
            "code": code,
            "records": items,
            "latest": {
                "hold_shares": latest.get("hold_shares", 0),
                "hold_ratio": latest.get("hold_ratio", 0),
                "a_ratio": latest.get("a_ratio", 0),
            },
        }
        _cache.set(cache_key, result, _TTL_FINANCIAL)
        return result
    except Exception as e:
        logger.error(f"获取 {code} 北向资金失败: {e}")
        return {"code": code, "records": [], "latest": {}}


# ── 市场大盘 & 热门板块 ──

_INDEX_MAP = [
    ("上证指数", "1.000001"),
    ("深证成指", "0.399001"),
    ("创业板指", "0.399006"),
]


@router.get("/market/indices")
async def market_indices():
    """主要指数实时行情（批量请求 ulist.np/get，15 秒缓存）"""
    hit, cached = _cache.get("market:indices")
    if hit:
        return cached
    try:
        secids = ",".join(sid for _, sid in _INDEX_MAP)
        url = (
            f"https://push2delay.eastmoney.com/api/qt/ulist.np/get"
            f"?fltt=2&fields=f2,f3,f4,f12,f14,f15,f16,f17,f18"
            f"&secids={secids}"
            f"&_={int(time.time() * 1000)}"
        )
        data = await _fetch_async(url)
        diff = (data.get("data") or {}).get("diff", [])

        # 建立 secid -> name 映射
        name_map = {sid.split(".")[-1]: name for name, sid in _INDEX_MAP}
        result_map = {}
        for item in diff:
            code = item.get("f12", "")
            name = name_map.get(code, item.get("f14", ""))
            price = float(item.get("f2") or 0)
            pre_close = float(item.get("f18") or 0)
            # f3 可能因微小变化被 API 四舍五入为 0，从 price/pre_close 自行计算
            change = round(price - pre_close, 2)
            change_pct = round(change / pre_close * 100, 3) if pre_close else 0
            result_map[code] = {
                "name": name,
                "price": round(price, 2),
                "change_pct": change_pct,
                "change": change,
            }

        # 按原始顺序返回
        result = [result_map.get(sid.split(".")[-1], {"name": name, "price": 0, "change_pct": 0, "change": 0})
                  for name, sid in _INDEX_MAP]
        _cache.set("market:indices", result, 15)
        return result
    except Exception as e:
        logger.warning(f"获取指数失败: {e}")
        return [{"name": name, "price": 0, "change_pct": 0, "change": 0} for name, _ in _INDEX_MAP]


@router.get("/market/hot-sectors")
async def market_hot_sectors():
    """热门行业板块 + 概念板块 TOP10（并发请求，30 秒缓存）"""
    hit, cached = _cache.get("market:hot_sectors")
    if hit:
        return cached
    ts = int(time.time() * 1000)

    def _fetch_sectors(fs: str, top: int = 10):
        url = (
            f"https://push2delay.eastmoney.com/api/qt/clist/get"
            f"?pn=1&pz={top}&po=1&np=1&fltt=2&invt=2&fid=f3"
            f"&fs={fs}&fields=f3,f12,f14,f104,f105"
            f"&_={ts}"
        )
        data = fetch_json(url)
        items = (data.get("data") or {}).get("diff", [])
        result = []
        for item in items:
            result.append({
                "name": item.get("f14", ""),
                "change_pct": round(item.get("f3", 0), 2),
                "rise_count": item.get("f104", 0),
                "fall_count": item.get("f105", 0),
            })
        return result

    industries_task = asyncio.to_thread(_fetch_sectors, "m:90+t:2+f:!50", 10)
    concepts_task = asyncio.to_thread(_fetch_sectors, "m:90+t:3+f:!50", 10)
    industries, concepts = await asyncio.gather(
        industries_task, concepts_task, return_exceptions=True
    )
    if isinstance(industries, Exception):
        logger.warning(f"获取行业板块失败: {industries}")
        industries = []
    if isinstance(concepts, Exception):
        logger.warning(f"获取概念板块失败: {concepts}")
        concepts = []
    result = {"industries": industries, "concepts": concepts}
    _cache.set("market:hot_sectors", result, 30)
    return result


@router.get("/market/stats")
async def market_stats():
    """市场涨跌家数统计（15 秒缓存）"""
    hit, cached = _cache.get("market:stats")
    if hit:
        return cached
    try:
        ts = int(time.time() * 1000)
        base = "https://push2delay.eastmoney.com/api/qt"
        fs = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"

        # 涨跌家数
        url_stats = (
            f"{base}/ulist.np/get"
            "?fltt=2&fields=f104,f105,f106"
            "&secids=1.000001,0.399001,0.399006"
            f"&_={ts}"
        )
        # 涨停：涨幅榜前100，统计 >= 9.9%
        url_up = (
            f"{base}/clist/get"
            f"?pn=1&pz=100&po=1&np=1&fltt=2&invt=2&fid=f3&fs={fs}"
            "&fields=f3"
            f"&_={ts}"
        )
        # 跌停：跌幅榜前100，统计 <= -9.9%
        url_down = (
            f"{base}/clist/get"
            f"?pn=1&pz=100&po=0&np=1&fltt=2&invt=2&fid=f3&fs={fs}"
            "&fields=f3"
            f"&_={ts}"
        )

        stats_data, up_data, down_data = await asyncio.gather(
            _fetch_async(url_stats),
            _fetch_async(url_up),
            _fetch_async(url_down),
        )

        items = (stats_data.get("data") or {}).get("diff", [])
        # 累加三个指数的涨跌家数（上证+深证+创业板）
        up_total = sum(it.get("f104", 0) or 0 for it in items)
        down_total = sum(it.get("f105", 0) or 0 for it in items)
        flat_total = sum(it.get("f106", 0) or 0 for it in items)

        up_stocks = (up_data.get("data") or {}).get("diff", [])
        limit_up = sum(1 for s in up_stocks if s.get("f3", 0) >= 9.9)

        down_stocks = (down_data.get("data") or {}).get("diff", [])
        limit_down = sum(1 for s in down_stocks if s.get("f3", 0) <= -9.9)

        result = {
            "up_count": up_total,
            "down_count": down_total,
            "flat_count": flat_total,
            "limit_up": limit_up,
            "limit_down": limit_down,
        }
        _cache.set("market:stats", result, 15)
        return result
    except Exception as e:
        logger.warning(f"获取市场统计失败: {e}")
        return {"up_count": 0, "down_count": 0, "flat_count": 0, "limit_up": 0, "limit_down": 0}


@router.get("/market/benchmark")
async def market_benchmark(count: int = 60):
    """获取沪深300基准收益曲线（5 分钟缓存）"""
    cache_key = f"market:benchmark:{count}"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached
    parsed = []
    try:
        url = (
            "https://push2his.eastmoney.com/api/qt/stock/kline/get"
            "?secid=1.000300"
            "&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13"
            "&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
            f"&klt=101&fqt=1&end=20500101&lmt={count}"
            f"&_={int(time.time() * 1000)}"
        )
        data = await _fetch_async(url)
        for k in (data.get("data") or {}).get("klines", []):
            parts = k.split(",")
            if len(parts) >= 3:
                parsed.append({"date": parts[0], "close": float(parts[2])})
    except Exception as e:
        logger.debug(f"push2his 基准数据失败，尝试腾讯回退: {e}")

    # 腾讯回退：沪深300 = sh000300
    if not parsed:
        try:
            turl = (
                f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
                f"?param=sh000300,day,,,{count},qfq"
            )
            tdata = await _fetch_async(turl)
            stock = (tdata.get("data") or {}).get("sh000300", {})
            klines = stock.get("qfqday") or stock.get("day") or []
            for k in klines:
                if len(k) >= 3:
                    parsed.append({"date": k[0], "close": float(k[2])})
        except Exception as e:
            logger.warning(f"腾讯基准回退也失败: {e}")

    if not parsed:
        return []

    base = parsed[0]["close"]
    result = [
        {"date": p["date"], "return_pct": round((p["close"] - base) / base * 100, 4)}
        for p in parsed
    ]
    _cache.set(cache_key, result, 300)
    return result


# ── 多股对比 ──

@router.get("/compare")
async def compare_stocks(
    codes: str = Query(..., description="逗号分隔的股票代码，最多5只"),
    period: str = Query("daily", description="K线周期"),
    count: int = Query(60, ge=10, le=500, description="K线数量"),
):
    """多股归一化收益率对比（基准日=100）"""
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    if not code_list:
        raise HTTPException(400, "请提供至少一个股票代码")
    if len(code_list) > 5:
        raise HTTPException(400, "最多支持5只股票对比")

    # 预加载股票名称映射
    name_map: dict[str, str] = {}
    try:
        import time as _time
        if _stock_list_cache["df"] is None or _time.time() - _stock_list_cache["ts"] > 300:
            from data.storage.storage import DataStorage
            storage = DataStorage()
            df = storage.get_stock_list()
            _stock_list_cache["df"] = df
            _stock_list_cache["ts"] = _time.time()
        else:
            df = _stock_list_cache["df"]
        if not df.empty:
            name_map = dict(zip(df["code"], df["name"]))
    except Exception:
        pass

    results = {}
    for code in code_list:
        code = _validate_code(code)
        cache_key = f"compare:{code}:{period}:{count}"
        hit, cached = _cache.get(cache_key)
        if hit:
            # 补全旧缓存中可能缺失的名称（不可变更新）
            if not cached.get("name") and code in name_map:
                results[code] = {**cached, "name": name_map[code]}
            else:
                results[code] = cached
            continue

        try:
            raw = await asyncio.to_thread(_fetch_kline_shared, code, count, period)
            if not raw or not raw.get("klines_raw"):
                continue

            # 名称来源：kline API > 股票列表缓存 > code
            stock_name = raw.get("name", "") or name_map.get(code, "") or code

            klines = []
            for parts in raw["klines_raw"]:
                if len(parts) >= 6:
                    klines.append({
                        "date": parts[0],
                        "close": float(parts[2]),
                    })

            if not klines:
                continue

            # 归一化：基准日 = 100
            base = klines[0]["close"]
            if base <= 0:
                continue

            normalized = [
                {"date": k["date"], "value": round(k["close"] / base * 100, 2)}
                for k in klines
            ]
            entry = {"name": stock_name, "data": normalized}
            _cache.set(cache_key, entry, _TTL_KLINE)
            results[code] = entry
        except Exception as e:
            logger.warning(f"对比数据获取失败 {code}: {e}")

    return {"codes": list(results.keys()), "data": results}


# ── 画线工具 CRUD ──

from pydantic import BaseModel as _BaseModel
from data.storage import DataStorage as _DataStorage

_drawing_storage = _DataStorage()


class DrawingCreate(_BaseModel):
    overlay_name: str
    points: list[dict]
    styles: dict = {}


@router.get("/drawings/{code}")
async def get_drawings(code: str):
    """获取指定股票的所有画线"""
    code = _validate_code(code)
    try:
        drawings = _drawing_storage.get_drawings(code)
        for d in drawings:
            d["points"] = json.loads(d["points"])
            d["styles"] = json.loads(d["styles"]) if d["styles"] else {}
        return {"code": code, "drawings": drawings}
    except Exception as e:
        logger.error(f"获取画线失败: {e}")
        return {"code": code, "drawings": []}


@router.post("/drawings/{code}")
async def save_drawing(code: str, body: DrawingCreate):
    """保存一条画线"""
    code = _validate_code(code)
    try:
        now = now_beijing_str()
        drawing_id = _drawing_storage.save_drawing(
            code=code,
            overlay_name=body.overlay_name,
            points_json=json.dumps(body.points),
            styles_json=json.dumps(body.styles),
            created_at=now,
        )
        return {"success": True, "id": drawing_id}
    except Exception as e:
        logger.error(f"保存画线失败: {e}")
        return {"success": False, "error": "保存失败"}


@router.delete("/drawings/{drawing_id}")
async def delete_drawing(drawing_id: int):
    """删除一条画线"""
    try:
        ok = _drawing_storage.delete_drawing(drawing_id)
        return {"success": ok}
    except Exception as e:
        logger.error(f"删除画线失败: {e}")
        return {"success": False, "error": "删除失败"}


@router.delete("/drawings/{code}/all")
async def delete_all_drawings(code: str):
    """清空指定股票的所有画线"""
    code = _validate_code(code)
    try:
        count = _drawing_storage.delete_all_drawings(code)
        return {"success": True, "deleted": count}
    except Exception as e:
        logger.error(f"清空画线失败: {e}")
        return {"success": False, "error": "清空失败"}


# ── 筹码分布 ──

@router.get("/chips/{code}")
async def get_chips_distribution(code: str, days: int = 120):
    """筹码分布计算

    基于历史 K 线成交量 + 换手率估算筹码在各价格区间的分布。
    返回：各价格区间的筹码占比、获利比例、平均成本、90% 集中度。
    """
    code = _validate_code(code)
    cache_key = f"chips:{code}:{days}"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached

    try:
        raw = await asyncio.to_thread(_fetch_kline_shared, code, days, "daily")
        if not raw or not raw.get("klines_raw"):
            return {"code": code, "chips": [], "profit_ratio": 0, "avg_cost": 0, "concentration_90": [0, 0]}

        klines = []
        for parts in raw["klines_raw"]:
            if len(parts) >= 6:
                # 换手率：优先用 API 提供的值，否则用成交量估算（假设流通股 50 亿股）
                turnover = 0
                if len(parts) > 10 and parts[10] != '-' and parts[10] != '0':
                    turnover = float(parts[10])
                elif float(parts[5]) > 0:
                    # 估算换手率：成交量 / 估算流通股（从 detail API 获取或默认 50 亿股）
                    turnover = min(float(parts[5]) / 5e9 * 100, 100)
                klines.append({
                    "date": parts[0],
                    "open": float(parts[1]),
                    "close": float(parts[2]),
                    "high": float(parts[3]),
                    "low": float(parts[4]),
                    "volume": float(parts[5]),
                    "turnover_rate": turnover,
                })

        if not klines:
            return {"code": code, "chips": [], "profit_ratio": 0, "avg_cost": 0, "concentration_90": [0, 0]}

        # 价格区间精度
        all_highs = [k["high"] for k in klines]
        all_lows = [k["low"] for k in klines]
        price_min = min(all_lows)
        price_max = max(all_highs)
        if price_max <= price_min:
            return {"code": code, "chips": [], "profit_ratio": 0, "avg_cost": price_min, "concentration_90": [price_min, price_max]}

        # 将价格区间分为 100 个档位
        n_bins = 100
        bin_width = (price_max - price_min) / n_bins
        chips = [0.0] * n_bins  # 各档位筹码量

        for k in klines:
            day_high = k["high"]
            day_low = k["low"]
            day_close = k["close"]
            day_vol = k["volume"]
            turnover = k["turnover_rate"] / 100.0 if k["turnover_rate"] > 0 else 0.01

            # 衰减旧筹码（换手率决定当日换手比例）
            decay = 1.0 - min(turnover, 1.0)
            for j in range(n_bins):
                chips[j] *= decay

            # 将当日成交量分配到价格区间
            # 用三角分布：以收盘价为中心，向高低扩散
            if day_high <= day_low:
                continue

            for j in range(n_bins):
                bin_price = price_min + (j + 0.5) * bin_width
                if bin_price < day_low or bin_price > day_high:
                    continue
                # 三角权重：离收盘价越近权重越高
                dist = abs(bin_price - day_close) / (day_high - day_low + 0.001)
                weight = max(0.01, 1.0 - dist)
                chips[j] += day_vol * weight

        # 归一化
        total_chips = sum(chips)
        if total_chips == 0:
            return {"code": code, "chips": [], "profit_ratio": 0, "avg_cost": 0, "concentration_90": [0, 0]}

        chips_pct = [c / total_chips * 100 for c in chips]

        # 当前价格（最后一根K线收盘价）
        current_price = klines[-1]["close"]

        # 获利比例
        profit_count = 0.0
        for j in range(n_bins):
            bin_price = price_min + (j + 0.5) * bin_width
            if bin_price <= current_price:
                profit_count += chips[j]
        profit_ratio = profit_count / total_chips

        # 平均成本
        avg_cost = 0.0
        for j in range(n_bins):
            bin_price = price_min + (j + 0.5) * bin_width
            avg_cost += bin_price * chips[j]
        avg_cost /= total_chips

        # 90% 筹码集中度区间
        cumulative = 0.0
        low_90 = price_min
        high_90 = price_max
        for j in range(n_bins):
            cumulative += chips[j] / total_chips
            if cumulative >= 0.05 and low_90 == price_min:
                low_90 = price_min + (j + 0.5) * bin_width
            if cumulative >= 0.95:
                high_90 = price_min + (j + 0.5) * bin_width
                break

        # 构建返回数据（只返回有筹码的区间）
        chips_data = []
        for j in range(n_bins):
            if chips_pct[j] > 0.01:
                chips_data.append({
                    "price": round(price_min + (j + 0.5) * bin_width, 2),
                    "pct": round(chips_pct[j], 2),
                })

        result = {
            "code": code,
            "name": raw.get("name", ""),
            "current_price": current_price,
            "chips": chips_data,
            "profit_ratio": round(profit_ratio * 100, 1),
            "avg_cost": round(avg_cost, 2),
            "concentration_90": [round(low_90, 2), round(high_90, 2)],
        }
        _cache.set(cache_key, result, _TTL_KLINE)
        return result
    except Exception as e:
        logger.error(f"筹码分布计算失败: {e}")
        return {"code": code, "chips": [], "profit_ratio": 0, "avg_cost": 0, "concentration_90": [0, 0]}


# ── 多周期共振分析 ──

def _compute_ma(closes: list[float], period: int) -> float | None:
    """计算简单移动平均"""
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def _compute_rsi(closes: list[float], period: int = 14) -> float | None:
    """计算 RSI"""
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(-period, 0):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _compute_macd(closes: list[float]) -> dict | None:
    """计算 MACD (DIF, DEA, MACD柱)"""
    if len(closes) < 35:
        return None
    ema12 = closes[0]
    ema26 = closes[0]
    dif_list = []
    for c in closes:
        ema12 = ema12 * 11/13 + c * 2/13
        ema26 = ema26 * 25/27 + c * 2/27
        dif_list.append(ema12 - ema26)
    dea = dif_list[0]
    for d in dif_list:
        dea = dea * 8/10 + d * 2/10
    dif = dif_list[-1]
    macd = (dif - dea) * 2
    return {"dif": round(dif, 4), "dea": round(dea, 4), "macd": round(macd, 4)}


def _analyze_timeframe(closes: list[float]) -> dict:
    """分析单个时间框架的技术指标状态"""
    if len(closes) < 30:
        return {"trend": "neutral", "signals": [], "strength": 50}

    ma5 = _compute_ma(closes, 5)
    ma10 = _compute_ma(closes, 10)
    ma20 = _compute_ma(closes, 20)
    rsi = _compute_rsi(closes, 14)
    macd = _compute_macd(closes)
    current = closes[-1]

    signals = []
    bullish = 0
    bearish = 0

    # MA 趋势
    if ma5 and ma10 and ma20:
        if ma5 > ma10 > ma20:
            signals.append({"name": "均线多头排列", "direction": "bullish"})
            bullish += 2
        elif ma5 < ma10 < ma20:
            signals.append({"name": "均线空头排列", "direction": "bearish"})
            bearish += 2
        elif current > ma20:
            signals.append({"name": "站上20日均线", "direction": "bullish"})
            bullish += 1
        else:
            signals.append({"name": "跌破20日均线", "direction": "bearish"})
            bearish += 1

    # MA 金叉/死叉
    if ma5 and ma10:
        prev_ma5 = _compute_ma(closes[:-1], 5)
        prev_ma10 = _compute_ma(closes[:-1], 10)
        if prev_ma5 and prev_ma10:
            if prev_ma5 <= prev_ma10 and ma5 > ma10:
                signals.append({"name": "MA5/10金叉", "direction": "bullish"})
                bullish += 1
            elif prev_ma5 >= prev_ma10 and ma5 < ma10:
                signals.append({"name": "MA5/10死叉", "direction": "bearish"})
                bearish += 1

    # RSI
    if rsi is not None:
        if rsi > 70:
            signals.append({"name": f"RSI超买({rsi:.0f})", "direction": "bearish"})
            bearish += 1
        elif rsi < 30:
            signals.append({"name": f"RSI超卖({rsi:.0f})", "direction": "bullish"})
            bullish += 1

    # MACD
    if macd:
        if macd["dif"] > macd["dea"] and macd["macd"] > 0:
            signals.append({"name": "MACD金叉+红柱", "direction": "bullish"})
            bullish += 2
        elif macd["dif"] < macd["dea"] and macd["macd"] < 0:
            signals.append({"name": "MACD死叉+绿柱", "direction": "bearish"})
            bearish += 2
        elif macd["dif"] > macd["dea"]:
            signals.append({"name": "MACD金叉", "direction": "bullish"})
            bullish += 1
        else:
            signals.append({"name": "MACD死叉", "direction": "bearish"})
            bearish += 1

    total = bullish + bearish
    if total == 0:
        trend = "neutral"
        strength = 50
    elif bullish > bearish:
        trend = "bullish"
        strength = 50 + int(50 * bullish / total)
    else:
        trend = "bearish"
        strength = 50 - int(50 * bearish / total)

    return {"trend": trend, "signals": signals, "strength": strength}


def _resample_to_weekly(daily_klines: list[dict]) -> list[dict]:
    """日K线聚合为周K线"""
    if not daily_klines:
        return []
    from datetime import datetime as dt
    weeks = []
    current_week = None
    week_data = None
    for k in daily_klines:
        d = k["date"][:10]
        try:
            dt_obj = dt.strptime(d, "%Y-%m-%d")
            week_key = f"{dt_obj.isocalendar()[0]}-{dt_obj.isocalendar()[1]:02d}"
        except Exception:
            week_key = d[:7]
        if week_key != current_week:
            if week_data is not None:
                weeks.append(week_data)
            current_week = week_key
            week_data = {"date": d, "open": k["open"], "high": k["high"], "low": k["low"],
                         "close": k["close"], "volume": k.get("volume", 0)}
        else:
            week_data["high"] = max(week_data["high"], k["high"])
            week_data["low"] = min(week_data["low"], k["low"])
            week_data["close"] = k["close"]
            week_data["volume"] = week_data.get("volume", 0) + k.get("volume", 0)
    if week_data is not None:
        weeks.append(week_data)
    return weeks


def _resample_to_monthly(daily_klines: list[dict]) -> list[dict]:
    """日K线聚合为月K线"""
    if not daily_klines:
        return []
    months = []
    current_month = None
    month_data = None
    for k in daily_klines:
        month_key = k["date"][:7]
        if month_key != current_month:
            if month_data is not None:
                months.append(month_data)
            current_month = month_key
            month_data = {"date": k["date"], "open": k["open"], "high": k["high"], "low": k["low"],
                          "close": k["close"], "volume": k.get("volume", 0)}
        else:
            month_data["high"] = max(month_data["high"], k["high"])
            month_data["low"] = min(month_data["low"], k["low"])
            month_data["close"] = k["close"]
            month_data["volume"] = month_data.get("volume", 0) + k.get("volume", 0)
    if month_data is not None:
        months.append(month_data)
    return months


@router.get("/multi-timeframe/{code}")
async def get_multi_timeframe(code: str):
    """多周期共振分析（日/周/月技术指标状态）"""
    cache_key = f"multi_tf:{code}"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached

    try:
        raw = await asyncio.to_thread(_fetch_kline_shared, code, 250, "daily")
        if not raw or not raw.get("klines_raw"):
            return {"success": False, "error": "K线数据不足"}

        # 解析原始 K 线数据
        klines = []
        for parts in raw["klines_raw"]:
            if len(parts) >= 6:
                klines.append({
                    "date": parts[0],
                    "open": float(parts[1]),
                    "close": float(parts[2]),
                    "high": float(parts[3]),
                    "low": float(parts[4]),
                    "volume": float(parts[5]),
                })
        if len(klines) < 30:
            return {"success": False, "error": "K线数据不足"}

        daily_closes = [k["close"] for k in klines]
        weekly_klines = _resample_to_weekly(klines)
        monthly_klines = _resample_to_monthly(klines)
        weekly_closes = [k["close"] for k in weekly_klines]
        monthly_closes = [k["close"] for k in monthly_klines]

        daily = _analyze_timeframe(daily_closes)
        weekly = _analyze_timeframe(weekly_closes)
        monthly = _analyze_timeframe(monthly_closes)

        directions = [daily["trend"], weekly["trend"], monthly["trend"]]
        bullish_count = directions.count("bullish")
        bearish_count = directions.count("bearish")

        if bullish_count == 3:
            resonance = "strong_bullish"
            resonance_label = "三周期共振看多"
        elif bullish_count == 2:
            resonance = "bullish"
            resonance_label = "偏多共振"
        elif bearish_count == 3:
            resonance = "strong_bearish"
            resonance_label = "三周期共振看空"
        elif bearish_count == 2:
            resonance = "bearish"
            resonance_label = "偏空共振"
        else:
            resonance = "neutral"
            resonance_label = "多空分歧"

        result = {
            "success": True,
            "code": code,
            "daily": daily,
            "weekly": weekly,
            "monthly": monthly,
            "resonance": resonance,
            "resonance_label": resonance_label,
            "strength": round((daily["strength"] + weekly["strength"] + monthly["strength"]) / 3),
        }
        _cache.set(cache_key, result, _TTL_KLINE)
        return result
    except Exception as e:
        logger.error(f"多周期分析失败 {code}: {e}")
        return {"success": False, "error": str(e)}


# ── 龙虎榜深度分析 ──

@router.get("/dragon-tiger/{code}")
async def get_dragon_tiger(code: str, days: int = Query(90, ge=1, le=365)):
    """龙虎榜深度分析：上榜记录 + 游资画像 + 收益统计"""
    code = _validate_code(code)
    cache_key = f"dragon-tiger:{code}:{days}"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached

    try:
        # 获取龙虎榜营业部明细（买入方）
        buy_url = (
            f"https://datacenter-web.eastmoney.com/api/data/v1/get"
            f"?reportName=RPT_BILLBOARD_DAILYDETAILSBUY&columns=ALL"
            f"&filter=(SECURITY_CODE=%22{code}%22)"
            f"&pageNumber=1&pageSize={days * 10}"
            f"&sortTypes=-1&sortColumns=TRADE_DATE"
        )
        buy_data = await _fetch_async(buy_url)

        records = []
        api_result = buy_data.get("result", {})
        if api_result and api_result.get("data"):
            for row in api_result["data"]:
                trade_date = str(row.get("TRADE_DATE", ""))[:10]
                buy_amount = float(row.get("BUY", 0) or 0)
                sell_amount = float(row.get("SELL", 0) or 0)
                net_amount = float(row.get("NET", 0) or 0)
                reason = row.get("EXPLANATION", "") or ""
                trader_name = row.get("OPERATEDEPT_NAME", "") or ""
                rise_prob = float(row.get("RISE_PROBABILITY_3DAY", 0) or 0)

                records.append({
                    "date": trade_date,
                    "buy_amount": round(buy_amount / 1e4, 2),  # 万元
                    "sell_amount": round(sell_amount / 1e4, 2),
                    "net_amount": round(net_amount / 1e4, 2),
                    "reason": reason,
                    "trader_name": trader_name,
                    "change_rate": float(row.get("CHANGE_RATE", 0) or 0),
                    "rise_prob_3d": round(rise_prob, 1),
                })

        # 按日期分组
        date_groups: dict[str, list] = {}
        for r in records:
            date_groups.setdefault(r["date"], []).append(r)

        # 汇总上榜记录
        listing_records = []
        for date, items in sorted(date_groups.items(), reverse=True)[:20]:
            total_buy = sum(i["buy_amount"] for i in items)
            total_sell = sum(i["sell_amount"] for i in items)
            total_net = sum(i["net_amount"] for i in items)
            reasons = list(set(i["reason"] for i in items if i["reason"]))
            change_rate = items[0]["change_rate"] if items else 0
            listing_records.append({
                "date": date,
                "buy_amount": round(total_buy, 2),
                "sell_amount": round(total_sell, 2),
                "net_amount": round(total_net, 2),
                "reasons": reasons[:3],
                "trader_count": len(items),
                "change_rate": change_rate,
            })

        # 游资画像（按营业部聚合）
        trader_map: dict[str, dict] = {}
        for r in records:
            name = r["trader_name"]
            if not name:
                continue
            if name not in trader_map:
                trader_map[name] = {
                    "name": name,
                    "total_buy": 0,
                    "total_sell": 0,
                    "total_net": 0,
                    "count": 0,
                    "dates": set(),
                    "rise_probs": [],
                }
            t = trader_map[name]
            t["total_buy"] += r["buy_amount"]
            t["total_sell"] += r["sell_amount"]
            t["total_net"] += r["net_amount"]
            t["count"] += 1
            t["dates"].add(r["date"])
            if r["rise_prob_3d"] > 0:
                t["rise_probs"].append(r["rise_prob_3d"])

        # 排序：按净买入额排序
        traders = sorted(trader_map.values(), key=lambda x: x["total_net"], reverse=True)
        trader_list = []
        for t in traders[:15]:
            avg_rise = round(sum(t["rise_probs"]) / len(t["rise_probs"]), 1) if t["rise_probs"] else 0
            trader_list.append({
                "name": t["name"],
                "total_buy": round(t["total_buy"], 2),
                "total_sell": round(t["total_sell"], 2),
                "total_net": round(t["total_net"], 2),
                "count": t["count"],
                "listing_days": len(t["dates"]),
                "avg_rise_prob": avg_rise,
            })

        # 收益统计（上榜后N日收益）
        # 需要获取足够长的日K线来覆盖龙虎榜日期
        kline_days = max(days, 365)  # 至少获取1年K线
        kline_raw = await asyncio.to_thread(_fetch_kline_shared, code, kline_days, "daily")
        kline_map: dict[str, dict] = {}
        if kline_raw and kline_raw.get("klines_raw"):
            for k in kline_raw["klines_raw"]:
                if len(k) >= 6:
                    kline_map[k[0]] = {
                        "close": float(k[2]),
                        "open": float(k[1]),
                    }

        return_stats = []
        for rec in listing_records[:10]:
            date = rec["date"]
            entry_close = kline_map.get(date, {}).get("close")
            if not entry_close:
                continue
            ret = {"date": date, "entry_price": entry_close}
            for offset, label in [(1, "1d"), (3, "3d"), (5, "5d"), (10, "10d")]:
                # 找到上榜后第 offset 个交易日
                sorted_dates = sorted(kline_map.keys())
                try:
                    idx = sorted_dates.index(date)
                    if idx + offset < len(sorted_dates):
                        future_close = kline_map[sorted_dates[idx + offset]]["close"]
                        ret[label] = round((future_close - entry_close) / entry_close * 100, 2)
                except ValueError:
                    pass
            return_stats.append(ret)

        # 统计汇总
        total_listings = len(date_groups)
        total_net_all = sum(r["net_amount"] for r in records)
        avg_return_5d = 0
        valid_returns = [r.get("5d") for r in return_stats if r.get("5d") is not None]
        if valid_returns:
            avg_return_5d = round(sum(valid_returns) / len(valid_returns), 2)

        result = {
            "success": True,
            "code": code,
            "summary": {
                "total_listings": total_listings,
                "total_net_amount": round(total_net_all, 2),
                "avg_return_5d": avg_return_5d,
                "period_days": days,
            },
            "records": listing_records,
            "traders": trader_list,
            "return_stats": return_stats,
        }
        _cache.set(cache_key, result, _TTL_KLINE)
        return result
    except Exception as e:
        logger.error(f"龙虎榜分析失败 {code}: {e}")
        return {"success": False, "error": str(e)}


# ── 个股新闻 ──

@router.get("/news/{code}")
async def get_stock_news(code: str, limit: int = 20):
    """获取个股新闻 + 情绪分析"""
    code = _validate_code(code)
    cache_key = f"news:{code}:{limit}"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached

    try:
        from alpha.news_collector import fetch_stock_news, compute_news_sentiment
        news, sentiment = await asyncio.gather(
            fetch_stock_news(code, limit),
            compute_news_sentiment(code, limit),
        )
        result = {
            "success": True,
            "code": code,
            "news": news,
            "sentiment": sentiment,
        }
        _cache.set(cache_key, result, _TTL_QUOTE)
        return result
    except Exception as e:
        logger.error(f"个股新闻获取失败 {code}: {e}")
        return {"success": False, "error": str(e), "news": []}
