"""数据层单元测试"""
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from data.storage.storage import DataStorage


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

    def test_get_latest_date_empty(self, db):
        """无数据时最新日期为 None"""
        assert db.get_latest_date("999999") is None
