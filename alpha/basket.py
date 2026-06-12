"""篮子交易计划生成。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import math
import pandas as pd
from sqlalchemy import text

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

        available_price_data = {
            code: df
            for code, df in price_data.items()
            if df is not None and not df.empty and "date" in df.columns
        }
        if not available_price_data:
            return {"success": False, "error": "无可用价格数据"}

        predictions_by_date = {}
        first_date = min(df["date"].iloc[0] for df in available_price_data.values())
        predictions_by_date = {str(first_date): candidates}

        result = backtester.run(predictions_by_date, available_price_data)
        return {"success": True, **result.to_dict()}

    def audit_backtest_draft(
        self,
        candidates: list[dict],
        price_data: dict[str, pd.DataFrame] | None,
        backtest_draft: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Summarize whether a manual draft can be tested with the available data."""
        safe_actions = ["view", "edit", "run_backtest_after_confirmation"]
        if not backtest_draft or not isinstance(backtest_draft, dict):
            return {
                "available": False,
                "manual_only": True,
                "conditions_applied_to_backtest": False,
                "execution_status": "not_executed",
                "requires_confirmation": True,
                "allowed_actions": safe_actions,
                "sample_status": "missing_draft",
                "warnings": ["未提供回测草案条件"],
            }

        raw_conditions = backtest_draft.get("conditions")
        conditions = raw_conditions if isinstance(raw_conditions, dict) else {}
        event_date = str(conditions.get("event_date") or "").strip()
        holding_periods = self._normalize_holding_periods(conditions.get("holding_periods"))
        codes = [str(item.get("code", "")).strip() for item in candidates if str(item.get("code", "")).strip()]
        warnings: list[str] = []
        samples: list[dict[str, Any]] = []
        missing_samples: list[dict[str, str]] = []
        cost_model = self._normalize_audit_cost_model(conditions.get("cost_model"))
        benchmark_context, benchmark_df = self._resolve_audit_benchmark(conditions.get("benchmark"), price_data)
        unsupported_execution_keys = [
            key
            for key in (
                "entry_rule",
                "exit_rule",
                "risk_controls",
                "cost_model",
                "benchmark",
                "position_sizing",
                "stop_loss",
                "take_profit",
            )
            if key in conditions
        ]
        try:
            event_date_ts = pd.Timestamp(event_date) if event_date else None
        except (TypeError, ValueError):
            event_date_ts = None
            warnings.append(f"草案 event_date 无法解析: {event_date}")

        for code in codes:
            df = (price_data or {}).get(code)
            normalized_df = self._normalize_price_frame(df)
            if normalized_df.empty:
                missing_samples.append({"code": code, "reason": "missing_price_data"})
                continue

            event_index = self._locate_event_index(normalized_df, event_date_ts)
            if event_index is None:
                missing_samples.append({"code": code, "reason": "event_date_out_of_range"})
                continue

            entry_index = event_index + 1
            if entry_index >= len(normalized_df):
                samples.append({
                    "code": code,
                    "event_date": str(normalized_df.iloc[event_index]["date"].date()),
                    "sample_status": "no_next_bar",
                    "holding_returns": {},
                })
                continue

            entry_row = normalized_df.iloc[entry_index]
            entry_price = self._price_from_row(entry_row, "open") or self._price_from_row(entry_row, "close")
            holding_returns: dict[str, float | None] = {}
            holding_costs: dict[str, float | None] = {}
            holding_net_returns: dict[str, float | None] = {}
            holding_benchmark_returns: dict[str, float | None] = {}
            holding_excess_returns: dict[str, float | None] = {}
            holding_exit_dates: dict[str, str] = {}
            for period in holding_periods:
                exit_index = entry_index + period - 1
                if exit_index >= len(normalized_df) or not entry_price:
                    holding_returns[str(period)] = None
                    holding_costs[str(period)] = None
                    holding_net_returns[str(period)] = None
                    holding_benchmark_returns[str(period)] = None
                    holding_excess_returns[str(period)] = None
                    continue
                exit_row = normalized_df.iloc[exit_index]
                exit_price = self._price_from_row(exit_row, "close")
                key = str(period)
                holding_exit_dates[key] = str(exit_row["date"].date())
                gross_return = round((exit_price / entry_price - 1) * 100, 4) if entry_price and exit_price else None
                holding_returns[key] = gross_return
                if gross_return is None:
                    holding_costs[key] = None
                    holding_net_returns[key] = None
                    holding_benchmark_returns[key] = None
                    holding_excess_returns[key] = None
                    continue

                cost_pct = round(float(cost_model["estimated_round_trip_cost_pct"]), 4)
                net_return = round(gross_return - cost_pct, 4)
                benchmark_return = self._benchmark_return_for_window(
                    benchmark_df,
                    entry_row["date"],
                    exit_row["date"],
                )
                holding_costs[key] = cost_pct
                holding_net_returns[key] = net_return
                holding_benchmark_returns[key] = benchmark_return
                holding_excess_returns[key] = (
                    round(net_return - benchmark_return, 4)
                    if benchmark_return is not None
                    else None
                )

            samples.append({
                "code": code,
                "event_date": str(normalized_df.iloc[event_index]["date"].date()),
                "entry_date": str(entry_row["date"].date()),
                "entry_price": round(entry_price, 4) if entry_price else None,
                "sample_status": "ready",
                "holding_returns": holding_returns,
                "holding_costs": holding_costs,
                "holding_net_returns": holding_net_returns,
                "holding_benchmark_returns": holding_benchmark_returns,
                "holding_excess_returns": holding_excess_returns,
                "holding_exit_dates": holding_exit_dates,
            })

        if not event_date:
            warnings.append("草案缺少 event_date，无法按事件日定位样本")
        if raw_conditions is not None and not isinstance(raw_conditions, dict):
            warnings.append("草案 conditions 必须是 JSON 对象，当前仅保留安全审计状态")
        if missing_samples:
            warnings.append(f"{len(missing_samples)} 只候选缺少事件日或价格数据")
        ready_count = sum(1 for item in samples if item.get("sample_status") == "ready")
        if not samples:
            sample_status = "no_sample"
        elif ready_count == len(codes) and ready_count == len(samples):
            sample_status = "ready"
        else:
            sample_status = "partial"

        event_statistics = self._summarize_event_study(
            samples,
            holding_periods,
            len(codes),
            missing_samples,
            sample_status,
            cost_model,
            benchmark_context,
        )

        return {
            "available": bool(samples),
            "manual_only": True,
            "conditions_applied_to_backtest": False,
            "execution_status": "not_executed",
            "requires_confirmation": True,
            "allowed_actions": safe_actions,
            "sample_status": sample_status,
            "draft_type": str(backtest_draft.get("draft_type") or "event_group_backtest_draft"),
            "event_date": event_date,
            "entry_rule": str(conditions.get("entry_rule") or ""),
            "exit_rule": str(conditions.get("exit_rule") or ""),
            "holding_periods": holding_periods,
            "condition_keys": sorted(str(key) for key in conditions.keys()),
            "unsupported_execution_keys": unsupported_execution_keys,
            "candidate_count": len(codes),
            "sample_count": len(samples),
            "coverage_ratio": round(len(samples) / len(codes), 4) if codes else 0,
            "event_statistics": event_statistics,
            "event_study": event_statistics,
            "samples": samples[:50],
            "missing_samples": missing_samples[:50],
            "warnings": warnings,
            "note": "草案审计仅用于验证样本覆盖和持有期收益；草案条件不会改变本次篮子回测规则，也不会自动交易或模拟盘下单。",
        }

    def _summarize_event_study(
        self,
        samples: list[dict[str, Any]],
        holding_periods: list[int],
        candidate_count: int,
        missing_samples: list[dict[str, str]],
        sample_status: str,
        cost_model: dict[str, Any],
        benchmark: dict[str, Any],
    ) -> dict[str, Any]:
        ready_samples = [item for item in samples if item.get("sample_status") == "ready"]
        period_stats: dict[str, dict[str, Any]] = {}
        for period in holding_periods:
            key = str(period)
            values = [
                float(item.get("holding_returns", {}).get(key))
                for item in ready_samples
                if isinstance(item.get("holding_returns", {}).get(key), (int, float))
                and math.isfinite(float(item.get("holding_returns", {}).get(key)))
            ]
            net_values = self._numeric_sample_values(ready_samples, "holding_net_returns", key)
            cost_values = self._numeric_sample_values(ready_samples, "holding_costs", key)
            benchmark_values = self._numeric_sample_values(ready_samples, "holding_benchmark_returns", key)
            excess_values = self._numeric_sample_values(ready_samples, "holding_excess_returns", key)
            if not values:
                period_stats[key] = {
                    "period": period,
                    "sample_count": 0,
                    "mean_return_pct": None,
                    "median_return_pct": None,
                    "mean_cost_pct": None,
                    "mean_net_return_pct": None,
                    "median_net_return_pct": None,
                    "net_win_rate": None,
                    "mean_benchmark_return_pct": None,
                    "mean_excess_return_pct": None,
                    "median_excess_return_pct": None,
                    "excess_win_rate": None,
                    "win_rate": None,
                    "best_return_pct": None,
                    "worst_return_pct": None,
                    "sample_std_pct": None,
                    "net_sample_std_pct": None,
                    "excess_sample_std_pct": None,
                    "t_stat_return": None,
                    "t_stat_net_return": None,
                    "t_stat_excess_return": None,
                    "significance_status": "insufficient_sample",
                    "significance_note": "无可统计样本",
                    "positive_count": 0,
                    "negative_count": 0,
                    "net_positive_count": 0,
                    "net_negative_count": 0,
                    "excess_positive_count": 0,
                    "excess_negative_count": 0,
                }
                continue
            sorted_values = sorted(values)
            midpoint = len(sorted_values) // 2
            if len(sorted_values) % 2:
                median = sorted_values[midpoint]
            else:
                median = (sorted_values[midpoint - 1] + sorted_values[midpoint]) / 2
            positive_count = sum(1 for value in values if value > 0)
            negative_count = sum(1 for value in values if value < 0)
            net_positive_count = sum(1 for value in net_values if value > 0)
            net_negative_count = sum(1 for value in net_values if value < 0)
            excess_positive_count = sum(1 for value in excess_values if value > 0)
            excess_negative_count = sum(1 for value in excess_values if value < 0)
            return_sig = self._significance_summary(values)
            net_sig = self._significance_summary(net_values)
            excess_sig = self._significance_summary(excess_values)
            period_stats[key] = {
                "period": period,
                "sample_count": len(values),
                "mean_return_pct": round(sum(values) / len(values), 4),
                "median_return_pct": round(median, 4),
                "mean_cost_pct": self._mean_or_none(cost_values),
                "mean_net_return_pct": self._mean_or_none(net_values),
                "median_net_return_pct": self._median_or_none(net_values),
                "net_win_rate": round(net_positive_count / len(net_values), 4) if net_values else None,
                "mean_benchmark_return_pct": self._mean_or_none(benchmark_values),
                "mean_excess_return_pct": self._mean_or_none(excess_values),
                "median_excess_return_pct": self._median_or_none(excess_values),
                "excess_win_rate": round(excess_positive_count / len(excess_values), 4) if excess_values else None,
                "win_rate": round(positive_count / len(values), 4),
                "best_return_pct": round(max(values), 4),
                "worst_return_pct": round(min(values), 4),
                "sample_std_pct": return_sig["sample_std_pct"],
                "net_sample_std_pct": net_sig["sample_std_pct"],
                "excess_sample_std_pct": excess_sig["sample_std_pct"],
                "t_stat_return": return_sig["t_stat"],
                "t_stat_net_return": net_sig["t_stat"],
                "t_stat_excess_return": excess_sig["t_stat"],
                "significance_status": excess_sig["status"] if benchmark.get("available") else net_sig["status"],
                "significance_note": (
                    excess_sig["note"]
                    if benchmark.get("available")
                    else f"{net_sig['note']}；未计算基准超额显著性"
                ),
                "positive_count": positive_count,
                "negative_count": negative_count,
                "net_positive_count": net_positive_count,
                "net_negative_count": net_negative_count,
                "excess_positive_count": excess_positive_count,
                "excess_negative_count": excess_negative_count,
            }

        best_period = None
        ranked_stats = [
            stat
            for stat in period_stats.values()
            if stat.get("sample_count") and isinstance(stat.get("mean_return_pct"), (int, float))
        ]
        if ranked_stats:
            best = max(ranked_stats, key=lambda item: (float(item["mean_return_pct"]), int(item["sample_count"])))
            best_period = {
                "period": best["period"],
                "mean_return_pct": best["mean_return_pct"],
                "sample_count": best["sample_count"],
            }

        entry_dates = [str(item.get("entry_date")) for item in ready_samples if item.get("entry_date")]
        return {
            "available": bool(ready_samples),
            "status": sample_status if ready_samples else "no_sample",
            "method": "next_bar_open_to_holding_close",
            "unit": "percent",
            "calculation_status": "computed" if ready_samples else "insufficient_sample",
            "cost_model": cost_model,
            "benchmark": benchmark,
            "holding_periods": holding_periods,
            "candidate_count": candidate_count,
            "sample_count": len(samples),
            "ready_sample_count": len(ready_samples),
            "missing_sample_count": len(missing_samples),
            "coverage_ratio": round(len(ready_samples) / candidate_count, 4) if candidate_count else 0,
            "by_holding_period": period_stats,
            "period_stats": period_stats,
            "best_period": best_period,
            "sample_window": {
                "first_entry_date": min(entry_dates) if entry_dates else "",
                "last_entry_date": max(entry_dates) if entry_dates else "",
            },
            "methodology": "按草案 event_date 定位样本，使用事件日后下一交易日开盘价入场；毛收益按持有期收盘价计算，净收益扣除估算双边成本，基准可用时计算净超额收益。",
            "limitations": [
                "未执行草案 entry_rule/exit_rule 风控逻辑",
                "成本为审计估算，不代表真实成交、最低佣金逐笔影响或冲击成本",
                "基准只在本地可用价格数据覆盖事件窗口时计算；不可用时不伪造超额收益",
                "t-stat 仅为样本均值相对 0 的描述性统计，不构成策略显著有效证明",
                "样本只覆盖当前候选和本地可用价格数据",
            ],
        }

    def _normalize_audit_cost_model(self, raw: Any) -> dict[str, Any]:
        default_cost = BacktestConfig().cost
        source = "default"
        values = {
            "commission": default_cost.commission,
            "slippage": default_cost.slippage,
            "stamp_tax": default_cost.stamp_tax,
        }
        if isinstance(raw, dict):
            source = "draft_conditions"
            for key in values:
                values[key] = self._normalize_rate(raw.get(key), values[key])
        elif raw not in (None, ""):
            source = "invalid_draft_conditions"

        round_trip_rate = values["commission"] * 2 + values["slippage"] * 2 + values["stamp_tax"]
        return {
            "available": True,
            "calculation_status": "computed",
            "source": source,
            "commission": round(values["commission"], 6),
            "slippage": round(values["slippage"], 6),
            "stamp_tax": round(values["stamp_tax"], 6),
            "estimated_round_trip_cost_pct": round(round_trip_rate * 100, 4),
            "methodology": "按买入佣金+买入滑点+卖出佣金+卖出滑点+卖出印花税估算双边成本；未按单笔金额套用最低佣金。",
        }

    def _normalize_rate(self, value: Any, fallback: float) -> float:
        try:
            rate = float(value)
        except (TypeError, ValueError):
            return fallback
        if not math.isfinite(rate) or rate < 0 or rate > 0.05:
            return fallback
        return rate

    def _resolve_audit_benchmark(
        self,
        raw: Any,
        price_data: dict[str, pd.DataFrame] | None,
    ) -> tuple[dict[str, Any], pd.DataFrame]:
        code, name = self._normalize_benchmark_identity(raw)
        if not code:
            return {
                "available": False,
                "calculation_status": "not_computed",
                "code": "",
                "name": "",
                "source": "not_requested",
                "data_source": "",
                "reason": "benchmark_not_requested",
            }, pd.DataFrame()

        benchmark_df = self._benchmark_frame_from_price_data(code, price_data)
        data_source = "price_data"
        if benchmark_df.empty:
            try:
                benchmark_df = self._normalize_price_frame(self._storage.get_stock_daily(code, None, None))
                data_source = "storage"
            except Exception:
                benchmark_df = pd.DataFrame()
        if benchmark_df.empty:
            benchmark_df = self._benchmark_frame_from_storage_variants(code)
            data_source = "storage_sql"
        if benchmark_df.empty:
            return {
                "available": False,
                "calculation_status": "not_computed",
                "code": code,
                "name": name,
                "source": "draft_conditions",
                "data_source": "",
                "reason": "missing_benchmark_price_data",
            }, pd.DataFrame()

        return {
            "available": True,
            "calculation_status": "computed",
            "code": code,
            "name": name,
            "source": "draft_conditions",
            "data_source": data_source,
            "reason": "",
        }, benchmark_df

    def _normalize_benchmark_identity(self, raw: Any) -> tuple[str, str]:
        if isinstance(raw, dict):
            raw_code = str(raw.get("code") or raw.get("symbol") or "").strip()
            raw_name = str(raw.get("name") or raw.get("label") or raw_code).strip()
        else:
            raw_code = str(raw or "").strip()
            raw_name = raw_code
        if not raw_code:
            return "", ""
        aliases = {
            "沪深300": ("000300", "沪深300"),
            "hs300": ("000300", "沪深300"),
            "csi300": ("000300", "沪深300"),
            "中证500": ("000905", "中证500"),
            "上证指数": ("000001", "上证指数"),
            "创业板指": ("399006", "创业板指"),
        }
        alias = aliases.get(raw_code.lower()) or aliases.get(raw_code)
        if alias:
            return alias
        lowered = raw_code.lower()
        if lowered.startswith(("sh", "sz", "bj")):
            lowered = lowered[2:]
        digits = "".join(ch for ch in lowered if ch.isdigit())
        if len(digits) >= 6:
            return digits[:6], raw_name or digits[:6]
        return "", raw_name or raw_code

    def _benchmark_frame_from_price_data(
        self,
        code: str,
        price_data: dict[str, pd.DataFrame] | None,
    ) -> pd.DataFrame:
        if not price_data:
            return pd.DataFrame()
        keys = [code, f"sh{code}", f"sz{code}", f"bj{code}", code[-6:]]
        for key in keys:
            df = price_data.get(key)
            normalized = self._normalize_price_frame(df)
            if not normalized.empty:
                return normalized
        return pd.DataFrame()

    def _benchmark_frame_from_storage_variants(self, code: str) -> pd.DataFrame:
        engine = getattr(self._storage, "_engine", None)
        if engine is None:
            return pd.DataFrame()
        variants = []
        for item in (code, code[-6:], f"sh{code[-6:]}", f"sz{code[-6:]}", f"bj{code[-6:]}"):
            if item and item not in variants:
                variants.append(item)
        params = {f"code_{idx}": value for idx, value in enumerate(variants)}
        placeholders = ", ".join(f":code_{idx}" for idx in range(len(variants)))
        try:
            with engine.connect() as conn:
                rows = conn.execute(
                    text(
                        "SELECT code, date, open, high, low, close, volume, amount "
                        f"FROM stock_daily WHERE code IN ({placeholders}) "
                        "ORDER BY date"
                    ),
                    params,
                ).mappings().all()
        except Exception:
            return pd.DataFrame()
        if not rows:
            return pd.DataFrame()

        rows_by_date: dict[Any, dict[str, Any]] = {}
        preferred = [f"sh{code[-6:]}", code[-6:], f"sz{code[-6:]}", f"bj{code[-6:]}"]
        priority = {value: idx for idx, value in enumerate(preferred)}
        for row in rows:
            row_dict = dict(row)
            row_date = row_dict.get("date")
            existing = rows_by_date.get(row_date)
            if existing is None or priority.get(str(row_dict.get("code")), 99) < priority.get(str(existing.get("code")), 99):
                rows_by_date[row_date] = row_dict
        return self._normalize_price_frame(pd.DataFrame(rows_by_date.values()))

    def _benchmark_return_for_window(
        self,
        benchmark_df: pd.DataFrame,
        entry_date: Any,
        exit_date: Any,
    ) -> float | None:
        if benchmark_df.empty:
            return None
        try:
            entry_ts = pd.Timestamp(entry_date).normalize()
            exit_ts = pd.Timestamp(exit_date).normalize()
        except (TypeError, ValueError):
            return None
        entry_matches = benchmark_df.index[benchmark_df["date"].dt.normalize() >= entry_ts]
        exit_matches = benchmark_df.index[benchmark_df["date"].dt.normalize() >= exit_ts]
        if len(entry_matches) == 0 or len(exit_matches) == 0:
            return None
        entry_price = self._price_from_row(benchmark_df.iloc[int(entry_matches[0])], "close")
        exit_price = self._price_from_row(benchmark_df.iloc[int(exit_matches[0])], "close")
        if not entry_price or not exit_price:
            return None
        return round((exit_price / entry_price - 1) * 100, 4)

    def _numeric_sample_values(self, samples: list[dict[str, Any]], field: str, key: str) -> list[float]:
        values: list[float] = []
        for item in samples:
            value = item.get(field, {}).get(key)
            if isinstance(value, (int, float)) and math.isfinite(float(value)):
                values.append(float(value))
        return values

    def _mean_or_none(self, values: list[float]) -> float | None:
        return round(sum(values) / len(values), 4) if values else None

    def _median_or_none(self, values: list[float]) -> float | None:
        if not values:
            return None
        sorted_values = sorted(values)
        midpoint = len(sorted_values) // 2
        if len(sorted_values) % 2:
            return round(sorted_values[midpoint], 4)
        return round((sorted_values[midpoint - 1] + sorted_values[midpoint]) / 2, 4)

    def _significance_summary(self, values: list[float]) -> dict[str, Any]:
        if len(values) < 2:
            return {
                "sample_std_pct": None,
                "t_stat": None,
                "status": "insufficient_sample",
                "note": "样本数少于 2，仅展示描述性收益",
            }
        mean_value = sum(values) / len(values)
        variance = sum((value - mean_value) ** 2 for value in values) / (len(values) - 1)
        sample_std = math.sqrt(variance)
        if sample_std <= 0:
            return {
                "sample_std_pct": 0,
                "t_stat": None,
                "status": "zero_variance",
                "note": "样本波动为 0，无法计算有效 t-stat",
            }
        t_stat = mean_value / (sample_std / math.sqrt(len(values)))
        return {
            "sample_std_pct": round(sample_std, 4),
            "t_stat": round(t_stat, 4),
            "status": "computed_descriptive",
            "note": "描述性单样本 t-stat，未做多重检验或样本外验证",
        }

    def _normalize_price_frame(self, df: pd.DataFrame | None) -> pd.DataFrame:
        if df is None or df.empty or "date" not in df.columns:
            return pd.DataFrame()
        normalized = df.copy()
        normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
        normalized = normalized.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        return normalized

    def _locate_event_index(self, df: pd.DataFrame, event_date_ts: pd.Timestamp | None) -> int | None:
        if df.empty or event_date_ts is None or pd.isna(event_date_ts):
            return None
        matches = df.index[df["date"].dt.normalize() >= event_date_ts.normalize()]
        if len(matches) == 0:
            return None
        return int(matches[0])

    def _normalize_holding_periods(self, raw: Any) -> list[int]:
        values = raw if isinstance(raw, list) else [raw]
        periods: list[int] = []
        for item in values:
            try:
                period = int(item)
            except (TypeError, ValueError):
                continue
            if 1 <= period <= 120 and period not in periods:
                periods.append(period)
        return periods or [1, 3, 5]

    def _price_from_row(self, row: pd.Series, column: str) -> float:
        value = row.get(column, 0)
        try:
            price = float(value)
        except (TypeError, ValueError):
            return 0.0
        return price if math.isfinite(price) and price > 0 else 0.0
