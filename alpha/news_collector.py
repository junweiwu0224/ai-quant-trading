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
import re

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
_TOPIC_KEYWORDS = {
    "半导体",
    "新能源车",
    "人工智能",
    "机器人",
    "低空经济",
    "算力",
    "存储芯片",
    "医药",
    "银行",
    "有色金属",
    "光伏",
    "电池",
}
_MEDIA_NAME_NOISE = {
    "证券时报",
    "证券日报",
    "中国证券报",
    "上海证券报",
    "财联社",
    "第一财经",
    "每日经济新闻",
    "央视新闻",
    "财新",
    "同花顺",
    "东方财富",
}
_AMBIGUOUS_GLOBAL_INDUSTRY_TERMS = {"证券", "银行"}
_TITLE_NOISE_TERMS = {
    "公司",
    "公告",
    "表示",
    "称",
    "事项",
    "本公司",
    "非本公司",
    "相关",
}
_EVENT_KEYWORDS = {
    "信息披露",
    "违法违规",
    "证监会",
    "处罚",
    "罚款",
    "行政处罚",
    "减持",
    "增持",
    "回购",
    "并购",
    "订单",
    "涨停",
    "跌停",
    "中标",
    "立案",
    "问询",
    "停牌",
    "复牌",
    "业绩",
    "亏损",
    "盈利",
    "增长",
    "突破",
}

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
_MARKET_NEWS_RANKING = {
    "method": "actionable_value",
    "description": "按个股关联、主题关联、情绪强度和来源可信度综合排序",
}
_SOURCE_PRIORITY = {
    "stock_zh_a_alerts_cls": 3,
    "stock_info_global_em": 2,
    "stock_info_global_ths": 2,
    "stock_news_main_cx": 2,
    "news_cctv": 1,
}


def _load_local_stock_universe() -> list[dict[str, str]]:
    try:
        from data.storage.storage import DataStorage
        stock_list = DataStorage().get_stock_list()
        if hasattr(stock_list, "to_dict"):
            rows = stock_list.to_dict("records")
        else:
            rows = stock_list or []
        return [
            {
                "code": str(row.get("code") or "").strip(),
                "name": str(row.get("name") or "").strip(),
                "industry": str(row.get("industry") or "").strip(),
            }
            for row in rows
            if str(row.get("code") or "").strip() and str(row.get("name") or "").strip()
        ]
    except Exception as exc:
        logger.debug(f"加载本地股票信息失败，新闻关联降级: {exc}")
        return []


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
        "summary": content,
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


def _topic_match_text(text: str) -> str:
    clean = text
    for name in sorted(_MEDIA_NAME_NOISE, key=len, reverse=True):
        clean = clean.replace(name, "")
    return clean


def _enrich_news_links(record: dict, stock_universe: list[dict[str, str]]) -> dict:
    text = f"{record.get('title', '')} {record.get('summary', '')} {record.get('content', '')}".strip()
    topic_text = _topic_match_text(text)
    linked_stocks: list[dict[str, str]] = []
    seen_codes: set[str] = set()
    for stock in stock_universe:
        name = str(stock.get("name") or "").strip()
        code = str(stock.get("code") or "").strip()
        if not name or len(name) < 2 or name not in text or code in seen_codes:
            continue
        linked_stocks.append({
            "code": code,
            "name": name,
            "industry": str(stock.get("industry") or "").strip(),
            "match": "name",
        })
        seen_codes.add(code)
        if len(linked_stocks) >= 5:
            break

    industry_counts: dict[str, int] = {}
    for stock in stock_universe:
        industry = str(stock.get("industry") or "").strip()
        if industry:
            industry_counts[industry] = industry_counts.get(industry, 0) + 1

    topics: list[dict[str, Any]] = []
    seen_topics: set[str] = set()

    def add_topic(name: str, match: str, stock_count: int = 0) -> None:
        topic = name.strip()
        if not topic or topic in seen_topics:
            return
        topics.append({"name": topic, "match": match, "stock_count": stock_count})
        seen_topics.add(topic)

    for industry, count in sorted(industry_counts.items(), key=lambda item: (-item[1], item[0])):
        if industry in _AMBIGUOUS_GLOBAL_INDUSTRY_TERMS:
            continue
        if industry in topic_text:
            add_topic(industry, "industry", count)
    for stock in linked_stocks:
        industry = stock.get("industry") or ""
        if industry:
            add_topic(industry, "stock", 1)
    for keyword in sorted(_TOPIC_KEYWORDS, key=len, reverse=True):
        if keyword in topic_text:
            add_topic(keyword, "keyword", 0)

    if linked_stocks:
        record["stocks"] = linked_stocks
    if topics:
        record["topics"] = topics[:6]
    return record


def _score_market_news_record(record: dict) -> dict:
    stocks = record.get("stocks") if isinstance(record.get("stocks"), list) else []
    topics = record.get("topics") if isinstance(record.get("topics"), list) else []
    sentiment_strength = abs(float(record.get("sentiment") or 0))
    source_priority = _SOURCE_PRIORITY.get(str(record.get("source_key") or ""), 0)

    score = (
        min(len(stocks), 5) * 3.0
        + min(len(topics), 6) * 1.5
        + min(sentiment_strength, 1.0) * 2.0
        + source_priority * 0.5
    )
    reasons: list[str] = []
    if stocks:
        reasons.append("关联个股")
    if topics:
        reasons.append("关联主题")
    if sentiment_strength >= 0.2:
        reasons.append("情绪显著")
    if source_priority >= 3:
        reasons.append("高优先级来源")
    if not reasons:
        reasons.append("滚动快讯")

    record["value_score"] = round(score, 2)
    record["value_reasons"] = reasons
    return record


def _normalize_news_title_for_dedupe(title: str) -> str:
    text = _topic_match_text(str(title or ""))
    text = re.sub(r"^[\u4e00-\u9fa5A-Za-z0-9_-]{2,12}[：:]", "", text)
    text = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]+", "", text)
    for term in sorted(_TITLE_NOISE_TERMS, key=len, reverse=True):
        text = text.replace(term, "")
    return text


def _event_terms(record: dict) -> set[str]:
    text = _normalize_news_title_for_dedupe(f"{record.get('title', '')}{record.get('summary', '')}")
    return {keyword for keyword in _EVENT_KEYWORDS if keyword in text}


def _stock_keys(record: dict) -> set[str]:
    return {
        str(stock.get("code") or stock.get("name") or "").strip()
        for stock in record.get("stocks", [])
        if str(stock.get("code") or stock.get("name") or "").strip()
    }


def _is_similar_market_news(existing: dict, candidate: dict) -> bool:
    existing_title = _normalize_news_title_for_dedupe(existing.get("title", ""))
    candidate_title = _normalize_news_title_for_dedupe(candidate.get("title", ""))
    if not existing_title or not candidate_title:
        return False
    if existing_title == candidate_title:
        return True
    shorter, longer = sorted((existing_title, candidate_title), key=len)
    if len(shorter) >= 12 and shorter in longer:
        return True

    shared_stocks = _stock_keys(existing) & _stock_keys(candidate)
    if not shared_stocks:
        return False
    shared_terms = _event_terms(existing) & _event_terms(candidate)
    if len(shared_terms) >= 2:
        return True
    if shared_terms:
        shared_chars = set(existing_title) & set(candidate_title)
        shorter_len = max(1, min(len(set(existing_title)), len(set(candidate_title))))
        return len(shared_chars) / shorter_len >= 0.6
    return False


def _market_news_preference(record: dict) -> tuple[float, int, int, int, str]:
    stocks = record.get("stocks") if isinstance(record.get("stocks"), list) else []
    topics = record.get("topics") if isinstance(record.get("topics"), list) else []
    summary = str(record.get("summary") or "")
    return (
        float(record.get("value_score") or 0),
        len(stocks),
        len(topics),
        len(summary),
        str(record.get("time") or ""),
    )


def _dedupe_market_news(records: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    for record in records:
        duplicate_index = next(
            (idx for idx, existing in enumerate(deduped) if _is_similar_market_news(existing, record)),
            None,
        )
        if duplicate_index is None:
            deduped.append(record)
            continue
        if _market_news_preference(record) > _market_news_preference(deduped[duplicate_index]):
            deduped[duplicate_index] = record
    return deduped


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

    try:
        import akshare as ak
    except ImportError:
        logger.warning("AKShare 未安装，市场新闻采集不可用")
        return {"timestamp": timestamp, "news": [], "overall_sentiment": 0, "sources": [], "errors": ["akshare_missing"]}

    loop = asyncio.get_event_loop()
    sources = _build_market_news_sources(ak)
    if not sources:
        return {"timestamp": timestamp, "news": [], "overall_sentiment": 0, "sources": [], "errors": ["no_news_source"]}
    stock_universe = _load_local_stock_universe()

    for source_key, fetcher in sources:
        try:
            df = await loop.run_in_executor(None, fetcher)
            source_records = _normalize_market_news_frame(df, source_key, max_items)
        except Exception as e:
            errors.append(f"{source_key}: {e}")
            logger.warning(f"市场新闻源失败({source_key}): {e}")
            continue

        for record in source_records:
            record = _enrich_news_links(record, stock_universe)
            record = _score_market_news_record(record)
            records.append(record)

    records = _dedupe_market_news(records)
    records.sort(
        key=lambda item: (
            -(float(item.get("value_score") or 0)),
            str(item.get("time") or ""),
        ),
        reverse=False,
    )
    records = records[:max(max_items, 0)]
    source_counts: dict[str, int] = {}
    for record in records:
        source_counts[record["source"]] = source_counts.get(record["source"], 0) + 1
    scores = [item["sentiment"] for item in records if item["sentiment"] != 0]
    overall = float(np.mean(scores)) if scores else 0
    linked_news_count = sum(1 for item in records if item.get("stocks"))
    linked_stock_keys = {
        stock.get("code") or stock.get("name")
        for item in records
        for stock in item.get("stocks", [])
        if stock.get("code") or stock.get("name")
    }
    topic_names = {
        topic.get("name")
        for item in records
        for topic in item.get("topics", [])
        if topic.get("name")
    }
    result = {
        "timestamp": timestamp,
        "news": records,
        "overall_sentiment": round(overall, 4),
        "sources": [{"name": name, "count": count} for name, count in source_counts.items()],
        "linked_news_count": linked_news_count,
        "linked_stock_count": len(linked_stock_keys),
        "topic_count": len(topic_names),
        "ranking": dict(_MARKET_NEWS_RANKING),
    }
    if errors:
        result["partial_errors"] = errors[:3]
    return result
