"""问财（iwencai）自然语言查询客户端

封装 pywencai 库，提供自然语言股票查询能力。
限流：≥12s 间隔（防止反爬封禁）。
降级：不可用时返回空 DataFrame。

用法：
    from alpha.iwencai_client import query_iwencai
    df = await query_iwencai("近5日涨幅超过10%的股票")
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from loguru import logger

# 限流：上次查询时间戳
_last_query_time: float = 0.0
_MIN_INTERVAL: float = 12.0  # 最少间隔 12 秒


@dataclass(frozen=True)
class IwencaiProviderResult:
    """问财 provider 查询结果，保留失败原因而不是把所有失败折叠为空表。"""

    data: pd.DataFrame
    provider: str = "iwencai"
    provider_status: str = "ok"
    failure_type: str = ""
    failure_reason: str = ""
    response_type: str = ""
    local_wait_seconds: float = 0.0
    retry_after_seconds: float | None = None
    data_as_of: str = ""
    cache_status: str = "live_request"


def _empty_result(**kwargs: Any) -> IwencaiProviderResult:
    return IwencaiProviderResult(data=pd.DataFrame(), data_as_of=_utc_now(), **kwargs)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _classify_provider_exception(exc: Exception) -> tuple[str, str, str, float | None]:
    message = str(exc).lower()
    exc_type = type(exc).__name__
    if any(token in message for token in ("unknown field", "unsupported", "不支持", "字段未接入", "暂不支持")):
        return "ok", "unsupported_field", "问财暂不支持该字段或字段暂未接入", None
    if any(token in message for token in ("schema drift", "schema changed", "column mapping", "字段结构", "列结构")):
        return "schema_drift", "schema_drift", "问财返回字段结构变化，条件证据需重新适配", None
    if any(token in message for token in ("rate", "limit", "too many", "429", "频繁", "限流", "访问过快")):
        return "rate_limited", "rate_limited", "问财源限流或访问频率受限，请稍后重试", _MIN_INTERVAL
    if any(token in message for token in ("timeout", "timed out", "超时")):
        return "request_failed", "timeout", "问财请求超时，请稍后重试", None
    if any(token in message for token in ("login", "permission", "auth", "unauthorized", "forbidden", "权限", "登录", "认证")):
        return "provider_unavailable", "permission_denied", "问财源需要权限、登录或凭证，当前不可用", None
    logger.debug(f"问财 provider 异常类型: {exc_type}")
    return "request_failed", "request_failed", "问财查询失败，请稍后重试", None


async def query_iwencai_with_status(query: str, cookie: str = "") -> IwencaiProviderResult:
    """自然语言查询问财，并返回 provider 状态。

    该函数不会泄露 cookie 或原始异常文本，供 API 层构造可诊断的任务路由状态。
    """
    global _last_query_time

    try:
        import pywencai
    except ImportError:
        logger.warning("pywencai 未安装，问财查询不可用")
        return _empty_result(
            provider_status="provider_unavailable",
            failure_type="provider_unavailable",
            failure_reason="pywencai 未安装，问财查询不可用",
            response_type="import_error",
        )

    elapsed = time.time() - _last_query_time
    wait = 0.0
    if elapsed < _MIN_INTERVAL:
        wait = _MIN_INTERVAL - elapsed
        logger.debug(f"问财限流等待 {wait:.1f}s")
        await asyncio.sleep(wait)

    try:
        _last_query_time = time.time()

        # pywencai 是同步库，需要在线程池中运行
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(None, lambda: pywencai.get(query=query, cookie=cookie or None))

        if df is None or not isinstance(df, pd.DataFrame):
            response_type = type(df).__name__
            logger.warning(f"问财返回非 DataFrame: {response_type}")
            return _empty_result(
                provider_status="invalid_provider_response",
                failure_type="invalid_provider_response",
                failure_reason="问财返回格式异常，无法稳定解析为候选池",
                response_type=response_type,
                local_wait_seconds=wait,
            )

        if df.empty:
            logger.info(f"问财查询无结果: {query}")
            return IwencaiProviderResult(
                data=df,
                provider_status="ok",
                failure_type="no_match",
                failure_reason="问财源正常返回空结果",
                response_type="DataFrame",
                local_wait_seconds=wait,
                data_as_of=_utc_now(),
            )

        logger.info(f"问财查询成功: {query} → {len(df)} 行")
        return IwencaiProviderResult(
            data=df,
            provider_status="ok",
            response_type="DataFrame",
            local_wait_seconds=wait,
            data_as_of=_utc_now(),
        )

    except Exception as exc:
        provider_status, failure_type, failure_reason, retry_after = _classify_provider_exception(exc)
        logger.warning(f"问财查询失败: {type(exc).__name__}")
        return _empty_result(
            provider_status=provider_status,
            failure_type=failure_type,
            failure_reason=failure_reason,
            response_type=type(exc).__name__,
            local_wait_seconds=wait,
            retry_after_seconds=retry_after,
        )


async def query_iwencai(query: str, cookie: str = "") -> pd.DataFrame:
    """自然语言查询问财

    Args:
        query: 自然语言查询语句（如 "近5日涨幅超过10%的股票"）
        cookie: 可选的问财 Cookie（提高成功率）

    Returns:
        查询结果 DataFrame，失败返回空 DataFrame
    """
    result = await query_iwencai_with_status(query, cookie=cookie)
    return result.data


async def query_stock_info(code: str, cookie: str = "") -> dict:
    """通过问财获取股票综合信息

    Args:
        code: 股票代码
        cookie: 可选 Cookie

    Returns:
        包含各项信息的字典
    """
    df = await query_iwencai(f"{code}股票基本面", cookie=cookie)
    if df.empty:
        return {}

    result = {}
    try:
        row = df.iloc[0]
        for col in df.columns:
            val = row[col]
            if pd.notna(val):
                result[str(col)] = val
    except Exception as e:
        logger.warning(f"解析问财结果失败: {e}")

    return result


async def query_hot_stocks(cookie: str = "") -> pd.DataFrame:
    """查询当前热门股票

    Returns:
        热门股票 DataFrame
    """
    return await query_iwencai("今日热门股票", cookie=cookie)
