from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import time
from zoneinfo import ZoneInfo

import pytest

from backup.manager import BackupManager
from data.markets import (
    A_SHARE_MARKET_ADAPTER,
    HONG_KONG_MARKET_ADAPTER,
    ProviderHealth,
    ProviderStatus,
    TradingCalendar,
)
from decision.domain import evaluate_decision
from decision.runtime import DecisionRuntime
from decision.store import DecisionStore, report_fingerprint
from decision.validation import (
    MIN_HISTORY_COVERAGE_PCT,
    is_valid_universe_snapshot_ref,
    select_weight_candidate,
    walk_forward_validate,
)
from engine.decision_worker import PREPARATION_SLOTS, DecisionWorker, WorkerCallbacks, SQLiteWorkerLease
from engine.events.outbox import SQLiteOutbox


_VALID_UNIVERSE_REF = "sha256:" + "a" * 64


def test_report_freezes_data_quality_and_replays_with_the_same_hash(tmp_path: Path) -> None:
    store = DecisionStore(tmp_path / "decisions.db")
    portfolio = store.create_portfolio("workspace-1", "CN", "测试组合")
    version = store.create_version(
        "workspace-1",
        portfolio["id"],
        {"strategies": [{"strategy_name": "momentum", "version": "v1", "weight": 1, "enabled": True}]},
    )
    member = store.add_member("workspace-1", portfolio["id"], "600519")
    snapshot = store.create_snapshot(
        "workspace-1",
        version["id"],
        {
            "market": "CN",
            "members": [{
                "membership_id": member["id"],
                "symbol": "600519",
                "coverage": 30,
                "quality_status": "ok",
                "strategy_outputs": [{
                    "strategy_name": "momentum",
                    "strategy_version": "v1",
                    "normalized_score": 72,
                    "confidence": 1,
                    "data_quality": 1,
                }],
            }],
            "provider": "Tushare Pro",
            "provider_status": "integrated",
            "updated_at": "2026-08-14T01:00:00+00:00",
            "coverage_pct": 100,
            "field_sources": {"close": "Tushare Pro"},
            "provider_health": {"Tushare Pro": {"healthy": True, "validated": True, "coverage_pct": 100}},
            "fallback_reason": "",
        },
        "Tushare Pro",
        "ok",
    )
    run = store.create_run("workspace-1", portfolio["id"], version["id"], snapshot["id"], "manual:1", "manual", "manual")
    evaluation = evaluate_decision(
        snapshot["payload"]["members"][0]["strategy_outputs"],
        {"momentum": {"enabled": True, "weight": 1, "version": "v1"}},
        confirmed=True,
    )
    decision = store.record_decision(run["id"], member["id"], {"symbol": "600519", **evaluation.as_dict()})
    report = store.create_report(run, snapshot, version, [decision], "manual")
    store.complete_run(run["id"])

    assert report["body"]["data_quality"]["provider_health"]["Tushare Pro"]["coverage_pct"] == 100
    assert report["body"]["market"] == "CN"
    assert report["body"]["validation"]["status"] == "not_run"
    assert report["body"]["evidence"]["member_count"] == 1
    replay = DecisionRuntime(store, object()).replay_report("workspace-1", report["id"])
    assert replay["match"] is True
    BackupManager().backup(tmp_path / "backup", [store.database])
    restored = BackupManager().restore(
        tmp_path / "backup",
        tmp_path / "restore",
        replay_decision_id=decision["id"],
    )
    assert restored["replay"]["match"] is True
    altered = dict(report["body"])
    altered["data_quality"] = {**altered["data_quality"], "coverage_pct": 99}
    assert report["report_hash"] != __import__("decision.store", fromlist=["content_hash"]).content_hash(report_fingerprint(altered))

    store.add_ai_commentary("workspace-1", report["id"], "fixture-model", "explain", report["body"]["input_hash"], "补充说明")
    enriched = store.get_report("workspace-1", report["id"])
    assert enriched is not None
    assert enriched["ai_commentary_status"] == "available"
    assert enriched["ai_commentary"][0]["content"] == "补充说明"
    token, link = store.issue_share_link("workspace-1", report["id"])
    enriched = store.get_report("workspace-1", report["id"])
    assert enriched is not None
    assert enriched["share_link"]["id"] == link["id"]
    assert "token_hash" not in enriched["share_link"]
    shared = store.resolve_share(token)
    assert shared is not None
    assert shared["ai_commentary"][0]["content"] == "补充说明"


def test_runtime_freezes_previous_action_before_evaluating_a_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Frame:
        def __init__(self, rows: list[dict]) -> None:
            self.rows = rows

        empty = False

        def tail(self, count: int) -> "Frame":
            return Frame(self.rows[-count:])

        def iterrows(self):
            return enumerate(self.rows)

    class Storage:
        def get_stock_daily(self, _symbol: str) -> Frame:
            return Frame([
                {
                    "date": date.today() - timedelta(days=29 - index),
                    "open": 10.0,
                    "high": 11.0,
                    "low": 9.0,
                    "close": 10.5,
                    "volume": 1_000.0,
                    "amount": 10_500.0,
                }
                for index in range(30)
            ])

    store = DecisionStore(tmp_path / "decisions.db")
    portfolio = store.create_portfolio("workspace-1", "CN", "测试组合")
    store.create_version(
        "workspace-1",
        portfolio["id"],
        {"strategies": [{"strategy_name": "momentum", "version": "v1", "weight": 1, "enabled": True}]},
    )
    member = store.add_member("workspace-1", portfolio["id"], "600519")
    calls: list[str] = []

    def changing_history(membership_id: str) -> dict[str, str]:
        calls.append(membership_id)
        return {"action": "hold" if len(calls) == 1 else "buy_candidate"}

    monkeypatch.setattr(store, "latest_decision", changing_history)
    result = DecisionRuntime(store, Storage()).run("workspace-1", portfolio["id"], trigger="manual")

    member_snapshot = result["snapshot"]["payload"]["members"][0]
    assert calls == [member["id"]]
    assert member_snapshot["previous_action"] == "hold"
    assert result["decisions"][0]["previous_action"] == "hold"


def test_notification_target_refs_are_protected_at_storage_and_api_boundaries(tmp_path: Path) -> None:
    store = DecisionStore(tmp_path / "decisions.db")
    with pytest.raises(ValueError, match="secret_ref_must_use_env_reference"):
        store.create_target("workspace-1", "wecom_robot", "目标", {"secret_ref": "https://secret.example"})
    with pytest.raises(ValueError, match="endpoint_ref_must_use_env_reference"):
        store.create_target("workspace-1", "wecom_robot", "目标", {"secret_ref": "env://SECRET", "endpoint_ref": "https://webhook.example"})

    target = store.create_target("workspace-1", "wecom_robot", "目标", {"secret_ref": "env://SECRET"})
    assert target["config"] == {"secret_ref": "env://SECRET", "endpoint_ref": ""}

    from dashboard.routers.decisions import TargetRequest

    assert TargetRequest(channel="wecom_robot", label="目标", secret_ref="env://SECRET").secret_ref == "env://SECRET"
    with pytest.raises(ValueError, match="secret_ref_must_use_env_reference"):
        TargetRequest(channel="wecom_robot", label="目标", secret_ref="raw-secret")


def test_state_event_rejects_cross_portfolio_version_and_membership_references(tmp_path: Path) -> None:
    store = DecisionStore(tmp_path / "decisions.db")
    workspace_id = "workspace-1"
    portfolio = store.create_portfolio(workspace_id, "CN", "组合一")
    other_portfolio = store.create_portfolio(workspace_id, "CN", "组合二")
    version = store.create_version(
        workspace_id,
        portfolio["id"],
        {"strategies": [{"strategy_name": "momentum", "version": "v1", "weight": 1, "enabled": True}]},
    )
    other_version = store.create_version(
        workspace_id,
        portfolio["id"],
        {"strategies": [{"strategy_name": "momentum", "version": "v2", "weight": 1, "enabled": True}]},
    )
    member = store.add_member(workspace_id, portfolio["id"], "600519")
    other_member = store.add_member(workspace_id, other_portfolio["id"], "600519")
    snapshot = store.create_snapshot(workspace_id, version["id"], {"market": "CN", "members": []}, "fixture", "ok")
    run = store.create_run(workspace_id, portfolio["id"], version["id"], snapshot["id"], "manual:state-event", "scheduled", "daily")
    decision = store.record_decision(
        run["id"],
        member["id"],
        {"symbol": member["symbol"], "action": "buy_candidate", "valid": True, "confirmed": True, "confirming_bar_end": "2026-08-14T07:00:00+00:00"},
    )

    event = {
        "portfolio_id": portfolio["id"],
        "membership_id": member["id"],
        "action": "buy_candidate",
        "confirming_bar_end": "2026-08-14T07:00:00+00:00",
        "portfolio_version_id": version["id"],
        "decision_id": decision["id"],
        "event_type": "state_change",
    }
    assert store.record_state_event(**event) is True
    assert store.record_state_event(**event) is False

    with pytest.raises(ValueError, match="decision_state_event_reference_mismatch"):
        store.record_state_event(**{**event, "membership_id": other_member["id"]})
    with pytest.raises(ValueError, match="decision_state_event_reference_mismatch"):
        store.record_state_event(**{**event, "portfolio_id": other_portfolio["id"]})
    with pytest.raises(ValueError, match="decision_state_event_reference_mismatch"):
        store.record_state_event(**{**event, "portfolio_version_id": other_version["id"]})


def test_stale_data_keeps_the_last_valid_action_but_invalid_input_does_not_invent_one() -> None:
    weights = {"momentum": {"enabled": True, "weight": 1, "version": "v1"}}
    outputs = [{"strategy_name": "momentum", "normalized_score": 80, "confidence": 1, "data_quality": 1}]
    stale = evaluate_decision(outputs, weights, previous_action="buy_candidate", data_stale=True)
    invalid = evaluate_decision(outputs, weights, previous_action=None, data_invalid=True)

    assert stale.action == "buy_candidate"
    assert stale.stale is True
    assert "stale_data" in stale.reason_codes
    assert invalid.action == "decision_invalid"
    assert invalid.valid is False


def test_risk_veto_remains_actionable_when_ordinary_score_fields_are_absent() -> None:
    evaluation = evaluate_decision(
        [{"strategy_name": "drawdown_risk", "risk_veto": True, "reason_codes": ["drawdown_over_limit"]}],
        {"drawdown_risk": {"enabled": True, "weight": 0, "is_risk_veto": True}},
        confirmed=True,
    )

    assert evaluation.action == "major_risk"
    assert evaluation.risk_veto is True
    assert evaluation.valid is True


def test_daily_provider_qualification_uses_daily_capability_and_a_verified_calendar() -> None:
    longbridge = next(item for item in HONG_KONG_MARKET_ADAPTER.providers if item.name == "Longbridge")
    now = datetime(2026, 8, 15, tzinfo=timezone.utc)
    calendar = TradingCalendar(
        name="fixture_hkex_calendar",
        source="fixture_exchange_schedule",
        holidays=frozenset({date(2024, 1, 1)}),
        verified=True,
        kind="verified_exchange",
    )
    adapter = replace(
        HONG_KONG_MARKET_ADAPTER,
        calendar=calendar,
        providers=(replace(longbridge, status=ProviderStatus.INTEGRATED),),
    )
    health = {
        "Longbridge": ProviderHealth(
            healthy=True,
            validated=True,
            updated_at=now.isoformat(),
            coverage_pct=100,
            field_sources={"close": "Longbridge"},
        )
    }

    result = adapter.automatic_push_eligibility(health, granularity="1d", now=now)

    assert result.eligible is True
    assert result.qualified_provider == "Longbridge"
    assert calendar.is_trading_day(date(2024, 1, 1)) is False


def test_weekday_fallback_holiday_counterexample_is_unverified_and_cannot_qualify_automation() -> None:
    longbridge = next(item for item in HONG_KONG_MARKET_ADAPTER.providers if item.name == "Longbridge")
    adapter = replace(
        HONG_KONG_MARKET_ADAPTER,
        providers=(replace(longbridge, status=ProviderStatus.INTEGRATED),),
    )
    now = datetime(2026, 8, 15, tzinfo=timezone.utc)
    health = {
        "Longbridge": ProviderHealth(
            healthy=True,
            validated=True,
            completed_bars=True,
            updated_at=now.isoformat(),
            coverage_pct=100,
            field_sources={"close": "Longbridge"},
        )
    }

    # 2024-01-01 was an HKEX holiday but is a Monday.  The fallback's weekday
    # answer demonstrates why it must never be presented as exchange-verified.
    assert adapter.calendar.is_trading_day(date(2024, 1, 1)) is True
    capabilities = adapter.capability_matrix()
    assert capabilities["calendar_name"] == "weekday_fallback"
    assert capabilities["calendar_source"] == "local_weekday_fallback"
    assert capabilities["calendar_kind"] == "weekday_fallback"
    assert capabilities["calendar_verified"] is False
    assert capabilities["calendar_status"] == "unverified_fallback"
    assert capabilities["calendar_automation_eligible"] is False
    assert capabilities["automatic_push_declared_by_adapter"] is True
    assert capabilities["automatic_push_supported"] is False
    assert adapter.supports_scheduled_daily_report is False

    result = adapter.automatic_push_eligibility(health, granularity="1d", now=now)
    assert result.eligible is False
    assert "verified exchange calendar is required for automatic push" in result.reasons


def test_market_disabled_for_automatic_push_stays_disabled_with_qualified_inputs() -> None:
    tushare = next(item for item in A_SHARE_MARKET_ADAPTER.providers if item.name == "Tushare Pro")
    adapter = replace(
        A_SHARE_MARKET_ADAPTER,
        calendar=TradingCalendar(
            name="fixture_sse_calendar",
            source="fixture_exchange_schedule",
            verified=True,
            kind="verified_exchange",
        ),
        providers=(replace(tushare, status=ProviderStatus.INTEGRATED),),
    )
    now = datetime(2026, 8, 15, tzinfo=timezone.utc)
    health = {
        "Tushare Pro": ProviderHealth(
            healthy=True,
            validated=True,
            updated_at=now.isoformat(),
            coverage_pct=100,
            field_sources={"close": "Tushare Pro"},
        )
    }

    result = adapter.automatic_push_eligibility(health, granularity="1d", now=now)

    assert result.eligible is False
    assert "automatic push is disabled for this market" in result.reasons


def test_validation_exposes_hard_gates_and_survivorship_requirement() -> None:
    history = {"600519": [
        {"date": (date(2020, 1, 1) + timedelta(days=index)).isoformat(), "open": 100, "close": 100 + index * 0.01}
        for index in range(1_700)
    ]}
    result = walk_forward_validate(
        history,
        {"momentum": {"enabled": True, "weight": 1}},
        min_history_months=54,
        train_months=24,
        out_of_sample_months=6,
        step_months=6,
    ).as_dict()

    assert result["required_windows"] == 3
    assert result["hard_gates"]["max_drawdown"] == 0.25
    assert result["hard_gates"]["annualized_turnover"] == 12.0
    assert "survivorship_bias_control_required" in result["reasons"]
    assert "benchmark_total_return_series_required" in result["reasons"]
    assert result["execution_contract"]["execution_rule"] == "signal_at_close_then_next_tradable_bar_open"
    assert result["calendar"] == "weekday_fallback"
    assert result["calendar_source"] == "local_weekday_fallback"
    assert result["calendar_verified"] is False


def test_sparse_four_and_a_half_year_span_fails_overall_and_every_walk_forward_window() -> None:
    start = date(2020, 1, 1)
    end = date(2024, 8, 1)
    rows: list[dict[str, object]] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            rows.append({"date": current.isoformat(), "open": 100, "close": 101})
        current += timedelta(days=30)
    benchmark = [
        {"date": item["date"], "total_return_index": 100 + index}
        for index, item in enumerate(rows)
    ]

    result = walk_forward_validate(
        {"600519": rows},
        {"momentum": {"enabled": True, "weight": 1}},
        benchmark_history={"000300": benchmark},
        survivorship_bias_control=True,
        universe_snapshot_ref=_VALID_UNIVERSE_REF,
    ).as_dict()

    assert result["passed"] is False
    assert result["history_end"] >= "2024-07-01"
    assert result["coverage_pct"]["600519"] < MIN_HISTORY_COVERAGE_PCT
    assert "history_coverage_below_minimum" in result["reasons"]
    assert result["windows"]
    assert all(window["passed"] is False for window in result["windows"])
    assert all(
        "window_history_coverage_below_minimum" in window["reason"]
        for window in result["windows"]
    )


def test_validation_uses_versioned_execution_model_and_benchmark_contract() -> None:
    bars = [
        {"date": (date(2020, 1, 1) + timedelta(days=index)).isoformat(), "open": 100, "close": 101}
        for index in range(1_700)
    ]
    contract = {
        "market": "CN",
        "source": "fixture-provider-v1",
        "execution_rule": "signal_at_close_then_next_tradable_bar_open",
        "annualization_days": 252,
        "benchmark": "fixture-total-return",
        "benchmark_source": "fixture-provider-v1",
        "cost_model": {
            "version": "broker-fixture-v2",
            "commission_rate": 0.0002,
            "stamp_tax_rate": 0.001,
            "buy_slippage": 0.001,
            "sell_slippage": 0.001,
            "min_commission": 5,
        },
    }
    result = walk_forward_validate(
        {"600519": bars},
        {"momentum": {"enabled": True, "weight": 1}},
        min_history_months=1,
        train_months=1,
        out_of_sample_months=1,
        step_months=1,
        required_windows=1,
        survivorship_bias_control=True,
        universe_snapshot_ref=_VALID_UNIVERSE_REF,
        execution_contract=contract,
        benchmark_history={"000300": bars},
    ).as_dict()

    assert result["cost_model_version"] == "broker-fixture-v2"
    assert result["execution_contract"]["source"] == "fixture-provider-v1"
    assert result["execution_contract"]["cost_model"]["buy_slippage"] == 0.001
    assert "benchmark_total_return_series_required" not in result["reasons"]


def test_validation_enters_at_the_next_bar_open(monkeypatch) -> None:
    from decision.domain import DecisionEvaluation

    monkeypatch.setattr(
        "decision.validation.builtin_strategy_outputs",
        lambda _bars, _names: [{
            "strategy_name": "momentum",
            "normalized_score": 80,
            "confidence": 1,
            "data_quality": 1,
        }],
    )
    calls = 0

    def score_once(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return DecisionEvaluation(
            action="buy_candidate" if calls == 1 else "hold",
            score=80 if calls == 1 else 50,
            valid=True,
            stale=False,
            risk_veto=False,
            reason_codes=(),
            contributions=(),
        )

    monkeypatch.setattr("decision.validation.score_strategy_outputs", score_once)
    bars = [
        {
            "date": (date(2020, 1, 1) + timedelta(days=index)).isoformat(),
            "open": 10 if index == 0 else 200,
            "close": 10 if index == 0 else 210,
        }
        for index in range(100)
    ]
    result = walk_forward_validate(
        {"600519": bars},
        {"momentum": {"enabled": True, "weight": 1}},
        min_history_months=1,
        train_months=1,
        out_of_sample_months=1,
        step_months=1,
        required_windows=1,
        survivorship_bias_control=True,
        universe_snapshot_ref=_VALID_UNIVERSE_REF,
        cost_model={
            "version": "fixture-no-cost-v1",
            "commission_rate": 0,
            "stamp_tax_rate": 0,
            "buy_slippage": 0,
            "sell_slippage": 0,
            "min_commission": 0,
        },
        benchmark_history={"000300": [{"date": item["date"], "total_return_index": 100} for item in bars]},
    ).as_dict()

    window = result["windows"][0]
    assert window["signals"] > 0
    expected = (1.05 ** (252 / window["trading_days"])) - 1
    assert window["annualized_return"] == pytest.approx(expected)


def test_candidate_selection_is_deterministic_and_applies_all_hard_limits() -> None:
    result = select_weight_candidate(
        {"version_id": "current", "oos_annualized_return": 0.05},
        [
            {"candidate_id": "valid", "weights": {"momentum": 1}, "frozen_sample_ref": "validation-evidence-1", "oos_annualized_return": 0.08, "max_drawdown": 0.10, "annualized_turnover": 3, "max_single_asset_weight": 0.15},
            {"candidate_id": "drawdown", "weights": {"momentum": 1}, "oos_annualized_return": 0.10, "max_drawdown": 0.30, "annualized_turnover": 2, "max_single_asset_weight": 0.15},
            {"candidate_id": "schema-free-text", "oos_annualized_return": 0.20, "max_drawdown": 0.01, "annualized_turnover": 1, "max_single_asset_weight": 0.10},
        ],
    )

    assert result["selected_candidate_id"] == "valid"
    rejected = {item["candidate_id"]: item["reasons"] for item in result["candidates"]}
    assert "max_drawdown_exceeded" in rejected["drawdown"]
    assert "candidate_schema_invalid" in rejected["schema-free-text"]


def test_validation_marks_out_of_order_bars_as_not_lookahead_safe() -> None:
    history = {
        "600519": [
            {"date": "2024-01-03", "open": 10, "close": 10.2},
            {"date": "2024-01-02", "open": 10, "close": 10.1},
        ]
    }
    result = walk_forward_validate(
        history,
        {"momentum": {"enabled": True, "weight": 1}},
        min_history_months=1,
        train_months=1,
        out_of_sample_months=1,
        step_months=1,
        required_windows=1,
        survivorship_bias_control=True,
        universe_snapshot_ref=_VALID_UNIVERSE_REF,
    ).as_dict()
    assert result["lookahead_safe"] is False
    assert "600519:bars_out_of_order" in result["reasons"]
    assert result["passed"] is False


def test_validation_requires_a_frozen_universe_reference_when_survivorship_control_is_on() -> None:
    result = walk_forward_validate(
        {},
        {"momentum": {"enabled": True, "weight": 1}},
        survivorship_bias_control=True,
        universe_snapshot_ref=None,
    ).as_dict()

    assert "universe_snapshot_ref_required" in result["reasons"]
    assert result["passed"] is False


@pytest.mark.parametrize(
    "reference",
    ("latest", "fixture-universe-v1", "../../mutable-universe", "sha256:not-a-digest"),
)
def test_validation_rejects_arbitrary_nonempty_universe_references(reference: str) -> None:
    result = walk_forward_validate(
        {},
        {"momentum": {"enabled": True, "weight": 1}},
        survivorship_bias_control=True,
        universe_snapshot_ref=reference,
    ).as_dict()

    assert is_valid_universe_snapshot_ref(reference) is False
    assert result["universe_snapshot_ref"] is None
    assert "universe_snapshot_ref_invalid" in result["reasons"]
    assert result["passed"] is False


def test_worker_portfolios_require_workspace_automation_permission(tmp_path: Path) -> None:
    store = DecisionStore(tmp_path / "decisions.db")
    disabled_workspace = store.create_portfolio("workspace-disabled", "CN", "关闭工作区")
    enabled_workspace = store.create_portfolio("workspace-enabled", "CN", "开启工作区")
    store.set_auto_push("workspace-disabled", disabled_workspace["id"], True)
    store.set_auto_push("workspace-enabled", enabled_workspace["id"], True)

    flags = {"workspace-disabled": False, "workspace-enabled": True}
    selected = store.list_portfolios_for_worker(lambda workspace_id: flags[workspace_id])

    assert [item["id"] for item in selected] == [enabled_workspace["id"]]
    assert store.list_portfolios_for_worker() == []


def test_decision_store_rejects_cross_workspace_references(tmp_path: Path) -> None:
    store = DecisionStore(tmp_path / "decisions.db")
    portfolio_a = store.create_portfolio("workspace-a", "CN", "组合 A")
    portfolio_b = store.create_portfolio("workspace-b", "CN", "组合 B")
    version_a = store.create_version("workspace-a", portfolio_a["id"], {"strategies": [{"strategy_name": "a", "weight": 1}]})
    version_b = store.create_version("workspace-b", portfolio_b["id"], {"strategies": [{"strategy_name": "b", "weight": 1}]})
    member_a = store.add_member("workspace-a", portfolio_a["id"], "A")
    member_b = store.add_member("workspace-b", portfolio_b["id"], "B")
    snapshot_a = store.create_snapshot(
        "workspace-a",
        version_a["id"],
        {"members": [{"membership_id": member_a["id"], "symbol": "A"}]},
        "fixture",
        "ok",
    )
    snapshot_b = store.create_snapshot(
        "workspace-b",
        version_b["id"],
        {"members": [{"membership_id": member_b["id"], "symbol": "B"}]},
        "fixture",
        "ok",
    )
    target_a = store.create_target("workspace-a", "wecom_robot", "目标 A", {"secret_ref": "env://A"})
    target_b = store.create_target("workspace-b", "wecom_robot", "目标 B", {"secret_ref": "env://B"})

    with pytest.raises(KeyError, match="portfolio_version_not_found"):
        store.create_snapshot("workspace-b", version_a["id"], {"members": []}, "fixture", "ok")

    with pytest.raises(ValueError, match="decision_run_reference_mismatch"):
        store.create_run("workspace-b", portfolio_b["id"], version_a["id"], snapshot_b["id"], "cross-version", "manual", "manual")
    with pytest.raises(ValueError, match="decision_run_reference_mismatch"):
        store.create_run("workspace-b", portfolio_b["id"], version_b["id"], snapshot_a["id"], "cross-snapshot", "manual", "manual")

    run_a = store.create_run("workspace-a", portfolio_a["id"], version_a["id"], snapshot_a["id"], "workspace-a-run", "manual", "manual")
    with pytest.raises(ValueError, match="decision_membership_run_mismatch"):
        store.record_decision(run_a["id"], member_b["id"], {"symbol": "B", "action": "hold"})

    with pytest.raises(ValueError, match="notification_route_workspace_mismatch"):
        store.create_route("workspace-a", portfolio_a["id"], target_b["id"], "scheduled")
    with pytest.raises(ValueError, match="notification_route_workspace_mismatch"):
        store.create_route("workspace-b", portfolio_b["id"], target_a["id"], "scheduled")

    decision_a = store.record_decision(run_a["id"], member_a["id"], {"symbol": "A", "action": "hold", "valid": True})
    report_a = store.create_report(run_a, snapshot_a, version_a, [decision_a], "manual")
    forged_decision = {**decision_a, "action": "major_risk"}
    with pytest.raises(ValueError, match="decision_report_decision_reference_mismatch"):
        store.create_report(run_a, snapshot_a, version_a, [forged_decision], "manual")
    with pytest.raises(ValueError, match="decision_report_snapshot_reference_mismatch"):
        store.create_report(run_a, {**snapshot_a, "payload_hash": "forged"}, version_a, [decision_a], "manual")
    run_b = store.create_run("workspace-b", portfolio_b["id"], version_b["id"], snapshot_b["id"], "workspace-b-run", "manual", "manual")
    decision_b = store.record_decision(run_b["id"], member_b["id"], {"symbol": "B", "action": "hold", "valid": True})
    with pytest.raises(ValueError, match="decision_report_snapshot_reference_mismatch"):
        store.create_report(run_a, snapshot_b, version_a, [decision_a], "manual")
    with pytest.raises(ValueError, match="decision_report_version_reference_mismatch"):
        store.create_report(run_a, snapshot_a, version_b, [decision_a], "manual")
    with pytest.raises(ValueError, match="decision_report_decisions_incomplete"):
        store.create_report(run_a, snapshot_a, version_a, [decision_b], "manual")
    with pytest.raises(ValueError, match="decision_report_run_reference_mismatch"):
        store.create_report({**run_a, "workspace_id": "workspace-b"}, snapshot_a, version_a, [decision_a], "manual")
    with pytest.raises(ValueError, match="delivery_reference_workspace_mismatch"):
        store.claim_delivery("workspace-b", report_a["id"], target_b["id"], "cross-delivery", "owner-b")
    with pytest.raises(ValueError, match="delivery_reference_workspace_mismatch"):
        store.record_delivery_attempt("workspace-b", report_a["id"], target_a["id"], "cross-attempt", "failed")


def test_members_use_market_identity_without_changing_legacy_display_code(tmp_path: Path) -> None:
    store = DecisionStore(tmp_path / "decisions.db")
    portfolio = store.create_portfolio("workspace", "a", "组合")

    first = store.add_member("workspace", portfolio["id"], "sh600519")
    second = store.add_member("workspace", portfolio["id"], "600519")

    assert portfolio["market"] == "CN"
    assert first["id"] == second["id"]
    assert first["instrument_id"] == "SH.600519"
    assert first["symbol"] == "600519"


def test_completed_decision_runs_are_append_only(tmp_path: Path) -> None:
    store = DecisionStore(tmp_path / "decisions.db")
    portfolio = store.create_portfolio("workspace", "CN", "组合")
    version = store.create_version("workspace", portfolio["id"], {"strategies": [{"strategy_name": "a", "weight": 1}]})
    member = store.add_member("workspace", portfolio["id"], "A")
    snapshot = store.create_snapshot(
        "workspace",
        version["id"],
        {"members": [{"membership_id": member["id"], "symbol": "A"}]},
        "fixture",
        "ok",
    )
    run = store.create_run("workspace", portfolio["id"], version["id"], snapshot["id"], "append-only", "manual", "manual")
    payload = {"symbol": "A", "action": "hold", "valid": True}
    store.record_decision(run["id"], member["id"], payload)
    store.complete_run(run["id"])

    with pytest.raises(RuntimeError, match="decision_run_not_writable"):
        store.record_decision(run["id"], member["id"], {**payload, "action": "major_risk"})


def test_provider_health_rejects_overcoverage_and_future_timestamps() -> None:
    from data.markets import HONG_KONG_MARKET_ADAPTER, ProviderStatus
    from dataclasses import replace

    provider = next(item for item in HONG_KONG_MARKET_ADAPTER.providers if item.name == "Longbridge")
    adapter = replace(HONG_KONG_MARKET_ADAPTER, providers=(replace(provider, status=ProviderStatus.INTEGRATED),))
    health = {
        "Longbridge": {
            "healthy": True,
            "validated": True,
            "completed_bars": True,
            "coverage_pct": 101,
            "updated_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
            "field_sources": {"close": "Longbridge"},
        }
    }
    assert adapter.automatic_push_eligibility(health, granularity="5m").eligible is False

    future = dict(health["Longbridge"])
    future["coverage_pct"] = 100
    future["updated_at"] = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    assert adapter.automatic_push_eligibility({"Longbridge": future}, granularity="5m").eligible is False


def test_delivery_claim_is_not_reentrant_for_the_same_owner(tmp_path: Path) -> None:
    store = DecisionStore(tmp_path / "decisions.db")
    portfolio = store.create_portfolio("workspace", "CN", "组合")
    version = store.create_version("workspace", portfolio["id"], {"strategies": [{"strategy_name": "a", "weight": 1}]})
    member = store.add_member("workspace", portfolio["id"], "A")
    snapshot = store.create_snapshot(
        "workspace",
        version["id"],
        {"members": [{"membership_id": member["id"], "symbol": "A"}]},
        "fixture",
        "ok",
    )
    run = store.create_run("workspace", portfolio["id"], version["id"], snapshot["id"], "claim-run", "manual", "manual")
    decision = store.record_decision(run["id"], member["id"], {"symbol": "A", "action": "hold", "valid": True})
    report = store.create_report(run, snapshot, version, [decision], "manual")
    target = store.create_target("workspace", "wecom_robot", "目标", {"secret_ref": "env://TARGET"})

    first = store.claim_delivery("workspace", report["id"], target["id"], "same-key", "owner")
    second = store.claim_delivery("workspace", report["id"], target["id"], "same-key", "owner")

    assert first["claimed"] is True
    assert second["claimed"] is False
    assert second["reason"] == "claimed_by_self"


def _delivery_fixture(tmp_path: Path) -> tuple[DecisionStore, dict[str, object], dict[str, object], dict[str, object]]:
    store = DecisionStore(tmp_path / "decisions.db")
    portfolio = store.create_portfolio("workspace", "CN", "组合")
    version = store.create_version("workspace", portfolio["id"], {"strategies": [{"strategy_name": "a", "weight": 1}]})
    member = store.add_member("workspace", portfolio["id"], "A")
    snapshot = store.create_snapshot(
        "workspace",
        version["id"],
        {"members": [{"membership_id": member["id"], "symbol": "A"}]},
        "fixture",
        "ok",
    )
    run = store.create_run("workspace", portfolio["id"], version["id"], snapshot["id"], "delivery-run", "manual", "manual")
    decision = store.record_decision(run["id"], member["id"], {"symbol": "A", "action": "hold", "valid": True})
    report = store.create_report(run, snapshot, version, [decision], "manual")
    target = store.create_target("workspace", "wecom_robot", "目标", {"secret_ref": "env://TARGET"})
    return store, report, target, portfolio


def test_delivery_claim_serializes_competing_owners(tmp_path: Path) -> None:
    store, report, target, _ = _delivery_fixture(tmp_path)

    def claim(owner: str) -> dict[str, object]:
        return store.claim_delivery("workspace", report["id"], target["id"], "concurrent-key", owner)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, ("owner-a", "owner-b")))

    assert sum(bool(result["claimed"]) for result in results) == 1
    assert {result.get("reason") for result in results if not result["claimed"]} == {"claimed"}


def test_delivery_attempt_numbers_are_serialized_for_concurrent_retries(tmp_path: Path) -> None:
    store, report, target, _ = _delivery_fixture(tmp_path)

    def record(_: int) -> dict[str, object]:
        return store.record_delivery_attempt("workspace", report["id"], target["id"], "concurrent-attempt", "failed", error="fixture")

    with ThreadPoolExecutor(max_workers=2) as pool:
        attempts = list(pool.map(record, (1, 2)))

    assert {int(item["attempt_no"]) for item in attempts} == {1, 2}
    assert len(store.list_delivery_attempts("workspace", report["id"])) == 2


def test_invalid_worker_fence_does_not_append_delivery_attempt(tmp_path: Path, monkeypatch) -> None:
    from decision.delivery import DecisionDeliveryService
    from engine.events.models import DomainEvent
    from engine.notifications.models import DeliveryResult

    store, report, target, portfolio = _delivery_fixture(tmp_path)
    store.mark_target_test("workspace", target["id"], "passed")
    store.create_route("workspace", portfolio["id"], target["id"], "state_change")
    monkeypatch.setenv("DECISION_EXTERNAL_DELIVERY_ENABLED", "true")
    fence = {"valid": True}

    class FakeAdapter:
        def send(self, _event):
            fence["valid"] = False
            return DeliveryResult(delivered=True, details={"fixture": True})

    def check_fence() -> None:
        if not fence["valid"]:
            raise RuntimeError("decision worker lease fence token is no longer valid")

    service = DecisionDeliveryService(
        store,
        owner_id="worker-a",
        worker_owned=True,
        fence_token_provider=lambda: "fence-a",
        fence_check=check_fence,
        eligibility_check=lambda _workspace_id, _portfolio_id: {"eligible": True},
    )
    service._adapter = lambda _target: FakeAdapter()
    event = DomainEvent.create(
        "decision.report.state_change",
        portfolio["id"],
        {"changes": [{"symbol": "A", "action": "hold"}]},
        idempotency_key="fixture-fence-event",
    )

    with pytest.raises(RuntimeError, match="fence token"):
        service._deliver_event("workspace", report["id"], event)

    assert service._fence_token() == "fence-a"
    assert store.list_delivery_attempts("workspace", report["id"]) == []


def test_stale_worker_cannot_overwrite_new_owner_heartbeat(tmp_path: Path) -> None:
    now = datetime(2026, 8, 14, 0, 0, tzinfo=timezone.utc)
    first = SQLiteWorkerLease(tmp_path / "worker.db")
    second = SQLiteWorkerLease(tmp_path / "worker.db")
    try:
        acquired = first.acquire("owner-a", ttl_seconds=10, now=now)
        assert acquired is not None
        assert first.heartbeat("owner-a", fence_token=acquired.fence_token, status="ready", now=now) is True

        reclaimed = second.acquire("owner-b", ttl_seconds=10, now=now + timedelta(seconds=11))
        assert reclaimed is not None
        assert first.heartbeat("owner-a", fence_token=acquired.fence_token, status="ready", now=now + timedelta(seconds=12)) is False

        stale_readiness = second.readiness(now=now + timedelta(seconds=12))
        assert stale_readiness["ready"] is False
        assert stale_readiness["owner_id"] == "owner-a"
        assert stale_readiness["lease_matches"] is False

        assert second.heartbeat("owner-b", fence_token=reclaimed.fence_token, status="ready", now=now + timedelta(seconds=12)) is True
        ready = second.readiness(now=now + timedelta(seconds=12))
        assert ready["ready"] is True
        assert ready["owner_id"] == "owner-b"
    finally:
        first.close()
        second.close()


def test_runtime_worker_callbacks_apply_workspace_automation_permission(tmp_path: Path) -> None:
    store = DecisionStore(tmp_path / "decisions.db")
    disabled = store.create_portfolio("workspace-disabled", "CN", "关闭工作区")
    enabled = store.create_portfolio("workspace-enabled", "US", "开启工作区")
    store.set_auto_push("workspace-disabled", disabled["id"], True)
    store.set_auto_push("workspace-enabled", enabled["id"], True)
    runtime = DecisionRuntime(
        store,
        object(),
        workspace_automation_enabled=lambda workspace_id: workspace_id == "workspace-enabled",
    )

    contexts = runtime.worker_callbacks().schedule_contexts(datetime(2026, 8, 14, tzinfo=timezone.utc))

    assert [market for market, _local in contexts] == ["US"]


def test_worker_runs_due_slots_in_each_market_context(tmp_path: Path) -> None:
    current = datetime(2026, 8, 14, 12, 30, tzinfo=timezone.utc)
    prepared: list[tuple[str, str]] = []
    callbacks = WorkerCallbacks(
        is_trading_day=lambda _when: True,
        schedule_contexts=lambda now: (
            ("CN", now.astimezone(ZoneInfo("Asia/Shanghai"))),
            ("US", now.astimezone(ZoneInfo("America/New_York"))),
        ),
        prepare_for_context=lambda **kwargs: prepared.append((kwargs["market"], kwargs["slot"])),
    )
    worker = DecisionWorker(
        SQLiteWorkerLease(tmp_path / "worker.db"),
        SQLiteOutbox(tmp_path / "events.db"),
        callbacks=callbacks,
        poll_interval_seconds=60,
    )
    try:
        assert worker.acquire(now=current) is True
        tick = worker.tick(now=current)
    finally:
        worker.close()

    assert prepared == [("US", "morning")]
    assert tick.prepared_slots == ("US:morning",)


def test_worker_slot_completion_survives_restart(tmp_path: Path) -> None:
    now = datetime(2026, 8, 14, 0, 30, tzinfo=timezone.utc)
    prepared: list[str] = []
    callbacks = WorkerCallbacks(
        is_trading_day=lambda _when: True,
        prepare=lambda **kwargs: prepared.append(str(kwargs["slot"])),
    )
    first = DecisionWorker(
        SQLiteWorkerLease(tmp_path / "worker.db"),
        SQLiteOutbox(tmp_path / "events.db"),
        callbacks=callbacks,
        poll_interval_seconds=60,
    )
    try:
        assert first.acquire(now=now) is True
        tick = first.tick(now=now)
        assert tick.prepared_slots == ("morning",)
    finally:
        first.close()

    second = DecisionWorker(
        SQLiteWorkerLease(tmp_path / "worker.db"),
        SQLiteOutbox(tmp_path / "events.db"),
        callbacks=callbacks,
        poll_interval_seconds=60,
    )
    try:
        assert second.acquire(now=now + timedelta(seconds=30)) is True
        replay = second.tick(now=now + timedelta(seconds=30))
    finally:
        second.close()

    assert prepared == ["morning"]
    assert replay.prepared_slots == ()


def test_worker_renews_lease_during_a_long_synchronous_callback(tmp_path: Path) -> None:
    callbacks = WorkerCallbacks(
        is_trading_day=lambda _when: True,
        prepare=lambda **_kwargs: time.sleep(2.4),
    )
    worker = DecisionWorker(
        SQLiteWorkerLease(tmp_path / "worker.db"),
        SQLiteOutbox(tmp_path / "events.db"),
        callbacks=callbacks,
        lease_ttl_seconds=1.2,
        poll_interval_seconds=60,
    )
    worker._slots_due = lambda slots, *_args, **_kwargs: ("morning",) if tuple(slots) == PREPARATION_SLOTS else ()
    try:
        assert worker.acquire() is True
        tick = worker.tick()
    finally:
        worker.close()

    assert tick.skipped is False
    assert tick.prepared_slots == ("morning",)


def test_failed_preparation_does_not_mark_the_slot_processed(tmp_path: Path) -> None:
    callbacks = WorkerCallbacks(
        is_trading_day=lambda _when: True,
        prepare=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("fixture preparation failed")),
    )
    worker = DecisionWorker(
        SQLiteWorkerLease(tmp_path / "worker.db"),
        SQLiteOutbox(tmp_path / "events.db"),
        callbacks=callbacks,
        poll_interval_seconds=60,
    )
    worker._slots_due = lambda slots, *_args, **_kwargs: ("morning",) if tuple(slots) == PREPARATION_SLOTS else ()
    now = datetime(2026, 8, 14, 0, 0, tzinfo=timezone.utc)
    try:
        assert worker.acquire(now=now) is True
        with pytest.raises(RuntimeError, match="fixture preparation failed"):
            worker.tick(now=now)
        assert worker._processed_slots == set()
    finally:
        worker.close()


def test_worker_fence_token_rejects_a_reclaimed_lease(tmp_path: Path) -> None:
    first = SQLiteWorkerLease(tmp_path / "worker.db")
    second = SQLiteWorkerLease(tmp_path / "worker.db")
    acquired = first.acquire("owner-a", ttl_seconds=10, now=datetime(2026, 8, 14, 0, 0, tzinfo=timezone.utc))
    assert acquired is not None
    reclaimed = second.acquire("owner-b", ttl_seconds=10, now=datetime(2026, 8, 14, 0, 0, 11, tzinfo=timezone.utc))
    assert reclaimed is not None
    assert reclaimed.fence_token != acquired.fence_token
    assert first.renew("owner-a", fence_token=acquired.fence_token, now=datetime(2026, 8, 14, 0, 0, 12, tzinfo=timezone.utc)) is None
    assert first.release("owner-a", fence_token=acquired.fence_token) is False
    assert second.current().fence_token == reclaimed.fence_token
    first.close()
    second.close()


def test_worker_fence_rejects_an_expired_lease_even_when_token_matches(tmp_path: Path) -> None:
    now = datetime(2026, 8, 14, 0, 0, tzinfo=timezone.utc)
    worker = DecisionWorker(
        SQLiteWorkerLease(tmp_path / "worker.db"),
        SQLiteOutbox(tmp_path / "events.db"),
        lease_ttl_seconds=10,
        poll_interval_seconds=60,
    )
    try:
        assert worker.acquire(now=now) is True
        with pytest.raises(RuntimeError, match="fence token"):
            worker._assert_fence(now=now + timedelta(seconds=10))
        assert worker.owns_lease is False
        assert worker.fence_token == ""
    finally:
        worker.close()


def test_worker_stops_when_running_heartbeat_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 8, 14, 0, 0, tzinfo=timezone.utc)
    worker = DecisionWorker(
        SQLiteWorkerLease(tmp_path / "worker.db"),
        SQLiteOutbox(tmp_path / "events.db"),
        poll_interval_seconds=60,
    )
    try:
        assert worker.acquire(now=now) is True
        monkeypatch.setattr(worker.lease, "heartbeat", lambda *_args, **_kwargs: False)
        tick = worker.tick(now=now + timedelta(seconds=1))
        assert tick.skipped is True
        assert worker.owns_lease is False
        assert worker.fence_token == ""
    finally:
        worker.close()


def test_worker_stops_when_ready_heartbeat_is_rejected_after_work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 8, 14, 0, 0, tzinfo=timezone.utc)
    heartbeat_statuses: list[str] = []
    worker = DecisionWorker(
        SQLiteWorkerLease(tmp_path / "worker.db"),
        SQLiteOutbox(tmp_path / "events.db"),
        poll_interval_seconds=60,
    )
    try:
        assert worker.acquire(now=now) is True

        def heartbeat(*_args, **kwargs) -> bool:
            status = str(kwargs.get("status") or "")
            heartbeat_statuses.append(status)
            return status != "ready"

        monkeypatch.setattr(worker.lease, "heartbeat", heartbeat)
        tick = worker.tick(now=now + timedelta(seconds=1))
        assert tick.skipped is True
        assert heartbeat_statuses == ["running", "ready"]
        assert worker.owns_lease is False
    finally:
        worker.close()


def test_worker_runs_daily_backup_hook_at_the_declared_safe_slot(tmp_path: Path) -> None:
    backups: list[str] = []
    callbacks = WorkerCallbacks(
        is_trading_day=lambda _when: True,
        daily_backup=lambda **kwargs: backups.append(kwargs["scheduled_for"].isoformat()),
    )
    worker = DecisionWorker(
        SQLiteWorkerLease(tmp_path / "worker.db"),
        SQLiteOutbox(tmp_path / "events.db"),
        callbacks=callbacks,
        poll_interval_seconds=60,
    )
    try:
        now = datetime(2026, 8, 14, 18, 0, tzinfo=timezone.utc)
        assert worker.acquire(now=now) is True
        tick = worker.tick(now=now)
    finally:
        worker.close()

    assert tick.backup_completed is True
    assert len(backups) == 1


def test_worker_daily_backup_creates_a_manifest_from_local_databases(tmp_path: Path, monkeypatch) -> None:
    import config.settings as settings

    database_dir = tmp_path / "db"
    database_dir.mkdir()
    backup_dir = tmp_path / "backups"
    monkeypatch.setattr(settings, "DB_DIR", database_dir)
    monkeypatch.setenv("DECISION_BACKUP_DIR", str(backup_dir))
    store = DecisionStore(database_dir / "decisions.db")
    lease = SQLiteWorkerLease(database_dir / "worker_leases.db")
    outbox = SQLiteOutbox(database_dir / "events.db")
    worker = DecisionWorker(lease, outbox, poll_interval_seconds=60)
    try:
        result = worker._run_daily_backup(scheduled_for=datetime(2026, 8, 15, 2, tzinfo=timezone.utc))
    finally:
        worker.close()

    assert result["status"] == "created"
    assert (backup_dir / "2026-08-15" / "manifest.json").is_file()
    del store


def test_report_delivery_summary_is_bounded_and_idempotent() -> None:
    from decision.delivery import DecisionDeliveryService

    body = {
        "portfolio_id": "portfolio-1",
        "quality_status": "ok",
        "decisions": [
            {"symbol": str(index), "action": "watch", "confirmed": True, "previous_action": "hold"}
            for index in range(20)
        ],
    }
    report = {"id": "report-1", "decision_run_id": "run-1", "report_hash": "hash-1", "body": body}
    event = DecisionDeliveryService._event(report, "state_change", "/report/share-1")
    assert len(event.payload["changes"]) == 10
    assert event.payload["report_url"] == "/report/share-1"
    assert DecisionDeliveryService._event(report, "state_change", "/report/share-1").idempotency_key == event.idempotency_key
