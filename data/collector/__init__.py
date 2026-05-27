"""Data collection package exports."""

from .collector import StockCollector

__all__ = ["StockCollector", "QuoteData", "get_quote_service"]


def __getattr__(name):
    if name in {"QuoteData", "get_quote_service"}:
        from .quote_service import QuoteData, get_quote_service

        exports = {
            "QuoteData": QuoteData,
            "get_quote_service": get_quote_service,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
