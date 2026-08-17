from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from decision.data_quality import validate_bars
from decision.domain import evaluate_decision
from decision.runtime import DecisionRuntime
from decision.store import DecisionStore
from data.markets import get_market_adapter


def _bars(start: date, count: int = 30) -> list[dict[str, object]]:
    return [
        {
            "date": start + timedelta(days=index),
            "open": 10.0 + index,
            "high": 11.0 + index,
            "low": 9.0 + index,
            "close": 10.5 + index,
            "volume": 1000.0,
        }
        for index in range(count)
    ]


def test_bar_quality_rejects_non_finite_duplicate_and_revised_rows() -> None:
    bars = _bars(date(2026, 1, 1))
    bars[4]["close"] = float("nan")
    bars[5]["revision"] = True
    bars[6]["date"] = bars[5]["date"]

    result = validate_bars(bars)

    assert result.valid is False
    assert "duplicate_bar_time" in result.reasons
    assert "bar_5:provider_revision" in result.reasons
    assert any(reason.startswith("bar_4:invalid:close") for reason in result.reasons)
    assert result.field_coverage["close"] < 100


def test_risk_veto_requires_independent_evidence() -> None:
    weights = {"risk": {"enabled": True, "weight": 0, "is_risk_veto": True}}

    bare = evaluate_decision([{"strategy_name": "risk", "risk_veto": True}], weights, confirmed=True)
    evidenced = evaluate_decision(
        [{"strategy_name": "risk", "risk_veto": True, "risk_evidence": {"rule": "drawdown_limit"}}],
        weights,
        confirmed=True,
    )

    assert bare.action == "decision_invalid"
    assert "risk_evidence_missing:risk" in bare.reason_codes
    assert evidenced.action == "major_risk"


class _Frame:
    empty = False

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def tail(self, count: int) -> "_Frame":
        return _Frame(self.rows[-count:])

    def iterrows(self):
        return enumerate(self.rows)


class _Storage:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def get_stock_daily(self, _symbol: str) -> _Frame:
        return _Frame(self.rows)


def test_invalid_feed_keeps_last_action_for_one_trade_date_then_invalidates(tmp_path: Path) -> None:
    store = DecisionStore(tmp_path / "decisions.db")
    portfolio = store.create_portfolio("workspace", "CN", "Lifecycle")
    version = store.create_version(
        "workspace",
        portfolio["id"],
        {"strategies": [{"strategy_name": "momentum", "version": "v1", "weight": 1, "enabled": True}]},
    )
    store.add_member("workspace", portfolio["id"], "600519")
    base = date.today()
    rows = _bars(base - timedelta(days=29))
    storage = _Storage(rows)
    runtime = DecisionRuntime(store, storage)

    first = runtime.run("workspace", portfolio["id"], trigger="scheduled_prepare:morning", run_key="lifecycle-1")
    previous = first["decisions"][0]["action"]
    rows[0]["close"] = float("nan")

    pending = runtime.run("workspace", portfolio["id"], trigger="scheduled_prepare:morning", run_key="lifecycle-2")
    assert pending["decisions"][0]["action"] == previous
    assert pending["decisions"][0]["valid"] is False
    assert pending["decisions"][0]["stale"] is True

    next_trade = get_market_adapter("CN").next_trading_day(base)
    assert next_trade is not None
    rows[-1]["date"] = next_trade
    invalid = runtime.run("workspace", portfolio["id"], trigger="scheduled_prepare:morning", run_key="lifecycle-3")
    assert invalid["decisions"][0]["action"] == "decision_invalid"
    assert invalid["decisions"][0]["valid"] is False


def test_manual_and_preview_runs_never_contaminate_automatic_state(tmp_path: Path) -> None:
    store = DecisionStore(tmp_path / "decisions.db")
    portfolio = store.create_portfolio("workspace", "CN", "Manual isolation")
    store.create_version(
        "workspace",
        portfolio["id"],
        {"strategies": [{"strategy_name": "momentum", "version": "v1", "weight": 1, "enabled": True}]},
    )
    member = store.add_member("workspace", portfolio["id"], "600519")
    runtime = DecisionRuntime(store, _Storage(_bars(date.today() - timedelta(days=29))))

    manual = runtime.run("workspace", portfolio["id"], trigger="manual", run_key="manual-isolated")
    preview = runtime.run("workspace", portfolio["id"], trigger="preview", run_key="preview-isolated")

    assert manual["decisions"][0]["action"] != "decision_invalid"
    assert preview["decisions"][0]["previous_action"] is None
    assert store.get_member_state(member["id"]) is None

    automatic = runtime.run(
        "workspace",
        portfolio["id"],
        trigger="scheduled_prepare:morning",
        run_key="automatic-after-manual",
    )
    assert automatic["decisions"][0]["previous_action"] is None
    assert store.get_member_state(member["id"])["last_valid_action"] == automatic["decisions"][0]["action"]

    state_after_automatic = store.get_member_state(member["id"])
    runtime.run("workspace", portfolio["id"], trigger="manual", run_key="manual-after-automatic")
    assert store.get_member_state(member["id"]) == state_after_automatic


def test_replaying_a_worker_run_key_does_not_rebuild_or_change_the_frozen_input(tmp_path: Path, monkeypatch) -> None:
    store = DecisionStore(tmp_path / "decisions.db")
    portfolio = store.create_portfolio("workspace", "CN", "Restart idempotency")
    store.create_version(
        "workspace",
        portfolio["id"],
        {"strategies": [{"strategy_name": "momentum", "version": "v1", "weight": 1, "enabled": True}]},
    )
    store.add_member("workspace", portfolio["id"], "600519")
    runtime = DecisionRuntime(store, _Storage(_bars(date.today() - timedelta(days=29))))

    first = runtime.run(
        "workspace",
        portfolio["id"],
        trigger="scheduled_prepare:morning",
        run_key="command:restart-1",
    )
    monkeypatch.setattr(runtime, "build_snapshot", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("snapshot must not rebuild")))

    replay = runtime.run(
        "workspace",
        portfolio["id"],
        trigger="scheduled_prepare:morning",
        run_key="command:restart-1",
    )

    assert replay["run"]["id"] == first["run"]["id"]
    assert replay["snapshot"]["id"] == first["snapshot"]["id"]
    assert replay["report"]["report_hash"] == first["report"]["report_hash"]
    assert len(store.list_reports("workspace", portfolio["id"])) == 1
