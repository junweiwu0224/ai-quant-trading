"""Deterministic local decision runtime.

This runtime consumes the repository's local daily data only.  It intentionally
reports the current provider as manual-only until the qualified target sources
are integrated, so a useful preview cannot accidentally become an auto-push.
"""

from __future__ import annotations

import os
import math
import inspect
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Mapping

from config.settings import DB_DIR
from data.storage.storage import DataStorage

from .domain import confirm_completed_bars, evaluate_decision
from .data_quality import parse_bar_time, validate_bars
from .market import get_market_adapter
from .strategies import builtin_strategy_outputs
from .store import DecisionStore, content_hash, scheduled_run_context
from .validation import walk_forward_validate


_VALIDATION_DEFAULTS: dict[str, Any] = {
    "cost_bps": 10.0,
    "min_history_months": 54,
    "train_months": 24,
    "out_of_sample_months": 6,
    "step_months": 6,
    "required_windows": 3,
    "max_drawdown": 0.25,
    "max_annualized_turnover": 12.0,
}

# The validator eventually constructs ``datetime.date`` values from these
# durations.  Keep malformed or unbounded input away from that arithmetic;
# an accepted value can still fail normal historical-data gates later.
_VALIDATION_INT_RANGES: dict[str, tuple[int, int]] = {
    "min_history_months": (1, 1_200),
    "train_months": (1, 1_200),
    "out_of_sample_months": (1, 1_200),
    "step_months": (1, 1_200),
    "required_windows": (1, 1_000),
}
_VALIDATION_FLOAT_RANGES: dict[str, tuple[float, float]] = {
    "cost_bps": (0.0, 10_000.0),
    "max_drawdown": (0.0, 1.0),
    "max_annualized_turnover": (0.0, 1_000.0),
}
_VALIDATION_CONFIG_INVALID = "validation_config_invalid"
_PROVIDER_NOT_CONNECTED = "provider_not_connected"
_MARKET_DATA_UNAVAILABLE = "market_data_unavailable"


def _invalid_validation_issue(field: str, reason: str, fallback: Any) -> dict[str, Any]:
    return {"field": field, "reason": reason, "fallback": fallback}


def _parse_validation_int(value: Any, *, minimum: int, maximum: int) -> tuple[int | None, str | None]:
    if isinstance(value, bool):
        return None, "boolean_not_integer"
    if isinstance(value, int):
        number = value
    elif isinstance(value, float):
        if not math.isfinite(value):
            return None, "not_finite"
        if not value.is_integer():
            return None, "not_integral"
        number = int(value)
    elif isinstance(value, str):
        try:
            number = int(value.strip(), 10)
        except (TypeError, ValueError, OverflowError):
            return None, "not_an_integer"
    else:
        return None, "not_an_integer"
    if number < minimum or number > maximum:
        return None, "out_of_range"
    return number, None


def _parse_validation_float(value: Any, *, minimum: float, maximum: float) -> tuple[float | None, str | None]:
    if isinstance(value, bool):
        return None, "boolean_not_number"
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None, "not_a_number"
    if not math.isfinite(number):
        return None, "not_finite"
    if number < minimum or number > maximum:
        return None, "out_of_range"
    return number, None


def _read_validation_config(raw: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Resolve validation settings without allowing malformed config to pass.

    Missing fields retain the historical defaults.  A supplied field that is
    malformed is also resolved to its default so validation can still produce
    an auditable result, but the issue is returned to make the version
    ineligible until its configuration is corrected.
    """

    issues: list[dict[str, Any]] = []
    if raw is None:
        source: Mapping[str, Any] = {}
    elif isinstance(raw, Mapping):
        source = raw
    else:
        source = {}
        issues.append(_invalid_validation_issue("validation", "expected_mapping", "defaults"))

    resolved: dict[str, Any] = {}
    for field, (minimum, maximum) in _VALIDATION_INT_RANGES.items():
        if field not in source:
            resolved[field] = _VALIDATION_DEFAULTS[field]
            continue
        value, reason = _parse_validation_int(source[field], minimum=minimum, maximum=maximum)
        if reason:
            resolved[field] = _VALIDATION_DEFAULTS[field]
            issues.append(_invalid_validation_issue(field, reason, _VALIDATION_DEFAULTS[field]))
        else:
            resolved[field] = value

    for field, (minimum, maximum) in _VALIDATION_FLOAT_RANGES.items():
        if field not in source:
            resolved[field] = _VALIDATION_DEFAULTS[field]
            continue
        value, reason = _parse_validation_float(source[field], minimum=minimum, maximum=maximum)
        if reason:
            resolved[field] = _VALIDATION_DEFAULTS[field]
            issues.append(_invalid_validation_issue(field, reason, _VALIDATION_DEFAULTS[field]))
        else:
            resolved[field] = value

    resolved["cost_model_version"] = str(source.get("cost_model_version") or "generic-assumption-v1")

    raw_survivorship = source.get("survivorship_bias_control", False)
    if raw_survivorship is None:
        resolved["survivorship_bias_control"] = False
    elif isinstance(raw_survivorship, bool):
        resolved["survivorship_bias_control"] = raw_survivorship
    elif isinstance(raw_survivorship, str) and raw_survivorship.strip().lower() in {"true", "1", "yes"}:
        resolved["survivorship_bias_control"] = True
    elif isinstance(raw_survivorship, str) and raw_survivorship.strip().lower() in {"false", "0", "no"}:
        resolved["survivorship_bias_control"] = False
    else:
        resolved["survivorship_bias_control"] = False
        issues.append(_invalid_validation_issue("survivorship_bias_control", "not_a_boolean", False))

    raw_universe_ref = source.get("universe_snapshot_ref")
    if raw_universe_ref is None or raw_universe_ref == "":
        resolved["universe_snapshot_ref"] = None
    elif isinstance(raw_universe_ref, str):
        resolved["universe_snapshot_ref"] = raw_universe_ref.strip() or None
    else:
        resolved["universe_snapshot_ref"] = None
        issues.append(_invalid_validation_issue("universe_snapshot_ref", "not_a_string", None))

    raw_benchmark_symbol = source.get("benchmark_symbol")
    if raw_benchmark_symbol is None or raw_benchmark_symbol == "":
        resolved["benchmark_symbol"] = None
    elif isinstance(raw_benchmark_symbol, str):
        resolved["benchmark_symbol"] = raw_benchmark_symbol.strip() or None
    else:
        resolved["benchmark_symbol"] = None
        issues.append(_invalid_validation_issue("benchmark_symbol", "not_a_string", None))

    return resolved, issues


def _date_text(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value or "")


def _strategy_outputs(bars: list[Mapping[str, Any]], strategy_names: set[str]) -> list[dict[str, Any]]:
    return builtin_strategy_outputs(bars, strategy_names)


def _bar_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.fromisoformat(str(value)[:10]).replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _default_benchmark_symbol(market: str) -> str | None:
    """Return only an identifier we can resolve through a real adapter.

    The local quant database currently stores security bars, not total-return
    index bars.  Keeping the identifier in the frozen contract is useful for a
    future provider, while the absence of a loader remains a hard validation
    gate instead of becoming a price-index approximation.
    """

    return {"CN": "000300"}.get(str(market or "CN").upper())


@dataclass
class DecisionRuntime:
    store: DecisionStore
    storage: DataStorage
    workspace_automation_enabled: Callable[[str], bool] | None = None
    benchmark_history_loader: Callable[[str, str], Mapping[str, Any] | None] | None = None
    intraday_bars_loader: Callable[..., Mapping[str, Any] | None] | None = None
    outbox: Any | None = None
    worker_owner_id: str = ""
    worker_fence_check: Callable[[], None] | None = None
    worker_fence_token_provider: Callable[[], str] | None = None

    def bind_worker(
        self,
        owner_id: str,
        fence_check: Callable[[], None],
        fence_token_provider: Callable[[], str] | None = None,
    ) -> None:
        """Bind execution to the current Worker lease without changing reads.

        Dashboard callers leave this unbound and can still perform manual,
        read-only analysis.  Worker callbacks use the same runtime but must
        pass the lease fence before every durable fact is written.
        """

        self.worker_owner_id = str(owner_id or "")
        self.worker_fence_check = fence_check
        self.worker_fence_token_provider = fence_token_provider

    def _assert_worker_fence(self, override: Callable[[], None] | None = None) -> None:
        checker = override or self.worker_fence_check
        if checker is not None:
            checker()

    def _freeze_previous_action(self, membership_id: str) -> str | None:
        """Capture the completed action before an input snapshot is sealed."""

        state_getter = getattr(self.store, "get_member_state", None)
        if callable(state_getter):
            state = state_getter(membership_id)
            if isinstance(state, Mapping) and state.get("last_valid_action"):
                return str(state["last_valid_action"])

        getter = getattr(self.store, "latest_decision", None)
        if not callable(getter):
            return None
        # Manual analysis and previews are deliberately non-authoritative.  A
        # completed manual run must not become the input to a later automatic
        # run merely because it happens to be the newest decision row.
        try:
            previous = getter(membership_id, automatic_only=True)
        except TypeError:
            # Keep small test doubles and older compatible stores usable while
            # the production store learns the stricter query contract.
            previous = getter(membership_id)
        if not isinstance(previous, Mapping):
            return None
        action = previous.get("action")
        return str(action) if action is not None else None

    @staticmethod
    def _invalid_persists_to_next_trading_day(
        adapter: Any,
        invalid_since: str | None,
        current_trade_date: str | None,
    ) -> bool:
        if not invalid_since or not current_trade_date:
            return False
        try:
            start = date.fromisoformat(str(invalid_since)[:10])
            current = date.fromisoformat(str(current_trade_date)[:10])
        except ValueError:
            return False
        if current <= start:
            return False
        next_trade = adapter.canonical.next_trading_day(start)
        return next_trade is not None and next_trade <= current

    @classmethod
    def from_environment(cls) -> "DecisionRuntime":
        from dashboard.account_store import account_store

        def workspace_automation_enabled(workspace_id: str) -> bool:
            workspace = account_store.get_workspace(workspace_id)
            settings = (workspace or {}).get("settings", {})
            return bool(settings.get("decision_worker_enabled")) and bool(settings.get("decision_auto_push_enabled"))

        return cls(
            DecisionStore(DB_DIR / "decisions.db"),
            DataStorage(),
            workspace_automation_enabled=workspace_automation_enabled,
        )

    def _execution_contract(self, market: str, *, benchmark_symbol: str | None = None) -> dict[str, Any]:
        """Freeze the canonical market semantics into each validation result."""

        adapter = get_market_adapter(market).canonical
        return {
            **adapter.capability_matrix(),
            "source": "market_adapter",
            "execution_rule": "signal_at_close_then_next_tradable_bar_open",
            "tradability_rule": "complete_bar_positive_open_close_volume; no_fill_on_halt_limit_or_missing_quote",
            "delisting_policy": "retain_last_available_quote_and_mark_delisted",
            "missing_data_policy": "skip_missing_bars_and_never_fill_zero",
            "benchmark_source": "explicit_total_return_series_required",
            "benchmark_value_field": "total_return_index",
            "benchmark_instrument": benchmark_symbol or _default_benchmark_symbol(market),
        }

    def _load_benchmark_history(
        self,
        market: str,
        benchmark_symbol: str | None,
    ) -> Mapping[str, Any] | None:
        """Load only an explicitly supplied total-return benchmark adapter.

        ``DataStorage.get_stock_daily`` is intentionally not used as a
        benchmark fallback: its ``close`` field is a price series and does not
        prove dividends or other corporate actions were included.
        """

        if not benchmark_symbol or self.benchmark_history_loader is None:
            return None
        loaded = self.benchmark_history_loader(str(market), str(benchmark_symbol))
        return loaded if isinstance(loaded, Mapping) else None

    def _ensure_version(self, workspace_id: str, portfolio_id: str) -> dict[str, Any]:
        version = self.store.get_current_version(workspace_id, portfolio_id)
        return version or self.store.create_version(workspace_id, portfolio_id, {})

    def _build_market_data_unavailable_snapshot(
        self,
        workspace_id: str,
        portfolio_id: str,
        portfolio: Mapping[str, Any],
        version: Mapping[str, Any],
        members: list[Mapping[str, Any]],
        strategy_names: set[str],
        adapter: Any,
        previous_actions: Mapping[str, str | None],
        *,
        fence_check: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        """Freeze an explicit non-CN data boundary without using A-share storage.

        ``DataStorage`` is an A-share ``stock_daily`` adapter.  Non-CN manual
        research remains usable as an auditable unavailable result, but it must
        never turn that table into cross-market history.
        """

        provider_health = {
            provider.name: {
                "healthy": False,
                "validated": False,
                "completed_bars": False,
                "updated_at": None,
                "coverage_pct": 0.0,
                "field_sources": {},
                "status": _PROVIDER_NOT_CONNECTED,
                "reason": _MARKET_DATA_UNAVAILABLE,
                "declared_status": provider.status.value,
            }
            for provider in adapter.canonical.providers
        }
        provider_evidence = {
            "provider": _PROVIDER_NOT_CONNECTED,
            "request_hash": None,
            "response_hash": None,
            "normalized_sequence_hash": content_hash([]),
            "collection_watermark": None,
            "collected_at": None,
            "cache_age_seconds": None,
            "cache_age_status": "not_applicable",
            "replayable_copy": False,
            "status": "not_collected",
        }
        items = [
            {
                "membership_id": member["id"],
                "symbol": member["symbol"],
                "name": member.get("name", ""),
                "bars": [],
                "latest_bar": "",
                "coverage": 0,
                "coverage_pct": 0.0,
                "stale": False,
                "quality_status": "invalid",
                "quality_reason": _MARKET_DATA_UNAVAILABLE,
                "previous_action": previous_actions.get(str(member["id"])),
                "strategy_outputs": _strategy_outputs([], strategy_names),
            }
            for member in members
        ]
        payload = {
            "market": portfolio["market"],
            "portfolio_id": portfolio_id,
            "portfolio_version_id": version["id"],
            "members": items,
            "captured_at": "",
            "provider": "none",
            "provider_status": _PROVIDER_NOT_CONNECTED,
            "updated_at": "",
            "coverage_pct": 0.0,
            "field_sources": {},
            "provider_health": provider_health,
            "provider_evidence": provider_evidence,
            "stale": False,
            "quality_status": _MARKET_DATA_UNAVAILABLE,
            "market_data_status": _MARKET_DATA_UNAVAILABLE,
            "fallback_reason": _MARKET_DATA_UNAVAILABLE,
            "manual_research": bool(adapter.daily_research),
            "adapter": adapter.capabilities(),
        }
        self._assert_worker_fence(fence_check)
        return self.store.create_snapshot(
            workspace_id,
            version["id"],
            payload,
            _PROVIDER_NOT_CONNECTED,
            _MARKET_DATA_UNAVAILABLE,
        )

    def build_snapshot(
        self,
        workspace_id: str,
        portfolio_id: str,
        *,
        fence_check: Callable[[], None] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        portfolio = self.store.get_portfolio(workspace_id, portfolio_id)
        if not portfolio:
            raise KeyError("portfolio_not_found")
        version = self._ensure_version(workspace_id, portfolio_id)
        # Disabled memberships remain visible in settings and history, but
        # cannot silently participate in a new snapshot or qualify automation.
        members = [
            member
            for member in self.store.list_members(workspace_id, portfolio_id)
            if bool(member.get("enabled", True))
        ]
        # The prior action is part of the input boundary.  Reading it later
        # during evaluation would make the same snapshot depend on mutable
        # database state and would break replay determinism.
        previous_actions = {
            str(member["id"]): self._freeze_previous_action(str(member["id"]))
            for member in members
        }
        strategy_config = version.get("config", {}).get("strategies", [])
        names = {str(item.get("strategy_name")) for item in strategy_config if item.get("enabled", True)}
        adapter = get_market_adapter(portfolio["market"])
        if adapter.market != "CN":
            return portfolio, version, self._build_market_data_unavailable_snapshot(
                workspace_id,
                portfolio_id,
                portfolio,
                version,
                members,
                names,
                adapter,
                previous_actions,
                fence_check=fence_check,
            )
        items: list[dict[str, Any]] = []
        invalid = 0
        stale_count = 0
        member_states: dict[str, Mapping[str, Any]] = {}
        state_getter = getattr(self.store, "get_member_state", None)
        if callable(state_getter):
            member_states = {
                str(member["id"]): (state_getter(str(member["id"])) or {})
                for member in members
            }
        field_sources = {
            "date": "local_quant_db",
            "open": "local_quant_db",
            "high": "local_quant_db",
            "low": "local_quant_db",
            "close": "local_quant_db",
            "volume": "local_quant_db",
        }
        stale_after_days = max(1, int(os.getenv("DECISION_DAILY_STALE_DAYS", "7")))
        for member in members:
            frame = self.storage.get_stock_daily(member["symbol"])
            bars: list[dict[str, Any]] = []
            if not frame.empty:
                for _, row in frame.tail(180).iterrows():
                    bar: dict[str, Any] = {}
                    for key in ("date", "open", "high", "low", "close", "volume", "amount"):
                        value = row[key] if key in row else None
                        if key == "date":
                            bar[key] = _date_text(value) if value is not None else None
                        elif value is None:
                            bar[key] = None
                        else:
                            try:
                                number = float(value)
                            except (TypeError, ValueError, OverflowError):
                                bar[key] = None
                            else:
                                bar[key] = number if math.isfinite(number) else None
                    bars.append(bar)
            quality_result = validate_bars(bars, minimum_bars=30)
            latest = bars[-1].get("date") if bars else ""
            latest_at = _bar_datetime(quality_result.latest_bar or latest)
            current_trade_date = latest_at.date().isoformat() if latest_at else None
            state = member_states.get(str(member["id"]), {})
            invalid_persisted = self._invalid_persists_to_next_trading_day(
                adapter,
                state.get("invalid_since_trade_date"),
                current_trade_date,
            )
            quality = "ok" if quality_result.valid else "invalid"
            stale = bool(latest_at and datetime.now(timezone.utc) - latest_at > timedelta(days=stale_after_days))
            if quality != "ok":
                invalid += 1
            if stale:
                stale_count += 1
            item_quality = "invalid" if quality != "ok" else "stale" if stale else "ok"
            items.append({
                "membership_id": member["id"],
                "symbol": member["symbol"],
                "name": member.get("name", ""),
                "bars": bars,
                "latest_bar": latest,
                "coverage": quality_result.valid_bar_count,
                "coverage_pct": min(100.0, round(quality_result.valid_bar_count / 30 * 100, 2)),
                "stale": stale,
                "quality_status": item_quality,
                "quality_reasons": list(quality_result.reasons),
                "field_coverage": quality_result.field_coverage,
                "previous_action": previous_actions.get(str(member["id"])),
                "invalid_since_trade_date": state.get("invalid_since_trade_date"),
                "invalid_persisted": invalid_persisted,
                "strategy_outputs": _strategy_outputs(bars, names) if quality_result.valid else [],
            })
        # Wall-clock capture time belongs to the immutable snapshot row's
        # ``created_at`` metadata.  Keeping it out of the payload hash makes
        # the same completed-bar input produce the same snapshot/run key after
        # a Worker restart instead of manufacturing a new run every poll.
        observed_dates = [_bar_datetime(item.get("latest_bar")) for item in items if item.get("latest_bar")]
        observed_at = max((value for value in observed_dates if value is not None), default=None)
        captured_at = observed_at.isoformat(timespec="seconds") if observed_at else ""
        provider_health = {
            "local_quant_db": {
                "healthy": bool(items),
                "validated": False,
                "completed_bars": False,
                "quality_validated": not invalid and bool(items),
                "updated_at": captured_at,
                "coverage_pct": round((sum(1 for item in items if item["coverage"] >= 30) / len(items)) * 100, 2) if items else 0.0,
                "field_sources": dict(field_sources),
                "field_coverage": {
                    field: round(
                        sum(float(item.get("field_coverage", {}).get(field, 0.0)) for item in items) / max(1, len(items)),
                        2,
                    )
                    for field in field_sources
                },
            }
        }
        normalized_sequences = [
            {
                "symbol": str(item.get("symbol") or ""),
                "bars": list(item.get("bars") or []),
            }
            for item in items
        ]
        request_descriptor = {
            "provider": "local_quant_db",
            "market": str(portfolio.get("market") or "CN"),
            "symbols": sorted(str(item.get("symbol") or "") for item in items),
            "fields": sorted(field_sources),
            "window_bars": 180,
            "normalization": "iso_dates_finite_numeric_values_sorted_members",
        }
        response_descriptor = {
            "provider": "local_quant_db",
            "sequences": normalized_sequences,
        }
        request_hash = content_hash(request_descriptor)
        response_hash = content_hash(response_descriptor)
        provider_evidence = {
            "provider": "local_quant_db",
            "request_hash": request_hash,
            "response_hash": response_hash,
            "normalized_sequence_hash": content_hash(normalized_sequences),
            # The legacy store exposes the latest bar timestamp but not the
            # provider collection timestamp. Keep that limitation explicit.
            "collection_watermark": captured_at or None,
            "collected_at": captured_at or None,
            "cache_age_seconds": None,
            "cache_age_status": "not_reported_by_legacy_store",
            "replayable_copy": True,
            "status": "normalized_local_snapshot",
        }
        provider_health["local_quant_db"].update(
            {
                "request_hash": request_hash,
                "response_hash": response_hash,
                "normalized_sequence_hash": provider_evidence["normalized_sequence_hash"],
                "collection_watermark": provider_evidence["collection_watermark"],
                "collected_at": provider_evidence["collected_at"],
                "cache_age_seconds": None,
                "cache_age_status": provider_evidence["cache_age_status"],
            }
        )
        payload = {
            "market": portfolio["market"],
            "portfolio_id": portfolio_id,
            "portfolio_version_id": version["id"],
            "members": items,
            "captured_at": captured_at,
            "provider": "local_quant_db",
            "provider_status": "legacy_manual",
            "updated_at": captured_at,
            "coverage_pct": round((sum(1 for item in items if item["coverage"] >= 30) / len(items)) * 100, 2) if items else 0.0,
            "field_sources": field_sources,
            "provider_health": provider_health,
            "provider_evidence": provider_evidence,
            "stale": bool(stale_count),
            "fallback_reason": "目标 provider 尚未接入；当前快照仅用于手动研究",
            "adapter": adapter.capabilities(),
        }
        snapshot_quality = "invalid" if invalid or not members else "stale" if stale_count else "ok"
        self._assert_worker_fence(fence_check)
        snapshot = self.store.create_snapshot(workspace_id, version["id"], payload, "local_quant_db", snapshot_quality)
        self._assert_worker_fence(fence_check)
        return portfolio, version, snapshot

    def run(
        self,
        workspace_id: str,
        portfolio_id: str,
        *,
        trigger: str = "manual",
        report_type: str = "decision",
        run_key: str | None = None,
        fence_check: Callable[[], None] | None = None,
        snapshot_override: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._assert_worker_fence(fence_check)
        requested_run_key = str(run_key or "").strip()

        def result_for_existing(existing_run: Mapping[str, Any], existing_snapshot: Mapping[str, Any], existing_version: Mapping[str, Any], existing_portfolio: Mapping[str, Any]) -> dict[str, Any]:
            existing_decisions = self.store.list_decisions(str(existing_run["id"]))
            if self._stateful_trigger(str(existing_run.get("trigger") or "")) and existing_run.get("status") == "completed":
                # A crash can occur after the run is completed but before the
                # derived member lifecycle row is written.  Reconcile it from
                # the immutable run on replay; this is idempotent and keeps
                # manual/preview runs out of the automatic state machine.
                self._persist_member_states(existing_run, existing_snapshot, existing_decisions, fence_check=fence_check)
            reports = self.store.list_reports(workspace_id, str(existing_portfolio["id"]), limit=50)
            return {
                "run": dict(existing_run),
                "snapshot": dict(existing_snapshot),
                "version": dict(existing_version),
                "decisions": existing_decisions,
                "report": next((item for item in reports if item.get("decision_run_id") == existing_run["id"]), None),
            }

        # Worker commands always provide a stable key (normally command:<id>).
        # Look it up before touching mutable member state or rebuilding a
        # snapshot so a restart resumes the exact frozen input.
        existing_run = None
        run_lookup = getattr(self.store, "get_run_by_key", None)
        if requested_run_key and callable(run_lookup):
            existing_run = run_lookup(workspace_id, requested_run_key)
            if existing_run is not None:
                if (
                    existing_run.get("portfolio_id") != portfolio_id
                    or existing_run.get("trigger") != trigger
                    or existing_run.get("report_type") != report_type
                ):
                    raise ValueError("decision_run_key_conflict")
                snapshot = self.store.get_snapshot(str(existing_run["snapshot_id"]))
                version = self.store.get_version(workspace_id, str(existing_run["portfolio_version_id"]))
                portfolio = self.store.get_portfolio(workspace_id, portfolio_id)
                if not snapshot or not version or not portfolio:
                    raise RuntimeError("decision_run_reference_corrupt")
                if existing_run.get("status") == "completed":
                    return result_for_existing(existing_run, snapshot, version, portfolio)
                run = existing_run
            else:
                run = None
        else:
            run = None

        if run is None:
            portfolio = self.store.get_portfolio(workspace_id, portfolio_id)
            if not portfolio:
                raise KeyError("portfolio_not_found")
            version = self._ensure_version(workspace_id, portfolio_id)
            if snapshot_override is None:
                portfolio, version, snapshot = self.build_snapshot(workspace_id, portfolio_id, fence_check=fence_check)
            elif isinstance(snapshot_override.get("payload"), Mapping) and snapshot_override.get("id"):
                snapshot = dict(snapshot_override)
            else:
                payload = dict(snapshot_override)
                self._assert_worker_fence(fence_check)
                snapshot = self.store.create_snapshot(
                    workspace_id,
                    version["id"],
                    payload,
                    str(payload.get("provider") or "intraday_loader"),
                    str(payload.get("quality_status") or "ok"),
                )
                self._assert_worker_fence(fence_check)
            if str(snapshot.get("portfolio_version_id") or version["id"]) != str(version["id"]):
                raise ValueError("decision_snapshot_version_mismatch")
            requested_run_key = requested_run_key or f"{trigger}:{portfolio_id}:{version['id']}:{snapshot['payload_hash']}"
            self._assert_worker_fence(fence_check)
            run = self.store.create_run(workspace_id, portfolio_id, version["id"], snapshot["id"], requested_run_key, trigger, report_type)
            # Another Worker may have won the insert race after both callers
            # built an input snapshot.  Always resume the row that actually
            # owns the idempotency key rather than continuing with our local
            # snapshot.
            if run.get("snapshot_id") != snapshot.get("id") or run.get("portfolio_version_id") != version.get("id"):
                snapshot = self.store.get_snapshot(str(run["snapshot_id"]))
                version = self.store.get_version(workspace_id, str(run["portfolio_version_id"]))
                portfolio = self.store.get_portfolio(workspace_id, portfolio_id)
                if not snapshot or not version or not portfolio:
                    raise RuntimeError("decision_run_reference_corrupt")
            if run.get("status") == "completed":
                return result_for_existing(run, snapshot, version, portfolio)

        config = version.get("config", {})
        weights = {str(item.get("strategy_name")): item for item in config.get("strategies", [])}
        decisions = []
        for item in snapshot["payload"].get("members", []):
            self._assert_worker_fence(fence_check)
            quality_invalid = item.get("quality_status") == "invalid" or item.get("coverage", 0) < 30
            invalid_pending = bool(quality_invalid and not item.get("invalid_persisted") and item.get("previous_action"))
            evaluation = evaluate_decision(
                item.get("strategy_outputs", []),
                weights,
                previous_action=item.get("previous_action"),
                data_stale=item.get("quality_status") == "stale" or invalid_pending,
                data_invalid=quality_invalid and not invalid_pending,
                invalid_pending=invalid_pending,
                confirmed=bool(item.get("confirmed", trigger not in {"intraday"})),
            )
            payload = {
                "symbol": item["symbol"],
                "confirming_bar_end": item.get("latest_bar") or "",
                **evaluation.as_dict(),
            }
            decision = self.store.record_decision(run["id"], item["membership_id"], payload)
            decisions.append(decision)
        self._assert_worker_fence(fence_check)
        report = self.store.create_report(run, snapshot, version, decisions, report_type)
        self._assert_worker_fence(fence_check)
        self.store.complete_run(run["id"])
        self._persist_member_states(run, snapshot, decisions, fence_check=fence_check)
        completed_run = self.store.get_run(workspace_id, run["id"]) or run
        return {"run": completed_run, "snapshot": snapshot, "version": version, "decisions": decisions, "report": report}

    @staticmethod
    def _stateful_trigger(trigger: str) -> bool:
        """Only Worker/automatic triggers may update future state."""

        return str(trigger or "").strip() not in {"manual", "preview"}

    def _persist_member_states(
        self,
        run: Mapping[str, Any],
        snapshot: Mapping[str, Any],
        decisions: list[Mapping[str, Any]],
        *,
        fence_check: Callable[[], None] | None = None,
    ) -> None:
        if not self._stateful_trigger(str(run.get("trigger") or "")):
            return
        state_updater = getattr(self.store, "update_member_state", None)
        event_recorder = getattr(self.store, "record_state_event", None)
        if not callable(state_updater) and not callable(event_recorder):
            return
        members = {
            str(item.get("membership_id")): item
            for item in (snapshot.get("payload", {}).get("members", []) or [])
            if isinstance(item, Mapping) and item.get("membership_id")
        }
        for decision in decisions:
            self._assert_worker_fence(fence_check)
            membership_id = str(decision.get("membership_id") or "")
            item = members.get(membership_id, {})
            if callable(state_updater):
                state_updater(
                    membership_id,
                    action=str(decision.get("action") or "decision_invalid"),
                    valid=bool(decision.get("valid")),
                    stale=bool(decision.get("stale")),
                    quality_status=str(item.get("quality_status") or "unknown"),
                    trade_date=(str(decision.get("confirming_bar_end") or item.get("latest_bar") or "")[:10] or None),
                )
            if callable(event_recorder) and bool(decision.get("confirmed")) and decision.get("previous_action") != decision.get("action"):
                event_recorder(
                    portfolio_id=str(run["portfolio_id"]),
                    membership_id=membership_id,
                    action=str(decision.get("action") or ""),
                    confirming_bar_end=str(decision.get("confirming_bar_end") or ""),
                    portfolio_version_id=str(run["portfolio_version_id"]),
                    decision_id=str(decision["id"]),
                    event_type="major_risk" if decision.get("action") == "major_risk" else "state_change",
                )

    def _persist_validation_artifact(self, version_id: str, result: Mapping[str, Any]) -> None:
        saver = getattr(self.store, "save_validation", None)
        if callable(saver):
            saver(version_id, result)

    def validate(
        self,
        workspace_id: str,
        portfolio_id: str,
        *,
        fence_check: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        self._assert_worker_fence(fence_check)
        portfolio, version, _ = self.build_snapshot(workspace_id, portfolio_id, fence_check=fence_check)
        members = [
            member
            for member in self.store.list_members(workspace_id, portfolio_id)
            if bool(member.get("enabled", True))
        ]
        adapter = get_market_adapter(portfolio["market"])
        version_config = version.get("config")
        if not isinstance(version_config, Mapping):
            version_config = {}
        strategies = version_config.get("strategies", [])
        weights = {str(item.get("strategy_name")): item for item in strategies}
        validation_config, validation_config_issues = _read_validation_config(version_config.get("validation"))
        benchmark_symbol = validation_config.get("benchmark_symbol") or _default_benchmark_symbol(portfolio["market"])
        if adapter.market != "CN":
            reasons = [_PROVIDER_NOT_CONNECTED, _MARKET_DATA_UNAVAILABLE]
            if validation_config_issues:
                reasons.extend(
                    [
                        _VALIDATION_CONFIG_INVALID,
                        *[f"{_VALIDATION_CONFIG_INVALID}:{issue['field']}" for issue in validation_config_issues],
                    ]
            )
            if not members:
                reasons.append("portfolio_has_no_members")
            result = {
                "passed": False,
                "reasons": list(dict.fromkeys(reasons)),
                "lookahead_safe": False,
                "windows": [],
                "history_start": None,
                "history_end": None,
                "calendar": adapter.canonical.exchange_calendar,
                "execution_rule": self._execution_contract(portfolio["market"], benchmark_symbol=benchmark_symbol)["execution_rule"],
                "execution_contract": self._execution_contract(portfolio["market"], benchmark_symbol=benchmark_symbol),
                "cost_model_version": validation_config["cost_model_version"],
                "coverage": {str(member["symbol"]): 0 for member in members},
                "annualization_days": adapter.canonical.annualization_days,
                "required_windows": validation_config["required_windows"],
                "max_drawdown_limit": validation_config["max_drawdown"],
                "annualized_turnover_limit": validation_config["max_annualized_turnover"],
                "survivorship_bias_control": validation_config["survivorship_bias_control"] and bool(validation_config["universe_snapshot_ref"]),
                "universe_snapshot_ref": validation_config["universe_snapshot_ref"],
                "portfolio_id": portfolio_id,
                "version_id": version["id"],
                "benchmark_instrument": benchmark_symbol,
                "benchmark_history_available": False,
                "quality_status": _MARKET_DATA_UNAVAILABLE,
                "provider_status": _PROVIDER_NOT_CONNECTED,
                "market_data_status": _MARKET_DATA_UNAVAILABLE,
                "manual_research": bool(adapter.daily_research),
                "validation_config": dict(validation_config),
                "validation_config_valid": not validation_config_issues,
                "validation_config_issues": list(validation_config_issues),
            }
            self._assert_worker_fence(fence_check)
            self._persist_validation_artifact(version["id"], result)
            self._assert_worker_fence(fence_check)
            return result

        history: dict[str, list[dict[str, Any]]] = {}
        for member in members:
            frame = self.storage.get_stock_daily(member["symbol"])
            if frame.empty:
                history[member["symbol"]] = []
                continue
            history[member["symbol"]] = [
                {
                    key: _date_text(row[key]) if key == "date" else row[key]
                    for key in ("date", "open", "high", "low", "close", "volume", "amount")
                    if key in row
                }
                for _, row in frame.iterrows()
            ]
        benchmark_symbol = validation_config.get("benchmark_symbol") or _default_benchmark_symbol(portfolio["market"])
        benchmark_history = self._load_benchmark_history(portfolio["market"], benchmark_symbol)
        result = walk_forward_validate(
            history,
            weights,
            calendar=get_market_adapter(portfolio["market"]).canonical.exchange_calendar,
            cost_model_version=validation_config["cost_model_version"],
            cost_bps=validation_config["cost_bps"],
            min_history_months=validation_config["min_history_months"],
            train_months=validation_config["train_months"],
            out_of_sample_months=validation_config["out_of_sample_months"],
            step_months=validation_config["step_months"],
            required_windows=validation_config["required_windows"],
            max_drawdown_limit=validation_config["max_drawdown"],
            annualized_turnover_limit=validation_config["max_annualized_turnover"],
            annualization_days=get_market_adapter(portfolio["market"]).canonical.annualization_days,
            survivorship_bias_control=validation_config["survivorship_bias_control"] and bool(validation_config["universe_snapshot_ref"]),
            universe_snapshot_ref=validation_config["universe_snapshot_ref"],
            execution_contract=self._execution_contract(portfolio["market"], benchmark_symbol=benchmark_symbol),
            benchmark_history=benchmark_history,
        ).as_dict()
        result.update(
            {
                "portfolio_id": portfolio_id,
                "version_id": version["id"],
                "benchmark_instrument": benchmark_symbol,
                "benchmark_history_available": benchmark_history is not None,
            }
        )
        result.update(
            {
                "validation_config": dict(validation_config),
                "validation_config_valid": not validation_config_issues,
                "validation_config_issues": list(validation_config_issues),
            }
        )
        if validation_config_issues:
            reasons = list(result.get("reasons") or [])
            for reason in (
                _VALIDATION_CONFIG_INVALID,
                *[f"{_VALIDATION_CONFIG_INVALID}:{issue['field']}" for issue in validation_config_issues],
            ):
                if reason not in reasons:
                    reasons.append(reason)
            result["reasons"] = reasons
            result["passed"] = False
        if not members:
            result["passed"] = False
            result.setdefault("reasons", []).append("portfolio_has_no_members")
        self._assert_worker_fence(fence_check)
        self._persist_validation_artifact(version["id"], result)
        self._assert_worker_fence(fence_check)
        return result

    def eligibility(self, workspace_id: str, portfolio_id: str) -> dict[str, Any]:
        self._assert_worker_fence()
        version = self._ensure_version(workspace_id, portfolio_id)
        current_version_id = version["id"]
        latest_preview = self.store.latest_report(
            workspace_id,
            portfolio_id,
            "preview",
            portfolio_version_id=current_version_id,
        )
        preview_candidates = [
            latest_preview
        ] if latest_preview and latest_preview.get("report_hash") and latest_preview.get("body", {}).get("decisions") and latest_preview.get("body", {}).get("quality_status") == "ok" else []
        validation = self.validate(workspace_id, portfolio_id)
        portfolio = self.store.get_portfolio(workspace_id, portfolio_id) or {}
        adapter = get_market_adapter(portfolio.get("market", "CN"))
        active_members = [
            item for item in self.store.list_members(workspace_id, portfolio_id)
            if bool(item.get("enabled", True))
        ]
        strategy_configs = [
            item for item in (version.get("config", {}).get("strategies") or [])
            if isinstance(item, Mapping) and bool(item.get("enabled", True))
        ]
        weighted_strategies = [item for item in strategy_configs if not bool(item.get("is_risk_veto", False))]
        preview_decisions = (preview_candidates[0].get("body", {}).get("decisions") or []) if preview_candidates else []
        preview_member_ids = {
            str(item.get("membership_id")) for item in preview_decisions if isinstance(item, Mapping)
        }
        active_member_ids = {str(item.get("id")) for item in active_members}
        required_strategy_names = {
            str(item.get("strategy_name"))
            for item in strategy_configs
            if str(item.get("strategy_name") or "")
        }
        preview_strategy_ok = bool(weighted_strategies) and all(
            bool(item.get("valid"))
            and str(item.get("action") or "") != "decision_invalid"
            and required_strategy_names.issubset(
                {
                    str(contribution.get("strategy_name"))
                    for contribution in (item.get("contributions") or [])
                    if isinstance(contribution, Mapping)
                }
            )
            for item in preview_decisions
            if isinstance(item, Mapping)
        )
        preview_ok = bool(
            preview_candidates
            and active_members
            and preview_member_ids == active_member_ids
            and len(preview_decisions) == len(active_members)
            and preview_strategy_ok
        )
        targets = self.store.list_targets(workspace_id)
        routes = self.store.list_routes(workspace_id, portfolio_id)
        active_routes = [route for route in routes if route.get("enabled")]
        reasons: list[str] = []
        if not active_members:
            reasons.append("enabled_member_required")
        if not strategy_configs or not weighted_strategies:
            reasons.append("enabled_strategy_required")
        if not preview_ok:
            reasons.append("preview_required")
        if not validation["passed"]:
            reasons.append("walk_forward_validation_required")
        if validation.get("validation_config_issues"):
            reasons.append(_VALIDATION_CONFIG_INVALID)
            reasons.extend(
                f"{_VALIDATION_CONFIG_INVALID}:{issue['field']}"
                for issue in validation["validation_config_issues"]
            )
        preview_quality = (preview_candidates[0].get("body", {}).get("data_quality") or {}) if preview_candidates else {}
        provider_health = preview_quality.get("provider_health") or {}
        required_granularities = sorted({"1d" if route.get("event_type") == "scheduled" else "5m" for route in active_routes})
        if not required_granularities:
            required_granularities = ["1d"]
        provider_eligibilities = {
            granularity: adapter.canonical.automatic_push_eligibility(
                provider_health,
                granularity=granularity,
                max_age_seconds=86_400 if granularity == "1d" else 900,
            )
            for granularity in required_granularities
        }
        adapter_ok = all(item.eligible for item in provider_eligibilities.values())
        if not adapter_ok:
            reasons.append("provider_not_qualified_for_automatic_push")
        if not targets or not active_routes:
            reasons.append("notification_target_and_route_required")
        target_by_id = {target["id"]: target for target in targets}
        target_ok = bool(active_routes) and all(
            target_by_id.get(route["target_id"], {}).get("test_status") == "passed"
            and bool(target_by_id.get(route["target_id"], {}).get("enabled"))
            for route in active_routes
        )
        if not target_ok:
            reasons.append("each_notification_target_must_pass_test")
        checks = {
            "preview_ok": preview_ok,
            "validation_ok": validation["passed"],
            "health_ok": bool(
                preview_ok
                and validation.get("lookahead_safe")
                and not preview_quality.get("stale")
                and float(preview_quality.get("coverage_pct", 0) or 0) >= 100.0
                and bool(preview_quality.get("field_sources"))
                and bool(active_members)
                and bool(weighted_strategies)
            ),
            "adapter_ok": adapter_ok,
            "target_ok": target_ok,
        }
        if not checks["health_ok"]:
            reasons.append("data_health_not_qualified")
        self._assert_worker_fence()
        saved = self.store.save_eligibility(version["id"], checks, reasons)
        self._assert_worker_fence()
        eligible = not reasons
        if not eligible:
            self._revoke_ineligible_auto_push(workspace_id, portfolio_id)
        return {
            "eligible": eligible,
            "version_id": version["id"],
            "checks": checks,
            "reasons": list(dict.fromkeys(reasons)),
            "adapter": adapter.capabilities(),
            "required_granularities": required_granularities,
            "provider_eligibility": {
                "eligible": adapter_ok,
                "items": {
                    key: {"eligible": value.eligible, "reasons": list(value.reasons), "granularity": value.granularity, "qualified_provider": value.qualified_provider}
                    for key, value in provider_eligibilities.items()
                },
            },
            "validation": validation,
            "stored": saved,
        }

    def _revoke_ineligible_auto_push(self, workspace_id: str, portfolio_id: str) -> None:
        """Fail closed when a portfolio no longer qualifies for auto-push."""

        set_auto_push = getattr(self.store, "set_auto_push", None)
        list_portfolios = getattr(self.store, "list_portfolios", None)
        if not callable(set_auto_push) or not callable(list_portfolios):
            return
        self._assert_worker_fence()
        portfolio = set_auto_push(workspace_id, portfolio_id, False)
        if portfolio is None:
            return
        remaining = any(
            bool(item.get("enabled")) and bool(item.get("auto_push_enabled"))
            for item in list_portfolios(workspace_id)
        )
        self._assert_worker_fence()
        from dashboard.account_store import account_store

        account_store.update_workspace_settings(
            workspace_id,
            {"decision_auto_push_enabled": remaining},
        )

    def process_commands(
        self,
        *,
        owner_id: str,
        limit: int = 20,
        now: datetime | None = None,
        fence_check: Callable[[], None] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute durable control-plane commands under Worker ownership.

        HTTP only creates these rows.  Keeping claim, execution and completion
        here makes the same immutable runtime serve manual commands and the
        scheduled callbacks without giving Dashboard a second execution path.
        """

        self._assert_worker_fence(fence_check)
        results: list[dict[str, Any]] = []
        for command in self.store.claim_commands(owner_id, limit=limit, now=now):
            self._assert_worker_fence(fence_check)
            command_id = str(command["id"])
            payload = command.get("payload") if isinstance(command.get("payload"), Mapping) else {}
            command_type = str(command.get("command_type") or "")
            portfolio_id = str(payload.get("portfolio_id") or command.get("portfolio_id") or "")
            try:
                if not self.store.renew_command(command_id, owner_id):
                    raise RuntimeError("decision_command_lease_lost")
                if command_type == "decision.preview":
                    result = self.run(
                        str(command["workspace_id"]),
                        portfolio_id,
                        trigger="preview",
                        report_type="preview",
                        run_key=str(payload.get("run_key") or f"command:{command_id}"),
                        fence_check=fence_check,
                    )
                    self._assert_worker_fence(fence_check)
                    result["eligibility"] = self.eligibility(str(command["workspace_id"]), portfolio_id)
                    completed = self.store.complete_command(command_id, owner_id, result)
                elif command_type == "decision.analyze":
                    result = self.run(
                        str(command["workspace_id"]),
                        portfolio_id,
                        trigger="manual",
                        report_type="manual",
                        run_key=str(payload.get("run_key") or f"command:{command_id}"),
                        fence_check=fence_check,
                    )
                    self._assert_worker_fence(fence_check)
                    completed = self.store.complete_command(command_id, owner_id, result)
                elif command_type == "decision.validate":
                    workspace_id = str(command["workspace_id"])
                    result = {
                        "validation": self.validate(workspace_id, portfolio_id, fence_check=fence_check),
                        "eligibility": self.eligibility(workspace_id, portfolio_id),
                    }
                    self._assert_worker_fence(fence_check)
                    completed = self.store.complete_command(command_id, owner_id, result)
                elif command_type == "decision.enable_auto_push":
                    workspace_id = str(command["workspace_id"])
                    eligibility = self.eligibility(workspace_id, portfolio_id)
                    if not eligibility["eligible"]:
                        self._assert_worker_fence(fence_check)
                        completed = self.store.complete_command(
                            command_id,
                            owner_id,
                            {"enabled": False, "eligibility": eligibility},
                            status="rejected",
                        )
                    else:
                        self._assert_worker_fence(fence_check)
                        from dashboard.account_store import account_store

                        portfolio = self.store.set_auto_push(workspace_id, portfolio_id, True)
                        self._assert_worker_fence(fence_check)
                        workspace = account_store.update_workspace_settings(
                            workspace_id,
                            {"decision_auto_push_enabled": True},
                        )
                        completed = self.store.complete_command(
                            command_id,
                            owner_id,
                            {
                                "enabled": True,
                                "portfolio": portfolio,
                                "workspace": workspace,
                                "eligibility": eligibility,
                            },
                        )
                elif command_type == "decision.disable_auto_push":
                    workspace_id = str(command["workspace_id"])
                    self._assert_worker_fence(fence_check)
                    portfolio = self.store.set_auto_push(workspace_id, portfolio_id, False)
                    if portfolio is None:
                        raise KeyError("portfolio_not_found")
                    self._assert_worker_fence(fence_check)
                    # The workspace switch is only a coarse opt-in for the
                    # Worker. Keep it on while another portfolio remains
                    # opted in, otherwise make the status truthful without
                    # touching any other portfolio's immutable history.
                    from dashboard.account_store import account_store

                    remaining = any(
                        bool(item.get("enabled")) and bool(item.get("auto_push_enabled"))
                        for item in self.store.list_portfolios(workspace_id)
                    )
                    workspace = account_store.update_workspace_settings(
                        workspace_id,
                        {"decision_auto_push_enabled": remaining},
                    )
                    completed = self.store.complete_command(
                        command_id,
                        owner_id,
                        {
                            "enabled": False,
                            "portfolio": portfolio,
                            "workspace": workspace,
                        },
                    )
                elif command_type == "notification.test_target":
                    from .delivery import DecisionDeliveryService

                    delivery = DecisionDeliveryService(
                        self.store,
                        owner_id=owner_id,
                        worker_owned=True,
                        fence_check=fence_check or self.worker_fence_check,
                    )
                    result = delivery.test_target(str(command["workspace_id"]), str(payload["target_id"]))
                    self._assert_worker_fence(fence_check)
                    completed = self.store.complete_command(command_id, owner_id, result)
                else:
                    raise ValueError("unsupported_decision_command")
                results.append(completed)
            except Exception as exc:
                self._assert_worker_fence(fence_check)
                results.append(self.store.fail_command(command_id, owner_id, str(exc)))
        return results

    def worker_callbacks(self):
        from engine.decision_worker import WorkerCallbacks

        def worker_portfolios() -> list[dict[str, Any]]:
            return self.store.list_portfolios_for_worker(self.workspace_automation_enabled)

        def schedule_contexts(now: datetime):
            portfolios = worker_portfolios()
            markets = sorted({str(item.get("market") or "CN") for item in portfolios}) or ["CN"]
            return tuple((market, now.astimezone(get_market_adapter(market).canonical.timezone)) for market in markets)

        def any_market_trading_day(when: datetime) -> bool:
            portfolios = worker_portfolios()
            markets = {str(item.get("market") or "CN") for item in portfolios} or {"CN"}
            return any(get_market_adapter(market).canonical.is_trading_day(when.astimezone(get_market_adapter(market).canonical.timezone)) for market in markets)

        return WorkerCallbacks(
            is_trading_day=any_market_trading_day,
            prepare=lambda **kwargs: self._prepare_slot(kwargs["slot"], kwargs["scheduled_for"]),
            send_prepared=lambda **kwargs: self._send_slot(kwargs["slot"], kwargs["scheduled_for"]),
            poll_completed_bars=lambda **kwargs: self._poll_bars(kwargs["observed_at"]),
            schedule_contexts=schedule_contexts,
            prepare_for_context=lambda **kwargs: self._prepare_slot(kwargs["slot"], kwargs["scheduled_for"], market=kwargs.get("market")),
            send_for_context=lambda **kwargs: self._send_slot(kwargs["slot"], kwargs["scheduled_for"], market=kwargs.get("market")),
            poll_for_context=lambda **kwargs: self._poll_bars(kwargs["observed_at"], market=kwargs.get("market")),
            process_commands=lambda **kwargs: self.process_commands(
                owner_id=str(kwargs.get("owner_id") or "decision-worker"),
                limit=int(kwargs.get("limit") or 20),
                now=kwargs.get("now"),
                fence_check=kwargs.get("fence_check"),
            ),
        )

    def _prepare_slot(self, slot: str, scheduled_for: datetime, *, market: str | None = None) -> list[dict[str, Any]]:
        results = []
        failures: list[str] = []
        for portfolio in self.store.list_portfolios_for_worker(self.workspace_automation_enabled):
            self._assert_worker_fence()
            if not portfolio.get("enabled"):
                continue
            if market and str(portfolio.get("market") or "CN") != str(market):
                continue
            market_adapter = get_market_adapter(portfolio.get("market", "CN"))
            if not bool(getattr(market_adapter, "supports_scheduled_daily_report", False)):
                results.append({
                    "portfolio_id": portfolio["id"],
                    "status": "skipped",
                    "reason": "verified_exchange_calendar_required",
                })
                continue
            market_time = scheduled_for.astimezone(market_adapter.canonical.timezone)
            if not market_adapter.canonical.is_trading_day(market_time):
                continue
            try:
                self._assert_worker_fence()
                version = self._ensure_version(portfolio["workspace_id"], portfolio["id"])
                results.append(
                    self.run(
                        portfolio["workspace_id"],
                        portfolio["id"],
                        trigger=f"scheduled_prepare:{slot}",
                        report_type="prepared",
                        run_key=f"prepared:{portfolio['id']}:{version['id']}:{slot}:{market_time.date()}",
                    )
                )
            except Exception as exc:
                failures.append(f"{portfolio['id']}: {exc}")
        if failures:
            # Do not let the Worker mark this slot as processed after a partial
            # preparation.  Successful portfolios are idempotent by run_key;
            # the next misfire retry can therefore repair the failed subset.
            raise RuntimeError("scheduled_prepare_failed: " + "; ".join(failures))
        return results

    def _send_slot(self, slot: str, scheduled_for: datetime, *, market: str | None = None) -> list[dict[str, Any]]:
        from .delivery import DecisionDeliveryService
        from engine.events.outbox import SQLiteOutbox

        outbox = SQLiteOutbox(DB_DIR / "events.db")
        delivery = DecisionDeliveryService(
            self.store,
            outbox=outbox,
            owner_id=self.worker_owner_id or "decision-worker-scheduled-delivery",
            worker_owned=True,
            eligibility_check=self.eligibility,
            fence_token_provider=self.worker_fence_token_provider,
            fence_check=self.worker_fence_check,
        )
        results: list[dict[str, Any]] = []
        base_url = os.getenv("DECISION_REPORT_BASE_URL", "").rstrip("/")
        try:
            for portfolio in self.store.list_portfolios_for_worker(self.workspace_automation_enabled):
                self._assert_worker_fence()
                workspace_id = str(portfolio["workspace_id"])
                portfolio_id = str(portfolio["id"])
                if market and str(portfolio.get("market") or "CN") != str(market):
                    continue
                market_adapter = get_market_adapter(portfolio.get("market", "CN"))
                if not bool(getattr(market_adapter, "supports_scheduled_daily_report", False)):
                    results.append({
                        "portfolio_id": portfolio_id,
                        "status": "not_eligible",
                        "reasons": ["verified_exchange_calendar_required"],
                    })
                    continue
                market_time = scheduled_for.astimezone(market_adapter.canonical.timezone)
                if not market_adapter.canonical.is_trading_day(market_time):
                    continue
                eligibility = self.eligibility(workspace_id, portfolio_id)
                if not eligibility["eligible"]:
                    results.append({"portfolio_id": portfolio_id, "status": "not_eligible", "reasons": eligibility["reasons"]})
                    continue
                self._assert_worker_fence()
                version = self._ensure_version(workspace_id, portfolio_id)
                reports = self.store.list_prepared_reports(
                    workspace_id,
                    slot,
                    market_time.date().isoformat(),
                    portfolio_id=portfolio_id,
                    portfolio_version_id=version["id"],
                )
                report = next(
                    (
                        item
                        for item in reports
                        if item.get("body", {}).get("portfolio_id") == portfolio_id
                        and item.get("body", {}).get("portfolio_version_id") == version["id"]
                    ),
                    None,
                )
                if not report:
                    results.append({"portfolio_id": portfolio_id, "status": "prepared_report_missing"})
                    continue
                self._assert_worker_fence()
                report_url = self._report_url_for_events(
                    outbox,
                    delivery,
                    workspace_id,
                    report,
                    ("scheduled",),
                    base_url,
                )
                self._assert_worker_fence()
                event_id = delivery.enqueue_report(workspace_id, report["id"], "scheduled", report_url=report_url)
                self._assert_worker_fence()
                results.append({"portfolio_id": portfolio_id, "report_id": report["id"], "event_id": event_id, "status": "queued"})
            return results
        finally:
            outbox.close()

    def _report_url_for_events(
        self,
        outbox: Any,
        delivery: Any,
        workspace_id: str,
        report: Mapping[str, Any],
        event_types: tuple[str, ...],
        base_url: str,
    ) -> str:
        """Reuse an immutable event URL before issuing a new share token.

        The raw token cannot be reconstructed from the database hash.  The
        Outbox payload is therefore the durable source for retries; only a
        genuinely new event needs a new share-link row.
        """

        getter = getattr(outbox, "get_by_idempotency_key", None)
        if callable(getter):
            for event_type in event_types:
                event = delivery._event(report, event_type, "")
                existing = getter(event.idempotency_key)
                if existing is None:
                    continue
                payload = dict(existing.event.payload)
                if (
                    str(payload.get("workspace_id") or "") == workspace_id
                    and str(payload.get("report_id") or "") == str(report.get("id") or "")
                    and str(payload.get("report_url") or "")
                ):
                    return str(payload["report_url"])

        self._assert_worker_fence()
        token, _ = self.store.issue_share_link(workspace_id, str(report["id"]))
        return f"{base_url}/report/{token}" if base_url else f"/report/{token}"

    @staticmethod
    def _loader_call(
        loader: Callable[..., Mapping[str, Any] | None],
        *,
        market: str,
        symbols: list[str],
        observed_at: datetime,
    ) -> Mapping[str, Any] | None:
        """Call a provider seam without imposing a concrete SDK signature."""

        # Choose the compatibility call shape from the callable signature so a
        # provider-raised TypeError is not mistaken for an argument mismatch
        # and executed a second time.
        try:
            parameters = tuple(inspect.signature(loader).parameters.values())
        except (TypeError, ValueError):
            parameters = ()
        accepts_keywords = any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters)
        accepts_keywords = accepts_keywords or all(
            name in {parameter.name for parameter in parameters}
            for name in ("market", "symbols", "observed_at")
        )
        if accepts_keywords:
            return loader(market=market, symbols=tuple(symbols), observed_at=observed_at)
        return loader(market, tuple(symbols), observed_at)

    @staticmethod
    def _provider_health_payload(value: Any) -> dict[str, Any]:
        """Convert provider health dataclasses and mappings to JSON facts."""

        if isinstance(value, Mapping):
            payload = dict(value)
        else:
            payload = {
                field: getattr(value, field, None)
                for field in ("healthy", "validated", "completed_bars", "updated_at", "coverage_pct", "field_sources")
                if hasattr(value, field)
            }
        updated_at = payload.get("updated_at")
        if isinstance(updated_at, (datetime, date)):
            payload["updated_at"] = updated_at.isoformat()
        field_sources = payload.get("field_sources")
        payload["field_sources"] = dict(field_sources) if isinstance(field_sources, Mapping) else {}
        return payload

    @staticmethod
    def _normalise_intraday_result(raw: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
        """Normalize provider evidence while preserving a fail-closed shape."""

        metadata = dict(raw)
        provider = str(raw.get("provider") or raw.get("source") or "").strip()
        health = raw.get("provider_health")
        if health is None:
            health = raw.get("health")
        if not isinstance(health, Mapping):
            health = {}
        # Accept one-provider health shorthand, but never invent a healthy
        # status or a completion flag when the provider omitted it.
        if provider and any(key in health for key in ("healthy", "validated", "completed_bars", "coverage_pct")):
            health = {provider: dict(health)}
        normalized_health = {
            str(name): DecisionRuntime._provider_health_payload(value)
            for name, value in health.items()
        }
        metadata.update(
            {
                "provider": provider,
                "provider_health": normalized_health,
                "provider_status": str(raw.get("provider_status") or ""),
                "request_hash": str(raw.get("request_hash") or ""),
                "response_hash": str(raw.get("response_hash") or ""),
                "provider_evidence": dict(raw.get("provider_evidence") or {}) if isinstance(raw.get("provider_evidence"), Mapping) else {},
            }
        )
        source = raw.get("completed_bars")
        if source is None:
            source = raw.get("bars_by_symbol")
        if source is None:
            source = raw.get("bars")
        if source is None:
            source = raw.get("data")
        grouped: dict[str, list[dict[str, Any]]] = {}

        def add(symbol: Any, entries: Any) -> None:
            clean_symbol = str(symbol or "").strip()
            if not clean_symbol:
                return
            if isinstance(entries, Mapping):
                entries = entries.get("bars") or entries.get("items") or []
            if not isinstance(entries, (list, tuple)):
                return
            for entry in entries:
                if not isinstance(entry, Mapping):
                    continue
                row = dict(entry)
                row["symbol"] = clean_symbol
                bar_end = row.get("bar_end") or row.get("end") or row.get("datetime") or row.get("date")
                if bar_end is not None:
                    normalized_bar_end = bar_end.isoformat() if isinstance(bar_end, (datetime, date)) else bar_end
                    row["bar_end"] = normalized_bar_end
                    row.setdefault("date", normalized_bar_end)
                # Completion must be explicit.  The domain confirmation gate
                # treats a missing marker as incomplete instead of guessing.
                row["completed"] = bool(row.get("completed", row.get("is_completed", False)))
                grouped.setdefault(clean_symbol, []).append(row)

        if isinstance(source, Mapping):
            for symbol, entries in source.items():
                add(symbol, entries)
        elif isinstance(source, (list, tuple)):
            for entry in source:
                if not isinstance(entry, Mapping):
                    continue
                symbol = entry.get("symbol") or entry.get("code") or entry.get("instrument")
                if symbol is None:
                    continue
                add(symbol, [entry])
        return metadata, grouped

    @staticmethod
    def _intraday_symbol_bars(grouped: Mapping[str, list[dict[str, Any]]], symbol: str) -> list[dict[str, Any]]:
        requested = str(symbol or "").strip()
        candidates = [requested]
        if "." in requested:
            candidates.append(requested.split(".", 1)[1])
        candidates.extend([requested.upper(), requested.lower()])
        for candidate in candidates:
            if candidate in grouped:
                return [dict(item) for item in grouped[candidate]]
        return []

    @staticmethod
    def _intraday_event_types(decisions: list[Mapping[str, Any]]) -> tuple[str, ...]:
        event_types: list[str] = []
        if any(
            str(item.get("action") or "") == "major_risk"
            and item.get("previous_action") != "major_risk"
            and bool(item.get("confirmed"))
            for item in decisions
        ):
            event_types.append("major_risk")
        if any(
            str(item.get("action") or "") != "major_risk"
            and item.get("previous_action") is not None
            and item.get("previous_action") != item.get("action")
            and bool(item.get("confirmed"))
            for item in decisions
        ):
            event_types.append("state_change")
        return tuple(event_types)

    def _enqueue_intraday_events(self, workspace_id: str, report: Mapping[str, Any], decisions: list[Mapping[str, Any]]) -> list[str]:
        """Write report events only; the Worker dispatcher owns network I/O."""

        if self.outbox is None:
            return []
        from .delivery import DecisionDeliveryService

        service = DecisionDeliveryService(
            self.store,
            outbox=self.outbox,
            owner_id=self.worker_owner_id or "decision-worker-intraday",
            worker_owned=True,
            fence_token_provider=self.worker_fence_token_provider,
            fence_check=self.worker_fence_check,
        )
        event_types = self._intraday_event_types(decisions)
        if not event_types:
            return []
        base_url = os.getenv("DECISION_REPORT_BASE_URL", "").rstrip("/")
        report_url = self._report_url_for_events(
            self.outbox,
            service,
            workspace_id,
            report,
            event_types,
            base_url,
        )
        events: list[str] = []
        for event_type in event_types:
            self._assert_worker_fence()
            event_id = service.enqueue_report(workspace_id, str(report["id"]), event_type, report_url=report_url)
            self._assert_worker_fence()
            if event_id:
                events.append(event_id)
        return events

    def _poll_bars(self, observed_at: datetime, *, market: str | None = None) -> dict[str, Any]:
        """Poll an injected completed-5m source and run confirmed decisions."""

        market_code = str(market or "CN").strip().upper()
        observed = observed_at if observed_at.tzinfo else observed_at.replace(tzinfo=timezone.utc)
        portfolios = [
            item
            for item in self.store.list_portfolios_for_worker(self.workspace_automation_enabled)
            if str(item.get("market") or "CN").upper() == market_code
        ]
        base = {"observed_at": observed.isoformat(), "market": market_code}
        if self.intraday_bars_loader is None:
            return {**base, "status": "skipped", "reason": "no_qualified_5m_provider"}
        if not portfolios:
            return {**base, "status": "skipped", "reason": "no_eligible_portfolio"}
        symbols = sorted(
            {
                str(member.get("symbol") or "")
                for portfolio in portfolios
                for member in self.store.list_members(str(portfolio["workspace_id"]), str(portfolio["id"]))
                if bool(member.get("enabled", True)) and str(member.get("symbol") or "")
            }
        )
        try:
            raw = self._loader_call(self.intraday_bars_loader, market=market_code, symbols=symbols, observed_at=observed)
            if not isinstance(raw, Mapping):
                raise ValueError("intraday_loader_result_invalid")
            metadata, grouped = self._normalise_intraday_result(raw)
        except Exception as exc:
            return {**base, "status": "skipped", "reason": "intraday_loader_error", "error": str(exc)[:300]}

        adapter = get_market_adapter(market_code)
        provider_health = metadata.get("provider_health") or {}
        eligibility = adapter.canonical.automatic_push_eligibility(
            provider_health,
            granularity="5m",
            max_age_seconds=900,
            now=observed,
        )
        provider = str(metadata.get("provider") or "")
        if not eligibility.eligible or not provider or provider != eligibility.qualified_provider:
            return {
                **base,
                "status": "skipped",
                "reason": "no_qualified_5m_provider",
                "provider": provider,
                "provider_health": provider_health,
                "eligibility": {"eligible": eligibility.eligible, "reasons": list(eligibility.reasons)},
            }

        results: list[dict[str, Any]] = []
        for portfolio in portfolios:
            workspace_id = str(portfolio["workspace_id"])
            portfolio_id = str(portfolio["id"])
            version = self._ensure_version(workspace_id, portfolio_id)
            config = version.get("config") if isinstance(version.get("config"), Mapping) else {}
            weights = {str(item.get("strategy_name")): item for item in (config.get("strategies") or []) if isinstance(item, Mapping)}
            strategy_names = {name for name in weights if name}
            members = [
                item
                for item in self.store.list_members(workspace_id, portfolio_id)
                if bool(item.get("enabled", True))
            ]
            snapshot_members: list[dict[str, Any]] = []
            blocked_reason = ""
            for member in members:
                bars = self._intraday_symbol_bars(grouped, str(member.get("symbol") or ""))
                parsed_times = [parse_bar_time(item.get("bar_end")) for item in bars]
                if (
                    not bars
                    or any(value is None or value > observed for value in parsed_times)
                    or any(not bool(item.get("completed")) for item in bars)
                    or any(bool(item.get(key)) for item in bars for key in ("revision", "revised", "provider_revision", "missing"))
                ):
                    blocked_reason = "completed_5m_bars_invalid"
                    break
                quality = validate_bars(bars, minimum_bars=30)
                if not quality.valid:
                    blocked_reason = "intraday_bar_quality_invalid"
                    break
                previous_action = self._freeze_previous_action(str(member["id"]))
                prior_outputs = _strategy_outputs(bars[:-1], strategy_names)
                current_outputs = _strategy_outputs(bars, strategy_names)
                prior_evaluation = evaluate_decision(
                    prior_outputs,
                    weights,
                    previous_action=previous_action,
                    confirmed=True,
                )
                current_evaluation = evaluate_decision(
                    current_outputs,
                    weights,
                    previous_action=previous_action,
                    confirmed=True,
                )
                current_is_major_risk = (
                    current_evaluation.valid
                    and current_evaluation.risk_veto
                    and current_evaluation.action == "major_risk"
                )
                if current_is_major_risk:
                    confirmation_bar_ends = [bars[-1].get("bar_end")]
                    confirmation_rule = "current_effective_risk_input"
                else:
                    if len(bars) < 2:
                        blocked_reason = "two_completed_5m_bars_not_confirmed"
                        break
                    confirmation_pair = [
                        {**bars[-2], "bar_end": bars[-2].get("bar_end"), "action": prior_evaluation.action},
                        {**bars[-1], "bar_end": bars[-1].get("bar_end"), "action": current_evaluation.action},
                    ]
                    if (
                        not prior_evaluation.valid
                        or not current_evaluation.valid
                        or prior_evaluation.action in {"decision_invalid", "stale"}
                        or current_evaluation.action in {"decision_invalid", "stale"}
                        or prior_evaluation.action != current_evaluation.action
                        or not confirm_completed_bars(confirmation_pair, current_evaluation.action)
                    ):
                        blocked_reason = "two_completed_5m_bars_not_confirmed"
                        break
                    confirmation_bar_ends = [bars[-2].get("bar_end"), bars[-1].get("bar_end")]
                    confirmation_rule = "two_adjacent_completed_bars_same_action"
                snapshot_members.append(
                    {
                        "membership_id": member["id"],
                        "symbol": member["symbol"],
                        "name": member.get("name", ""),
                        "bars": bars,
                        "latest_bar": bars[-1].get("bar_end") or "",
                        "coverage": quality.valid_bar_count,
                        "coverage_pct": 100.0,
                        "quality_status": "ok",
                        "quality_reasons": list(quality.reasons),
                        "field_coverage": quality.field_coverage,
                        "previous_action": previous_action,
                        "invalid_persisted": False,
                        "confirmed": True,
                        "confirmation_bar_ends": confirmation_bar_ends,
                        "confirmation_rule": confirmation_rule,
                        "confirmed_action": current_evaluation.action,
                        "strategy_outputs": current_outputs,
                    }
                )
            if blocked_reason or not members or len(snapshot_members) != len(members):
                results.append({"portfolio_id": portfolio_id, "status": "blocked", "reason": blocked_reason or "portfolio_has_no_members"})
                continue
            # The pair timestamps, membership set and current action define the
            # automatic run identity.  Provider collection timestamps do not.
            pair_identity = [
                {
                    "membership_id": item["membership_id"],
                    "bar_ends": item["confirmation_bar_ends"],
                    "action": item["confirmed_action"],
                }
                for item in snapshot_members
            ]
            run_key = "intraday:%s:%s:%s" % (portfolio_id, version["id"], content_hash(pair_identity))
            run_lookup = getattr(self.store, "get_run_by_key", None)
            existing = run_lookup(workspace_id, run_key) if callable(run_lookup) else None
            if existing is not None:
                result = self.run(
                    workspace_id,
                    portfolio_id,
                    trigger="intraday",
                    report_type="intraday",
                    run_key=run_key,
                )
            else:
                evidence = dict(metadata.get("provider_evidence") or {})
                evidence.update(
                    {
                        "provider": provider,
                        "request_hash": metadata.get("request_hash") or evidence.get("request_hash"),
                        "response_hash": metadata.get("response_hash") or evidence.get("response_hash"),
                        "collected_at": evidence.get("collected_at") or metadata.get("collected_at") or observed.isoformat(timespec="seconds"),
                    }
                )
                payload = {
                    "market": market_code,
                    "portfolio_id": portfolio_id,
                    "portfolio_version_id": version["id"],
                    "members": snapshot_members,
                    "captured_at": max(item["latest_bar"] for item in snapshot_members),
                    "provider": provider,
                    "provider_status": str(metadata.get("provider_status") or "integrated"),
                    "updated_at": (provider_health.get(provider) or {}).get("updated_at") if isinstance(provider_health.get(provider), Mapping) else "",
                    "coverage_pct": 100.0,
                    "field_sources": (provider_health.get(provider) or {}).get("field_sources", {}) if isinstance(provider_health.get(provider), Mapping) else {},
                    "provider_health": provider_health,
                    "provider_evidence": evidence,
                    "stale": False,
                    "fallback_reason": "",
                    "adapter": adapter.capabilities(),
                    "intraday_confirmation": {
                        "granularity": "5m",
                        "rules": sorted({str(item.get("confirmation_rule") or "") for item in snapshot_members}),
                    },
                }
                self._assert_worker_fence()
                snapshot = self.store.create_snapshot(workspace_id, version["id"], payload, provider, "ok")
                self._assert_worker_fence()
                result = self.run(
                    workspace_id,
                    portfolio_id,
                    trigger="intraday",
                    report_type="intraday",
                    run_key=run_key,
                    snapshot_override=snapshot,
                )
            report = result.get("report")
            event_ids = self._enqueue_intraday_events(workspace_id, report, result.get("decisions") or []) if report else []
            results.append(
                {
                    "portfolio_id": portfolio_id,
                    "run_id": result.get("run", {}).get("id"),
                    "report_id": report.get("id") if report else None,
                    "status": "processed",
                    "event_ids": event_ids,
                }
            )
        status = "processed" if any(item.get("status") == "processed" for item in results) else "blocked"
        return {
            **base,
            "status": status,
            "provider": provider,
            "provider_health": provider_health,
            "portfolios": results,
        }

    def replay_report(self, workspace_id: str, report_id: str) -> dict[str, Any]:
        """Recompute a frozen report without fetching new market data."""

        from .store import report_fingerprint

        report = self.store.get_report(workspace_id, report_id)
        if not report:
            raise KeyError("report_not_found")
        run = self.store.get_run(workspace_id, report["decision_run_id"])
        if not run:
            raise KeyError("decision_run_not_found")
        snapshot = self.store.get_snapshot(run["snapshot_id"])
        version = self.store.get_version(workspace_id, run["portfolio_version_id"])
        if not snapshot or not version:
            raise KeyError("frozen_input_not_found")
        weights = {str(item.get("strategy_name")): item for item in version.get("config", {}).get("strategies", [])}
        original_by_membership = {
            str(item.get("membership_id")): item
            for item in (report.get("body", {}).get("decisions") or [])
            if isinstance(item, Mapping)
        }
        decisions = []
        for item in snapshot["payload"].get("members", []):
            original = original_by_membership.get(str(item.get("membership_id")), {})
            evaluation = evaluate_decision(
                item.get("strategy_outputs", []),
                weights,
                # New snapshots carry the previous action as an input fact;
                # the report fallback keeps legacy snapshots replayable.
                previous_action=item.get("previous_action", original.get("previous_action")),
                data_stale=item.get("quality_status") == "stale",
                data_invalid=(item.get("quality_status") == "invalid" or item.get("coverage", 0) < 30)
                and not bool(item.get("invalid_persisted")),
                invalid_pending=bool(item.get("invalid_persisted") is False and item.get("quality_status") == "invalid" and item.get("previous_action")),
                confirmed=bool(original.get("confirmed", True)),
            )
            confirming_bar_end = original["confirming_bar_end"] if "confirming_bar_end" in original else (item.get("latest_bar") or None)
            decisions.append({"membership_id": item["membership_id"], "symbol": item["symbol"], "confirming_bar_end": confirming_bar_end, **evaluation.as_dict()})
        snapshot_payload = snapshot.get("payload") if isinstance(snapshot.get("payload"), Mapping) else {}
        data_quality = {key: snapshot_payload[key] for key in ("provider", "provider_status", "updated_at", "captured_at", "coverage_pct", "field_sources", "provider_health", "provider_evidence", "stale", "fallback_reason", "adapter") if key in snapshot_payload}
        schedule_context = scheduled_run_context(run)
        original_body = report.get("body") if isinstance(report.get("body"), Mapping) else {}
        body = {
            "report_type": report["report_type"],
            "portfolio_id": run["portfolio_id"],
            "portfolio_version_id": run["portfolio_version_id"],
            "input_hash": snapshot["payload_hash"],
            "version_hash": version["config_hash"],
            "source": snapshot["source"],
            "quality_status": snapshot["quality_status"],
            "data_quality": data_quality,
            "trigger": run["trigger"],
            "run_key": run.get("run_key"),
            "schedule_slot": original_body.get("schedule_slot") or schedule_context["schedule_slot"],
            "trade_date": original_body.get("trade_date") or schedule_context["trade_date"],
            "decisions": decisions,
        }
        for key in ("market", "market_capabilities", "strategy_weights", "evidence", "validation", "eligibility"):
            if key in original_body:
                body[key] = original_body[key]
        replay_hash = __import__("decision.store", fromlist=["content_hash"]).content_hash(report_fingerprint(body))
        return {"report_id": report_id, "stored_report_hash": report["report_hash"], "replay_report_hash": replay_hash, "match": replay_hash == report["report_hash"], "input_hash": snapshot["payload_hash"], "version_hash": version["config_hash"]}


__all__ = ["DecisionRuntime"]
