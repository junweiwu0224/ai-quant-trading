"""组合回测引擎

基于 AI 选股结果模拟组合交易，计算含交易成本的绩效指标。

支持：
- 等权 / 风险平价 / 因子加权 仓位分配
- 佣金万3 + 印花税千1（卖出）+ 滑点0.1%
- 最大持仓20只、单只2%~10%、行业≤30%
- 净值曲线、年化收益、最大回撤、夏普、卡玛、胜率
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger


# ── 交易成本模型 ──

@dataclass(frozen=True)
class CostModel:
    """A 股交易成本"""
    commission: float = 0.0003     # 佣金费率（万3）
    stamp_tax: float = 0.001       # 印花税（千1，仅卖出）
    slippage: float = 0.001        # 滑点（0.1%）
    min_commission: float = 5.0    # 最低佣金 5 元


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


@dataclass
class BacktestResult:
    """回测结果"""
    equity_curve: list[dict]
    trades: list[dict]
    daily_returns: list[float]
    metrics: dict
    holdings_history: list[dict]

    def to_dict(self) -> dict:
        return {
            "equity_curve": self.equity_curve,
            "trades": self.trades[-100:],
            "metrics": self.metrics,
            "holdings_history": self.holdings_history,
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
        cost = config.cost
        constraints = config.constraints

        cash = config.initial_cash
        positions: dict[str, dict] = {}  # {code: {shares, avg_price}}
        equity_curve = []
        trades = []
        holdings_history = []
        daily_returns = []

        all_dates = sorted(set(
            dt for df in price_data.values()
            for dt in (df["date"].astype(str).tolist() if "date" in df.columns else [])
        ))

        prev_equity = cash

        for i, dt in enumerate(all_dates):
            # 获取当日收盘价
            prices = {}
            for code, df in price_data.items():
                day = df[df["date"].astype(str) == dt]
                if not day.empty:
                    prices[code] = float(day.iloc[0]["close"])

            # 计算当日权益
            equity = cash
            for code, pos in positions.items():
                price = prices.get(code, pos["avg_price"])
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
                    trades_today = self._rebalance(
                        positions, new_weights, prices, cash, equity, cost,
                    )
                    trades.extend(trades_today)

                    # 更新 cash
                    for t in trades_today:
                        if t["type"] == "buy":
                            cash -= t["cost"]
                        else:
                            cash += t["revenue"]

            # 记录持仓
            holdings = []
            for code, pos in positions.items():
                price = prices.get(code, pos["avg_price"])
                holdings.append({
                    "code": code,
                    "shares": pos["shares"],
                    "avg_price": round(pos["avg_price"], 2),
                    "market_value": round(pos["shares"] * price, 2),
                })
            holdings_history.append({"date": dt, "holdings": holdings, "cash": round(cash, 2)})

        metrics = self._compute_metrics(equity_curve, daily_returns, trades)

        return BacktestResult(
            equity_curve=equity_curve,
            trades=trades,
            daily_returns=daily_returns,
            metrics=metrics,
            holdings_history=holdings_history,
        )

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
        cost: CostModel,
    ) -> list[dict]:
        """执行调仓"""
        trades = []

        # 卖出不在目标中的持仓
        codes_to_sell = [c for c in positions if c not in target_weights]
        for code in codes_to_sell:
            price = prices.get(code)
            if not price or price <= 0:
                continue
            pos = positions[code]
            revenue = pos["shares"] * price
            fee = max(revenue * cost.commission, cost.min_commission)
            tax = revenue * cost.stamp_tax
            slip = revenue * cost.slippage
            net = revenue - fee - tax - slip
            cash += net

            trades.append({
                "date": "",
                "type": "sell",
                "code": code,
                "shares": pos["shares"],
                "price": round(price, 2),
                "revenue": round(net, 2),
                "cost": round(fee + tax + slip, 2),
            })
            del positions[code]

        # 调整现有持仓和新建仓位
        for code, target_w in target_weights.items():
            target_value = equity * target_w
            price = prices.get(code)
            if not price or price <= 0:
                continue

            current_shares = positions.get(code, {}).get("shares", 0)
            current_value = current_shares * price
            diff = target_value - current_value

            if abs(diff) < equity * 0.01:
                continue

            if diff > 0 and cash > 0:
                # 买入
                buy_value = min(diff, cash * 0.95)
                shares = int(buy_value / price / 100) * 100
                if shares <= 0:
                    continue
                cost_amount = shares * price
                fee = max(cost_amount * cost.commission, cost.min_commission)
                slip = cost_amount * cost.slippage
                total = cost_amount + fee + slip
                if total > cash:
                    continue
                cash -= total

                if code in positions:
                    old = positions[code]
                    total_shares = old["shares"] + shares
                    positions[code] = {
                        "shares": total_shares,
                        "avg_price": (old["avg_price"] * old["shares"] + price * shares) / total_shares,
                    }
                else:
                    positions[code] = {"shares": shares, "avg_price": price}

                trades.append({
                    "date": "",
                    "type": "buy",
                    "code": code,
                    "shares": shares,
                    "price": round(price, 2),
                    "cost": round(cost_amount + fee + slip, 2),
                })

            elif diff < -equity * 0.01:
                # 减仓
                sell_shares = min(int(abs(diff) / price / 100) * 100, current_shares)
                if sell_shares <= 0:
                    continue
                revenue = sell_shares * price
                fee = max(revenue * cost.commission, cost.min_commission)
                tax = revenue * cost.stamp_tax
                slip = revenue * cost.slippage
                net = revenue - fee - tax - slip
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
                    "date": "",
                    "type": "sell",
                    "code": code,
                    "shares": sell_shares,
                    "price": round(price, 2),
                    "revenue": round(net, 2),
                    "cost": round(fee + tax + slip, 2),
                })

        return trades

    @staticmethod
    def _compute_metrics(
        equity_curve: list[dict],
        daily_returns: list[float],
        trades: list[dict],
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
            days = n  # 简化：按交易日计算
            annual_return = (1 + total_return) ** (252 / max(days, 1)) - 1
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
            sharpe = (avg_ret / std_ret * np.sqrt(252)) if std_ret > 0 else 0.0
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
            "trading_days": n,
        }
