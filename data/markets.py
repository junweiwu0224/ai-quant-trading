"""Explicit multi-market capability contracts.

This module declares what the product can claim.  It does not connect to a
provider, infer health from a package import, or upgrade a legacy feed into an
automatic-push source.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from enum import Enum
from typing import Any, Mapping, Optional
from zoneinfo import ZoneInfo


class MarketCode(str, Enum):
    CN = "CN"
    HK = "HK"
    US = "US"
    JP = "JP"
    KR = "KR"
    TW = "TW"


class ProviderStatus(str, Enum):
    LEGACY_CURRENT = "legacy_current"
    INTEGRATED = "integrated"
    TARGET_NOT_INTEGRATED = "target_not_integrated"


@dataclass(frozen=True)
class TradingCalendar:
    """Small, injectable calendar interface used by all offline consumers.

    The default implementation only knows the weekday rule.  It is an
    explicit fallback, not a claim that an exchange holiday provider is
    connected.  Callers that have a verified exchange calendar can inject it
    through ``MarketAdapter.calendar`` or pass holidays for a fixture.
    """

    name: str = "weekday_fallback"
    source: str = "local_weekday_fallback"
    holidays: frozenset[date] = frozenset()
    verified: bool = False
    kind: str = "weekday_fallback"

    @property
    def is_verified_exchange_calendar(self) -> bool:
        """Whether this calendar is evidence-backed for exchange automation.

        The weekday implementation is deliberately useful for offline/manual
        calculations, but it cannot stand in for an exchange holiday
        schedule.  Keep this property on the calendar object so every caller
        has to make that distinction explicitly.
        """

        return bool(self.verified) and self.kind == "verified_exchange"

    def is_trading_day(
        self,
        when: datetime | date,
        *,
        holidays: set[date] | frozenset[date] = frozenset(),
    ) -> bool:
        day = when.date() if isinstance(when, datetime) else when
        if not isinstance(day, date):
            raise TypeError("calendar date must be a date or datetime")
        return day.weekday() < 5 and day not in self.holidays and day not in holidays

    def trading_days(
        self,
        start: datetime | date,
        end: datetime | date,
        *,
        holidays: set[date] | frozenset[date] = frozenset(),
    ) -> tuple[date, ...]:
        start_day = start.date() if isinstance(start, datetime) else start
        end_day = end.date() if isinstance(end, datetime) else end
        if start_day > end_day:
            return ()
        days: list[date] = []
        current = start_day
        while current <= end_day:
            if self.is_trading_day(current, holidays=holidays):
                days.append(current)
            current += timedelta(days=1)
        return tuple(days)

    def next_trading_day(
        self,
        when: datetime | date,
        *,
        holidays: set[date] | frozenset[date] = frozenset(),
        include_current: bool = False,
        max_days: int = 3660,
    ) -> date | None:
        day = when.date() if isinstance(when, datetime) else when
        if not isinstance(day, date):
            raise TypeError("calendar date must be a date or datetime")
        if not include_current:
            day += timedelta(days=1)
        for _ in range(max(0, int(max_days)) + 1):
            if self.is_trading_day(day, holidays=holidays):
                return day
            day += timedelta(days=1)
        return None


WeekdayTradingCalendar = TradingCalendar


@dataclass(frozen=True)
class ProviderCapability:
    """A declared provider role, separate from runtime health."""

    name: str
    status: ProviderStatus
    granularities: frozenset[str]
    purpose: str
    qualifies_for_intraday_auto_push: bool = False
    qualifies_for_daily_auto_push: bool = False


@dataclass(frozen=True)
class ProviderHealth:
    """Runtime evidence required before a provider can qualify a trigger."""

    healthy: bool = False
    validated: bool = False
    completed_bars: bool = False
    updated_at: Optional[str] = None
    coverage_pct: float = 0.0
    field_sources: Mapping[str, str] | None = None

    @property
    def coverage_complete(self) -> bool:
        try:
            coverage = float(self.coverage_pct)
        except (TypeError, ValueError, OverflowError):
            return False
        return math.isfinite(coverage) and 100.0 <= coverage <= 100.0

    @property
    def qualified_intraday(self) -> bool:
        return self.healthy and self.validated and self.completed_bars and self.coverage_complete and bool(self.field_sources)

    @property
    def qualified_daily(self) -> bool:
        return self.healthy and self.validated and self.coverage_complete and bool(self.field_sources)


@dataclass(frozen=True)
class AutomaticPushEligibility:
    eligible: bool
    market: MarketCode
    granularity: str
    qualified_provider: Optional[str] = None
    reasons: tuple[str, ...] = ()


class InstrumentNormalizationError(ValueError):
    pass


_CN_SYMBOL_RE = re.compile(r"^(?:(?:SH|SZ)[.]?)?(\d{6})$", re.IGNORECASE)
_HK_SYMBOL_RE = re.compile(r"^(?:HK[.]?)?(\d{1,5})(?:[.]HK)?$", re.IGNORECASE)
_US_SYMBOL_RE = re.compile(r"^(?:US[.]?)?([A-Z][A-Z0-9.-]{0,14})$", re.IGNORECASE)
_FOUR_DIGIT_SYMBOL_RE = re.compile(r"^(?:[A-Z]{2}[.]?)?(\d{4,6})$", re.IGNORECASE)


@dataclass(frozen=True)
class MarketAdapter:
    """Market semantics and capability claims behind one explicit interface."""

    code: MarketCode
    display_name: str
    timezone_name: str
    exchange_calendar: str
    currency: str
    price_increment: float
    benchmark: str
    adjustment_policy: str
    corporate_actions_policy: str
    cost_model: str
    daily_granularities: frozenset[str]
    intraday_granularities: frozenset[str]
    report_types: frozenset[str]
    providers: tuple[ProviderCapability, ...]
    automatic_push_supported: bool
    annualization_days: int = 252
    calendar: TradingCalendar = field(default_factory=TradingCalendar)

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)

    @property
    def supports_manual_daily_research(self) -> bool:
        return "manual_research" in self.report_types and "1d" in self.daily_granularities

    @property
    def supports_scheduled_daily_report(self) -> bool:
        return (
            "scheduled_daily_report" in self.report_types
            and "1d" in self.daily_granularities
            and self.calendar_verified
        )

    def supports_granularity(self, granularity: str) -> bool:
        return str(granularity) in self.daily_granularities | self.intraday_granularities

    def is_trading_day(self, when: datetime | date, *, holidays: set[date] | frozenset[date] = frozenset()) -> bool:
        """Return the answer from the adapter's explicit calendar seam."""

        return bool(self.calendar.is_trading_day(when, holidays=holidays))

    @property
    def calendar_name(self) -> str:
        return str(getattr(self.calendar, "name", self.exchange_calendar))

    @property
    def calendar_source(self) -> str:
        return str(getattr(self.calendar, "source", "unknown"))

    @property
    def calendar_kind(self) -> str:
        return str(getattr(self.calendar, "kind", "unknown"))

    @property
    def calendar_verified(self) -> bool:
        """Return verified exchange-calendar status, never inferred by name."""

        marker = getattr(self.calendar, "is_verified_exchange_calendar", False)
        if callable(marker):
            try:
                marker = marker()
            except Exception:
                return False
        return marker is True

    @property
    def calendar_status(self) -> str:
        return "verified_exchange" if self.calendar_verified else "unverified_fallback"

    def trading_days(
        self,
        start: datetime | date,
        end: datetime | date,
        *,
        holidays: set[date] | frozenset[date] = frozenset(),
    ) -> tuple[date, ...]:
        """Return calendar sessions without consulting a provider implicitly."""

        method = getattr(self.calendar, "trading_days", None)
        if callable(method):
            return tuple(method(start, end, holidays=holidays))
        start_day = start.date() if isinstance(start, datetime) else start
        end_day = end.date() if isinstance(end, datetime) else end
        current = start_day
        days: list[date] = []
        while current <= end_day:
            if self.is_trading_day(current, holidays=holidays):
                days.append(current)
            current += timedelta(days=1)
        return tuple(days)

    def next_trading_day(
        self,
        when: datetime | date,
        *,
        holidays: set[date] | frozenset[date] = frozenset(),
        include_current: bool = False,
    ) -> date | None:
        method = getattr(self.calendar, "next_trading_day", None)
        if callable(method):
            return method(when, holidays=holidays, include_current=include_current)
        day = when.date() if isinstance(when, datetime) else when
        if not include_current:
            day += timedelta(days=1)
        for _ in range(3661):
            if self.is_trading_day(day, holidays=holidays):
                return day
            day += timedelta(days=1)
        return None

    def execution_contract(self, *, cost_model: Any = None, benchmark_instrument: str | None = None) -> Any:
        """Build the shared execution contract without claiming a provider."""

        from engine.execution_model import ExecutionDataContract, resolve_execution_cost_model

        resolved_cost = resolve_execution_cost_model(cost_model)
        return ExecutionDataContract(
            market=self.code.value,
            timezone=self.timezone_name,
            exchange_calendar=self.exchange_calendar,
            calendar_name=self.calendar_name,
            calendar_source=self.calendar_source,
            benchmark=self.benchmark,
            benchmark_instrument=benchmark_instrument,
            annualization_days=self.annualization_days,
            source="market_adapter",
            cost_model=resolved_cost,
        )

    @property
    def supports_intraday_automatic_push(self) -> bool:
        return self.automatic_push_supported and self.calendar_verified and bool(self.intraday_granularities)

    def normalize_instrument(self, symbol: str) -> str:
        """Canonicalize only identifier syntax; never perform symbol lookup."""

        value = str(symbol or "").strip().upper()
        if self.code is MarketCode.CN:
            match = _CN_SYMBOL_RE.fullmatch(value)
            if match:
                code = match.group(1)
                exchange = "SH" if code.startswith(("5", "6", "9")) else "SZ"
                return "%s.%s" % (exchange, code)
        elif self.code is MarketCode.HK:
            match = _HK_SYMBOL_RE.fullmatch(value)
            if match:
                return "HK.%05d" % int(match.group(1))
        elif self.code is MarketCode.US:
            match = _US_SYMBOL_RE.fullmatch(value)
            if match:
                return "US.%s" % match.group(1)
        else:
            match = _FOUR_DIGIT_SYMBOL_RE.fullmatch(value)
            if match:
                digits = match.group(1)
                if self.code is MarketCode.KR:
                    digits = digits.zfill(6)
                elif self.code in {MarketCode.JP, MarketCode.TW}:
                    digits = digits.zfill(4)
                return "%s.%s" % (self.code.value, digits)
        raise InstrumentNormalizationError("invalid %s instrument: %r" % (self.code.value, symbol))

    normalize_symbol = normalize_instrument

    def automatic_push_eligibility(
        self,
        provider_health: Mapping[str, ProviderHealth | Mapping[str, Any]] | None = None,
        *,
        granularity: str = "5m",
        max_age_seconds: int = 900,
        now: Any = None,
    ) -> AutomaticPushEligibility:
        """Require a healthy, validated source of completed intraday bars.

        Declaring a target source is insufficient.  A caller must supply fresh
        runtime health for a provider explicitly marked eligible in this matrix.
        """

        granularity = str(granularity)
        reasons: list[str] = []
        if not self.automatic_push_supported:
            reasons.append("automatic push is disabled for this market")
        if not self.calendar_verified:
            reasons.append("verified exchange calendar is required for automatic push")
        declared_granularities = self.daily_granularities if granularity == "1d" else self.intraday_granularities
        if granularity not in declared_granularities:
            reasons.append("%s bars are not declared for this market" % granularity)
        is_daily = granularity == "1d"
        candidates = [
            provider
            for provider in self.providers
            if (provider.qualifies_for_daily_auto_push if is_daily else provider.qualifies_for_intraday_auto_push)
            and granularity in provider.granularities
        ]
        health_by_provider = provider_health or {}
        if max_age_seconds < 0:
            raise ValueError("max_age_seconds cannot be negative")
        if now is None:
            from datetime import datetime, timezone

            now = datetime.now(timezone.utc)
        elif not getattr(now, "tzinfo", None):
            from datetime import timezone

            now = now.replace(tzinfo=timezone.utc)
        for provider in candidates:
            raw_health = health_by_provider.get(provider.name)
            health = _coerce_health(raw_health)
            qualified = health and (health.qualified_daily if is_daily else health.qualified_intraday)
            if not reasons and health and provider.status is ProviderStatus.INTEGRATED and qualified:
                from datetime import datetime

                try:
                    updated = datetime.fromisoformat(str(health.updated_at).replace("Z", "+00:00")) if health.updated_at else None
                except ValueError:
                    updated = None
                if updated is None:
                    reasons.append("qualified provider health has no updated_at")
                    continue
                if not updated.tzinfo:
                    from datetime import timezone

                    updated = updated.replace(tzinfo=timezone.utc)
                if updated > now:
                    reasons.append("qualified provider health is from the future")
                    continue
                age = max(0.0, (now - updated).total_seconds())
                if age > max_age_seconds:
                    reasons.append("qualified provider health is stale")
                    continue
                return AutomaticPushEligibility(
                    eligible=True,
                    market=self.code,
                    granularity=granularity,
                    qualified_provider=provider.name,
                )
        if not candidates:
            reasons.append("no provider is declared for qualified %s auto push" % ("daily" if is_daily else "intraday"))
        else:
            reasons.append("no qualified %s provider has healthy validated completed bars" % ("daily" if is_daily else "intraday"))
        return AutomaticPushEligibility(
            eligible=False,
            market=self.code,
            granularity=granularity,
            reasons=tuple(dict.fromkeys(reasons)),
        )

    def is_automatic_push_eligible(
        self,
        provider_health: Mapping[str, ProviderHealth | Mapping[str, Any]] | None = None,
        *,
        granularity: str = "5m",
    ) -> bool:
        return self.automatic_push_eligibility(provider_health, granularity=granularity).eligible

    can_auto_push = is_automatic_push_eligible

    def capability_matrix(self) -> dict[str, Any]:
        """Return a serializable, credential-free projection for reports/UI."""

        return {
            "market": self.code.value,
            "display_name": self.display_name,
            "timezone": self.timezone_name,
            "exchange_calendar": self.exchange_calendar,
            "calendar_name": self.calendar_name,
            "calendar_source": self.calendar_source,
            "calendar_kind": self.calendar_kind,
            "calendar_verified": self.calendar_verified,
            "calendar_status": self.calendar_status,
            "calendar_automation_eligible": self.calendar_verified,
            "currency": self.currency,
            "price_increment": self.price_increment,
            "benchmark": self.benchmark,
            "adjustment_policy": self.adjustment_policy,
            "corporate_actions_policy": self.corporate_actions_policy,
            "cost_model": self.cost_model,
            "daily_granularities": sorted(self.daily_granularities),
            "intraday_granularities": sorted(self.intraday_granularities),
            "report_types": sorted(self.report_types),
            "automatic_push_declared_by_adapter": self.automatic_push_supported,
            "automatic_push_supported": self.automatic_push_supported and self.calendar_verified,
            "annualization_days": self.annualization_days,
            "providers": [
                {
                    "name": provider.name,
                    "status": provider.status.value,
                    "granularities": sorted(provider.granularities),
                    "purpose": provider.purpose,
                    "qualifies_for_intraday_auto_push": provider.qualifies_for_intraday_auto_push,
                    "qualifies_for_daily_auto_push": provider.qualifies_for_daily_auto_push,
                }
                for provider in self.providers
            ],
        }


def _coerce_health(value: ProviderHealth | Mapping[str, Any] | None) -> ProviderHealth | None:
    if isinstance(value, ProviderHealth):
        return value
    if isinstance(value, Mapping):
        try:
            coverage_pct = float(value.get("coverage_pct", 0) or 0)
        except (TypeError, ValueError, OverflowError):
            return None
        return ProviderHealth(
            healthy=bool(value.get("healthy")),
            validated=bool(value.get("validated")),
            completed_bars=bool(value.get("completed_bars")),
            updated_at=str(value["updated_at"]) if value.get("updated_at") else None,
            coverage_pct=coverage_pct,
            field_sources=value.get("field_sources") if isinstance(value.get("field_sources"), Mapping) else None,
        )
    return None


def _provider(
    name: str,
    status: ProviderStatus,
    granularities: tuple[str, ...],
    purpose: str,
    *,
    qualified_intraday: bool = False,
    qualified_daily: bool = False,
) -> ProviderCapability:
    return ProviderCapability(
        name=name,
        status=status,
        granularities=frozenset(granularities),
        purpose=purpose,
        qualifies_for_intraday_auto_push=qualified_intraday,
        qualifies_for_daily_auto_push=qualified_daily,
    )


A_SHARE_MARKET_ADAPTER = MarketAdapter(
    code=MarketCode.CN,
    display_name="A shares",
    timezone_name="Asia/Shanghai",
    exchange_calendar="SSE/SZSE",
    currency="CNY",
    price_increment=0.01,
    benchmark="CSI 300 total return",
    adjustment_policy="provider versioned forward adjustment",
    corporate_actions_policy="provider corporate-action snapshot required for backtests",
    cost_model="versioned A-share broker cost model",
    daily_granularities=frozenset({"1d"}),
    intraday_granularities=frozenset({"1m", "5m", "15m", "30m", "60m"}),
    report_types=frozenset({"manual_research", "scheduled_daily_report", "intraday_signal"}),
    providers=(
        _provider("mootdx", ProviderStatus.LEGACY_CURRENT, ("1d", "1m", "5m", "15m", "30m", "60m"), "current legacy quote and bars"),
        _provider("tencent", ProviderStatus.LEGACY_CURRENT, ("1d",), "current legacy daily fallback"),
        _provider("eastmoney", ProviderStatus.LEGACY_CURRENT, ("1d", "5m", "15m", "30m", "60m"), "current legacy fallback"),
        _provider("Tushare Pro", ProviderStatus.TARGET_NOT_INTEGRATED, ("1d",), "target historical and backtest source", qualified_daily=True),
        _provider("TickFlow", ProviderStatus.TARGET_NOT_INTEGRATED, ("5m",), "target completed intraday source", qualified_intraday=True),
    ),
    # The capability shape is ready, but no current provider is qualified for
    # automatic delivery until the target source is actually integrated and
    # independently health-validated.
    automatic_push_supported=False,
)


def _longbridge_market(code: MarketCode, display_name: str, currency: str, calendar: str, benchmark: str) -> MarketAdapter:
    return MarketAdapter(
        code=code,
        display_name=display_name,
        timezone_name="Asia/Hong_Kong" if code is MarketCode.HK else "America/New_York",
        exchange_calendar=calendar,
        currency=currency,
        price_increment=0.01,
        benchmark=benchmark,
        adjustment_policy="Longbridge adjustment version required",
        corporate_actions_policy="Longbridge corporate-action snapshot required for backtests",
        cost_model="versioned market-specific cost model",
        daily_granularities=frozenset({"1d"}),
        intraday_granularities=frozenset({"5m"}),
        report_types=frozenset({"manual_research", "scheduled_daily_report", "intraday_signal"}),
        providers=(
            _provider("Longbridge", ProviderStatus.TARGET_NOT_INTEGRATED, ("1d", "5m"), "target daily and completed intraday source", qualified_intraday=True, qualified_daily=True),
        ),
        automatic_push_supported=True,
    )


HONG_KONG_MARKET_ADAPTER = _longbridge_market(MarketCode.HK, "Hong Kong", "HKD", "HKEX", "Hang Seng total return")
US_MARKET_ADAPTER = _longbridge_market(MarketCode.US, "United States", "USD", "NYSE/NASDAQ", "S&P 500 total return")


def _manual_daily_market(code: MarketCode, display_name: str, timezone_name: str, currency: str, calendar: str, benchmark: str) -> MarketAdapter:
    return MarketAdapter(
        code=code,
        display_name=display_name,
        timezone_name=timezone_name,
        exchange_calendar=calendar,
        currency=currency,
        price_increment=0.01,
        benchmark=benchmark,
        adjustment_policy="provider adjustment version required",
        corporate_actions_policy="manual daily research only; snapshot provider treatment",
        cost_model="market-specific model required before automated validation",
        daily_granularities=frozenset({"1d"}),
        intraday_granularities=frozenset(),
        report_types=frozenset({"manual_research", "scheduled_daily_report"}),
        providers=(
            _provider("YFinance", ProviderStatus.TARGET_NOT_INTEGRATED, ("1d",), "manual daily research only"),
        ),
        automatic_push_supported=False,
    )


JAPAN_MARKET_ADAPTER = _manual_daily_market(MarketCode.JP, "Japan", "Asia/Tokyo", "JPY", "TSE", "TOPIX total return")
KOREA_MARKET_ADAPTER = _manual_daily_market(MarketCode.KR, "Korea", "Asia/Seoul", "KRW", "KRX", "KOSPI total return")
TAIWAN_MARKET_ADAPTER = _manual_daily_market(MarketCode.TW, "Taiwan", "Asia/Taipei", "TWD", "TWSE", "TAIEX total return")


MARKET_ADAPTERS: Mapping[MarketCode, MarketAdapter] = {
    adapter.code: adapter
    for adapter in (
        A_SHARE_MARKET_ADAPTER,
        HONG_KONG_MARKET_ADAPTER,
        US_MARKET_ADAPTER,
        JAPAN_MARKET_ADAPTER,
        KOREA_MARKET_ADAPTER,
        TAIWAN_MARKET_ADAPTER,
    )
}

_MARKET_ALIASES = {
    "CN": MarketCode.CN,
    "A": MarketCode.CN,
    "A_SHARE": MarketCode.CN,
    "ASHARE": MarketCode.CN,
    "HK": MarketCode.HK,
    "US": MarketCode.US,
    "JP": MarketCode.JP,
    "KR": MarketCode.KR,
    "TW": MarketCode.TW,
    "A股": MarketCode.CN,
    "港股": MarketCode.HK,
    "美股": MarketCode.US,
    "日股": MarketCode.JP,
    "韩股": MarketCode.KR,
    "台股": MarketCode.TW,
}


def get_market_adapter(market: MarketCode | str) -> MarketAdapter:
    if isinstance(market, MarketCode):
        return MARKET_ADAPTERS[market]
    normalized = str(market or "").strip().upper()
    code = _MARKET_ALIASES.get(normalized)
    if code is None:
        raise KeyError("unknown market: %r" % market)
    return MARKET_ADAPTERS[code]


def market_capability_matrix() -> dict[str, dict[str, Any]]:
    return {code.value: adapter.capability_matrix() for code, adapter in MARKET_ADAPTERS.items()}


__all__ = [
    "A_SHARE_MARKET_ADAPTER",
    "AutomaticPushEligibility",
    "HONG_KONG_MARKET_ADAPTER",
    "InstrumentNormalizationError",
    "JAPAN_MARKET_ADAPTER",
    "KOREA_MARKET_ADAPTER",
    "MARKET_ADAPTERS",
    "MarketAdapter",
    "MarketCode",
    "ProviderCapability",
    "ProviderHealth",
    "ProviderStatus",
    "TAIWAN_MARKET_ADAPTER",
    "TradingCalendar",
    "WeekdayTradingCalendar",
    "US_MARKET_ADAPTER",
    "get_market_adapter",
    "market_capability_matrix",
]
