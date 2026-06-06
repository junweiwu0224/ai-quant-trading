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
from typing import Any, Callable

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

_TITLE_FIELDS = ("标题", "新闻标题", "title", "summary", "摘要", "内容", "content", "事件")
_CONTENT_FIELDS = ("摘要", "内容", "content", "summary", "新闻内容", "digest")
_TIME_FIELDS = ("发布时间", "时间", "time", "日期", "date", "发布日期", "showTime")
_URL_FIELDS = ("链接", "新闻链接", "url", "detailUrl", "uniqueUrl")
_STOCK_NEWS_SOURCE_LABELS = {
    "stock_zh_a_alerts_cls": "财联社A股电报",
    "stock_info_global_em": "东方财富快讯",
    "stock_info_global_ths": "同花顺快讯",
    "stock_news_main_cx": "财新数据通",
    "news_cctv": "央视新闻",
}


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


def _first_present(row: Any, fields: tuple[str, ...]) -> str:
    for field in fields:
        try:
            value = row.get(field, "")
        except AttributeError:
            value = ""
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() != "nan":
            return text
    return ""


def _normalize_market_news_row(row: Any, source_key: str) -> dict | None:
    title = _first_present(row, _TITLE_FIELDS)
    content = _first_present(row, _CONTENT_FIELDS)
    if not title and content:
        title = content
    title = title.strip()
    if not title:
        return None

    time_text = _first_present(row, _TIME_FIELDS)
    url = _first_present(row, _URL_FIELDS)
    sentiment_text = f"{title} {content}".strip()
    sentiment = _analyze_text(sentiment_text)

    return {
        "title": title,
        "time": time_text,
        "url": url,
        "source": _STOCK_NEWS_SOURCE_LABELS.get(source_key, source_key),
        "source_key": source_key,
        "sentiment": round(sentiment, 4),
    }


def _normalize_market_news_frame(df: Any, source_key: str, max_items: int) -> list[dict]:
    if df is None or getattr(df, "empty", True):
        return []

    records: list[dict] = []
    for _, row in df.head(max(max_items, 1)).iterrows():
        record = _normalize_market_news_row(row, source_key)
        if record:
            records.append(record)
    return records


def _build_market_news_sources(ak: Any) -> list[tuple[str, Callable[[], Any]]]:
    sources: list[tuple[str, Callable[[], Any]]] = []

    legacy_alerts = getattr(ak, "stock_zh_a_alerts_cls", None)
    if callable(legacy_alerts):
        sources.append(("stock_zh_a_alerts_cls", legacy_alerts))

    for name in ("stock_info_global_em", "stock_info_global_ths", "stock_news_main_cx"):
        fn = getattr(ak, name, None)
        if callable(fn):
            sources.append((name, fn))

    news_cctv = getattr(ak, "news_cctv", None)
    if callable(news_cctv):
        sources.append(("news_cctv", lambda: news_cctv(date=datetime.now().strftime("%Y%m%d"))))

    return sources


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
    timestamp = datetime.now().isoformat()
    errors: list[str] = []
    records: list[dict] = []
    seen_titles: set[str] = set()
    source_counts: dict[str, int] = {}

    try:
        import akshare as ak
    except ImportError:
        logger.warning("AKShare 未安装，市场新闻采集不可用")
        return {"timestamp": timestamp, "news": [], "overall_sentiment": 0, "sources": [], "errors": ["akshare_missing"]}

    loop = asyncio.get_event_loop()
    sources = _build_market_news_sources(ak)
    if not sources:
        return {"timestamp": timestamp, "news": [], "overall_sentiment": 0, "sources": [], "errors": ["no_news_source"]}

    for source_key, fetcher in sources:
        if len(records) >= max_items:
            break
        try:
            df = await loop.run_in_executor(None, fetcher)
            source_records = _normalize_market_news_frame(df, source_key, max_items)
        except Exception as e:
            errors.append(f"{source_key}: {e}")
            logger.warning(f"市场新闻源失败({source_key}): {e}")
            continue

        for record in source_records:
            key = record["title"].strip()
            if key in seen_titles:
                continue
            seen_titles.add(key)
            records.append(record)
            source_counts[record["source"]] = source_counts.get(record["source"], 0) + 1
            if len(records) >= max_items:
                break

    scores = [item["sentiment"] for item in records if item["sentiment"] != 0]
    overall = float(np.mean(scores)) if scores else 0
    result = {
        "timestamp": timestamp,
        "news": records,
        "overall_sentiment": round(overall, 4),
        "sources": [{"name": name, "count": count} for name, count in source_counts.items()],
    }
    if errors:
        result["partial_errors"] = errors[:3]
    return result
