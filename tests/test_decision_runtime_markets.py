from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest

import decision.runtime as runtime_module
from decision.runtime import DecisionRuntime


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


class _Store:
    def __init__(self, market: str) -> None:
        self.market = market
        self.version = {
            "id": "version-1",
            "config": {
                "strategies": [
                    {"strategy_name": "momentum", "enabled": True, "weight": 1},
                ]
            },
        }
        self.snapshot_args: tuple[str, str] | None = None
        self.snapshot: dict[str, Any] | None = None

    def get_portfolio(self, _workspace_id: str, _portfolio_id: str) -> dict[str, Any]:
        return {"id": "portfolio-1", "market": self.market}

    def get_current_version(self, _workspace_id: str, _portfolio_id: str) -> dict[str, Any]:
        return self.version

    def create_version(self, _workspace_id: str, _portfolio_id: str, _config: dict[str, Any]) -> dict[str, Any]:
        return self.version

    def list_members(self, _workspace_id: str, _portfolio_id: str) -> list[dict[str, Any]]:
        return [{"id": "membership-1", "symbol": "600519", "name": "测试标的"}]

    def create_snapshot(
        self,
        _workspace_id: str,
        _version_id: str,
        payload: dict[str, Any],
        source: str,
        quality_status: str,
    ) -> dict[str, Any]:
        self.snapshot_args = source, quality_status
        self.snapshot = {
            "id": "snapshot-1",
            "payload": payload,
            "quality_status": quality_status,
            "source": source,
        }
        return self.snapshot


class _Storage:
    def __init__(self, frame: _Frame | None = None) -> None:
        self.frame = frame or _Frame([])
        self.calls = 0

    def get_stock_daily(self, _symbol: str) -> _Frame:
        self.calls += 1
        return self.frame


def _bars(count: int = 30) -> _Frame:
    start = date.today() - timedelta(days=count - 1)
    return _Frame(
        [
            {
                "date": start + timedelta(days=index),
                "open": 10.0,
                "high": 11.0,
                "low": 9.0,
                "close": 10.5,
                "volume": 1000.0,
                "amount": 10_500.0,
            }
            for index in range(count)
        ]
    )


def test_non_cn_snapshot_is_fail_closed_without_consuming_a_share_storage() -> None:
    store = _Store("HK")
    storage = _Storage()
    runtime = DecisionRuntime(store, storage)

    _portfolio, _version, snapshot = runtime.build_snapshot("workspace-1", "portfolio-1")

    assert storage.calls == 0
    assert store.snapshot_args == ("provider_not_connected", "market_data_unavailable")
    assert snapshot["quality_status"] == "market_data_unavailable"
    payload = snapshot["payload"]
    assert payload["provider_status"] == "provider_not_connected"
    assert payload["market_data_status"] == "market_data_unavailable"
    assert payload["fallback_reason"] == "market_data_unavailable"
    assert payload["field_sources"] == {}
    assert payload["coverage_pct"] == 0.0
    assert payload["members"][0]["bars"] == []
    assert payload["members"][0]["quality_status"] == "invalid"


def test_non_cn_snapshot_does_not_parse_cn_only_stale_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _Store("JP")
    storage = _Storage()
    runtime = DecisionRuntime(store, storage)
    monkeypatch.setenv("DECISION_DAILY_STALE_DAYS", "not-an-integer")

    _portfolio, _version, snapshot = runtime.build_snapshot("workspace-1", "portfolio-1")

    assert storage.calls == 0
    assert snapshot["quality_status"] == "market_data_unavailable"


def test_non_cn_validation_is_fail_closed_without_storage_or_walk_forward(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _Store("US")
    storage = _Storage()
    runtime = DecisionRuntime(store, storage)

    def fail_validation(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("non-CN validation must not run on A-share history")

    monkeypatch.setattr(runtime_module, "walk_forward_validate", fail_validation)

    result = runtime.validate("workspace-1", "portfolio-1")

    assert storage.calls == 0
    assert result["passed"] is False
    assert result["quality_status"] == "market_data_unavailable"
    assert result["provider_status"] == "provider_not_connected"
    assert result["market_data_status"] == "market_data_unavailable"
    assert {"provider_not_connected", "market_data_unavailable"}.issubset(result["reasons"])
    assert result["benchmark_history_available"] is False


def test_cn_snapshot_keeps_using_local_daily_storage() -> None:
    store = _Store("CN")
    storage = _Storage(_bars())
    runtime = DecisionRuntime(store, storage)

    _portfolio, _version, snapshot = runtime.build_snapshot("workspace-1", "portfolio-1")

    assert storage.calls == 1
    assert snapshot["source"] == "local_quant_db"
    assert snapshot["quality_status"] == "ok"
    payload = snapshot["payload"]
    assert payload["provider"] == "local_quant_db"
    assert payload["provider_status"] == "legacy_manual"
    assert payload["members"][0]["coverage"] == 30
    evidence = payload["provider_evidence"]
    assert evidence["provider"] == "local_quant_db"
    assert evidence["request_hash"]
    assert evidence["response_hash"]
    assert evidence["normalized_sequence_hash"]
    assert evidence["collection_watermark"] == payload["captured_at"]
    assert evidence["cache_age_status"] == "not_reported_by_legacy_store"
    assert payload["provider_health"]["local_quant_db"]["request_hash"] == evidence["request_hash"]
