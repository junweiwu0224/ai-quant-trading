def test_agentic_agents_endpoint_lists_builtin_agents(client):
    resp = client.get("/api/agentic/agents")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert any(item["id"] == "qlib_agent" for item in body["agents"])


def test_agentic_signals_endpoint_returns_list(client, monkeypatch, tmp_path):
    from dashboard.routers import agentic as agentic_router
    from agentic.repository import AgenticRepository
    from agentic.signals import SignalService

    monkeypatch.setattr(agentic_router, "signal_service", SignalService(AgenticRepository(tmp_path / "agentic.db")))

    resp = client.get("/api/agentic/signals")

    assert resp.status_code == 200
    assert resp.json() == {"success": True, "signals": []}


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
    assert req["strategy"] == "qlib_signal"
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
            assert context == {"universe": "signal_top", "risk_mode": "balanced", "max_holdings": 5}
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
    assert body["results"][0]["promotion"]["promoted"] is True


def test_agentic_promoted_strategy_candidate_can_be_queued_for_paper(client, monkeypatch):
    from dashboard.routers import agentic as agentic_router
    from agentic.models import PaperStrategyCandidate

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

    monkeypatch.setattr(agentic_router, "paper_strategy_candidate_service", FakeService())

    resp = client.post(
        "/api/agentic/strategy/paper-candidates",
        json={
            "sample": {"codes": ["000001"]},
            "result": {
                "candidate": {"id": "qlib_ranked_core", "name": "Qlib 核心轮动", "dsl": {"strategy_type": "ranked_rotation"}},
                "metrics": {"trades": 18, "max_drawdown": 0.08, "sharpe": 1.1},
                "promotion": {"promoted": True, "reason": "passed promotion gate"},
            },
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["candidate"]["candidate_id"] == "qlib_ranked_core"
    assert body["candidate"]["name"] == "AI信号基线轮动"
    assert body["candidate"]["status"] == "paper_candidate"
    assert body["candidate"]["requires_confirmation"] is True


def test_agentic_unpromoted_strategy_candidate_is_rejected_for_paper(client, monkeypatch):
    from dashboard.routers import agentic as agentic_router

    class FakeService:
        def enqueue(self, result, sample):
            raise ValueError("only promoted candidates can be queued for paper trading")

    monkeypatch.setattr(agentic_router, "paper_strategy_candidate_service", FakeService())

    resp = client.post(
        "/api/agentic/strategy/paper-candidates",
        json={"sample": {"codes": ["000001"]}, "result": {"promotion": {"promoted": False}}},
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
    assert body["candidates"][0]["name"] == "AI信号基线轮动"


def test_agentic_paper_strategy_candidate_can_be_confirmed(client, monkeypatch):
    from dashboard.routers import agentic as agentic_router
    from agentic.models import PaperStrategyCandidate

    class FakeService:
        def confirm(self, candidate_id):
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

    resp = client.post("/api/agentic/strategy/paper-candidates/paper_strategy_1/confirm")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["candidate"]["candidate_id"] == "qlib_ranked_core"
    assert body["candidate"]["name"] == "AI信号基线轮动"
    assert body["candidate"]["status"] == "paper_active"
    assert body["candidate"]["requires_confirmation"] is False


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
    assert body["execution"]["name"] == "AI信号基线轮动"
    assert body["execution"]["status"] == "paper_intent_pending"
    assert body["execution"]["requires_confirmation"] is True


def test_agentic_paper_execution_can_be_confirmed_with_risk_gate(client, monkeypatch):
    from dashboard.routers import agentic as agentic_router
    from agentic.models import PaperStrategyExecution

    class FakeService:
        def confirm_execution(self, execution_id, portfolio=None, risk_context=None):
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
