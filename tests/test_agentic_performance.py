from agentic.performance import AgentPerformanceCalculator


def test_agent_performance_calculates_win_rate_and_average_return():
    calc = AgentPerformanceCalculator()

    snapshot = calc.calculate(
        "qlib_agent",
        [
            {"return": 0.05, "max_drawdown": 0.02},
            {"return": -0.02, "max_drawdown": 0.04},
            {"return": 0.03, "max_drawdown": 0.01},
        ],
    )

    assert snapshot["agent_id"] == "qlib_agent"
    assert snapshot["signal_count"] == 3
    assert snapshot["win_rate"] == 2 / 3
    assert round(snapshot["avg_return"], 4) == 0.02
    assert snapshot["max_drawdown"] == 0.04
