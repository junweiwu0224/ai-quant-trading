from agentic.repository import AgenticRepository
from agentic.signal_ledger import SignalLedger
from agentic.signals import SignalService


def test_agentic_outcome_aggregate_get_separates_metrics_and_hides_small_ranks(client, monkeypatch, tmp_path):
    from dashboard.routers import agentic as agentic_router

    repo = AgenticRepository(tmp_path / "agentic.db")
    service = SignalService(repo)
    signal = service.publish(
        agent_id="fixture",
        source="fixture-source",
        code="600000",
        direction="buy",
        confidence=0.8,
        time_horizon="3d",
        entry_reasons=["fixture"],
        risk_notes=["fixture"],
        suggested_position=0.1,
        take_profit=0.05,
        stop_loss=0.02,
        metadata={"profile": "trend", "market_phase": "recovery"},
    )
    SignalLedger(repo.db_path).record_outcome(
        signal.id,
        status="win",
        realized_return=0.04,
        max_drawdown=0.01,
        metadata={
            "outcome_version": 2,
            "horizon_days": 3,
            "direction_hit": True,
            "take_profit_hit": True,
            "stop_loss_hit": False,
            "executable": True,
            "profile": "trend",
            "market_phase": "recovery",
        },
        observed_at="2026-08-13T15:00:00Z",
    )
    monkeypatch.setattr(agentic_router, "agentic_repository", repo)

    response = client.get("/api/agentic/outcomes/aggregate?min_samples=2")

    assert response.status_code == 200
    body = response.json()
    assert body["metric_scope"] == "decision_signal_outcome"
    aggregate = body["aggregates"][0]
    assert aggregate["source"] == "fixture-source"
    assert aggregate["profile"] == "trend"
    assert aggregate["horizon"] == 3
    assert aggregate["market_phase"] == "recovery"
    assert aggregate["direction"]["hit_rate"] == 1.0
    assert aggregate["take_profit"]["hit_rate"] == 1.0
    assert aggregate["stop_loss"]["hit_rate"] == 0.0
    assert aggregate["executability"]["hit_rate"] == 1.0
    assert aggregate["rank"] is None
    assert aggregate["ranking_status"] == "insufficient_sample"


def test_agentic_outcome_aggregate_get_filters_dimensions(client, monkeypatch, tmp_path):
    from dashboard.routers import agentic as agentic_router

    repo = AgenticRepository(tmp_path / "agentic.db")
    service = SignalService(repo)
    signal = service.publish(
        agent_id="fixture",
        source="source-a",
        code="600001",
        direction="buy",
        confidence=0.8,
        time_horizon="3d",
        entry_reasons=["fixture"],
        risk_notes=["fixture"],
        suggested_position=0.1,
        metadata={"profile": "mean-reversion", "market_phase": "risk-off"},
    )
    SignalLedger(repo.db_path).record_outcome(
        signal.id,
        status="loss",
        realized_return=-0.02,
        metadata={
            "horizon_days": 3,
            "direction_hit": False,
            "profile": "mean-reversion",
            "market_phase": "risk-off",
        },
        observed_at="2026-08-13T15:00:00Z",
    )
    monkeypatch.setattr(agentic_router, "agentic_repository", repo)

    response = client.get(
        "/api/agentic/outcomes/aggregate?source=source-a&profile=mean-reversion&horizon_days=3&market_phase=risk-off"
    )

    assert response.status_code == 200
    assert len(response.json()["aggregates"]) == 1
