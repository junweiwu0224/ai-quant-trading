import json
import sqlite3
from pathlib import Path

from click.testing import CliRunner


def _seed_daily_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE stock_info (code TEXT PRIMARY KEY, name TEXT, industry TEXT)"
    )
    conn.execute(
        """CREATE TABLE stock_daily (
            code TEXT,
            date TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            amount REAL
        )"""
    )
    conn.executemany(
        "INSERT INTO stock_info (code, name, industry) VALUES (?, ?, ?)",
        [
            ("sh600519", "贵州茅台", "白酒"),
            ("sz000001", "平安银行", "银行"),
        ],
    )
    rows = [
        ("sh600519", "2026-05-20", 100.0, 102.0, 99.0, 100.0, 1000.0, 100000.0),
        ("sh600519", "2026-05-21", 100.0, 105.0, 99.5, 104.0, 1200.0, 124800.0),
        ("sh600519", "2026-05-22", 104.0, 110.0, 103.0, 109.0, 1500.0, 163500.0),
        ("sz000001", "2026-05-20", 10.0, 10.2, 9.8, 10.0, 5000.0, 50000.0),
        ("sz000001", "2026-05-21", 10.0, 10.1, 9.7, 9.9, 4500.0, 44550.0),
        ("sz000001", "2026-05-22", 9.9, 10.0, 9.5, 9.6, 4300.0, 41280.0),
    ]
    conn.executemany(
        "INSERT INTO stock_daily (code, date, open, high, low, close, volume, amount) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()


def test_generate_predictions_writes_dashboard_cache(tmp_path):
    from data.qlib.predictor import generate_predictions

    db_path = tmp_path / "quant.db"
    cache_path = tmp_path / "predictions_cache.json"
    _seed_daily_db(db_path)

    summary = generate_predictions(
        db_path=db_path,
        cache_path=cache_path,
        lookback_days=3,
        limit=20,
    )

    assert summary.success is True
    assert summary.latest_date == "2026-05-22"
    assert summary.total == 2
    assert summary.cache_path == cache_path
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert sorted(payload.keys()) == [
        "generated_at",
        "latest_date",
        "method",
        "predictions",
        "total",
    ]
    assert payload["method"] == "local_momentum_v1"
    assert payload["latest_date"] == "2026-05-22"
    latest_predictions = payload["predictions"]["2026-05-22"]
    assert set(latest_predictions.keys()) == {"600519", "000001"}
    assert latest_predictions["600519"] > latest_predictions["000001"]
    assert all(0.0 <= score <= 1.0 for score in latest_predictions.values())


def test_generate_historical_predictions_writes_daily_series(tmp_path):
    from data.qlib.predictor import generate_historical_predictions

    db_path = tmp_path / "quant.db"
    cache_path = tmp_path / "predictions_cache.json"
    _seed_daily_db(db_path)

    summary = generate_historical_predictions(
        db_path=db_path,
        cache_path=cache_path,
        start_date="2026-05-20",
        end_date="2026-05-22",
        lookback_days=2,
        min_history_days=2,
        limit=20,
    )

    assert summary.success is True
    assert summary.latest_date == "2026-05-22"
    assert summary.total == 2
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert payload["method"] == "local_momentum_v1"
    assert payload["latest_date"] == "2026-05-22"
    assert sorted(payload["predictions"].keys()) == ["2026-05-21", "2026-05-22"]
    assert set(payload["predictions"]["2026-05-21"].keys()) == {"600519", "000001"}
    assert set(payload["predictions"]["2026-05-22"].keys()) == {"600519", "000001"}
    assert payload["predictions"]["2026-05-22"]["600519"] > payload["predictions"]["2026-05-22"]["000001"]


def test_generate_historical_predictions_refuses_sparse_history(tmp_path):
    from data.qlib.predictor import generate_historical_predictions

    db_path = tmp_path / "quant.db"
    cache_path = tmp_path / "predictions_cache.json"
    _seed_daily_db(db_path)

    summary = generate_historical_predictions(
        db_path=db_path,
        cache_path=cache_path,
        start_date="2026-05-20",
        end_date="2026-05-20",
        lookback_days=3,
        min_history_days=2,
        min_universe_size=2,
    )

    assert summary.success is False
    assert summary.total == 0
    assert "no usable historical predictions" in summary.message
    assert not cache_path.exists()


def test_generate_historical_predictions_cli_writes_cache(tmp_path):
    from scripts.generate_qlib_historical_predictions import main

    db_path = tmp_path / "quant.db"
    cache_path = tmp_path / "predictions_cache.json"
    _seed_daily_db(db_path)

    result = CliRunner().invoke(
        main,
        [
            "--db-path",
            str(db_path),
            "--cache-path",
            str(cache_path),
            "--start",
            "2026-05-20",
            "--end",
            "2026-05-22",
            "--lookback",
            "2",
            "--min-history-days",
            "2",
        ],
    )

    assert result.exit_code == 0
    assert "historical predictions: success=True latest=2026-05-22 total=2" in result.output
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert sorted(payload["predictions"].keys()) == ["2026-05-21", "2026-05-22"]


def test_write_predictions_cache_creates_parent_directory(tmp_path):
    from data.qlib.predictor import write_predictions_cache

    cache_path = tmp_path / "nested" / "predictions_cache.json"
    summary = write_predictions_cache(
        predictions={"2026-05-22": {"600519": 0.75}},
        cache_path=cache_path,
        method="unit_test",
    )

    assert summary.success is True
    assert cache_path.exists()
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert payload["predictions"]["2026-05-22"]["600519"] == 0.75
    assert payload["total"] == 1


def test_generate_predictions_refuses_single_stock_universe(tmp_path):
    from data.qlib.predictor import generate_predictions

    db_path = tmp_path / "quant.db"
    cache_path = tmp_path / "predictions_cache.json"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE stock_daily (
            code TEXT,
            date TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            amount REAL
        )"""
    )
    conn.executemany(
        "INSERT INTO stock_daily (code, date, open, high, low, close, volume, amount) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("sh920001", "2026-05-20", 10.0, 10.2, 9.8, 10.0, 1000.0, 10000.0),
            ("sh920001", "2026-05-21", 10.0, 10.4, 9.9, 10.3, 1100.0, 11330.0),
            ("sh920001", "2026-05-22", 10.3, 10.6, 10.2, 10.5, 1200.0, 12600.0),
        ],
    )
    conn.commit()
    conn.close()

    summary = generate_predictions(db_path=db_path, cache_path=cache_path, lookback_days=3)

    assert summary.success is False
    assert summary.total == 1
    assert "insufficient stock_daily coverage" in summary.message
    assert not cache_path.exists()


def test_generate_predictions_removes_stale_cache_when_universe_is_insufficient(tmp_path):
    from data.qlib.predictor import generate_predictions

    db_path = tmp_path / "quant.db"
    cache_path = tmp_path / "predictions_cache.json"
    cache_path.write_text(
        json.dumps({"predictions": {"2026-05-21": {"600519": 0.91}}}),
        encoding="utf-8",
    )
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE stock_daily (
            code TEXT,
            date TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            amount REAL
        )"""
    )
    conn.executemany(
        "INSERT INTO stock_daily (code, date, open, high, low, close, volume, amount) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("sh920001", "2026-05-20", 10.0, 10.2, 9.8, 10.0, 1000.0, 10000.0),
            ("sh920001", "2026-05-21", 10.0, 10.4, 9.9, 10.3, 1100.0, 11330.0),
            ("sh920001", "2026-05-22", 10.3, 10.6, 10.2, 10.5, 1200.0, 12600.0),
        ],
    )
    conn.commit()
    conn.close()

    summary = generate_predictions(db_path=db_path, cache_path=cache_path, lookback_days=3)

    assert summary.success is False
    assert not cache_path.exists()
