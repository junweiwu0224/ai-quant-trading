from agentic.strategy_dsl import StrategyDSL, validate_strategy_dsl


def test_strategy_dsl_accepts_ranked_rotation_template():
    dsl = StrategyDSL("ranked_rotation", "signal_top", "signal_score", [{"signal_score_min": 0.5}, {"close_above_ma": 20}], "daily", 5, 0.05, 0.12, 10)
    assert validate_strategy_dsl(dsl).max_holdings == 5


def test_strategy_dsl_keeps_legacy_qlib_aliases():
    dsl = StrategyDSL("ranked_rotation", "qlib_top", "qlib_score", [{"qlib_score_min": 0.5}], "daily", 5, 0.05, 0.12, 10)
    normalized = validate_strategy_dsl(dsl)

    assert normalized.universe == "signal_top"
    assert normalized.rank_by == "signal_score"
    assert normalized.filters == [{"signal_score_min": 0.5}]


def test_strategy_dsl_rejects_unsafe_strategy_type():
    dsl = StrategyDSL("python_exec", "qlib_top", "qlib_score", [], "daily", 5, 0.05, None, None)
    try:
        validate_strategy_dsl(dsl)
    except ValueError as exc:
        assert "unsupported strategy_type" in str(exc)
    else:
        raise AssertionError("unsafe DSL should be rejected")


def test_strategy_dsl_rejects_malformed_bounds_and_filters():
    cases = [
        (StrategyDSL("ranked_rotation", "all", "qlib_score", [], "daily", 5, 0.05, None, None), "unsupported universe"),
        (StrategyDSL("ranked_rotation", "qlib_top", "custom_code", [], "daily", 5, 0.05, None, None), "unsupported rank_by"),
        (StrategyDSL("ranked_rotation", "qlib_top", "qlib_score", [], "tick", 5, 0.05, None, None), "unsupported rebalance"),
        (StrategyDSL("ranked_rotation", "qlib_top", "qlib_score", [], "daily", 5.5, 0.05, None, None), "max_holdings"),
        (StrategyDSL("ranked_rotation", "qlib_top", "qlib_score", [], "daily", True, 0.05, None, None), "max_holdings"),
        (StrategyDSL("ranked_rotation", "qlib_top", "qlib_score", [], "daily", 5, 0, None, None), "stop_loss"),
        (StrategyDSL("ranked_rotation", "qlib_top", "qlib_score", [], "daily", 5, 0.05, -0.1, None), "take_profit"),
        (StrategyDSL("ranked_rotation", "qlib_top", "qlib_score", [], "daily", 5, 0.05, None, 0), "max_holding_days"),
        (StrategyDSL("ranked_rotation", "qlib_top", "qlib_score", [{"python": "exec"}], "daily", 5, 0.05, None, None), "unsupported filter"),
    ]

    for dsl, message in cases:
        try:
            validate_strategy_dsl(dsl)
        except ValueError as exc:
            assert message in str(exc)
        else:
            raise AssertionError(f"{dsl} should be rejected")
