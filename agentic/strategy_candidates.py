from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from agentic.strategy_dsl import SUPPORTED_UNIVERSES, StrategyDSL, validate_strategy_dsl


@dataclass(frozen=True)
class StrategyCandidate:
    id: str
    name: str
    thesis: str
    dsl: StrategyDSL
    risk_notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["dsl"] = asdict(self.dsl)
        return payload


class StrategyCandidateGenerator:
    def generate(self, context: dict[str, Any] | None = None, limit: int = 4) -> list[StrategyCandidate]:
        context = dict(context or {})
        universe = _safe_universe(context.get("universe"), default="qlib_top")
        max_holdings = _safe_max_holdings(context.get("max_holdings"), default=5)
        risk_mode = str(context.get("risk_mode") or "balanced").lower()
        stop_loss = 0.035 if risk_mode == "conservative" else 0.05
        take_profit = 0.10 if risk_mode == "conservative" else 0.12
        templates = [
            StrategyCandidate(
                id="qlib_ranked_core",
                name="Qlib 核心轮动",
                thesis="优先验证 Qlib Top 中预测分最高的一组股票，适合作为 Agent 默认基线。",
                dsl=StrategyDSL(
                    strategy_type="ranked_rotation",
                    universe=universe,
                    rank_by="qlib_score",
                    filters=[{"qlib_score_min": 0.5}, {"close_above_ma": 20}],
                    rebalance="daily",
                    max_holdings=max_holdings,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    max_holding_days=10,
                ),
                risk_notes=["依赖 Qlib 覆盖率", "需要样本回测确认换手和回撤"],
            ),
            StrategyCandidate(
                id="qlib_threshold_quality",
                name="Qlib 阈值质量筛选",
                thesis="只在 Qlib 分数达到阈值时参与，降低低置信度信号进入组合的概率。",
                dsl=StrategyDSL(
                    strategy_type="threshold_signal",
                    universe=universe,
                    rank_by="qlib_score",
                    filters=[{"qlib_score_min": 0.6}, {"volatility_max": 0.08}],
                    rebalance="daily",
                    max_holdings=max_holdings,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    max_holding_days=8,
                ),
                risk_notes=["可能减少交易次数", "强行情中可能漏掉早期趋势"],
            ),
            StrategyCandidate(
                id="hotspot_volume_rotation",
                name="热点量能轮动",
                thesis="在热点或问财池内按量价动量排序，捕捉短周期主题扩散。",
                dsl=StrategyDSL(
                    strategy_type="ranked_rotation",
                    universe=universe if universe != "qlib_top" else "hotspot_pool",
                    rank_by="volume_adjusted_momentum",
                    filters=[{"turnover_min": 1.5}, {"drawdown_3d_between": [-0.08, 0.03]}],
                    rebalance="daily",
                    max_holdings=max(2, min(max_holdings, 6)),
                    stop_loss=stop_loss,
                    take_profit=0.15 if risk_mode != "conservative" else 0.10,
                    max_holding_days=5,
                ),
                risk_notes=["热点退潮时回撤可能更快", "需要限制持仓天数"],
            ),
            StrategyCandidate(
                id="defensive_mean_reversion",
                name="防守均值回复",
                thesis="在波动可控的股票上验证短期超跌修复，用作轮动策略的防守对照。",
                dsl=StrategyDSL(
                    strategy_type="mean_reversion",
                    universe=universe,
                    rank_by="momentum_20d",
                    filters=[{"volatility_max": 0.06}],
                    rebalance="weekly",
                    max_holdings=max_holdings,
                    stop_loss=min(stop_loss, 0.04),
                    take_profit=0.08,
                    max_holding_days=12,
                ),
                risk_notes=["趋势下跌中可能反复止损", "需要与趋势类候选分开评估"],
            ),
        ]
        valid = [candidate for candidate in templates if _is_valid(candidate.dsl)]
        return valid[: max(1, int(limit))]


def _safe_universe(value: object, default: str) -> str:
    candidate = str(value or default)
    return candidate if candidate in SUPPORTED_UNIVERSES else default


def _safe_max_holdings(value: object, default: int) -> int:
    if type(value) is int and 1 <= value <= 20:
        return value
    return default


def _is_valid(dsl: StrategyDSL) -> bool:
    try:
        validate_strategy_dsl(dsl)
    except ValueError:
        return False
    return True


