from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from decision.runtime import DecisionRuntime
from decision.store import DecisionStore


class _Frame:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    @property
    def empty(self) -> bool:
        return not self.rows

    def tail(self, count: int) -> "_Frame":
        return _Frame(self.rows[-count:])

    def iterrows(self):
        return enumerate(self.rows)


class _Storage:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def get_stock_daily(self, _symbol: str) -> _Frame:
        return _Frame(self.rows)


def _rows(count: int = 30) -> list[dict[str, Any]]:
    start = date(2026, 7, 1)
    return [
        {
            "date": start + timedelta(days=index),
            "open": 10.0,
            "high": 11.0,
            "low": 9.0,
            "close": 10.5,
            "volume": 1000.0,
            "amount": 10500.0,
        }
        for index in range(count)
    ]


def test_daily_snapshot_provider_evidence_is_stable_and_replayable(tmp_path: Path) -> None:
    store = DecisionStore(tmp_path / "decisions.db")
    portfolio = store.create_portfolio("workspace-1", "CN", "证据组合")
    version = store.create_version(
        "workspace-1",
        portfolio["id"],
        {"strategies": [{"strategy_name": "momentum", "enabled": True, "weight": 1}]},
    )
    store.add_member("workspace-1", portfolio["id"], "600519")
    runtime = DecisionRuntime(store, _Storage(_rows()))

    _portfolio, _version, first = runtime.build_snapshot("workspace-1", portfolio["id"])
    _portfolio, _version, second = runtime.build_snapshot("workspace-1", portfolio["id"])

    evidence = first["payload"]["provider_evidence"]
    assert first["payload_hash"] == second["payload_hash"]
    assert first["id"] == second["id"]
    assert evidence["request_hash"]
    assert evidence["response_hash"]
    assert evidence["normalized_sequence_hash"]
    assert evidence["collection_watermark"] == first["payload"]["captured_at"]
    assert evidence["cache_age_seconds"] is None
    assert evidence["cache_age_status"] == "not_reported_by_legacy_store"
    assert evidence["replayable_copy"] is True
    assert first["payload"]["provider_health"]["local_quant_db"]["response_hash"] == evidence["response_hash"]
