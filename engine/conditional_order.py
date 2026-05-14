"""条件单执行引擎"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from loguru import logger

from config.datetime_utils import now_beijing, now_beijing_iso
from engine.alert_engine import Alert
from engine.models import Direction, OrderType, PaperConfig
from engine.order_manager import OrderManager
from engine.risk_manager import RiskManager
from utils.db import get_connection


@dataclass(frozen=True)
class ConditionalOrderRule:
    id: int
    alert_rule_id: int
    code: str
    direction: Direction
    order_type: OrderType
    volume: int
    price: Optional[float] = None
    max_amount: float = 0.0
    enabled: bool = False
    cooldown: int = 300
    last_triggered_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "alert_rule_id": self.alert_rule_id,
            "code": self.code,
            "direction": self.direction.value,
            "order_type": self.order_type.value,
            "price": self.price,
            "volume": self.volume,
            "max_amount": self.max_amount,
            "enabled": self.enabled,
            "cooldown": self.cooldown,
            "last_triggered_at": self.last_triggered_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class ConditionalOrderEvent:
    id: int
    conditional_order_id: Optional[int]
    alert_rule_id: Optional[int]
    code: str
    action: str
    reason: str
    order_id: Optional[str] = None
    quote_price: Optional[float] = None
    created_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "conditional_order_id": self.conditional_order_id,
            "alert_rule_id": self.alert_rule_id,
            "code": self.code,
            "action": self.action,
            "order_id": self.order_id,
            "reason": self.reason,
            "quote_price": self.quote_price,
            "created_at": self.created_at,
        }


class ConditionalOrderEngine:
    """预警触发后创建模拟盘订单。"""

    def __init__(
        self,
        db_path: str | None = None,
        config: PaperConfig | None = None,
        order_manager: OrderManager | None = None,
        risk_manager: RiskManager | None = None,
    ):
        self.config = config or PaperConfig()
        self.db_path = db_path or self.config.db_path
        self.config.db_path = self.db_path
        self.order_manager = order_manager or OrderManager(self.db_path)
        self.risk_manager = risk_manager or RiskManager(self.config, self.db_path)

    def _get_conn(self):
        return get_connection(self.db_path)

    def list_rules(self, enabled_only: bool = False) -> list[ConditionalOrderRule]:
        conn = self._get_conn()
        try:
            sql = "SELECT * FROM conditional_orders"
            params = []
            if enabled_only:
                sql += " WHERE enabled = ?"
                params.append(1)
            sql += " ORDER BY created_at DESC, id DESC"
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_rule(row) for row in rows]
        finally:
            conn.close()

    def create_rule(
        self,
        alert_rule_id: int,
        code: str,
        direction: str | Direction,
        order_type: str | OrderType,
        volume: int,
        price: float | None = None,
        max_amount: float = 0.0,
        enabled: bool = False,
        cooldown: int = 300,
    ) -> ConditionalOrderRule:
        direction_value = Direction.from_value(direction)
        order_type_value = OrderType(order_type) if isinstance(order_type, str) else order_type
        self._validate_rule(alert_rule_id, code, direction_value, order_type_value, volume, price, max_amount, cooldown)

        now = now_beijing_iso()
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """INSERT INTO conditional_orders
                (alert_rule_id, code, direction, order_type, price, volume, max_amount,
                 enabled, cooldown, last_triggered_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    alert_rule_id,
                    code,
                    direction_value.value,
                    order_type_value.value,
                    price,
                    volume,
                    max_amount,
                    1 if enabled else 0,
                    cooldown,
                    None,
                    now,
                    now,
                ),
            )
            conn.commit()
            return self.get_rule(cursor.lastrowid)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_rule(self, rule_id: int) -> ConditionalOrderRule:
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT * FROM conditional_orders WHERE id = ?", (rule_id,)).fetchone()
            if row is None:
                raise ValueError(f"条件单不存在: {rule_id}")
            return self._row_to_rule(row)
        finally:
            conn.close()

    def update_rule(self, rule_id: int, updates: dict) -> ConditionalOrderRule:
        current = self.get_rule(rule_id)
        next_data = {
            "alert_rule_id": updates.get("alert_rule_id", current.alert_rule_id),
            "code": updates.get("code", current.code),
            "direction": updates.get("direction", current.direction),
            "order_type": updates.get("order_type", current.order_type),
            "price": updates.get("price", current.price),
            "volume": updates.get("volume", current.volume),
            "max_amount": updates.get("max_amount", current.max_amount),
            "enabled": updates.get("enabled", current.enabled),
            "cooldown": updates.get("cooldown", current.cooldown),
        }
        direction_value = Direction.from_value(next_data["direction"])
        order_type_raw = next_data["order_type"]
        order_type_value = OrderType(order_type_raw) if isinstance(order_type_raw, str) else order_type_raw
        self._validate_rule(
            next_data["alert_rule_id"],
            next_data["code"],
            direction_value,
            order_type_value,
            next_data["volume"],
            next_data["price"],
            next_data["max_amount"],
            next_data["cooldown"],
        )

        conn = self._get_conn()
        try:
            conn.execute(
                """UPDATE conditional_orders SET
                alert_rule_id = ?, code = ?, direction = ?, order_type = ?, price = ?,
                volume = ?, max_amount = ?, enabled = ?, cooldown = ?, updated_at = ?
                WHERE id = ?""",
                (
                    next_data["alert_rule_id"],
                    next_data["code"],
                    direction_value.value,
                    order_type_value.value,
                    next_data["price"],
                    next_data["volume"],
                    next_data["max_amount"],
                    1 if next_data["enabled"] else 0,
                    next_data["cooldown"],
                    now_beijing_iso(),
                    rule_id,
                ),
            )
            conn.commit()
            return self.get_rule(rule_id)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def delete_rule(self, rule_id: int) -> bool:
        conn = self._get_conn()
        try:
            cursor = conn.execute("DELETE FROM conditional_orders WHERE id = ?", (rule_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def list_events(self, limit: int = 50) -> list[ConditionalOrderEvent]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT * FROM conditional_order_events
                ORDER BY created_at DESC, id DESC LIMIT ?""",
                (max(1, min(limit, 500)),),
            ).fetchall()
            return [self._row_to_event(row) for row in rows]
        finally:
            conn.close()

    def handle_alerts(self, alerts: list[Alert], quotes: dict) -> list[ConditionalOrderEvent]:
        events = []
        if not alerts:
            return events

        rules_by_alert_id: dict[int, list[ConditionalOrderRule]] = {}
        for rule in self.list_rules(enabled_only=True):
            rules_by_alert_id.setdefault(rule.alert_rule_id, []).append(rule)

        for alert in alerts:
            for rule in rules_by_alert_id.get(alert.rule_id, []):
                quote = quotes.get(rule.code) or quotes.get(alert.code)
                if quote is None:
                    events.append(self._record_event(rule, "skipped", "未找到触发行情", None, None))
                    continue
                try:
                    events.append(self._execute_rule(rule, alert, quote))
                except Exception as exc:
                    logger.exception(f"条件单执行异常: rule={rule.id}, alert={alert.rule_id}")
                    events.append(self._record_event(rule, "rejected", f"执行异常: {exc}", None, getattr(quote, "price", None)))
        return events

    def _execute_rule(self, rule: ConditionalOrderRule, alert: Alert, quote) -> ConditionalOrderEvent:
        now = now_beijing()
        quote_price = float(getattr(quote, "price", 0) or 0)
        if self._is_cooldown_active(rule, now):
            return self._record_event(rule, "skipped", "冷却期内跳过", None, quote_price)

        risk_ok, reason = self._check_risk(rule, quote_price)
        if not risk_ok:
            self._mark_triggered(rule.id, now)
            return self._record_event(rule, "rejected", reason, None, quote_price)

        order_price = rule.price if rule.order_type == OrderType.LIMIT else None
        order = self.order_manager.create_order(
            code=rule.code,
            direction=rule.direction,
            order_type=rule.order_type,
            volume=rule.volume,
            price=order_price,
            strategy_name="conditional_order",
            signal_reason=f"条件单#{rule.id} 由预警#{alert.rule_id}触发: {alert.message}",
        )
        self._mark_triggered(rule.id, now)
        return self._record_event(rule, "created_order", "已创建模拟盘订单", order.order_id, quote_price)

    def _is_cooldown_active(self, rule: ConditionalOrderRule, now: datetime) -> bool:
        if not rule.last_triggered_at or rule.cooldown <= 0:
            return False
        try:
            last = datetime.fromisoformat(rule.last_triggered_at)
        except ValueError:
            return False
        return (now - last).total_seconds() < rule.cooldown

    def _check_risk(self, rule: ConditionalOrderRule, quote_price: float) -> tuple[bool, str]:
        if quote_price <= 0:
            return False, "行情价格无效"

        notional = quote_price * rule.volume
        if rule.direction == Direction.LONG and rule.max_amount > 0 and notional > rule.max_amount:
            return False, f"超过最大下单金额: {notional:.2f} > {rule.max_amount:.2f}"

        cash, positions, prices = self._load_portfolio_snapshot(rule.code, quote_price)
        if rule.direction == Direction.LONG:
            return self.risk_manager.check_buy_order(rule.code, quote_price, rule.volume, cash, positions, prices)
        return self.risk_manager.check_sell_order(rule.code, rule.volume, positions)

    def _load_portfolio_snapshot(self, code: str, quote_price: float) -> tuple[float, dict, dict]:
        conn = self._get_conn()
        try:
            cash = self.config.initial_cash
            row = conn.execute(
                "SELECT cash FROM paper_equity_curve ORDER BY timestamp DESC, id DESC LIMIT 1"
            ).fetchone()
            if row and row["cash"] is not None:
                cash = float(row["cash"])

            positions = {}
            prices = {code: quote_price}
            for pos in conn.execute("SELECT code, volume, current_price, avg_price FROM paper_positions").fetchall():
                positions[pos["code"]] = int(pos["volume"])
                price = pos["current_price"] or pos["avg_price"] or quote_price
                prices[pos["code"]] = float(price)
            return cash, positions, prices
        finally:
            conn.close()

    def _mark_triggered(self, rule_id: int, triggered_at: datetime):
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE conditional_orders SET last_triggered_at = ?, updated_at = ? WHERE id = ?",
                (triggered_at.isoformat(), now_beijing_iso(), rule_id),
            )
            conn.commit()
        finally:
            conn.close()

    def _record_event(
        self,
        rule: ConditionalOrderRule,
        action: str,
        reason: str,
        order_id: str | None,
        quote_price: float | None,
    ) -> ConditionalOrderEvent:
        conn = self._get_conn()
        created_at = now_beijing_iso()
        try:
            cursor = conn.execute(
                """INSERT INTO conditional_order_events
                (conditional_order_id, alert_rule_id, code, action, order_id, reason, quote_price, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (rule.id, rule.alert_rule_id, rule.code, action, order_id, reason, quote_price, created_at),
            )
            conn.commit()
            return ConditionalOrderEvent(
                id=cursor.lastrowid,
                conditional_order_id=rule.id,
                alert_rule_id=rule.alert_rule_id,
                code=rule.code,
                action=action,
                order_id=order_id,
                reason=reason,
                quote_price=quote_price,
                created_at=created_at,
            )
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _validate_rule(
        self,
        alert_rule_id: int,
        code: str,
        direction: Direction,
        order_type: OrderType,
        volume: int,
        price: float | None,
        max_amount: float,
        cooldown: int,
    ):
        if alert_rule_id <= 0:
            raise ValueError("预警规则ID必须大于0")
        normalized_code = code.strip()
        if len(normalized_code) != 6 or not normalized_code.isdigit():
            raise ValueError("股票代码必须是6位数字")
        if direction not in (Direction.LONG, Direction.SHORT):
            raise ValueError("方向必须是 buy 或 sell")
        if order_type not in (OrderType.MARKET, OrderType.LIMIT):
            raise ValueError("条件单仅支持市价单和限价单")
        if volume <= 0 or volume % 100 != 0:
            raise ValueError("数量必须是100的正整数倍")
        if order_type == OrderType.LIMIT and (price is None or price <= 0):
            raise ValueError("限价条件单必须指定有效价格")
        if max_amount < 0:
            raise ValueError("最大下单金额不能为负数")
        if cooldown < 0:
            raise ValueError("冷却时间不能为负数")

    @staticmethod
    def _row_to_rule(row) -> ConditionalOrderRule:
        return ConditionalOrderRule(
            id=row["id"],
            alert_rule_id=row["alert_rule_id"],
            code=row["code"],
            direction=Direction.from_value(row["direction"]),
            order_type=OrderType(row["order_type"]),
            price=row["price"],
            volume=row["volume"],
            max_amount=row["max_amount"] or 0.0,
            enabled=bool(row["enabled"]),
            cooldown=row["cooldown"] or 0,
            last_triggered_at=row["last_triggered_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_event(row) -> ConditionalOrderEvent:
        return ConditionalOrderEvent(
            id=row["id"],
            conditional_order_id=row["conditional_order_id"],
            alert_rule_id=row["alert_rule_id"],
            code=row["code"],
            action=row["action"],
            order_id=row["order_id"],
            reason=row["reason"],
            quote_price=row["quote_price"],
            created_at=row["created_at"],
        )
