from __future__ import annotations

import pandas as pd
import pytest

from alpha.backtest import PortfolioBacktester
from engine.execution_model import ExecutionCostModelVersion


def test_versioned_round_trip_uses_the_declared_fill_prices() -> None:
    model = ExecutionCostModelVersion(
        version="fixture-v1",
        commission_rate=0,
        stamp_tax_rate=0,
        buy_slippage=0.01,
        sell_slippage=0.02,
        min_commission=0,
    )

    assert model.round_trip_return(100, 110) == pytest.approx((110 * 0.98) / (100 * 1.01) - 1)


def test_alpha_backtest_executes_a_close_signal_on_the_next_open() -> None:
    prices = pd.DataFrame([
        {"date": "2024-01-01", "open": 100, "high": 110, "low": 90, "close": 100, "volume": 1000},
        {"date": "2024-01-02", "open": 200, "high": 210, "low": 190, "close": 205, "volume": 1000},
        {"date": "2024-01-03", "open": 210, "high": 220, "low": 200, "close": 215, "volume": 1000},
    ])

    result = PortfolioBacktester().run(
        {"2024-01-01": [{"code": "600519", "probability": 1.0}]},
        {"600519": prices},
    )

    assert result.trades[0]["date"] == "2024-01-02"
    assert result.trades[0]["price"] == pytest.approx(200.2)
    assert result.execution_contract["execution_rule"] == "signal_at_close_then_next_tradable_bar_open"
