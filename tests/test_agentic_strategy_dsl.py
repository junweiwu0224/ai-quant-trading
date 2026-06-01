from agentic.strategy_dsl import StrategyDSL, validate_strategy_dsl


def test_strategy_dsl_accepts_ranked_rotation_template():
    dsl = StrategyDSL(
        "ranked_rotation",
        "qlib_top",
        "qlib_score",
        [{"close_above_ma": 20}],
        "daily",
        5,
        0.05,
        0.12,
        10,
    )
    assert validate_strategy_dsl(dsl).max_holdings == 5


def test_strategy_dsl_rejects_unsafe_strategy_type():
    dsl = StrategyDSL("python_exec", "all", "custom_code", [], "tick", 50, None, None, None)
    try:
        validate_strategy_dsl(dsl)
    except ValueError as exc:
        assert "unsupported strategy_type" in str(exc)
    else:
        raise AssertionError("unsafe DSL should be rejected")
