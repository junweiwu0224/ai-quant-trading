import asyncio
import types

import pandas as pd

from alpha import news_collector


def test_market_news_falls_back_when_legacy_alerts_missing(monkeypatch):
    fake_ak = types.SimpleNamespace(
        stock_info_global_em=lambda: pd.DataFrame(
            [
                {
                    "标题": "新能源车产业链订单增长",
                    "摘要": "车规级芯片需求增长，产业链公司订单改善",
                    "发布时间": "2026-06-06 22:42:26",
                    "链接": "https://example.test/news/1",
                }
            ]
        )
    )
    monkeypatch.setitem(__import__("sys").modules, "akshare", fake_ak)

    data = asyncio.run(news_collector.fetch_market_news_summary(max_items=5))

    assert len(data["news"]) == 1
    assert data["news"][0]["title"] == "新能源车产业链订单增长"
    assert data["news"][0]["source"] == "东方财富快讯"
    assert data["news"][0]["url"] == "https://example.test/news/1"
    assert data["sources"] == [{"name": "东方财富快讯", "count": 1}]


def test_market_news_merges_sources_and_deduplicates_titles(monkeypatch):
    fake_ak = types.SimpleNamespace(
        stock_zh_a_alerts_cls=lambda: pd.DataFrame(
            [
                {"标题": "半导体景气度回暖", "发布时间": "2026-06-06 10:00:00"},
            ]
        ),
        stock_info_global_em=lambda: pd.DataFrame(
            [
                {"标题": "半导体景气度回暖", "发布时间": "2026-06-06 10:01:00"},
                {"标题": "低空经济项目密集落地", "发布时间": "2026-06-06 10:02:00"},
            ]
        ),
    )
    monkeypatch.setitem(__import__("sys").modules, "akshare", fake_ak)

    data = asyncio.run(news_collector.fetch_market_news_summary(max_items=10))

    assert [item["title"] for item in data["news"]] == [
        "半导体景气度回暖",
        "低空经济项目密集落地",
    ]
    assert data["news"][0]["source"] == "财联社A股电报"
    assert data["news"][1]["source"] == "东方财富快讯"
