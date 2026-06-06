"""Full-market stock_daily synchronization."""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from config.settings import FULL_STOCK_DAILY_SYNC_STATUS
from data.collector.http_client import fetch_json, fetch_json_tencent
from data.providers.astock_data_adapter import normalize_stock_code
from data.storage import DataStorage

EASTMONEY_STOCK_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048,m:0+t:81+s:2052"
EASTMONEY_SNAPSHOT_FIELDS = "f2,f3,f5,f6,f12,f14,f15,f16,f17"


@dataclass(frozen=True)
class FullSyncItem:
    code: str
    success: bool
    rows: int = 0
    written: int = 0
    latest_date: str | None = None
    source: str = ""
    error: str = ""


@dataclass(frozen=True)
class FullSyncSummary:
    success: bool
    target_count: int
    success_count: int
    fail_count: int
    coverage: dict[str, Any]
    started_at: str
    finished_at: str
    duration_sec: float
    items: list[FullSyncItem] = field(default_factory=list)
    snapshot_count: int = 0


def _plain_code(code: object) -> str:
    return normalize_stock_code(str(code or "")) or ""


def _quote_symbol(code: str) -> str:
    plain = _plain_code(code)
    if plain.startswith(("43", "83", "87", "88", "92")):
        return f"bj{plain}"
    if plain.startswith(("6", "9")):
        return f"sh{plain}"
    return f"sz{plain}"


def _safe_float(value: Any) -> float | None:
    if value in (None, "", "-", "--"):
        return None
    try:
        val = float(value)
        return val if val == val else None
    except Exception:
        return None


def _normalize_daily_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if "date" not in out.columns and "datetime" in out.columns:
        out = out.rename(columns={"datetime": "date"})
    for column in ("date", "open", "high", "low", "close", "volume", "amount"):
        if column not in out.columns:
            out[column] = 0
    if "adj_factor" not in out.columns:
        out["adj_factor"] = 1.0
    out["date"] = pd.to_datetime(out["date"])
    return out[["date", "open", "high", "low", "close", "volume", "amount", "adj_factor"]]


def _parse_tencent_quote_fallback(stock_payload: dict[str, Any]) -> dict[str, Any] | None:
    symbol, quote = next(iter((stock_payload.get("qt") or {}).items()), ("", []))
    if not isinstance(quote, list) or len(quote) < 36:
        return None
    raw_time = str(quote[30] or "")
    if len(raw_time) < 8:
        return None
    price = _safe_float(quote[3])
    open_price = _safe_float(quote[5]) or price
    high = _safe_float(quote[33]) or price
    low = _safe_float(quote[34]) or price
    volume = _safe_float(quote[36])
    amount_raw = _safe_float(quote[37])
    amount = amount_raw * 10000 if amount_raw is not None else 0.0
    if price is None:
        return None
    return {
        "date": raw_time[:8],
        "open": open_price,
        "high": high,
        "low": low,
        "close": price,
        "volume": volume or 0.0,
        "amount": amount or 0.0,
        "adj_factor": 1.0,
        "fallback_symbol": symbol,
    }


def fetch_tencent_daily(code: str, count: int = 260) -> pd.DataFrame:
    """Fetch recent qfq daily bars from Tencent."""
    plain = _plain_code(code)
    if not plain:
        return pd.DataFrame()
    symbol = _quote_symbol(plain)
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,{int(count)},qfq"
    payload = fetch_json_tencent(url, timeout=10)
    stock_payload = (payload.get("data") or {}).get(symbol, {}) or {}
    rows = stock_payload.get("qfqday") or stock_payload.get("day") or []
    parsed: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 6:
            continue
        parsed.append(
            {
                "date": row[0],
                "open": _safe_float(row[1]),
                "close": _safe_float(row[2]),
                "high": _safe_float(row[3]),
                "low": _safe_float(row[4]),
                "volume": _safe_float(row[5]),
                "amount": 0.0,
                "adj_factor": 1.0,
            }
        )
    if not parsed:
        fallback = _parse_tencent_quote_fallback(stock_payload)
        if fallback:
            parsed.append(fallback)
    return _normalize_daily_frame(pd.DataFrame(parsed))


def fetch_full_market_snapshot(page_size: int = 100) -> dict[str, dict[str, Any]]:
    """Fetch latest full-market quote snapshot keyed by plain code."""
    result: dict[str, dict[str, Any]] = {}
    page = 1
    total = None
    page_size = max(1, min(int(page_size), 100))
    while True:
        url = (
            "https://push2delay.eastmoney.com/api/qt/clist/get"
            f"?pn={page}&pz={int(page_size)}&po=1&np=1&fltt=2&invt=2"
            f"&fid=f3&fs={EASTMONEY_STOCK_FS}&fields={EASTMONEY_SNAPSHOT_FIELDS}"
        )
        payload = fetch_json(url, timeout=12)
        data = payload.get("data") or {}
        rows = data.get("diff") or []
        total = int(data.get("total") or total or 0)
        if not rows:
            break
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = _plain_code(row.get("f12"))
            if not code:
                continue
            result[code] = {
                "code": code,
                "name": str(row.get("f14") or ""),
                "open": _safe_float(row.get("f17")),
                "high": _safe_float(row.get("f15")),
                "low": _safe_float(row.get("f16")),
                "close": _safe_float(row.get("f2")),
                "volume": _safe_float(row.get("f5")),
                "amount": _safe_float(row.get("f6")),
            }
        if len(result) >= total or len(rows) < page_size:
            break
        page += 1
    return result


def _merge_snapshot(df: pd.DataFrame, snapshot: dict[str, Any] | None) -> pd.DataFrame:
    if df.empty or not snapshot:
        return df
    out = df.copy()
    last_idx = out["date"].idxmax()
    for field in ("open", "high", "low", "close", "volume", "amount"):
        value = snapshot.get(field)
        if value is None:
            continue
        out.loc[last_idx, field] = value
    return out


def _write_status(
    status_path: Path,
    *,
    started_at: datetime,
    target_count: int,
    items: list[FullSyncItem],
    coverage: dict[str, Any],
    snapshot_count: int,
    finished: bool = False,
) -> None:
    success_count = sum(1 for item in items if item.success)
    fail_count = sum(1 for item in items if not item.success)
    payload = {
        "source": "tencent_qfq_daily+eastmoney_full_market_snapshot",
        "finished": finished,
        "success": finished and fail_count == 0 and success_count == target_count,
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": datetime.now().isoformat(timespec="seconds") if finished else None,
        "duration_sec": round(time.perf_counter() - _START_PERF, 3),
        "target_count": target_count,
        "processed_count": len(items),
        "success_count": success_count,
        "fail_count": fail_count,
        "snapshot_count": snapshot_count,
        "coverage": coverage,
        "items": [
            {
                "code": item.code,
                "success": item.success,
                "rows": item.rows,
                "written": item.written,
                "latest_date": item.latest_date,
                "source": item.source,
                "error": item.error,
            }
            for item in items
        ],
    }
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


_START_PERF = time.perf_counter()


def sync_full_stock_daily(
    *,
    codes: Iterable[str] | None = None,
    count: int = 260,
    limit: int = 0,
    skip_existing: bool = False,
    update_existing: bool = True,
    status_path: Path | None = None,
    storage: DataStorage | None = None,
    progress_every: int = 25,
    sleep_sec: float = 0.0,
    workers: int = 1,
    fetch_daily_fn=fetch_tencent_daily,
    fetch_snapshot_fn=fetch_full_market_snapshot,
) -> FullSyncSummary:
    """Synchronize stock_daily for the full local stock_info universe."""
    started_at = datetime.now()
    start_perf = time.perf_counter()
    global _START_PERF
    _START_PERF = start_perf

    storage = storage or DataStorage()
    status_file = Path(status_path) if status_path is not None else FULL_STOCK_DAILY_SYNC_STATUS
    target_codes = [_plain_code(code) for code in (codes if codes is not None else storage.get_all_stock_codes())]
    target_codes = [code for code in target_codes if code]
    if limit and limit > 0:
        target_codes = target_codes[: int(limit)]

    snapshot: dict[str, dict[str, Any]] = {}
    snapshot_error = ""
    try:
        snapshot = fetch_snapshot_fn()
    except Exception as exc:
        snapshot_error = str(exc)

    items: list[FullSyncItem] = []
    if not target_codes:
        coverage = storage.get_stock_daily_coverage()
        _write_status(
            status_file,
            started_at=started_at,
            target_count=0,
            items=items,
            coverage=coverage,
            snapshot_count=len(snapshot),
            finished=True,
        )
        return FullSyncSummary(
            success=False,
            target_count=0,
            success_count=0,
            fail_count=0,
            coverage=coverage,
            started_at=started_at.isoformat(timespec="seconds"),
            finished_at=datetime.now().isoformat(timespec="seconds"),
            duration_sec=round(time.perf_counter() - start_perf, 3),
            items=items,
            snapshot_count=len(snapshot),
        )

    def _save_fetched_item(code: str, df: pd.DataFrame | None, error: str = "") -> FullSyncItem:
        if error:
            return FullSyncItem(code=code, success=False, error=error)
        try:
            df = _merge_snapshot(df if df is not None else pd.DataFrame(), snapshot.get(code))
            if df.empty:
                item_error = "empty daily frame"
                if snapshot_error:
                    item_error = f"{item_error}; snapshot_error={snapshot_error}"
                return FullSyncItem(code=code, success=False, error=item_error)
            normalized = _normalize_daily_frame(df)
            written = int(storage.save_stock_daily(code, normalized, update_existing=update_existing))
            latest_date = str(pd.Timestamp(normalized["date"].max()).date())
            return FullSyncItem(
                code=code,
                success=True,
                rows=len(normalized),
                written=written,
                latest_date=latest_date,
                source="tencent_qfq_daily+eastmoney_snapshot",
            )
        except Exception as exc:
            return FullSyncItem(code=code, success=False, error=str(exc))

    def _record_progress(processed: int, finished: bool = False) -> None:
        if progress_every and (
            processed == 1 or processed % progress_every == 0 or processed == len(target_codes) or finished
        ):
            _write_status(
                status_file,
                started_at=started_at,
                target_count=len(target_codes),
                items=items,
                coverage=storage.get_stock_daily_coverage(),
                snapshot_count=len(snapshot),
                finished=finished,
            )

    work_codes: list[str] = []
    for code in target_codes:
        if skip_existing and storage.get_latest_date(code):
            items.append(FullSyncItem(code=code, success=True, source="skipped_existing"))
            _record_progress(len(items))
        else:
            work_codes.append(code)

    if workers <= 1:
        for code in work_codes:
            try:
                df = fetch_daily_fn(code, count=count)
                item = _save_fetched_item(code, df)
            except Exception as exc:
                item = _save_fetched_item(code, None, str(exc))
            items.append(item)

            if sleep_sec > 0:
                time.sleep(sleep_sec)
            _record_progress(len(items))
    else:
        max_workers = max(1, min(int(workers), 16))

        def _fetch_one(code: str) -> tuple[str, pd.DataFrame | None, str]:
            try:
                return code, fetch_daily_fn(code, count=count), ""
            except Exception as exc:
                return code, None, str(exc)

        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="full-daily-sync") as pool:
            futures = {pool.submit(_fetch_one, code): code for code in work_codes}
            for future in as_completed(futures):
                code, df, error = future.result()
                items.append(_save_fetched_item(code, df, error))
                _record_progress(len(items))
                if sleep_sec > 0:
                    time.sleep(sleep_sec)

    coverage = storage.get_stock_daily_coverage()
    success_count = sum(1 for item in items if item.success)
    fail_count = len(items) - success_count
    finished_at = datetime.now().isoformat(timespec="seconds")
    _write_status(
        status_file,
        started_at=started_at,
        target_count=len(target_codes),
        items=items,
        coverage=coverage,
        snapshot_count=len(snapshot),
        finished=True,
    )
    return FullSyncSummary(
        success=fail_count == 0 and success_count == len(target_codes),
        target_count=len(target_codes),
        success_count=success_count,
        fail_count=fail_count,
        coverage=coverage,
        started_at=started_at.isoformat(timespec="seconds"),
        finished_at=finished_at,
        duration_sec=round(time.perf_counter() - start_perf, 3),
        items=items,
        snapshot_count=len(snapshot),
    )
