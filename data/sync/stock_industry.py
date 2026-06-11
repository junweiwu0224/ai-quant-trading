"""Synchronize missing stock_info industry fields."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

from data.providers.astock_data_adapter import fetch_industry_batch
from data.storage.storage import DataStorage, _normalize_storage_code


@dataclass(frozen=True)
class StockIndustrySyncSummary:
    target_count: int
    fetched_count: int
    filled_count: int
    updated_count: int
    dry_run: bool
    items: list[dict[str, str]] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.filled_count == self.target_count


def _plain_code(code: str) -> str:
    _, plain = _normalize_storage_code(str(code or "").strip())
    return plain or ""


def _chunked(items: list[str], size: int) -> Iterable[list[str]]:
    size = max(1, int(size or 1))
    for idx in range(0, len(items), size):
        yield items[idx : idx + size]


def _missing_industry_codes(storage: DataStorage, codes: Iterable[str] | None) -> list[str]:
    requested = [_plain_code(code) for code in (codes or [])]
    requested_set = {code for code in requested if code}
    stock_list = storage.get_stock_list()
    if stock_list.empty:
        return []

    result: list[str] = []
    seen: set[str] = set()
    for _, row in stock_list.iterrows():
        code = _plain_code(str(row.get("code") or ""))
        if not code or code in seen:
            continue
        if requested_set and code not in requested_set:
            continue
        industry = str(row.get("industry") or "").strip()
        if industry:
            continue
        seen.add(code)
        result.append(code)
    return result


def sync_stock_industries(
    *,
    storage: DataStorage | None = None,
    codes: Iterable[str] | None = None,
    batch_size: int = 80,
    dry_run: bool = False,
    fetch_industry_fn: Callable[[list[str]], dict[str, dict[str, str]]] = fetch_industry_batch,
) -> StockIndustrySyncSummary:
    """Fill missing local stock industries from a batch industry provider."""
    storage = storage or DataStorage()
    target_codes = _missing_industry_codes(storage, codes)
    fetched: dict[str, dict[str, str]] = {}
    for batch in _chunked(target_codes, batch_size):
        fetched.update(fetch_industry_fn(batch) or {})

    industry_map: dict[str, str] = {}
    items: list[dict[str, str]] = []
    for code in target_codes:
        info = fetched.get(code) or {}
        industry = str(info.get("industry") or "").strip()
        sector = str(info.get("sector") or "").strip()
        concepts = str(info.get("concepts") or "").strip()
        status = "filled" if industry else "missing"
        if industry:
            industry_map[code] = industry
        items.append(
            {
                "code": code,
                "industry": industry,
                "sector": sector,
                "concepts": concepts,
                "status": status,
            }
        )

    updated_count = 0
    if industry_map and not dry_run:
        updated_count = storage.update_stock_industry(industry_map)

    return StockIndustrySyncSummary(
        target_count=len(target_codes),
        fetched_count=len(fetched),
        filled_count=len(industry_map),
        updated_count=updated_count,
        dry_run=dry_run,
        items=items,
    )
