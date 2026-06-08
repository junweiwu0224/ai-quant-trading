from agentic.backtest_compiler import BacktestCompileRequest, BacktestCompiler, extract_promotion_metrics
from agentic.strategy_dsl import StrategyDSL


def test_compiler_maps_ranked_rotation_signal_dsl_to_backtest_request():
    dsl = StrategyDSL(
        strategy_type="ranked_rotation",
        universe="signal_top",
        rank_by="signal_score",
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
    assert req["strategy_display_name"] == "AI信号策略"
    assert req["legacy_strategy"] == "qlib_signal"
    assert req["agentic"]["signal_strategy"] == "signal_score_strategy"
    assert req["agentic"]["strategy_adapter"] == "qlib_signal"
    assert req["agentic"]["is_legacy_adapter"] is True
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


def test_compiler_normalizes_legacy_qlib_dsl_to_signal_metadata():
    dsl = StrategyDSL(
        strategy_type="threshold_signal",
        universe="qlib_top",
        rank_by="qlib_score",
        filters=[{"qlib_score_min": 0.7}],
        rebalance="daily",
        max_holdings=3,
        stop_loss=0.05,
        take_profit=None,
        max_holding_days=8,
    )

    req = BacktestCompiler().compile(
        BacktestCompileRequest(dsl, ["600519"], "2024-01-01", "2024-12-31", 50000)
    )

    assert req["strategy"] == "qlib_signal"
    assert req["legacy_strategy"] == "qlib_signal"
    assert req["strategy_display_name"] == "AI信号策略"
    assert req["params"]["buy_threshold"] == 0.7
    assert req["agentic"]["universe"] == "signal_top"
    assert req["agentic"]["rank_by"] == "signal_score"
    assert req["agentic"]["filters"] == [{"signal_score_min": 0.7}]
    assert req["agentic"]["legacy_aliases"] == {
        "universe": "qlib_top",
        "rank_by": "qlib_score",
        "filters": ["qlib_score_min"],
    }


def test_compiler_rejects_empty_codes():
    dsl = StrategyDSL("ranked_rotation", "signal_top", "signal_score", [], "daily", 5, 0.05, None, 10)

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
