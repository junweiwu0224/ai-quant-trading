"""Contract tests for the six-market provider boundary."""

import pytest
from fastapi.testclient import TestClient

from data.providers import market_data


MARKETS = ("CN", "HK", "US", "JP", "KR", "TW")
NON_CN_MARKETS = MARKETS[1:]


@pytest.fixture
def client() -> TestClient:
    from dashboard.app import app

    return TestClient(app)


def _snapshot(code: str, *, available: bool = True) -> dict:
    index = {
        "success": available,
        "available": available,
        "market": code,
        "provider": f"fixture-{code}",
        "source": "fixture_provider",
        "index": {
            "symbol": f"^{code}",
            "name": f"{code} benchmark",
            "price": 100.0,
            "change_pct": 1.25,
        },
        "as_of": "2026-08-18",
        "data_state": "manual_research" if available else "unavailable",
        "error": None if available else f"{code} index unavailable",
    }
    universe = {
        "success": available,
        "available": available,
        "market": code,
        "provider": f"fixture-{code}",
        "source": "fixture_provider",
        "universe": ([{"symbol": f"{code}.FIX", "name": f"{code} fixture"}] if available else []),
        "total": 1 if available else 0,
        "data_state": "manual_research" if available else "unavailable",
        "error": None if available else f"{code} universe unavailable",
    }
    component = {
        "status": "not_available",
        "items": [],
        "reason": f"{code} breadth is not provided by fixture",
    }
    return {
        "success": available,
        "available": available,
        "market": code,
        "provider": f"fixture-{code}",
        "source": "fixture_provider",
        "data_state": "manual_research" if available else "unavailable",
        "manual_research_only": True,
        "authoritative": False,
        "index": index,
        "universe": universe,
        "breadth": component,
        "sectors": {**component, "reason": f"{code} sectors are not provided by fixture"},
        "news": {**component, "reason": f"{code} news is not provided by fixture"},
        "signals": {"status": "not_integrated", "items": [], "reason": "fixture signal provider absent"},
        "errors": [] if available else [f"{code} provider unavailable"],
    }


@pytest.mark.parametrize("market", MARKETS)
def test_each_market_snapshot_preserves_provider_contract(client, monkeypatch, market):
    expected = _snapshot(market)
    monkeypatch.setattr(market_data, "fetch_market_snapshot", lambda code, **kwargs: _snapshot(code))

    response = client.get(f"/api/market/snapshot?market={market}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["market"] == market
    # CN keeps its legacy aggregation endpoints; the market-level snapshot is
    # intentionally unavailable rather than claiming a second provider.
    if market == "CN":
        assert payload["success"] is False
        assert payload["available"] is False
        return
    assert payload["success"] is True
    assert payload["available"] is True
    assert payload["provider"] == expected["provider"]
    assert payload["source"] == expected["source"]
    assert payload["data_state"] == expected["data_state"]
    assert payload["manual_research_only"] is True
    assert payload["authoritative"] is False
    assert payload["index"]["market"] == market
    assert payload["universe"]["market"] == market


@pytest.mark.parametrize("market", NON_CN_MARKETS)
def test_market_endpoints_keep_market_scope_and_do_not_fabricate_on_provider_failure(
    client, monkeypatch, market
):
    monkeypatch.setattr(market_data, "fetch_market_snapshot", lambda code, **kwargs: _snapshot(code, available=False))

    for path in (
        "breadth",
        "radar?fast=true",
        "sectors?fast=true",
        "heatmap?fast=true",
        "hotspot",
    ):
        response = client.get(f"/api/market/{path}&market={market}" if "?" in path else f"/api/market/{path}?market={market}")
        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is False
        assert payload["available"] is False
        assert payload["market"] == market
        assert payload["manual_research_only"] is True
        assert payload["authoritative"] is False
        assert payload["source_unavailable"] is True
        assert payload["error"]
        for field in ("total_stocks", "market_change_pct"):
            if field in payload:
                assert payload[field] is None


@pytest.mark.parametrize(
    "path",
    (
        "/api/market/snapshot",
        "/api/market/breadth",
        "/api/market/radar",
        "/api/market/sectors",
        "/api/market/heatmap",
        "/api/market/hotspot",
        "/api/market/news",
    ),
)
def test_market_endpoints_reject_unknown_market(client, path):
    response = client.get(f"{path}?market=ZZ")

    assert response.status_code == 400
    assert response.json()["detail"] == "无效市场: ZZ"
