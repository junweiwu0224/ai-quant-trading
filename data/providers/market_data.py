"""Market-aware research data providers.

The A-share feed remains owned by :mod:`astock_data_adapter`.  This module
owns the deliberately smaller manual-research contract for the other markets
so their symbols never fall through to an A-share endpoint.  The provider is
read-only and is not eligible for deterministic decisions or auto delivery.
"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any
from urllib.parse import quote, urlparse
from xml.etree import ElementTree
from zoneinfo import ZoneInfo



from data.collector.cache import TTLCache
from data.collector.http_client import get_client
from data.markets import get_market_adapter


YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
_ALLOWED_HOSTS = {"query1.finance.yahoo.com", "query2.finance.yahoo.com"}
_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "AIQuantTrading/1.0 (manual research)",
}
_CHART_CACHE_TTL_SECONDS = 60
_SEARCH_CACHE_TTL_SECONDS = 300
_chart_cache = TTLCache(max_size=128)
_search_cache = TTLCache(max_size=64)

# Yahoo's index symbols are stable identifiers and avoid deriving an index from
# the CN feed.  The ETF is used only as the explicit universe proxy where Yahoo
# does not expose an exchange constituent list through the chart API.
_MARKET_INDEX_TICKERS = {
    "HK": "^HSI",
    "US": "^GSPC",
    "JP": "^N225",
    "KR": "^KS11",
    "TW": "^TWII",
}
_MARKET_UNIVERSE_PROXIES = {
    "HK": "2800.HK",
    "US": "SPY",
    "JP": "1306.T",
    "KR": "069500.KS",
    "TW": "0050.TW",
}
_MARKET_SECTOR_PROXIES = {
    "HK": [("0700.HK", "科技"), ("0005.HK", "金融")],
    "US": [("XLK", "科技"), ("XLF", "金融"), ("XLE", "能源")],
    "JP": [("1613.T", "电子"), ("1615.T", "金融")],
    "KR": [("091160.KS", "半导体"), ("091170.KS", "金融")],
    "TW": [("0052.TW", "科技"), ("0051.TW", "金融")],
}
# Yahoo exposes no exchange-wide constituent or breadth endpoint. These are
# liquid, explicitly labelled sector ETF proxies, not claims of full-market
# sector coverage. Keep the lists conservative so an unavailable proxy is
# represented as unavailable rather than replaced with invented values.
_MARKET_SECTOR_PROXIES = {
    "HK": {"Hang Seng Tech": "3033.HK", "China Enterprises": "2828.HK"},
    "US": {"Technology": "XLK", "Financials": "XLF", "Energy": "XLE", "Healthcare": "XLV", "Industrials": "XLI", "Consumer": "XLY"},
    "JP": {"Banks": "1615.T", "Automobiles": "1622.T", "Machinery": "1624.T", "Retail": "1630.T"},
    "KR": {"Semiconductors": "091160.KS", "Banks": "091170.KS", "Automobiles": "091180.KS"},
    "TW": {"Technology": "0052.TW", "Electronics": "0053.TW", "Financials": "0055.TW"},
}
_SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search"
_YAHOO_RSS_URL = "https://feeds.finance.yahoo.com/rss/2.0/headline"
_NEWS_CACHE_TTL_SECONDS = 300
_news_cache = TTLCache(max_size=64)


def _envelope(
    market: str,
    *,
    component: str,
    data: Any = None,
    error: str | None = None,
    provider: str = "Yahoo Finance",
) -> dict[str, Any]:
    """Build the shared market-level response state for every consumer."""

    available = error is None and data is not None
    return {
        "success": available,
        "available": available,
        "market": market,
        "component": component,
        "provider": provider,
        "source": "yahoo_finance" if available else "yahoo_finance",
        "data_state": "live_snapshot" if available else "unavailable",
        "authoritative": False,
        "manual_research_only": True,
        "degraded": not available,
        "data": data if available else None,
        "error": error,
    }


class MarketProviderError(RuntimeError):
    """Raised when an external market provider returns unusable data."""


def _plain_symbol(market: str, symbol: str) -> tuple[str, str]:
    adapter = get_market_adapter(market)
    canonical = adapter.normalize_instrument(symbol)
    return adapter.code.value, canonical.rsplit(".", 1)[-1]


def yahoo_symbol(market: str, symbol: str) -> str:
    """Translate our canonical instrument into a Yahoo Finance ticker."""

    market_code, plain = _plain_symbol(market, symbol)
    if market_code == "US":
        return plain
    if market_code == "HK":
        # Yahoo uses four-digit HK tickers (Tencent is 0700.HK).
        return f"{int(plain):04d}.HK"
    suffix = {"JP": ".T", "KR": ".KS", "TW": ".TW"}.get(market_code)
    if suffix is None:
        raise MarketProviderError(f"Yahoo Finance provider does not handle {market_code}")
    return f"{plain}{suffix}"


def _fetch_chart(ticker: str, *, interval: str, range_value: str) -> dict[str, Any]:
    parsed = urlparse(f"{YAHOO_CHART_URL}/{ticker}")
    if parsed.hostname not in _ALLOWED_HOSTS:
        raise MarketProviderError("market provider host is not allowed")
    cache_key = f"yahoo-chart:{ticker}:{interval}:{range_value}"
    hit, cached = _chart_cache.get(cache_key)
    if hit:
        return cached
    try:
        response = get_client().get(
            f"{YAHOO_CHART_URL}/{ticker}",
            params={
                "range": range_value,
                "interval": interval,
                "events": "div,splits",
                "includePrePost": "false",
            },
            timeout=8.0,
            headers=_HEADERS,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # provider errors are rendered as a data state
        raise MarketProviderError(f"Yahoo Finance 请求失败: {exc}") from exc
    if not isinstance(payload, dict):
        raise MarketProviderError("Yahoo Finance 返回格式无效")
    _chart_cache.set(cache_key, payload, _CHART_CACHE_TTL_SECONDS)
    return payload


def _interval_for_period(period: str) -> tuple[str, str]:
    normalized = str(period or "daily").strip().lower()
    if normalized in {"daily", "day", "1d"}:
        return "1d", "5y"
    if normalized in {"weekly", "week", "1w"}:
        return "1wk", "10y"
    if normalized in {"monthly", "month", "1mo"}:
        return "1mo", "max"
    raise MarketProviderError(f"Yahoo Finance 当前仅支持日线、周线和月线，收到 {period}")


def _date_from_timestamp(value: Any, timezone_name: str) -> str | None:
    try:
        timestamp = float(value)
        if not math.isfinite(timestamp):
            return None
        return datetime.fromtimestamp(timestamp, ZoneInfo(timezone_name)).date().isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _fetch_search(query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    cache_key = f"yahoo-search:{query}:{limit}"
    hit, cached = _search_cache.get(cache_key)
    if hit:
        return cached
    try:
        response = get_client().get(
            _SEARCH_URL,
            params={"q": query, "quotesCount": max(1, min(limit, 25)), "newsCount": 0},
            timeout=8.0,
            headers=_HEADERS,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise MarketProviderError(f"Yahoo Finance 搜索失败: {exc}") from exc
    rows = payload.get("quotes") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise MarketProviderError("Yahoo Finance 搜索返回格式无效")
    normalized = [
        {
            "symbol": str(row.get("symbol") or ""),
            "name": str(row.get("longname") or row.get("shortname") or row.get("symbol") or ""),
            "exchange": row.get("exchange"),
            "quote_type": row.get("quoteType"),
        }
        for row in rows
        if isinstance(row, dict) and row.get("symbol")
    ]
    _search_cache.set(cache_key, normalized, _SEARCH_CACHE_TTL_SECONDS)
    return normalized


def market_index_ticker(market: str) -> str:
    """Return the adapter benchmark ticker for a supported non-CN market."""
    code = get_market_adapter(market).code.value
    try:
        return _MARKET_INDEX_TICKERS[code]
    except KeyError as exc:
        raise MarketProviderError(f"市场级 provider 不支持 {code}") from exc


def fetch_market_index(market: str, *, period: str = "daily") -> dict[str, Any]:
    """Fetch the selected market benchmark using the same normalized history seam."""
    ticker = market_index_ticker(market)
    history = _fetch_chart(ticker, interval=_interval_for_period(period)[0], range_value=_interval_for_period(period)[1])
    result = (history.get("chart") or {}).get("result") or []
    if not result:
        raise MarketProviderError(f"Yahoo Finance 没有返回 {market} 指数数据")
    chart = result[0] or {}
    bars = _normalize_chart_bars(chart, market, count=120)
    if not bars:
        raise MarketProviderError(f"Yahoo Finance 返回的 {market} 指数数据为空")
    meta = chart.get("meta") or {}
    return {
        "success": True, "available": True, "market": get_market_adapter(market).code.value,
        "provider": "Yahoo Finance", "source": "yahoo_finance_chart", "ticker": ticker,
        "name": meta.get("longName") or meta.get("shortName") or ticker,
        "currency": meta.get("currency") or get_market_adapter(market).currency,
        "index": {"symbol": ticker, "name": meta.get("longName") or meta.get("shortName") or ticker, "price": bars[-1]["close"], "change_pct": bars[-1]["change_pct"], "as_of": bars[-1]["date"]},
        "klines": bars, "as_of": bars[-1]["date"], "data_state": "manual_research",
        "manual_research_only": True, "authoritative": False, "degraded": False,
    }


def _normalize_chart_bars(chart: dict[str, Any], market: str, *, count: int = 120) -> list[dict[str, Any]]:
    adapter = get_market_adapter(market)
    timestamps = chart.get("timestamp") or []
    quote = ((chart.get("indicators") or {}).get("quote") or [{}])[0] or {}
    closes = quote.get("close") or []
    bars: list[dict[str, Any]] = []
    for index, timestamp in enumerate(timestamps):
        date_label = _date_from_timestamp(timestamp, adapter.timezone_name)
        close = _number(closes[index] if index < len(closes) else None)
        if not date_label or close is None:
            continue
        previous = bars[-1]["close"] if bars else None
        bars.append({"date": date_label, "open": _number((quote.get("open") or [None])[index] if index < len(quote.get("open") or []) else None), "high": _number((quote.get("high") or [None])[index] if index < len(quote.get("high") or []) else None), "low": _number((quote.get("low") or [None])[index] if index < len(quote.get("low") or []) else None), "close": close, "volume": _number((quote.get("volume") or [None])[index] if index < len(quote.get("volume") or []) else None), "change_pct": round((close - previous) / previous * 100, 4) if previous else 0.0})
    return bars[-max(1, int(count)):]


def fetch_market_universe(market: str, *, query: str | None = None, limit: int = 50) -> dict[str, Any]:
    """Return an explicit Yahoo search universe; never substitutes CN symbols."""
    adapter = get_market_adapter(market)
    code = adapter.code.value
    if code not in _MARKET_UNIVERSE_PROXIES:
        raise MarketProviderError(f"市场级 provider 不支持 {code}")
    search_query = query or _MARKET_UNIVERSE_PROXIES[code]
    rows = _fetch_search(search_query, limit=limit)
    rows = [row for row in rows if str(row.get("symbol", "")).upper().endswith((".HK", ".T", ".KS", ".TW")) or code == "US"]
    return {"success": True, "available": bool(rows), "market": code, "provider": "Yahoo Finance", "source": "yahoo_finance_search", "universe": rows, "total": len(rows), "proxy_ticker": _MARKET_UNIVERSE_PROXIES[code], "data_state": "manual_research", "manual_research_only": True, "authoritative": False, "degraded": not bool(rows), "error": None if rows else "Yahoo Finance 未返回该市场 universe"}


def _fetch_sector_proxy(market: str, name: str, ticker: str) -> dict[str, Any]:
    """Fetch one sector ETF and retain its proxy boundary in the row."""
    try:
        research_symbol = ticker.split(".", 1)[0] if "." in ticker else ticker
        quote = fetch_market_quote(market, research_symbol)
        return {
            "code": ticker,
            "name": name,
            "ticker": quote.get("ticker") or yahoo_symbol(market, research_symbol),
            "price": quote.get("price"),
            "change_pct": quote.get("change_pct"),
            "as_of": quote.get("as_of"),
            "currency": quote.get("currency"),
            "source": "yahoo_finance_chart",
            "proxy": True,
            "proxy_type": "sector_etf",
            "coverage": "sector ETF proxy; not exchange-wide sector breadth",
            "authoritative": False,
            "manual_research_only": True,
        }
    except (MarketProviderError, KeyError, ValueError) as exc:
        return {
            "code": ticker, "name": name, "ticker": ticker, "source": "yahoo_finance_chart",
            "proxy": True, "proxy_type": "sector_etf", "authoritative": False,
            "manual_research_only": True, "available": False, "error": str(exc),
        }


def fetch_market_sector_proxies(market: str) -> dict[str, Any]:
    """Fetch the declared liquid ETF proxies for a market's sector view."""
    code = get_market_adapter(market).code.value
    definitions = _MARKET_SECTOR_PROXIES.get(code, {})
    if not definitions:
        return {
            "status": "not_available", "available": False, "items": [],
            "reason": "Yahoo Finance adapter has no declared sector ETF proxies",
            "proxy": True, "coverage": "none", "authoritative": False,
            "manual_research_only": True,
        }
    with ThreadPoolExecutor(max_workers=min(6, len(definitions))) as pool:
        futures = [pool.submit(_fetch_sector_proxy, code, name, ticker) for name, ticker in definitions.items()]
        items = [future.result() for future in as_completed(futures)]
    items.sort(key=lambda item: item["name"])
    available = [item for item in items if item.get("price") is not None and not item.get("error")]
    return {
        "status": "proxy_snapshot" if available else "unavailable", "available": bool(available),
        "items": items, "proxy": True, "proxy_type": "sector_etf", "coverage": "declared ETF proxies only",
        "coverage_pct": None, "authoritative": False, "manual_research_only": True,
        "reason": None if available else "Yahoo Finance sector ETF proxies unavailable",
    }


def fetch_market_snapshot(market: str, *, query: str | None = None, limit: int = 50) -> dict[str, Any]:
    """Return one truthful research envelope for every market-level UI block."""
    code = get_market_adapter(market).code.value
    try:
        index = fetch_market_index(code)
    except MarketProviderError as exc:
        index = _envelope(code, component="index", error=str(exc))
    try:
        universe = fetch_market_universe(code, query=query, limit=limit)
    except MarketProviderError as exc:
        universe = _envelope(code, component="universe", error=str(exc))

    sectors = fetch_market_sector_proxies(code)
    try:
        news = fetch_market_news(code, market_index_ticker(code), limit=min(30, max(1, limit)))
        news = {**news, "status": "proxy_snapshot", "items": news.get("news", []), "proxy": True,
                "coverage": "benchmark ticker headlines; not exchange-wide news", "authoritative": False,
                "manual_research_only": True}
    except (MarketProviderError, KeyError, ValueError) as exc:
        news = {"status": "unavailable", "available": False, "items": [], "news": [], "reason": str(exc),
                "proxy": True, "authoritative": False, "manual_research_only": True}

    breadth = {"status": "not_available", "available": False, "items": [],
               "reason": "Yahoo Finance does not provide exchange-wide breadth", "coverage_pct": None,
               "proxy": False, "authoritative": False, "manual_research_only": True}
    unavailable = {"status": "not_integrated", "available": False, "items": [],
                   "reason": "No deterministic provider is integrated for this market", "coverage_pct": None,
                   "proxy": False, "authoritative": False, "manual_research_only": True}
    errors = [item["error"] for item in (index, universe, news) if item.get("error")]
    return {
        "success": bool(index.get("available") or universe.get("available")),
        "available": bool(index.get("available") or universe.get("available")),
        "market": code, "provider": "Yahoo Finance", "source": "yahoo_finance",
        "data_state": "manual_research", "manual_research_only": True, "authoritative": False,
        "coverage_pct": None, "index": index, "universe": universe,
        "breadth": breadth, "sectors": sectors, "heatmap": sectors,
        "hotspots": unavailable, "news": news, "signals": unavailable, "errors": errors,
    }

def fetch_market_history(
    market: str,
    symbol: str,
    *,
    count: int = 120,
    period: str = "daily",
) -> dict[str, Any]:
    """Fetch normalized OHLCV bars for a non-CN manual research request."""

    adapter = get_market_adapter(market)
    market_code, plain = _plain_symbol(market, symbol)
    ticker = yahoo_symbol(market_code, plain)
    interval, range_value = _interval_for_period(period)
    payload = _fetch_chart(ticker, interval=interval, range_value=range_value)
    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        error = ((payload.get("chart") or {}).get("error") or {}).get("description")
        raise MarketProviderError(str(error or "Yahoo Finance 没有返回该标的的历史数据"))
    chart = result[0] or {}
    timestamps = chart.get("timestamp") or []
    quote = ((chart.get("indicators") or {}).get("quote") or [{}])[0] or {}
    # Keep OHLC internally consistent.  Mixing adjusted close with raw
    # open/high/low would create artificial gaps in the research chart.
    closes = quote.get("close") or []
    bars: list[dict[str, Any]] = []
    for index, timestamp in enumerate(timestamps):
        date_label = _date_from_timestamp(timestamp, adapter.timezone_name)
        if not date_label:
            continue
        values = {
            "open": _number((quote.get("open") or [None])[index] if index < len(quote.get("open") or []) else None),
            "high": _number((quote.get("high") or [None])[index] if index < len(quote.get("high") or []) else None),
            "low": _number((quote.get("low") or [None])[index] if index < len(quote.get("low") or []) else None),
            "close": _number(closes[index] if index < len(closes) else None),
            "volume": _number((quote.get("volume") or [None])[index] if index < len(quote.get("volume") or []) else None),
        }
        if values["close"] is None:
            continue
        previous = bars[-1]["close"] if bars else None
        change_pct = ((values["close"] - previous) / previous * 100) if previous else 0.0
        bars.append({
            "date": date_label,
            **values,
            "amount": None,
            "change_pct": round(change_pct, 4),
            "change": round(values["close"] - previous, 6) if previous else 0.0,
            "amplitude": None,
            "turnover": None,
        })
    bars = bars[-max(1, int(count)) :]
    if not bars:
        raise MarketProviderError("Yahoo Finance 返回的历史数据为空")
    meta = chart.get("meta") or {}
    return {
        "success": True,
        "available": True,
        "market": market_code,
        "code": plain,
        "provider": "Yahoo Finance",
        "source": "yahoo_finance_chart",
        "source_version": "chart-v8",
        "ticker": ticker,
        "name": str(meta.get("longName") or meta.get("shortName") or ticker),
        "meta": {
            "regularMarketPrice": meta.get("regularMarketPrice"),
            "previousClose": meta.get("previousClose") or meta.get("chartPreviousClose"),
            "exchangeName": meta.get("exchangeName"),
        },
        "currency": meta.get("currency") or adapter.currency,
        "period": period,
        "klines": bars,
        "as_of": bars[-1]["date"],
        "updated_at": datetime.now(adapter.timezone).isoformat(timespec="seconds"),
        "coverage_pct": round(min(100.0, len(bars) / max(1, int(count)) * 100), 1),
        "data_state": "manual_research",
        "manual_research_only": True,
        "authoritative": False,
        "degraded": False,
    }


def fetch_market_news(market: str, symbol: str, *, limit: int = 20) -> dict[str, Any]:
    """Fetch ticker-scoped headlines from Yahoo's public RSS feed.

    Headlines are research context only; they are never signal inputs eligible
    for deterministic scoring or automatic delivery.
    """
    market_code = get_market_adapter(market).code.value
    if str(symbol or "").startswith("^"):
        ticker = str(symbol).strip()
        plain = ticker
    else:
        market_code, plain = _plain_symbol(market, symbol)
        ticker = yahoo_symbol(market_code, plain)
    safe_limit = max(1, min(int(limit), 50))
    cache_key = f"yahoo-news:{ticker}:{safe_limit}"
    hit, cached = _news_cache.get(cache_key)
    if hit:
        return cached
    try:
        response = get_client().get(
            _YAHOO_RSS_URL,
            params={"s": ticker, "region": "US", "lang": "en-US"},
            timeout=8.0,
            headers={**_HEADERS, "Accept": "application/rss+xml, application/xml"},
        )
        response.raise_for_status()
        root = ElementTree.fromstring(response.content)
    except Exception as exc:
        raise MarketProviderError(f"Yahoo Finance 新闻请求失败: {exc}") from exc
    items: list[dict[str, Any]] = []
    for item in root.findall(".//item")[:safe_limit]:
        def text(name: str) -> str:
            node = item.find(name)
            return (node.text or "").strip() if node is not None else ""
        title, url, published = text("title"), text("link"), text("pubDate")
        if not title:
            continue
        items.append({"title": title, "url": url, "published_at": published, "source": "Yahoo Finance RSS", "ticker": ticker})
    result = {"success": True, "available": bool(items), "market": market_code, "code": plain, "ticker": ticker, "provider": "Yahoo Finance", "source": "yahoo_finance_rss", "news": items, "count": len(items), "data_state": "manual_research", "manual_research_only": True, "authoritative": False, "degraded": not bool(items), "error": None if items else "Yahoo Finance 未返回该标的新闻"}
    _news_cache.set(cache_key, result, _NEWS_CACHE_TTL_SECONDS)
    return result


def fetch_market_quote(market: str, symbol: str) -> dict[str, Any]:
    """Fetch the latest Yahoo quote metadata using the same chart seam."""

    history = fetch_market_history(market, symbol, count=2, period="daily")
    latest = history["klines"][-1]
    previous = history["klines"][-2] if len(history["klines"]) > 1 else None
    price = _number(((history.get("meta") or {}).get("regularMarketPrice"))) or latest.get("close")
    if previous and price is not None:
        change = price - previous.get("close", price)
        change_pct = change / previous["close"] * 100 if previous.get("close") else 0.0
    else:
        change = latest.get("change") or 0.0
        change_pct = latest.get("change_pct") or 0.0
    return {
        **history,
        "price": price,
        "open": latest.get("open"),
        "high": latest.get("high"),
        "low": latest.get("low"),
        "pre_close": previous.get("close") if previous else None,
        "change": round(change, 6) if change is not None else None,
        "change_pct": round(change_pct, 4) if change_pct is not None else None,
        "volume": latest.get("volume"),
        "amount": None,
        "industry": None,
        "sector": None,
    }


__all__ = ["MarketProviderError", "fetch_market_history", "fetch_market_quote", "fetch_market_news", "fetch_market_index", "fetch_market_universe", "fetch_market_sector_proxies", "fetch_market_snapshot", "market_index_ticker", "yahoo_symbol"]
