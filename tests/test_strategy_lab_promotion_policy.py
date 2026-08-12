from agentic.strategy_dsl import StrategyDSL
from agentic.strategy_lab import PromotionGate, StrategyLab


def test_strategy_lab_exposes_the_canonical_promotion_decision():
    dsl = StrategyDSL(
        "ranked_rotation",
        "signal_top",
        "signal_score",
        [{"close_above_ma": 20}],
        "daily",
        5,
        0.05,
        0.12,
        10,
    )
    result = StrategyLab(PromotionGate(min_trades=1, max_drawdown=0.2, min_sharpe=0.1)).evaluate_iteration(
        dsl,
        {"trades": 2, "max_drawdown": 0.05, "sharpe": 0.8},
    )
    assert result.promoted
    assert result.promotion_decision is not None
    assert result.promotion_decision.target == "strategy_candidate"
    assert result.promotion_decision.policy_version == "promotion-v1"
