from agentic.strategy_candidates import StrategyCandidateGenerator
from agentic.strategy_dsl import validate_strategy_dsl


def test_strategy_candidate_generator_returns_valid_default_candidates():
    candidates = StrategyCandidateGenerator().generate(limit=4)

    assert len(candidates) == 4
    assert [item.id for item in candidates] == [
        "signal_ranked_core",
        "signal_threshold_quality",
        "hotspot_volume_rotation",
        "defensive_mean_reversion",
    ]
    assert candidates[0].dsl.universe == "signal_top"
    assert candidates[0].dsl.rank_by == "signal_score"
    assert candidates[0].dsl.filters[0] == {"signal_score_min": 0.5}
    for candidate in candidates:
        validate_strategy_dsl(candidate.dsl)
        assert candidate.name
        assert candidate.thesis
        assert candidate.risk_notes


def test_strategy_candidate_generator_adapts_to_context():
    candidates = StrategyCandidateGenerator().generate(
        context={"universe": "iwencai_pool", "risk_mode": "conservative", "max_holdings": 3},
        limit=2,
    )

    assert [item.dsl.universe for item in candidates] == ["iwencai_pool", "iwencai_pool"]
    assert all(item.dsl.max_holdings == 3 for item in candidates)
    assert all(item.dsl.stop_loss <= 0.04 for item in candidates)


def test_strategy_candidate_generator_ignores_invalid_context_values():
    candidates = StrategyCandidateGenerator().generate(
        context={"universe": "invalid", "max_holdings": 99, "risk_mode": "unknown"},
        limit=1,
    )

    assert candidates[0].dsl.universe == "signal_top"
    assert candidates[0].dsl.max_holdings == 5
    assert candidates[0].dsl.stop_loss == 0.05
