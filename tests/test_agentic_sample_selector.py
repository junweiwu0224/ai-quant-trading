from __future__ import annotations

from datetime import date, timedelta

import pytest

from agentic.sample_selector import BacktestSampleSelector
from utils.db import get_connection


def _create_stock_daily(db_path):
    with get_connection(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE stock_daily (
                code TEXT NOT NULL,
                date DATE NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                amount REAL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE stock_info (
                code TEXT PRIMARY KEY,
                name TEXT,
                industry TEXT
            )
            """
        )
        conn.commit()


def _insert_days(db_path, code: str, start: date, days: int):
    rows = []
    for offset in range(days):
        current = start + timedelta(days=offset)
        rows.append((code, current.isoformat(), 10, 11, 9, 10 + offset, 1000, 10000))
    with get_connection(db_path) as conn:
        conn.executemany(
            "INSERT INTO stock_daily (code, date, open, high, low, close, volume, amount) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()


def test_sample_selector_picks_codes_with_sufficient_common_coverage(tmp_path):
    db_path = tmp_path / "quant.db"
    _create_stock_daily(db_path)
    _insert_days(db_path, "sh600519", date(2024, 1, 1), 80)
    _insert_days(db_path, "000001", date(2024, 1, 5), 80)
    _insert_days(db_path, "sz000333", date(2024, 1, 1), 20)

    selector = BacktestSampleSelector(db_path)
    sample = selector.select(min_days=60, max_codes=2)

    assert sample.codes == ["000001", "600519"]
    assert sample.trading_days >= 60
    assert sample.start_date == "2024-01-05"
    assert sample.end_date == "2024-03-20"
    assert sample.source == "local_stock_daily"


def test_sample_selector_enriches_selected_codes_with_stock_names(tmp_path):
    db_path = tmp_path / "quant.db"
    _create_stock_daily(db_path)
    _insert_days(db_path, "sh600519", date(2024, 1, 1), 80)
    _insert_days(db_path, "000001", date(2024, 1, 5), 80)
    with get_connection(db_path) as conn:
        conn.executemany(
            "INSERT INTO stock_info (code, name, industry) VALUES (?, ?, ?)",
            [("sh600519", "贵州茅台", "白酒"), ("000001", "平安银行", "银行")],
        )
        conn.commit()

    sample = BacktestSampleSelector(db_path).select(min_days=60, max_codes=2)

    assert sample.names == {"000001": "平安银行", "600519": "贵州茅台"}
    assert sample.to_dict()["stock_names"] == sample.names


def test_sample_selector_rejects_when_no_stock_daily_coverage(tmp_path):
    db_path = tmp_path / "quant.db"
    _create_stock_daily(db_path)
    _insert_days(db_path, "000001", date(2024, 1, 1), 10)

    selector = BacktestSampleSelector(db_path)

    with pytest.raises(ValueError, match="no local stock_daily coverage"):
        selector.select(min_days=60, max_codes=3)
