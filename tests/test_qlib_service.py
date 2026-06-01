import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient


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


def test_qlib_service_train_generates_cache(tmp_path, monkeypatch):
    from data.qlib import service as qlib_service

    db_path = tmp_path / "quant.db"
    cache_path = tmp_path / "predictions_cache.json"
    _seed_daily_db(db_path)
    monkeypatch.setattr(qlib_service, "DB_PATH", db_path)
    monkeypatch.setattr(qlib_service, "QLIB_PRED_CACHE", cache_path)
    qlib_service.TRAIN_STATE.update(
        {
            "training": False,
            "last_success": None,
            "last_error": None,
            "latest_date": None,
            "total": 0,
        }
    )

    client = TestClient(qlib_service.app)
    response = client.post("/train")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["training"] is False
    assert payload["latest_date"] == "2026-05-22"
    assert payload["total"] == 2
    assert cache_path.exists()
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    assert sorted(cache["predictions"].keys()) == ["2026-05-21", "2026-05-22"]

    status = client.get("/train/status").json()
    assert status["training"] is False
    assert status["last_success"] is not None
    assert status["last_error"] is None
    assert status["latest_date"] == "2026-05-22"


def test_qlib_service_health_reports_cache(tmp_path, monkeypatch):
    from data.qlib import service as qlib_service
    from data.qlib.predictor import write_predictions_cache

    cache_path = tmp_path / "predictions_cache.json"
    monkeypatch.setattr(qlib_service, "QLIB_PRED_CACHE", cache_path)
    write_predictions_cache({"2026-05-22": {"600519": 0.75}}, cache_path=cache_path)

    client = TestClient(qlib_service.app)
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["status"] == "online"
    assert payload["cache_exists"] is True
    assert payload["latest_date"] == "2026-05-22"
    assert payload["total"] == 1


def test_service_module_exposes_cli_main():
    from data.qlib.service import main

    assert callable(main)


def test_service_main_runs_current_app_after_auto_train(monkeypatch, tmp_path):
    from data.qlib import service as qlib_service

    db_path = tmp_path / "quant.db"
    cache_path = tmp_path / "predictions_cache.json"
    _seed_daily_db(db_path)
    monkeypatch.setattr(qlib_service, "DB_PATH", db_path)
    monkeypatch.setattr(qlib_service, "QLIB_PRED_CACHE", cache_path)
    captured = {}
    monkeypatch.setattr(
        qlib_service.uvicorn,
        "run",
        lambda app, host, port: captured.update({"app": app, "host": host, "port": port}),
    )
    qlib_service.TRAIN_STATE.update(
        {
            "training": False,
            "last_started": None,
            "last_success": None,
            "last_error": None,
            "latest_date": None,
            "total": 0,
        }
    )

    qlib_service.main(["--host", "127.0.0.1", "--port", "8313", "--auto-train"])

    assert captured == {"app": qlib_service.app, "host": "127.0.0.1", "port": 8313}
    assert qlib_service.TRAIN_STATE["last_success"] is not None
    assert qlib_service.TRAIN_STATE["latest_date"] == "2026-05-22"
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    assert sorted(cache["predictions"].keys()) == ["2026-05-21", "2026-05-22"]
