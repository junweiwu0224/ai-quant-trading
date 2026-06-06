from math import nan

from agentic.strategy_dsl import StrategyDSL
from agentic.strategy_lab import PromotionGate, StrategyLab


def valid_dsl():
    return StrategyDSL("ranked_rotation", "signal_top", "signal_score", [{"close_above_ma": 20}], "daily", 5, 0.05, 0.12, 10)


def test_strategy_lab_promotes_only_when_metrics_pass_gate():
    lab = StrategyLab(PromotionGate(min_trades=10, max_drawdown=0.12, min_sharpe=0.8))
    result = lab.evaluate_iteration(valid_dsl(), {"trades": 18, "max_drawdown": 0.08, "sharpe": 1.1, "annual_return": 0.22})
    assert result.promoted is True
    assert result.reason == "passed promotion gate"


def test_strategy_lab_rejects_gate_failures_and_bad_metrics():
    lab = StrategyLab(PromotionGate(min_trades=10, max_drawdown=0.12, min_sharpe=0.8))
    cases = [
        ({"trades": 9, "max_drawdown": 0.08, "sharpe": 1.1}, "insufficient trades"),
        ({"trades": 18, "max_drawdown": 0.2, "sharpe": 1.1}, "max drawdown exceeded"),
        ({"trades": 18, "max_drawdown": 0.08, "sharpe": 0.7}, "sharpe below threshold"),
        ({"max_drawdown": 0.08, "sharpe": 1.1}, "missing metric: trades"),
        ({"trades": nan, "max_drawdown": nan, "sharpe": nan}, "metric trades must be finite"),
    ]
    for metrics, reason in cases:
        result = lab.evaluate_iteration(valid_dsl(), metrics)
        assert result.promoted is False
        assert result.reason == reason
