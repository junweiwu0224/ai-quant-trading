import sqlite3
from pathlib import Path


def _seed_signal_db(db_path: Path) -> None:
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
    rows = [
        ("sh600519", "2026-05-20", 100, 101, 99, 100, 1000, 100000),
        ("sh600519", "2026-05-21", 100, 106, 99, 105, 1000, 105000),
        ("sh600519", "2026-05-22", 105, 111, 104, 110, 1000, 110000),
        ("sh600519", "2026-05-25", 110, 116, 109, 115, 1000, 115000),
        ("sh600519", "2026-05-26", 115, 119, 114, 118, 1000, 118000),
        ("sz000001", "2026-05-20", 10, 10.2, 9.8, 10, 1000, 10000),
        ("sz000001", "2026-05-21", 10, 10.1, 9.7, 9.8, 1000, 9800),
        ("sz000001", "2026-05-22", 9.8, 10.0, 9.6, 9.7, 1000, 9700),
        ("sz000001", "2026-05-25", 9.7, 9.9, 9.5, 9.6, 1000, 9600),
        ("sz000001", "2026-05-26", 9.6, 9.8, 9.4, 9.5, 1000, 9500),
    ]
    conn.executemany(
        "INSERT INTO stock_daily (code, date, open, high, low, close, volume, amount) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()


def test_signal_engine_reads_legacy_cache_as_local_momentum(tmp_path):
    from data.qlib.predictor import write_predictions_cache
    from data.signals.engine import build_signal_context, get_signal_records

    cache_path = tmp_path / "predictions_cache.json"
    write_predictions_cache(
        {
            "2026-05-21": {"600519": 0.8, "000001": 0.2},
            "2026-05-22": {"600519": 0.9, "000001": 0.1},
        },
        cache_path=cache_path,
        method="local_momentum_v1",
    )

    records, meta = get_signal_records(cache_path=cache_path, top_n=1)
    assert meta["provider"] == "local_momentum"
    assert meta["model_version"] == "local_momentum_v1"
    assert meta["total"] == 2
    assert records[0].code == "600519"
    assert records[0].rank == 1
    assert records[0].provider == "local_momentum"
    assert records[0].confidence == "unverified"

    ctx = build_signal_context(cache_path=cache_path, top_limit=1)
    assert ctx["ordered_codes"] == ["600519"]
    assert ctx["items"]["000001"]["signal_rank"] == 2
    assert ctx["items"]["000001"]["qlib_rank"] == 2


def test_signal_validation_reports_top_return_metrics(tmp_path):
    from data.qlib.predictor import write_predictions_cache
    from data.signals.validation import validate_signal_provider

    db_path = tmp_path / "quant.db"
    cache_path = tmp_path / "predictions_cache.json"
    _seed_signal_db(db_path)
    write_predictions_cache(
        {
            "2026-05-20": {"600519": 0.9, "000001": 0.1},
            "2026-05-21": {"600519": 0.9, "000001": 0.1},
            "2026-05-22": {"600519": 0.9, "000001": 0.1},
        },
        cache_path=cache_path,
        method="local_momentum_v1",
    )

    summary = validate_signal_provider(db_path=db_path, cache_path=cache_path, top_n=1)

    assert summary.status == "validated"
    assert summary.sample_days >= 2
    assert summary.metrics["1d"]["top_n"] == 1
    assert summary.metrics["1d"]["top_excess_return_pct"] > 0
    assert summary.metrics["1d"]["rank_ic"] > 0
