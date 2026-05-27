"""Daily bar synchronization for local Qlib coverage."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Callable, Iterable

import pandas as pd

from data.providers.astock_data_adapter import AStockDataAdapter
from data.qlib.candidates import build_default_coverage_codes, dedupe_codes
from data.qlib.predictor import QlibPredictionSummary, generate_predictions
from data.storage import DataStorage


@dataclass(frozen=True)
class SyncItem:
    code: str
    success: bool
    rows: int = 0
    written: int = 0
    latest_date: str | None = None
    error: str = ""


@dataclass(frozen=True)
class SyncSummary:
    success: bool
    success_count: int
    fail_count: int
    items: list[SyncItem] = field(default_factory=list)
    prediction_success: bool | None = None
    prediction_latest_date: str | None = None
    prediction_total: int | None = None
    prediction_message: str = ""


def normalize_daily_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()
    if "date" not in out.columns and "datetime" in out.columns:
        out = out.rename(columns={"datetime": "date"})
    if "vol" in out.columns and "volume" not in out.columns:
        out["volume"] = out["vol"]
    for column in ("date", "open", "high", "low", "close", "volume", "amount"):
        if column not in out.columns:
            out[column] = 0
    if "adj_factor" not in out.columns:
        out["adj_factor"] = 1.0

    out["date"] = pd.to_datetime(out["date"])
    return out[["date", "open", "high", "low", "close", "volume", "amount", "adj_factor"]]


async def _fetch_kline(adapter: AStockDataAdapter, code: str, count: int) -> pd.DataFrame:
    return await adapter.get_kline(code, frequency=9, start=0, offset=count)


def sync_qlib_daily(
    codes: Iterable[str] | None = None,
    count: int = 260,
    storage: DataStorage | None = None,
    adapter: AStockDataAdapter | None = None,
    generate_predictions_fn: Callable[[], QlibPredictionSummary] | None = None,
    generate_predictions_cache: bool = False,
    min_success: int = 2,
    limit: int = 80,
) -> SyncSummary:
    storage = storage or DataStorage()
    target_codes = dedupe_codes(codes) if codes is not None else build_default_coverage_codes(storage, limit=limit)
    adapter = adapter or AStockDataAdapter()
    prediction_fn = generate_predictions_fn or generate_predictions

    items: list[SyncItem] = []
    for code in target_codes:
        try:
            raw_df = asyncio.run(_fetch_kline(adapter, code, count))
            df = normalize_daily_frame(raw_df)
            if df.empty:
                items.append(SyncItem(code=code, success=False, error="empty kline"))
                continue
            written = int(storage.save_stock_daily(code, df))
            latest_date = str(pd.Timestamp(df["date"].max()).date())
            items.append(
                SyncItem(
                    code=code,
                    success=True,
                    rows=len(df),
                    written=written,
                    latest_date=latest_date,
                )
            )
        except Exception as exc:
            items.append(SyncItem(code=code, success=False, error=str(exc)))

    success_count = sum(1 for item in items if item.success)
    fail_count = len(items) - success_count
    prediction_success: bool | None = None
    prediction_latest_date: str | None = None
    prediction_total: int | None = None
    prediction_message = ""

    if generate_predictions_cache and success_count >= min_success:
        prediction = prediction_fn()
        prediction_success = bool(prediction.success)
        prediction_latest_date = prediction.latest_date
        prediction_total = prediction.total
        prediction_message = prediction.message

    return SyncSummary(
        success=fail_count == 0 and success_count >= min_success,
        success_count=success_count,
        fail_count=fail_count,
        items=items,
        prediction_success=prediction_success,
        prediction_latest_date=prediction_latest_date,
        prediction_total=prediction_total,
        prediction_message=prediction_message,
    )
