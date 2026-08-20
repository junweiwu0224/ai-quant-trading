"""订单管理器"""
import uuid
from datetime import datetime
from typing import List, Optional

from loguru import logger

from config.settings import PROJECT_ROOT
from config.datetime_utils import now_beijing, now_beijing_iso
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
        operation_id: Optional[str] = None,
    ) -> PaperOrder:
        """创建订单
        
        DEPRECATED: 此方法已废弃，不应直接调用。
        所有订单创建必须通过统一执行协议：
        - 手工订单: PaperCommandClient.enqueue_manual_order()
        - 条件单: PaperCommandClient.enqueue_manual_order() (from ConditionalOrderEngine)
        - 策略信号: PaperEngine._execute_pending_orders_v2() -> inline RiskGate -> PaperAdapter
        
        保留此方法仅用于向后兼容测试和遗留代码过渡。
        """
        raise NotImplementedError(
            "OrderManager.create_order() 已废弃。\n"
            "请使用统一执行协议：\n"
            "- 手工订单: PaperCommandClient.enqueue_manual_order()\n"
            "- 条件单: ConditionalOrderEngine._execute_rule() 自动调用 enqueue_manual_order()\n"
            "- 策略信号: PaperEngine._execute_pending_orders_v2() 内联执行"
        )

    def create_orders_in_transaction(
        self,
        conn,
        orders: list[PaperOrder],
        *,
        operation_id: Optional[str] = None,
        operation_request_hash: Optional[str] = None,
    ) -> list[PaperOrder]:
        """Persist paper orders on a caller-owned transaction."""

        if not orders:
            return []
        for order in orders:
            self._validate_order(order.code, order.direction, order.order_type, order.volume, order.price)
            conn.execute(
                """INSERT INTO paper_orders
                (order_id, code, direction, order_type, price, volume, status,
                 filled_price, filled_volume, commission, stamp_tax, slippage,
                 strategy_name, signal_reason, operation_id, operation_request_hash,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    order.order_id, order.code, order.direction.value,
                    order.order_type.value, order.price, order.volume,
                    order.status.value, order.filled_price, order.filled_volume,
                    order.commission, order.stamp_tax, order.slippage,
                    order.strategy_name, order.signal_reason, operation_id, operation_request_hash,
                    order.created_at.isoformat(), order.updated_at.isoformat(),
                ),
            )
        return orders

    def create_orders_idempotently(
        self,
        orders: list[PaperOrder],
        *,
        operation_id: str,
        operation_request_hash: Optional[str] = None,
    ) -> list[PaperOrder]:
        """Create or recover a paper-order batch by its durable operation id.

        The paper database is deliberately a separate adapter from Agentic DB.
        This method is the recovery seam for the case where paper orders commit
        first and the Agentic execution projection has to be repaired later.
        """

        operation_id = str(operation_id or "").strip()
        if not operation_id:
            raise ValueError("operation_id is required")
        conn = self._get_conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                "SELECT * FROM paper_orders WHERE operation_id = ? ORDER BY created_at ASC, order_id ASC",
                (operation_id,),
            ).fetchall()
            if rows:
                if operation_request_hash:
                    for row in rows:
                        stored_hash = row["operation_request_hash"]
                        if stored_hash and stored_hash != operation_request_hash:
                            raise ValueError("operation_id was already used for different paper-order facts")
                return [self._row_to_order(row) for row in rows]

            persisted = self.create_orders_in_transaction(
                conn,
                orders,
                operation_id=operation_id,
                operation_request_hash=operation_request_hash,
            )
            conn.commit()
            return persisted
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_orders_by_operation(self, operation_id: str) -> list[PaperOrder]:
        operation_id = str(operation_id or "").strip()
        if not operation_id:
            raise ValueError("operation_id is required")
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM paper_orders WHERE operation_id = ? ORDER BY created_at ASC, order_id ASC",
                (operation_id,),
            ).fetchall()
            if not rows:
                raise KeyError("paper orders not found for operation: %s" % operation_id)
            return [self._row_to_order(row) for row in rows]
        finally:
            conn.close()

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

        DEPRECATED: 此方法已废弃。
        PaperEngine 使用内置的 _match_orders() 和 _execute_pending_orders_v2() 进行撮合。
        所有撮合逻辑现在通过统一执行协议：
        OrderIntentBatch -> RiskGate -> PaperAdapter -> paper_ledger
        
        保留此方法仅用于文档和过渡期警告。
        """
        raise NotImplementedError(
            "OrderManager.match_orders() 已废弃。\n"
            "PaperEngine 使用 _execute_pending_orders_v2() -> PaperAdapter 进行撮合。"
        )

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
        """判断是否应该撮合
        
        DEPRECATED: 此方法已废弃，撮合逻辑现在在 PaperAdapter 中。
        """
        raise NotImplementedError("_should_match() 已废弃，使用 PaperAdapter 进行撮合")

    def _execute_order(self, order: PaperOrder, quote, config: PaperConfig) -> Optional[PaperTrade]:
        """执行订单
        
        DEPRECATED: 此方法已废弃，执行逻辑现在在 PaperAdapter 中。
        """
        raise NotImplementedError("_execute_order() 已废弃，使用 PaperAdapter.execute_batch() 进行执行")

    def _save_order(self, order: PaperOrder, *, operation_id: Optional[str] = None, operation_request_hash: Optional[str] = None):
        """保存订单到数据库
        
        DEPRECATED: 此方法已废弃，订单持久化现在通过 PaperAdapter.execute_batch() 完成。
        保留仅用于 create_orders_in_transaction() 向后兼容。
        """
        raise NotImplementedError(
            "_save_order() 已废弃。\n"
            "订单持久化现在通过 PaperAdapter 写入 paper_ledger。"
        )

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
