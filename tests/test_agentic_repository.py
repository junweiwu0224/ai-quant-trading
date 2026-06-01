from dataclasses import dataclass, field

from agentic.models import ResearchJob
from agentic.repository import AgenticRepository


@dataclass(frozen=True)
class SignalLike:
    id: str
    agent_id: str
    source: str
    code: str
    direction: str
    confidence: float
    time_horizon: str
    entry_reasons: list[str]
    risk_notes: list[str]
    suggested_position: float
    stop_loss: float | None
    take_profit: float | None
    status: str
    created_at: str
    expires_at: str | None = None
    metadata: dict = field(default_factory=dict)


def test_repository_saves_and_lists_signals(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    signal = SignalLike(
        "sig_1",
        "qlib_agent",
        "qlib",
        "605066.SH",
        "buy",
        0.72,
        "3-10d",
        ["Qlib score top 5"],
        ["break MA20 invalidates"],
        0.1,
        0.05,
        0.12,
        "new",
        "2026-06-01T15:00:00+08:00",
    )

    repo.save_signal(signal)
    rows = repo.list_signals()

    assert len(rows) == 1
    assert rows[0].id == "sig_1"
    assert rows[0].code == "605066"
    assert rows[0].entry_reasons == ("Qlib score top 5",)


def test_repository_get_signal_raises_for_missing_id(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")

    try:
        repo.get_signal("missing")
    except KeyError as exc:
        assert "signal not found" in str(exc)
    else:
        raise AssertionError("missing signal should raise")


def test_repository_saves_and_gets_research_jobs(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    job = ResearchJob(
        id="research_1",
        code="605066.SH",
        status="completed",
        roles=["qlib", "market", "theme", "bear", "decision"],
        final_report={"decision": "paper_candidate", "qlib_score": 0.72},
        created_at="2026-06-01T20:30:00+08:00",
        updated_at="2026-06-01T20:31:00+08:00",
    )

    repo.save_research_job(job)
    restored = repo.get_research_job("research_1")

    assert restored == job
    assert restored.code == "605066"


def test_repository_saves_and_lists_paper_strategy_candidates(tmp_path):
    from agentic.models import PaperStrategyCandidate

    repo = AgenticRepository(tmp_path / "agentic.db")
    candidate = PaperStrategyCandidate(
        id="paper_strategy_1",
        candidate_id="qlib_ranked_core",
        name="Qlib 核心轮动",
        dsl={"strategy_type": "ranked_rotation", "universe": "qlib_top"},
        sample={"codes": ["000001"], "start_date": "2024-01-01", "end_date": "2024-03-31", "trading_days": 60},
        metrics={"trades": 18, "max_drawdown": 0.08, "sharpe": 1.1},
        promotion={"promoted": True, "reason": "passed promotion gate"},
        status="paper_candidate",
        requires_confirmation=True,
        created_at="2026-06-01T21:30:00+08:00",
    )

    repo.save_paper_strategy_candidate(candidate)
    rows = repo.list_paper_strategy_candidates()

    assert rows == [candidate]
    assert rows[0].requires_confirmation is True
