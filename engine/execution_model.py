"""Versioned execution and data contracts shared by backtest consumers.

The project has more than one historical backtest entry point.  They may keep
their public configuration shapes, but the economic assumptions and audit
metadata must come from this module so a decision validator cannot silently
invent a second execution model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Mapping


@dataclass(frozen=True)
class ExecutionCostModelVersion:
    """A complete, serializable cost and slippage assumption set."""

    version: str = "generic-assumption-v1"
    commission_rate: float = 0.0003
    stamp_tax_rate: float = 0.001
    buy_slippage: float = 0.002
    sell_slippage: float = 0.002
    min_commission: float = 5.0
    notional_assumption: float = 100_000.0
    currency: str = "CNY"
    transfer_fee_rate: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("execution cost model version cannot be empty")
        for name in (
            "commission_rate",
            "stamp_tax_rate",
            "buy_slippage",
            "sell_slippage",
            "min_commission",
            "notional_assumption",
            "transfer_fee_rate",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be a finite non-negative number")
        if self.notional_assumption <= 0:
            raise ValueError("notional_assumption must be positive")

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "commission_rate": self.commission_rate,
            "stamp_tax_rate": self.stamp_tax_rate,
            "buy_slippage": self.buy_slippage,
            "sell_slippage": self.sell_slippage,
            "min_commission": self.min_commission,
            "notional_assumption": self.notional_assumption,
            "currency": self.currency,
            "transfer_fee_rate": self.transfer_fee_rate,
        }

    def with_version(self, version: str) -> "ExecutionCostModelVersion":
        return replace(self, version=str(version or self.version))

    def _validate_transaction(self, reference_price: float, shares: float) -> tuple[float, float]:
        price = float(reference_price)
        quantity = float(shares)
        if not math.isfinite(price) or price <= 0:
            raise ValueError("execution reference price must be positive and finite")
        if not math.isfinite(quantity) or quantity <= 0:
            raise ValueError("execution shares must be positive and finite")
        return price, quantity

    def buy_fill(self, reference_price: float, shares: float) -> "ExecutionFill":
        """Calculate a buy fill from a reference/open price.

        All backtest consumers use this projection instead of reimplementing
        fee, slippage and minimum-commission arithmetic locally.
        """

        price, quantity = self._validate_transaction(reference_price, shares)
        fill_price = price * (1.0 + self.buy_slippage)
        gross = fill_price * quantity
        commission = max(gross * self.commission_rate, self.min_commission)
        transfer_fee = gross * self.transfer_fee_rate
        return ExecutionFill(
            side="buy",
            reference_price=price,
            fill_price=fill_price,
            shares=quantity,
            gross=gross,
            commission=commission,
            stamp_tax=0.0,
            cash_delta=gross + commission + transfer_fee,
            transfer_fee=transfer_fee,
        )

    def sell_fill(self, reference_price: float, shares: float) -> "ExecutionFill":
        """Calculate a sell fill from a reference/open or close price."""

        price, quantity = self._validate_transaction(reference_price, shares)
        fill_price = price * (1.0 - self.sell_slippage)
        gross = fill_price * quantity
        commission = max(gross * self.commission_rate, self.min_commission)
        stamp_tax = gross * self.stamp_tax_rate
        transfer_fee = gross * self.transfer_fee_rate
        return ExecutionFill(
            side="sell",
            reference_price=price,
            fill_price=fill_price,
            shares=quantity,
            gross=gross,
            commission=commission,
            stamp_tax=stamp_tax,
            cash_delta=gross - commission - stamp_tax - transfer_fee,
            transfer_fee=transfer_fee,
        )

    def round_trip_return(self, opening_price: float, closing_price: float) -> float:
        """Return a one-bar long trade result using next-open execution.

        The calculation is deliberately explicit about both sides of the
        trade and the minimum commission.  It is used by validation only; the
        live/paper engines still own order matching and position state.
        """

        opening = float(opening_price)
        closing = float(closing_price)
        if not math.isfinite(opening) or not math.isfinite(closing) or opening <= 0 or closing <= 0:
            raise ValueError("execution prices must be positive finite numbers")
        notional = self.notional_assumption
        buy = self.buy_fill(opening, notional / (opening * (1.0 + self.buy_slippage)))
        sell = self.sell_fill(closing, buy.shares)
        return sell.cash_delta / buy.cash_delta - 1.0


@dataclass(frozen=True)
class ExecutionFill:
    """One deterministic transaction projection shared by backtest engines."""

    side: str
    reference_price: float
    fill_price: float
    shares: float
    gross: float
    commission: float
    stamp_tax: float
    cash_delta: float
    transfer_fee: float = 0.0


DEFAULT_A_SHARE_EXECUTION_COST_MODEL = ExecutionCostModelVersion()


@dataclass(frozen=True)
class ExecutionDataContract:
    """Market-data and execution semantics frozen into a validation result."""

    market: str = "CN"
    timezone: str = "Asia/Shanghai"
    exchange_calendar: str = "SSE/SZSE"
    calendar_name: str = "weekday_fallback"
    calendar_source: str = "local_weekday_fallback"
    execution_rule: str = "signal_at_close_then_next_tradable_bar_open"
    tradability_rule: str = "complete_bar_positive_open_close_volume; no_fill_on_halt_limit_or_missing_quote"
    adjustment_policy: str = "provider_versioned_adjustment_required"
    corporate_actions_policy: str = "provider_corporate_action_snapshot_required"
    delisting_policy: str = "retain_last_available_quote_and_mark_delisted"
    missing_data_policy: str = "skip_missing_bars_and_never_fill_zero"
    deferred_execution_policy: str = "retain_order_until_next_tradable_bar; never_fill_missing_quote"
    coverage_policy: str = "observed_trading_days_over_expected_calendar_days"
    benchmark: str = "CSI 300 total return"
    benchmark_source: str = "explicit_total_return_series_required"
    benchmark_value_field: str = "total_return_index"
    benchmark_instrument: str | None = None
    annualization_days: int = 252
    source: str = "default_assumption"
    cost_model: ExecutionCostModelVersion = DEFAULT_A_SHARE_EXECUTION_COST_MODEL

    def as_dict(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "timezone": self.timezone,
            "exchange_calendar": self.exchange_calendar,
            "calendar_name": self.calendar_name,
            "calendar_source": self.calendar_source,
            "execution_rule": self.execution_rule,
            "tradability_rule": self.tradability_rule,
            "adjustment_policy": self.adjustment_policy,
            "corporate_actions_policy": self.corporate_actions_policy,
            "delisting_policy": self.delisting_policy,
            "missing_data_policy": self.missing_data_policy,
            "deferred_execution_policy": self.deferred_execution_policy,
            "coverage_policy": self.coverage_policy,
            "benchmark": self.benchmark,
            "benchmark_source": self.benchmark_source,
            "benchmark_value_field": self.benchmark_value_field,
            "benchmark_instrument": self.benchmark_instrument,
            "annualization_days": self.annualization_days,
            "source": self.source,
            "cost_model": self.cost_model.as_dict(),
        }


DEFAULT_A_SHARE_EXECUTION_CONTRACT = ExecutionDataContract()


def resolve_execution_cost_model(
    value: ExecutionCostModelVersion | Mapping[str, Any] | None = None,
    *,
    version: str | None = None,
    legacy_cost_bps: float | None = None,
) -> ExecutionCostModelVersion:
    """Resolve the shared model while keeping the old flat-bps API usable."""

    if isinstance(value, ExecutionCostModelVersion):
        model = value
    elif isinstance(value, Mapping):
        model = replace(
            DEFAULT_A_SHARE_EXECUTION_COST_MODEL,
            version=str(value.get("version") or DEFAULT_A_SHARE_EXECUTION_COST_MODEL.version),
            commission_rate=float(value.get("commission_rate", value.get("commission", DEFAULT_A_SHARE_EXECUTION_COST_MODEL.commission_rate))),
            stamp_tax_rate=float(value.get("stamp_tax_rate", value.get("stamp_tax", DEFAULT_A_SHARE_EXECUTION_COST_MODEL.stamp_tax_rate))),
            buy_slippage=float(value.get("buy_slippage", value.get("slippage", DEFAULT_A_SHARE_EXECUTION_COST_MODEL.buy_slippage))),
            sell_slippage=float(value.get("sell_slippage", value.get("slippage", DEFAULT_A_SHARE_EXECUTION_COST_MODEL.sell_slippage))),
            min_commission=float(value.get("min_commission", DEFAULT_A_SHARE_EXECUTION_COST_MODEL.min_commission)),
            notional_assumption=float(value.get("notional_assumption", DEFAULT_A_SHARE_EXECUTION_COST_MODEL.notional_assumption)),
            currency=str(value.get("currency") or DEFAULT_A_SHARE_EXECUTION_COST_MODEL.currency),
            transfer_fee_rate=float(value.get("transfer_fee_rate", value.get("transfer_fee", DEFAULT_A_SHARE_EXECUTION_COST_MODEL.transfer_fee_rate))),
        )
    else:
        model = DEFAULT_A_SHARE_EXECUTION_COST_MODEL
    legacy_applied = False
    if legacy_cost_bps is not None:
        # Older callers exposed one flat cost number.  Keep that explicit and
        # versioned instead of silently mixing it with the canonical model.
        try:
            legacy_bps = float(legacy_cost_bps)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("legacy_cost_bps must be finite and non-negative") from exc
        if not math.isfinite(legacy_bps) or legacy_bps < 0:
            raise ValueError("legacy_cost_bps must be finite and non-negative")
        rate = legacy_bps / 10_000.0
        legacy_version = version if version and version != DEFAULT_A_SHARE_EXECUTION_COST_MODEL.version else "legacy-flat-bps-v1"
        model = replace(
            model,
            version=legacy_version,
            commission_rate=rate,
            stamp_tax_rate=0.0,
            buy_slippage=0.0,
            sell_slippage=0.0,
            transfer_fee_rate=0.0,
        )
        legacy_applied = True
    if version and not legacy_applied:
        model = model.with_version(version)
    return model


def resolve_execution_contract(
    value: ExecutionDataContract | Mapping[str, Any] | None = None,
    *,
    cost_model: ExecutionCostModelVersion | None = None,
) -> ExecutionDataContract:
    """Coerce a market adapter projection into a frozen contract."""

    if isinstance(value, ExecutionDataContract):
        return replace(value, cost_model=cost_model or value.cost_model)
    if isinstance(value, Mapping):
        return ExecutionDataContract(
            market=str(value.get("market") or "CN"),
            timezone=str(value.get("timezone") or "Asia/Shanghai"),
            exchange_calendar=str(value.get("exchange_calendar") or "SSE/SZSE"),
            calendar_name=str(value.get("calendar_name") or value.get("calendar") or DEFAULT_A_SHARE_EXECUTION_CONTRACT.calendar_name),
            calendar_source=str(value.get("calendar_source") or DEFAULT_A_SHARE_EXECUTION_CONTRACT.calendar_source),
            execution_rule=str(value.get("execution_rule") or DEFAULT_A_SHARE_EXECUTION_CONTRACT.execution_rule),
            tradability_rule=str(value.get("tradability_rule") or DEFAULT_A_SHARE_EXECUTION_CONTRACT.tradability_rule),
            adjustment_policy=str(value.get("adjustment_policy") or DEFAULT_A_SHARE_EXECUTION_CONTRACT.adjustment_policy),
            corporate_actions_policy=str(value.get("corporate_actions_policy") or DEFAULT_A_SHARE_EXECUTION_CONTRACT.corporate_actions_policy),
            delisting_policy=str(value.get("delisting_policy") or DEFAULT_A_SHARE_EXECUTION_CONTRACT.delisting_policy),
            missing_data_policy=str(value.get("missing_data_policy") or DEFAULT_A_SHARE_EXECUTION_CONTRACT.missing_data_policy),
            deferred_execution_policy=str(value.get("deferred_execution_policy") or DEFAULT_A_SHARE_EXECUTION_CONTRACT.deferred_execution_policy),
            coverage_policy=str(value.get("coverage_policy") or DEFAULT_A_SHARE_EXECUTION_CONTRACT.coverage_policy),
            benchmark=str(value.get("benchmark") or DEFAULT_A_SHARE_EXECUTION_CONTRACT.benchmark),
            benchmark_source=str(value.get("benchmark_source") or DEFAULT_A_SHARE_EXECUTION_CONTRACT.benchmark_source),
            benchmark_value_field=str(value.get("benchmark_value_field") or DEFAULT_A_SHARE_EXECUTION_CONTRACT.benchmark_value_field),
            benchmark_instrument=(str(value["benchmark_instrument"]) if value.get("benchmark_instrument") else None),
            annualization_days=int(value.get("annualization_days") or DEFAULT_A_SHARE_EXECUTION_CONTRACT.annualization_days),
            source=str(value.get("source") or "market_adapter"),
            cost_model=cost_model or resolve_execution_cost_model(value.get("cost_model")),
        )
    return replace(DEFAULT_A_SHARE_EXECUTION_CONTRACT, cost_model=cost_model or DEFAULT_A_SHARE_EXECUTION_COST_MODEL)


__all__ = [
    "DEFAULT_A_SHARE_EXECUTION_CONTRACT",
    "DEFAULT_A_SHARE_EXECUTION_COST_MODEL",
    "ExecutionCostModelVersion",
    "ExecutionDataContract",
    "ExecutionFill",
    "resolve_execution_contract",
    "resolve_execution_cost_model",
]
