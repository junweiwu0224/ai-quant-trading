"""组合回测引擎

基于 AI 选股结果模拟组合交易，计算含交易成本的绩效指标。

支持：
- 等权 / 风险平价 / 因子加权 仓位分配
- 佣金万3 + 印花税千1（卖出）+ 滑点0.1%
- 最大持仓20只、单只2%~10%、行业≤30%
- 净值曲线、年化收益、最大回撤、夏普、卡玛、胜率
"""
from __future__ import annotations

from datetime import date
from dataclasses import dataclass
from typing import Any, Mapping, Optional

import numpy as np
import pandas as pd
from loguru import logger

from engine.execution_model import (
    DEFAULT_A_SHARE_EXECUTION_CONTRACT,
    ExecutionCostModelVersion,
    ExecutionDataContract,
    resolve_execution_contract,
    resolve_execution_cost_model,
)
from data.markets import get_market_adapter
from engine.market_rules import MarketRule, get_market_rule


# ── 交易成本模型 ──

@dataclass(frozen=True)
class CostModel:
    """A 股交易成本"""
    commission: float = 0.0003     # 佣金费率（万3）
    stamp_tax: float = 0.001       # 印花税（千1，仅卖出）
    slippage: float = 0.001        # 滑点（0.1%）
    min_commission: float = 5.0    # 最低佣金 5 元
    version: str = "alpha-legacy-v1"

    def to_execution_model(self) -> ExecutionCostModelVersion:
        return ExecutionCostModelVersion(
            version=self.version,
            commission_rate=self.commission,
            stamp_tax_rate=self.stamp_tax,
            buy_slippage=self.slippage,
            sell_slippage=self.slippage,
            min_commission=self.min_commission,
        )


@dataclass(frozen=True)
class PortfolioConstraints:
    """组合约束"""
    max_positions: int = 20
    min_weight: float = 0.02       # 单只最低 2%
    max_weight: float = 0.10       # 单只最高 10%
    max_industry_pct: float = 0.30 # 单行业 ≤30%
    max_annual_vol: float = 0.15   # 年化波动率 ≤15%


@dataclass(frozen=True)
class BacktestConfig:
    """回测配置"""
    initial_cash: float = 1_000_000
    rebalance_days: int = 5       # 调仓周期（交易日）
    allocation: str = "equal"     # equal / risk_parity / factor_weighted
    cost: CostModel = CostModel()
    constraints: PortfolioConstraints = PortfolioConstraints()
    benchmark: str = "000300"     # 基准指数代码
    execution_contract: ExecutionDataContract | Mapping[str, Any] | None = None
    execution_cost_model: ExecutionCostModelVersion | Mapping[str, Any] | None = None
    market: str = "CN"
    market_rule: MarketRule | None = None
    trading_calendar: Any = None


@dataclass
class BacktestResult:
    """回测结果"""
    equity_curve: list[dict]
    trades: list[dict]
    daily_returns: list[float]
    metrics: dict
    holdings_history: list[dict]
    execution_contract: dict | None = None
    coverage: dict | None = None

    def to_dict(self) -> dict:
        return {
            "equity_curve": self.equity_curve,
            "trades": self.trades[-100:],
            "metrics": self.metrics,
            "holdings_history": self.holdings_history,
            # Keep the same frozen economic contract visible to API callers as
            # the engine backtest result.  Without this field the UI could
            # compare numbers produced under different cost assumptions while
            # presenting them as one validation result.
            "execution_contract": self.execution_contract,
            "coverage": self.coverage or {},
        }


# ── 仓位分配算法 ──

def allocate_equal(selected: list[dict], constraints: PortfolioConstraints) -> dict[str, float]:
    """等权分配"""
    n = min(len(selected), constraints.max_positions)
    if n == 0:
        return {}
    weight = 1.0 / n
    weight = max(constraints.min_weight, min(constraints.max_weight, weight))
    return {s["code"]: weight for s in selected[:n]}


def allocate_risk_parity(
    selected: list[dict],
    vol_data: dict[str, float],
    constraints: PortfolioConstraints,
) -> dict[str, float]:
    """风险平价分配（波动率倒数加权）"""
    n = min(len(selected), constraints.max_positions)
    if n == 0:
        return {}

    inv_vols = {}
    for s in selected[:n]:
        vol = vol_data.get(s["code"], 0.02)
        if vol > 0:
            inv_vols[s["code"]] = 1.0 / vol

    total = sum(inv_vols.values())
    if total == 0:
        return allocate_equal(selected, constraints)

    weights = {code: iv / total for code, iv in inv_vols.items()}
    return {
        code: max(constraints.min_weight, min(constraints.max_weight, w))
        for code, w in weights.items()
    }


def allocate_factor_weighted(
    selected: list[dict],
    constraints: PortfolioConstraints,
) -> dict[str, float]:
    """因子加权（概率归一化）"""
    n = min(len(selected), constraints.max_positions)
    if n == 0:
        return {}

    probs = {s["code"]: s.get("probability", 0.5) for s in selected[:n]}
    total = sum(probs.values())
    if total == 0:
        return allocate_equal(selected, constraints)

    weights = {code: p / total for code, p in probs.items()}
    return {
        code: max(constraints.min_weight, min(constraints.max_weight, w))
        for code, w in weights.items()
    }


# ── 回测引擎 ──

class PortfolioBacktester:
    """组合回测引擎"""

    def __init__(self, config: Optional[BacktestConfig] = None):
        self._config = config or BacktestConfig()
        self._market_rule = self._config.market_rule or get_market_rule(self._config.market)
        self._trading_calendar = self._config.trading_calendar or self._market_rule.calendar
        configured_cost = self._config.execution_cost_model
        if configured_cost is None and isinstance(self._config.execution_contract, Mapping):
            contract_cost = self._config.execution_contract.get("cost_model")
            if isinstance(contract_cost, Mapping):
                configured_cost = contract_cost
        self._execution_cost = resolve_execution_cost_model(
            configured_cost if configured_cost is not None else self._config.cost.to_execution_model()
        )
        adapter = get_market_adapter(self._config.market)
        self._execution_contract = resolve_execution_contract(
            self._config.execution_contract or adapter.execution_contract(cost_model=self._execution_cost),
            cost_model=self._execution_cost,
        )

    def run(
        self,
        predictions_by_date: dict[str, list[dict]],
        price_data: dict[str, pd.DataFrame],
    ) -> BacktestResult:
        """执行回测

        Args:
            predictions_by_date: {date_str: [{"code", "probability", ...}, ...]}
            price_data: {code: DataFrame(date, open, high, low, close, volume)}
        """
        config = self._config
        constraints = config.constraints
        if config.rebalance_days <= 0:
            raise ValueError("rebalance_days must be positive")

        cash = config.initial_cash
        positions: dict[str, dict] = {}  # {code: {shares, avg_price}}
        equity_curve = []
        trades = []
        holdings_history = []
        daily_returns = []
        pending_rebalance: tuple[dict[str, float], float] | None = None
        deferred: list[dict[str, str]] = []
        last_close: dict[str, float] = {}

        all_dates = sorted(set(
            dt for df in price_data.values()
            for dt in (df["date"].astype(str).tolist() if "date" in df.columns else [])
            if self._is_trading_day(dt)
        ))

        prev_equity = cash

        for i, dt in enumerate(all_dates):
            # A signal observed at the previous close becomes executable at
            # this bar's open.  Keeping the order pending for one iteration
            # prevents the historical close from becoming an impossible fill.
            if pending_rebalance is not None:
                target_weights, signal_equity = pending_rebalance
                rows = self._rows_for_date(price_data, dt)
                execution_prices, block_reasons = self._execution_context(rows, last_close)
                trades_today, unresolved, cash_after = self._rebalance_with_status(
                    positions,
                    target_weights,
                    execution_prices,
                    cash,
                    signal_equity,
                    trade_date=dt,
                    block_reasons=block_reasons,
                )
                trades.extend(trades_today)
                cash = cash_after
                if unresolved:
                    pending_rebalance = (target_weights, signal_equity)
                    deferred.extend(
                        {
                            "date": dt,
                            "code": code,
                            "reason": block_reasons.get(code, {}).get("buy") or "missing_quote",
                        }
                        for code in sorted(unresolved)
                    )
                else:
                    pending_rebalance = None

            # 获取当日收盘价
            prices = self._prices_for_date(price_data, dt, "close")
            for code, price in prices.items():
                last_close[code] = price

            # 计算当日权益
            equity = cash
            for code, pos in positions.items():
                price = prices.get(code, last_close.get(code, pos["avg_price"]))
                equity += pos["shares"] * price

            equity_curve.append({"date": dt, "equity": round(equity, 2)})
            if prev_equity > 0:
                daily_returns.append((equity - prev_equity) / prev_equity)
            prev_equity = equity

            # 调仓日
            if i % config.rebalance_days == 0:
                preds = predictions_by_date.get(dt, [])
                if not preds:
                    # 尝试最近的预测
                    for lookback in range(1, 8):
                        lookback_dt = all_dates[max(0, i - lookback)]
                        preds = predictions_by_date.get(lookback_dt, [])
                        if preds:
                            break

                if preds:
                    new_weights = self._allocate(preds, constraints)
                    if i + 1 < len(all_dates):
                        pending_rebalance = (new_weights, equity)

            # 记录持仓
            holdings = []
            for code, pos in positions.items():
                price = prices.get(code, last_close.get(code, pos["avg_price"]))
                holdings.append({
                    "code": code,
                    "shares": pos["shares"],
                    "avg_price": round(pos["avg_price"], 2),
                    "market_value": round(pos["shares"] * price, 2),
                })
            holdings_history.append({"date": dt, "holdings": holdings, "cash": round(cash, 2)})

        metrics = self._compute_metrics(
            equity_curve,
            daily_returns,
            trades,
            annualization_days=self._execution_contract.annualization_days,
        )

        return BacktestResult(
            equity_curve=equity_curve,
            trades=trades,
            daily_returns=daily_returns,
            metrics=metrics,
            holdings_history=holdings_history,
            execution_contract=self._execution_contract.as_dict(),
            coverage=self._coverage(price_data, all_dates, deferred),
        )

    def _is_trading_day(self, value: str) -> bool:
        try:
            return bool(self._trading_calendar.is_trading_day(date.fromisoformat(str(value)[:10])))
        except (AttributeError, TypeError, ValueError):
            return False

    @staticmethod
    def _positive_number(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return number if np.isfinite(number) and number > 0 else None

    @classmethod
    def _rows_for_date(cls, price_data: dict[str, pd.DataFrame], dt: str) -> dict[str, dict[str, Any]]:
        rows: dict[str, dict[str, Any]] = {}
        for code, frame in price_data.items():
            if "date" not in frame.columns:
                continue
            matches = frame[frame["date"].astype(str).str[:10] == str(dt)[:10]]
            if not matches.empty:
                rows[code] = matches.iloc[0].to_dict()
        return rows

    @staticmethod
    def _prices_for_date(
        price_data: dict[str, pd.DataFrame],
        dt: str,
        field: str,
    ) -> dict[str, float]:
        prices: dict[str, float] = {}
        for code, df in price_data.items():
            if "date" not in df.columns:
                continue
            day = df[df["date"].astype(str).str[:10] == str(dt)[:10]]
            if not day.empty:
                value = day.iloc[0].get(field)
                try:
                    number = float(value)
                except (TypeError, ValueError, OverflowError):
                    continue
                if np.isfinite(number) and number > 0:
                    prices[code] = number
        return prices

    def _execution_context(
        self,
        rows: dict[str, dict[str, Any]],
        last_close: dict[str, float],
    ) -> tuple[dict[str, float], dict[str, dict[str, str | None]]]:
        prices: dict[str, float] = {}
        block_reasons: dict[str, dict[str, str | None]] = {}
        for code, row in rows.items():
            opening = self._positive_number(row.get("open"))
            closing = self._positive_number(row.get("close"))
            # Price-limit enforcement is only sound when the frozen bar
            # carries its own pre-close or explicit limits.  Falling back to
            # the last observed close can fabricate a limit lock across a
            # provider gap and incorrectly defer a fill.
            pre_close = row.get("pre_close")
            prices[code] = opening or 0.0
            common = {
                "open_price": opening,
                "close_price": closing,
                "volume": row.get("volume"),
                "pre_close": pre_close,
                "bar_status": row.get("status"),
                "suspended": row.get("suspended", False),
                "limit_up": row.get("limit_up"),
                "limit_down": row.get("limit_down"),
            }
            block_reasons[code] = {
                "buy": self._market_rule.execution_block_reason(code, "buy", **common),
                "sell": self._market_rule.execution_block_reason(code, "sell", **common),
            }
        return prices, block_reasons

    def _coverage(
        self,
        price_data: dict[str, pd.DataFrame],
        observed_dates: list[str],
        deferred: list[dict[str, str]],
    ) -> dict[str, Any]:
        if observed_dates:
            expected = len(self._trading_calendar.trading_days(
                date.fromisoformat(str(observed_dates[0])[:10]),
                date.fromisoformat(str(observed_dates[-1])[:10]),
            ))
        else:
            expected = 0
        per_symbol: dict[str, dict[str, Any]] = {}
        for code, frame in price_data.items():
            dates = {
                str(value)[:10]
                for value in frame.get("date", pd.Series(dtype=str)).tolist()
                if self._is_trading_day(str(value))
            }
            observed = len(dates & set(observed_dates))
            per_symbol[code] = {
                "observed_trading_days": observed,
                "expected_trading_days": expected,
                "coverage_pct": round(observed / expected * 100, 2) if expected else 0.0,
            }
        return {
            "calendar": self._execution_contract.calendar_name,
            "calendar_source": self._execution_contract.calendar_source,
            "expected_trading_days": expected,
            "observed_trading_days": len(observed_dates),
            "per_symbol": per_symbol,
            "deferred": deferred,
        }

    def _allocate(self, predictions: list[dict], constraints: PortfolioConstraints) -> dict[str, float]:
        """根据配置选择分配方式"""
        if self._config.allocation == "risk_parity":
            vol_data = {}
            for p in predictions[:constraints.max_positions]:
                vol_data[p["code"]] = p.get("risk_score", 0.5) * 0.03
            return allocate_risk_parity(predictions, vol_data, constraints)
        elif self._config.allocation == "factor_weighted":
            return allocate_factor_weighted(predictions, constraints)
        else:
            return allocate_equal(predictions, constraints)

    def _rebalance(
        self,
        positions: dict[str, dict],
        target_weights: dict[str, float],
        prices: dict[str, float],
        cash: float,
        equity: float,
        cost: CostModel | None = None,
        *,
        trade_date: str = "",
    ) -> list[dict]:
        """Execute a rebalance using the legacy list-returning interface."""
        trades, _unresolved, _cash_after = self._rebalance_with_status(
            positions,
            target_weights,
            prices,
            cash,
            equity,
            trade_date=trade_date,
        )
        return trades

    def _rebalance_with_status(
        self,
        positions: dict[str, dict],
        target_weights: dict[str, float],
        prices: dict[str, float],
        cash: float,
        equity: float,
        *,
        trade_date: str = "",
        block_reasons: dict[str, dict[str, str | None]] | None = None,
    ) -> tuple[list[dict], set[str], float]:
        """Rebalance and retain symbols that cannot trade on this bar."""
        trades: list[dict] = []
        unresolved: set[str] = set()
        block_reasons = block_reasons or {}

        def blocked(code: str, side: str) -> bool:
            return bool(block_reasons.get(code, {}).get(side))

        # 卖出不在目标中的持仓
        codes_to_sell = [c for c in positions if c not in target_weights]
        for code in codes_to_sell:
            price = prices.get(code)
            if not price or price <= 0:
                unresolved.add(code)
                continue
            if blocked(code, "sell"):
                unresolved.add(code)
                continue
            pos = positions[code]
            fill = self._execution_cost.sell_fill(price, pos["shares"])
            net = fill.cash_delta
            cash += net

            trades.append({
                "date": trade_date,
                "type": "sell",
                "code": code,
                "shares": pos["shares"],
                "price": round(fill.fill_price, 2),
                "revenue": round(net, 2),
                "cost": round(fill.commission + fill.stamp_tax + fill.transfer_fee, 2),
            })
            del positions[code]

        # 调整现有持仓和新建仓位
        for code, target_w in target_weights.items():
            target_value = equity * target_w
            price = prices.get(code)
            if not price or price <= 0:
                unresolved.add(code)
                continue

            current_shares = positions.get(code, {}).get("shares", 0)
            current_value = current_shares * price
            diff = target_value - current_value

            if abs(diff) < equity * 0.01:
                continue

            if diff > 0 and cash > 0:
                if blocked(code, "buy"):
                    unresolved.add(code)
                    continue
                # 买入
                buy_value = min(diff, cash * 0.95)
                shares = self._market_rule.round_volume(code, int(buy_value / price))
                if shares <= 0:
                    continue
                fill = self._execution_cost.buy_fill(price, shares)
                total = fill.cash_delta
                if total > cash:
                    continue
                cash -= total

                if code in positions:
                    old = positions[code]
                    total_shares = old["shares"] + shares
                    positions[code] = {
                        "shares": total_shares,
                        "avg_price": (old["avg_price"] * old["shares"] + fill.fill_price * shares) / total_shares,
                    }
                else:
                    positions[code] = {"shares": shares, "avg_price": fill.fill_price}

                trades.append({
                    "date": trade_date,
                    "type": "buy",
                    "code": code,
                    "shares": shares,
                    "price": round(fill.fill_price, 2),
                    "cost": round(total, 2),
                })

            elif diff < -equity * 0.01:
                if blocked(code, "sell"):
                    unresolved.add(code)
                    continue
                # 减仓
                sell_shares = min(self._market_rule.round_volume(code, int(abs(diff) / price)), current_shares)
                if sell_shares <= 0:
                    continue
                fill = self._execution_cost.sell_fill(price, sell_shares)
                net = fill.cash_delta
                cash += net

                remaining = current_shares - sell_shares
                if remaining > 0:
                    positions[code] = {
                        "shares": remaining,
                        "avg_price": positions[code]["avg_price"],
                    }
                else:
                    del positions[code]

                trades.append({
                    "date": trade_date,
                    "type": "sell",
                    "code": code,
                    "shares": sell_shares,
                    "price": round(fill.fill_price, 2),
                    "revenue": round(net, 2),
                    "cost": round(fill.commission + fill.stamp_tax + fill.transfer_fee, 2),
                })

        return trades, unresolved, cash

    @staticmethod
    def _compute_metrics(
        equity_curve: list[dict],
        daily_returns: list[float],
        trades: list[dict],
        annualization_days: int = 252,
    ) -> dict:
        """计算回测绩效指标"""
        if not equity_curve:
            return {}

        equities = [p["equity"] for p in equity_curve]
        dates = [p["date"] for p in equity_curve]
        n = len(equities)
        initial = equities[0]

        total_return = (equities[-1] - initial) / initial if initial > 0 else 0

        # 年化收益
        if n > 1:
            days = max(n - 1, 1)
            annual_return = (1 + total_return) ** (max(1, annualization_days) / days) - 1
        else:
            annual_return = 0.0

        # 最大回撤
        peak = equities[0]
        max_dd = 0.0
        for eq in equities:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak
            if dd > max_dd:
                max_dd = dd

        # 夏普比率
        if daily_returns:
            avg_ret = np.mean(daily_returns)
            std_ret = np.std(daily_returns, ddof=1)
            sharpe = (avg_ret / std_ret * np.sqrt(max(1, annualization_days))) if std_ret > 0 else 0.0
        else:
            sharpe = 0.0

        # 卡玛比率
        calmar = annual_return / max_dd if max_dd > 0 else 0.0

        # 交易统计
        sell_trades = [t for t in trades if t["type"] == "sell"]
        win_trades = [t for t in sell_trades if t.get("revenue", 0) > t.get("cost", 0)]
        win_rate = len(win_trades) / len(sell_trades) if sell_trades else 0

        total_cost = sum(t.get("cost", 0) for t in trades)

        return {
            "total_return": round(total_return, 4),
            "annual_return": round(annual_return, 4),
            "max_drawdown": round(max_dd, 4),
            "sharpe_ratio": round(sharpe, 4),
            "calmar_ratio": round(calmar, 4),
            "win_rate": round(win_rate, 4),
            "total_trades": len(trades),
            "total_cost": round(total_cost, 2),
            "final_equity": round(equities[-1], 2) if equities else 0,
            "trading_days": max(n - 1, 0),
        }
