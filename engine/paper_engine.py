"""模拟盘引擎"""
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from config.settings import LOG_DIR, PROJECT_ROOT
from data.collector.quote_service import QuoteData, get_quote_service
from engine.backtest_engine import BacktestConfig
from engine.models import PaperConfig as NewPaperConfig
from engine.order_manager import OrderManager
from engine.performance_analyzer import PerformanceAnalyzer
from engine.risk_manager import RiskManager
from risk.position import PositionManager
from risk.stoploss import StopLossManager
from strategy.base import Bar, BaseStrategy, Direction, Portfolio, Trade


@dataclass
class PaperConfig:
    """模拟盘配置"""
    initial_cash: float = 1_000_000  # 初始资金
    interval_seconds: int = 30        # 行情轮询间隔
    commission_rate: float = 0.0003   # 万三佣金
    stamp_tax_rate: float = 0.001     # 千一印花税
    slippage: float = 0.002           # 0.2% 滑点
    state_dir: str = str(LOG_DIR / "paper")  # 状态持久化目录
    enable_risk: bool = True          # 启用风控


class PaperTradeLog:
    """交易日志"""

    def __init__(self, log_dir: str = str(LOG_DIR / "paper")):
        self._dir = Path(log_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._log_file = self._dir / f"trades_{datetime.now():%Y%m%d}.jsonl"
        self._trades: list[dict] = []

    def record(self, trade: Trade, equity: float):
        """记录成交"""
        entry = {
            "time": datetime.now().isoformat(),
            "code": trade.code,
            "direction": trade.direction.value,
            "price": round(trade.price, 3),
            "volume": trade.volume,
            "entry_price": round(trade.entry_price, 3),
            "trade_id": trade.trade_id,
            "equity": round(equity, 2),
        }
        self._trades.append(entry)

        try:
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.error(f"交易日志写入失败: {e}")

        logger.info(
            f"[交易] {trade.direction.value} {trade.code} "
            f"价格={trade.price:.2f} 数量={trade.volume} 收益={equity:,.0f}"
        )

    @property
    def today_trades(self) -> list[dict]:
        return list(self._trades)


class PaperStateManager:
    """模拟盘状态持久化"""

    def __init__(self, state_dir: str = str(LOG_DIR / "paper")):
        self._dir = Path(state_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._state_file = self._dir / "portfolio_state.json"
        self._snapshot_file = self._dir / "portfolio_snapshots.jsonl"

    def save(self, portfolio: Portfolio):
        """保存投资组合状态"""
        state = {
            "saved_at": datetime.now().isoformat(),
            "cash": portfolio.cash,
            "positions": dict(portfolio.positions),
            "avg_prices": {k: round(v, 4) for k, v in portfolio.avg_prices.items()},
            "trade_count": len(portfolio.trades),
            "entry_dates": dict(portfolio.entry_dates),
            "strategies": dict(portfolio.strategies),
        }
        self._state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2))
        logger.debug(f"状态已保存: 现金={portfolio.cash:,.0f}")

    def load(self) -> Optional[dict]:
        """加载投资组合状态"""
        if not self._state_file.exists():
            return None
        try:
            data = json.loads(self._state_file.read_text())
            logger.info(f"加载状态: 现金={data['cash']:,.0f}, 持仓={len(data['positions'])}只")
            return data
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"状态文件损坏: {e}")
            return None


class PaperEngine:
    """模拟盘引擎"""

    def __init__(
        self,
        strategy: BaseStrategy,
        codes: list[str],
        config: Optional[PaperConfig] = None,
    ):
        self._strategy = strategy
        self._codes = codes
        self._config = config or PaperConfig()
        self._quote_service = get_quote_service()
        self._quote_service.subscribe(codes)
        self._trade_log = PaperTradeLog(self._config.state_dir)
        self._state_mgr = PaperStateManager(self._config.state_dir)
        self._running = False

        # 风控
        self._position_mgr = PositionManager() if self._config.enable_risk else None
        self._stoploss_mgr = StopLossManager() if self._config.enable_risk else None

        # 新增：订单管理器、绩效分析器、风险管理器
        new_config = NewPaperConfig(
            initial_cash=self._config.initial_cash,
            interval_seconds=self._config.interval_seconds,
            enable_risk=self._config.enable_risk,
            commission_rate=self._config.commission_rate,
            stamp_tax_rate=self._config.stamp_tax_rate,
            slippage=self._config.slippage,
            state_dir=self._config.state_dir,
        )
        self._order_manager = OrderManager(new_config.db_path)
        self._performance_analyzer = PerformanceAnalyzer(new_config.db_path)
        self._risk_manager = RiskManager(new_config, new_config.db_path)

        # 初始化投资组合
        self._portfolio = self._init_portfolio()
        self._strategy.init(self._portfolio)

    def _init_portfolio(self) -> Portfolio:
        """初始化或恢复投资组合"""
        state = self._state_mgr.load()
        if state:
            portfolio = Portfolio(
                cash=state["cash"],
                positions=state["positions"],
                avg_prices=state.get("avg_prices", {}),
                entry_dates=state.get("entry_dates", {}),
                strategies=state.get("strategies", {}),
            )
            logger.info(f"恢复投资组合: 现金={portfolio.cash:,.0f}, 持仓={portfolio.positions}")
            return portfolio
        return Portfolio(cash=self._config.initial_cash)

    @property
    def portfolio(self) -> Portfolio:
        return self._portfolio

    @property
    def trade_log(self) -> PaperTradeLog:
        return self._trade_log

    @property
    def order_manager(self) -> OrderManager:
        return self._order_manager

    @property
    def performance_analyzer(self) -> PerformanceAnalyzer:
        return self._performance_analyzer

    @property
    def risk_manager(self) -> RiskManager:
        return self._risk_manager

    def run_once(self) -> dict:
        """执行一轮行情检查和策略推送

        Returns:
            {quotes: {...}, equity: float, positions: {...}, trades: [...]}
        """
        # 1. 从 QuoteService 获取实时行情（后台服务持续更新）
        quotes = self._quote_service.get_all_quotes()
        if not quotes:
            return {"error": "无行情数据"}

        now = datetime.now().date()
        prices = {c: q.price for c, q in quotes.items()}
        equity = self._portfolio.get_total_equity(prices)

        # 2. 风控：止损检查
        if self._stoploss_mgr:
            self._stoploss_mgr.update_equity(now, equity)
            self._check_stoploss(quotes, equity)

        # 3. 推送行情给策略
        for code, quote in quotes.items():
            bar = Bar(
                code=code,
                date=now,
                open=quote.open,
                high=quote.high,
                low=quote.low,
                close=quote.price,
                volume=quote.volume,
                amount=quote.amount,
            )
            self._strategy.on_bar(bar)

        # 4. 撮合挂单
        new_trades = self._match_orders(quotes)

        # 5. 风控：仓位过滤
        if self._position_mgr:
            self._filter_orders(prices)

        # 6. 记录交易
        for trade in new_trades:
            equity = self._portfolio.get_total_equity(prices)
            self._trade_log.record(trade, equity)

        # 7. 保存状态
        self._state_mgr.save(self._portfolio)

        equity = self._portfolio.get_total_equity(prices)
        return {
            "time": datetime.now().isoformat(),
            "equity": round(equity, 2),
            "cash": round(self._portfolio.cash, 2),
            "positions": dict(self._portfolio.positions),
            "prices": prices,
            "new_trades": len(new_trades),
        }

    def run_loop(self):
        """持续运行模拟盘"""
        self._running = True
        logger.info(f"模拟盘启动: 标的={self._codes}, 间隔={self._config.interval_seconds}秒")

        consecutive_errors = 0
        MAX_CONSECUTIVE_ERRORS = 10

        while self._running:
            try:
                result = self.run_once()
                consecutive_errors = 0  # 成功后重置
                if "error" not in result:
                    logger.info(
                        f"收益={result['equity']:,.0f} "
                        f"现金={result['cash']:,.0f} "
                        f"持仓={len(result['positions'])}只 "
                        f"新成交={result['new_trades']}"
                    )
            except KeyboardInterrupt:
                logger.info("收到停止信号")
                break
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"模拟盘异常 ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}): {e}")
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    logger.critical("连续失败过多，模拟盘自动停止")
                    break

            time.sleep(self._config.interval_seconds)

        # 退出前保存状态
        self._state_mgr.save(self._portfolio)
        logger.info("模拟盘已停止")

    def stop(self):
        """停止模拟盘"""
        self._running = False

    def _check_stoploss(self, quotes: dict[str, QuoteData], equity: float):
        """止损检查"""
        for code, vol in list(self._portfolio.positions.items()):
            if vol <= 0:
                continue
            quote = quotes.get(code)
            if quote is None:
                continue

            entry_price = self._portfolio.avg_prices.get(code, 0)
            signals = self._stoploss_mgr.check_all(
                code=code,
                entry_price=entry_price,
                current_price=quote.price,
                equity=equity,
            )

            for signal in signals:
                if signal.code == "*":
                    for c in list(self._portfolio.positions.keys()):
                        if self._portfolio.positions[c] > 0:
                            self._submit_sell(c, quotes.get(c, quote).price, self._portfolio.positions[c])
                    logger.warning(f"[止损] {signal.reason}")
                    return
                elif signal.action == "sell" and vol > 0:
                    self._submit_sell(code, quote.price, vol)
                    self._stoploss_mgr.clear_trailing_high(code)
                    logger.warning(f"[止损] {signal.reason}")
                    break

    def _submit_sell(self, code: str, price: float, volume: int):
        """直接提交卖出（止损用）"""
        self._strategy.sell(code, price, volume)

    def _match_orders(self, quotes: dict[str, QuoteData]) -> list[Trade]:
        """撮合挂单"""
        pending = self._strategy.get_pending_orders()
        trades = []

        for order in pending:
            quote = quotes.get(order.code)
            if quote is None:
                order.status = "cancelled"
                continue

            if order.direction == Direction.LONG:
                fill_price = quote.price * (1 + self._config.slippage)
                cost = fill_price * order.volume
                commission = max(cost * self._config.commission_rate, 5.0)

                if self._portfolio.cash >= cost + commission:
                    self._portfolio.cash -= cost + commission
                    old_vol = self._portfolio.positions.get(order.code, 0)
                    old_avg = self._portfolio.avg_prices.get(order.code, 0.0)
                    new_vol = old_vol + order.volume
                    new_avg = (old_avg * old_vol + fill_price * order.volume) / new_vol
                    self._portfolio.positions[order.code] = new_vol
                    self._portfolio.avg_prices[order.code] = new_avg
                    order.status = "filled"

                    # 记录建仓日期和变动类型
                    if old_vol == 0:
                        self._portfolio.entry_dates[order.code] = datetime.now().strftime("%Y-%m-%d")
                        action_type = "new"
                    else:
                        action_type = "add"
                    self._portfolio.strategies[order.code] = getattr(self._strategy, 'name', self._strategy.__class__.__name__)

                    trade = Trade(
                        code=order.code,
                        direction=order.direction,
                        price=fill_price,
                        volume=order.volume,
                        order_id=order.order_id,
                        datetime=datetime.now().date(),
                    )
                    self._strategy.record_trade(trade)
                    trades.append(trade)
                else:
                    order.status = "cancelled"
                    logger.warning(f"[{order.code}] 资金不足，取消买入")

            elif order.direction == Direction.SHORT:
                current_pos = self._portfolio.positions.get(order.code, 0)
                actual_vol = min(order.volume, current_pos)
                if actual_vol <= 0:
                    order.status = "cancelled"
                    continue

                fill_price = quote.price * (1 - self._config.slippage)
                revenue = fill_price * actual_vol
                commission = max(revenue * self._config.commission_rate, 5.0)
                stamp_tax = revenue * self._config.stamp_tax_rate

                entry_price = self._portfolio.avg_prices.get(order.code, fill_price)

                self._portfolio.cash += revenue - commission - stamp_tax
                self._portfolio.positions[order.code] = current_pos - actual_vol
                if self._portfolio.positions[order.code] == 0:
                    del self._portfolio.positions[order.code]
                    del self._portfolio.avg_prices[order.code]
                    self._portfolio.entry_dates.pop(order.code, None)
                    self._portfolio.strategies.pop(order.code, None)

                order.status = "filled" if actual_vol >= order.volume else "partial"

                trade = Trade(
                    code=order.code,
                    direction=order.direction,
                    price=fill_price,
                    volume=actual_vol,
                    order_id=order.order_id,
                    datetime=datetime.now().date(),
                    entry_price=entry_price,
                )
                self._strategy.record_trade(trade)
                trades.append(trade)

        return trades

    def _filter_orders(self, prices: dict[str, float]):
        """仓位过滤"""
        pending = self._strategy.get_pending_orders()
        kept = []
        for order in pending:
            if order.direction == Direction.LONG:
                passed, reason = self._position_mgr.check_buy(
                    code=order.code,
                    price=order.price,
                    volume=order.volume,
                    portfolio=self._portfolio,
                    prices=prices,
                )
                if not passed:
                    order.status = "cancelled"
                    logger.info(f"[仓位] 拒绝买入 {order.code}: {reason}")
                    continue
            kept.append(order)
        self._strategy._pending_orders = kept
