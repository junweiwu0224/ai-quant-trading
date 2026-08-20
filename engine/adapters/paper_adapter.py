"""Paper 执行适配器 - 接收 ExecutionPermit，执行撮合，原子写入账本"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from config.datetime_utils import now_beijing, now_beijing_iso
from engine.execution_protocol import ExecutionPermit, OrderIntent, OrderIntentBatch
from utils.db import get_connection


@dataclass(frozen=True)
class Fill:
    """成交记录"""
    order_intent_key: str
    instrument: str
    side: str
    filled_price: float
    filled_volume: int
    trade_id: str
    filled_at: str
    execution_run_id: str
    account_id: str


@dataclass(frozen=True)
class QuoteSnapshot:
    """行情快照（撮合用）"""
    instrument: str
    price: float
    timestamp: str


class PaperAdapter:
    """Paper 撮合适配器 - 唯一有权执行成交和写账本的组件"""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._ensure_tables()

    def _ensure_tables(self):
        """确保 ledger、audit、outbox 表存在"""
        with get_connection(self._db_path) as conn:
            # 账本表（唯一权威成交记录）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS paper_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_id TEXT NOT NULL UNIQUE,
                    execution_run_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    order_intent_key TEXT NOT NULL,
                    instrument TEXT NOT NULL,
                    side TEXT NOT NULL,
                    filled_price REAL NOT NULL,
                    filled_volume INTEGER NOT NULL,
                    filled_at TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_run ON paper_ledger(execution_run_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_account ON paper_ledger(account_id)")

            # 审计表（每次 permit 验证和执行的完整记录）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS paper_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    execution_run_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    permit_fence TEXT NOT NULL,
                    action TEXT NOT NULL,
                    approved_count INTEGER NOT NULL,
                    rejected_count INTEGER NOT NULL,
                    filled_count INTEGER NOT NULL,
                    result TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)

            # Outbox（事件发布表，用于解耦通知）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS paper_outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    published INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_outbox_published ON paper_outbox(published)")
            conn.commit()

    def execute_batch(
        self,
        batch: OrderIntentBatch,
        permit: ExecutionPermit,
        quotes: dict[str, QuoteSnapshot],
    ) -> list[Fill]:
        """
        执行批次 - fail-closed：permit 无效则拒绝整个批次
        
        Returns:
            成交列表（可能是部分批准的子集）
        """
        # 最终验证：permit 必须仍然有效
        now_utc = datetime.now(timezone.utc)
        if not permit.is_valid(now=now_utc):
            logger.error(f"Permit 已失效: run={permit.execution_run_id} fence={permit.fence_token}")
            self._audit_reject(permit, "permit_invalid")
            return []

        # permit 必须绑定到这个 batch
        if permit.batch_id != batch.batch_id:
            logger.error(f"Permit batch 不匹配: permit={permit.batch_id} batch={batch.batch_id}")
            self._audit_reject(permit, "batch_mismatch")
            return []

        fills = []
        # 只执行 permit 批准的 intent
        approved_keys = set(permit.idempotency_keys)
        approved_intents = {intent.idempotency_key: intent for intent in batch.intents if intent.idempotency_key in approved_keys}

        for key, intent in approved_intents.items():
            quote = quotes.get(intent.instrument)
            if not quote:
                logger.warning(f"无行情: {intent.instrument}")
                continue

            # 简单撮合逻辑（ponytail: 先用最简单的市价成交）
            filled_price = quote.price
            filled_volume = int(intent.quantity)

            trade_id = f"{permit.execution_run_id}:{key}:{now_beijing_iso()}"
            fill = Fill(
                order_intent_key=key,
                instrument=intent.instrument,
                side=str(intent.side),
                filled_price=filled_price,
                filled_volume=filled_volume,
                trade_id=trade_id,
                filled_at=now_beijing_iso(),
                execution_run_id=permit.execution_run_id,
                account_id=permit.account_id,
            )
            fills.append(fill)

        # 原子提交：ledger + audit + outbox
        if fills:
            self._commit_atomic(permit, fills)

        return fills

    def _commit_atomic(self, permit: ExecutionPermit, fills: list[Fill]):
        """原子提交账本 + 审计 + outbox"""
        with get_connection(self._db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                # 1. 写入账本
                for fill in fills:
                    conn.execute(
                        """
                        INSERT INTO paper_ledger 
                        (trade_id, execution_run_id, account_id, order_intent_key, 
                         instrument, side, filled_price, filled_volume, filled_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            fill.trade_id,
                            fill.execution_run_id,
                            fill.account_id,
                            fill.order_intent_key,
                            fill.instrument,
                            fill.side,
                            fill.filled_price,
                            fill.filled_volume,
                            fill.filled_at,
                        ),
                    )

                # 2. 写入审计
                approved_count = len(permit.idempotency_keys)
                rejected_count = len(permit.evaluated_intent_keys) - approved_count
                conn.execute(
                    """
                    INSERT INTO paper_audit 
                    (execution_run_id, account_id, permit_fence, action, 
                     approved_count, rejected_count, filled_count, result)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        permit.execution_run_id,
                        permit.account_id,
                        permit.fence_token,
                        "execute_batch",
                        approved_count,
                        rejected_count,
                        len(fills),
                        "success",
                    ),
                )

                # 3. 写入 outbox（异步通知用）
                for fill in fills:
                    conn.execute(
                        """
                        INSERT INTO paper_outbox (event_type, aggregate_id, payload)
                        VALUES (?, ?, ?)
                        """,
                        (
                            "trade_filled",
                            fill.execution_run_id,
                            json.dumps({
                                "trade_id": fill.trade_id,
                                "instrument": fill.instrument,
                                "side": fill.side,
                                "price": fill.filled_price,
                                "volume": fill.filled_volume,
                            }),
                        ),
                    )

                conn.commit()
                logger.info(
                    f"账本提交成功: run={permit.execution_run_id} "
                    f"fills={len(fills)} fence={permit.fence_token}"
                )
            except Exception as e:
                conn.rollback()
                logger.error(f"账本提交失败: {e}")
                raise

    def _audit_reject(self, permit: ExecutionPermit, reason: str):
        """记录拒绝审计"""
        with get_connection(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO paper_audit 
                (execution_run_id, account_id, permit_fence, action, 
                 approved_count, rejected_count, filled_count, result)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    permit.execution_run_id,
                    permit.account_id,
                    permit.fence_token,
                    "execute_batch",
                    0,
                    len(permit.evaluated_intent_keys),
                    0,
                    reason,
                ),
            )
            conn.commit()

    def get_ledger(self, execution_run_id: str) -> list[Fill]:
        """查询执行运行的账本"""
        with get_connection(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT order_intent_key, instrument, side, filled_price, 
                       filled_volume, trade_id, filled_at, execution_run_id, account_id
                FROM paper_ledger
                WHERE execution_run_id = ?
                ORDER BY created_at
                """,
                (execution_run_id,),
            ).fetchall()
            return [
                Fill(
                    order_intent_key=r[0],
                    instrument=r[1],
                    side=r[2],
                    filled_price=r[3],
                    filled_volume=r[4],
                    trade_id=r[5],
                    filled_at=r[6],
                    execution_run_id=r[7],
                    account_id=r[8],
                )
                for r in rows
            ]
