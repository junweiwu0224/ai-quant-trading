"""实盘交易引擎"""
import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from config.settings import LOG_DIR
from data.collector.quote_service import QuoteData, get_quote_service
from engine.broker import BrokerGateway, OrderSide, OrderStatus, SimulatedBroker
from engine.paper_engine import PaperTradeLog, PaperConfig
from risk.position import PositionManager
from risk.stoploss import StopLossManager
from strategy.base import Bar, BaseStrategy, Direction, Portfolio


@dataclass
class LiveConfig:
    """实盘配置"""
    interval_seconds: int = 30
    state_dir: str = str(LOG_DIR / "live")
    enable_risk: bool = True
    dry_run: bool = True  # True=模拟盘模式，False=实盘


class LivePortfolioAdapter:
    """将 BrokerGateway 接口适配为 Portfolio"""

    def __init__(self, broker: BrokerGateway):
        self._broker = broker
        self._trades: list = []
        self._orders: list = []
        self._equity_curve: list = []

    @property
    def trades(self) -> list:
        return self._trades

    @property
    def orders(self) -> list:
        return self._orders

    @property
    def equity_curve(self) -> list:
        return self._equity_curve

    def get_account_snapshot(self) -> dict:
        account = self._broker.get_account()
        positions = self._broker.get_positions()
        return {
            "cash": account.available,
            "total_equity": account.total_equity,
            "market_value": account.market_value,
            "positions": {p.code: p.volume for p in positions},
            "avg_prices": {p.code: p.avg_price for p in positions},
        }

    def record_equity(self, date, equity: float):
        self._equity_curve.append({"date": date, "equity": equity})


class LiveTradingEngine:
    """实盘交易引擎"""

    def __init__(
        self,
        strategy: BaseStrategy,
        codes: list[str],
        broker: Optional[BrokerGateway] = None,
        config: Optional[LiveConfig] = None,
    ):
        self._strategy = strategy
        self._codes = codes
        self._config = config or LiveConfig()
        self._quote_service = get_quote_service()
        self._quote_service.subscribe(codes)
        self._trade_log = PaperTradeLog(self._config.state_dir)
        self._running = False

        # 券商网关
        if broker:
            self._broker = broker
        elif self._config.dry_run:
            self._broker = SimulatedBroker()
        else:
            raise ValueError("实盘模式必须提供 broker 实例")

        # 风控
        self._position_mgr = PositionManager() if self._config.enable_risk else None
        self._stoploss_mgr = StopLossManager() if self._config.enable_risk else None

        # 适配器
        self._adapter = LivePortfolioAdapter(self._broker)

        # 创建虚拟 Portfolio 供策略使用
        account = self._broker.get_account()
        self._portfolio = Portfolio(cash=account.available)
        self._sync_positions()
        self._strategy.init(self._portfolio)

    def _sync_positions(self):
        """从券商同步持仓到 Portfolio"""
        positions = self._broker.get_positions()
        self._portfolio.positions = {p.code: p.volume for p in positions}
        self._portfolio.avg_prices = {p.code: p.avg_price for p in positions}

    @property
    def broker(self) -> BrokerGateway:
        return self._broker

    def run_once(self) -> dict:
        """执行一轮"""
        if not self._broker.is_connected():
            self._broker.connect()

        # 1. 从 QuoteService 获取实时行情
        quotes = self._quote_service.get_all_quotes()
        if not quotes:
            return {"error": "无行情数据"}

        now = datetime.now().date()
        prices = {c: q.price for c, q in quotes.items()}

        # 设置模拟价格
        if isinstance(self._broker, SimulatedBroker):
            for c, q in quotes.items():
                self._broker.set_price(c, q.price)

        # 2. 同步账户状态
        self._sync_positions()
        self._portfolio.cash = self._broker.get_account().available

        equity = self._broker.get_account().total_equity
        self._adapter.record_equity(now, equity)

        # 3. 风控：止损检查
        if self._stoploss_mgr:
            self._stoploss_mgr.update_equity(now, equity)
            self._check_stoploss(quotes, equity)

        # 4. 推送行情给策略
        for code, quote in quotes.items():
            bar = Bar(
                code=code, date=now,
                open=quote.open, high=quote.high, low=quote.low,
                close=quote.price, volume=quote.volume, amount=quote.amount,
            )
            self._strategy.on_bar(bar)

        # 5. 执行策略挂单
        new_trades = self._execute_orders(quotes)

        # 6. 记录交易
        for trade in new_trades:
            self._trade_log.record(trade, equity)

        # 7. T+1 结算
        if isinstance(self._broker, SimulatedBroker):
            self._broker.settle_t1()

        account = self._broker.get_account()
        return {
            "time": datetime.now().isoformat(),
            "equity": round(account.total_equity, 2),
            "cash": round(account.available, 2),
            "market_value": round(account.market_value, 2),
            "positions": {p.code: p.volume for p in self._broker.get_positions()},
            "new_trades": len(new_trades),
        }

    def run_loop(self):
        """持续运行"""
        self._running = True
        if not self._broker.connect():
            logger.error("券商连接失败")
            return

        mode = "模拟盘" if self._config.dry_run else "实盘"
        logger.info(f"{mode}启动: 标的={self._codes}, 间隔={self._config.interval_seconds}秒")

        while self._running:
            try:
                result = self.run_once()
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
                logger.error(f"实盘异常: {e}")

            time.sleep(self._config.interval_seconds)

        self._broker.disconnect()
        logger.info("实盘已停止")

    def stop(self):
        self._running = False

    def _check_stoploss(self, quotes, equity: float):
        for code, vol in list(self._portfolio.positions.items()):
            if vol <= 0:
                continue
            quote = quotes.get(code)
            if quote is None:
                continue

            entry_price = self._portfolio.avg_prices.get(code, 0)
            signals = self._stoploss_mgr.check_all(
                code=code, entry_price=entry_price,
                current_price=quote.price, equity=equity,
            )

            for signal in signals:
                if signal.code == "*":
                    for c in list(self._portfolio.positions.keys()):
                        if self._portfolio.positions[c] > 0:
                            q = quotes.get(c)
                            if q:
                                self._submit_sell(c, q.price, self._portfolio.positions[c])
                    logger.warning(f"[止损] {signal.reason}")
                    return
                elif signal.action == "sell" and vol > 0:
                    self._submit_sell(code, quote.price, vol)
                    self._stoploss_mgr.clear_trailing_high(code)
                    logger.warning(f"[止损] {signal.reason}")
                    break

    def _submit_sell(self, code: str, price: float, volume: int):
        self._strategy.sell(code, price, volume)

    def _execute_orders(self, quotes) -> list:
        """通过券商网关执行策略挂单"""
        from strategy.base import Trade

        pending = self._strategy.get_pending_orders()
        trades = []

        for order in pending:
            quote = quotes.get(order.code)
            if quote is None:
                order.status = "cancelled"
                continue

            if order.direction == Direction.LONG:
                side = OrderSide.BUY
            elif order.direction == Direction.SHORT:
                side = OrderSide.SELL
            else:
                continue

            result = self._broker.place_order(
                code=order.code,
                side=side,
                price=quote.price,
                volume=order.volume,
            )

            if result.status == OrderStatus.FILLED:
                order.status = "filled"
                trade = Trade(
                    code=order.code,
                    direction=order.direction,
                    price=result.filled_price,
                    volume=result.filled_volume,
                    order_id=order.order_id,
                    datetime=datetime.now().date(),
                    entry_price=self._portfolio.avg_prices.get(order.code, 0),
                )
                self._strategy.record_trade(trade)
                trades.append(trade)
            elif result.status == OrderStatus.PARTIAL:
                order.status = "partial"
            else:
                order.status = "cancelled"
                logger.info(f"[{order.code}] 订单{result.status.value}: {result.message}")

        # 同步持仓
        self._sync_positions()
        self._portfolio.cash = self._broker.get_account().available

        return trades
