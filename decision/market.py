"""Compatibility projection over the canonical :mod:`data.markets` matrix.

The decision package historically exposed a smaller ``MarketAdapter`` shape.
Keeping this projection preserves those callers while making ``data.markets``
the only authority for provider status and capability claims.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from data.markets import MARKET_ADAPTERS as CANONICAL_MARKETS
from data.markets import MarketAdapter as CanonicalMarketAdapter
from data.markets import MarketCode, ProviderHealth


@dataclass(frozen=True)
class MarketAdapter:
    canonical: CanonicalMarketAdapter

    @property
    def market(self) -> str:
        return self.canonical.code.value

    @property
    def label(self) -> str:
        return self.canonical.display_name

    @property
    def timezone(self) -> str:
        return self.canonical.timezone_name

    @property
    def currency(self) -> str:
        return self.canonical.currency

    @property
    def source(self) -> str:
        current = [item.name for item in self.canonical.providers if item.status.value in {"legacy_current", "integrated"}]
        return "/".join(current) or ", ".join(item.name for item in self.canonical.providers)

    @property
    def source_status(self) -> str:
        if any(item.status.value == "integrated" for item in self.canonical.providers):
            return "integrated"
        return "not_connected" if not any(item.status.value == "legacy_current" for item in self.canonical.providers) else "legacy_manual"

    @property
    def daily_research(self) -> bool:
        return self.canonical.supports_manual_daily_research

    @property
    def intraday_5m(self) -> bool:
        # Capability declaration is not runtime qualification.  The decision
        # API only exposes this as true after a qualified health probe exists.
        return False

    @property
    def automatic_push(self) -> bool:
        return False

    @property
    def fallback_reason(self) -> str:
        candidates = [item.name for item in self.canonical.providers if item.qualifies_for_intraday_auto_push]
        if candidates:
            return "%s 尚未完成集成、健康和覆盖率资格检查" % ", ".join(candidates)
        return "该市场没有已声明的合格盘中自动推送 provider"

    def capabilities(self) -> dict[str, Any]:
        value = self.canonical.capability_matrix()
        value.update(
            {
                "market": self.market,
                "label": self.label,
                "timezone": self.timezone,
                "source": self.source,
                "source_status": self.source_status,
                "daily_research": self.daily_research,
                "intraday_5m": self.intraday_5m,
                "automatic_push": self.automatic_push,
                "fallback_reason": self.fallback_reason,
            }
        )
        return value

    def automatic_push_eligibility(self, provider_health: Mapping[str, ProviderHealth | Mapping[str, Any]] | None = None, *, granularity: str = "5m"):
        return self.canonical.automatic_push_eligibility(provider_health, granularity=granularity)


MARKET_ADAPTERS: dict[str, MarketAdapter] = {
    code.value: MarketAdapter(adapter) for code, adapter in CANONICAL_MARKETS.items()
}


def get_market_adapter(market: str) -> MarketAdapter:
    normalized = str(market or "CN").strip().upper()
    aliases = {"A": "CN", "A_SHARE": "CN", "ASHARE": "CN", "A股": "CN", "港股": "HK", "美股": "US", "日股": "JP", "韩股": "KR", "台股": "TW"}
    return MARKET_ADAPTERS[aliases.get(normalized, normalized)]


__all__ = ["MARKET_ADAPTERS", "MarketAdapter", "get_market_adapter"]
