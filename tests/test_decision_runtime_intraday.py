from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

import decision.runtime as runtime_module
from data.markets import ProviderHealth
from decision.runtime import DecisionRuntime
from decision.store import DecisionStore
from engine.events.outbox import SQLiteOutbox


OBSERVED_AT = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)


def _bars(*, count: int = 30) -> list[dict[str, Any]]:
    start = OBSERVED_AT - timedelta(minutes=5 * count)
    rows: list[dict[str, Any]] = []
    for index in range(count):
        end = start + timedelta(minutes=5 * index)
        text = end.isoformat()
        rows.append(
            {
                "date": text,
                "bar_end": text,
                "open": 10.0,
                "high": 11.0,
                "low": 9.0,
                "close": 10.5,
                "volume": 1_000.0,
                "completed": True,
            }
        )
    return rows


class _FixtureAdapter:
    def __init__(self, eligible: bool) -> None:
        self.eligible = eligible
        self.canonical = self
        self.market = "CN"

    def automatic_push_eligibility(self, *_args: Any, **_kwargs: Any) -> Any:
        return SimpleNamespace(
            eligible=self.eligible,
            qualified_provider="FixtureProvider" if self.eligible else None,
            reasons=() if self.eligible else ("fixture_provider_not_qualified",),
            granularity=str(_kwargs.get("granularity") or "5m"),
        )

    def capabilities(self) -> dict[str, Any]:
        return {
            "market": "CN",
            "source": "fixture",
            "source_status": "integrated",
            "calendar_status": "verified_exchange",
        }


class _Frame:
    empty = False

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def tail(self, count: int) -> "_Frame":
        return _Frame(self.rows[-count:])

    def iterrows(self):
        return enumerate(self.rows)


class _DailyStorage:
    def get_stock_daily(self, _symbol: str) -> _Frame:
        return _Frame(_bars())


def _healthy_provider() -> ProviderHealth:
    return ProviderHealth(
        healthy=True,
        validated=True,
        completed_bars=True,
        updated_at="2026-08-14T11:55:00+00:00",
        coverage_pct=100.0,
        field_sources={"close": "FixtureProvider", "volume": "FixtureProvider"},
    )


def _runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    loader: Callable[..., Any] | None,
    eligible: bool = True,
    strategy_output: Callable[[list[dict[str, Any]], set[str]], list[dict[str, Any]]] | None = None,
    storage: Any | None = None,
) -> tuple[DecisionRuntime, DecisionStore, SQLiteOutbox, dict[str, Any], dict[str, Any]]:
    store = DecisionStore(tmp_path / "decisions.db")
    portfolio = store.create_portfolio("workspace", "CN", "Intraday fixture")
    store.create_version(
        "workspace",
        portfolio["id"],
        {"strategies": [{"strategy_name": "momentum", "version": "v1", "weight": 1, "enabled": True}]},
    )
    member = store.add_member("workspace", portfolio["id"], "600519")
    store.set_auto_push("workspace", portfolio["id"], True)
    store.update_member_state(
        member["id"],
        action="watch",
        valid=True,
        stale=False,
        quality_status="ok",
        trade_date="2026-08-13",
    )
    outbox = SQLiteOutbox(tmp_path / "events.db")
    runtime = DecisionRuntime(
        store,
        storage if storage is not None else object(),
        workspace_automation_enabled=lambda workspace_id: workspace_id == "workspace",
        intraday_bars_loader=loader,
        outbox=outbox,
    )
    monkeypatch.setattr(runtime_module, "get_market_adapter", lambda _market: _FixtureAdapter(eligible))
    if strategy_output is not None:
        monkeypatch.setattr(runtime_module, "_strategy_outputs", strategy_output)
    return runtime, store, outbox, portfolio, member


def _loader_result(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "provider": "FixtureProvider",
        "provider_status": "integrated",
        "request_hash": "request-hash",
        "response_hash": "response-hash",
        "provider_health": {"FixtureProvider": _healthy_provider()},
        "provider_evidence": {"collected_at": "2026-08-14T11:59:00+00:00", "window": "5m"},
        "bars_by_symbol": {"600519": rows},
    }


def _positive_strategy(bars: list[dict[str, Any]], names: set[str]) -> list[dict[str, Any]]:
    del bars
    return [
        {
            "strategy_name": name,
            "strategy_version": "v1",
            "normalized_score": 80.0,
            "confidence": 1.0,
            "data_quality": 1.0,
            "reason_codes": ["fixture_positive"],
        }
        for name in sorted(names)
    ]


def test_intraday_without_loader_is_fail_closed(tmp_path: Path) -> None:
    runtime = DecisionRuntime(
        DecisionStore(tmp_path / "decisions.db"),
        object(),
        workspace_automation_enabled=lambda _workspace_id: True,
    )

    result = runtime._poll_bars(OBSERVED_AT, market="CN")

    assert result["status"] == "skipped"
    assert result["reason"] == "no_qualified_5m_provider"


def test_intraday_provider_health_gate_precedes_run_creation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _bars()
    runtime, store, outbox, portfolio, _member = _runtime(
        tmp_path,
        monkeypatch,
        loader=lambda **_kwargs: _loader_result(rows),
        eligible=False,
        strategy_output=_positive_strategy,
    )
    try:
        result = runtime._poll_bars(OBSERVED_AT, market="CN")

        assert result["status"] == "skipped"
        assert result["reason"] == "no_qualified_5m_provider"
        assert store.list_reports("workspace", portfolio["id"]) == []
        assert outbox.claim(consumer="intraday-test") == []
    finally:
        outbox.close()


@pytest.mark.parametrize(
    "mutate, expected_reason",
    [
        (lambda rows: rows[-1].pop("completed"), "completed_5m_bars_invalid"),
        (lambda rows: rows[-1].update({"revision": True}), "completed_5m_bars_invalid"),
        (lambda rows: rows[-1].update({"bar_end": (OBSERVED_AT + timedelta(minutes=5)).isoformat(), "date": (OBSERVED_AT + timedelta(minutes=5)).isoformat()}), "completed_5m_bars_invalid"),
        (lambda rows: rows[-1].update({"bar_end": (datetime.fromisoformat(rows[-2]["bar_end"]) + timedelta(minutes=10)).isoformat(), "date": (datetime.fromisoformat(rows[-2]["date"]) + timedelta(minutes=10)).isoformat()}), "two_completed_5m_bars_not_confirmed"),
    ],
)
def test_intraday_rejects_unusable_bar_pairs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutate: Callable[[list[dict[str, Any]]], Any],
    expected_reason: str,
) -> None:
    rows = _bars()
    mutate(rows)
    runtime, store, outbox, portfolio, _member = _runtime(
        tmp_path,
        monkeypatch,
        loader=lambda **_kwargs: _loader_result(rows),
        strategy_output=_positive_strategy,
    )
    try:
        result = runtime._poll_bars(OBSERVED_AT, market="CN")

        assert result["status"] == "blocked"
        assert result["portfolios"] == [{"portfolio_id": portfolio["id"], "status": "blocked", "reason": expected_reason}]
        assert store.list_reports("workspace", portfolio["id"]) == []
        assert outbox.claim(consumer="intraday-test") == []
    finally:
        outbox.close()


def test_intraday_requires_same_action_before_creating_a_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _bars()

    def changing_strategy(bars: list[dict[str, Any]], names: set[str]) -> list[dict[str, Any]]:
        score = 80.0 if len(bars) % 2 == 0 else 20.0
        return [
            {
                "strategy_name": name,
                "strategy_version": "v1",
                "normalized_score": score,
                "confidence": 1.0,
                "data_quality": 1.0,
            }
            for name in sorted(names)
        ]

    runtime, store, outbox, portfolio, _member = _runtime(
        tmp_path,
        monkeypatch,
        loader=lambda **_kwargs: _loader_result(rows),
        strategy_output=changing_strategy,
    )
    try:
        result = runtime._poll_bars(OBSERVED_AT, market="CN")

        assert result["status"] == "blocked"
        assert result["portfolios"][0]["reason"] == "two_completed_5m_bars_not_confirmed"
        assert store.list_reports("workspace", portfolio["id"]) == []
        assert outbox.claim(consumer="intraday-test") == []
    finally:
        outbox.close()


def test_intraday_confirmation_persists_evidence_and_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _bars()
    runtime, store, outbox, portfolio, _member = _runtime(
        tmp_path,
        monkeypatch,
        loader=lambda **_kwargs: _loader_result(rows),
        strategy_output=_positive_strategy,
    )
    try:
        first = runtime._poll_bars(OBSERVED_AT, market="CN")
        second = runtime._poll_bars(OBSERVED_AT, market="CN")

        assert first["status"] == "processed"
        assert second["status"] == "processed"
        first_portfolio = first["portfolios"][0]
        second_portfolio = second["portfolios"][0]
        assert first_portfolio["run_id"] == second_portfolio["run_id"]
        assert first_portfolio["event_ids"] == second_portfolio["event_ids"]
        assert len(store.list_reports("workspace", portfolio["id"])) == 1
        report = store.get_report("workspace", first_portfolio["report_id"])
        assert report is not None
        decision = report["body"]["decisions"][0]
        assert decision["confirmed"] is True
        assert decision["previous_action"] == "watch"
        assert report["body"]["evidence"]["provider"] == "FixtureProvider"
        assert report["body"]["evidence"]["request_hash"] == "request-hash"
        assert report["body"]["evidence"]["response_hash"] == "response-hash"
        assert report["body"]["evidence"]["collected_at"] == "2026-08-14T11:59:00+00:00"
        assert len(first_portfolio["event_ids"]) == 1
        event = outbox.get(first_portfolio["event_ids"][0])
        assert event is not None
        report_url = str(event.event.payload["report_url"])
        assert report_url.startswith("/report/")
        assert report["id"] not in report_url
        token = report_url.rsplit("/", 1)[-1]
        shared = store.resolve_share(token)
        assert shared is not None
        assert shared["report_id"] == report["id"]
        with store._connection() as conn:
            assert conn.execute("SELECT COUNT(*) FROM report_share_links").fetchone()[0] == 1
    finally:
        outbox.close()


def test_intraday_without_a_confirmed_change_does_not_issue_a_share_link(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _bars()

    def stable_strategy(bars: list[dict[str, Any]], names: set[str]) -> list[dict[str, Any]]:
        del bars
        return [
            {
                "strategy_name": name,
                "strategy_version": "v1",
                "normalized_score": 60.0,
                "confidence": 1.0,
                "data_quality": 1.0,
            }
            for name in sorted(names)
        ]

    runtime, store, outbox, portfolio, _member = _runtime(
        tmp_path,
        monkeypatch,
        loader=lambda **_kwargs: _loader_result(rows),
        strategy_output=stable_strategy,
    )
    try:
        result = runtime._poll_bars(OBSERVED_AT, market="CN")

        assert result["status"] == "processed"
        assert all(item.get("event_ids") == [] for item in result["portfolios"])
        with store._connection() as conn:
            assert conn.execute("SELECT COUNT(*) FROM report_share_links").fetchone()[0] == 0
    finally:
        outbox.close()


def test_intraday_accepts_datetime_bar_end_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _bars()
    for row in rows:
        row["bar_end"] = datetime.fromisoformat(row["bar_end"])
    runtime, _store, outbox, _portfolio, _member = _runtime(
        tmp_path,
        monkeypatch,
        loader=lambda **_kwargs: _loader_result(rows),
        strategy_output=_positive_strategy,
    )
    try:
        result = runtime._poll_bars(OBSERVED_AT, market="CN")

        assert result["status"] == "processed"
    finally:
        outbox.close()


def test_intraday_first_major_risk_enqueues_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _bars()

    def risk_strategy(bars: list[dict[str, Any]], names: set[str]) -> list[dict[str, Any]]:
        del bars
        return [
            {
                "strategy_name": name,
                "strategy_version": "v1",
                "normalized_score": 50.0,
                "confidence": 1.0,
                "data_quality": 1.0,
                "risk_veto": True,
                "risk_evidence": {"rule": "fixture_risk"},
            }
            for name in sorted(names)
        ]

    runtime, store, outbox, portfolio, _member = _runtime(
        tmp_path,
        monkeypatch,
        loader=lambda **_kwargs: _loader_result(rows),
        strategy_output=risk_strategy,
    )
    try:
        first = runtime._poll_bars(OBSERVED_AT, market="CN")
        second = runtime._poll_bars(OBSERVED_AT, market="CN")

        first_event_id = first["portfolios"][0]["event_ids"][0]
        assert second["portfolios"][0]["event_ids"] == [first_event_id]
        event = outbox.get(first_event_id)
        assert event is not None
        assert event.event.event_type == "decision.report.major_risk"
        assert len(outbox.claim(consumer="intraday-test")) == 1
        assert outbox.claim(consumer="intraday-test") == []
        assert len(store.list_reports("workspace", portfolio["id"])) == 1
    finally:
        outbox.close()


def test_intraday_first_major_risk_uses_current_input_without_two_bar_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = _bars()

    def current_risk_strategy(bars: list[dict[str, Any]], names: set[str]) -> list[dict[str, Any]]:
        current = len(bars) == len(rows)
        return [
            {
                "strategy_name": name,
                "strategy_version": "v1",
                "normalized_score": 60.0,
                "confidence": 1.0,
                "data_quality": 1.0,
                **(
                    {
                        "risk_veto": True,
                        "risk_evidence": {"rule": "fixture_current_risk"},
                    }
                    if current
                    else {}
                ),
            }
            for name in sorted(names)
        ]

    runtime, store, outbox, portfolio, _member = _runtime(
        tmp_path,
        monkeypatch,
        loader=lambda **_kwargs: _loader_result(rows),
        strategy_output=current_risk_strategy,
    )
    try:
        first = runtime._poll_bars(OBSERVED_AT, market="CN")
        second = runtime._poll_bars(OBSERVED_AT, market="CN")

        first_portfolio = first["portfolios"][0]
        second_portfolio = second["portfolios"][0]
        assert first["status"] == "processed"
        assert first_portfolio["event_ids"]
        assert second_portfolio["event_ids"] == first_portfolio["event_ids"]
        report = store.get_report("workspace", first_portfolio["report_id"])
        assert report is not None
        decision = report["body"]["decisions"][0]
        assert decision["action"] == "major_risk"
        assert decision["confirmed"] is True
        assert decision["confirming_bar_end"] == rows[-1]["bar_end"]
        assert len(outbox.claim(consumer="intraday-current-risk")) == 1
    finally:
        outbox.close()


@pytest.mark.parametrize("keep_other_portfolio_enabled", [False, True])
def test_ineligible_portfolio_disables_auto_push_and_syncs_workspace_switch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    keep_other_portfolio_enabled: bool,
) -> None:
    runtime, store, _outbox, portfolio, _member = _runtime(
        tmp_path,
        monkeypatch,
        loader=None,
    )
    other = store.create_portfolio("workspace", "CN", "Other portfolio") if keep_other_portfolio_enabled else None
    if other is not None:
        store.set_auto_push("workspace", other["id"], True)

    from dashboard.account_store import account_store

    updates: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        account_store,
        "update_workspace_settings",
        lambda workspace_id, settings: updates.append((workspace_id, settings))
        or {"id": workspace_id, "settings": settings},
    )
    monkeypatch.setattr(
        runtime,
        "validate",
        lambda *_args, **_kwargs: {
            "passed": True,
            "lookahead_safe": True,
            "validation_config_issues": [],
        },
    )

    try:
        result = runtime.eligibility("workspace", portfolio["id"])

        assert result["eligible"] is False
        assert store.get_portfolio("workspace", portfolio["id"])["auto_push_enabled"] is False
        assert updates == [("workspace", {"decision_auto_push_enabled": keep_other_portfolio_enabled})]
        if other is not None:
            assert store.get_portfolio("workspace", other["id"])["auto_push_enabled"] is True
    finally:
        runtime.outbox.close()


def test_ineligible_auto_push_does_not_block_manual_analysis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, store, outbox, portfolio, _member = _runtime(
        tmp_path,
        monkeypatch,
        loader=None,
        strategy_output=_positive_strategy,
        storage=_DailyStorage(),
    )
    from dashboard.account_store import account_store

    monkeypatch.setattr(account_store, "update_workspace_settings", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        runtime,
        "validate",
        lambda *_args, **_kwargs: {
            "passed": True,
            "lookahead_safe": True,
            "validation_config_issues": [],
        },
    )

    try:
        runtime.eligibility("workspace", portfolio["id"])
        result = runtime.run(
            "workspace",
            portfolio["id"],
            trigger="manual",
            report_type="manual",
            run_key="manual-after-ineligible",
        )

        assert result["report"] is not None
        assert result["decisions"][0]["valid"] is True
    finally:
        outbox.close()
