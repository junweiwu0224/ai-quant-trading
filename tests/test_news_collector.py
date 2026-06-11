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


def test_market_news_deduplicates_similar_same_stock_events(monkeypatch):
    fake_ak = types.SimpleNamespace(
        stock_info_global_em=lambda: pd.DataFrame(
            [
                {
                    "标题": "永泰能源：公司实控人因非本公司事项被证监会罚款680万元",
                    "摘要": "",
                    "发布时间": "2026-06-09 17:32:22",
                },
            ]
        ),
        stock_info_global_ths=lambda: pd.DataFrame(
            [
                {
                    "标题": "永泰能源：实控人王广西因信息披露违法违规被罚款680万元",
                    "摘要": "",
                    "发布时间": "2026-06-09 17:32:02",
                },
            ]
        ),
    )
    monkeypatch.setitem(__import__("sys").modules, "akshare", fake_ak)
    monkeypatch.setattr(
        news_collector,
        "_load_local_stock_universe",
        lambda: [{"code": "600157", "name": "永泰能源", "industry": "煤炭"}],
    )

    data = asyncio.run(news_collector.fetch_market_news_summary(max_items=10))

    assert len(data["news"]) == 1
    assert "永泰能源" in data["news"][0]["title"]
    assert "罚款680万元" in data["news"][0]["title"]
    assert data["sources"] == [{"name": data["news"][0]["source"], "count": 1}]
    assert data["linked_news_count"] == 1


def test_market_news_prioritizes_actionable_value_over_source_order(monkeypatch):
    fake_ak = types.SimpleNamespace(
        stock_zh_a_alerts_cls=lambda: pd.DataFrame(
            [
                {
                    "标题": "外围市场小幅波动",
                    "摘要": "隔夜市场窄幅震荡，A股开盘前情绪中性",
                    "发布时间": "2026-06-06 09:00:00",
                },
            ]
        ),
        stock_info_global_em=lambda: pd.DataFrame(
            [
                {
                    "标题": "宁德时代带动新能源车产业链订单增长",
                    "摘要": "新能源车和电力设备产业链订单增长，头部公司排产改善",
                    "发布时间": "2026-06-06 09:05:00",
                },
            ]
        ),
    )
    monkeypatch.setitem(__import__("sys").modules, "akshare", fake_ak)
    monkeypatch.setattr(
        news_collector,
        "_load_local_stock_universe",
        lambda: [
            {"code": "300750", "name": "宁德时代", "industry": "电力设备"},
            {"code": "002594", "name": "比亚迪", "industry": "汽车"},
        ],
    )

    data = asyncio.run(news_collector.fetch_market_news_summary(max_items=1))

    assert data["ranking"] == {
        "method": "actionable_value",
        "description": "按个股关联、主题关联、情绪强度和来源可信度综合排序",
    }
    assert [item["title"] for item in data["news"]] == ["宁德时代带动新能源车产业链订单增长"]
    assert data["news"][0]["value_score"] > 0
    assert "关联个股" in data["news"][0]["value_reasons"]
    assert "关联主题" in data["news"][0]["value_reasons"]


def test_market_news_enriches_stock_and_topic_links_from_local_universe(monkeypatch):
    fake_ak = types.SimpleNamespace(
        stock_info_global_em=lambda: pd.DataFrame(
            [
                {
                    "标题": "宁德时代带动新能源车产业链订单增长",
                    "摘要": "半导体设备公司景气度回暖，新能源车产业链公司订单改善",
                    "发布时间": "2026-06-06 22:42:26",
                }
            ]
        )
    )
    monkeypatch.setitem(__import__("sys").modules, "akshare", fake_ak)

    stock_universe = [
        {"code": "300750", "name": "宁德时代", "industry": "电力设备"},
        {"code": "688012", "name": "中微公司", "industry": "半导体"},
        {"code": "000001", "name": "平安银行", "industry": "银行"},
    ]
    monkeypatch.setattr(news_collector, "_load_local_stock_universe", lambda: stock_universe)

    data = asyncio.run(news_collector.fetch_market_news_summary(max_items=5))

    item = data["news"][0]
    assert item["stocks"] == [
        {"code": "300750", "name": "宁德时代", "industry": "电力设备", "match": "name"}
    ]
    assert item["topics"] == [
        {"name": "半导体", "match": "industry", "stock_count": 1},
        {"name": "电力设备", "match": "stock", "stock_count": 1},
        {"name": "新能源车", "match": "keyword", "stock_count": 0},
    ]
    assert data["linked_news_count"] == 1
    assert data["linked_stock_count"] == 1
    assert data["topic_count"] == 3


def test_market_news_does_not_treat_media_name_as_industry_topic(monkeypatch):
    fake_ak = types.SimpleNamespace(
        stock_info_global_em=lambda: pd.DataFrame(
            [
                {
                    "标题": "证券时报：半导体材料六氟化钨量价齐升",
                    "摘要": "中船特气国产特气龙头产能持续释放",
                    "发布时间": "2026-06-08 22:42:26",
                }
            ]
        )
    )
    monkeypatch.setitem(__import__("sys").modules, "akshare", fake_ak)

    stock_universe = [
        {"code": "688146", "name": "中船特气", "industry": "半导体"},
        {"code": "601059", "name": "信达证券", "industry": "证券"},
    ]
    monkeypatch.setattr(news_collector, "_load_local_stock_universe", lambda: stock_universe)

    data = asyncio.run(news_collector.fetch_market_news_summary(max_items=5))

    item = data["news"][0]
    assert item["stocks"] == [
        {"code": "688146", "name": "中船特气", "industry": "半导体", "match": "name"}
    ]
    assert {"name": "半导体", "match": "industry", "stock_count": 1} in item["topics"]
    assert all(topic["name"] != "证券" for topic in item["topics"])


def test_market_news_does_not_treat_exchange_phrase_as_securities_topic(monkeypatch):
    fake_ak = types.SimpleNamespace(
        stock_info_global_em=lambda: pd.DataFrame(
            [
                {
                    "标题": "半导体材料六氟化钨量价齐升 国产特气龙头企业产能持续释放",
                    "摘要": "中船特气公告称，根据上海证券交易所有关规定，股票交易属于严重异常波动情形",
                    "发布时间": "2026-06-08 22:42:26",
                }
            ]
        )
    )
    monkeypatch.setitem(__import__("sys").modules, "akshare", fake_ak)

    stock_universe = [
        {"code": "688146", "name": "中船特气", "industry": ""},
        {"code": "601059", "name": "信达证券", "industry": "证券"},
    ]
    monkeypatch.setattr(news_collector, "_load_local_stock_universe", lambda: stock_universe)

    data = asyncio.run(news_collector.fetch_market_news_summary(max_items=5))

    item = data["news"][0]
    assert item["stocks"] == [
        {"code": "688146", "name": "中船特气", "industry": "", "match": "name"}
    ]
    assert {"name": "半导体", "match": "keyword", "stock_count": 0} in item["topics"]
    assert all(topic["name"] != "证券" for topic in item["topics"])


def test_load_local_stock_universe_uses_storage_stock_list(monkeypatch):
    class FakeStorage:
        def get_stock_list(self):
            return pd.DataFrame(
                [
                    {"code": "300750", "name": "宁德时代", "industry": "电力设备"},
                    {"code": "688012", "name": "中微公司", "industry": "半导体"},
                ]
            )

    from data.storage import storage as storage_module

    monkeypatch.setattr(storage_module, "DataStorage", FakeStorage)

    assert news_collector._load_local_stock_universe() == [
        {"code": "300750", "name": "宁德时代", "industry": "电力设备"},
        {"code": "688012", "name": "中微公司", "industry": "半导体"},
    ]
