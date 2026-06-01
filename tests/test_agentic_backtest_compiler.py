from agentic.backtest_compiler import BacktestCompileRequest, BacktestCompiler, extract_promotion_metrics
from agentic.strategy_dsl import StrategyDSL


def test_compiler_maps_ranked_rotation_qlib_dsl_to_backtest_request():
    dsl = StrategyDSL(
        strategy_type="ranked_rotation",
        universe="qlib_top",
        rank_by="qlib_score",
        filters=[{"close_above_ma": 20}],
        rebalance="daily",
        max_holdings=5,
        stop_loss=0.05,
        take_profit=0.12,
        max_holding_days=10,
    )
    compiler = BacktestCompiler()

    req = compiler.compile(
        BacktestCompileRequest(
            dsl=dsl,
            codes=["605066.SH", "000001"],
            start_date="2024-01-01",
            end_date="2024-12-31",
            initial_cash=50000,
        )
    )

    assert req["strategy"] == "qlib_signal"
    assert req["codes"] == ["605066", "000001"]
    assert req["start_date"] == "2024-01-01"
    assert req["end_date"] == "2024-12-31"
    assert req["initial_cash"] == 50000
    assert req["enable_risk"] is True
    assert req["params"]["mode"] == "ranking"
    assert req["params"]["top_n"] == 5
    assert req["params"]["position_pct"] == 0.9
    assert req["risk_config"]["stop_loss_pct"] == 0.05
    assert req["risk_config"]["take_profit_pct"] == 0.12


def test_compiler_rejects_empty_codes():
    dsl = StrategyDSL("ranked_rotation", "qlib_top", "qlib_score", [], "daily", 5, 0.05, None, 10)

    try:
        BacktestCompiler().compile(BacktestCompileRequest(dsl, [], "2024-01-01", "2024-12-31", 50000))
    except ValueError as exc:
        assert "codes is required" in str(exc)
    else:
        raise AssertionError("empty codes should be rejected")


def test_extract_promotion_metrics_from_backtest_response():
    metrics = extract_promotion_metrics(
        {
            "total_trades": 18,
            "max_drawdown": 0.08,
            "sharpe_ratio": 1.1,
            "annual_return": 0.22,
            "total_return": 0.18,
        }
    )

    assert metrics == {
        "trades": 18,
        "max_drawdown": 0.08,
        "sharpe": 1.1,
        "annual_return": 0.22,
        "total_return": 0.18,
    }
