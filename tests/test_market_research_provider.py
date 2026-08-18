from __future__ import annotations

import asyncio

from dashboard.routers import decisions, stock_detail
from data.providers import market_data


class _Response:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "chart": {
                "result": [
                    {
                        "timestamp": [1723723200, 1723809600, 1724068800],
                        "indicators": {
                            "quote": [{
                                "open": [100, 101, 102],
                                "high": [103, 104, 105],
                                "low": [99, 100, 101],
                                "close": [102, 103, 104],
                                "volume": [1000, 1100, 1200],
                            }],
                        },
                        "meta": {
                            "currency": "USD",
                            "longName": "Apple Inc.",
                            "regularMarketPrice": 104,
                            "chartPreviousClose": 103,
                        },
                    }
                ],
                "error": None,
            }
        }


class _Client:
    def get(self, *_args, **_kwargs):
        return _Response()


class _CountingClient(_Client):
    def __init__(self) -> None:
        self.calls = 0

    def get(self, *_args, **_kwargs):
        self.calls += 1
        return super().get(*_args, **_kwargs)


def test_yahoo_symbol_mapping_is_market_aware() -> None:
    assert market_data.yahoo_symbol("US", "AAPL") == "AAPL"
    assert market_data.yahoo_symbol("HK", "00700") == "0700.HK"
    assert market_data.yahoo_symbol("JP", "7203") == "7203.T"
    assert market_data.yahoo_symbol("KR", "005930") == "005930.KS"
    assert market_data.yahoo_symbol("TW", "2330") == "2330.TW"


def test_market_history_normalizes_chart_rows(monkeypatch) -> None:
    market_data._chart_cache.clear()
    monkeypatch.setattr(market_data, "get_client", lambda: _Client())

    result = market_data.fetch_market_history("US", "AAPL", count=2)

    assert result["source"] == "yahoo_finance_chart"
    assert result["manual_research_only"] is True
    assert [row["close"] for row in result["klines"]] == [103.0, 104.0]
    assert result["as_of"]


def test_market_history_reuses_chart_payload_across_count_requests(monkeypatch) -> None:
    market_data._chart_cache.clear()
    client = _CountingClient()
    monkeypatch.setattr(market_data, "get_client", lambda: client)

    market_data.fetch_market_history("US", "AAPL", count=120)
    market_data.fetch_market_history("US", "AAPL", count=250)

    assert client.calls == 1


def test_market_news_normalizes_yahoo_rss_and_caches(monkeypatch) -> None:
    market_data._news_cache.clear()
    class Response:
        content = b"<rss><channel><item><title>Apple update</title><link>https://example.test/a</link><pubDate>today</pubDate></item></channel></rss>"
        def raise_for_status(self):
            return None
    class Client:
        calls = 0
        def get(self, *_args, **_kwargs):
            self.calls += 1
            return Response()
    client = Client()
    monkeypatch.setattr(market_data, "get_client", lambda: client)
    first = market_data.fetch_market_news("US", "AAPL", limit=5)
    second = market_data.fetch_market_news("US", "AAPL", limit=5)
    assert first["source"] == "yahoo_finance_rss"
    assert first["news"][0]["title"] == "Apple update"
    assert first["manual_research_only"] is True
    assert second["news"] == first["news"]
    assert client.calls == 1


    stock_detail._cache.clear()
    calls = 0

    def fake_quote(_market: str, _symbol: str) -> dict:
        nonlocal calls
        calls += 1
        return {"code": "AAPL", "name": "Apple Inc.", "source": "fixture", "klines": [], "price": 104}

    monkeypatch.setattr(stock_detail, "fetch_market_quote", fake_quote)

    first = asyncio.run(stock_detail.get_stock_detail("AAPL", "US"))
    second = asyncio.run(stock_detail.get_stock_detail("AAPL", "US"))

    assert first["price"] == second["price"] == 104
    assert calls == 1


def test_decision_research_renders_non_cn_bars_without_a_share_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        decisions,
        "fetch_market_history",
        lambda *args, **kwargs: {
            "source": "yahoo_finance_chart",
            "provider": "Yahoo Finance",
            "as_of": "2026-08-18",
            "updated_at": "2026-08-18T16:00:00-04:00",
            "coverage_pct": 100.0,
            "klines": [{"date": "2026-08-18", "open": 100, "high": 105, "low": 99, "close": 104, "volume": 1000}],
        },
    )

    payload = asyncio.run(decisions.research("US", "AAPL", {"workspace": {"id": "fixture"}}))

    assert payload["status"] == "manual_research"
    assert payload["bars"][0]["close"] == 104
    assert payload["authoritative"] is False
    assert payload["data_quality"]["manual_research_only"] is True


def test_market_snapshot_exposes_proxy_boundaries_without_fabricated_breadth(monkeypatch) -> None:
    monkeypatch.setattr(market_data, "fetch_market_index", lambda market: {"available": True, "market": market, "index": {"change_pct": 1.2}})
    monkeypatch.setattr(market_data, "fetch_market_universe", lambda market, **kwargs: {"available": True, "universe": [], "total": 0})
    monkeypatch.setattr(market_data, "fetch_market_sector_proxies", lambda market: {
        "status": "proxy_snapshot", "available": True, "items": [{"ticker": "XLK", "proxy": True}],
        "proxy": True, "authoritative": False, "manual_research_only": True,
    })
    monkeypatch.setattr(market_data, "fetch_market_news", lambda *args, **kwargs: {
        "available": True, "news": [{"title": "fixture"}], "manual_research_only": True,
    })

    result = market_data.fetch_market_snapshot("US")

    assert result["success"] is True
    assert result["sectors"]["proxy"] is True
    assert result["sectors"]["authoritative"] is False
    assert result["news"]["proxy"] is True
    assert result["breadth"]["available"] is False
    assert result["signals"]["status"] == "not_integrated"
    assert result["manual_research_only"] is True
