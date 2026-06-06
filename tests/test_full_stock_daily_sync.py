import json

import pandas as pd


def _frame(close: float) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": "2026-06-04",
                "open": close - 0.2,
                "high": close + 0.4,
                "low": close - 0.3,
                "close": close,
                "volume": 1000,
                "amount": 0,
            },
            {
                "date": "2026-06-05",
                "open": close,
                "high": close + 0.5,
                "low": close - 0.2,
                "close": close + 0.1,
                "volume": 1200,
                "amount": 0,
            },
        ]
    )


def test_sync_full_stock_daily_writes_full_stock_info_coverage(tmp_path):
    from data.storage.storage import DataStorage
    from data.sync.full_stock_daily import sync_full_stock_daily

    storage = DataStorage(db_url=f"sqlite:///{tmp_path / 'test.db'}")
    storage.init_db()
    storage.save_stock_info(
        pd.DataFrame(
            [
                {"code": "000001", "name": "平安银行", "industry": "银行", "list_date": ""},
                {"code": "600519", "name": "贵州茅台", "industry": "白酒", "list_date": ""},
            ]
        )
    )
    status_path = tmp_path / "full_status.json"

    def fake_daily(code, count=260):
        return _frame(10.0 if code == "000001" else 100.0)

    def fake_snapshot():
        return {
            "000001": {"open": 11.0, "high": 11.2, "low": 10.8, "close": 11.1, "volume": 3000, "amount": 33000},
            "600519": {"open": 101.0, "high": 102.0, "low": 100.0, "close": 101.5, "volume": 4000, "amount": 406000},
        }

    summary = sync_full_stock_daily(
        storage=storage,
        status_path=status_path,
        fetch_daily_fn=fake_daily,
        fetch_snapshot_fn=fake_snapshot,
        progress_every=1,
    )

    assert summary.success is True
    assert summary.target_count == 2
    assert summary.coverage["daily_covered"] == 2
    assert summary.coverage["coverage_pct"] == 100.0
    assert storage.get_stock_daily("000001").iloc[-1]["amount"] == 33000

    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["finished"] is True
    assert status["success_count"] == 2
    assert status["coverage"]["daily_covered"] == 2


def test_quote_symbol_uses_beijing_exchange_prefix():
    from data.sync.full_stock_daily import _quote_symbol

    assert _quote_symbol("920211") == "bj920211"
    assert _quote_symbol("600519") == "sh600519"
    assert _quote_symbol("000001") == "sz000001"
