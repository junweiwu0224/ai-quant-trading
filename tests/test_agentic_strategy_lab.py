from agentic.strategy_dsl import StrategyDSL
from agentic.strategy_lab import PromotionGate, StrategyLab


def test_strategy_lab_promotes_only_when_metrics_pass_gate():
    lab = StrategyLab(PromotionGate(min_trades=10, max_drawdown=0.12, min_sharpe=0.8))
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
    result = lab.evaluate_iteration(
        dsl,
        {"trades": 18, "max_drawdown": 0.08, "sharpe": 1.1, "annual_return": 0.22},
    )
    assert result.promoted is True
    assert result.reason == "passed promotion gate"
