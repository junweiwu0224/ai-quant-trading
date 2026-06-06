from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentic.models import normalize_signal_code
from agentic.strategy_dsl import StrategyDSL, validate_strategy_dsl


@dataclass(frozen=True)
class BacktestCompileRequest:
    dsl: StrategyDSL
    codes: list[str]
    start_date: str
    end_date: str
    initial_cash: float = 1_000_000
    commission_rate: float = 0.0003
    stamp_tax_rate: float = 0.001
    slippage: float = 0.002
    benchmark: str = ""
    period: str = "daily"


class BacktestCompiler:
    def compile(self, request: BacktestCompileRequest) -> dict[str, Any]:
        dsl = validate_strategy_dsl(request.dsl)
        codes = _normalize_codes(request.codes)
        if not codes:
            raise ValueError("codes is required for backtest compilation")

        if dsl.strategy_type == "ranked_rotation" and dsl.rank_by in {"signal_score", "qlib_score"}:
            strategy = "qlib_signal"
            params = {
                "mode": "ranking",
                "top_n": dsl.max_holdings,
                "position_pct": 0.9,
                "score_normalize": True,
            }
        elif dsl.strategy_type == "threshold_signal" and dsl.rank_by in {"signal_score", "qlib_score"}:
            strategy = "qlib_signal"
            params = {
                "mode": "absolute",
                "buy_threshold": _filter_value(dsl.filters, "signal_score_min", _filter_value(dsl.filters, "qlib_score_min", 0.5)),
                "sell_threshold": -0.3,
                "position_pct": 0.9,
                "score_normalize": True,
            }
        elif dsl.strategy_type == "mean_reversion":
            strategy = "rsi"
            params = {"period": 14, "oversold": 30, "overbought": 70, "position_pct": 0.9}
        else:
            strategy = "momentum"
            params = {"lookback": 20, "entry_threshold": 0.05, "position_pct": 0.9}

        return {
            "strategy": strategy,
            "codes": codes,
            "start_date": request.start_date,
            "end_date": request.end_date,
            "initial_cash": request.initial_cash,
            "commission_rate": request.commission_rate,
            "stamp_tax_rate": request.stamp_tax_rate,
            "slippage": request.slippage,
            "benchmark": request.benchmark,
            "period": request.period,
            "enable_risk": True,
            "risk_config": {
                "stop_loss_pct": dsl.stop_loss,
                "take_profit_pct": dsl.take_profit or 0.2,
                "max_drawdown_pct": 0.15,
                "max_single_position_pct": min(0.2, 1 / max(1, dsl.max_holdings)),
                "daily_loss_pct": 0.03,
            },
            "params": params,
            "agentic": {
                "strategy_type": dsl.strategy_type,
                "universe": dsl.universe,
                "rank_by": dsl.rank_by,
                "filters": dsl.filters,
                "rebalance": dsl.rebalance,
                "max_holding_days": dsl.max_holding_days,
            },
        }


def extract_promotion_metrics(backtest_response: dict[str, Any]) -> dict[str, Any]:
    return {
        "trades": int(backtest_response.get("total_trades", 0) or 0),
        "max_drawdown": float(backtest_response.get("max_drawdown", 0) or 0),
        "sharpe": float(backtest_response.get("sharpe_ratio", 0) or 0),
        "annual_return": float(backtest_response.get("annual_return", 0) or 0),
        "total_return": float(backtest_response.get("total_return", 0) or 0),
    }


def _normalize_codes(codes: list[str]) -> list[str]:
    seen = set()
    result = []
    for code in codes or []:
        normalized = normalize_signal_code(code)
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _filter_value(filters: list[dict[str, Any]], key: str, default: Any) -> Any:
    for item in filters:
        if key in item:
            return item[key]
    return default
