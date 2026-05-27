# Qlib 链路修复实施计划

> **面向代理执行者：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务逐步执行此计划。步骤使用复选框 (`- [ ]`) 追踪。

**目标：** 修复 `python -m data.qlib.service` 缺失导致的 Qlib/AI 预测链路断裂，让仪表盘能启动本地 Qlib 兼容服务、生成预测缓存，并让机会池获得真实 AI 覆盖。

**架构：** 新增一个轻量 Qlib 兼容模块 `data/qlib`，先不引入完整 pyqlib 训练栈，而是基于本地 `stock_daily` 和 `stock_info` 生成确定性横截面预测分数，写入现有 `data/qlib/predictions_cache.json` 合同。FastAPI 微服务负责 `/health`、`/train`、`/train/status` 和 `--auto-train` 启动补缓存；现有 dashboard Qlib 路由继续读缓存并代理训练触发。

**技术栈：** Python 3.11、FastAPI、uvicorn、SQLite、pytest、FastAPI TestClient、现有 `config.settings`、`utils.db`、`data.storage.storage` 代码格式工具。

---

## 文件结构

- 新建 `data/qlib/__init__.py`
  - 声明轻量 Qlib 兼容包，保证 `python -m data.qlib.service` 可导入。
- 新建 `data/qlib/predictor.py`
  - 只负责从 SQLite 读取本地日线，计算确定性预测分数，写入预测缓存。
  - 对外暴露 `QlibPredictionSummary`、`generate_predictions()`、`write_predictions_cache()`。
- 新建 `data/qlib/service.py`
  - 只负责 FastAPI 服务、训练状态和 CLI 启动。
  - 对外暴露 `app`、`train_now()`、`main()`。
- 新建 `tests/test_qlib_service.py`
  - 覆盖 predictor 写缓存、服务训练、健康状态、CLI 参数入口的核心行为。
- 修改 `dashboard/routers/qlib.py`
  - 健康接口返回更明确的 `cache_exists`、`cache_path`、`service_url`、`prediction_total`，保持旧字段兼容。
  - `/api/qlib/top` 继续读取预测缓存，测试临时缓存能返回 Top 数据。
- 修改 `tests/test_api_v2_full.py`
  - 扩展 `TestQlib`，用临时预测缓存验证 `/api/qlib/top` 与 `/api/qlib/health` 合同。
- 修改 `tests/test_dashboard.py`
  - 增加机会池 AI 覆盖回归：当 `_load_qlib_context()` 有覆盖时，不应再给该标的打 `AI未覆盖`。

---

### 任务 1: 预测缓存生成器

**文件：**
- 新建: `data/qlib/__init__.py`
- 新建: `data/qlib/predictor.py`
- 测试: `tests/test_qlib_service.py`

- [ ] **步骤 1：编写失败测试**

在 `tests/test_qlib_service.py` 写入以下测试。该测试先构造临时 SQLite 数据库，再要求 `generate_predictions()` 写出符合现有 dashboard 合同的 `{"predictions": {"YYYY-MM-DD": {"600519": score}}}`。

```python
import json
import sqlite3
from pathlib import Path


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
    from data.qlib.predictor import generate_predictions, write_predictions_cache

    db_path = tmp_path / "quant.db"
    cache_path = tmp_path / "predictions_cache.json"
    _seed_daily_db(db_path)

    summary = generate_predictions(db_path=db_path, cache_path=cache_path, lookback_days=3, limit=20)

    assert summary.success is True
    assert summary.latest_date == "2026-05-22"
    assert summary.total == 2
    assert summary.cache_path == cache_path
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert sorted(payload.keys()) == ["generated_at", "latest_date", "method", "predictions", "total"]
    assert payload["method"] == "local_momentum_v1"
    assert payload["latest_date"] == "2026-05-22"
    assert set(payload["predictions"]["2026-05-22"].keys()) == {"600519", "000001"}
    assert payload["predictions"]["2026-05-22"]["600519"] > payload["predictions"]["2026-05-22"]["000001"]
    assert all(0.0 <= score <= 1.0 for score in payload["predictions"]["2026-05-22"].values())


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
```

- [ ] **步骤 2：运行测试确认失败**

运行: `python -m pytest tests/test_qlib_service.py::test_generate_predictions_writes_dashboard_cache tests/test_qlib_service.py::test_write_predictions_cache_creates_parent_directory -q`

预期: 失败，并提示 `ModuleNotFoundError: No module named 'data.qlib'`。

- [ ] **步骤 3：编写最小实现**

新建 `data/qlib/__init__.py`：

```python
"""Lightweight Qlib-compatible prediction service package."""
```

新建 `data/qlib/predictor.py`：

```python
"""Local deterministic predictor for the dashboard Qlib cache contract."""
from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from config.settings import DB_PATH, QLIB_PRED_CACHE


METHOD_NAME = "local_momentum_v1"


@dataclass(frozen=True)
class QlibPredictionSummary:
    success: bool
    latest_date: str | None
    total: int
    cache_path: Path
    method: str = METHOD_NAME
    message: str = ""


def _plain_code(code: str) -> str:
    raw = str(code or "").strip()
    if raw[:2].lower() in {"sh", "sz"}:
        raw = raw[2:]
    return raw if len(raw) == 6 and raw.isdigit() else ""


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _fetch_daily_rows(db_path: Path, lookback_days: int, limit: int) -> list[sqlite3.Row]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(
            """WITH latest_dates AS (
                   SELECT DISTINCT date
                   FROM stock_daily
                   ORDER BY date DESC
                   LIMIT ?
               )
               SELECT code, date, open, high, low, close, volume, amount
               FROM stock_daily
               WHERE date IN (SELECT date FROM latest_dates)
               ORDER BY code, date""",
            (max(2, lookback_days),),
        )
        rows = cursor.fetchall()
    finally:
        conn.close()
    return rows[: max(limit * max(2, lookback_days) * 4, limit)]


def _score_series(rows: list[sqlite3.Row]) -> float | None:
    ordered = sorted(rows, key=lambda row: str(row["date"]))
    closes = [_safe_float(row["close"]) for row in ordered]
    closes = [value for value in closes if value is not None and value > 0]
    if len(closes) < 2:
        return None

    first = closes[0]
    last = closes[-1]
    momentum = (last / first) - 1.0 if first else 0.0
    returns = [
        (closes[index] / closes[index - 1]) - 1.0
        for index in range(1, len(closes))
        if closes[index - 1]
    ]
    avg_return = sum(returns) / len(returns) if returns else 0.0
    variance = sum((item - avg_return) ** 2 for item in returns) / len(returns) if returns else 0.0
    volatility = math.sqrt(variance)

    amounts = [_safe_float(row["amount"]) for row in ordered]
    amounts = [value for value in amounts if value is not None and value > 0]
    latest_amount = amounts[-1] if amounts else 0.0
    liquidity = math.log10(latest_amount + 1.0) / 10.0

    raw_score = 0.5 + momentum * 4.0 + avg_return * 6.0 - volatility * 2.0 + liquidity * 0.12
    return max(0.0, min(1.0, raw_score))


def _build_predictions(rows: list[sqlite3.Row], limit: int) -> tuple[str | None, dict[str, float]]:
    if not rows:
        return None, {}

    latest_date = max(str(row["date"]) for row in rows)
    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        code = _plain_code(str(row["code"]))
        if not code:
            continue
        grouped.setdefault(code, []).append(row)

    scored: list[tuple[str, float]] = []
    for code, series in grouped.items():
        if not any(str(row["date"]) == latest_date for row in series):
            continue
        score = _score_series(series)
        if score is None:
            continue
        scored.append((code, round(score, 6)))

    scored.sort(key=lambda item: item[1], reverse=True)
    return latest_date, dict(scored[:limit])


def write_predictions_cache(
    predictions: dict[str, dict[str, float]],
    cache_path: Path = QLIB_PRED_CACHE,
    method: str = METHOD_NAME,
) -> QlibPredictionSummary:
    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    latest_date = max(predictions.keys()) if predictions else None
    latest_predictions = predictions.get(latest_date, {}) if latest_date else {}
    payload = {
        "predictions": predictions,
        "latest_date": latest_date,
        "total": len(latest_predictions),
        "method": method,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return QlibPredictionSummary(
        success=True,
        latest_date=latest_date,
        total=len(latest_predictions),
        cache_path=cache_path,
        method=method,
    )


def generate_predictions(
    db_path: Path = DB_PATH,
    cache_path: Path = QLIB_PRED_CACHE,
    lookback_days: int = 60,
    limit: int = 300,
) -> QlibPredictionSummary:
    db_path = Path(db_path)
    cache_path = Path(cache_path)
    rows = _fetch_daily_rows(db_path=db_path, lookback_days=lookback_days, limit=limit)
    latest_date, latest_predictions = _build_predictions(rows, limit=limit)
    if not latest_predictions:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        return QlibPredictionSummary(
            success=False,
            latest_date=latest_date,
            total=0,
            cache_path=cache_path,
            message=f"no usable stock_daily rows in {db_path}",
        )
    return write_predictions_cache(
        predictions={str(latest_date): latest_predictions},
        cache_path=cache_path,
        method=METHOD_NAME,
    )
```

- [ ] **步骤 4：运行测试确认通过**

运行: `python -m pytest tests/test_qlib_service.py::test_generate_predictions_writes_dashboard_cache tests/test_qlib_service.py::test_write_predictions_cache_creates_parent_directory -q`

预期: `2 passed`。

- [ ] **步骤 5：提交**

```bash
git add data/qlib/__init__.py data/qlib/predictor.py tests/test_qlib_service.py
git commit -m "feat: add local qlib predictor"
```

---

### 任务 2: Qlib 兼容微服务

**文件：**
- 新建: `data/qlib/service.py`
- 修改: `tests/test_qlib_service.py`

- [ ] **步骤 1：编写失败测试**

在 `tests/test_qlib_service.py` 追加以下测试。它们要求 `data.qlib.service` 可导入，服务训练会写缓存，健康检查能报告缓存状态。

```python
from fastapi.testclient import TestClient


def test_qlib_service_train_generates_cache(tmp_path, monkeypatch):
    from data.qlib import service as qlib_service

    db_path = tmp_path / "quant.db"
    cache_path = tmp_path / "predictions_cache.json"
    _seed_daily_db(db_path)
    monkeypatch.setattr(qlib_service, "DB_PATH", db_path)
    monkeypatch.setattr(qlib_service, "QLIB_PRED_CACHE", cache_path)
    qlib_service.TRAIN_STATE.update({"training": False, "last_success": None, "last_error": None, "latest_date": None, "total": 0})

    client = TestClient(qlib_service.app)
    response = client.post("/train")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["training"] is False
    assert payload["latest_date"] == "2026-05-22"
    assert payload["total"] == 2
    assert cache_path.exists()

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
```

- [ ] **步骤 2：运行测试确认失败**

运行: `python -m pytest tests/test_qlib_service.py::test_qlib_service_train_generates_cache tests/test_qlib_service.py::test_qlib_service_health_reports_cache tests/test_qlib_service.py::test_service_module_exposes_cli_main -q`

预期: 失败，并提示 `ImportError` 或 `ModuleNotFoundError: No module named 'data.qlib.service'`。

- [ ] **步骤 3：编写最小实现**

新建 `data/qlib/service.py`：

```python
"""FastAPI microservice for local Qlib-compatible predictions."""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI
from loguru import logger

from config.settings import DB_PATH, QLIB_PRED_CACHE
from data.qlib.predictor import generate_predictions


app = FastAPI(title="Junwei Quant Qlib Service")

TRAIN_STATE: dict[str, Any] = {
    "training": False,
    "last_started": None,
    "last_success": None,
    "last_error": None,
    "latest_date": None,
    "total": 0,
}


def _cache_payload(cache_path: Path = QLIB_PRED_CACHE) -> dict[str, Any]:
    cache_path = Path(cache_path)
    if not cache_path.exists():
        return {}
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"failed to read qlib cache: {exc}")
        return {}


def _cache_status(cache_path: Path = QLIB_PRED_CACHE) -> dict[str, Any]:
    cache_path = Path(cache_path)
    if not cache_path.exists():
        return {
            "success": True,
            "status": "offline",
            "cache_exists": False,
            "latest_date": None,
            "total": 0,
            "cache_age_hours": None,
        }

    payload = _cache_payload(cache_path)
    predictions = payload.get("predictions", payload) if isinstance(payload, dict) else {}
    latest_date = max(predictions.keys()) if isinstance(predictions, dict) and predictions else None
    total = len(predictions.get(latest_date, {})) if latest_date and isinstance(predictions.get(latest_date), dict) else 0
    age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
    if age_hours < 24:
        status = "online"
    elif age_hours < 72:
        status = "stale"
    else:
        status = "offline"
    return {
        "success": True,
        "status": status,
        "cache_exists": True,
        "latest_date": latest_date,
        "total": total,
        "cache_age_hours": round(age_hours, 1),
    }


def train_now() -> dict[str, Any]:
    if TRAIN_STATE["training"]:
        return {"success": False, "training": True, "message": "training already running"}

    TRAIN_STATE.update({
        "training": True,
        "last_started": datetime.now().isoformat(timespec="seconds"),
        "last_error": None,
    })
    try:
        summary = generate_predictions(db_path=DB_PATH, cache_path=QLIB_PRED_CACHE)
        if not summary.success:
            TRAIN_STATE.update({
                "training": False,
                "last_error": summary.message,
                "latest_date": summary.latest_date,
                "total": summary.total,
            })
            return {
                "success": False,
                "training": False,
                "message": summary.message,
                "latest_date": summary.latest_date,
                "total": summary.total,
            }
        TRAIN_STATE.update({
            "training": False,
            "last_success": datetime.now().isoformat(timespec="seconds"),
            "latest_date": summary.latest_date,
            "total": summary.total,
            "last_error": None,
        })
        return {
            "success": True,
            "training": False,
            "latest_date": summary.latest_date,
            "total": summary.total,
            "cache_path": str(summary.cache_path),
            "method": summary.method,
        }
    except Exception as exc:
        TRAIN_STATE.update({
            "training": False,
            "last_error": str(exc),
        })
        logger.exception("qlib training failed")
        return {"success": False, "training": False, "message": str(exc)}


@app.get("/health")
def health() -> dict[str, Any]:
    return _cache_status(QLIB_PRED_CACHE)


@app.post("/train")
def train() -> dict[str, Any]:
    return train_now()


@app.get("/train/status")
def train_status() -> dict[str, Any]:
    return dict(TRAIN_STATE)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run local Qlib-compatible prediction service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--auto-train", action="store_true")
    args = parser.parse_args(argv)

    if args.auto_train:
        result = train_now()
        logger.info(f"qlib auto-train result: {result}")

    uvicorn.run("data.qlib.service:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
```

- [ ] **步骤 4：运行测试确认通过**

运行: `python -m pytest tests/test_qlib_service.py::test_qlib_service_train_generates_cache tests/test_qlib_service.py::test_qlib_service_health_reports_cache tests/test_qlib_service.py::test_service_module_exposes_cli_main -q`

预期: `3 passed`。

- [ ] **步骤 5：提交**

```bash
git add data/qlib/service.py tests/test_qlib_service.py
git commit -m "feat: add qlib prediction service"
```

---

### 任务 3: Dashboard Qlib API 合同增强

**文件：**
- 修改: `dashboard/routers/qlib.py`
- 修改: `tests/test_api_v2_full.py`

- [ ] **步骤 1：编写失败测试**

在 `tests/test_api_v2_full.py` 的 `TestQlib` 类里追加以下测试。测试使用临时缓存，不依赖真实运行的 8002 服务。

```python
    def test_top_predictions_reads_cache_and_enriches_rows(self, client, monkeypatch, tmp_path):
        cache_path = tmp_path / "predictions_cache.json"
        cache_path.write_text(
            '{"predictions":{"2026-05-22":{"600519":0.81,"000001":0.62}}}',
            encoding="utf-8",
        )
        monkeypatch.setattr(qlib_router, "PRED_CACHE_FILE", cache_path)
        monkeypatch.setattr(
            qlib_router,
            "_enrich_with_stock_info",
            lambda codes: {
                "600519": {"name": "贵州茅台", "industry": "白酒", "price": 1688.0},
                "000001": {"name": "平安银行", "industry": "银行", "price": 10.5},
            },
        )

        resp = client.get("/api/qlib/top", params={"top_n": 1})

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        assert payload["date"] == "2026-05-22"
        assert payload["total"] == 2
        assert payload["predictions"][0]["code"] == "600519"
        assert payload["predictions"][0]["name"] == "贵州茅台"
        assert payload["predictions"][0]["score"] == 0.81

    def test_qlib_health_reports_cache_metadata(self, client, monkeypatch, tmp_path):
        cache_path = tmp_path / "predictions_cache.json"
        cache_path.write_text(
            '{"predictions":{"2026-05-22":{"600519":0.81,"000001":0.62}}}',
            encoding="utf-8",
        )
        monkeypatch.setattr(qlib_router, "PRED_CACHE_FILE", cache_path)

        resp = client.get("/api/qlib/health")

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        assert payload["status"] in {"online", "stale", "offline"}
        assert payload["cache_exists"] is True
        assert payload["last_update"] == "2026-05-22"
        assert payload["prediction_total"] == 2
        assert payload["service_url"] == qlib_router.QLIB_SERVICE_URL
```

- [ ] **步骤 2：运行测试确认失败**

运行: `python -m pytest tests/test_api_v2_full.py::TestQlib::test_top_predictions_reads_cache_and_enriches_rows tests/test_api_v2_full.py::TestQlib::test_qlib_health_reports_cache_metadata -q`

预期: 第二个测试失败，提示响应里缺少 `cache_exists`、`prediction_total` 或 `service_url`；第一个测试应通过或暴露缓存读取兼容问题。

- [ ] **步骤 3：编写最小实现**

修改 `dashboard/routers/qlib.py` 的 `qlib_health()`。保留旧字段 `success`、`status`、`last_update`、`cache_age_hours`，新增缓存元数据：

```python
@router.get("/health")
async def qlib_health():
    """Qlib 服务健康检查。"""
    try:
        if not PRED_CACHE_FILE.exists():
            return {
                "success": True,
                "status": "offline",
                "last_update": None,
                "cache_age_hours": None,
                "cache_exists": False,
                "cache_path": str(PRED_CACHE_FILE),
                "prediction_total": 0,
                "service_url": QLIB_SERVICE_URL,
            }

        import time
        mtime = PRED_CACHE_FILE.stat().st_mtime
        age_hours = (time.time() - mtime) / 3600

        latest_date = None
        prediction_total = 0
        try:
            data = json.loads(PRED_CACHE_FILE.read_text(encoding="utf-8"))
            preds = data.get("predictions", data)
            latest_date = max(preds.keys()) if isinstance(preds, dict) and preds else None
            latest_preds = preds.get(latest_date, {}) if latest_date and isinstance(preds, dict) else {}
            prediction_total = len(latest_preds) if isinstance(latest_preds, dict) else 0
        except Exception:
            latest_date = None
            prediction_total = 0

        if age_hours < 24:
            status = "online"
        elif age_hours < 72:
            status = "stale"
        else:
            status = "offline"

        return {
            "success": True,
            "status": status,
            "last_update": latest_date,
            "cache_age_hours": round(age_hours, 1),
            "cache_exists": True,
            "cache_path": str(PRED_CACHE_FILE),
            "prediction_total": prediction_total,
            "service_url": QLIB_SERVICE_URL,
        }
    except Exception as e:
        logger.error(f"Qlib 健康检查失败: {e}")
        return {
            "success": True,
            "status": "offline",
            "last_update": None,
            "cache_age_hours": None,
            "cache_exists": False,
            "cache_path": str(PRED_CACHE_FILE),
            "prediction_total": 0,
            "service_url": QLIB_SERVICE_URL,
        }
```

- [ ] **步骤 4：运行测试确认通过**

运行: `python -m pytest tests/test_api_v2_full.py::TestQlib -q`

预期: `TestQlib` 全部通过。

- [ ] **步骤 5：提交**

```bash
git add dashboard/routers/qlib.py tests/test_api_v2_full.py
git commit -m "feat: expose qlib cache health metadata"
```

---

### 任务 4: 机会池 AI 覆盖回归

**文件：**
- 修改: `tests/test_dashboard.py`
- 可选修改: `dashboard/routers/datahub.py`

- [ ] **步骤 1：编写失败测试**

在 `tests/test_dashboard.py` 中追加一个直接调用 `_score_decision()` 的窄测试。如果现有行为已正确，该测试会直接通过；若后续改动破坏 AI 覆盖，它会回归失败。

```python
def test_decision_score_does_not_flag_ai_uncovered_when_qlib_rank_exists():
    from dashboard.routers.datahub import _score_decision

    decision = _score_decision(
        {
            "peg_next_year": 1.2,
            "growth_next_year_pct": 20,
            "report_count": 3,
        },
        {
            "qlib_rank": 8,
            "qlib_score": 0.76,
            "qlib_diamond": False,
        },
    )

    assert "AI未覆盖" not in decision["risk_tags"]
    assert "AI前10" in decision["reason_tags"]
    assert decision["decision_score"] >= 70
```

- [ ] **步骤 2：运行测试确认结果**

运行: `python -m pytest tests/test_dashboard.py::test_decision_score_does_not_flag_ai_uncovered_when_qlib_rank_exists -q`

预期: 通过。如果失败，说明 `_score_decision()` 的 AI 覆盖判断有 bug。

- [ ] **步骤 3：仅在失败时编写最小实现**

如果步骤 2 失败，修改 `dashboard/routers/datahub.py` 中 `_score_decision()` 的 Qlib 判断，确保只在 `qlib_rank` 缺失或为 0 时加入 `AI未覆盖`：

```python
    if qlib_rank:
        if qlib_rank <= 10:
            score += 18
            reasons.append("AI前10")
        elif qlib_rank <= 50:
            score += 10
            reasons.append("AI候选池")
        elif qlib_rank <= 100:
            score += 5
            reasons.append("AI覆盖")
    else:
        risks.append("AI未覆盖")
```

- [ ] **步骤 4：运行测试确认通过**

运行: `python -m pytest tests/test_dashboard.py::test_decision_score_does_not_flag_ai_uncovered_when_qlib_rank_exists -q`

预期: `1 passed`。

- [ ] **步骤 5：提交**

```bash
git add tests/test_dashboard.py dashboard/routers/datahub.py
git commit -m "test: cover qlib opportunity coverage"
```

---

### 任务 5: 集成验证和本地启动修复

**文件：**
- 修改: `scripts/run_dashboard.py`（仅当 smoke 发现参数或启动错误时）
- 测试: `tests/test_qlib_service.py`, `tests/test_api_v2_full.py`, `tests/test_dashboard.py`

- [ ] **步骤 1：运行单元集成测试**

运行:

```bash
python -m pytest tests/test_qlib_service.py tests/test_api_v2_full.py::TestQlib tests/test_dashboard.py -q
```

预期: 全部通过。

- [ ] **步骤 2：验证模块 CLI 可启动到 health**

用临时端口启动服务，确认 `/health` 可访问，然后停止该进程。PowerShell 命令：

```powershell
$proc = Start-Process -FilePath python -ArgumentList @("-m", "data.qlib.service", "--port", "8313", "--auto-train") -WorkingDirectory "." -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 5
try {
  Invoke-RestMethod -Uri "http://127.0.0.1:8313/health" -TimeoutSec 5 | ConvertTo-Json -Depth 5
} finally {
  Stop-Process -Id $proc.Id -Force
}
```

预期: 返回 JSON，至少包含 `success=true`、`status`、`cache_exists`、`latest_date`、`total`。如果本地数据库没有足够日线，允许 `cache_exists=false` 或 `total=0`，但服务不能因 `ModuleNotFoundError` 崩溃。

- [ ] **步骤 3：处理 8002 端口占用**

运行:

```powershell
Get-NetTCPConnection -LocalPort 8002 -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,State,OwningProcess
```

如果占用进程仍是 `python scripts/run_dashboard.py --host 127.0.0.1 --port 8002 --no-qlib`，先在最终说明里明确：这是旧错误进程，不是 Qlib 服务。不要无提示杀掉用户正在用的进程；如果要完整重启本地 8311，需要先停止该旧 8002 dashboard 再用 `scripts/run_dashboard.py --port 8311` 启动。

- [ ] **步骤 4：可选验证仪表盘代理**

如果 8002 可用，运行:

```powershell
$env:QLIB_SERVICE_URL = "http://127.0.0.1:8313"
python -m pytest tests/test_api_v2_full.py::TestQlib -q
```

预期: `TestQlib` 通过。

- [ ] **步骤 5：提交**

如果本任务改了 `scripts/run_dashboard.py`，提交：

```bash
git add scripts/run_dashboard.py tests/test_qlib_service.py tests/test_api_v2_full.py tests/test_dashboard.py
git commit -m "fix: verify qlib dashboard startup path"
```

如果没有代码改动，不提交。

---

## 自我审查

- 规范覆盖：计划覆盖了 `data.qlib.service` 缺失、预测缓存缺失、dashboard Qlib API 可读缓存、机会池 AI 覆盖和本地启动 smoke。
- 占位符扫描：没有 `TBD`、`TODO`、`implement later` 或未定义函数名；每个代码修改步骤都包含实际代码。
- 类型一致性：`QlibPredictionSummary` 字段在 predictor、service 和测试中一致；缓存合同保持 `predictions -> date -> code -> score`；dashboard 旧字段保持兼容。
- 范围控制：没有引入完整 pyqlib 训练、模型文件或外部网络依赖；runtime `data/qlib/predictions_cache.json` 已被 `.gitignore` 的 `data/qlib/` 覆盖，不应提交。
