"""回测引擎"""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import pandas as pd
from loguru import logger

from data.storage import DataStorage
from risk.position import PositionManager
from risk.stoploss import StopLossManager
from risk.monitor import RiskAlert, RiskMonitor
from strategy.base import Bar, BaseStrategy, Direction, Portfolio, Trade


@dataclass
class BacktestConfig:
    """回测配置"""
    initial_cash: float = 1_000_000.0
    commission_rate: float = 0.0003  # 万三佣金
    stamp_tax_rate: float = 0.001  # 千一印花税（卖出收取）
    slippage: float = 0.002  # 0.2% 滑点
    enable_risk: bool = False  # 是否启用风控


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
    risk_alerts: list = field(default_factory=list)
    warmup_days: int = 0
    error: Optional[str] = None

    def summary(self) -> dict:
        return {
            "回测区间": f"{self.start_date} ~ {self.end_date}",
            "初始资金": f"{self.initial_cash:,.0f}",
            "最终收益": f"{self.final_equity:,.2f}",
            "总收益率": f"{self.total_return:.2%}",
            "年化收益率": f"{self.annual_return:.2%}",
            "最大回撤": f"{self.max_drawdown:.2%}",
            "夏普比率": f"{self.sharpe_ratio:.2f}",
            "胜率": f"{self.win_rate:.2%}",
            "总交易次数": self.total_trades,
        }


class BacktestEngine:
    """回测引擎"""

    def __init__(
        self,
        config: Optional[BacktestConfig] = None,
        position_manager: Optional[PositionManager] = None,
        stoploss_manager: Optional[StopLossManager] = None,
        risk_monitor: Optional[RiskMonitor] = None,
    ):
        self._config = config or BacktestConfig()
        self._storage = DataStorage()
        self._position_mgr = position_manager or (PositionManager() if self._config.enable_risk else None)
        self._stoploss_mgr = stoploss_manager or (StopLossManager() if self._config.enable_risk else None)
        self._risk_monitor = risk_monitor or (RiskMonitor() if self._config.enable_risk else None)

    def run(
        self,
        strategy: BaseStrategy,
        codes: list[str],
        start_date: str,
        end_date: str,
        warmup_periods: int = 20,
        min_trading_days: int = 5,
    ) -> BacktestResult:
        """运行回测"""
        logger.info(f"回测开始: {start_date} ~ {end_date}, 标的: {codes}")

        # 验证日期范围
        start = pd.Timestamp(start_date).date()
        end = pd.Timestamp(end_date).date()
        if start >= end:
            return BacktestResult(error="开始日期必须早于结束日期")

        # 计算预热期开始日期
        warmup_start = start - pd.Timedelta(days=warmup_periods * 2)  # 预留足够的自然日

        # 加载数据（包括预热期）
        bars_by_code = self._load_bars(codes, str(warmup_start), end_date)
        if not bars_by_code:
            logger.error("无回测数据")
            return BacktestResult(error="数据库中没有足够的历史数据，请选择更晚的开始日期")

        # 合并所有日期并排序
        all_dates = sorted({bar.date for bars in bars_by_code.values() for bar in bars})

        # 分离预热期和正式回测期
        warmup_dates = [d for d in all_dates if d < start]
        backtest_dates = [d for d in all_dates if d >= start]

        # 验证预热期是否足够
        if len(warmup_dates) < warmup_periods:
            logger.warning(f"预热期不足: 需要 {warmup_periods} 个交易日，实际 {len(warmup_dates)} 个")
            # 如果预热期不足，尝试从数据库中获取更多历史数据
            if len(warmup_dates) < warmup_periods:
                return BacktestResult(
                    error=f"数据库中没有足够的历史数据来初始化策略（需要 {warmup_periods} 个交易日的预热期，实际只有 {len(warmup_dates)} 个）。请选择更晚的开始日期。"
                )

        # 验证最小回测期
        if len(backtest_dates) < min_trading_days:
            return BacktestResult(
                error=f"回测日期范围太短（只有 {len(backtest_dates)} 个交易日，最少需要 {min_trading_days} 个）。请选择更长的日期范围。"
            )

        logger.info(f"预热期: {len(warmup_dates)} 个交易日, 回测期: {len(backtest_dates)} 个交易日")

        portfolio = Portfolio(cash=self._config.initial_cash)
        strategy.init(portfolio)

        # 预热期：只运行策略的 on_bar() 方法，不记录权益曲线
        for current_date in warmup_dates:
            daily_bars = {}
            for code, bars in bars_by_code.items():
                for bar in bars:
                    if bar.date == current_date:
                        daily_bars[code] = bar
                        break

            # 推送预热期K线
            for bar in daily_bars.values():
                if bar.volume > 0 and bar.open > 0:
                    strategy.on_bar(bar)

        # 正式回测期：运行完整的回测逻辑
        for current_date in backtest_dates:
            daily_bars = {}
            for code, bars in bars_by_code.items():
                for bar in bars:
                    if bar.date == current_date:
                        daily_bars[code] = bar
                        break

            # 1. 先处理上一日挂单
            self._match_orders(strategy, portfolio, daily_bars)

            # 计算当日价格和权益
            prices = {code: bar.close for code, bar in daily_bars.items()}
            equity = portfolio.get_total_equity(prices)

            # 2. 风控：止损检查
            if self._stoploss_mgr:
                self._stoploss_mgr.update_equity(current_date, equity)
                self._check_stoploss(strategy, portfolio, daily_bars, equity)

            # 3. 风控：更新权益后重新计算（止损可能已平仓）
            equity = portfolio.get_total_equity(prices)

            # 4. 风控：日亏损限额检查（触发则跳过新交易）
            skip_trading = False
            if self._stoploss_mgr:
                dl_signal = self._stoploss_mgr.check_daily_loss(equity)
                if dl_signal:
                    skip_trading = True
                    logger.warning(f"[风控] {dl_signal.reason}")

            # 5. 推送当日K线（过滤停牌/零成交量）
            if not skip_trading:
                for bar in daily_bars.values():
                    if bar.volume > 0 and bar.open > 0:
                        strategy.on_bar(bar)

            # 6. 风控：仓位检查 — 过滤不合规的挂单
            if self._position_mgr:
                self._filter_orders_by_position(strategy, portfolio, prices)

            # 7. 风控监控：记录风险快照
            if self._risk_monitor:
                self._risk_monitor.snapshot(current_date, portfolio, prices)

            # 记录权益曲线
            equity = portfolio.get_total_equity(prices)
            portfolio.equity_curve.append({"date": current_date, "equity": equity})

        # 生成报告
        result = self._generate_report(portfolio)
        result.warmup_days = len(warmup_dates)
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

    def _check_stoploss(
        self,
        strategy: BaseStrategy,
        portfolio: Portfolio,
        daily_bars: dict[str, Bar],
        equity: float,
    ):
        """检查止损规则，触发则生成卖出订单"""
        if not self._stoploss_mgr:
            return

        for code, vol in list(portfolio.positions.items()):
            if vol <= 0:
                continue
            bar = daily_bars.get(code)
            if bar is None:
                continue

            entry_price = portfolio.avg_prices.get(code, 0)
            signals = self._stoploss_mgr.check_all(
                code=code,
                entry_price=entry_price,
                current_price=bar.close,
                equity=equity,
            )

            for signal in signals:
                if signal.code == "*":
                    # 全局信号：全部平仓
                    for c, v in list(portfolio.positions.items()):
                        if v > 0:
                            strategy.sell(c, daily_bars.get(c, bar).close, v)
                    logger.warning(f"[止损] {signal.reason}")
                    return
                elif signal.action == "sell" and vol > 0:
                    strategy.sell(code, bar.close, vol)
                    self._stoploss_mgr.clear_trailing_high(code)
                    logger.warning(f"[止损] {signal.reason}")
                    break

    def _filter_orders_by_position(
        self,
        strategy: BaseStrategy,
        portfolio: Portfolio,
        prices: dict[str, float],
    ):
        """过滤不符合仓位规则的挂单"""
        if not self._position_mgr:
            return

        pending = strategy.get_pending_orders()
        kept = []
        for order in pending:
            if order.direction == Direction.LONG:
                passed, reason = self._position_mgr.check_buy(
                    code=order.code,
                    price=order.price,
                    volume=order.volume,
                    portfolio=portfolio,
                    prices=prices,
                )
                if not passed:
                    order.status = "cancelled"
                    logger.info(f"[仓位] 拒绝买入 {order.code}: {reason}")
                    continue
            kept.append(order)
        strategy._pending_orders = kept

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
            risk_alerts=self._risk_monitor.alerts if self._risk_monitor else [],
        )
