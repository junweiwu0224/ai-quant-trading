from agentic.paper_strategy_candidates import PaperStrategyCandidateService
from agentic.repository import AgenticRepository
from agentic.strategy_candidates import StrategyCandidateGenerator


def _promoted_result():
    candidate = StrategyCandidateGenerator().generate(limit=1)[0].to_dict()
    return {
        "candidate": candidate,
        "metrics": {"trades": 18, "max_drawdown": 0.08, "sharpe": 1.1},
        "promotion": {"promoted": True, "reason": "passed promotion gate"},
    }


def test_paper_strategy_candidate_service_enqueues_promoted_candidate(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    service = PaperStrategyCandidateService(repo)

    record = service.enqueue(
        _promoted_result(),
        sample={"codes": ["000001"], "start_date": "2024-01-01", "end_date": "2024-03-31", "trading_days": 60},
    )

    assert record.status == "paper_candidate"
    assert record.requires_confirmation is True
    assert record.candidate_id == "qlib_ranked_core"
    assert repo.list_paper_strategy_candidates()[0] == record


def test_paper_strategy_candidate_service_rejects_unpromoted_candidate(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    service = PaperStrategyCandidateService(repo)
    result = _promoted_result()
    result["promotion"] = {"promoted": False, "reason": "insufficient trades"}

    try:
        service.enqueue(result, sample={"codes": ["000001"]})
    except ValueError as exc:
        assert "only promoted candidates" in str(exc)
    else:
        raise AssertionError("unpromoted candidate should be rejected")
