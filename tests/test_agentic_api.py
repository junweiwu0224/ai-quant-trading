def test_agentic_agents_endpoint_lists_builtin_agents(client):
    resp = client.get("/api/agentic/agents")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    agents = {item["id"]: item for item in body["agents"]}
    assert "signal_agent" in agents
    assert agents["qlib_agent"]["legacy_alias_for"] == "signal_agent"


def test_agentic_signals_endpoint_returns_list(client, monkeypatch, tmp_path):
    from dashboard.routers import agentic as agentic_router
    from agentic.repository import AgenticRepository
    from agentic.signals import SignalService
    from agentic.promotion import PromotionContext

    monkeypatch.setattr(agentic_router, "signal_service", SignalService(AgenticRepository(tmp_path / "agentic.db")))

    resp = client.get("/api/agentic/signals")

    assert resp.status_code == 200
    assert resp.json() == {"success": True, "signals": []}


def test_agentic_research_run_is_idempotent_and_exposes_structured_report(client, monkeypatch, tmp_path):
    from dashboard.routers import agentic as agentic_router
    from agentic.repository import AgenticRepository
    from agentic.research_pipeline import ResearchPipeline
    from agentic.signals import SignalService

    repo = AgenticRepository(tmp_path / "agentic.db")
    service = SignalService(repo)
    monkeypatch.setattr(agentic_router, "agentic_repository", repo)
    monkeypatch.setattr(agentic_router, "signal_service", service)
    monkeypatch.setattr(agentic_router, "research_pipeline", ResearchPipeline(repo, signal_service=service))

    payload = {
        "code": "600000.SH",
        "run_key": "api-research-1",
        "context": {
            "as_of": "2026-08-13T08:00:00Z",
            "evidence_snapshot_id": "snapshot_fixture",
            "evidence_status": "citable",
            "technicals": {"trend": "up"},
            "signal_score": 0.72,
            "signal_validation": {"confidence": "validated_positive", "sample_days": 42},
        },
    }
    first = client.post("/api/agentic/research/run", json=payload)
    assert first.status_code == 200
    body = first.json()["research"]
    assert body["report"]["decision_signal"]["action"] == "buy"
    assert body["context"]["evidence_snapshot_id"] == "snapshot_fixture"
    assert body["decision_signal_id"]

    replay = client.post("/api/agentic/research/run", json=payload)
    assert replay.status_code == 200
    assert replay.json()["research"]["id"] == body["id"]
    assert len(repo.list_signals()) == 1

    detail = client.get(f"/api/agentic/research/{body['id']}")
    assert detail.status_code == 200
    assert detail.json()["research"]["report_id"] == body["report_id"]


def test_agentic_signal_outcome_api_reports_insufficient_local_sample(client, monkeypatch, tmp_path):
    from dashboard.routers import agentic as agentic_router
    from agentic.repository import AgenticRepository
    from agentic.signals import SignalService

    repo = AgenticRepository(tmp_path / "agentic.db")
    service = SignalService(repo)
    signal = service.publish(
        agent_id="fixture",
        source="fixture",
        code="600000",
        direction="buy",
        confidence=0.7,
        time_horizon="3d",
        entry_reasons=["fixture"],
        risk_notes=["fixture"],
        suggested_position=0.1,
    )
    monkeypatch.setattr(agentic_router, "agentic_repository", repo)
    monkeypatch.setattr(agentic_router, "signal_service", service)
    response = client.post(f"/api/agentic/signals/{signal.id}/outcome?horizon_days=5")
    assert response.status_code == 200
    assert response.json()["evaluation"]["status"] == "insufficient_sample"


def test_daily_brief_read_api_returns_persisted_brief(client, monkeypatch, tmp_path):
    from dashboard.routers import agentic as agentic_router
    from agentic.repository import AgenticRepository
    from agentic.daily_workflow import DailyBrief

    repo = AgenticRepository(tmp_path / "agentic.db")
    repo.save_daily_brief(DailyBrief(
        snapshot_id="snapshot-1", captured_at="2026-08-13T08:00:00Z", watchlist=("600000",),
        evidence_count=1, promotions=(), event_id="event-1", research_jobs=(), report_count=0,
        markdown="# brief", run_key="daily:2026-08-13:600000",
    ))
    monkeypatch.setattr(agentic_router, "agentic_repository", repo)

    response = client.get("/api/agentic/briefs/daily/2026-08-13")
    assert response.status_code == 200
    assert response.json()["brief"]["markdown"] == "# brief"


def test_agentic_screening_api_persists_source_health(client, monkeypatch, tmp_path):
    from dashboard.routers import agentic as agentic_router
    from agentic.repository import AgenticRepository
    from alpha.screening_runtime import ScreeningRuntime

    class FakeScreener:
        def screen(self, **kwargs):
            return {"total": 1, "stocks": [{"code": "600000", "change_pct": 2.0}]}

    repo = AgenticRepository(tmp_path / "agentic.db")
    monkeypatch.setattr(agentic_router, "agentic_repository", repo)
    monkeypatch.setattr(agentic_router, "screening_runtime", ScreeningRuntime(FakeScreener()))
    response = client.post("/api/agentic/screening/run", json={"strategy_name": "fixture"})
    assert response.status_code == 200
    assert response.json()["run"]["source_health"]["status"] == "ok"
    assert repo.list_screening_runs(limit=1)[0]["strategy_name"] == "fixture"


def test_agentic_daily_brief_run_api_collects_and_replays(client, monkeypatch, tmp_path):
    from dashboard.routers import agentic as agentic_router
    from agentic.daily_run import DailyResearchRunService
    from agentic.repository import AgenticRepository
    from agentic.signals import SignalService
    from data.evidence.store import InMemoryEvidenceStore
    from engine.events.outbox import InMemoryOutboxStore

    repo = AgenticRepository(tmp_path / "agentic.db")
    service = SignalService(repo)
    evidence = InMemoryEvidenceStore()
    outbox = InMemoryOutboxStore()

    async def market(store, max_items, source, **kwargs):
        from data.evidence.collector import ingest_records
        result = ingest_records(store, source=source, records=[{
            "title": "market fixture", "content": "fixture", "observed_at": "2026-08-13T08:00:00Z", "symbol": "600000"
        }], query="fixture", snapshot_metadata={"collection_status": "ok"})
        return {"collection_status": "ok", "evidence_snapshot_id": result.snapshot.id, "evidence_count": 1, "news": [{"title": "market fixture"}], "overall_sentiment": 0.1}

    async def stock(code, store, max_items, **kwargs):
        return {"code": code, "collection_status": "empty", "evidence_count": 0, "news": []}

    daily = DailyResearchRunService(
        evidence, repo, outbox, signal_service=service,
        market_collector=market, stock_collector=stock,
    )
    monkeypatch.setattr(agentic_router, "_daily_run_service", lambda: daily)
    first = client.post("/api/agentic/briefs/daily/run", json={
        "watchlist": ["600000"], "run_key": "daily:fixture:600000", "operation_id": "daily-op-1",
        "captured_at": "2026-08-13T08:00:00Z",
    })
    assert first.status_code == 200, first.text
    assert first.json()["brief"]["report_count"] == 1
    replay = client.post("/api/agentic/briefs/daily/run", json={
        "watchlist": ["600000"], "run_key": "daily:fixture:600000", "operation_id": "daily-op-1",
    })
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert len(repo.list_research_jobs(limit=10)) == 1


def test_agentic_signal_paper_gate_and_manual_confirmation_api(client, monkeypatch, tmp_path):
    from dashboard.routers import agentic as agentic_router
    from agentic.repository import AgenticRepository
    from agentic.signals import SignalService

    service = SignalService(AgenticRepository(tmp_path / "agentic.db"))
    monkeypatch.setattr(agentic_router, "signal_service", service)
    signal = service.publish(
        agent_id="signal_agent",
        source="fixture",
        code="600000",
        direction="buy",
        confidence=0.8,
        time_horizon="swing",
        entry_reasons=["fixture evidence"],
        risk_notes=["fixture risk"],
        suggested_position=0.1,
    )

    gate = client.post(
        f"/api/agentic/signals/{signal.id}/paper-gate",
        json={
            "operation_id": "api-gate-1",
            "context": {
                "evidence_count": 1,
                "provenance_complete": True,
                "backtest_passed": True,
                "risk_approved": True,
                "signal_validation_passed": True,
            },
        },
    )
    assert gate.status_code == 200
    assert gate.json()["decision"]["approved"] is True
    assert gate.json()["operation"]["operation_id"] == "api-gate-1"

    confirmation = client.post(
        f"/api/agentic/signals/{signal.id}/paper-pending",
        json={
            "operation_id": "api-confirm-1",
            "approval_operation_id": "api-gate-1",
            "confirmed_by": "user-1",
        },
    )
    assert confirmation.status_code == 200
    assert confirmation.json()["signal"]["status"] == "paper_pending"
    assert confirmation.json()["operation"]["operation_id"] == "api-confirm-1"

    replay = client.post(
        f"/api/agentic/signals/{signal.id}/paper-pending",
        json={
            "operation_id": "api-confirm-1",
            "approval_operation_id": "api-gate-1",
            "confirmed_by": "user-1",
        },
    )
    assert replay.status_code == 200
    assert replay.json()["signal"]["status"] == "paper_pending"


def test_agentic_operation_audit_endpoint_lists_and_reads_operations(client, monkeypatch, tmp_path):
    from dashboard.routers import agentic as agentic_router
    from agentic.repository import AgenticRepository
    from agentic.signals import SignalService
    from agentic.promotion import PromotionContext

    repo = AgenticRepository(tmp_path / "agentic.db")
    service = SignalService(repo)
    monkeypatch.setattr(agentic_router, "signal_service", service)
    signal = service.publish(
        agent_id="audit-agent",
        source="fixture",
        code="000001",
        direction="buy",
        confidence=0.7,
        time_horizon="swing",
        entry_reasons=["fixture"],
        risk_notes=["fixture"],
        suggested_position=0.1,
    )
    service.approve_paper_pending(
        signal.id,
        PromotionContext(
            evidence_count=1,
            provenance_complete=True,
            backtest_passed=True,
            risk_approved=True,
            signal_validation_passed=True,
        ),
        operation_id="audit-gate-1",
    )

    listing = client.get("/api/agentic/operations?limit=10&aggregate_type=signal")
    assert listing.status_code == 200
    assert listing.json()["operations"][0]["operation_id"] == "audit-gate-1"

    detail = client.get("/api/agentic/operations/audit-gate-1")
    assert detail.status_code == 200
    assert detail.json()["operation"]["command"] == "signal.paper_gate"


def test_agentic_health_reports_core_components(client):
    resp = client.get("/api/agentic/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["components"]["registry"] == "online"
    assert body["components"]["signals"] == "online"


def test_agentic_compile_backtest_endpoint_returns_backtest_request(client):
    resp = client.post(
        "/api/agentic/strategy/compile-backtest",
        json={
            "dsl": {
                "strategy_type": "ranked_rotation",
                "universe": "signal_top",
                "rank_by": "signal_score",
                "filters": [{"close_above_ma": 20}],
                "rebalance": "daily",
                "max_holdings": 5,
                "stop_loss": 0.05,
                "take_profit": 0.12,
                "max_holding_days": 10,
            },
            "codes": ["605066.SH", "000001"],
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "initial_cash": 50000,
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    req = body["backtest_request"]
    assert req["strategy"] == "signal_strategy"
    assert req["legacy_strategy"] == "qlib_signal"
    assert req["strategy_display_name"] == "AI信号策略"
    assert req["agentic"]["signal_strategy"] == "signal_score_strategy"
    assert req["agentic"]["strategy_adapter"] == "qlib_signal"
    assert req["codes"] == ["605066", "000001"]
    assert req["params"]["mode"] == "ranking"
    assert req["risk_config"]["stop_loss_pct"] == 0.05


def test_agentic_run_backtest_endpoint_compiles_runs_and_evaluates(client, monkeypatch):
    from dashboard.routers import agentic as agentic_router

    class FakeResult:
        compiled_request = {"strategy": "qlib_signal", "params": {"mode": "ranking"}}
        backtest_response = {"total_trades": 18, "max_drawdown": 0.08, "sharpe_ratio": 1.1}
        metrics = {"trades": 18, "max_drawdown": 0.08, "sharpe": 1.1}

        class promotion:
            promoted = True
            reason = "passed promotion gate"
            metrics = {"trades": 18, "max_drawdown": 0.08, "sharpe": 1.1}

    class FakeRunner:
        async def run_and_evaluate(self, request):
            assert request.codes == ["605066.SH", "000001"]
            return FakeResult()

    monkeypatch.setattr(agentic_router, "backtest_runner", FakeRunner())

    resp = client.post(
        "/api/agentic/strategy/run-backtest",
        json={
            "dsl": {
                "strategy_type": "ranked_rotation",
                "universe": "signal_top",
                "rank_by": "signal_score",
                "filters": [{"close_above_ma": 20}],
                "rebalance": "daily",
                "max_holdings": 5,
                "stop_loss": 0.05,
                "take_profit": 0.12,
                "max_holding_days": 10,
            },
            "codes": ["605066.SH", "000001"],
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "initial_cash": 50000,
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["promotion"]["promoted"] is True
    assert body["promotion"]["reason"] == "passed promotion gate"
    assert body["metrics"]["trades"] == 18


def test_agentic_backtest_sample_endpoint_returns_local_coverage(client, monkeypatch):
    from dashboard.routers import agentic as agentic_router
    from agentic.sample_selector import BacktestSample

    class FakeSelector:
        def select(self, min_days=60, max_codes=5):
            assert min_days == 30
            assert max_codes == 2
            return BacktestSample(codes=["000001", "600519"], start_date="2024-01-01", end_date="2024-03-31", trading_days=60)

    monkeypatch.setattr(agentic_router, "sample_selector", FakeSelector())

    resp = client.get("/api/agentic/backtest-sample?min_days=30&max_codes=2")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["sample"]["codes"] == ["000001", "600519"]
    assert body["sample"]["source"] == "local_stock_daily"


def test_agentic_backtest_sample_endpoint_reports_missing_coverage(client, monkeypatch):
    from dashboard.routers import agentic as agentic_router

    class EmptySelector:
        def select(self, min_days=60, max_codes=5):
            raise ValueError("no local stock_daily coverage with enough history for agentic backtest")

    monkeypatch.setattr(agentic_router, "sample_selector", EmptySelector())

    resp = client.get("/api/agentic/backtest-sample")

    assert resp.status_code == 404
    assert "no local stock_daily coverage" in resp.json()["detail"]


def test_agentic_strategy_candidates_endpoint_returns_valid_dsl_candidates(client):
    resp = client.get("/api/agentic/strategy/candidates?limit=2&universe=iwencai_pool&risk_mode=conservative&max_holdings=3")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert len(body["candidates"]) == 2
    assert body["candidates"][0]["id"] == "signal_ranked_core"
    assert body["candidates"][0]["dsl"]["universe"] == "iwencai_pool"
    assert body["candidates"][0]["dsl"]["max_holdings"] == 3
    assert body["candidates"][0]["dsl"]["stop_loss"] <= 0.04


def test_agentic_run_strategy_candidates_endpoint_returns_ranked_results(client, monkeypatch):
    from dashboard.routers import agentic as agentic_router
    from agentic.sample_selector import BacktestSample
    from agentic.strategy_candidates import StrategyCandidateGenerator
    from agentic.strategy_lab import StrategyIterationResult

    class FakeBacktester:
        async def run(self, context=None, limit=4, min_days=60, max_codes=5, initial_cash=1_000_000):
            assert context == {
                "universe": "signal_top",
                "risk_mode": "balanced",
                "max_holdings": 5,
                "signal_validation": {
                    "confidence": "validated_positive",
                    "sample_days": 42,
                    "provider": "local_momentum",
                },
            }
            assert limit == 2
            assert min_days == 60
            assert max_codes == 3
            assert initial_cash == 50000
            candidates = StrategyCandidateGenerator().generate(limit=2)
            metrics = {"trades": 18, "max_drawdown": 0.08, "sharpe": 1.1}
            result = type("Result", (), {})()
            result.sample = BacktestSample(["000001"], "2024-01-01", "2024-03-31", 60)
            result.results = []
            result.to_dict = lambda: {
                "sample": result.sample.to_dict(),
                "results": [
                    {
                        "candidate": candidates[0].to_dict(),
                        "backtest_request": {"strategy": "qlib_signal"},
                        "backtest": {"total_trades": 18},
                        "metrics": metrics,
                        "promotion": {
                            "promoted": True,
                            "reason": "passed promotion gate",
                            "metrics": StrategyIterationResult(candidates[0].dsl, metrics, True, "passed promotion gate").metrics,
                        },
                    }
                ],
            }
            return result

    monkeypatch.setattr(agentic_router, "candidate_backtester", FakeBacktester())
    monkeypatch.setattr(
        agentic_router,
        "validate_signal_provider",
        lambda **kwargs: type(
            "Validation",
            (),
            {
                "to_dict": lambda self: {
                    "confidence": "validated_positive",
                    "sample_days": 42,
                    "provider": "local_momentum",
                }
            },
        )(),
    )

    resp = client.post(
        "/api/agentic/strategy/run-candidates",
        json={
            "context": {"universe": "signal_top", "risk_mode": "balanced", "max_holdings": 5},
            "limit": 2,
            "min_days": 60,
            "max_codes": 3,
            "initial_cash": 50000,
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["sample"]["codes"] == ["000001"]
    assert body["results"][0]["result_id"].startswith("candidate_result_")
    assert body["results"][0]["promotion"]["promoted"] is True


def test_agentic_promoted_strategy_candidate_can_be_queued_by_server_result_id(client, monkeypatch):
    from dashboard.routers import agentic as agentic_router
    from agentic.models import PaperStrategyCandidate

    def load_result(result_id):
        assert result_id == "candidate_result_server_1"
        return (
            {
                "candidate": {"id": "qlib_ranked_core", "name": "Qlib 核心轮动", "dsl": {"strategy_type": "ranked_rotation"}},
                "metrics": {"trades": 18, "max_drawdown": 0.08, "sharpe": 1.1},
                "promotion": {"promoted": True, "reason": "passed promotion gate"},
                "gate_checks": [
                    {"id": "data_quality", "passed": True},
                    {"id": "backtest_quality", "passed": True},
                    {"id": "risk_boundary", "passed": True},
                    {"id": "signal_validation", "passed": True},
                ],
            },
            {"codes": ["000001"]},
        )

    class FakeService:
        def enqueue(self, result, sample):
            assert result["promotion"]["promoted"] is True
            assert sample["codes"] == ["000001"]
            return PaperStrategyCandidate(
                id="paper_strategy_1",
                candidate_id=result["candidate"]["id"],
                name=result["candidate"]["name"],
                dsl=result["candidate"]["dsl"],
                sample=sample,
                metrics=result["metrics"],
                promotion=result["promotion"],
                status="paper_candidate",
                requires_confirmation=True,
                created_at="2026-06-01T21:35:00+00:00",
            )

    monkeypatch.setattr(agentic_router.agentic_repository, "get_candidate_backtest_result", load_result)
    monkeypatch.setattr(agentic_router, "paper_strategy_candidate_service", FakeService())
    monkeypatch.setattr(
        agentic_router,
        "validate_signal_provider",
        lambda **kwargs: type(
            "Validation",
            (),
            {
                "to_dict": lambda self: {
                    "confidence": "validated_positive",
                    "sample_days": 42,
                    "provider": "local_momentum",
                }
            },
        )(),
    )

    resp = client.post(
        "/api/agentic/strategy/paper-candidates",
        json={"result_id": "candidate_result_server_1"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["candidate"]["candidate_id"] == "qlib_ranked_core"
    assert body["candidate"]["canonical_candidate_id"] == "signal_ranked_core"
    assert body["candidate"]["legacy_candidate_id"] == "qlib_ranked_core"
    assert body["candidate"]["name"] == "AI信号基线轮动"
    assert body["candidate"]["status"] == "paper_candidate"
    assert body["candidate"]["requires_confirmation"] is True


def test_agentic_paper_candidate_enqueue_requires_server_result_id(client, monkeypatch):
    from dashboard.routers import agentic as agentic_router

    class FakeService:
        def enqueue(self, result, sample):
            raise AssertionError("enqueue must not accept browser-supplied candidate result payloads")

    monkeypatch.setattr(agentic_router, "paper_strategy_candidate_service", FakeService())

    resp = client.post(
        "/api/agentic/strategy/paper-candidates",
        json={},
    )

    assert resp.status_code == 400
    assert "server result_id is required" in resp.json()["detail"]


def test_agentic_paper_candidate_enqueue_rejects_extra_browser_payload(client, monkeypatch):
    from dashboard.routers import agentic as agentic_router
    from agentic.models import PaperStrategyCandidate

    monkeypatch.setattr(
        agentic_router.agentic_repository,
        "get_candidate_backtest_result",
        lambda result_id: (
            {
                "candidate": {"id": "signal_ranked_core", "name": "AI信号基线轮动", "dsl": {"strategy_type": "ranked_rotation"}},
                "metrics": {"trades": 18, "max_drawdown": 0.08, "sharpe": 1.1},
                "promotion": {"promoted": True, "reason": "passed promotion gate"},
                "gate_checks": [
                    {"id": "data_quality", "passed": True},
                    {"id": "backtest_quality", "passed": True},
                    {"id": "risk_boundary", "passed": True},
                    {"id": "signal_validation", "passed": True, "detail": "服务端通过 · 样本 42 天"},
                ],
            },
            {"codes": ["000001"]},
        ),
    )

    class FakeService:
        def enqueue(self, result, sample):
            return PaperStrategyCandidate(
                id="paper_strategy_1",
                candidate_id=result["candidate"]["id"],
                name=result["candidate"]["name"],
                dsl=result["candidate"]["dsl"],
                sample=sample,
                metrics=result["metrics"],
                promotion=result["promotion"],
                status="paper_candidate",
                requires_confirmation=True,
                created_at="2026-06-01T21:35:00+00:00",
            )

    monkeypatch.setattr(agentic_router, "paper_strategy_candidate_service", FakeService())
    monkeypatch.setattr(
        agentic_router,
        "validate_signal_provider",
        lambda **kwargs: type(
            "Validation",
            (),
            {
                "to_dict": lambda self: {
                    "confidence": "validated_positive",
                    "sample_days": 42,
                    "provider": "local_momentum",
                }
            },
        )(),
    )

    resp = client.post(
        "/api/agentic/strategy/paper-candidates",
        json={
            "result_id": "candidate_result_server_1",
            "sample": {"codes": ["999999"]},
            "result": {
                "promotion": {"promoted": True},
                "gate_checks": [{"id": "signal_validation", "passed": True}],
            },
        },
    )

    assert resp.status_code == 422


def test_agentic_paper_candidate_enqueue_revalidates_server_result(client, monkeypatch):
    from dashboard.routers import agentic as agentic_router

    class FakeService:
        def enqueue(self, result, sample):
            raise AssertionError("enqueue must not run when server-side signal validation fails")

    monkeypatch.setattr(
        agentic_router.agentic_repository,
        "get_candidate_backtest_result",
        lambda result_id: (
            {
                "candidate": {"id": "signal_ranked_core", "name": "AI信号基线轮动", "dsl": {"strategy_type": "ranked_rotation"}},
                "metrics": {"trades": 18, "max_drawdown": 0.08, "sharpe": 1.1},
                "promotion": {"promoted": True, "reason": "passed promotion gate"},
                "gate_checks": [
                    {"id": "data_quality", "passed": True},
                    {"id": "backtest_quality", "passed": True},
                    {"id": "risk_boundary", "passed": True},
                    {"id": "signal_validation", "passed": True, "detail": "此前通过 · 样本 42 天"},
                ],
            },
            {"codes": ["000001"]},
        ),
    )
    monkeypatch.setattr(agentic_router, "paper_strategy_candidate_service", FakeService())
    monkeypatch.setattr(
        agentic_router,
        "validate_signal_provider",
        lambda **kwargs: type(
            "Validation",
            (),
            {
                "to_dict": lambda self: {
                    "confidence": "validated_neutral",
                    "sample_days": 1,
                    "provider": "local_momentum",
                }
            },
        )(),
    )

    resp = client.post(
        "/api/agentic/strategy/paper-candidates",
        json={"result_id": "candidate_result_server_1"},
    )

    assert resp.status_code == 400
    assert "AI验证样本不足" in resp.json()["detail"]


def test_agentic_unpromoted_strategy_candidate_is_rejected_for_paper(client, monkeypatch):
    from dashboard.routers import agentic as agentic_router

    class FakeService:
        def enqueue(self, result, sample):
            raise ValueError("only promoted candidates can be queued for paper trading")

    monkeypatch.setattr(agentic_router, "paper_strategy_candidate_service", FakeService())
    monkeypatch.setattr(
        agentic_router.agentic_repository,
        "get_candidate_backtest_result",
        lambda result_id: ({"promotion": {"promoted": False}}, {"codes": ["000001"]}),
    )

    resp = client.post(
        "/api/agentic/strategy/paper-candidates",
        json={"result_id": "candidate_result_unpromoted_1"},
    )

    assert resp.status_code == 400
    assert "only promoted candidates" in resp.json()["detail"]


def test_agentic_paper_strategy_candidate_list_normalizes_legacy_qlib_names(client, monkeypatch):
    from dashboard.routers import agentic as agentic_router
    from agentic.models import PaperStrategyCandidate

    class FakeService:
        def list(self, limit=100):
            assert limit == 20
            return [
                PaperStrategyCandidate(
                    id="paper_strategy_1",
                    candidate_id="qlib_ranked_core",
                    name="Qlib 核心轮动",
                    dsl={"strategy_type": "ranked_rotation"},
                    sample={"codes": ["000001"]},
                    metrics={"trades": 18},
                    promotion={"promoted": True},
                    status="paper_candidate",
                    requires_confirmation=True,
                    created_at="2026-06-01T21:40:00+00:00",
                )
            ]

    monkeypatch.setattr(agentic_router, "paper_strategy_candidate_service", FakeService())

    resp = client.get("/api/agentic/strategy/paper-candidates?limit=20")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["candidates"][0]["candidate_id"] == "qlib_ranked_core"
    assert body["candidates"][0]["canonical_candidate_id"] == "signal_ranked_core"
    assert body["candidates"][0]["legacy_candidate_id"] == "qlib_ranked_core"
    assert body["candidates"][0]["name"] == "AI信号基线轮动"


def test_agentic_paper_strategy_candidate_can_be_confirmed(client, monkeypatch):
    from dashboard.routers import agentic as agentic_router
    from agentic.models import PaperStrategyCandidate
    from agentic.operations import OperationRecord

    class FakeService:
        class repository:
            @staticmethod
            def get_operation(operation_id):
                return OperationRecord(
                    operation_id=operation_id,
                    command="strategy.paper_candidate.confirm",
                    aggregate_type="paper_strategy_candidate",
                    aggregate_id="paper_strategy_1",
                    request={"candidate_id": "paper_strategy_1", "confirmed_by": "user-1", "to_status": "paper_active"},
                    request_hash="fixture",
                    status="completed",
                    result={"candidate_id": "paper_strategy_1", "status": "paper_active"},
                    created_at="2026-06-01T21:40:00+00:00",
                    completed_at="2026-06-01T21:40:00+00:00",
                )

        def confirm(self, candidate_id, **kwargs):
            assert candidate_id == "paper_strategy_1"
            return PaperStrategyCandidate(
                id="paper_strategy_1",
                candidate_id="qlib_ranked_core",
                name="Qlib 核心轮动",
                dsl={"strategy_type": "ranked_rotation"},
                sample={"codes": ["000001"]},
                metrics={"trades": 18},
                promotion={"promoted": True},
                status="paper_active",
                requires_confirmation=False,
                created_at="2026-06-01T21:40:00+00:00",
            )

    monkeypatch.setattr(agentic_router, "paper_strategy_candidate_service", FakeService())

    resp = client.post(
        "/api/agentic/strategy/paper-candidates/paper_strategy_1/confirm",
        json={"operation_id": "api-candidate-confirm-1", "confirmed_by": "user-1"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["candidate"]["candidate_id"] == "qlib_ranked_core"
    assert body["candidate"]["canonical_candidate_id"] == "signal_ranked_core"
    assert body["candidate"]["legacy_candidate_id"] == "qlib_ranked_core"
    assert body["candidate"]["name"] == "AI信号基线轮动"
    assert body["candidate"]["status"] == "paper_active"
    assert body["candidate"]["requires_confirmation"] is False
    assert body["operation"]["operation_id"] == "api-candidate-confirm-1"


def test_agentic_active_paper_strategy_candidate_can_generate_pending_intent(client, monkeypatch):
    from dashboard.routers import agentic as agentic_router
    from agentic.models import PaperStrategyExecution

    class FakeService:
        def run_active(self, candidate_id):
            assert candidate_id == "paper_strategy_1"
            return PaperStrategyExecution(
                id="paper_execution_1",
                candidate_record_id="paper_strategy_1",
                candidate_id="qlib_ranked_core",
                name="Qlib 核心轮动",
                dsl={"strategy_type": "ranked_rotation"},
                codes=("000001", "600519"),
                status="paper_intent_pending",
                reason="manual trigger generated a pending paper strategy intent",
                requires_confirmation=True,
                created_at="2026-06-01T21:50:00+00:00",
            )

    monkeypatch.setattr(agentic_router, "paper_strategy_candidate_service", FakeService())

    resp = client.post("/api/agentic/strategy/paper-candidates/paper_strategy_1/run")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["execution"]["candidate_id"] == "qlib_ranked_core"
    assert body["execution"]["canonical_candidate_id"] == "signal_ranked_core"
    assert body["execution"]["legacy_candidate_id"] == "qlib_ranked_core"
    assert body["execution"]["name"] == "AI信号基线轮动"
    assert body["execution"]["status"] == "paper_intent_pending"
    assert body["execution"]["requires_confirmation"] is True


def test_agentic_paper_execution_can_be_confirmed_with_risk_gate(client, monkeypatch):
    from dashboard.routers import agentic as agentic_router
    from agentic.models import PaperStrategyExecution

    class FakeService:
        def confirm_execution(self, execution_id, portfolio=None, risk_context=None, **kwargs):
            assert execution_id == "paper_execution_1"
            assert risk_context["cash_pct"] == 0.05
            return PaperStrategyExecution(
                id="paper_execution_1",
                candidate_record_id="paper_strategy_1",
                candidate_id="qlib_ranked_core",
                name="Qlib 核心轮动",
                dsl={"strategy_type": "ranked_rotation"},
                codes=("000001",),
                status="paper_intent_confirmed",
                reason="risk gate passed; ready for simulated order adapter",
                requires_confirmation=False,
                created_at="2026-06-01T22:00:00+00:00",
            )

    monkeypatch.setattr(agentic_router, "paper_strategy_candidate_service", FakeService())

    resp = client.post(
        "/api/agentic/strategy/paper-executions/paper_execution_1/confirm",
        json={"portfolio": {"total_equity": 100000, "positions": {}}, "risk_context": {"cash_pct": 0.05}},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["execution"]["candidate_id"] == "qlib_ranked_core"
    assert body["execution"]["canonical_candidate_id"] == "signal_ranked_core"
    assert body["execution"]["legacy_candidate_id"] == "qlib_ranked_core"
    assert body["execution"]["name"] == "AI信号基线轮动"
    assert body["execution"]["status"] == "paper_intent_confirmed"
    assert body["execution"]["requires_confirmation"] is False


def test_agentic_paper_execution_list_normalizes_legacy_qlib_names(client, monkeypatch):
    from dashboard.routers import agentic as agentic_router
    from agentic.models import PaperStrategyExecution

    class FakeService:
        def list_executions(self, limit=100):
            assert limit == 20
            return [
                PaperStrategyExecution(
                    id="paper_execution_1",
                    candidate_record_id="paper_strategy_1",
                    candidate_id="qlib_ranked_core",
                    name="Qlib 核心轮动",
                    dsl={"strategy_type": "ranked_rotation"},
                    codes=("000001",),
                    status="paper_intent_pending",
                    reason="manual trigger generated a pending paper strategy intent",
                    requires_confirmation=True,
                    created_at="2026-06-01T22:00:00+00:00",
                )
            ]

    monkeypatch.setattr(agentic_router, "paper_strategy_candidate_service", FakeService())

    resp = client.get("/api/agentic/strategy/paper-executions?limit=20")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["executions"][0]["candidate_id"] == "qlib_ranked_core"
    assert body["executions"][0]["canonical_candidate_id"] == "signal_ranked_core"
    assert body["executions"][0]["legacy_candidate_id"] == "qlib_ranked_core"
    assert body["executions"][0]["name"] == "AI信号基线轮动"


def test_agentic_confirmed_execution_can_create_order_drafts(client, monkeypatch):
    from dashboard.routers import agentic as agentic_router
    from agentic.models import AgenticPaperOrderDraft

    class FakeService:
        def create_order_drafts(self, execution_id, volume_per_code=100):
            assert execution_id == "paper_execution_1"
            assert volume_per_code == 200
            return [
                AgenticPaperOrderDraft(
                    id="agentic_order_draft_1",
                    execution_id=execution_id,
                    code="000001",
                    direction="buy",
                    order_type="market",
                    volume=200,
                    status="draft_pending",
                    strategy_name="agentic:qlib_ranked_core",
                    signal_reason="confirmed agentic paper intent paper_execution_1",
                    created_at="2026-06-01T22:20:00+00:00",
                )
            ]

    monkeypatch.setattr(agentic_router, "paper_strategy_candidate_service", FakeService())

    resp = client.post(
        "/api/agentic/strategy/paper-executions/paper_execution_1/order-drafts",
        json={"volume_per_code": 200},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["drafts"][0]["status"] == "draft_pending"
    assert body["drafts"][0]["volume"] == 200
    assert body["drafts"][0]["strategy_name"] == "agentic:qlib_ranked_core"
    assert body["drafts"][0]["strategy_display_id"] == "agentic:signal_ranked_core"
    assert body["drafts"][0]["legacy_strategy_name"] == "agentic:qlib_ranked_core"
    assert body["drafts"][0]["strategy_display_name"] == "AI信号基线轮动"


def test_agentic_confirmed_execution_can_submit_real_paper_orders(client, monkeypatch):
    from dashboard.routers import agentic as agentic_router
    from engine.models import Direction, OrderStatus, OrderType, PaperOrder

    class FakeService:
        def submit_confirmed_execution_orders(self, execution_id, volume_per_code=100):
            assert execution_id == "paper_execution_1"
            assert volume_per_code == 200
            return [
                PaperOrder(
                    order_id="ORD-AGENTIC1",
                    code="000001",
                    direction=Direction.LONG,
                    order_type=OrderType.MARKET,
                    volume=200,
                    status=OrderStatus.PENDING,
                    strategy_name="agentic:qlib_ranked_core",
                    signal_reason="confirmed agentic paper intent paper_execution_1",
                )
            ]

    monkeypatch.setattr(agentic_router, "paper_strategy_candidate_service", FakeService())

    resp = client.post(
        "/api/agentic/strategy/paper-executions/paper_execution_1/paper-orders",
        json={"volume_per_code": 200},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["orders"][0]["order_id"] == "ORD-AGENTIC1"
    assert body["orders"][0]["status"] == "pending"
    assert body["orders"][0]["strategy_name"] == "agentic:signal_ranked_core"
    assert body["orders"][0]["legacy_strategy_name"] == "agentic:qlib_ranked_core"
    assert body["orders"][0]["strategy_display_name"] == "AI信号基线轮动"


def test_agentic_paper_strategy_write_apis_are_idempotent_and_expose_conflicts(
    client, monkeypatch, tmp_path
):
    from dashboard.routers import agentic as agentic_router
    from agentic.paper_strategy_candidates import PaperStrategyCandidateService
    from agentic.repository import AgenticRepository
    from agentic.strategy_candidates import StrategyCandidateGenerator
    from engine.order_manager import OrderManager

    repo = AgenticRepository(tmp_path / "agentic.db")
    service = PaperStrategyCandidateService(repo, order_manager=OrderManager(str(tmp_path / "paper_trading.db")))
    monkeypatch.setattr(agentic_router, "agentic_repository", repo)
    monkeypatch.setattr(agentic_router, "paper_strategy_candidate_service", service)
    monkeypatch.setattr(
        agentic_router,
        "validate_signal_provider",
        lambda **kwargs: type(
            "Validation",
            (),
            {
                "to_dict": lambda self: {
                    "confidence": "validated_positive",
                    "sample_days": 42,
                    "provider": "local_momentum",
                }
            },
        )(),
    )

    candidates = StrategyCandidateGenerator().generate(limit=2)
    sample = {"codes": ["000001", "600519"], "trading_days": 60}

    def save_result(candidate):
        return repo.save_candidate_backtest_result(
            {
                "candidate": candidate.to_dict(),
                "metrics": {"trades": 18, "max_drawdown": 0.08, "sharpe": 1.1},
                "promotion": {"promoted": True, "reason": "passed promotion gate"},
                "gate_checks": [
                    {"id": "data_quality", "passed": True},
                    {"id": "backtest_quality", "passed": True},
                    {"id": "risk_boundary", "passed": True},
                    {"id": "signal_validation", "passed": True, "detail": "fixture validated"},
                ],
            },
            sample,
        )

    result_id = save_result(candidates[0])
    enqueue_payload = {"result_id": result_id, "operation_id": "api-paper-enqueue-1"}
    first = client.post("/api/agentic/strategy/paper-candidates", json=enqueue_payload)
    assert first.status_code == 200
    assert first.json()["operation_status"] == "completed"
    assert first.json()["operation_state"] == "completed"
    candidate_id = first.json()["candidate"]["id"]

    replay = client.post("/api/agentic/strategy/paper-candidates", json=enqueue_payload)
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["operation_state"] == "replayed"
    assert replay.json()["message"] == "已恢复"

    second_result_id = save_result(candidates[1])
    conflict = client.post(
        "/api/agentic/strategy/paper-candidates",
        json={"result_id": second_result_id, "operation_id": "api-paper-enqueue-1"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "operation_conflict"
    assert conflict.json()["detail"]["message"] == "操作冲突：同一个 operation id 对应的请求事实已改变"

    confirm_payload = {"operation_id": "api-paper-confirm-1", "confirmed_by": "user-1"}
    confirmed = client.post(
        f"/api/agentic/strategy/paper-candidates/{candidate_id}/confirm",
        json=confirm_payload,
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["operation_status"] == "completed"
    confirmed_replay = client.post(
        f"/api/agentic/strategy/paper-candidates/{candidate_id}/confirm",
        json=confirm_payload,
    )
    assert confirmed_replay.status_code == 200
    assert confirmed_replay.json()["replayed"] is True
    confirmed_conflict = client.post(
        f"/api/agentic/strategy/paper-candidates/{candidate_id}/confirm",
        json={"operation_id": "api-paper-confirm-1", "confirmed_by": "user-2"},
    )
    assert confirmed_conflict.status_code == 409

    run_payload = {"operation_id": "api-paper-run-1"}
    execution = client.post(
        f"/api/agentic/strategy/paper-candidates/{candidate_id}/run",
        json=run_payload,
    )
    assert execution.status_code == 200
    assert execution.json()["operation_status"] == "completed"
    execution_replay = client.post(
        f"/api/agentic/strategy/paper-candidates/{candidate_id}/run",
        json=run_payload,
    )
    assert execution_replay.status_code == 200
    assert execution_replay.json()["replayed"] is True
    execution_id = execution.json()["execution"]["id"]

    risk_payload = {
        "operation_id": "api-paper-risk-1",
        "confirmed_by": "user-1",
        "portfolio": {"total_equity": 100000, "positions": {}},
        "risk_context": {"cash_pct": 0.05},
    }
    risk = client.post(
        f"/api/agentic/strategy/paper-executions/{execution_id}/confirm",
        json=risk_payload,
    )
    assert risk.status_code == 200
    assert risk.json()["operation_status"] == "completed"
    risk_replay = client.post(
        f"/api/agentic/strategy/paper-executions/{execution_id}/confirm",
        json=risk_payload,
    )
    assert risk_replay.status_code == 200
    assert risk_replay.json()["replayed"] is True
    risk_conflict = client.post(
        f"/api/agentic/strategy/paper-executions/{execution_id}/confirm",
        json={**risk_payload, "risk_context": {"cash_pct": 0.06}},
    )
    assert risk_conflict.status_code == 409

    draft_payload = {"volume_per_code": 100, "operation_id": "api-paper-drafts-1"}
    drafts = client.post(
        f"/api/agentic/strategy/paper-executions/{execution_id}/order-drafts",
        json=draft_payload,
    )
    assert drafts.status_code == 200
    assert drafts.json()["operation_status"] == "completed"
    drafts_replay = client.post(
        f"/api/agentic/strategy/paper-executions/{execution_id}/order-drafts",
        json=draft_payload,
    )
    assert drafts_replay.status_code == 200
    assert drafts_replay.json()["replayed"] is True
    drafts_conflict = client.post(
        f"/api/agentic/strategy/paper-executions/{execution_id}/order-drafts",
        json={"volume_per_code": 200, "operation_id": "api-paper-drafts-1"},
    )
    assert drafts_conflict.status_code == 409

    orders_payload = {"volume_per_code": 100, "operation_id": "api-paper-orders-1"}
    orders = client.post(
        f"/api/agentic/strategy/paper-executions/{execution_id}/paper-orders",
        json=orders_payload,
    )
    assert orders.status_code == 200
    assert orders.json()["operation_status"] == "completed"
    orders_replay = client.post(
        f"/api/agentic/strategy/paper-executions/{execution_id}/paper-orders",
        json=orders_payload,
    )
    assert orders_replay.status_code == 200
    assert orders_replay.json()["replayed"] is True
    orders_conflict = client.post(
        f"/api/agentic/strategy/paper-executions/{execution_id}/paper-orders",
        json={"volume_per_code": 200, "operation_id": "api-paper-orders-1"},
    )
    assert orders_conflict.status_code == 409


def test_agentic_paper_order_write_reports_recoverable_sync_failure(client, monkeypatch, tmp_path):
    from dashboard.routers import agentic as agentic_router
    from agentic.paper_strategy_candidates import PaperOrderRecoveryRequired
    from engine.models import Direction, OrderStatus, OrderType, PaperOrder

    order = PaperOrder(
        order_id="ORD-RECOVERABLE",
        code="000001",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        volume=100,
        status=OrderStatus.PENDING,
        strategy_name="agentic:signal_ranked_core",
        signal_reason="fixture",
    )

    class RecoveryService:
        def submit_confirmed_execution_orders(self, execution_id, volume_per_code=100, **kwargs):
            raise PaperOrderRecoveryRequired("api-recovery-1", [order], RuntimeError("sync failed"))

    monkeypatch.setattr(agentic_router, "paper_strategy_candidate_service", RecoveryService())

    response = client.post(
        "/api/agentic/strategy/paper-executions/paper_execution_1/paper-orders",
        json={"volume_per_code": 100, "operation_id": "api-recovery-1"},
    )

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "paper_order_recovery_required"
    assert detail["recoverable"] is True
    assert detail["operation_id"] == "api-recovery-1"
    assert detail["message"] == "订单已写入，但 Agentic 状态更新失败，可恢复"


def test_agentic_legacy_fake_write_adapters_remain_callable(client, monkeypatch):
    from dashboard.routers import agentic as agentic_router
    from agentic.models import AgenticPaperOrderDraft, PaperStrategyExecution

    class LegacyService:
        def run_active(self, candidate_id):
            return PaperStrategyExecution(
                id="legacy-execution-1",
                candidate_record_id=candidate_id,
                candidate_id="signal_ranked_core",
                name="AI信号基线轮动",
                dsl={"strategy_type": "ranked_rotation"},
                codes=("000001",),
                status="paper_intent_pending",
                reason="legacy adapter",
                requires_confirmation=True,
                created_at="2026-06-01T22:00:00+00:00",
            )

        def create_order_drafts(self, execution_id, volume_per_code=100):
            return [
                AgenticPaperOrderDraft(
                    id="legacy-draft-1",
                    execution_id=execution_id,
                    code="000001",
                    direction="buy",
                    order_type="market",
                    volume=volume_per_code,
                    status="draft_pending",
                    strategy_name="agentic:signal_ranked_core",
                    signal_reason="legacy adapter",
                    created_at="2026-06-01T22:00:00+00:00",
                )
            ]

    monkeypatch.setattr(agentic_router, "paper_strategy_candidate_service", LegacyService())

    run = client.post("/api/agentic/strategy/paper-candidates/legacy-candidate/run")
    assert run.status_code == 200
    assert run.json()["execution"]["id"] == "legacy-execution-1"

    drafts = client.post(
        "/api/agentic/strategy/paper-executions/legacy-execution-1/order-drafts",
        json={"volume_per_code": 200},
    )
    assert drafts.status_code == 200
    assert drafts.json()["drafts"][0]["volume"] == 200
