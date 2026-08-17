from __future__ import annotations

import asyncio
from pathlib import Path

import pandas as pd

from dashboard.routers import decisions


ACCOUNT = {"workspace": {"id": "research-fixture", "settings": {}}}


class _Storage:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame

    def get_stock_daily(self, _symbol: str) -> pd.DataFrame:
        return self.frame


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount"])


def test_research_prefers_local_stock_daily_and_marks_it_authoritative(monkeypatch) -> None:
    frame = pd.DataFrame(
        [
            {"date": "2026-08-15", "open": 100, "high": 103, "low": 99, "close": 102, "volume": 1000, "amount": 100000},
        ]
    )
    monkeypatch.setattr(decisions, "research_storage", _Storage(frame))
    monkeypatch.setattr(decisions, "fetch_kline", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("local data must win")))

    payload = asyncio.run(decisions.research("CN", "600519", ACCOUNT))

    assert payload["status"] == "ok"
    assert payload["source"] == "local_stock_daily"
    assert payload["authoritative"] is True
    assert payload["data_quality"]["manual_research_only"] is False
    assert payload["bars"][0]["amount"] == 100000


def test_research_external_fallback_is_degraded_and_manual_only(monkeypatch) -> None:
    monkeypatch.setattr(decisions, "research_storage", _Storage(_empty_frame()))
    monkeypatch.setattr(
        decisions,
        "fetch_kline",
        lambda *args, **kwargs: {"name": "fixture", "klines_raw": [["2026-08-15", "100", "102", "103", "99", "1000", "100000"]]},
    )

    payload = asyncio.run(decisions.research("CN", "600519", ACCOUNT))

    assert payload["status"] == "degraded"
    assert payload["source"] == "external_kline_fallback"
    assert payload["authoritative"] is False
    assert payload["data_quality"]["status"] == "partial"
    assert payload["data_quality"]["manual_research_only"] is True
    assert "manual_research_only" in payload["fallback_reason"]


def test_research_without_any_source_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(decisions, "research_storage", _Storage(_empty_frame()))
    monkeypatch.setattr(decisions, "fetch_kline", lambda *args, **kwargs: None)

    payload = asyncio.run(decisions.research("CN", "600519", ACCOUNT))

    assert payload["status"] == "no_data"
    assert payload["bars"] == []
    assert payload["authoritative"] is False
    assert payload["data_quality"]["status"] == "unavailable"


def test_non_cn_research_does_not_call_a_share_fallback(monkeypatch) -> None:
    monkeypatch.setattr(decisions, "fetch_kline", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("non-CN must not call A-share fallback")))

    payload = asyncio.run(decisions.research("HK", "00700", ACCOUNT))

    assert payload["status"] == "provider_not_connected"
    assert payload["bars"] == []
    assert payload["authoritative"] is False


def test_decision_status_separates_worker_process_and_workspace_automation(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(decisions, "DB_DIR", tmp_path)
    account = {"workspace": {"id": "research-fixture", "settings": {"decision_worker_enabled": False, "decision_auto_push_enabled": False}}}

    payload = asyncio.run(decisions.status(account))

    assert payload["worker_enabled"] is False
    assert payload["worker_automation_enabled"] is False
    assert payload["worker_process_ready"] is False
    assert payload["auto_push_enabled"] is False
