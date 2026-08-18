from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from dashboard.routers import llm


def test_non_cn_reports_fail_closed_without_calling_cn_provider(monkeypatch) -> None:
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("CN report provider must not be called for non-CN markets")

    monkeypatch.setattr("data.collector.http_client.fetch_json", fail_if_called)

    payload = asyncio.run(llm.get_stock_reports("AAPL", market="US"))

    assert payload["success"] is False
    assert payload["market"] == "US"
    assert payload["reports"] == []
    assert payload["items"] == []
    assert payload["data_state"] == "manual_research_only"


def test_cn_reports_expose_legacy_and_shared_items_fields(monkeypatch) -> None:
    monkeypatch.setattr(
        "data.collector.http_client.fetch_json",
        lambda *_args, **_kwargs: {
            "data": [{
                "title": "Fixture report",
                "orgSName": "Fixture Research",
                "publishDate": "2026-08-18 00:00:00",
                "encodeUrl": "fixture",
            }],
            "totalHits": 1,
        },
    )

    payload = asyncio.run(llm.get_stock_reports("600519", market="CN"))

    assert payload["success"] is True
    assert payload["reports"] == payload["items"]
    assert payload["items"][0]["title"] == "Fixture report"


def test_iwencai_rejects_non_cn_market_without_calling_cn_provider() -> None:
    request = llm.IwencaiRequest(query="AAPL", market="US")

    with pytest.raises(HTTPException) as raised:
        asyncio.run(llm.iwencai_query(request))

    assert raised.value.status_code == 400
    assert raised.value.detail == "问财仅支持 A 股 market"
