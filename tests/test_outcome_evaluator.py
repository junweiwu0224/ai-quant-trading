import sqlite3
import pytest

from agentic.models import TradingSignal
from agentic.outcome_evaluator import DecisionSignalOutcomeEvaluator
from agentic.repository import AgenticRepository
from agentic.signal_ledger import SignalLedger


def _signal(direction="buy", **overrides):
    return TradingSignal(
        id="sig-outcome",
        agent_id="research",
        source="fixture",
        code="600000",
        direction=direction,
        confidence=0.8,
        time_horizon="3d",
        entry_reasons=["fixture"],
        risk_notes=["fixture risk"],
        suggested_position=0.1,
        stop_loss=overrides.get("stop_loss"),
        take_profit=overrides.get("take_profit"),
        status="new",
        created_at="2026-08-10T00:00:00Z",
        metadata=overrides.get("metadata", {}),
        target_price=overrides.get("target_price"),
        missing_fields=overrides.get("missing_fields", []),
        model_metadata=overrides.get("model_metadata", {}),
    )


def test_decision_signal_outcome_is_not_strategy_backtest_and_records_t_plus_n():
    ledger = SignalLedger(sqlite3.connect(":memory:"))
    evaluator = DecisionSignalOutcomeEvaluator(
        ledger,
        lambda code, start, end: [{"close": 100}, {"close": 102}, {"close": 101}, {"close": 105}],
    )

    result = evaluator.evaluate(_signal(), horizon_days=3, end="2026-08-13T00:00:00Z")

    assert result.status == "win"
    assert result.sample_sufficient is True
    assert result.realized_return == pytest.approx(0.05)
    assert ledger.latest_outcome("sig-outcome").metadata["kind"] == "decision_signal_t+n"


def test_outcome_evaluator_explicitly_reports_insufficient_sample():
    ledger = SignalLedger(sqlite3.connect(":memory:"))
    evaluator = DecisionSignalOutcomeEvaluator(ledger, lambda code, start, end: [{"close": 100}])

    result = evaluator.evaluate(_signal(), horizon_days=3, end="2026-08-13T00:00:00Z")

    assert result.status == "insufficient_sample"
    assert result.outcome is None


def test_outcome_evaluator_separates_direction_targets_and_executability():
    ledger = SignalLedger(sqlite3.connect(":memory:"))
    evaluator = DecisionSignalOutcomeEvaluator(
        ledger,
        lambda code, start, end: [
            {"close": 100, "high": 100, "low": 100},
            {"close": 104, "high": 106, "low": 99},
            {"close": 103, "high": 104, "low": 98},
        ],
    )

    result = evaluator.evaluate(
        _signal(
            take_profit=0.05,
            stop_loss=0.02,
            metadata={"profile": "trend", "market_phase": "recovery"},
            model_metadata={"execution_status": "ready"},
        ),
        horizon_days=2,
        end="2026-08-13T00:00:00Z",
    )

    assert result.direction_hit is True
    assert result.take_profit_hit is True
    assert result.stop_loss_hit is True
    assert result.executable is True
    assert result.profile == "trend"
    assert result.market_phase == "recovery"
    assert result.outcome.metadata["outcome_version"] == 2


def test_outcome_evaluator_sell_direction_and_explicit_not_executable():
    ledger = SignalLedger(sqlite3.connect(":memory:"))
    evaluator = DecisionSignalOutcomeEvaluator(
        ledger,
        lambda code, start, end: [{"close": 100}, {"close": 95}, {"close": 94}],
    )

    result = evaluator.evaluate(
        _signal(
            direction="sell",
            take_profit=0.04,
            metadata={"decision_signal": {"execution_status": "blocked"}},
        ),
        horizon_days=2,
        end="2026-08-13T00:00:00Z",
    )

    assert result.direction_hit is True
    assert result.take_profit_hit is True
    assert result.stop_loss_hit is None
    assert result.executable is False


def test_outcome_evaluator_sorts_dates_and_deduplicates_identical_price_rows():
    ledger = SignalLedger(sqlite3.connect(":memory:"))
    evaluator = DecisionSignalOutcomeEvaluator(
        ledger,
        lambda code, start, end: [
            {"date": "2026-08-13", "close": 105},
            {"date": "2026-08-11", "close": 100},
            {"date": "2026-08-12", "close": 102},
            {"date": "2026-08-12", "close": 102},
            {"date": "2026-08-14", "close": float("nan")},
            {"date": "2026-08-15", "close": float("inf")},
        ],
    )

    result = evaluator.evaluate(_signal(), horizon_days=2, end="2026-08-13T00:00:00Z")

    assert result.status == "win"
    assert result.observed_days == 3
    assert result.realized_return == pytest.approx(0.05)
    assert result.outcome.metadata["kind"] == "decision_signal_t+n"


def test_outcome_evaluator_rejects_nonfinite_close_values():
    ledger = SignalLedger(sqlite3.connect(":memory:"))
    evaluator = DecisionSignalOutcomeEvaluator(
        ledger,
        lambda code, start, end: [
            {"date": "2026-08-11", "close": 100},
            {"date": "2026-08-12", "close": float("nan")},
            {"date": "2026-08-13", "close": float("inf")},
        ],
    )

    result = evaluator.evaluate(_signal(), horizon_days=1, end="2026-08-13T00:00:00Z")

    assert result.status == "insufficient_sample"
    assert result.observed_days == 1
    assert result.outcome is None


def test_outcome_evaluator_rejects_conflicting_duplicate_price_rows():
    ledger = SignalLedger(sqlite3.connect(":memory:"))
    evaluator = DecisionSignalOutcomeEvaluator(
        ledger,
        lambda code, start, end: [
            {"date": "2026-08-11", "close": 100},
            {"date": "2026-08-12", "close": 102},
            {"date": "2026-08-12", "close": 103},
            {"date": "2026-08-13", "close": 105},
        ],
    )

    result = evaluator.evaluate(_signal(), horizon_days=2, end="2026-08-13T00:00:00Z")

    assert result.status == "invalid_sample"
    assert result.sample_sufficient is False
    assert result.outcome is None
    assert "重复时间点" in result.reason


def test_outcome_evaluator_calculates_sell_drawdown_on_short_equity_curve():
    ledger = SignalLedger(sqlite3.connect(":memory:"))
    evaluator = DecisionSignalOutcomeEvaluator(
        ledger,
        lambda code, start, end: [
            {"date": "2026-08-11", "close": 100},
            {"date": "2026-08-12", "close": 80},
            {"date": "2026-08-13", "close": 90},
        ],
    )

    result = evaluator.evaluate(
        _signal(direction="sell"), horizon_days=2, end="2026-08-13T00:00:00Z"
    )

    assert result.realized_return == pytest.approx(0.1)
    assert result.max_drawdown == pytest.approx(1 - (100 / 90) / (100 / 80))
    assert result.outcome.metadata["kind"] == "decision_signal_t+n"


def test_repository_aggregates_outcomes_by_source_profile_horizon_and_phase(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    signal = _signal(metadata={"profile": "trend", "market_phase": "recovery"})
    repo.save_signal(signal)
    ledger = SignalLedger(repo.db_path)
    for index, direction_hit in enumerate((True, False)):
        ledger.record_outcome(
            signal.id,
            status="win" if direction_hit else "loss",
            realized_return=0.05 if direction_hit else -0.02,
            metadata={
                "outcome_version": 2,
                "horizon_days": 3,
                "direction_hit": direction_hit,
                "take_profit_hit": direction_hit,
                "stop_loss_hit": not direction_hit,
                "executable": True,
                "profile": "trend",
                "market_phase": "recovery",
            },
            observed_at=f"2026-06-0{index + 2}T15:00:00+08:00",
        )

    groups = repo.list_outcome_aggregates(min_samples=2)

    assert len(groups) == 1
    assert groups[0]["source"] == "fixture"
    assert groups[0]["profile"] == "trend"
    assert groups[0]["horizon"] == 3
    assert groups[0]["market_phase"] == "recovery"
    assert groups[0]["direction"]["hit_rate"] == 0.5
    assert groups[0]["take_profit"]["hit_rate"] == 0.5
    assert groups[0]["executability"]["hit_rate"] == 1.0
    assert groups[0]["rank"] == 1


def test_repository_does_not_rank_insufficient_outcome_group(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    signal = _signal()
    repo.save_signal(signal)
    SignalLedger(repo.db_path).record_outcome(
        signal.id,
        status="win",
        realized_return=0.05,
        metadata={"horizon_days": 3, "direction_hit": True},
        observed_at="2026-06-02T15:00:00+08:00",
    )

    group = repo.list_outcome_aggregates(min_samples=2)[0]

    assert group["ranking_status"] == "insufficient_sample"
    assert group["rank"] is None
