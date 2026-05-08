"""模拟盘引擎"""
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from config.settings import LOG_DIR, PROJECT_ROOT
from config.datetime_utils import now_beijing, now_beijing_iso, now_beijing_str, today_beijing, today_beijing_compact


def _is_trading_hours() -> bool:
    """判断当前是否在 A 股交易时段（周一至周五 9:30-11:30, 13:00-15:00）"""
    now = now_beijing()
    if now.weekday() >= 5:  # 周六日
        return False
    t = now.hour * 60 + now.minute
    return (570 <= t <= 690) or (780 <= t <= 900)  # 9:30-11:30, 13:00-15:00
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
        self._log_file = self._dir / f"trades_{now_beijing():%Y%m%d}.jsonl"
        self._trades: list[dict] = []

    def record(self, trade: Trade, equity: float):
        """记录成交"""
        entry = {
            "time": now_beijing_iso(),
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

    def save(self, portfolio: Portfolio, today_bought: Optional[dict] = None, today_date: str = ""):
        """保存投资组合状态"""
        state = {
            "saved_at": now_beijing_iso(),
            "cash": portfolio.cash,
            "positions": dict(portfolio.positions),
            "avg_prices": {k: round(v, 4) for k, v in portfolio.avg_prices.items()},
            "trade_count": len(portfolio.trades),
            "entry_dates": dict(portfolio.entry_dates),
            "strategies": dict(portfolio.strategies),
            "today_bought": dict(today_bought) if today_bought else {},
            "today_date": today_date,
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

        # T+1 限制：记录当日买入的股票数量
        self._today_bought: dict[str, int] = {}
        self._today_date: str = ""
        self.strategy_name: str = ""  # 由外部设置，用于 portfolio.strategies 记录

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
            # 恢复 T+1 状态
            saved_date = state.get("today_date", "")
            today_str = now_beijing().strftime("%Y-%m-%d")
            if saved_date == today_str:
                self._today_bought = dict(state.get("today_bought", {}))
                self._today_date = saved_date
                logger.info(f"恢复 T+1 状态: {self._today_bought}")
            else:
                self._today_bought = {}
                self._today_date = ""
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

        now = now_beijing().date()
        today_str = now.strftime("%Y-%m-%d")
        if today_str != self._today_date:
            self._today_bought.clear()
            self._today_date = today_str
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

        # 4. 风控：仓位过滤（必须在撮合前执行）
        if self._position_mgr:
            self._filter_orders(prices)

        # 5. 加载 DB 中的手动订单到引擎队列
        self._load_db_orders()

        # 6. 撮合挂单
        new_trades = self._match_orders(quotes)

        # 7. 记录交易
        for trade in new_trades:
            equity = self._portfolio.get_total_equity(prices)
            self._trade_log.record(trade, equity)

        # 8. 同步状态到 DB（持仓 + 交易 + 订单）
        self._sync_to_db(new_trades)

        # 9. 保存状态文件（含 T+1 数据）
        self._state_mgr.save(self._portfolio, self._today_bought, self._today_date)

        equity = self._portfolio.get_total_equity(prices)
        return {
            "time": now_beijing_iso(),
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

        _non_trading_logged = False

        while self._running:
            # 非交易时段跳过（周末、午休、盘前盘后）
            if not _is_trading_hours():
                if not _non_trading_logged:
                    logger.info("非交易时段，模拟盘等待中（交易时段: 周一至周五 9:30-11:30, 13:00-15:00）")
                    _non_trading_logged = True
                time.sleep(self._config.interval_seconds)
                continue
            _non_trading_logged = False

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

        # 退出前保存状态（含 T+1 数据）
        self._state_mgr.save(self._portfolio, self._today_bought, self._today_date)
        logger.info("模拟盘已停止")

    def stop(self):
        """停止模拟盘"""
        self._running = False

    def _load_position_stop_prices(self) -> dict[str, dict]:
        """从 DB 加载每个持仓的止损止盈价"""
        result = {}
        try:
            import sqlite3
            conn = sqlite3.connect(self._order_manager.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT code, stop_loss_price, take_profit_price FROM paper_positions "
                "WHERE stop_loss_price IS NOT NULL OR take_profit_price IS NOT NULL"
            )
            for row in cursor.fetchall():
                result[row["code"]] = {
                    "stop_loss": row["stop_loss_price"],
                    "take_profit": row["take_profit_price"],
                }
            conn.close()
        except Exception as e:
            logger.debug(f"加载止损止盈价失败: {e}")
        return result

    def _check_stoploss(self, quotes: dict[str, QuoteData], equity: float):
        """止损检查：优先检查 DB 中的止损止盈价，再检查百分比规则"""
        # 加载 DB 中的止损止盈价（每轮都读，确保实时更新）
        db_stop_prices = self._load_position_stop_prices()

        for code, vol in list(self._portfolio.positions.items()):
            if vol <= 0:
                continue
            quote = quotes.get(code)
            if quote is None:
                continue

            entry_price = self._portfolio.avg_prices.get(code, 0)

            # 1. 优先检查 DB 中设置的止损止盈价
            stop_cfg = db_stop_prices.get(code)
            if stop_cfg:
                if stop_cfg["stop_loss"] and quote.price <= stop_cfg["stop_loss"]:
                    self._submit_sell(code, quote.price, vol)
                    logger.warning(
                        f"[止损] {code} 触发止损价 {stop_cfg['stop_loss']:.2f}，"
                        f"当前 {quote.price:.2f}"
                    )
                    continue
                if stop_cfg["take_profit"] and quote.price >= stop_cfg["take_profit"]:
                    self._submit_sell(code, quote.price, vol)
                    logger.warning(
                        f"[止盈] {code} 触发止盈价 {stop_cfg['take_profit']:.2f}，"
                        f"当前 {quote.price:.2f}"
                    )
                    continue

            # 2. 回退到百分比规则
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
                if hasattr(order, '_db_order_id'):
                    self._update_db_order_status(order._db_order_id, "cancelled")
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
                        self._portfolio.entry_dates[order.code] = now_beijing().strftime("%Y-%m-%d")
                        action_type = "new"
                    else:
                        action_type = "add"
                    self._portfolio.strategies[order.code] = self.strategy_name or self._strategy.__class__.__name__

                    trade = Trade(
                        code=order.code,
                        direction=order.direction,
                        price=fill_price,
                        volume=order.volume,
                        order_id=order.order_id,
                        datetime=now_beijing().date(),
                    )
                    if hasattr(order, '_db_order_id'):
                        trade._db_order_id = order._db_order_id
                    self._strategy.record_trade(trade)
                    trades.append(trade)
                    # T+1：记录当日买入量
                    self._today_bought[order.code] = self._today_bought.get(order.code, 0) + order.volume
                else:
                    order.status = "cancelled"
                    if hasattr(order, '_db_order_id'):
                        self._update_db_order_status(order._db_order_id, "cancelled")
                    logger.warning(f"[{order.code}] 资金不足，取消买入")

            elif order.direction == Direction.SHORT:
                current_pos = self._portfolio.positions.get(order.code, 0)
                # T+1：扣除当日买入的不可卖数量
                today_bought = self._today_bought.get(order.code, 0)
                sellable = max(0, current_pos - today_bought)
                actual_vol = min(order.volume, sellable)
                if actual_vol <= 0:
                    order.status = "cancelled"
                    if hasattr(order, '_db_order_id'):
                        self._update_db_order_status(order._db_order_id, "cancelled")
                    if current_pos > 0 and today_bought > 0:
                        logger.info(f"[{order.code}] T+1限制：持仓{current_pos}股，今日买入{today_bought}股，可卖0股")
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
                    datetime=now_beijing().date(),
                    entry_price=entry_price,
                )
                if hasattr(order, '_db_order_id'):
                    trade._db_order_id = order._db_order_id
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
                    if hasattr(order, '_db_order_id'):
                        self._update_db_order_status(order._db_order_id, "cancelled")
                    logger.info(f"[仓位] 拒绝买入 {order.code}: {reason}")
                    continue
            kept.append(order)
        self._strategy._pending_orders = kept

    def _update_db_order_status(self, db_order_id: str, status: str):
        """更新 DB 中订单状态"""
        try:
            import sqlite3
            conn = sqlite3.connect(self._order_manager.db_path)
            conn.execute(
                "UPDATE paper_orders SET status=?, updated_at=? WHERE order_id=?",
                (status, now_beijing_iso(), db_order_id),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"更新 DB 订单状态失败: {e}")

    def _load_db_orders(self):
        """从 DB 加载手动提交的待处理订单到引擎队列"""
        try:
            import sqlite3
            from engine.models import Direction as ModelDirection
            conn = sqlite3.connect(self._order_manager.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM paper_orders WHERE status = 'pending' ORDER BY created_at ASC"
            )
            rows = cursor.fetchall()
            conn.close()

            for row in rows:
                # 转换为引擎内部 Order
                direction = Direction.LONG if row["direction"] == "long" else Direction.SHORT
                order = Order(
                    code=row["code"],
                    direction=direction,
                    price=row["price"] or 0.0,
                    volume=row["volume"],
                    order_id=0,  # 引擎内部 ID
                )
                # 附带 DB order_id 用于后续状态更新
                order._db_order_id = row["order_id"]
                self._strategy._pending_orders.append(order)

            if rows:
                logger.debug(f"从 DB 加载 {len(rows)} 笔手动订单")
        except Exception as e:
            logger.debug(f"加载 DB 订单失败: {e}")

    def _sync_to_db(self, new_trades: list[Trade]):
        """同步引擎状态到 DB（持仓 + 交易 + 订单状态）"""
        try:
            import sqlite3
            conn = sqlite3.connect(self._order_manager.db_path)
            now_str = now_beijing_iso()

            # 1. 同步持仓到 paper_positions 表
            # 先获取现有持仓的止损止盈价（避免覆盖用户设置）
            existing = {}
            cursor = conn.execute("SELECT code, stop_loss_price, take_profit_price, max_position_pct FROM paper_positions")
            for row in cursor.fetchall():
                existing[row["code"]] = {
                    "stop_loss": row["stop_loss_price"],
                    "take_profit": row["take_profit_price"],
                    "max_pct": row["max_position_pct"],
                }

            # 删除不再持有的持仓
            held_codes = set(self._portfolio.positions.keys())
            if held_codes:
                placeholders = ",".join("?" * len(held_codes))
                conn.execute(
                    f"DELETE FROM paper_positions WHERE code NOT IN ({placeholders})",
                    list(held_codes),
                )
            else:
                conn.execute("DELETE FROM paper_positions")

            # 获取当前价格
            quotes = self._quote_service.get_all_quotes()
            prices = {c: q.price for c, q in quotes.items()} if quotes else {}

            # 更新/插入持仓
            for code, vol in self._portfolio.positions.items():
                if vol <= 0:
                    continue
                avg_price = self._portfolio.avg_prices.get(code, 0)
                current_price = prices.get(code, avg_price)
                market_value = current_price * vol
                unrealized_pnl = (current_price - avg_price) * vol
                unrealized_pnl_pct = (current_price / avg_price - 1) if avg_price > 0 else 0

                prev = existing.get(code, {})
                stop_loss = prev.get("stop_loss")
                take_profit = prev.get("take_profit")
                max_pct = prev.get("max_pct", 0.3)

                conn.execute(
                    """INSERT INTO paper_positions
                    (code, volume, avg_price, current_price, market_value,
                     unrealized_pnl, unrealized_pnl_pct, stop_loss_price, take_profit_price,
                     max_position_pct, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(code) DO UPDATE SET
                        volume=excluded.volume, avg_price=excluded.avg_price,
                        current_price=excluded.current_price, market_value=excluded.market_value,
                        unrealized_pnl=excluded.unrealized_pnl, unrealized_pnl_pct=excluded.unrealized_pnl_pct,
                        stop_loss_price=excluded.stop_loss_price, take_profit_price=excluded.take_profit_price,
                        max_position_pct=excluded.max_position_pct, updated_at=excluded.updated_at""",
                    (code, vol, round(avg_price, 4), round(current_price, 4),
                     round(market_value, 2), round(unrealized_pnl, 2),
                     round(unrealized_pnl_pct, 4), stop_loss, take_profit,
                     max_pct, now_str),
                )

            # 2. 同步新交易到 paper_trades 表
            for trade in new_trades:
                entry_price = trade.entry_price or self._portfolio.avg_prices.get(trade.code, 0)
                profit = 0.0
                profit_pct = 0.0
                if trade.direction == Direction.SHORT and entry_price > 0:
                    profit = (trade.price - entry_price) * trade.volume
                    profit_pct = trade.price / entry_price - 1
                elif trade.direction == Direction.LONG and entry_price > 0:
                    # 买入时 profit 为 0（尚未实现盈亏）
                    pass

                commission = max(trade.price * trade.volume * self._config.commission_rate, 5.0)
                stamp_tax = trade.price * trade.volume * self._config.stamp_tax_rate if trade.direction == Direction.SHORT else 0
                equity = self._portfolio.get_total_equity(prices)

                trade_id = f"TRD-{trade.trade_id:06d}"
                db_order_id = getattr(trade, '_db_order_id', None) or f"ORD-AUTO-{trade.order_id:06d}"

                conn.execute(
                    """INSERT OR IGNORE INTO paper_trades
                    (trade_id, order_id, code, direction, price, volume,
                     entry_price, profit, profit_pct, commission, stamp_tax,
                     equity_after, strategy_name, signal_reason, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (trade_id, db_order_id, trade.code, trade.direction.value,
                     round(trade.price, 4), trade.volume, round(entry_price, 4),
                     round(profit, 2), round(profit_pct, 4),
                     round(commission, 2), round(stamp_tax, 2),
                     round(equity, 2), self.strategy_name, "",
                     now_str),
                )

                # 更新对应的 DB 订单状态为 filled
                if hasattr(trade, '_db_order_id') and trade._db_order_id:
                    conn.execute(
                        "UPDATE paper_orders SET status='filled', filled_price=?, filled_volume=?, updated_at=? WHERE order_id=?",
                        (round(trade.price, 4), trade.volume, now_str, trade._db_order_id),
                    )

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"同步到 DB 失败: {e}")
