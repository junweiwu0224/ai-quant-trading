from agentic.models import PaperStrategyCandidate, PaperStrategyExecution
from agentic.paper_strategy_candidates import PaperStrategyCandidateService
from agentic.repository import AgenticRepository
from agentic.strategy_candidates import StrategyCandidateGenerator
from engine.order_manager import OrderManager


def _promoted_result():
    candidate = StrategyCandidateGenerator().generate(limit=1)[0].to_dict()
    return {
        "candidate": candidate,
        "metrics": {"trades": 18, "max_drawdown": 0.08, "sharpe": 1.1},
        "promotion": {"promoted": True, "reason": "passed promotion gate"},
        "gate_checks": [
            {"id": "data_quality", "passed": True},
            {"id": "backtest_quality", "passed": True},
            {"id": "risk_boundary", "passed": True},
            {"id": "signal_validation", "passed": True, "detail": "验证偏正 · 样本 42 天"},
        ],
    }


def _persisted_candidate(validation: dict | None, *, status: str = "paper_candidate") -> PaperStrategyCandidate:
    candidate = StrategyCandidateGenerator().generate(limit=1)[0].to_dict()
    metrics = {"trades": 18, "max_drawdown": 0.08, "sharpe": 1.1}
    if validation is not None:
        metrics["signal_validation"] = validation
    return PaperStrategyCandidate(
        id=f"persisted_{status}",
        candidate_id=str(candidate["id"]),
        name=str(candidate["name"]),
        dsl=dict(candidate["dsl"]),
        sample={"codes": ["000001"], "trading_days": 60},
        metrics=metrics,
        promotion={"promoted": True, "reason": "passed promotion gate"},
        status=status,
        requires_confirmation=status == "paper_candidate",
        created_at="2026-06-09T00:00:00+00:00",
    )


def _persisted_execution(candidate: PaperStrategyCandidate, *, status: str = "paper_intent_pending") -> PaperStrategyExecution:
    return PaperStrategyExecution(
        id=f"execution_{status}",
        candidate_record_id=candidate.id,
        candidate_id=candidate.candidate_id,
        name=candidate.name,
        dsl=candidate.dsl,
        codes=("000001",),
        status=status,
        reason="persisted test execution",
        requires_confirmation=status == "paper_intent_pending",
        created_at="2026-06-09T00:00:00+00:00",
    )


def test_paper_strategy_candidate_service_enqueues_promoted_candidate(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    service = PaperStrategyCandidateService(repo)

    record = service.enqueue(
        _promoted_result(),
        sample={"codes": ["000001"], "start_date": "2024-01-01", "end_date": "2024-03-31", "trading_days": 60},
    )

    assert record.status == "paper_candidate"
    assert record.requires_confirmation is True
    assert record.candidate_id == "signal_ranked_core"
    assert record.metrics["signal_validation"]["passed"] is True
    assert record.metrics["signal_validation"]["detail"] == "验证偏正 · 样本 42 天"
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


def test_paper_strategy_candidate_service_rejects_failed_signal_validation_gate(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    service = PaperStrategyCandidateService(repo)
    result = _promoted_result()
    result["gate_checks"] = [
        {"id": "data_quality", "passed": True},
        {"id": "backtest_quality", "passed": True},
        {"id": "risk_boundary", "passed": True},
        {"id": "signal_validation", "passed": False, "detail": "AI未验证 · 样本 0 天"},
    ]

    try:
        service.enqueue(result, sample={"codes": ["000001"]})
    except ValueError as exc:
        assert "signal validation gate failed" in str(exc)
    else:
        raise AssertionError("candidate with failed signal validation gate should be rejected")


def test_paper_strategy_candidate_service_rejects_missing_signal_validation_gate(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    service = PaperStrategyCandidateService(repo)
    result = _promoted_result()
    result["gate_checks"] = [
        {"id": "data_quality", "passed": True},
        {"id": "backtest_quality", "passed": True},
        {"id": "risk_boundary", "passed": True},
    ]

    try:
        service.enqueue(result, sample={"codes": ["000001"]})
    except ValueError as exc:
        assert "missing signal validation" in str(exc)
    else:
        raise AssertionError("candidate missing signal validation gate should be rejected")


def test_paper_strategy_candidate_service_rejects_failed_gate_after_signal_validation(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    service = PaperStrategyCandidateService(repo)
    result = _promoted_result()
    result["gate_checks"] = [
        {"id": "signal_validation", "passed": True, "detail": "验证偏正 · 样本 42 天"},
        {"id": "risk_boundary", "passed": False, "detail": "最大回撤超限"},
    ]

    try:
        service.enqueue(result, sample={"codes": ["000001"]})
    except ValueError as exc:
        assert "risk_boundary" in str(exc) or "gate failed" in str(exc)
    else:
        raise AssertionError("candidate with any failed gate should be rejected")


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


def test_paper_strategy_candidate_service_rejects_persisted_candidate_without_signal_validation_on_confirm(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    service = PaperStrategyCandidateService(repo)
    record = _persisted_candidate(None)
    repo.save_paper_strategy_candidate(record)

    try:
        service.confirm(record.id)
    except ValueError as exc:
        assert "signal validation" in str(exc)
    else:
        raise AssertionError("persisted candidate without signal validation should not be confirmed")


def test_paper_strategy_candidate_service_rejects_persisted_candidate_with_failed_signal_validation_on_confirm(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    service = PaperStrategyCandidateService(repo)
    record = _persisted_candidate({"passed": False, "confidence": "unverified", "sample_days": 0})
    repo.save_paper_strategy_candidate(record)

    try:
        service.confirm(record.id)
    except ValueError as exc:
        assert "signal validation" in str(exc)
    else:
        raise AssertionError("persisted candidate with failed signal validation should not be confirmed")


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


def test_paper_strategy_candidate_service_rejects_active_candidate_without_signal_validation_on_run(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    service = PaperStrategyCandidateService(repo)
    record = _persisted_candidate(None, status="paper_active")
    repo.save_paper_strategy_candidate(record)

    try:
        service.run_active(record.id)
    except ValueError as exc:
        assert "signal validation" in str(exc)
    else:
        raise AssertionError("active candidate without signal validation should not run")


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


def test_paper_strategy_execution_confirm_rejects_linked_candidate_without_signal_validation(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    service = PaperStrategyCandidateService(repo)
    record = _persisted_candidate(None, status="paper_active")
    repo.save_paper_strategy_candidate(record)
    execution = _persisted_execution(record)
    repo.save_paper_strategy_execution(execution)

    try:
        service.confirm_execution(execution.id, portfolio={"total_equity": 100000, "positions": {}})
    except ValueError as exc:
        assert "signal validation" in str(exc)
    else:
        raise AssertionError("execution linked to unvalidated candidate should not be confirmed")


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


def test_confirmed_execution_can_create_paper_order_drafts(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    service = PaperStrategyCandidateService(repo)
    record = service.enqueue(_promoted_result(), sample={"codes": ["000001", "600519"], "trading_days": 60})
    service.confirm(record.id)
    execution = service.run_active(record.id)
    confirmed = service.confirm_execution(execution.id, portfolio={"total_equity": 100000, "positions": {}}, risk_context={"cash_pct": 0.05})

    drafts = service.create_order_drafts(confirmed.id, volume_per_code=100)

    assert [draft.code for draft in drafts] == ["000001", "600519"]
    assert all(draft.status == "draft_pending" for draft in drafts)
    assert all(draft.direction == "buy" and draft.order_type == "market" for draft in drafts)
    assert all(draft.volume == 100 for draft in drafts)
    assert repo.list_agentic_order_drafts()[0].execution_id == confirmed.id


def test_confirmed_execution_rejects_order_drafts_when_linked_candidate_lacks_signal_validation(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    service = PaperStrategyCandidateService(repo)
    record = _persisted_candidate(None, status="paper_active")
    repo.save_paper_strategy_candidate(record)
    execution = _persisted_execution(record, status="paper_intent_confirmed")
    repo.save_paper_strategy_execution(execution)

    try:
        service.create_order_drafts(execution.id)
    except ValueError as exc:
        assert "signal validation" in str(exc)
    else:
        raise AssertionError("unvalidated candidate should not create order drafts")


def test_order_drafts_require_confirmed_execution(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    service = PaperStrategyCandidateService(repo)
    record = service.enqueue(_promoted_result(), sample={"codes": ["000001"]})
    service.confirm(record.id)
    execution = service.run_active(record.id)

    try:
        service.create_order_drafts(execution.id)
    except ValueError as exc:
        assert "paper_intent_confirmed" in str(exc)
    else:
        raise AssertionError("unconfirmed execution should not create drafts")


def test_confirmed_execution_can_submit_real_paper_orders(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    order_manager = OrderManager(str(tmp_path / "paper_trading.db"))
    service = PaperStrategyCandidateService(repo, order_manager=order_manager)
    record = service.enqueue(_promoted_result(), sample={"codes": ["000001", "600519"], "trading_days": 60})
    service.confirm(record.id)
    execution = service.run_active(record.id)
    confirmed = service.confirm_execution(
        execution.id,
        portfolio={"total_equity": 100000, "positions": {}},
        risk_context={"cash_pct": 0.05},
    )

    orders = service.submit_confirmed_execution_orders(confirmed.id, volume_per_code=100)

    assert [order.code for order in orders] == ["000001", "600519"]
    assert all(order.status.value == "pending" for order in orders)
    assert all(order.strategy_name == "agentic:signal_ranked_core" for order in orders)
    persisted = order_manager.get_orders(page_size=10)["items"]
    assert [order["code"] for order in persisted] == ["600519", "000001"]
    assert repo.get_paper_strategy_execution(confirmed.id).status == "paper_orders_submitted"


def test_confirmed_execution_rejects_real_paper_orders_when_linked_candidate_lacks_signal_validation(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    service = PaperStrategyCandidateService(repo, order_manager=OrderManager(str(tmp_path / "paper_trading.db")))
    record = _persisted_candidate(None, status="paper_active")
    repo.save_paper_strategy_candidate(record)
    execution = _persisted_execution(record, status="paper_intent_confirmed")
    repo.save_paper_strategy_execution(execution)

    try:
        service.submit_confirmed_execution_orders(execution.id)
    except ValueError as exc:
        assert "signal validation" in str(exc)
    else:
        raise AssertionError("unvalidated candidate should not submit real paper orders")


def test_real_paper_order_submission_is_idempotency_guarded(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    order_manager = OrderManager(str(tmp_path / "paper_trading.db"))
    service = PaperStrategyCandidateService(repo, order_manager=order_manager)
    record = service.enqueue(_promoted_result(), sample={"codes": ["000001"], "trading_days": 60})
    service.confirm(record.id)
    execution = service.run_active(record.id)
    confirmed = service.confirm_execution(execution.id, portfolio={"total_equity": 100000, "positions": {}}, risk_context={"cash_pct": 0.05})

    service.submit_confirmed_execution_orders(confirmed.id)

    try:
        service.submit_confirmed_execution_orders(confirmed.id)
    except ValueError as exc:
        assert "paper_intent_confirmed" in str(exc)
    else:
        raise AssertionError("submitted execution should not submit duplicate orders")
    assert order_manager.get_orders(page_size=10)["total"] == 1


def test_real_paper_orders_require_confirmed_execution(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    service = PaperStrategyCandidateService(repo, order_manager=OrderManager(str(tmp_path / "paper_trading.db")))
    record = service.enqueue(_promoted_result(), sample={"codes": ["000001"]})
    service.confirm(record.id)
    execution = service.run_active(record.id)

    try:
        service.submit_confirmed_execution_orders(execution.id)
    except ValueError as exc:
        assert "paper_intent_confirmed" in str(exc)
    else:
        raise AssertionError("unconfirmed execution should not submit real orders")
