"""Tick 级回测引擎

支持日线/分钟线多粒度回测。Tick 数据可从外部导入，
也可以通过聚合器从分钟线生成更粗粒度的 Bar。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime, timedelta
from enum import Enum
from typing import Optional

import pandas as pd
from loguru import logger

from data.storage import DataStorage
from engine.backtest_engine import BacktestConfig, BacktestResult
from risk.position import PositionManager
from risk.stoploss import StopLossManager
from risk.monitor import RiskMonitor
from strategy.base import Bar, BaseStrategy, Direction, Portfolio, Trade


# ── 数据模型 ──

class BarPeriod(Enum):
    """K线周期"""
    TICK = "tick"          # 逐笔
    MIN_1 = "1m"           # 1 分钟
    MIN_5 = "5m"           # 5 分钟
    MIN_15 = "15m"         # 15 分钟
    MIN_30 = "30m"         # 30 分钟
    MIN_60 = "60m"         # 60 分钟
    DAILY = "daily"        # 日线

    @property
    def minutes(self) -> int:
        """周期对应的分钟数"""
        _map = {
            "tick": 0, "1m": 1, "5m": 5, "15m": 15,
            "30m": 30, "60m": 60, "daily": 240,
        }
        return _map.get(self.value, 0)

    @property
    def label(self) -> str:
        _map = {
            "tick": "逐笔", "1m": "1分钟", "5m": "5分钟",
            "15m": "15分钟", "30m": "30分钟", "60m": "60分钟",
            "daily": "日线",
        }
        return _map.get(self.value, self.value)


@dataclass(frozen=True)
class TickData:
    """逐笔数据"""
    code: str
    datetime: datetime
    price: float
    volume: int
    amount: float = 0.0
    bid_price: float = 0.0       # 买一价
    ask_price: float = 0.0       # 卖一价
    bid_volume: int = 0          # 买一量
    ask_volume: int = 0          # 卖一量

    def __post_init__(self):
        if self.price <= 0:
            raise ValueError(f"Tick 价格必须为正: {self.price}")
        if self.volume < 0:
            raise ValueError(f"Tick 成交量不能为负: {self.volume}")


@dataclass(frozen=True)
class IntradayBar:
    """分钟级 K 线（扩展 Bar，增加 datetime 字段）"""
    code: str
    datetime: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    period: BarPeriod = BarPeriod.MIN_1

    def to_bar(self) -> Bar:
        """转换为策略层 Bar（日期取 datetime 的 date 部分）"""
        return Bar(
            code=self.code,
            date=self.datetime.date(),
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            amount=self.amount,
        )


# ── 聚合器 ──

class TickAggregator:
    """将 Tick 数据聚合为指定周期的 K 线"""

    @staticmethod
    def aggregate_ticks(ticks: list[TickData], period: BarPeriod) -> list[IntradayBar]:
        """将 Tick 数据聚合为 K 线

        Args:
            ticks: 已按时间排序的 Tick 列表
            period: 目标周期（1m/5m/15m/30m/60m）

        Returns:
            聚合后的 IntradayBar 列表
        """
        if not ticks or period == BarPeriod.TICK:
            return []

        if period == BarPeriod.DAILY:
            return TickAggregator._aggregate_to_daily(ticks)

        minutes = period.minutes
        if minutes <= 0:
            return []

        bars: list[IntradayBar] = []
        current_bucket: list[TickData] = []
        bucket_start: Optional[datetime] = None

        for tick in ticks:
            # 计算当前 tick 所属的时间桶
            tick_bucket = TickAggregator._floor_datetime(tick.datetime, minutes)

            if bucket_start is None:
                bucket_start = tick_bucket

            if tick_bucket != bucket_start and current_bucket:
                # 当前桶结束，生成 Bar
                bar = TickAggregator._ticks_to_bar(
                    current_bucket, bucket_start, period
                )
                if bar:
                    bars.append(bar)
                current_bucket = []
                bucket_start = tick_bucket

            current_bucket.append(tick)

        # 最后一个桶
        if current_bucket and bucket_start:
            bar = TickAggregator._ticks_to_bar(
                current_bucket, bucket_start, period
            )
            if bar:
                bars.append(bar)

        return bars

    @staticmethod
    def aggregate_bars(bars: list[IntradayBar], target_period: BarPeriod) -> list[IntradayBar]:
        """将细粒度 K 线聚合为粗粒度（如 1m → 5m）

        Args:
            bars: 已排序的细粒度 IntradayBar
            target_period: 目标周期

        Returns:
            聚合后的 IntradayBar 列表
        """
        if not bars:
            return []

        target_minutes = target_period.minutes
        if target_minutes <= 0:
            return []

        result: list[IntradayBar] = []
        current_bucket: list[IntradayBar] = []
        bucket_start: Optional[datetime] = None

        for bar in bars:
            bar_bucket = TickAggregator._floor_datetime(bar.datetime, target_minutes)

            if bucket_start is None:
                bucket_start = bar_bucket

            if bar_bucket != bucket_start and current_bucket:
                merged = TickAggregator._merge_bars(
                    current_bucket, bucket_start, target_period
                )
                if merged:
                    result.append(merged)
                current_bucket = []
                bucket_start = bar_bucket

            current_bucket.append(bar)

        if current_bucket and bucket_start:
            merged = TickAggregator._merge_bars(
                current_bucket, bucket_start, target_period
            )
            if merged:
                result.append(merged)

        return result

    @staticmethod
    def _floor_datetime(dt: datetime, minutes: int) -> datetime:
        """将时间向下取整到最近的分钟桶"""
        total_minutes = dt.hour * 60 + dt.minute
        floored = (total_minutes // minutes) * minutes
        return dt.replace(
            hour=floored // 60,
            minute=floored % 60,
            second=0,
            microsecond=0,
        )

    @staticmethod
    def _ticks_to_bar(
        ticks: list[TickData], bucket_start: datetime, period: BarPeriod
    ) -> Optional[IntradayBar]:
        """将一批 Tick 聚合为一根 Bar"""
        if not ticks:
            return None

        first = ticks[0]
        code = first.code
        prices = [t.price for t in ticks]
        volumes = [t.volume for t in ticks]
        amounts = [t.amount for t in ticks]

        return IntradayBar(
            code=code,
            datetime=bucket_start,
            open=prices[0],
            high=max(prices),
            low=min(prices),
            close=prices[-1],
            volume=sum(volumes),
            amount=sum(amounts),
            period=period,
        )

    @staticmethod
    def _merge_bars(
        bars: list[IntradayBar], bucket_start: datetime, period: BarPeriod
    ) -> Optional[IntradayBar]:
        """合并多根细粒度 Bar 为一根粗粒度 Bar"""
        if not bars:
            return None

        return IntradayBar(
            code=bars[0].code,
            datetime=bucket_start,
            open=bars[0].open,
            high=max(b.high for b in bars),
            low=min(b.low for b in bars),
            close=bars[-1].close,
            volume=sum(b.volume for b in bars),
            amount=sum(b.amount for b in bars),
            period=period,
        )

    @staticmethod
    def _aggregate_to_daily(ticks: list[TickData]) -> list[IntradayBar]:
        """将 Tick 聚合为日线"""
        by_date: dict[date, list[TickData]] = {}
        for tick in ticks:
            d = tick.datetime.date()
            by_date.setdefault(d, []).append(tick)

        bars = []
        for d in sorted(by_date.keys()):
            day_ticks = by_date[d]
            if not day_ticks:
                continue
            prices = [t.price for t in day_ticks]
            bars.append(IntradayBar(
                code=day_ticks[0].code,
                datetime=datetime(d.year, d.month, d.day, 15, 0),
                open=prices[0],
                high=max(prices),
                low=min(prices),
                close=prices[-1],
                volume=sum(t.volume for t in day_ticks),
                amount=sum(t.amount for t in day_ticks),
                period=BarPeriod.DAILY,
            ))
        return bars


# ── Tick 级回测引擎 ──

class TickBacktestEngine:
    """支持多周期的回测引擎

    核心思路：
    1. 从存储层加载数据（日线或分钟线）
    2. 如果目标周期比数据源粗，通过聚合器合并
    3. 使用与 BacktestEngine 相同的撮合和风控逻辑
    4. Bar.date 统一使用 datetime.date()，Bar 的 datetime 信息保留在 IntradayBar 中
    """

    def __init__(
        self,
        config: Optional[BacktestConfig] = None,
        position_manager: Optional[PositionManager] = None,
        stoploss_manager: Optional[StopLossManager] = None,
        risk_monitor: Optional[RiskMonitor] = None,
    ):
        self._config = config or BacktestConfig()
        self._storage = DataStorage()
        self._position_mgr = position_manager or (
            PositionManager() if self._config.enable_risk else None
        )
        self._stoploss_mgr = stoploss_manager or (
            StopLossManager() if self._config.enable_risk else None
        )
        self._risk_monitor = risk_monitor or (
            RiskMonitor() if self._config.enable_risk else None
        )

    def run(
        self,
        strategy: BaseStrategy,
        codes: list[str],
        start_date: str,
        end_date: str,
        period: BarPeriod = BarPeriod.DAILY,
        warmup_periods: int = 20,
        min_trading_days: int = 5,
        benchmark_code: str = "",
        progress_callback=None,
    ) -> BacktestResult:
        """运行多周期回测

        Args:
            strategy: 策略实例
            codes: 股票代码列表
            start_date: 开始日期
            end_date: 结束日期
            period: K 线周期
            warmup_periods: 预热周期数
            min_trading_days: 最小回测天数
            benchmark_code: 基准代码
            progress_callback: 进度回调

        Returns:
            BacktestResult
        """
        logger.info(
            f"多周期回测开始: {start_date} ~ {end_date}, "
            f"标的: {codes}, 周期: {period.label}"
        )

        start = pd.Timestamp(start_date).date()
        end = pd.Timestamp(end_date).date()
        if start >= end:
            return BacktestResult(error="开始日期必须早于结束日期")

        # 加载并聚合数据
        bars_by_code = self._load_and_aggregate(codes, start, end, period)
        if not bars_by_code:
            return BacktestResult(error="没有足够的历史数据")

        # 按时间排序所有 Bar
        all_bars = sorted(
            {bar.datetime for bars in bars_by_code.values() for bar in bars}
        )

        # 计算预热期（按交易日数）
        warmup_cutoff = self._calc_warmup_cutoff(all_bars, warmup_periods)
        warmup_bars = [b for b in all_bars if b < warmup_cutoff]
        backtest_bars = [b for b in all_bars if b >= warmup_cutoff]

        if len(warmup_bars) < warmup_periods:
            logger.warning(
                f"预热期不足: 需要 {warmup_periods} 个周期，实际 {len(warmup_bars)} 个"
            )

        if len(backtest_bars) < min_trading_days:
            return BacktestResult(
                error=f"回测期太短（{len(backtest_bars)} 个周期，最少 {min_trading_days} 个）"
            )

        logger.info(
            f"预热期: {len(warmup_bars)} 个周期, 回测期: {len(backtest_bars)} 个周期"
        )

        portfolio = Portfolio(cash=self._config.initial_cash)
        strategy.init(portfolio)

        # 构建 datetime → {code: Bar} 索引
        bar_index = self._build_bar_index(bars_by_code)

        # 预热阶段
        for dt in warmup_bars:
            for bar in bar_index.get(dt, {}).values():
                if bar.volume > 0 and bar.open > 0:
                    strategy.on_bar(bar)

        # 回测阶段
        total = len(backtest_bars)
        for idx, dt in enumerate(backtest_bars):
            period_bars = bar_index.get(dt, {})

            # 1. 撮合上一周期挂单
            self._match_orders(strategy, portfolio, period_bars)

            # 2. 计算权益
            prices = {c: b.close for c, b in period_bars.items()}
            equity = portfolio.get_total_equity(prices)

            # 3. 止损检查
            if self._stoploss_mgr:
                self._stoploss_mgr.update_equity(dt.date(), equity)
                self._check_stoploss(strategy, portfolio, period_bars, equity)
                equity = portfolio.get_total_equity(prices)

            # 4. 日亏损限额
            skip_trading = False
            if self._stoploss_mgr:
                dl_signal = self._stoploss_mgr.check_daily_loss(equity)
                if dl_signal:
                    skip_trading = True

            # 5. 推送 K 线
            if not skip_trading:
                for bar in period_bars.values():
                    if bar.volume > 0 and bar.open > 0:
                        strategy.on_bar(bar)

            # 6. 仓位过滤
            if self._position_mgr:
                self._filter_orders(strategy, portfolio, prices)

            # 7. 风控快照
            if self._risk_monitor:
                self._risk_monitor.snapshot(dt.date(), portfolio, prices)

            # 8. 记录权益
            equity = portfolio.get_total_equity(prices)
            portfolio.equity_curve.append({
                "date": dt.date(),
                "equity": equity,
                "datetime": dt.isoformat(),
            })

            # 9. 进度回调
            if progress_callback:
                progress = (idx + 1) / total
                progress_callback(progress, dt.isoformat(), idx + 1, total)

        # 基准数据
        benchmark_curve = []
        if benchmark_code:
            benchmark_curve = self._load_benchmark(benchmark_code, start, end)

        result = self._generate_report(portfolio, benchmark_curve)
        result.warmup_days = len(warmup_bars)
        logger.info(
            f"多周期回测完成: 总收益 {result.total_return:.2%}, "
            f"最大回撤 {result.max_drawdown:.2%}"
        )
        return result

    def _load_and_aggregate(
        self,
        codes: list[str],
        start: date,
        end: date,
        period: BarPeriod,
    ) -> dict[str, list[IntradayBar]]:
        """加载数据并按目标周期聚合

        当前实现：从 stock_daily 表加载日线数据，
        对于非日线周期，将日线转换为 IntradayBar。
        未来可扩展为加载分钟线数据源。
        """
        result: dict[str, list[IntradayBar]] = {}

        for code in codes:
            warmup_start = start - pd.Timedelta(days=60)
            df = self._storage.get_stock_daily(code, warmup_start, end)

            if df.empty:
                logger.warning(f"[{code}] 无数据")
                continue

            if period == BarPeriod.DAILY:
                # 日线直接转换
                bars = [
                    IntradayBar(
                        code=code,
                        datetime=datetime.combine(row["date"], dtime(15, 0)),
                        open=row["open"],
                        high=row["high"],
                        low=row["low"],
                        close=row["close"],
                        volume=row["volume"],
                        amount=row["amount"],
                        period=BarPeriod.DAILY,
                    )
                    for _, row in df.iterrows()
                    if row["volume"] > 0 and row["open"] > 0
                ]
            else:
                # 将日线模拟为分钟线（骨架实现）
                # 实际场景应从分钟线数据源加载
                bars = self._simulate_intraday_from_daily(df, code, period)

            result[code] = bars

        return result

    def _simulate_intraday_from_daily(
        self,
        df: pd.DataFrame,
        code: str,
        period: BarPeriod,
    ) -> list[IntradayBar]:
        """从日线模拟生成分钟线（骨架实现）

        将每根日线拆分为多根分钟线，使用 OHLC 的线性插值。
        这是骨架实现，实际生产中应接入真实分钟线数据源。
        """
        bars: list[IntradayBar] = []
        minutes_per_day = 240  # A 股每日交易时间
        period_minutes = period.minutes
        bars_per_day = minutes_per_day // period_minutes

        # A 股交易时段
        morning_start = dtime(9, 30)
        morning_end = dtime(11, 30)
        afternoon_start = dtime(13, 0)
        afternoon_end = dtime(15, 0)

        for _, row in df.iterrows():
            if row["volume"] <= 0 or row["open"] <= 0:
                continue

            d = row["date"]
            o, h, l, c = row["open"], row["high"], row["low"], row["close"]
            vol = row["volume"]
            amt = row.get("amount", vol * (o + c) / 2)

            # 生成日内分钟线序列
            for i in range(bars_per_day):
                t = self._calc_bar_time(i, period_minutes, morning_start, morning_end,
                                        afternoon_start, afternoon_end)
                if t is None:
                    continue

                dt = datetime.combine(d, t)
                frac = (i + 1) / bars_per_day

                # 简单线性插值模拟价格路径
                base_price = o + (c - o) * frac
                noise = (h - l) * 0.1 * (1 if i % 2 == 0 else -1)
                bar_close = round(base_price + noise, 2)
                bar_open = round(o + (c - o) * (i / bars_per_day), 2) if i > 0 else o
                bar_high = round(max(bar_open, bar_close) + abs(h - l) * 0.05, 2)
                bar_low = round(min(bar_open, bar_close) - abs(h - l) * 0.05, 2)

                # 确保 high/low 在日线范围内
                bar_high = min(bar_high, h)
                bar_low = max(bar_low, l)

                bar_vol = int(vol / bars_per_day)

                bars.append(IntradayBar(
                    code=code,
                    datetime=dt,
                    open=bar_open,
                    high=bar_high,
                    low=bar_low,
                    close=bar_close,
                    volume=bar_vol,
                    amount=amt / bars_per_day,
                    period=period,
                ))

        return bars

    @staticmethod
    def _calc_bar_time(
        idx: int,
        period_minutes: int,
        morning_start: dtime,
        morning_end: dtime,
        afternoon_start: dtime,
        afternoon_end: dtime,
    ) -> Optional[dtime]:
        """计算第 idx 根 Bar 对应的时间"""
        morning_minutes = (
            (morning_end.hour - morning_start.hour) * 60
            + morning_end.minute - morning_start.minute
        )  # 120

        offset = idx * period_minutes

        if offset < morning_minutes:
            total = morning_start.hour * 60 + morning_start.minute + offset
            return dtime(total // 60, total % 60)

        afternoon_offset = offset - morning_minutes
        afternoon_minutes = (
            (afternoon_end.hour - afternoon_start.hour) * 60
            + afternoon_end.minute - afternoon_start.minute
        )  # 120

        if afternoon_offset < afternoon_minutes:
            total = afternoon_start.hour * 60 + afternoon_start.minute + afternoon_offset
            return dtime(total // 60, total % 60)

        return None

    def _build_bar_index(
        self, bars_by_code: dict[str, list[IntradayBar]]
    ) -> dict[datetime, dict[str, IntradayBar]]:
        """构建 datetime → {code: bar} 索引"""
        index: dict[datetime, dict[str, IntradayBar]] = {}
        for code, bars in bars_by_code.items():
            for bar in bars:
                index.setdefault(bar.datetime, {})[code] = bar
        return index

    def _calc_warmup_cutoff(
        self, all_bars: list[datetime], warmup_periods: int
    ) -> datetime:
        """计算预热截止时间"""
        if len(all_bars) <= warmup_periods:
            return all_bars[0]
        return all_bars[warmup_periods]

    def _match_orders(
        self,
        strategy: BaseStrategy,
        portfolio: Portfolio,
        bars: dict[str, IntradayBar],
    ):
        """撮合挂单"""
        orders = strategy.get_pending_orders()
        for order in orders:
            bar = bars.get(order.code)
            if bar is None:
                continue

            # 成交价：开盘价 ± 滑点
            if order.direction == Direction.LONG:
                fill_price = round(bar.open * (1 + self._config.slippage), 2)
            else:
                fill_price = round(bar.open * (1 - self._config.slippage), 2)

            # 计算费用
            commission = max(
                fill_price * order.volume * self._config.commission_rate,
                5.0,
            )
            stamp_tax = (
                fill_price * order.volume * self._config.stamp_tax_rate
                if order.direction == Direction.SHORT
                else 0
            )

            # 更新持仓
            if order.direction == Direction.LONG:
                cost = fill_price * order.volume + commission
                if portfolio.cash < cost:
                    continue  # 资金不足
                portfolio.cash -= cost
                old_vol = portfolio.positions.get(order.code, 0)
                old_avg = portfolio.avg_prices.get(order.code, 0)
                new_vol = old_vol + order.volume
                if new_vol > 0:
                    portfolio.avg_prices[order.code] = (
                        (old_avg * old_vol + fill_price * order.volume) / new_vol
                    )
                portfolio.positions[order.code] = new_vol
                portfolio.entry_dates.setdefault(order.code, str(bar.datetime.date()))
            else:
                revenue = fill_price * order.volume - commission - stamp_tax
                portfolio.cash += revenue
                old_vol = portfolio.positions.get(order.code, 0)
                new_vol = max(0, old_vol - order.volume)
                portfolio.positions[order.code] = new_vol

            # 记录成交
            trade = Trade(
                code=order.code,
                direction=order.direction,
                price=fill_price,
                volume=order.volume,
                order_id=order.order_id,
                datetime=bar.datetime.date(),
                entry_price=portfolio.avg_prices.get(order.code, 0),
                entry_date=portfolio.entry_dates.get(order.code),
            )
            strategy.record_trade(trade)
            order.status = "filled"

    def _check_stoploss(
        self,
        strategy: BaseStrategy,
        portfolio: Portfolio,
        bars: dict[str, IntradayBar],
        equity: float,
    ):
        """止损检查"""
        if not self._stoploss_mgr:
            return
        for code, vol in list(portfolio.positions.items()):
            if vol <= 0:
                continue
            bar = bars.get(code)
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
                if signal.action == "sell" and vol > 0:
                    strategy.sell(code, bar.close, vol)
                    self._stoploss_mgr.clear_trailing_high(code)
                    logger.warning(f"[止损] {signal.reason}")
                    break

    def _filter_orders(
        self,
        strategy: BaseStrategy,
        portfolio: Portfolio,
        prices: dict[str, float],
    ):
        """过滤不合规挂单"""
        if not self._position_mgr:
            return
        pending = strategy.get_pending_orders()
        kept = []
        for order in pending:
            if order.direction == Direction.LONG:
                passed, _ = self._position_mgr.check_buy(
                    code=order.code,
                    price=order.price,
                    volume=order.volume,
                    portfolio=portfolio,
                    prices=prices,
                )
                if passed:
                    kept.append(order)
            else:
                kept.append(order)
        # 将保留的订单放回
        strategy._pending_orders.extend(kept)

    def _load_benchmark(
        self, benchmark_code: str, start: date, end: date
    ) -> list[dict]:
        """加载基准数据"""
        df = self._storage.get_stock_daily(benchmark_code, start, end)
        if df.empty:
            return []
        closes = df["close"].tolist()
        dates = df["date"].tolist()
        if not closes or closes[0] == 0:
            return []
        first = closes[0]
        return [
            {"date": d, "equity": round(c / first, 6)}
            for d, c in zip(dates, closes)
        ]

    def _generate_report(
        self, portfolio: Portfolio, benchmark_curve: list[dict]
    ) -> BacktestResult:
        """生成回测报告（复用 BacktestEngine 的逻辑）"""
        curve = portfolio.equity_curve
        if not curve:
            return BacktestResult(error="无权益曲线数据")

        initial = curve[0]["equity"] if curve else self._config.initial_cash
        final = curve[-1]["equity"] if curve else initial
        total_return = (final / initial - 1) if initial else 0

        # 年化收益
        days = len(curve)
        annual_return = (
            (1 + total_return) ** (252 / max(days, 1)) - 1
            if total_return > -1
            else -1
        )

        # 最大回撤
        max_dd = 0
        peak = initial
        for point in curve:
            eq = point["equity"]
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

        # 夏普比率
        if len(curve) > 1:
            returns = [
                (curve[i]["equity"] / curve[i - 1]["equity"] - 1)
                for i in range(1, len(curve))
            ]
            avg_ret = sum(returns) / len(returns)
            std_ret = (
                sum((r - avg_ret) ** 2 for r in returns) / len(returns)
            ) ** 0.5
            sharpe = (avg_ret * 252 ** 0.5 / std_ret) if std_ret > 0 else 0

            # Sortino
            downside = [r for r in returns if r < 0]
            down_std = (
                sum(r ** 2 for r in downside) / len(downside)
            ) ** 0.5 if downside else 0
            sortino = (avg_ret * 252 ** 0.5 / down_std) if down_std > 0 else 0
        else:
            sharpe = sortino = 0

        # 交易统计
        trades = portfolio.trades
        sell_trades = [
            t for t in trades if t.direction == Direction.SHORT
        ]
        total_trades = len(sell_trades)
        if total_trades > 0:
            wins = [
                t for t in sell_trades
                if t.price > t.entry_price
            ]
            losses = [
                t for t in sell_trades
                if t.price <= t.entry_price
            ]
            win_rate = len(wins) / total_trades
            avg_win = (
                sum((t.price - t.entry_price) / t.entry_price for t in wins) / len(wins)
                if wins else 0
            )
            avg_loss = (
                sum((t.entry_price - t.price) / t.entry_price for t in losses) / len(losses)
                if losses else 0
            )
            profit_loss_ratio = (avg_win / avg_loss) if avg_loss > 0 else 0

            # 最大连续盈亏
            max_win_streak = max_loss_streak = 0
            current_win = current_loss = 0
            for t in sell_trades:
                if t.price > t.entry_price:
                    current_win += 1
                    current_loss = 0
                else:
                    current_loss += 1
                    current_win = 0
                max_win_streak = max(max_win_streak, current_win)
                max_loss_streak = max(max_loss_streak, current_loss)
        else:
            win_rate = profit_loss_ratio = 0
            max_win_streak = max_loss_streak = 0

        return BacktestResult(
            start_date=curve[0]["date"] if curve else None,
            end_date=curve[-1]["date"] if curve else None,
            initial_cash=initial,
            final_equity=round(final, 2),
            total_return=round(total_return, 6),
            annual_return=round(annual_return, 6),
            max_drawdown=round(max_dd, 6),
            sharpe_ratio=round(sharpe, 2),
            sortino_ratio=round(sortino, 2),
            calmar_ratio=round(annual_return / max_dd, 2) if max_dd > 0 else 0,
            win_rate=round(win_rate, 4),
            profit_loss_ratio=round(profit_loss_ratio, 2),
            max_consecutive_wins=max_win_streak,
            max_consecutive_losses=max_loss_streak,
            total_trades=total_trades,
            equity_curve=[
                {**{"date": str(p["date"]), "equity": p["equity"]},
                 **({"datetime": p["datetime"]} if "datetime" in p else {})}
                for p in curve
            ],
            benchmark_curve=benchmark_curve,
            trades=trades,
            risk_alerts=[],
            warmup_days=0,
        )

    @staticmethod
    def _trade_to_dict(trade: Trade) -> dict:
        return {
            "code": trade.code,
            "direction": trade.direction.value,
            "price": trade.price,
            "volume": trade.volume,
            "datetime": str(trade.datetime) if trade.datetime else None,
            "entry_price": trade.entry_price,
            "entry_date": str(trade.entry_date) if trade.entry_date else None,
        }
