"""数据层单元测试"""
import time
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from data.collector import http_client
from data.collector import quote_service
from data.collector.quote_service import QuoteData
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

    def test_fetch_kline_tencent_fallback_routes_9_prefix_to_sh(self, monkeypatch):
        monkeypatch.setattr(http_client, "fetch_kline_mootdx", lambda code, count, frequency: None)
        monkeypatch.setattr(http_client, "fetch_json", lambda *args, **kwargs: {"data": {"klines": []}})

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

        monkeypatch.setattr(http_client, "fetch_json_tencent", fake_tencent)

        result = http_client.fetch_kline("900001", count=1, period="day")

        assert result is not None
        assert "param=sh900001,day" in calls["url"]

    @staticmethod
    def _make_quote(code: str, price: float) -> QuoteData:
        return QuoteData(
            code=code,
            name=f"测试{code}",
            price=price,
            open=price,
            high=price * 1.01,
            low=price * 0.99,
            pre_close=price,
            volume=1000,
            amount=price * 1000,
            change_pct=0.0,
            timestamp=time.time(),
        )

    def test_fetch_batch_quotes_falls_back_for_missing_codes(self, monkeypatch):
        primary_quote = self._make_quote("000001", 10.0)
        fallback_quote = self._make_quote("600519", 1800.0)
        calls = {}

        monkeypatch.setattr(
            quote_service,
            "_fetch_batch_quotes_mootdx",
            lambda codes, stock_info=None: {"000001": primary_quote},
        )

        def fake_push2(codes):
            calls["fallback_codes"] = list(codes)
            return {"600519": fallback_quote}

        monkeypatch.setattr(quote_service, "_fetch_batch_quotes_push2", fake_push2)
        monkeypatch.setattr(quote_service, "_enrich_with_tencent", lambda result, codes: calls.setdefault("tencent_codes", list(codes)))
        monkeypatch.setattr(quote_service, "_enrich_with_industry", lambda result, codes: calls.setdefault("industry_codes", list(codes)))

        result = quote_service._fetch_batch_quotes(["000001", "600519", "bad"])

        assert result == {"000001": primary_quote, "600519": fallback_quote}
        assert calls["fallback_codes"] == ["600519"]
        assert calls["tencent_codes"] == ["000001", "600519"]
        assert calls["industry_codes"] == ["000001", "600519"]

    def test_fetch_batch_quotes_mootdx_fills_name_from_stock_info(self, monkeypatch):
        class FakeManager:
            async def quotes(self, codes):
                return pd.DataFrame([
                    {"code": "000001", "name": "", "price": 11.0, "open": 10.9, "high": 11.1, "low": 10.8, "last_close": 10.95, "vol": 1200.0, "amount": 132.0},
                ])

        monkeypatch.setattr("data.collector.mootdx_client.get_mootdx_manager", lambda: FakeManager())
        result = quote_service._fetch_batch_quotes_mootdx(["000001"], stock_info={"000001": {"name": "平安银行", "industry": "银行"}})

        assert result["000001"].name == "平安银行"
        assert result["000001"].industry == "银行"
        assert result["000001"].volume == 12.0

    def test_fetch_single_quote_merges_financial_fields(self, monkeypatch):
        quote = self._make_quote("000001", 10.0)

        monkeypatch.setattr(quote_service, "_fetch_batch_quotes", lambda codes, stock_info=None: {"000001": quote})
        monkeypatch.setattr(quote_service, "_fetch_financial_data", lambda code: {"pe_ttm": 12.3, "dividend_yield": 1.8})

        result = quote_service._fetch_single_quote("000001")

        assert result is not None
        assert result.pe_ttm == 12.3
        assert result.dividend_yield == 1.8
        assert result.price == 10.0

    def test_fetch_financial_data_mootdx_maps_bps_field(self, monkeypatch):
        class FakeManager:
            async def get_kline_full(self, code, frequency=9, total=250):
                return pd.DataFrame()

            async def finance(self, code):
                return pd.DataFrame([
                    {
                        "zongguben": 1000,
                        "liutongguben": 800,
                        "zhuyingshouru": 500,
                        "jinglirun": 100,
                        "meigujingzichan": 3.21,
                    }
                ])

            async def f10(self, code):
                return {}

        monkeypatch.setattr(
            "data.collector.mootdx_client.get_mootdx_manager",
            lambda: FakeManager(),
        )
        monkeypatch.setattr(quote_service._financial_cache, "get", lambda key: (False, None))
        monkeypatch.setattr(quote_service._financial_cache, "set", lambda key, value, ttl: None)

        result = quote_service._fetch_financial_data_mootdx("000001")

        assert result["bps"] == 3.21
        assert result.get("eps", 0) == 0

    def test_enrich_with_tencent_accepts_301_codes(self):
        quote = self._make_quote("301001", 10.0)
        result = {"301001": quote}

        class FakeResponse:
            content = (
                'v_sz301001="51~测试301001~301001~10.00~10.00~10.00~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~1.2~10.5~9.5~0~0~0~0~2.3~0~0~0~150~200~1.5~0~8.00~0~0~12.0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~13.5~7.5~0";'
            ).encode("gbk")

        class FakeClient:
            def get(self, url, timeout=5, headers=None):
                return FakeResponse()

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(quote_service, "get_client", lambda: FakeClient())
        try:
            quote_service._enrich_with_tencent(result, ["301001"])
        finally:
            monkeypatch.undo()

        assert result["301001"].limit_up == 12.0
