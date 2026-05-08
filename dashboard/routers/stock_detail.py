"""股票详情 API — K 线、资金流向、分时"""
import asyncio
import json
import time
import threading
from functools import wraps
from urllib.request import Request, urlopen

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

router = APIRouter()

# ── 内存缓存（TTL + LRU淘汰） ──
_cache: dict[str, tuple[float, object]] = {}
_cache_lock = threading.Lock()
_CACHE_MAX_SIZE = 500
_cache_ops = 0


def _cache_get(key: str) -> object | None:
    """读缓存，过期返回 None"""
    with _cache_lock:
        entry = _cache.get(key)
        if entry and entry[0] > time.time():
            return entry[1]
        _cache.pop(key, None)
        return None


def _cache_evict():
    """淘汰过期条目 + 超限时LRU淘汰最旧"""
    global _cache_ops
    _cache_ops += 1
    if _cache_ops < 50:
        return
    _cache_ops = 0
    now = time.time()
    expired = [k for k, (exp, _) in _cache.items() if exp <= now]
    for k in expired:
        _cache.pop(k, None)
    if len(_cache) > _CACHE_MAX_SIZE:
        sorted_keys = sorted(_cache, key=lambda k: _cache[k][0])
        for k in sorted_keys[:len(_cache) - _CACHE_MAX_SIZE]:
            _cache.pop(k, None)


def _cache_set(key: str, value: object, ttl: int):
    """写缓存"""
    with _cache_lock:
        _cache[key] = (time.time() + ttl, value)
        _cache_evict()


def _cached(key: str, ttl: int):
    """缓存装饰器（同步函数）"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cached = _cache_get(key)
            if cached is not None:
                return cached
            result = func(*args, **kwargs)
            _cache_set(key, result, ttl)
            return result
        return wrapper
    return decorator


async def _fetch_async(url: str) -> dict:
    """异步包装的 HTTP 请求，不阻塞事件循环"""
    def _do_fetch():
        req = Request(url, headers=_HEADERS)
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    return await asyncio.to_thread(_do_fetch)


@router.post("/sync-all")
async def sync_all_stocks():
    """同步全量A股列表到数据库"""
    try:
        from data.collector.collector import StockCollector
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


@router.get("/search")
async def search_stocks(
    q: str = Query("", description="搜索关键词"),
    limit: int = Query(50, description="返回数量限制"),
):
    """搜索股票（支持全量列表）"""
    try:
        from data.storage.storage import DataStorage
        storage = DataStorage()
        df = storage.get_stock_list()
        if df.empty:
            return []
        if q:
            df = df[df["code"].str.contains(q, na=False) | df["name"].str.contains(q, na=False)]
        return df.head(limit).to_dict("records")
    except Exception as e:
        logger.error(f"搜索股票失败: {e}")
        return []

_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com"}

# 缓存 TTL（秒）
_TTL_QUOTE = 5       # 实时行情
_TTL_KLINE = 60      # K线、分时
_TTL_FINANCIAL = 300  # 财务、股东、分红、公告、北向
_TTL_BOARD = 600     # 板块列表


def _validate_code(code: str) -> str:
    """校验股票代码：6位数字"""
    code = code.strip()
    if not code.isdigit() or len(code) != 6:
        raise HTTPException(400, f"无效的股票代码: {code}，需要6位数字")
    return code


def _secid(code: str) -> str:
    return f"1.{code}" if code.startswith("6") else f"0.{code}"


def _fetch(url: str) -> dict:
    req = Request(url, headers=_HEADERS)
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _fmt_cap(v: float) -> str:
    """格式化市值"""
    if v >= 1e12:
        return f"{v/1e12:.2f}万亿"
    if v >= 1e8:
        return f"{v/1e8:.2f}亿"
    if v >= 1e4:
        return f"{v/1e4:.2f}万"
    return f"{v:.2f}"


@router.get("/kline/{code}")
async def get_kline(code: str, period: str = "daily", count: int = 120):
    """获取 K 线数据"""
    code = _validate_code(code)
    cache_key = f"kline:{code}:{period}:{count}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    klt_map = {
        "1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 60,
        "daily": 101, "weekly": 102, "monthly": 103,
    }
    klt = klt_map.get(period, 101)
    secid = _secid(code)
    url = (
        f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={secid}"
        f"&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13"
        f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        f"&klt={klt}&fqt=1&end=20500101&lmt={count}"
        f"&_={int(time.time()*1000)}"
    )
    try:
        data = await _fetch_async(url)
        d = data.get("data", {})
        klines = d.get("klines", [])
        name = d.get("name", "")

        parsed = []
        for k in klines:
            parts = k.split(",")
            if len(parts) >= 11:
                parsed.append({
                    "date": parts[0],
                    "open": float(parts[1]),
                    "close": float(parts[2]),
                    "high": float(parts[3]),
                    "low": float(parts[4]),
                    "volume": float(parts[5]),
                    "amount": float(parts[6]),
                    "amplitude": float(parts[7]),
                    "change_pct": float(parts[8]),
                    "change": float(parts[9]),
                    "turnover": float(parts[10]),
                })

        result = {"code": code, "name": name, "period": period, "klines": parsed}
        _cache_set(cache_key, result, _TTL_KLINE)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"K线数据获取失败: {e}")
        raise HTTPException(502, f"K线数据获取失败: {e}")


@router.get("/timeline/{code}")
async def get_timeline(code: str):
    """获取今日分时数据"""
    code = _validate_code(code)
    cache_key = f"timeline:{code}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    secid = _secid(code)
    url = (
        f"https://push2his.eastmoney.com/api/qt/stock/trends2/get"
        f"?secid={secid}"
        f"&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13"
        f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58"
        f"&_={int(time.time()*1000)}"
    )
    try:
        data = await _fetch_async(url)
        d = data.get("data", {})
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
                    "volume": float(parts[5]),
                    "amount": float(parts[6]) if len(parts) > 6 else 0,
                    "avg_price": float(parts[7]) if len(parts) > 7 else 0,
                })

        result = {"code": code, "pre_close": pre_close, "trends": parsed}
        _cache_set(cache_key, result, _TTL_QUOTE)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"分时数据获取失败: {e}")
        raise HTTPException(502, f"分时数据获取失败: {e}")


@router.get("/capital-flow/{code}")
async def get_capital_flow(code: str, days: int = 20):
    """获取资金流向（日级别）"""
    code = _validate_code(code)
    cache_key = f"capital:{code}:{days}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    secid = _secid(code)
    url = (
        f"https://push2.eastmoney.com/api/qt/stock/fflow/daykline/get"
        f"?secid={secid}"
        f"&fields1=f1,f2,f3,f7"
        f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65"
        f"&lmt={days}"
        f"&_={int(time.time()*1000)}"
    )
    try:
        data = await _fetch_async(url)
        klines = data.get("data", {}).get("klines", [])

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
        _cache_set(cache_key, result, _TTL_KLINE)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"资金流向获取失败: {e}")
        raise HTTPException(502, f"资金流向获取失败: {e}")


@router.get("/order-book/{code}")
async def get_order_book(code: str):
    """获取五档盘口"""
    code = _validate_code(code)
    cache_key = f"orderbook:{code}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    secid = _secid(code)
    url = (
        f"https://push2.eastmoney.com/api/qt/stock/get"
        f"?secid={secid}"
        f"&fields=f31,f32,f33,f34,f35,f36,f37,f38,f39,f40,f19,f20,f17,f18,f15,f16,f13,f14,f11,f12"
        f"&_={int(time.time()*1000)}"
    )
    try:
        data = await _fetch_async(url)
        d = data.get("data", {})

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
        _cache_set(cache_key, result, _TTL_QUOTE)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"盘口数据获取失败: {e}")
        raise HTTPException(502, f"盘口数据获取失败: {e}")


@router.get("/detail/{code}")
async def get_stock_detail(code: str):
    """获取股票完整详情（聚合接口）"""
    code = _validate_code(code)
    from data.collector.quote_service import get_quote_service

    service = get_quote_service()
    quote = service.get_quote(code)

    if not quote:
        from data.collector.quote_service import _fetch_single_quote
        quote = await asyncio.to_thread(_fetch_single_quote, code)
        if not quote:
            raise HTTPException(404, f"股票 {code} 数据获取失败")

    return {
        "code": quote.code,
        "name": quote.name,
        "price": quote.price,
        "open": quote.open,
        "high": quote.high,
        "low": quote.low,
        "pre_close": quote.pre_close,
        "change_pct": quote.change_pct,
        "change": round(quote.price - quote.pre_close, 2) if quote.pre_close else 0,
        "volume": quote.volume,
        "amount": quote.amount,
        "industry": quote.industry,
        "sector": quote.sector,
        "concepts": [c.strip() for c in quote.concepts.split(",") if c.strip()] if quote.concepts else [],
        "market_cap": _fmt_cap(quote.market_cap),
        "circulating_cap": _fmt_cap(quote.circulating_cap),
        "pe_ratio": round(quote.pe_ratio, 2),
        "pb_ratio": round(quote.pb_ratio, 2),
        "turnover_rate": round(quote.turnover_rate, 2),
        "amplitude": round(quote.amplitude, 2),
        "volume_ratio": round(quote.volume_ratio, 2),
        # 新增专业字段
        "high_52w": round(quote.high_52w, 2),
        "low_52w": round(quote.low_52w, 2),
        "avg_volume_5d": round(quote.avg_volume_5d, 0),
        "avg_volume_10d": round(quote.avg_volume_10d, 0),
        "eps": round(quote.eps, 2),
        "bps": round(quote.bps, 2),
        "revenue": _fmt_cap(quote.revenue),
        "revenue_growth": round(quote.revenue_growth, 2),
        "net_profit": _fmt_cap(quote.net_profit),
        "net_profit_growth": round(quote.net_profit_growth, 2),
        "gross_margin": round(quote.gross_margin, 2),
        "net_margin": round(quote.net_margin, 2),
        "roe": round(quote.roe, 2),
        "debt_ratio": round(quote.debt_ratio, 2),
        "total_shares": _fmt_cap(quote.total_shares),
        "circulating_shares": _fmt_cap(quote.circulating_shares),
        "pe_ttm": round(quote.pe_ttm, 2),
        "ps_ratio": round(quote.ps_ratio, 2),
        "dividend_yield": round(quote.dividend_yield, 2),
        "limit_up": round(quote.limit_up, 2),
        "limit_down": round(quote.limit_down, 2),
        "outer_volume": round(quote.outer_volume, 0),
        "inner_volume": round(quote.inner_volume, 0),
    }


@router.get("/profit-trend/{code}")
async def get_profit_trend(code: str):
    """获取近8季度营收和净利润趋势"""
    code = _validate_code(code)
    cache_key = f"profit:{code}"
    cached = _cache_get(cache_key)
    if cached is not None:
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
        _cache_set(cache_key, result, _TTL_FINANCIAL)
        return result
    except Exception as e:
        logger.error(f"获取 {code} 利润趋势失败: {e}")
        return {"code": code, "trends": []}


@router.get("/shareholders/{code}")
async def get_shareholders(code: str):
    """获取十大流通股东"""
    code = _validate_code(code)
    cache_key = f"shareholders:{code}"
    cached = _cache_get(cache_key)
    if cached is not None:
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
        _cache_set(cache_key, result, _TTL_FINANCIAL)
        return result
    except Exception as e:
        logger.error(f"获取 {code} 股东数据失败: {e}")
        return {"code": code, "shareholders": []}


@router.get("/dividends/{code}")
async def get_dividends(code: str):
    """获取分红历史"""
    code = _validate_code(code)
    cache_key = f"dividends:{code}"
    cached = _cache_get(cache_key)
    if cached is not None:
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
        _cache_set(cache_key, result, _TTL_FINANCIAL)
        return result
    except Exception as e:
        logger.error(f"获取 {code} 分红数据失败: {e}")
        return {"code": code, "dividends": []}


@router.get("/announcements/{code}")
async def get_announcements(code: str):
    """获取最近公告"""
    code = _validate_code(code)
    cache_key = f"announcements:{code}"
    cached = _cache_get(cache_key)
    if cached is not None:
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

        ann_list = data.get("data", {}).get("list", [])
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
        _cache_set(cache_key, result, _TTL_FINANCIAL)
        return result
    except Exception as e:
        logger.error(f"获取 {code} 公告失败: {e}")
        return {"code": code, "announcements": []}


@router.get("/industry-comparison/{code}")
async def get_industry_comparison(code: str):
    """获取同行业对比数据"""
    code = _validate_code(code)
    cache_key = f"industry:{code}"
    cached = _cache_get(cache_key)
    if cached is not None:
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
                        f"https://push2.eastmoney.com/api/qt/clist/get"
                        f"?pn={pn}&pz=100&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281"
                        f"&fltt=2&invt=2&fid=f3&fs=m:90+t:2"
                        f"&fields=f12,f14"
                        f"&_={int(time.time() * 1000)}"
                    )
                    board_data = await _fetch_async(board_list_url)
                    board_list = board_data.get("data", {}).get("diff", [])
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
                logger.debug(f"获取板块列表失败: {e}")

        # 3. 如果找到了板块，获取成分股
        stocks = []
        if board_code:
            comp_url = (
                f"https://push2.eastmoney.com/api/qt/clist/get"
                f"?pn=1&pz=20&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281"
                f"&fltt=2&invt=2&fid=f20&fs=b:{board_code}+f:!50"
                f"&fields=f12,f14,f2,f3,f9,f23,f37,f20"
                f"&_={int(time.time() * 1000)}"
            )
            try:
                comp_data = await _fetch_async(comp_url)
                comp_list = comp_data.get("data", {}).get("diff", [])

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
        _cache_set(cache_key, result, _TTL_BOARD)
        return result
    except Exception as e:
        logger.error(f"获取 {code} 行业对比失败: {e}")
        return {"code": code, "industry": "", "stocks": []}


@router.get("/northbound/{code}")
async def get_northbound(code: str):
    """获取北向资金持仓数据"""
    code = _validate_code(code)
    cache_key = f"northbound:{code}"
    cached = _cache_get(cache_key)
    if cached is not None:
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
        _cache_set(cache_key, result, _TTL_FINANCIAL)
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
    """主要指数实时行情（并发请求）"""
    def _fetch_one(name: str, secid: str) -> dict:
        try:
            url = (
                f"https://push2.eastmoney.com/api/qt/stock/get"
                f"?secid={secid}&fields=f43,f44,f45,f46,f60,f169,f170"
                f"&_={int(time.time() * 1000)}"
            )
            d = _fetch(url).get("data", {})
            price = d.get("f43", 0) / 100
            pre_close = d.get("f60", 0) / 100
            change_pct = d.get("f170", 0) / 100
            return {
                "name": name,
                "price": round(price, 2),
                "change_pct": round(change_pct, 2),
                "change": round(price - pre_close, 2),
            }
        except Exception as e:
            logger.warning(f"获取指数 {name} 失败: {e}")
            return {"name": name, "price": 0, "change_pct": 0, "change": 0}

    results = await asyncio.gather(
        *[asyncio.to_thread(_fetch_one, name, sid) for name, sid in _INDEX_MAP]
    )
    return list(results)


@router.get("/market/hot-sectors")
async def market_hot_sectors():
    """热门行业板块 + 概念板块 TOP10（并发请求）"""
    ts = int(time.time() * 1000)

    def _fetch_sectors(fs: str, top: int = 10):
        url = (
            f"https://push2.eastmoney.com/api/qt/clist/get"
            f"?pn=1&pz={top}&po=1&np=1&fltt=2&invt=2&fid=f3"
            f"&fs={fs}&fields=f3,f12,f14,f104,f105,f136,f140"
            f"&_={ts}"
        )
        data = _fetch(url)
        items = data.get("data", {}).get("diff", [])
        result = []
        for item in items:
            leader_code = str(item.get("f140", ""))
            result.append({
                "name": item.get("f14", ""),
                "change_pct": round(item.get("f3", 0), 2),
                "rise_count": item.get("f104", 0),
                "fall_count": item.get("f105", 0),
                "leader_code": leader_code,
                "leader_pct": round(item.get("f136", 0), 2),
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
    return {"industries": industries, "concepts": concepts}


@router.get("/market/stats")
async def market_stats():
    """市场涨跌家数统计"""
    try:
        url = (
            "https://push2.eastmoney.com/api/qt/ulist.np/get"
            "?fltt=2&fields=f104,f105,f106,f107"
            "&secids=1.000001,0.399001,0.399006"
            f"&_={int(time.time() * 1000)}"
        )
        data = await _fetch_async(url)
        items = data.get("data", {}).get("diff", [])
        if not items:
            return {"up_count": 0, "down_count": 0, "flat_count": 0, "limit_up": 0, "limit_down": 0}
        item = items[0]
        return {
            "up_count": item.get("f104", 0),
            "down_count": item.get("f105", 0),
            "flat_count": item.get("f106", 0),
            "limit_up": item.get("f107", 0),
            "limit_down": 0,
        }
    except Exception as e:
        logger.warning(f"获取市场统计失败: {e}")
        return {"up_count": 0, "down_count": 0, "flat_count": 0, "limit_up": 0, "limit_down": 0}


@router.get("/market/benchmark")
async def market_benchmark(count: int = 60):
    """获取沪深300基准收益曲线"""
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
        klines = data.get("data", {}).get("klines", [])
        if not klines:
            return []

        parsed = []
        for k in klines:
            parts = k.split(",")
            if len(parts) >= 3:
                parsed.append({"date": parts[0], "close": float(parts[2])})

        if not parsed:
            return []

        base = parsed[0]["close"]
        return [
            {"date": p["date"], "return_pct": round((p["close"] - base) / base * 100, 4)}
            for p in parsed
        ]
    except Exception as e:
        logger.warning(f"获取基准数据失败: {e}")
        return []
