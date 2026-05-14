"""风险管理器"""
import json
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional, Tuple

from loguru import logger

from config.settings import PROJECT_ROOT
from config.datetime_utils import now_beijing, now_beijing_iso, now_beijing_str, today_beijing, today_beijing_compact
from engine.models import (
    Direction, OrderStatus, PaperConfig, PaperOrder, PaperPosition, RiskEvent
)
from utils.db import get_connection


class RiskManager:
    """风险管理器"""

    _RISK_CONFIG_FILE = PROJECT_ROOT / "logs" / "paper" / "risk_config.json"

    def __init__(self, config: PaperConfig, db_path: str = None):
        self.config = config
        self.db_path = db_path or config.db_path
        self.events: List[RiskEvent] = []
        self._load_persisted_rules()

    def _get_conn(self):
        """获取数据库连接（已配置 WAL + busy_timeout）"""
        return get_connection(self.db_path)

    def check_buy_order(
        self,
        code: str,
        price: float,
        volume: int,
        cash: float,
        positions: dict,
        prices: dict,
    ) -> Tuple[bool, str]:
        """检查买入订单是否符合风控规则"""
        # 1. 检查资金是否充足
        amount = price * volume
        commission = max(amount * self.config.commission_rate, 5.0)
        if cash < amount + commission:
            return False, f"资金不足: 需要{amount + commission:.2f}，可用{cash:.2f}"

        # 2. 检查单只股票仓位限制
        total_equity = cash + sum(
            vol * prices.get(c, 0) for c, vol in positions.items()
        )

        if total_equity > 0:
            current_value = positions.get(code, 0) * prices.get(code, 0)
            new_value = current_value + amount
            position_pct = new_value / total_equity

            if position_pct > self.config.max_position_pct:
                return False, f"超过单只最大仓位限制({self.config.max_position_pct*100}%): 当前{position_pct*100:.1f}%"

        # 3. 检查最大持仓数量
        if len(positions) >= self.config.max_positions and code not in positions:
            return False, f"超过最大持仓数量限制({self.config.max_positions}只)"

        return True, ""

    def check_sell_order(
        self,
        code: str,
        volume: int,
        positions: dict,
    ) -> Tuple[bool, str]:
        """检查卖出订单是否符合风控规则"""
        # 检查持仓是否充足
        current_position = positions.get(code, 0)
        if current_position < volume:
            return False, f"持仓不足: 需要{volume}股，可用{current_position}股"

        return True, ""

    def check_position_limit(
        self,
        code: str,
        volume: int,
        price: float,
        cash: float,
        positions: dict,
        prices: dict,
    ) -> Tuple[bool, str]:
        """检查仓位限制"""
        return self.check_buy_order(code, price, volume, cash, positions, prices)

    def check_drawdown_limit(
        self,
        current_equity: float,
        peak_equity: float,
    ) -> Tuple[bool, str]:
        """检查回撤限制"""
        if peak_equity <= 0:
            return True, ""

        drawdown = (peak_equity - current_equity) / peak_equity

        if drawdown >= self.config.max_drawdown:
            return False, f"触发最大回撤限制({self.config.max_drawdown*100}%): 当前回撤{drawdown*100:.1f}%"

        return True, ""

    def check_daily_loss_limit(
        self,
        daily_pnl: float,
        total_equity: float,
    ) -> Tuple[bool, str]:
        """检查单日亏损限制"""
        if total_equity <= 0:
            return True, ""

        if daily_pnl < 0:
            loss_pct = abs(daily_pnl) / total_equity
            if loss_pct >= self.config.max_daily_loss:
                return False, f"触发单日亏损限制({self.config.max_daily_loss*100}%): 当前亏损{loss_pct*100:.1f}%"

        return True, ""

    def check_stop_loss(
        self,
        position: PaperPosition,
        current_price: float,
    ) -> Optional[RiskEvent]:
        """检查止损"""
        if position.stop_loss_price and current_price <= position.stop_loss_price:
            event = RiskEvent(
                event_type="stop_loss",
                code=position.code,
                trigger_price=current_price,
                action="sell",
                reason=f"触发止损: 当前价{current_price:.2f} <= 止损价{position.stop_loss_price:.2f}",
            )
            self._save_risk_event(event)
            return event
        return None

    def check_take_profit(
        self,
        position: PaperPosition,
        current_price: float,
    ) -> Optional[RiskEvent]:
        """检查止盈"""
        if position.take_profit_price and current_price >= position.take_profit_price:
            event = RiskEvent(
                event_type="take_profit",
                code=position.code,
                trigger_price=current_price,
                action="sell",
                reason=f"触发止盈: 当前价{current_price:.2f} >= 止盈价{position.take_profit_price:.2f}",
            )
            self._save_risk_event(event)
            return event
        return None

    def check_trailing_stop(
        self,
        position: PaperPosition,
        current_price: float,
        trailing_pct: float = 0.05,
    ) -> Optional[RiskEvent]:
        """检查移动止损"""
        # 从持仓记录中获取最高价
        highest_price = self._get_highest_price(position.code)

        if highest_price > 0:
            # 更新最高价
            if current_price > highest_price:
                self._update_highest_price(position.code, current_price)
                highest_price = current_price

            # 计算回撤
            drawdown = (highest_price - current_price) / highest_price

            if drawdown >= trailing_pct:
                event = RiskEvent(
                    event_type="trailing_stop",
                    code=position.code,
                    trigger_price=current_price,
                    action="sell",
                    reason=f"触发移动止损: 最高价{highest_price:.2f}，当前价{current_price:.2f}，回撤{drawdown*100:.1f}%",
                )
                self._save_risk_event(event)
                return event

        return None

    def get_risk_events(
        self,
        event_type: Optional[str] = None,
        days: int = 30,
    ) -> List[dict]:
        """获取风控事件"""
        conn = self._get_conn()
        try:
            conditions = []
            params = []

            if event_type:
                conditions.append("event_type = ?")
                params.append(event_type)

            from datetime import timedelta
            start_date = (now_beijing() - timedelta(days=days)).isoformat()
            conditions.append("created_at >= ?")
            params.append(start_date)

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            cursor = conn.execute(
                f"SELECT * FROM paper_risk_events WHERE {where_clause} "
                f"ORDER BY created_at DESC",
                params
            )

            rows = cursor.fetchall()
            events = []

            for row in rows:
                events.append({
                    "id": row["id"],
                    "event_type": row["event_type"],
                    "code": row["code"],
                    "trigger_price": row["trigger_price"],
                    "action": row["action"],
                    "reason": row["reason"],
                    "created_at": row["created_at"],
                })

            return events
        finally:
            conn.close()

    def get_risk_rules(self) -> dict:
        """获取风控规则配置"""
        return {
            "max_position_pct": self.config.max_position_pct,
            "max_positions": self.config.max_positions,
            "max_drawdown": self.config.max_drawdown,
            "max_daily_loss": self.config.max_daily_loss,
            "commission_rate": self.config.commission_rate,
            "stamp_tax_rate": self.config.stamp_tax_rate,
            "slippage": self.config.slippage,
        }

    def _load_persisted_rules(self):
        """从文件加载持久化的风控规则"""
        if not self._RISK_CONFIG_FILE.exists():
            return
        try:
            data = json.loads(self._RISK_CONFIG_FILE.read_text())
            for key in ("max_position_pct", "max_positions", "max_drawdown", "max_daily_loss"):
                if key in data:
                    setattr(self.config, key, data[key])
            logger.info(f"从文件恢复风控规则: {data}")
        except Exception as e:
            logger.warning(f"加载风控配置文件失败: {e}")

    def _persist_rules(self):
        """将风控规则持久化到文件"""
        try:
            self._RISK_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            rules = {
                "max_position_pct": self.config.max_position_pct,
                "max_positions": self.config.max_positions,
                "max_drawdown": self.config.max_drawdown,
                "max_daily_loss": self.config.max_daily_loss,
            }
            self._RISK_CONFIG_FILE.write_text(json.dumps(rules, indent=2))
        except Exception as e:
            logger.warning(f"持久化风控配置失败: {e}")

    def update_risk_rules(self, rules: dict):
        """更新风控规则"""
        if "max_position_pct" in rules:
            self.config.max_position_pct = rules["max_position_pct"]
        if "max_positions" in rules:
            self.config.max_positions = rules["max_positions"]
        if "max_drawdown" in rules:
            self.config.max_drawdown = rules["max_drawdown"]
        if "max_daily_loss" in rules:
            self.config.max_daily_loss = rules["max_daily_loss"]

        self._persist_rules()
        logger.info(f"风控规则已更新: {rules}")

    def _save_risk_event(self, event: RiskEvent):
        """保存风控事件（失败时上抛，不静默吞掉）"""
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO paper_risk_events
                (event_type, code, trigger_price, action, reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    event.event_type,
                    event.code,
                    event.trigger_price,
                    event.action,
                    event.reason,
                    event.created_at.isoformat(),
                )
            )
            conn.commit()
        except Exception as e:
            logger.error(f"保存风控事件失败: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

    def _get_highest_price(self, code: str) -> float:
        """获取持仓期间最高价（从 paper_position_highs 表）"""
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "SELECT highest_price FROM paper_position_highs WHERE code = ?",
                (code,)
            )
            row = cursor.fetchone()
            return row[0] if row and row[0] else 0
        except Exception:
            # 表不存在时回退到交易记录
            try:
                cursor = conn.execute(
                    "SELECT MAX(price) FROM paper_trades WHERE code = ? AND direction = 'buy'",
                    (code,)
                )
                row = cursor.fetchone()
                return row[0] if row and row[0] else 0
            except Exception:
                return 0
        finally:
            conn.close()

    def _update_highest_price(self, code: str, price: float):
        """更新持仓期间最高价"""
        conn = self._get_conn()
        try:
            # 确保表存在
            conn.execute(
                """CREATE TABLE IF NOT EXISTS paper_position_highs (
                    code TEXT PRIMARY KEY,
                    highest_price REAL NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            conn.execute(
                """INSERT INTO paper_position_highs (code, highest_price, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(code) DO UPDATE SET
                     highest_price = MAX(highest_price, excluded.highest_price),
                     updated_at = excluded.updated_at""",
                (code, price, now_beijing_iso())
            )
            conn.commit()
        except Exception as e:
            logger.error(f"更新最高价失败: {e}")
            conn.rollback()
        finally:
            conn.close()

    def calculate_position_size(
        self,
        code: str,
        price: float,
        cash: float,
        positions: dict,
        prices: dict,
        risk_per_trade: float = 0.02,
    ) -> int:
        """计算仓位大小（基于风险）"""
        total_equity = cash + sum(
            vol * prices.get(c, 0) for c, vol in positions.items()
        )

        # 计算单笔最大风险金额
        max_risk_amount = total_equity * risk_per_trade

        # 计算仓位大小（假设止损为买入价的5%）
        stop_loss_pct = 0.05
        position_value = max_risk_amount / stop_loss_pct

        # 转换为股数（100的整数倍）
        shares = int(position_value / price / 100) * 100

        # 检查是否超过单只最大仓位
        max_position_value = total_equity * self.config.max_position_pct
        max_shares = int(max_position_value / price / 100) * 100

        return min(shares, max_shares)
