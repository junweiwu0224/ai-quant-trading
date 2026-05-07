"""回测引擎"""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import pandas as pd
from loguru import logger

from data.storage import DataStorage
from strategy.base import Bar, BaseStrategy, Direction, Portfolio, Trade


@dataclass
class BacktestConfig:
    """回测配置"""
    initial_cash: float = 1_000_000.0
    commission_rate: float = 0.0003  # 万三佣金
    stamp_tax_rate: float = 0.001  # 千一印花税（卖出收取）
    slippage: float = 0.002  # 0.2% 滑点


@dataclass
class BacktestResult:
    """回测结果"""
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    initial_cash: float = 0.0
    final_equity: float = 0.0
    total_return: float = 0.0
    annual_return: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    total_trades: int = 0
    equity_curve: list = field(default_factory=list)
    trades: list = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "回测区间": f"{self.start_date} ~ {self.end_date}",
            "初始资金": f"{self.initial_cash:,.0f}",
            "最终权益": f"{self.final_equity:,.2f}",
            "总收益率": f"{self.total_return:.2%}",
            "年化收益率": f"{self.annual_return:.2%}",
            "最大回撤": f"{self.max_drawdown:.2%}",
            "夏普比率": f"{self.sharpe_ratio:.2f}",
            "胜率": f"{self.win_rate:.2%}",
            "总交易次数": self.total_trades,
        }


class BacktestEngine:
    """回测引擎"""

    def __init__(self, config: Optional[BacktestConfig] = None):
        self._config = config or BacktestConfig()
        self._storage = DataStorage()

    def run(
        self,
        strategy: BaseStrategy,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> BacktestResult:
        """运行回测"""
        logger.info(f"回测开始: {start_date} ~ {end_date}, 标的: {codes}")

        portfolio = Portfolio(cash=self._config.initial_cash)
        strategy.init(portfolio)

        # 加载数据
        bars_by_code = self._load_bars(codes, start_date, end_date)
        if not bars_by_code:
            logger.error("无回测数据")
            return BacktestResult()

        # 合并所有日期并排序
        all_dates = sorted({bar.date for bars in bars_by_code.values() for bar in bars})
        logger.info(f"共 {len(all_dates)} 个交易日")

        # 逐日回测
        for current_date in all_dates:
            daily_bars = {}
            for code, bars in bars_by_code.items():
                for bar in bars:
                    if bar.date == current_date:
                        daily_bars[code] = bar
                        break

            # 1. 先处理上一日挂单
            self._match_orders(strategy, portfolio, daily_bars)

            # 2. 推送当日K线（过滤停牌/零成交量）
            for bar in daily_bars.values():
                if bar.volume > 0 and bar.open > 0:
                    strategy.on_bar(bar)

            # 3. 处理当日新挂单（下一日撮合）
            # 挂单在 strategy.on_bar 中通过 buy/sell 提交
            # 这里不做撮合，留到下一日

            # 记录权益曲线
            prices = {code: bar.close for code, bar in daily_bars.items()}
            equity = portfolio.get_total_equity(prices)
            portfolio.equity_curve.append({"date": current_date, "equity": equity})

        # 生成报告
        result = self._generate_report(portfolio)
        logger.info(f"回测完成: 总收益 {result.total_return:.2%}, 最大回撤 {result.max_drawdown:.2%}")
        return result

    def _load_bars(self, codes: list[str], start_date: str, end_date: str) -> dict[str, list[Bar]]:
        """从数据库加载K线数据"""
        result = {}
        start = pd.Timestamp(start_date).date()
        end = pd.Timestamp(end_date).date()

        for code in codes:
            df = self._storage.get_stock_daily(code, start, end)
            if df.empty:
                logger.warning(f"[{code}] 无数据")
                continue
            bars = [
                Bar(
                    code=code,
                    date=row["date"],
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    volume=row["volume"],
                    amount=row["amount"],
                )
                for _, row in df.iterrows()
            ]
            result[code] = bars
        return result

    def _match_orders(self, strategy: BaseStrategy, portfolio: Portfolio, daily_bars: dict[str, Bar]):
        """撮合挂单（以当日开盘价 + 滑点模拟）"""
        pending = strategy.get_pending_orders()
        for order in pending:
            bar = daily_bars.get(order.code)
            if bar is None:
                continue

            # 用开盘价 + 滑点计算成交价
            if order.direction == Direction.LONG:
                fill_price = bar.open * (1 + self._config.slippage)
                cost = fill_price * order.volume
                commission = max(cost * self._config.commission_rate, 5.0)

                if portfolio.cash >= cost + commission:
                    portfolio.cash -= cost + commission
                    old_vol = portfolio.positions.get(order.code, 0)
                    old_avg = portfolio.avg_prices.get(order.code, 0.0)
                    new_vol = old_vol + order.volume
                    new_avg = (old_avg * old_vol + fill_price * order.volume) / new_vol
                    portfolio.positions[order.code] = new_vol
                    portfolio.avg_prices[order.code] = new_avg
                    order.status = "filled"

                    trade = Trade(
                        code=order.code,
                        direction=order.direction,
                        price=fill_price,
                        volume=order.volume,
                        order_id=order.order_id,
                        datetime=bar.date,
                    )
                    strategy.record_trade(trade)
                else:
                    order.status = "cancelled"

            elif order.direction == Direction.SHORT:
                current_pos = portfolio.positions.get(order.code, 0)
                actual_vol = min(order.volume, current_pos)
                if actual_vol <= 0:
                    order.status = "cancelled"
                    continue

                fill_price = bar.open * (1 - self._config.slippage)
                revenue = fill_price * actual_vol
                commission = max(revenue * self._config.commission_rate, 5.0)
                stamp_tax = revenue * self._config.stamp_tax_rate

                entry_price = portfolio.avg_prices.get(order.code, fill_price)

                portfolio.cash += revenue - commission - stamp_tax
                portfolio.positions[order.code] = current_pos - actual_vol
                if portfolio.positions[order.code] == 0:
                    del portfolio.positions[order.code]
                    del portfolio.avg_prices[order.code]

                if actual_vol < order.volume:
                    order.status = "partial"
                    logger.warning(f"[{order.code}] 部分成交: 请求 {order.volume}, 实际 {actual_vol}")
                else:
                    order.status = "filled"

                trade = Trade(
                    code=order.code,
                    direction=order.direction,
                    price=fill_price,
                    volume=actual_vol,
                    order_id=order.order_id,
                    datetime=bar.date,
                    entry_price=entry_price,
                )
                strategy.record_trade(trade)

    def _generate_report(self, portfolio: Portfolio) -> BacktestResult:
        """生成回测报告"""
        curve = portfolio.equity_curve
        if not curve:
            return BacktestResult()

        equities = [p["equity"] for p in curve]
        dates = [p["date"] for p in curve]
        initial = self._config.initial_cash
        final = equities[-1]

        # 总收益率
        total_return = (final - initial) / initial

        # 年化收益率
        days = (dates[-1] - dates[0]).days
        annual_return = (1 + total_return) ** (365 / max(days, 1)) - 1 if days > 0 else 0.0

        # 最大回撤
        peak = equities[0]
        max_dd = 0.0
        for eq in equities:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak
            if dd > max_dd:
                max_dd = dd

        # 夏普比率（日收益率）
        if len(equities) > 1:
            daily_returns = [
                (equities[i] - equities[i - 1]) / equities[i - 1]
                for i in range(1, len(equities))
            ]
            avg_ret = sum(daily_returns) / len(daily_returns)
            std_ret = (sum((r - avg_ret) ** 2 for r in daily_returns) / len(daily_returns)) ** 0.5
            sharpe = (avg_ret / std_ret * (252 ** 0.5)) if std_ret > 0 else 0.0
        else:
            sharpe = 0.0

        # 胜率
        trades = portfolio.trades
        sell_trades = [t for t in trades if t.direction == Direction.SHORT]
        if sell_trades:
            wins = 0
            for t in sell_trades:
                if t.entry_price > 0 and t.price > t.entry_price:
                    wins += 1
            win_rate = wins / len(sell_trades)
        else:
            win_rate = 0.0

        return BacktestResult(
            start_date=dates[0],
            end_date=dates[-1],
            initial_cash=initial,
            final_equity=final,
            total_return=total_return,
            annual_return=annual_return,
            max_drawdown=max_dd,
            sharpe_ratio=sharpe,
            win_rate=win_rate,
            total_trades=len(trades),
            equity_curve=curve,
            trades=[t for t in trades],
        )
