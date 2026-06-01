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


def test_paper_strategy_candidate_service_confirms_candidate_without_ordering(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    service = PaperStrategyCandidateService(repo)
    record = service.enqueue(
        _promoted_result(),
        sample={"codes": ["000001"], "start_date": "2024-01-01", "end_date": "2024-03-31", "trading_days": 60},
    )

    confirmed = service.confirm(record.id)

    assert confirmed.id == record.id
    assert confirmed.status == "paper_active"
    assert confirmed.requires_confirmation is False
    assert repo.list_paper_strategy_candidates()[0].status == "paper_active"


def test_paper_strategy_candidate_service_rejects_missing_confirm(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    service = PaperStrategyCandidateService(repo)

    try:
        service.confirm("missing")
    except KeyError as exc:
        assert "paper strategy candidate not found" in str(exc)
    else:
        raise AssertionError("missing candidate should raise")


def test_paper_strategy_candidate_service_runs_active_candidate_as_pending_intent(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    service = PaperStrategyCandidateService(repo)
    record = service.enqueue(
        _promoted_result(),
        sample={"codes": ["000001", "600519"], "start_date": "2024-01-01", "end_date": "2024-03-31", "trading_days": 60},
    )
    service.confirm(record.id)

    execution = service.run_active(record.id)

    assert execution.candidate_record_id == record.id
    assert execution.status == "paper_intent_pending"
    assert execution.requires_confirmation is True
    assert execution.codes == ("000001", "600519")
    assert "manual trigger" in execution.reason
    assert repo.list_paper_strategy_executions()[0] == execution


def test_paper_strategy_candidate_service_refuses_to_run_unconfirmed_candidate(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    service = PaperStrategyCandidateService(repo)
    record = service.enqueue(_promoted_result(), sample={"codes": ["000001"]})

    try:
        service.run_active(record.id)
    except ValueError as exc:
        assert "only paper_active" in str(exc)
    else:
        raise AssertionError("unconfirmed candidate should not run")


def test_paper_strategy_execution_confirm_passes_risk_gate(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    service = PaperStrategyCandidateService(repo)
    record = service.enqueue(_promoted_result(), sample={"codes": ["000001"], "trading_days": 60})
    service.confirm(record.id)
    execution = service.run_active(record.id)

    confirmed = service.confirm_execution(
        execution.id,
        portfolio={"total_equity": 100000, "positions": {}},
        risk_context={"cash_pct": 0.05, "industry_map": {"000001": "bank"}},
    )

    assert confirmed.id == execution.id
    assert confirmed.status == "paper_intent_confirmed"
    assert confirmed.requires_confirmation is False
    assert "risk gate passed" in confirmed.reason


def test_paper_strategy_execution_confirm_rejects_risk_failure(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    service = PaperStrategyCandidateService(repo)
    record = service.enqueue(_promoted_result(), sample={"codes": ["600519"], "trading_days": 60})
    service.confirm(record.id)
    execution = service.run_active(record.id)

    rejected = service.confirm_execution(
        execution.id,
        portfolio={"total_equity": 100000, "positions": {}},
        risk_context={"cash_pct": 0.3, "blacklist": ["600519"]},
    )

    assert rejected.status == "rejected"
    assert rejected.requires_confirmation is False
    assert "blacklisted code: 600519" in rejected.reason
    assert "strategy cash pct" in rejected.reason
