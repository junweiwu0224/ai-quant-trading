"""订单管理器"""
import uuid
from datetime import datetime
from typing import List, Optional

from loguru import logger

from config.settings import PROJECT_ROOT
from config.datetime_utils import now_beijing, now_beijing_iso, now_beijing_str, today_beijing, today_beijing_compact
from engine.models import (
    Direction, OrderStatus, OrderType,
    PaperConfig, PaperOrder, PaperTrade
)
from utils.db import get_connection

DEFAULT_DB_PATH = str(PROJECT_ROOT / "data" / "paper_trading.db")


class OrderManager:
    """订单管理器"""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """初始化数据库连接"""
        from engine.migrate import init_database
        init_database(self.db_path)

    def _get_conn(self):
        """获取数据库连接（已配置 WAL + busy_timeout）"""
        return get_connection(self.db_path)

    def create_order(
        self,
        code: str,
        direction: Direction,
        order_type: OrderType,
        volume: int,
        price: Optional[float] = None,
        strategy_name: Optional[str] = None,
        signal_reason: Optional[str] = None,
    ) -> PaperOrder:
        """创建订单"""
        order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"

        # 验证订单参数
        self._validate_order(code, direction, order_type, volume, price)

        order = PaperOrder(
            order_id=order_id,
            code=code,
            direction=direction,
            order_type=order_type,
            price=price,
            volume=volume,
            status=OrderStatus.PENDING,
            strategy_name=strategy_name,
            signal_reason=signal_reason,
        )

        # 保存到数据库
        self._save_order(order)

        logger.info(
            f"[订单创建] {order_id} {direction.value} {code} "
            f"类型={order_type.value} 价格={price} 数量={volume}"
        )

        return order

    def cancel_order(self, order_id: str) -> PaperOrder:
        """撤销订单（原子操作，防止 TOCTOU 竞态）"""
        conn = self._get_conn()
        try:
            # 在单个事务中完成检查+更新
            cursor = conn.execute(
                "SELECT * FROM paper_orders WHERE order_id = ? AND status = 'pending'",
                (order_id,)
            )
            row = cursor.fetchone()
            if not row:
                # 检查订单是否存在
                cursor2 = conn.execute(
                    "SELECT status FROM paper_orders WHERE order_id = ?",
                    (order_id,)
                )
                status_row = cursor2.fetchone()
                if not status_row:
                    raise ValueError(f"订单不存在: {order_id}")
                raise ValueError(f"订单状态不允许撤销: {status_row['status']}")

            conn.execute(
                "UPDATE paper_orders SET status = 'cancelled', updated_at = ? WHERE order_id = ?",
                (now_beijing_iso(), order_id)
            )
            conn.commit()

            order = self._row_to_order(row)
            order.status = OrderStatus.CANCELLED
            logger.info(f"[订单撤销] {order_id}")
            return order
        finally:
            conn.close()

    def get_order(self, order_id: str) -> Optional[PaperOrder]:
        """获取订单详情"""
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "SELECT * FROM paper_orders WHERE order_id = ?",
                (order_id,)
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_order(row)
            return None
        finally:
            conn.close()

    def get_orders(
        self,
        status: Optional[str] = None,
        code: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        """获取订单列表"""
        conn = self._get_conn()
        try:
            conditions = []
            params = []

            if status:
                conditions.append("status = ?")
                params.append(status)

            if code:
                conditions.append("code = ?")
                params.append(code)

            if start_date:
                conditions.append("created_at >= ?")
                params.append(start_date.isoformat())

            if end_date:
                conditions.append("created_at <= ?")
                params.append(end_date.isoformat())

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            # 获取总数
            cursor = conn.execute(
                f"SELECT COUNT(*) FROM paper_orders WHERE {where_clause}",
                params
            )
            total = cursor.fetchone()[0]

            # 获取分页数据
            offset = (page - 1) * page_size
            cursor = conn.execute(
                f"SELECT * FROM paper_orders WHERE {where_clause} "
                f"ORDER BY created_at DESC LIMIT ? OFFSET ?",
                params + [page_size, offset]
            )
            rows = cursor.fetchall()

            orders = [self._row_to_order(row) for row in rows]

            return {
                "items": [o.to_dict() for o in orders],
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size,
            }
        finally:
            conn.close()

    def get_pending_orders(self, code: Optional[str] = None) -> List[PaperOrder]:
        """获取待撮合订单"""
        conn = self._get_conn()
        try:
            if code:
                cursor = conn.execute(
                    "SELECT * FROM paper_orders WHERE status = 'pending' AND code = ? "
                    "ORDER BY created_at ASC",
                    (code,)
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM paper_orders WHERE status = 'pending' "
                    "ORDER BY created_at ASC"
                )

            rows = cursor.fetchall()
            return [self._row_to_order(row) for row in rows]
        finally:
            conn.close()

    def match_orders(self, quotes: dict, config: PaperConfig) -> List[PaperTrade]:
        """撮合订单

        注意: 此方法未被 PaperEngine 主流程调用。
        PaperEngine 使用内置的 _match_orders() 进行撮合。
        保留此方法供未来扩展或独立测试使用。
        """
        pending = self.get_pending_orders()
        trades = []

        for order in pending:
            quote = quotes.get(order.code)
            if not quote:
                continue

            # 检查是否触发撮合条件
            if self._should_match(order, quote):
                trade = self._execute_order(order, quote, config)
                if trade:
                    trades.append(trade)

        return trades

    def _validate_order(
        self,
        code: str,
        direction: Direction,
        order_type: OrderType,
        volume: int,
        price: Optional[float],
    ):
        """验证订单参数"""
        if not code:
            raise ValueError("股票代码不能为空")

        if volume <= 0:
            raise ValueError("数量必须大于0")

        if volume % 100 != 0:
            raise ValueError("数量必须是100的整数倍")

        if order_type in [OrderType.LIMIT, OrderType.STOP_LOSS, OrderType.TAKE_PROFIT]:
            if price is None or price <= 0:
                raise ValueError(f"{order_type.value}单必须指定有效价格")

    def _should_match(self, order: PaperOrder, quote) -> bool:
        """判断是否应该撮合"""
        if order.order_type == OrderType.MARKET:
            return True
        elif order.order_type == OrderType.LIMIT:
            if order.direction == Direction.LONG:
                return quote.price <= order.price
            else:
                return quote.price >= order.price
        elif order.order_type == OrderType.STOP_LOSS:
            return quote.price <= order.price
        elif order.order_type == OrderType.TAKE_PROFIT:
            return quote.price >= order.price
        return False

    def _execute_order(self, order: PaperOrder, quote, config: PaperConfig) -> Optional[PaperTrade]:
        """执行订单"""
        try:
            # 计算成交价格（含滑点）
            if order.direction == Direction.LONG:
                fill_price = quote.price * (1 + config.slippage)
            else:
                fill_price = quote.price * (1 - config.slippage)

            # 计算费用
            volume = order.volume
            amount = fill_price * volume
            commission = max(amount * config.commission_rate, 5.0)
            stamp_tax = amount * config.stamp_tax_rate if order.direction == Direction.SHORT else 0

            # 更新订单状态
            order.filled_price = fill_price
            order.filled_volume = volume
            order.commission = commission
            order.stamp_tax = stamp_tax
            order.slippage = config.slippage
            order.status = OrderStatus.FILLED
            order.updated_at = now_beijing()

            self._update_order(order)

            # 创建交易记录
            trade = PaperTrade(
                trade_id=f"TRD-{uuid.uuid4().hex[:8].upper()}",
                order_id=order.order_id,
                code=order.code,
                direction=order.direction,
                price=fill_price,
                volume=volume,
                commission=commission,
                stamp_tax=stamp_tax,
                strategy_name=order.strategy_name,
                signal_reason=order.signal_reason,
            )

            self._save_trade(trade)

            logger.info(
                f"[订单成交] {order.order_id} {order.direction.value} {order.code} "
                f"价格={fill_price:.2f} 数量={volume} 费用={commission + stamp_tax:.2f}"
            )

            return trade

        except Exception as e:
            logger.error(f"订单执行失败: {e}")
            order.status = OrderStatus.REJECTED
            order.updated_at = now_beijing()
            self._update_order(order)
            return None

    def _save_order(self, order: PaperOrder):
        """保存订单到数据库"""
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO paper_orders
                (order_id, code, direction, order_type, price, volume, status,
                 filled_price, filled_volume, commission, stamp_tax, slippage,
                 strategy_name, signal_reason, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    order.order_id, order.code, order.direction.value,
                    order.order_type.value, order.price, order.volume,
                    order.status.value, order.filled_price, order.filled_volume,
                    order.commission, order.stamp_tax, order.slippage,
                    order.strategy_name, order.signal_reason,
                    order.created_at.isoformat(), order.updated_at.isoformat(),
                )
            )
            conn.commit()
        except Exception as e:
            logger.error(f"保存订单失败: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

    def _update_order(self, order: PaperOrder):
        """更新订单状态"""
        conn = self._get_conn()
        try:
            conn.execute(
                """UPDATE paper_orders SET
                status = ?, filled_price = ?, filled_volume = ?,
                commission = ?, stamp_tax = ?, slippage = ?, updated_at = ?
                WHERE order_id = ?""",
                (
                    order.status.value, order.filled_price, order.filled_volume,
                    order.commission, order.stamp_tax, order.slippage,
                    order.updated_at.isoformat(), order.order_id,
                )
            )
            conn.commit()
        except Exception as e:
            logger.error(f"更新订单失败: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

    def _save_trade(self, trade: PaperTrade):
        """保存交易记录"""
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO paper_trades
                (trade_id, order_id, code, direction, price, volume,
                 entry_price, profit, profit_pct, commission, stamp_tax,
                 equity_after, strategy_name, signal_reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    trade.trade_id, trade.order_id, trade.code,
                    trade.direction.value, trade.price, trade.volume,
                    trade.entry_price, trade.profit, trade.profit_pct,
                    trade.commission, trade.stamp_tax, trade.equity_after,
                    trade.strategy_name, trade.signal_reason,
                    trade.created_at.isoformat(),
                )
            )
            conn.commit()
        except Exception as e:
            logger.error(f"保存交易记录失败: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

    def _row_to_order(self, row) -> PaperOrder:
        """将数据库行转换为订单对象"""
        return PaperOrder(
            order_id=row["order_id"],
            code=row["code"],
            direction=Direction.from_value(row["direction"]),
            order_type=OrderType(row["order_type"]),
            price=row["price"],
            volume=row["volume"],
            status=OrderStatus(row["status"]),
            filled_price=row["filled_price"],
            filled_volume=row["filled_volume"],
            commission=row["commission"],
            stamp_tax=row["stamp_tax"],
            slippage=row["slippage"],
            strategy_name=row["strategy_name"],
            signal_reason=row["signal_reason"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
        )
