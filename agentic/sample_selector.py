from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

from config.settings import DB_PATH
from utils.db import get_connection


@dataclass(frozen=True)
class BacktestSample:
    codes: list[str]
    start_date: str
    end_date: str
    trading_days: int
    source: str = "local_stock_daily"

    def to_dict(self) -> dict:
        return asdict(self)


class BacktestSampleSelector:
    def __init__(self, db_path: str | Path = DB_PATH):
        self.db_path = Path(db_path)

    def select(self, min_days: int = 60, max_codes: int = 5) -> BacktestSample:
        min_days = max(1, int(min_days))
        max_codes = max(1, int(max_codes))
        coverage = self._load_coverage(min_days)
        if not coverage:
            raise ValueError("no local stock_daily coverage with enough history for agentic backtest")

        candidates = sorted(coverage, key=lambda item: (item["max_date"], item["count"], item["code"]), reverse=True)
        selected = candidates[:max_codes]
        selected, trading_days, common_start, common_end = self._find_common_window(selected, min_days)
        if not selected:
            raise ValueError("no local stock_daily coverage with enough overlapping history for agentic backtest")

        return BacktestSample(
            codes=sorted(item["code"] for item in selected),
            start_date=common_start,
            end_date=common_end,
            trading_days=trading_days,
        )

    def _find_common_window(self, selected: list[dict], min_days: int) -> tuple[list[dict], int, str, str]:
        while selected:
            common_start = max(item["min_date"] for item in selected)
            common_end = min(item["max_date"] for item in selected)
            codes = [item["code"] for item in selected]
            trading_days = self._count_common_trading_days(codes, common_start, common_end)
            if trading_days >= min_days:
                return selected, trading_days, common_start, common_end
            selected = selected[:-1]
        return [], 0, "", ""

    def _load_coverage(self, min_days: int) -> list[dict]:
        try:
            with get_connection(self.db_path, readonly=True) as conn:
                rows = conn.execute(
                    """
                    SELECT
                        CASE
                            WHEN lower(substr(code, 1, 2)) IN ('sh', 'sz') THEN substr(code, 3, 6)
                            ELSE code
                        END AS plain_code,
                        COUNT(DISTINCT date) AS count,
                        MIN(date) AS min_date,
                        MAX(date) AS max_date
                    FROM stock_daily
                    WHERE code IS NOT NULL AND date IS NOT NULL
                    GROUP BY plain_code
                    HAVING COUNT(DISTINCT date) >= ?
                    """,
                    (min_days,),
                ).fetchall()
        except sqlite3.Error as exc:
            raise ValueError("no local stock_daily coverage available for agentic backtest") from exc

        coverage: list[dict] = []
        for row in rows:
            code = _normalize_plain_code(row["plain_code"])
            if not code:
                continue
            coverage.append(
                {
                    "code": code,
                    "count": int(row["count"]),
                    "min_date": str(row["min_date"]),
                    "max_date": str(row["max_date"]),
                }
            )
        return coverage

    def _count_common_trading_days(self, codes: list[str], start_date: str, end_date: str) -> int:
        if not codes:
            return 0
        storage_codes = [_to_storage_code(code) for code in codes]
        all_codes = storage_codes + list(codes)
        code_placeholders = ",".join("?" for _ in all_codes)
        plain_placeholders = ",".join("?" for _ in codes)
        with get_connection(self.db_path, readonly=True) as conn:
            rows = conn.execute(
                f"""
                WITH normalized AS (
                    SELECT
                        CASE
                            WHEN lower(substr(code, 1, 2)) IN ('sh', 'sz') THEN substr(code, 3, 6)
                            ELSE code
                        END AS plain_code,
                        date
                    FROM stock_daily
                    WHERE code IN ({code_placeholders})
                      AND date >= ?
                      AND date <= ?
                    GROUP BY plain_code, date
                )
                SELECT date
                FROM normalized
                WHERE plain_code IN ({plain_placeholders})
                GROUP BY date
                HAVING COUNT(DISTINCT plain_code) = ?
                """,
                (*all_codes, start_date, end_date, *codes, len(codes)),
            ).fetchall()
        return len(rows)


def _normalize_plain_code(code: str) -> str:
    raw = str(code or "").strip()
    if raw[:2].lower() in {"sh", "sz"}:
        raw = raw[2:]
    if len(raw) == 6 and raw.isdigit():
        return raw
    return ""


def _to_storage_code(code: str) -> str:
    plain = _normalize_plain_code(code)
    if plain.startswith("6"):
        return f"sh{plain}"
    if plain.startswith(("0", "3", "9")):
        return f"sz{plain}"
    return plain
