"""篮子交易计划生成。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd

from alpha.backtest import BacktestConfig, PortfolioBacktester
from engine.models import Direction, OrderType
from data.storage import DataStorage


@dataclass(frozen=True)
class BasketLeg:
    code: str
    name: str
    industry: str
    probability: float
    weight: float
    price: float
    shares: int
    target_value: float
    estimated_cost: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "industry": self.industry,
            "probability": round(self.probability, 4),
            "weight": round(self.weight, 4),
            "price": round(self.price, 2),
            "shares": self.shares,
            "target_value": round(self.target_value, 2),
            "estimated_cost": round(self.estimated_cost, 2),
        }


@dataclass(frozen=True)
class BasketPlan:
    success: bool
    allocation: str
    initial_cash: float
    total_target_value: float
    total_estimated_cost: float
    legs: list[BasketLeg] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "allocation": self.allocation,
            "initial_cash": round(self.initial_cash, 2),
            "total_target_value": round(self.total_target_value, 2),
            "total_estimated_cost": round(self.total_estimated_cost, 2),
            "legs": [leg.to_dict() for leg in self.legs],
            "warnings": list(self.warnings),
            "error": self.error,
        }


class BasketBuilder:
    """将候选股票转成一键建仓计划。"""

    def __init__(self, storage: DataStorage | None = None):
        self._storage = storage or DataStorage()

    def build_plan(
        self,
        candidates: list[dict],
        initial_cash: float = 1_000_000,
        allocation: str = "equal",
        rebalance_days: int = 5,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> BasketPlan:
        try:
            if not candidates:
                return BasketPlan(
                    success=False,
                    allocation=allocation,
                    initial_cash=initial_cash,
                    total_target_value=0,
                    total_estimated_cost=0,
                    legs=[],
                    error="候选集为空",
                )

            config = BacktestConfig(
                initial_cash=initial_cash,
                rebalance_days=rebalance_days,
                allocation=allocation,
            )
            backtester = PortfolioBacktester(config)
            weights = backtester._allocate(candidates, config.constraints)
            if not weights:
                return BasketPlan(
                    success=False,
                    allocation=allocation,
                    initial_cash=initial_cash,
                    total_target_value=0,
                    total_estimated_cost=0,
                    legs=[],
                    error="无法生成目标权重",
                )

            meta_map = self._load_stock_meta()
            legs: list[BasketLeg] = []
            total_target_value = 0.0
            total_cost = 0.0
            warnings: list[str] = []

            for item in candidates:
                code = str(item.get("code", "")).strip()
                if not code or code not in weights:
                    continue

                price = self._latest_price(code, start_date, end_date)
                if price <= 0:
                    warnings.append(f"{code} 无可用价格，已跳过")
                    continue

                weight = float(weights[code])
                target_value = initial_cash * weight
                shares = int(target_value / price / 100) * 100
                if shares <= 0:
                    warnings.append(f"{code} 目标金额过低，已跳过")
                    continue

                cost_model = config.cost
                cost_amount = shares * price
                fee = max(cost_amount * cost_model.commission, cost_model.min_commission)
                slip = cost_amount * cost_model.slippage
                estimated_cost = cost_amount + fee + slip
                total_target_value += cost_amount
                total_cost += fee + slip

                meta = meta_map.get(code, {})
                legs.append(
                    BasketLeg(
                        code=code,
                        name=str(item.get("name") or meta.get("name") or ""),
                        industry=str(item.get("industry") or meta.get("industry") or ""),
                        probability=float(item.get("probability", item.get("score", 0.5))),
                        weight=weight,
                        price=price,
                        shares=shares,
                        target_value=cost_amount,
                        estimated_cost=estimated_cost,
                    )
                )

            if not legs:
                return BasketPlan(
                    success=False,
                    allocation=allocation,
                    initial_cash=initial_cash,
                    total_target_value=0,
                    total_estimated_cost=0,
                    legs=[],
                    warnings=warnings,
                    error="没有可下单的股票",
                )

            total_target_value = sum(leg.target_value for leg in legs)
            total_cost = sum(leg.estimated_cost - leg.target_value for leg in legs)
            return BasketPlan(
                success=True,
                allocation=allocation,
                initial_cash=initial_cash,
                total_target_value=total_target_value,
                total_estimated_cost=total_cost,
                legs=legs,
                warnings=warnings,
            )
        except Exception as exc:  # noqa: BLE001
            return BasketPlan(
                success=False,
                allocation=allocation,
                initial_cash=initial_cash,
                total_target_value=0,
                total_estimated_cost=0,
                legs=[],
                error=str(exc),
            )

    def create_order_drafts(self, plan: BasketPlan, strategy_name: str = "basket") -> list[dict[str, Any]]:
        drafts: list[dict[str, Any]] = []
        if not plan.success:
            return drafts
        for leg in plan.legs:
            drafts.append({
                "code": leg.code,
                "direction": Direction.LONG.value,
                "order_type": OrderType.MARKET.value,
                "price": leg.price,
                "volume": leg.shares,
                "strategy_name": strategy_name,
                "signal_reason": f"篮子交易 {plan.allocation}",
            })
        return drafts

    def _latest_price(
        self,
        code: str,
        start_date: date | None,
        end_date: date | None,
    ) -> float:
        df = self._storage.get_stock_daily(code, start_date, end_date)
        if df.empty:
            return 0.0
        latest = df.iloc[-1]
        return float(latest.get("close", 0.0) or 0.0)

    def _load_stock_meta(self) -> dict[str, dict[str, str]]:
        stock_list = self._storage.get_stock_list()
        if stock_list.empty:
            return {}
        return {
            str(row["code"]): {
                "name": str(row.get("name", "") or ""),
                "industry": str(row.get("industry", "") or ""),
            }
            for _, row in stock_list.iterrows()
        }

    def backtest_plan(
        self,
        candidates: list[dict],
        initial_cash: float = 1_000_000,
        allocation: str = "equal",
        rebalance_days: int = 5,
        price_data: dict[str, pd.DataFrame] | None = None,
    ) -> dict[str, Any]:
        config = BacktestConfig(
            initial_cash=initial_cash,
            rebalance_days=rebalance_days,
            allocation=allocation,
        )
        backtester = PortfolioBacktester(config)
        if not price_data:
            return {"success": False, "error": "缺少价格数据"}

        predictions_by_date = {}
        if price_data:
            first_date = min(
                df["date"].iloc[0]
                for df in price_data.values()
                if not df.empty
            )
            predictions_by_date = {str(first_date): candidates}

        result = backtester.run(predictions_by_date, price_data)
        return {"success": True, **result.to_dict()}
