from agentic.portfolio_risk import PortfolioRiskGate, PortfolioRiskLimits


def test_portfolio_risk_gate_allows_valid_intent():
    gate = PortfolioRiskGate(
        PortfolioRiskLimits(
            max_strategy_cash_pct=0.2,
            max_position_pct=0.1,
            max_holdings=5,
            blacklist={"600519"},
            max_industry_pct=0.4,
        )
    )

    result = gate.evaluate(
        intent={"cash_pct": 0.15, "codes": ["000001", "000333"]},
        portfolio={"total_equity": 100000, "positions": {"600000": 8000}},
        industry_map={"000001": "bank", "000333": "home", "600000": "bank"},
    )

    assert result.allowed is True
    assert result.reasons == ()


def test_portfolio_risk_gate_rejects_blacklist_and_limits():
    gate = PortfolioRiskGate(
        PortfolioRiskLimits(
            max_strategy_cash_pct=0.1,
            max_position_pct=0.05,
            max_holdings=2,
            blacklist={"600519"},
            max_industry_pct=0.2,
        )
    )

    result = gate.evaluate(
        intent={"cash_pct": 0.3, "codes": ["600519", "000001", "600000"]},
        portfolio={"total_equity": 100000, "positions": {"300750": 10000}},
        industry_map={"600519": "food", "000001": "bank", "600000": "bank", "300750": "battery"},
    )

    assert result.allowed is False
    assert "blacklisted code: 600519" in result.reasons
    assert "strategy cash pct 0.3000 exceeds 0.1000" in result.reasons
    assert "position pct 0.1000 exceeds 0.0500" in result.reasons
    assert "holding count 4 exceeds 2" in result.reasons
    assert "industry bank pct 0.2000 reaches limit 0.2000" in result.reasons
