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
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"failed to read qlib cache: {exc}")
        return {}
    return payload if isinstance(payload, dict) else {}


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
    predictions = payload.get("predictions", payload)
    latest_date = max(predictions.keys()) if isinstance(predictions, dict) and predictions else None
    latest_predictions = (
        predictions.get(latest_date, {})
        if latest_date and isinstance(predictions, dict)
        else {}
    )
    total = len(latest_predictions) if isinstance(latest_predictions, dict) else 0
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
        return {
            "success": False,
            "training": True,
            "message": "training already running",
        }

    TRAIN_STATE.update(
        {
            "training": True,
            "last_started": datetime.now().isoformat(timespec="seconds"),
            "last_error": None,
        }
    )
    try:
        summary = generate_predictions(db_path=DB_PATH, cache_path=QLIB_PRED_CACHE)
        if not summary.success:
            TRAIN_STATE.update(
                {
                    "training": False,
                    "last_error": summary.message,
                    "latest_date": summary.latest_date,
                    "total": summary.total,
                }
            )
            return {
                "success": False,
                "training": False,
                "message": summary.message,
                "latest_date": summary.latest_date,
                "total": summary.total,
            }

        TRAIN_STATE.update(
            {
                "training": False,
                "last_success": datetime.now().isoformat(timespec="seconds"),
                "last_error": None,
                "latest_date": summary.latest_date,
                "total": summary.total,
            }
        )
        return {
            "success": True,
            "training": False,
            "latest_date": summary.latest_date,
            "total": summary.total,
            "cache_path": str(summary.cache_path),
            "method": summary.method,
        }
    except Exception as exc:
        TRAIN_STATE.update(
            {
                "training": False,
                "last_error": str(exc),
            }
        )
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
    parser = argparse.ArgumentParser(
        description="Run local Qlib-compatible prediction service"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--auto-train", action="store_true")
    args = parser.parse_args(argv)

    if args.auto_train:
        result = train_now()
        logger.info(f"qlib auto-train result: {result}")

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
