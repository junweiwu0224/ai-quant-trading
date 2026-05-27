"""数据层单元测试"""
from datetime import date
import time
import tempfile
from pathlib import Path
import asyncio
import subprocess
import sys

import httpx
import pandas as pd
import pytest

from data.collector import http_client
from data.collector import quote_service
from data.collector.quote_service import QuoteData
from data.collector import shadow_validator
from data.collector.data_source import Quote
import data.providers.astock_data_adapter as astock_provider
from data.providers.astock_data_adapter import AStockDataAdapter
from data.services.valuation_service import ValuationService
from data.storage.storage import DataStorage, StockDaily, StockInfo, UserWatchlist


@pytest.fixture
def db(tmp_path):
    """创建临时数据库"""
    db_url = f"sqlite:///{tmp_path / 'test.db'}"
    storage = DataStorage(db_url=db_url)
    storage.init_db()
    return storage


@pytest.fixture
def sample_daily_df():
    """示例日K数据"""
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
            "open": [10.0, 10.5, 10.3],
            "high": [10.8, 10.9, 10.6],
            "low": [9.8, 10.2, 10.1],
            "close": [10.5, 10.3, 10.5],
            "volume": [100000, 120000, 110000],
            "amount": [1050000, 1236000, 1155000],
        }
    )


@pytest.fixture
def sample_info_df():
    """示例股票信息"""
    return pd.DataFrame(
        {
            "code": ["000001", "600519"],
            "name": ["平安银行", "贵州茅台"],
            "industry": ["银行", "白酒"],
            "list_date": ["1991-04-03", "2001-08-27"],
        }
    )


class TestStorage:
    def test_init_db_creates_tables(self, db):
        """数据库初始化应创建表"""
        assert db.get_all_stock_codes() == []

    def test_save_and_query_daily(self, db, sample_daily_df):
        """保存并查询日K数据"""
        count = db.save_stock_daily("000001", sample_daily_df)
        assert count == 3

        result = db.get_stock_daily("000001")
        assert len(result) == 3
        assert result.iloc[0]["close"] == 10.5

    def test_save_daily_dedup(self, db, sample_daily_df):
        """重复保存应去重"""
        db.save_stock_daily("000001", sample_daily_df)
        count = db.save_stock_daily("000001", sample_daily_df)
        assert count == 0

        result = db.get_stock_daily("000001")
        assert len(result) == 3

    def test_save_daily_dedup_legacy_plain_code_rows(self, db, sample_daily_df):
        """旧库无前缀记录再次写入时应避免逻辑重复"""
        session = db._get_session()
        try:
            for _, row in sample_daily_df.iterrows():
                session.add(
                    StockDaily(
                        code="000001",
                        date=pd.Timestamp(row["date"]).date(),
                        open=row.get("open"),
                        high=row.get("high"),
                        low=row.get("low"),
                        close=row.get("close"),
                        volume=row.get("volume"),
                        amount=row.get("amount"),
                        adj_factor=row.get("adj_factor", 1.0),
                    )
                )
            session.commit()
        finally:
            session.close()

        count = db.save_stock_daily("000001", sample_daily_df)

        assert count == 0
        result = db.get_stock_daily("000001")
        assert len(result) == 3

    def test_get_stock_daily_deduplicates_code_variants(self, db, sample_daily_df):
        session = db._get_session()
        try:
            first_row = sample_daily_df.iloc[0]
            row_date = pd.Timestamp(first_row["date"]).date()
            session.add_all(
                [
                    StockDaily(
                        code="000001",
                        date=row_date,
                        open=first_row["open"],
                        high=first_row["high"],
                        low=first_row["low"],
                        close=first_row["close"],
                        volume=first_row["volume"],
                        amount=first_row["amount"],
                        adj_factor=1.0,
                    ),
                    StockDaily(
                        code="sz000001",
                        date=row_date,
                        open=first_row["open"],
                        high=first_row["high"],
                        low=first_row["low"],
                        close=first_row["close"],
                        volume=first_row["volume"],
                        amount=first_row["amount"],
                        adj_factor=1.0,
                    ),
                ]
            )
            session.commit()
        finally:
            session.close()

        result = db.get_stock_daily("000001")

        assert len(result) == 1
        assert result.iloc[0]["code"] == "000001"

    def test_save_and_query_info(self, db, sample_info_df):
        """保存并查询股票信息"""
        count = db.save_stock_info(sample_info_df)
        assert count == 2

        codes = db.get_all_stock_codes()
        assert set(codes) == {"000001", "600519"}

    def test_save_info_update(self, db, sample_info_df):
        """重复保存股票信息应更新"""
        db.save_stock_info(sample_info_df)
        updated = pd.DataFrame(
            {
                "code": ["000001"],
                "name": ["平安银行(更新)"],
                "industry": ["银行"],
                "list_date": ["1991-04-03"],
            }
        )
        db.save_stock_info(updated)
        codes = db.get_all_stock_codes()
        assert len(codes) == 2

    def test_memory_db_url_uses_in_memory_database(self, sample_daily_df):
        db = DataStorage(db_url="sqlite:///:memory:")

        count = db.save_stock_daily("000001", sample_daily_df)
        result = db.get_stock_daily("000001")

        assert count == 3
        assert len(result) == 3

    def test_save_stock_info_merges_duplicate_code_variants(self, db):
        session = db._get_session()
        try:
            session.add_all(
                [
                    StockInfo(code="600519", name="贵州茅台", industry="旧行业", list_date="2001-08-27"),
                    StockInfo(code="sh600519", name="", industry="旧行业2", list_date=""),
                ]
            )
            session.commit()
        finally:
            session.close()

        count = db.save_stock_info(
            pd.DataFrame(
                {
                    "code": ["600519"],
                    "name": ["贵州茅台"],
                    "industry": ["白酒"],
                    "list_date": ["2001-08-27"],
                }
            )
        )

        assert count == 1
        result = db.get_stock_list()
        assert len(result) == 1
        row = result[result["code"] == "600519"].iloc[0]
        assert row["industry"] == "白酒"

    def test_query_with_date_range(self, db, sample_daily_df):
        """按日期范围查询"""
        db.save_stock_daily("000001", sample_daily_df)
        result = db.get_stock_daily(
            "000001",
            start_date=pd.Timestamp("2024-01-03").date(),
            end_date=pd.Timestamp("2024-01-04").date(),
        )
        assert len(result) == 2

    def test_query_empty(self, db):
        """查询无数据应返回空 DataFrame"""
        result = db.get_stock_daily("999999")
        assert result.empty

    def test_get_latest_date(self, db, sample_daily_df):
        """获取最新日期"""
        db.save_stock_daily("000001", sample_daily_df)
        latest = db.get_latest_date("000001")
        assert latest == pd.Timestamp("2024-01-04").date()

    def test_get_stock_list_returns_plain_codes(self, db, sample_info_df):
        db.save_stock_info(sample_info_df)

        result = db.get_stock_list()

        assert set(result["code"]) == {"000001", "600519"}

    def test_get_all_stock_codes_deduplicates_code_variants(self, db):
        session = db._get_session()
        try:
            session.add_all(
                [
                    StockInfo(code="600519", name="贵州茅台", industry="白酒", list_date="2001-08-27"),
                    StockInfo(code="sh600519", name="贵州茅台", industry="白酒", list_date="2001-08-27"),
                ]
            )
            session.commit()
        finally:
            session.close()

        assert db.get_all_stock_codes() == ["600519"]

    def test_get_stock_list_deduplicates_code_variants(self, db):
        session = db._get_session()
        try:
            session.add_all(
                [
                    StockInfo(code="600519", name="贵州茅台", industry="", list_date="2001-08-27"),
                    StockInfo(code="sh600519", name="", industry="白酒", list_date="2001-08-27"),
                ]
            )
            session.commit()
        finally:
            session.close()

        result = db.get_stock_list()

        assert len(result) == 1
        row = result.iloc[0]
        assert row["code"] == "600519"
        assert row["name"] == "贵州茅台"
        assert row["industry"] == "白酒"

    def test_update_stock_industry_updates_legacy_plain_code_row(self, db):
        session = db._get_session()
        try:
            session.add(StockInfo(code="600519", name="贵州茅台", industry="旧行业", list_date="2001-08-27"))
            session.commit()
        finally:
            session.close()

        count = db.update_stock_industry({"sh600519": "白酒"})

        assert count == 1
        result = db.get_stock_list()
        row = result[result["code"] == "600519"].iloc[0]
        assert row["industry"] == "白酒"
        assert len(result) == 1

    def test_update_stock_industry_merges_duplicate_code_variants(self, db):
        session = db._get_session()
        try:
            session.add_all(
                [
                    StockInfo(code="600519", name="贵州茅台", industry="旧行业", list_date="2001-08-27"),
                    StockInfo(code="sh600519", name="贵州茅台", industry="旧行业2", list_date="2001-08-27"),
                ]
            )
            session.commit()
        finally:
            session.close()

        count = db.update_stock_industry({"600519": "白酒"})

        assert count == 1
        result = db.get_stock_list()
        assert len(result) == 1
        row = result[result["code"] == "600519"].iloc[0]
        assert row["industry"] == "白酒"

    def test_remove_from_watchlist_deletes_legacy_plain_code_row(self, db):
        session = db._get_session()
        try:
            session.add(UserWatchlist(code="600519", added_at="2024-01-01T00:00:00"))
            session.commit()
        finally:
            session.close()

        removed = db.remove_from_watchlist("sh600519")

        assert removed is True
        assert db.get_watchlist() == []

    def test_remove_from_watchlist_deletes_all_code_variants(self, db):
        session = db._get_session()
        try:
            session.add_all(
                [
                    UserWatchlist(code="600519", added_at="2024-01-01T00:00:00"),
                    UserWatchlist(code="sh600519", added_at="2024-01-02T00:00:00"),
                ]
            )
            session.commit()
        finally:
            session.close()

        removed = db.remove_from_watchlist("600519")

        assert removed is True
        assert db.get_watchlist() == []
        assert db.remove_from_watchlist("600519") is False

    def test_get_watchlist_deduplicates_code_variants(self, db):
        session = db._get_session()
        try:
            session.add_all(
                [
                    UserWatchlist(code="600519", added_at="2024-01-01T00:00:00"),
                    UserWatchlist(code="sh600519", added_at="2024-01-02T00:00:00"),
                ]
            )
            session.commit()
        finally:
            session.close()

        assert db.get_watchlist() == ["600519"]

    def test_get_watchlist_with_info_deduplicates_code_variants(self, db, sample_daily_df):
        session = db._get_session()
        try:
            session.add_all(
                [
                    UserWatchlist(code="600519", added_at="2024-01-01T00:00:00"),
                    UserWatchlist(code="sh600519", added_at="2024-01-02T00:00:00"),
                    StockInfo(code="600519", name="贵州茅台", industry="", list_date="2001-08-27"),
                    StockInfo(code="sh600519", name="", industry="白酒", list_date="2001-08-27"),
                    StockDaily(
                        code="600519",
                        date=pd.Timestamp("2024-01-03").date(),
                        open=10.0,
                        high=10.5,
                        low=9.8,
                        close=10.2,
                        volume=1000,
                        amount=10200,
                        adj_factor=1.0,
                    ),
                    StockDaily(
                        code="sh600519",
                        date=pd.Timestamp("2024-01-03").date(),
                        open=10.0,
                        high=10.5,
                        low=9.8,
                        close=10.3,
                        volume=1000,
                        amount=10300,
                        adj_factor=1.0,
                    ),
                ]
            )
            session.commit()
        finally:
            session.close()

        result = db.get_watchlist_with_info()

        assert len(result) == 1
        assert result[0]["code"] == "600519"
        assert result[0]["name"] == "贵州茅台"
        assert result[0]["industry"] == "白酒"
        assert result[0]["latest_price"] == 10.3
        assert result[0]["latest_date"] == "2024-01-03"

    def test_remove_from_watchlist_is_idempotent_for_missing_record(self, db):
        assert db.remove_from_watchlist("sh600519") is False
        assert db.remove_from_watchlist("600519") is False

    def test_remove_from_watchlist_rejects_invalid_format_without_ghost_row(self, db):
        db.add_to_watchlist("600519")

        removed = db.remove_from_watchlist("600519.SH")

        assert removed is False
        assert db.get_watchlist() == ["600519"]

    def test_add_to_watchlist_rejects_invalid_code(self, db):
        added = db.add_to_watchlist("600519.SH")

        assert added is False
        assert db.get_watchlist() == []

    def test_normalize_stock_code_rejects_invalid_value(self):
        assert http_client.normalize_stock_code("000001") == "000001"
        assert http_client.normalize_stock_code(" abc ") is None
        assert http_client.normalize_stock_code("600519.SH") is None

    def test_http_client_exposes_transport_helpers_only(self):
        assert hasattr(http_client, "get_client")
        assert hasattr(http_client, "close_client")
        assert hasattr(http_client, "fetch_json")
        assert hasattr(http_client, "fetch_json_tencent")
        assert hasattr(http_client, "run_sync")
        assert hasattr(http_client, "normalize_stock_code")
        assert hasattr(http_client, "code_to_secid")
        assert hasattr(http_client, "calculate_limit_prices")
        assert not hasattr(http_client, "fetch_kline")
        assert not hasattr(http_client, "fetch_industry_batch")
        assert not hasattr(http_client, "fetch_concepts_batch")

    def test_astock_provider_contract_fetch_kline_tencent_fallback_routes_9_prefix_to_sh(self, monkeypatch):
        class FakeManager:
            async def get_kline_full(self, code, frequency=9, total=250):
                return pd.DataFrame()

        monkeypatch.setattr("data.collector.mootdx_client.get_mootdx_manager", lambda: FakeManager())
        monkeypatch.setattr(astock_provider, "fetch_json", lambda *args, **kwargs: {"data": {"klines": []}})

        calls = {}

        def fake_tencent(url, timeout=8):
            calls["url"] = url
            return {
                "data": {
                    "sh900001": {
                        "qfqday": [["2024-01-02", "10", "10.5", "10.8", "9.8", "1000"]]
                    }
                }
            }

        monkeypatch.setattr(astock_provider, "fetch_json_tencent", fake_tencent)

        result = astock_provider.fetch_kline("900001", count=1, period="day")

        assert result is not None
        assert "param=sh900001,day" in calls["url"]

    def test_astock_provider_contract_fetch_kline_prefers_tencent_when_push2his_fails(self, monkeypatch):
        class FakeManager:
            async def get_kline_full(self, code, frequency=9, total=250):
                return pd.DataFrame()

        monkeypatch.setattr("data.providers.astock_data_adapter._get_mootdx_manager", lambda: FakeManager())
        monkeypatch.setattr(astock_provider, "fetch_json", lambda *args, **kwargs: (_ for _ in ()).throw(httpx.RemoteProtocolError("server disconnected")))

        calls = {}

        def fake_tencent(url, timeout=8):
            calls["url"] = url
            return {
                "data": {
                    "sh600519": {
                        "qfqday": [["2024-01-02", "10", "10.5", "10.8", "9.8", "1000"]]
                    }
                }
            }

        monkeypatch.setattr(astock_provider, "fetch_json_tencent", fake_tencent)

        result = astock_provider.fetch_kline("600519", count=1, period="day")

        assert result is not None
        assert result["klines_raw"][0][0] == "2024-01-02"
        assert "param=sh600519,day" in calls["url"]

    def test_astock_provider_contract_provider_helpers_live_in_astock_module(self, monkeypatch):
        def fake_fetch_json(url, params=None, timeout=8.0, headers=None):
            if params and params.get("reportName") == "RPT_F10_BASIC_ORGINFO":
                return {
                    "result": {
                        "data": [
                            {
                                "SECURITY_CODE": "000001",
                                "INDUSTRYCSRC1": "银行",
                                "BOARD_NAME_LEVEL": "主板-金融-银行",
                            },
                            {
                                "SECURITY_CODE": "600519",
                                "INDUSTRYCSRC1": "白酒",
                                "BOARD_NAME_LEVEL": "主板-消费-白酒",
                            },
                        ]
                    }
            }
            if "push2delay.eastmoney.com" in url:
                if "0.000001" in url:
                    return {"data": {"f129": "白马,银行"}}
                return {"data": {"f129": "消费,白酒"}}
            return {"data": {}}

        monkeypatch.setattr(astock_provider, "fetch_json", fake_fetch_json)

        industry = astock_provider.fetch_industry_batch(["000001", "600519"])
        concepts = astock_provider.fetch_concepts_batch(["000001", "600519"])

        assert industry == {
            "000001": {"industry": "银行", "sector": "金融", "concepts": "银行"},
            "600519": {"industry": "白酒", "sector": "消费", "concepts": "白酒"},
        }
        assert concepts == {"000001": "白马,银行", "600519": "消费,白酒"}

    def test_fetch_json_retries_transient_httpx_errors(self, monkeypatch):
        calls = {"count": 0}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"ok": True}

        class FakeClient:
            def get(self, url, params=None, timeout=8.0, headers=None):
                calls["count"] += 1
                if calls["count"] == 1:
                    raise httpx.RemoteProtocolError("server disconnected")
                return FakeResponse()

        monkeypatch.setattr(http_client, "get_client", lambda: FakeClient())

        result = http_client.fetch_json("https://push2delay.eastmoney.com/api/qt/stock/get")

        assert result == {"ok": True}
        assert calls["count"] == 2

    def test_astock_provider_contract_adapter_data_source_methods_delegate_to_mootdx_manager(self, monkeypatch):
        class FakeManager:
            async def quotes(self, symbols):
                return pd.DataFrame([
                    {
                        "code": "000001",
                        "name": "",
                        "price": 11.0,
                        "open": 10.9,
                        "high": 11.1,
                        "low": 10.8,
                        "last_close": 10.95,
                        "vol": 1200.0,
                        "amount": 132.0,
                        "bid1": 10.9,
                        "ask1": 11.0,
                    }
                ])

            async def bars(self, symbol, frequency=9, start=0, offset=800):
                return pd.DataFrame([
                    {"datetime": "2024-01-02", "open": 10.0, "close": 10.5, "high": 10.8, "low": 9.8, "vol": 1000, "amount": 1050000},
                    {"datetime": "2024-01-03", "open": 10.5, "close": 10.3, "high": 10.9, "low": 10.2, "vol": 1200, "amount": 1236000},
                ])

            async def get_kline_full(self, symbol, frequency=9, total=5000):
                return pd.DataFrame([
                    {"high": 11, "low": 9, "vol": 100},
                    {"high": 12, "low": 8, "vol": 200},
                    {"high": 13, "low": 7, "vol": 300},
                    {"high": 14, "low": 6, "vol": 400},
                    {"high": 15, "low": 5, "vol": 500},
                ])

            async def minute(self, symbol):
                return pd.DataFrame([
                    {"time": "09:30", "price": 10.1, "volume": 100},
                ])

            async def finance(self, symbol):
                return pd.DataFrame([
                    {
                        "zongguben": 1000,
                        "liutongguben": 800,
                        "zhuyingshouru": 500,
                        "jinglirun": 100,
                        "meigujingzichan": 3.21,
                    }
                ])

            async def xdxr(self, symbol):
                return pd.DataFrame([
                    {"date": "2024-01-01", "reason": "分红"},
                ])

            async def f10(self, symbol, name=None):
                return {"财务分析": "摘要", "股东研究": "持股结构"}

        monkeypatch.setattr("data.collector.mootdx_client.get_mootdx_manager", lambda: FakeManager())

        adapter = AStockDataAdapter()

        quotes = asyncio.run(adapter.get_realtime_quotes(["000001"]))
        kline = asyncio.run(adapter.get_kline("000001"))
        minute = asyncio.run(adapter.get_minute("000001"))
        finance = asyncio.run(adapter.get_finance("000001"))
        xdxr = asyncio.run(adapter.get_xdxr("000001"))
        f10 = asyncio.run(adapter.get_f10("000001", section="财务分析"))

        assert len(quotes) == 1
        assert quotes[0].code == "000001"
        assert quotes[0].price == 11.0
        assert quotes[0].volume == 12.0

        assert isinstance(kline, pd.DataFrame)
        assert list(kline["close"]) == [10.5, 10.3]
        assert isinstance(minute, pd.DataFrame)
        assert not minute.empty
        assert finance["bps"] == 3.21
        assert finance["high_52w"] == 15
        assert finance["low_52w"] == 5
        assert finance["f10_text"] == "摘要"
        assert isinstance(xdxr, pd.DataFrame)
        assert xdxr.iloc[0]["reason"] == "分红"
        assert f10 == {"财务分析": "摘要"}

    def test_quote_service_polls_provider_and_updates_callbacks(self, monkeypatch, db):
        """QuoteService 应以 provider 为主路更新缓存和回调。"""
        calls = []

        class FakeProvider:
            async def get_realtime_quotes(self, codes):
                calls.append(list(codes))
                return [
                    Quote(
                        code="000001",
                        name="平安银行",
                        price=10.0,
                        open=9.9,
                        high=10.2,
                        low=9.8,
                        pre_close=9.9,
                        volume=1000,
                        amount=10000,
                        change_pct=1.01,
                    )
                ]

        callback_batches = []
        service = quote_service.QuoteService(interval=1.0, provider=FakeProvider(), storage=db)
        service.on_update(lambda quotes: callback_batches.append(quotes))
        service.subscribe(["000001", "bad"])

        monkeypatch.setattr(quote_service, "_enrich_with_tencent", lambda result, codes: None)
        monkeypatch.setattr(quote_service, "_enrich_with_industry", lambda result, codes: None)

        service._poll_once()

        quote = service.get_quote("000001")
        assert calls == [["000001"]]
        assert quote is not None
        assert quote.name == "平安银行"
        assert quote.price == 10.0
        assert service.update_count == 1
        assert callback_batches and callback_batches[0]["000001"].price == 10.0

    def test_quote_service_subscription_replacement_normalizes_codes(self, db):
        """订阅替换应只保留合法 6 位股票代码。"""
        service = quote_service.QuoteService(interval=1.0, provider=AStockDataAdapter(), storage=db)

        service.subscribe(["sz000001", "600519", "bad"])
        service.set_codes(["sh600519", "oops"])

        assert service.subscription_count == 1
        assert service.get_quote("000001") is None

    def test_fetch_market_stocks_keeps_successful_pages_on_later_failure(self, monkeypatch):
        calls = {"count": 0}

        first_page_items = [
            {"f12": f"000{i:03d}", "f14": f"测试{i}", "f2": "10", "f3": "1", "f5": "1", "f6": "1", "f7": "1", "f8": "1", "f9": "1", "f15": "1", "f16": "1", "f17": "1", "f20": "1", "f21": "1", "f23": "1", "f100": "银行", "f50": "1"}
            for i in range(1, 101)
        ]

        def fake_fetch_json(url, params=None, timeout=8.0, headers=None):
            calls["count"] += 1
            if calls["count"] == 1:
                return {"data": {"diff": first_page_items}}
            raise httpx.RemoteProtocolError("server disconnected")

        monkeypatch.setattr("alpha.screener.fetch_json", fake_fetch_json)
        monkeypatch.setattr("alpha.screener._MARKET_CACHE_TTL", 0)
        monkeypatch.setattr("alpha.screener._market_cache", [])
        monkeypatch.setattr("alpha.screener._market_cache_ts", 0)

        result = __import__("alpha.screener", fromlist=["_fetch_market_stocks"])._fetch_market_stocks(max_pages=2)

        assert len(result) == 100
        assert result[0]["code"] == "000001"
        assert calls["count"] == 2

    def test_data_provenance_snapshot_round_trip(self, db):
        """数据快照应保留来源版本和 JSON payload"""
        db.save_data_source_version(
            "astock",
            "2026.05.24",
            metadata={"adapter": "AStockDataAdapter"},
        )

        snapshot_id = db.save_data_snapshot(
            "000001",
            "valuation",
            "astock",
            "2026.05.24",
            {"peg_next_year": 0.16, "labels": ["高性价比"]},
            quality_status="ok",
        )

        versions = db.get_data_source_versions("astock", active_only=True)
        latest = db.get_latest_data_snapshot("000001", "valuation")

        assert versions == [
            {
                "id": versions[0]["id"],
                "source": "astock",
                "version": "2026.05.24",
                "active": True,
                "metadata": {"adapter": "AStockDataAdapter"},
                "created_at": versions[0]["created_at"],
                "updated_at": versions[0]["updated_at"],
            }
        ]
        assert versions[0]["updated_at"]
        assert latest["id"] == snapshot_id
        assert latest["code"] == "000001"
        assert latest["domain"] == "valuation"
        assert latest["source"] == "astock"
        assert latest["source_version"] == "2026.05.24"
        assert latest["payload"] == {"peg_next_year": 0.16, "labels": ["高性价比"]}
        assert latest["payload_hash"]
        assert latest["quality_status"] == "ok"
        assert latest["created_at"]

    def test_data_provenance_source_version_updated_at_changes_on_update(self, db, monkeypatch):
        """数据源版本更新应刷新 updated_at"""
        ticks = iter(["2026-05-24T00:00:00.000001", "2026-05-24T00:00:00.000002"])
        monkeypatch.setattr("data.storage.storage._now_iso", lambda: next(ticks))

        version_id = db.save_data_source_version("astock", "v1", active=False)
        first = db.get_data_source_versions("astock")[0]

        same_version_id = db.save_data_source_version("astock", "v1", active=True)
        updated = db.get_data_source_versions("astock")[0]
        health = db.get_data_source_health()

        assert same_version_id == version_id
        assert updated["created_at"] == first["created_at"]
        assert updated["updated_at"] == "2026-05-24T00:00:00.000002"
        assert first["updated_at"] == "2026-05-24T00:00:00.000001"
        assert updated["active"] is True
        assert health["sources"]["astock"]["last_seen_at"] == updated["updated_at"]

    def test_data_provenance_payload_hash_is_stable_for_equivalent_payload_order(self, db):
        """payload_hash 应不受 JSON key 顺序影响"""
        db.save_data_snapshot(
            "000001",
            "valuation",
            "astock",
            "v1",
            {"peg": 0.16, "nested": {"b": 2, "a": 1}},
        )
        first = db.get_latest_data_snapshot("000001", "valuation")

        db.save_data_snapshot(
            "000001",
            "valuation",
            "astock",
            "v1",
            {"nested": {"a": 1, "b": 2}, "peg": 0.16},
        )
        second = db.get_latest_data_snapshot("000001", "valuation")

        assert first["payload"] == {"peg": 0.16, "nested": {"b": 2, "a": 1}}
        assert second["payload"] == {"nested": {"a": 1, "b": 2}, "peg": 0.16}
        assert first["payload_hash"] == second["payload_hash"]

    def test_data_provenance_snapshot_sanitizes_json_payload(self, db):
        """快照 payload 应清洗 NaN 和日期为 JSON 安全值"""
        payload = {
            "price": float("nan"),
            "captured_at": date(2026, 5, 24),
            "nested": [1, float("inf"), {"seen_at": date(2026, 5, 23)}],
        }

        db.save_data_snapshot("000001", "quote", "astock", "v1", payload)
        latest = db.get_latest_data_snapshot("000001", "quote")

        assert latest["payload"] == {
            "price": None,
            "captured_at": "2026-05-24",
            "nested": [1, None, {"seen_at": "2026-05-23"}],
        }
        assert latest["payload_hash"]
        assert len(latest["payload_hash"]) == 64
        assert latest["payload_hash"] == db.get_latest_data_snapshot("000001", "quote")["payload_hash"]

    def test_data_provenance_quality_summary_infers_diff_count_from_details(self, db):
        """quality 记录应从 details.diff_count 推导 diff_count"""
        db.save_data_quality_record(
            "000001",
            "quote",
            "shadow_compare",
            "diff",
            {"diff_count": 2},
        )

        summary = db.get_data_quality_summary("quote")

        assert summary["shadow_diff_count"] == 2

    def test_data_provenance_quality_summary_and_source_health(self, db):
        """质量台账应能按 domain 汇总并给出数据源健康摘要"""
        db.save_data_source_version("astock", "v1", active=False)
        db.save_data_source_version("astock", "v2", active=True)
        db.save_data_source_version("eastmoney", "daily-20260524", active=True)

        db.save_data_quality_record("000001", "valuation", "shadow_compare", "ok", diff_count=0)
        db.save_data_quality_record("000002", "valuation", "shadow_compare", "diff", diff_count=3)
        db.save_data_quality_record("600519", "quote", "freshness", "warn", diff_count=0)

        valuation_summary = db.get_data_quality_summary("valuation")
        all_summary = db.get_data_quality_summary()
        health = db.get_data_source_health()

        assert valuation_summary["total"] == 2
        assert valuation_summary["by_status"] == {"diff": 1, "ok": 1}
        assert valuation_summary["shadow_diff_count"] == 3
        assert all_summary["total"] == 3
        assert all_summary["by_domain"] == {"quote": 1, "valuation": 2}
        assert all_summary["shadow_diff_count"] == 3
        assert health["total_active_sources"] == 2
        assert health["sources"]["astock"]["latest_version"] == "v2"
        assert health["sources"]["astock"]["active_versions"] == ["v2"]
        assert health["sources"]["eastmoney"]["latest_version"] == "daily-20260524"


class TestAStockValuation:
    def test_astock_adapter_imports_in_clean_interpreter(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from data.providers.astock_data_adapter import AStockDataAdapter; print(AStockDataAdapter.__name__)",
            ],
            cwd=Path(__file__).resolve().parent.parent,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0, result.stderr
        assert "AStockDataAdapter" in result.stdout

    def test_data_source_interface_exposes_valuation_snapshot(self):
        from data.collector.data_source import DataSource

        assert hasattr(DataSource, "get_valuation_snapshot")

    def test_adapter_build_summary_creates_peg_snapshot(self, monkeypatch):
        adapter = AStockDataAdapter()

        monkeypatch.setattr(
            adapter,
            "fetch_report_rows",
            lambda code, page_size=20: [
                {
                    "title": "看好成长",
                    "stock_code": "000001",
                    "stock_name": "平安银行",
                    "org": "某券商",
                    "author": "分析师A",
                    "date": "2026-05-01",
                    "rating": "买入",
                    "target_price": 12.0,
                    "this_year_eps": 1.0,
                    "next_year_eps": 1.5,
                    "next_two_year_eps": 2.0,
                    "this_year_pe": 10.0,
                    "next_year_pe": 8.0,
                    "next_two_year_pe": 6.0,
                    "actual_last_year_eps": 0.8,
                    "summary": "test",
                    "encode_url": "abc",
                }
            ],
        )

        summary = adapter.build_summary("000001")

        assert summary is not None
        assert summary.consensus_label == "高性价比"
        valuation = asyncio.run(adapter.get_valuation_snapshot("000001"))
        assert valuation["report_count"] == 1
        assert valuation["consensus_label"] == "高性价比"

    def test_valuation_service_snapshot_includes_valuation_block(self, monkeypatch, db):
        service = ValuationService(storage=db)

        monkeypatch.setattr(
            service,
            "_load_quote_context",
            lambda code: type(
                "Ctx",
                (),
                {
                    "code": "000001",
                    "name": "平安银行",
                    "industry": "银行",
                    "sector": "",
                    "price": 10.0,
                    "pe_ttm": 8.0,
                    "pb_ratio": 1.1,
                    "roe": 12.0,
                    "market_cap": 1000.0,
                    "circulating_cap": 900.0,
                    "source": "realtime",
                },
            )(),
        )
        monkeypatch.setattr(
            service.adapter,
            "get_valuation_snapshot",
            lambda code, report_limit=8: {
                "code": "000001",
                "stock_name": "平安银行",
                "report_count": 2,
                "latest_report_date": "2026-05-01",
                "latest_rating": "买入",
                "latest_org": "某券商",
                "target_price": 12.0,
                "actual_last_year_eps": 0.8,
                "forecast_this_year_eps": 1.0,
                "forecast_next_year_eps": 1.5,
                "forecast_next_two_year_eps": 2.0,
                "forecast_this_year_pe": 10.0,
                "forecast_next_year_pe": 8.0,
                "forecast_next_two_year_pe": 6.0,
                "growth_this_year_pct": 25.0,
                "growth_next_year_pct": 50.0,
                "growth_next_two_year_pct": 33.33,
                "consensus_label": "高性价比",
                "reports": [],
            },
        )

        snapshot = service.build_snapshot("000001")
        latest = db.get_latest_data_snapshot("000001", "valuation")

        assert snapshot["valuation_bucket"] == "高性价比"
        assert snapshot["peg_next_year"] == 0.16
        assert snapshot["report_count"] == 2
        assert snapshot["source"] == "astock"
        assert snapshot["source_version"] == AStockDataAdapter.SOURCE_VERSION
        assert snapshot["quality_status"] == "ok"
        assert snapshot["snapshot_at"]
        assert latest is not None
        assert latest["payload"]["peg_next_year"] == 0.16
        assert latest["source"] == "astock"
