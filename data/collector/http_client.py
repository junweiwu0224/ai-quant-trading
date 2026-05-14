"""共享 HTTP 客户端 + 股票代码转换工具

集中所有 HTTP 请求逻辑，使用 httpx 连接池。
供 quote_service.py 和 stock_detail.py 共用。
"""
import asyncio
import time
import re
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from urllib.parse import urlparse

import httpx
from loguru import logger

# ── 异步包装器（防止 mootdx/akshare 阻塞 FastAPI 事件循环）──
_sync_executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="datasource")


async def run_sync(func, *args, **kwargs):
    """将同步阻塞调用包装为异步"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_sync_executor, lambda: func(*args, **kwargs))

# ── 连接池客户端 ──
_client: httpx.Client | None = None


def get_client() -> httpx.Client:
    """获取共享 httpx 客户端（懒初始化，连接池复用）"""
    global _client
    if _client is None:
        _client = httpx.Client(
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            timeout=httpx.Timeout(8.0),
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://quote.eastmoney.com",
            },
        )
    return _client


def close_client():
    global _client
    if _client is not None:
        _client.close()
        _client = None


def fetch_json(url: str, params: dict | None = None, timeout: float = 8.0,
               headers: dict | None = None) -> dict:
    """统一 JSON 请求，返回解析后的 dict"""
    _validate_request_url(url)
    client = get_client()
    resp = client.get(url, params=params, timeout=timeout, headers=headers)
    resp.raise_for_status()
    return resp.json()


def fetch_json_tencent(url: str, timeout: float = 8.0) -> dict:
    """腾讯 API 专用（HTTP，不同 Referer）"""
    _validate_request_url(url)
    client = get_client()
    resp = client.get(url, timeout=timeout, headers={
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://web.ifzq.gtimg.cn",
    })
    resp.raise_for_status()
    return resp.json()


# ── 股票代码转换 ──

_STOCK_CODE_RE = re.compile(r"^(?:[sS][hH]|[sS][zZ])?(\d{6})$")


def _validate_request_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"unsupported url scheme: {parsed.scheme!r}")
    host = parsed.hostname or ""
    if not host.endswith((".eastmoney.com", ".gtimg.cn")):
        raise ValueError(f"unsupported request host: {host!r}")


def normalize_stock_code(code: str) -> str | None:
    """规范化股票代码，非法输入返回 None"""
    normalized = str(code).strip()
    match = _STOCK_CODE_RE.fullmatch(normalized)
    return match.group(1) if match else None


def code_to_secid(code: str) -> str:
    """股票代码 → 东方财富 secid（沪市 1.x，深市 0.x）"""
    normalized = normalize_stock_code(code)
    if not normalized:
        raise ValueError(f"invalid stock code: {code!r}")
    return f"1.{normalized}" if normalized.startswith(("6", "9")) else f"0.{normalized}"


def calculate_limit_prices(code: str, pre_close: float) -> tuple[float, float]:
    """计算涨跌停价（主板 ±10%，创业板/科创板 ±20%）"""
    if pre_close <= 0:
        return 0.0, 0.0
    normalized = normalize_stock_code(code)
    if not normalized:
        return 0.0, 0.0
    limit_pct = 0.20 if normalized.startswith(("300", "301", "688")) else 0.10
    return round(pre_close * (1 + limit_pct), 2), round(pre_close * (1 - limit_pct), 2)


# ── K 线数据（mootdx + push2his + 腾讯回退）──

def fetch_kline_mootdx(code: str, count: int = 250, frequency: int = 9) -> dict | None:
    """通过 mootdx 获取 K 线数据（新数据源路径）

    返回 {highs, lows, volumes, klines_raw, name}
    """
    try:
        from data.collector.mootdx_client import get_mootdx_manager
        manager = get_mootdx_manager()
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            df = loop.run_until_complete(manager.get_kline_full(code, frequency=frequency, total=count))
        finally:
            loop.close()

        if df is None or df.empty:
            return None

        klines_raw = []
        for _, row in df.iterrows():
            # 标准化格式：[date, open, close, high, low, volume]
            klines_raw.append([
                str(row.get("datetime", "")),
                str(row.get("open", 0)),
                str(row.get("close", 0)),
                str(row.get("high", 0)),
                str(row.get("low", 0)),
                str(row.get("vol", 0)),
            ])
        return {"klines_raw": klines_raw, "name": ""}
    except Exception as e:
        logger.warning(f"mootdx K线失败({code}): {e}")
        return None


def fetch_kline(code: str, count: int = 250, period: str = "day") -> dict | None:
    """获取 K 线原始数据，返回 {highs, lows, volumes, klines_raw}

    根据 DATA_SOURCE_MODE 选择数据源：
    - new: mootdx 为主，push2his/腾讯回退
    - legacy: push2his 为主，腾讯回退
    用于 52 周高低计算和 stock_detail K 线展示。
    """
    from config.settings import DATA_SOURCE_MODE

    normalized = normalize_stock_code(code)
    if not normalized:
        return None
    code = normalized

    freq_map = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 60,
                "day": 9, "daily": 9, "week": 10, "weekly": 10,
                "month": 11, "monthly": 11}
    freq = freq_map.get(period, 9)

    if DATA_SOURCE_MODE == "new":
        # 新数据源：mootdx 为主
        result = fetch_kline_mootdx(code, count, freq)
        if result:
            return result
        # mootdx 失败，回退 push2his
        logger.info(f"mootdx K线为空({code})，回退push2his")
    secid = code_to_secid(code)
    klt_map = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 60,
               "day": 101, "daily": 101, "week": 102, "weekly": 102,
               "month": 103, "monthly": 103}
    klt = klt_map.get(period, 101)

    # 尝试 push2his
    klines_raw = []
    name = ""
    try:
        url = (
            f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
            f"?secid={secid}"
            f"&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13"
            f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
            f"&klt={klt}&fqt=1&end=20500101&lmt={count}"
            f"&_={int(time.time() * 1000)}"
        )
        data = fetch_json(url, timeout=5)
        d = data.get("data") or {}
        name = d.get("name", "")
        for k in d.get("klines", []):
            parts = k.split(",")
            if len(parts) >= 6:
                # push2his 成交量单位是股，统一转为手（÷100）
                parts[5] = str(float(parts[5]) / 100)
                klines_raw.append(parts)
    except Exception as e:
        logger.warning(f"push2his K线失败({code}): {e}")

    # 腾讯回退
    if not klines_raw:
        try:
            prefix = "sh" if code.startswith(("6", "9")) else "sz"
            period_map = {"day": "day", "daily": "day", "week": "week",
                          "weekly": "week", "month": "month", "monthly": "month"}
            tp = period_map.get(period, "day")
            turl = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{code},{tp},,,{count},qfq"
            tdata = fetch_json_tencent(turl, timeout=8)
            stock_data = (tdata.get("data") or {}).get(f"{prefix}{code}", {})
            klines = stock_data.get(f"qfq{tp}") or stock_data.get(tp) or []
            for k in klines:
                if len(k) >= 6:
                    # 腾讯K线成交量单位是股，统一转为手（÷100）
                    klines_raw.append([str(k[0]), str(k[1]), str(k[2]),
                                       str(k[3]), str(k[4]), str(float(k[5]) / 100)])
        except Exception as e:
            logger.warning(f"腾讯K线回退失败({code}): {e}")

    if not klines_raw:
        return None

    return {"klines_raw": klines_raw, "name": name}


# ── 行业数据批量获取 ──

_DATACENTER_URL = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
_DATACENTER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://emweb.securities.eastmoney.com/",
}


def fetch_industry_batch(codes: list[str]) -> dict[str, dict[str, str]]:
    """从东方财富 F10 API 批量获取行业分类

    返回 {code: {industry, sector, concepts}}
    """
    valid_codes = [code for code in (normalize_stock_code(c) for c in codes) if code]
    if not valid_codes:
        return {}
    try:
        code_list = ",".join(f'"{c}"' for c in valid_codes)
        params = {
            "reportName": "RPT_F10_BASIC_ORGINFO",
            "columns": "SECURITY_CODE,INDUSTRYCSRC1,BOARD_NAME_LEVEL",
            "filter": f"(SECURITY_CODE in ({code_list}))",
            "pageSize": len(valid_codes),
            "pageNumber": 1,
            "source": "HSF10",
            "client": "PC",
        }
        data = fetch_json(_DATACENTER_URL, params=params, timeout=10,
                          headers=_DATACENTER_HEADERS)
        result = {}
        for row in (data.get("result", {}) or {}).get("data", []) or []:
            code = row.get("SECURITY_CODE", "")
            if not code:
                continue
            industry = row.get("INDUSTRYCSRC1", "")
            board_level = row.get("BOARD_NAME_LEVEL", "")
            parts = [p.strip() for p in board_level.split("-") if p.strip()] if board_level else []
            sector = parts[1] if len(parts) >= 2 else ""
            concepts = parts[2] if len(parts) >= 3 else ""
            result[code] = {"industry": industry, "sector": sector, "concepts": concepts}
        return result
    except Exception as e:
        logger.warning(f"批量获取行业数据失败: {e}")
        return {}


# ── 概念数据（push2delay，单只但并发）──

_PUSH2_FIELDS = "f57,f129"


def _fetch_concepts_single(code: str) -> str:
    """从 push2delay 获取单只股票概念（逗号分隔）"""
    try:
        secid = code_to_secid(code)
        url = (
            f"https://push2delay.eastmoney.com/api/qt/stock/get"
            f"?secid={secid}&fields={_PUSH2_FIELDS}"
            f"&ut=fa5fd1943c7b386f172d6893dbbd1d0c"
            f"&_={int(time.time() * 1000)}"
        )
        data = fetch_json(url, timeout=5)
        return str((data.get("data") or {}).get("f129") or "")
    except Exception:
        return ""


def fetch_concepts_batch(codes: list[str]) -> dict[str, str]:
    """并发获取多只股票概念，返回 {code: "概念1,概念2,..."}"""
    if not codes:
        return {}
    from concurrent.futures import ThreadPoolExecutor, as_completed
    result = {}
    with ThreadPoolExecutor(max_workers=min(len(codes), 10)) as pool:
        futures = {pool.submit(_fetch_concepts_single, c): c for c in codes}
        for fut in as_completed(futures):
            code = futures[fut]
            try:
                concepts = fut.result()
                if concepts:
                    result[code] = concepts
            except Exception:
                pass
    return result
