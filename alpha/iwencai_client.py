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

import pandas as pd
from loguru import logger

# 限流：上次查询时间戳
_last_query_time: float = 0.0
_MIN_INTERVAL: float = 12.0  # 最少间隔 12 秒


async def query_iwencai(query: str, cookie: str = "") -> pd.DataFrame:
    """自然语言查询问财

    Args:
        query: 自然语言查询语句（如 "近5日涨幅超过10%的股票"）
        cookie: 可选的问财 Cookie（提高成功率）

    Returns:
        查询结果 DataFrame，失败返回空 DataFrame
    """
    global _last_query_time

    # 限流检查
    elapsed = time.time() - _last_query_time
    if elapsed < _MIN_INTERVAL:
        wait = _MIN_INTERVAL - elapsed
        logger.debug(f"问财限流等待 {wait:.1f}s")
        await asyncio.sleep(wait)

    try:
        import pywencai

        _last_query_time = time.time()

        # pywencai 是同步库，需要在线程池中运行
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(None, lambda: pywencai.get(query=query, cookie=cookie or None))

        if df is None or not isinstance(df, pd.DataFrame):
            logger.warning(f"问财返回非 DataFrame: {type(df)}")
            return pd.DataFrame()

        if df.empty:
            logger.info(f"问财查询无结果: {query}")
            return df

        logger.info(f"问财查询成功: {query} → {len(df)} 行")
        return df

    except ImportError:
        logger.warning("pywencai 未安装，问财查询不可用")
        return pd.DataFrame()
    except Exception as e:
        logger.warning(f"问财查询失败: {e}")
        return pd.DataFrame()


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
