"""新闻情绪因子

基于东方财富公告和新闻数据，计算情绪评分。
使用 SnowNLP（轻量中文 NLP）进行情感分析，不可用时降级为关键词匹配。

因子：
- sentiment_score: 当日情绪分 [-1, 1]
- sentiment_avg_3d: 近 3 日平均情绪
- sentiment_avg_5d: 近 5 日平均情绪
- sentiment_change: 情绪变化率（当日 vs 3日均值）
"""
from __future__ import annotations

import time
from typing import Optional

import numpy as np
from loguru import logger

from data.collector.http_client import fetch_json

# SnowNLP 可选依赖
try:
    from snownlp import SnowNLP
    _HAS_SNOWNLP = True
except ImportError:
    _HAS_SNOWNLP = False

# 情绪关键词（降级方案）
_POSITIVE_KEYWORDS = {"增长", "盈利", "突破", "利好", "创新高", "超预期", "增持", "回购", "分红", "大涨"}
_NEGATIVE_KEYWORDS = {"亏损", "下跌", "利空", "减持", "违规", "处罚", "暴跌", "风险", "退市", "业绩下滑"}


def _keyword_sentiment(text: str) -> float:
    """关键词匹配情绪分析 [-1, 1]"""
    pos = sum(1 for w in _POSITIVE_KEYWORDS if w in text)
    neg = sum(1 for w in _NEGATIVE_KEYWORDS if w in text)
    total = pos + neg
    if total == 0:
        return 0.0
    return (pos - neg) / total


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
    return _keyword_sentiment(text)


def fetch_news_sentiment(code: str, days: int = 7) -> dict[str, float]:
    """获取新闻/公告情绪因子（东财公告 + AKShare 巨潮回退）"""
    try:
        # 优先获取东财公告
        ann_url = (
            f"https://datacenter.eastmoney.com/securities/api/data/get"
            f"?type=RPT_F10_ANNOUNCEMENT&sty=ALL"
            f"&filter=(SECURITY_CODE=%22{code}%22)"
            f"&p=1&ps=20&sr=-1&st=NOTICE_DATE"
            f"&_={int(time.time() * 1000)}"
        )
        ann_data = fetch_json(ann_url, timeout=5,
                              headers={"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com"})

        scores = []
        api_result = ann_data.get("result", {})
        if api_result and api_result.get("data"):
            for row in api_result["data"]:
                title = row.get("TITLE", "") or ""
                content = row.get("CONTENT", "") or ""
                text = title + " " + content[:200]
                score = _analyze_text(text)
                if score != 0:
                    scores.append(score)

        # 东财无数据时回退到 AKShare 巨潮公告
        if not scores:
            scores = _fetch_cninfo_sentiment(code)

        if not scores:
            return {
                "sentiment_score": 0, "sentiment_avg_3d": 0,
                "sentiment_avg_5d": 0, "sentiment_change": 0,
            }

        # 当日情绪（前几条的平均）
        recent = scores[:5]
        avg_3d = np.mean(scores[:10]) if len(scores) >= 3 else np.mean(scores)
        avg_5d = np.mean(scores) if len(scores) >= 5 else np.mean(scores)
        current = np.mean(recent)
        change = current - avg_3d if avg_3d != 0 else 0

        return {
            "sentiment_score": round(float(current), 4),
            "sentiment_avg_3d": round(float(avg_3d), 4),
            "sentiment_avg_5d": round(float(avg_5d), 4),
            "sentiment_change": round(float(change), 4),
        }
    except Exception as e:
        logger.warning(f"获取 {code} 情绪因子失败: {e}")
        return {
            "sentiment_score": 0, "sentiment_avg_3d": 0,
            "sentiment_avg_5d": 0, "sentiment_change": 0,
        }


def _fetch_cninfo_sentiment(code: str) -> list[float]:
    """通过 AKShare 巨潮资讯获取公告情绪（回退方案）"""
    try:
        import akshare as ak
        df = ak.stock_notice_cninfo(symbol=code)
        if df is None or df.empty:
            return []

        scores = []
        for _, row in df.head(20).iterrows():
            title = str(row.get("公告标题", "") or "")
            score = _analyze_text(title)
            if score != 0:
                scores.append(score)
        return scores
    except Exception as e:
        logger.warning(f"AKShare 巨潮公告失败({code}): {e}")
        return []
