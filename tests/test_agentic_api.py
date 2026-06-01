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
    assert body["candidates"][0]["id"] == "qlib_ranked_core"
    assert body["candidates"][0]["dsl"]["universe"] == "iwencai_pool"
    assert body["candidates"][0]["dsl"]["max_holdings"] == 3
    assert body["candidates"][0]["dsl"]["stop_loss"] <= 0.04
