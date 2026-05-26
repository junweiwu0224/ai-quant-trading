"""共享 HTTP 客户端 + 股票代码转换工具."""
import asyncio
import re
import time
from concurrent.futures import ThreadPoolExecutor
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


_TRANSIENT_HTTP_ERRORS = (
    httpx.TimeoutException,
    httpx.TransportError,
    httpx.RemoteProtocolError,
)
_WARNING_THROTTLE_SECONDS = 60
_warning_throttle: dict[str, float] = {}


def _should_log_warning(key: str, interval: float = _WARNING_THROTTLE_SECONDS) -> bool:
    now = time.time()
    last = _warning_throttle.get(key, 0.0)
    if now - last < interval:
        return False
    _warning_throttle[key] = now
    return True


def _log_throttled_warning(key: str, message: str) -> None:
    if _should_log_warning(key):
        logger.warning(message)


def _request_json(
    url: str,
    params: dict | None = None,
    timeout: float = 8.0,
    headers: dict | None = None,
) -> dict:
    client = get_client()
    resp = client.get(url, params=params, timeout=timeout, headers=headers)
    resp.raise_for_status()
    return resp.json()


def _request_json_with_retry(
    url: str,
    params: dict | None = None,
    timeout: float = 8.0,
    headers: dict | None = None,
    *,
    retry_key: str,
) -> dict:
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            return _request_json(url, params=params, timeout=timeout, headers=headers)
        except _TRANSIENT_HTTP_ERRORS as exc:
            last_error = exc
            if attempt == 0:
                continue
            _log_throttled_warning(retry_key, f"{retry_key}: {exc}")
        except Exception:
            raise
    if last_error is not None:
        raise last_error
    raise RuntimeError("request failed unexpectedly")


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
    return _request_json_with_retry(
        url,
        params=params,
        timeout=timeout,
        headers=headers,
        retry_key=f"http-json:{urlparse(url).netloc}{urlparse(url).path}",
    )


def fetch_json_tencent(url: str, timeout: float = 8.0) -> dict:
    """腾讯 API 专用（HTTP，不同 Referer）"""
    _validate_request_url(url)
    return _request_json_with_retry(
        url,
        timeout=timeout,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://web.ifzq.gtimg.cn",
        },
        retry_key=f"http-json-tencent:{urlparse(url).netloc}{urlparse(url).path}",
    )


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
