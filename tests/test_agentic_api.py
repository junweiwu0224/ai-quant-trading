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
                "universe": "qlib_top",
                "rank_by": "qlib_score",
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
                "universe": "qlib_top",
                "rank_by": "qlib_score",
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
