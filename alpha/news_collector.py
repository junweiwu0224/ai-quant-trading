"""新闻采集与情绪分析模块

基于 AKShare 东方财富新闻接口，采集个股新闻和全市场热点关键词。
使用 SnowNLP 进行情绪分析，输出结构化数据供 LLM 和因子系统使用。

数据源：
- 个股新闻：ak.stock_news_em(symbol=code)
- 热门关键词：ak.stock_hot_keyword_em(symbol=code)
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

import numpy as np
from loguru import logger

# SnowNLP 可选依赖
try:
    from snownlp import SnowNLP
    _HAS_SNOWNLP = True
except ImportError:
    _HAS_SNOWNLP = False

# 情绪关键词（降级方案）
_POSITIVE_KEYWORDS = {"增长", "盈利", "突破", "利好", "创新高", "超预期", "增持", "回购", "分红", "大涨", "涨停"}
_NEGATIVE_KEYWORDS = {"亏损", "下跌", "利空", "减持", "违规", "处罚", "暴跌", "风险", "退市", "业绩下滑", "跌停"}


def _analyze_text(text: str) -> float:
    """分析单条文本情绪 [-1, 1]"""
    if not text or len(text) < 5:
        return 0.0
    if _HAS_SNOWNLP:
        try:
            score = SnowNLP(text).sentiments
            return score * 2 - 1  # [0,1] -> [-1,1]
        except Exception:
            pass
    # 关键词降级
    pos = sum(1 for w in _POSITIVE_KEYWORDS if w in text)
    neg = sum(1 for w in _NEGATIVE_KEYWORDS if w in text)
    total = pos + neg
    if total == 0:
        return 0.0
    return (pos - neg) / total


async def fetch_stock_news(code: str, max_items: int = 20) -> list[dict]:
    """获取个股新闻列表

    Returns:
        [{"title": "...", "source": "...", "time": "...", "sentiment": 0.5}, ...]
    """
    try:
        import akshare as ak
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(None, lambda: ak.stock_news_em(symbol=code))

        if df is None or df.empty:
            return []

        records = []
        for _, row in df.head(max_items).iterrows():
            title = str(row.get("新闻标题", "") or "")
            sentiment = round(_analyze_text(title), 4)
            records.append({
                "title": title,
                "source": str(row.get("文章来源", "") or ""),
                "time": str(row.get("发布时间", "") or ""),
                "url": str(row.get("新闻链接", "") or ""),
                "sentiment": sentiment,
            })
        return records

    except ImportError:
        logger.warning("AKShare 未安装，新闻采集不可用")
        return []
    except Exception as e:
        logger.warning(f"获取个股新闻失败({code}): {e}")
        return []


async def fetch_hot_keywords(code: str) -> list[str]:
    """获取个股热门关键词

    Returns:
        ["锂电池", "新能源", ...]
    """
    try:
        import akshare as ak
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(None, lambda: ak.stock_hot_keyword_em(symbol=code))

        if df is None or df.empty:
            return []

        keywords = []
        if "关键词" in df.columns:
            keywords = df["关键词"].dropna().head(10).tolist()
        return [str(k) for k in keywords]

    except Exception as e:
        logger.warning(f"获取热门关键词失败({code}): {e}")
        return []


async def compute_news_sentiment(code: str, max_items: int = 20) -> dict:
    """计算新闻情绪因子

    Returns:
        {
            "sentiment_score": 0.3,      # 当日情绪 [-1, 1]
            "sentiment_avg_3d": 0.2,     # 近3日平均
            "sentiment_avg_5d": 0.1,     # 近5日平均
            "sentiment_change": 0.1,     # 变化率
            "news_count": 15,            # 新闻数量
            "hot_keywords": ["锂电池", ...],
        }
    """
    news = await fetch_stock_news(code, max_items)
    if not news:
        return {
            "sentiment_score": 0, "sentiment_avg_3d": 0,
            "sentiment_avg_5d": 0, "sentiment_change": 0,
            "news_count": 0, "hot_keywords": [],
        }

    scores = [n["sentiment"] for n in news if n["sentiment"] != 0]
    if not scores:
        return {
            "sentiment_score": 0, "sentiment_avg_3d": 0,
            "sentiment_avg_5d": 0, "sentiment_change": 0,
            "news_count": len(news), "hot_keywords": [],
        }

    # 获取热门关键词
    keywords = await fetch_hot_keywords(code)

    recent = scores[:5]
    avg_3d = float(np.mean(scores[:10])) if len(scores) >= 3 else float(np.mean(scores))
    avg_5d = float(np.mean(scores)) if len(scores) >= 5 else float(np.mean(scores))
    current = float(np.mean(recent))
    change = current - avg_3d if avg_3d != 0 else 0

    return {
        "sentiment_score": round(current, 4),
        "sentiment_avg_3d": round(avg_3d, 4),
        "sentiment_avg_5d": round(avg_5d, 4),
        "sentiment_change": round(change, 4),
        "news_count": len(news),
        "hot_keywords": keywords,
    }


async def fetch_market_news_summary(max_items: int = 30) -> dict:
    """获取全市场新闻摘要

    Returns:
        {
            "timestamp": "...",
            "news": [...],
            "overall_sentiment": 0.2,
            "summary": "今日市场情绪偏正面..."
        }
    """
    try:
        import akshare as ak
        loop = asyncio.get_event_loop()
        # 获取市场快讯
        df = await loop.run_in_executor(None, ak.stock_zh_a_alerts_cls)

        if df is None or df.empty:
            return {"timestamp": datetime.now().isoformat(), "news": [], "overall_sentiment": 0}

        records = []
        scores = []
        for _, row in df.head(max_items).iterrows():
            title = str(row.get("标题", "") or row.get("内容", "") or "")
            sentiment = _analyze_text(title)
            records.append({
                "title": title,
                "time": str(row.get("发布时间", "") or ""),
                "sentiment": round(sentiment, 4),
            })
            if sentiment != 0:
                scores.append(sentiment)

        overall = float(np.mean(scores)) if scores else 0

        return {
            "timestamp": datetime.now().isoformat(),
            "news": records,
            "overall_sentiment": round(overall, 4),
        }

    except Exception as e:
        logger.warning(f"获取市场新闻失败: {e}")
        return {"timestamp": datetime.now().isoformat(), "news": [], "overall_sentiment": 0}
