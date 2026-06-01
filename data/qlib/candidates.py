"""Shared stock candidate pools for research and Qlib coverage."""
from __future__ import annotations

from typing import Iterable

from data.providers.astock_data_adapter import normalize_stock_code
from data.storage.storage import DataStorage


REPRESENTATIVE_CODES = [
    "600519",
    "000001",
    "300750",
    "000858",
    "601318",
    "000333",
    "600036",
    "002594",
    "601899",
    "600276",
    "002475",
    "600900",
]

QLIB_DAILY_SUPPORTED_PREFIXES = ("000", "001", "002", "003", "300", "301", "600", "601", "603", "605", "688")


def plain_code(code: object) -> str:
    return normalize_stock_code(str(code or "")) or ""


def dedupe_codes(codes: Iterable[object]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for code in codes:
        normalized = plain_code(code)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def is_supported_daily_code(code: object) -> bool:
    normalized = plain_code(code)
    return bool(normalized and normalized.startswith(QLIB_DAILY_SUPPORTED_PREFIXES))


def fallback_seed_codes(storage: DataStorage, limit: int) -> list[str]:
    stock_list = storage.get_stock_list()
    if not stock_list.empty:
        available = {plain_code(row.get("code")) for _, row in stock_list.iterrows()}
        seeded = [code for code in REPRESENTATIVE_CODES if code in available and is_supported_daily_code(code)]
        if len(seeded) >= min(limit, 5):
            return seeded[:limit]
        for _, row in stock_list.head(max(limit * 4, 20)).iterrows():
            code = plain_code(row.get("code"))
            if code and is_supported_daily_code(code) and code not in seeded:
                seeded.append(code)
            if len(seeded) >= limit:
                break
        return seeded[:limit]

    return REPRESENTATIVE_CODES[:limit]


def build_default_coverage_codes(storage: DataStorage, limit: int = 80) -> list[str]:
    watchlist_codes: list[str] = []
    try:
        for _, codes in storage.get_all_watchlist_codes():
            watchlist_codes.extend(codes)
    except Exception:
        watchlist_codes = []

    fallback_codes = fallback_seed_codes(storage, limit)
    return [code for code in dedupe_codes([*REPRESENTATIVE_CODES, *watchlist_codes, *fallback_codes]) if is_supported_daily_code(code)][:limit]
