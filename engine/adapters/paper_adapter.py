"""Paper execution adapter: the only component allowed to commit fills."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Mapping

from config.datetime_utils import now_beijing_iso
from engine.execution_protocol import Environment, ExecutionPermit, OrderIntentBatch, Side
from utils.db import get_connection


@dataclass(frozen=True)
class Fill:
    order_intent_key: str
    instrument: str
    side: str
    filled_price: float
    filled_volume: int
    trade_id: str
    filled_at: str
    execution_run_id: str
    account_id: str
    commission: float = 0.0
    stamp_tax: float = 0.0
    slippage: float = 0.0
    workspace_id: str = "default"
    environment: str = "paper"
    permit_id: str = ""
    decision_id: str = ""
    fence_token: str = ""


@dataclass(frozen=True)
class QuoteSnapshot:
    instrument: str
    price: float
    timestamp: str
    industry: str = ""
    limit_up: float | None = None
    limit_down: float | None = None
    is_suspended: bool = False


class PaperAdapter:
    """Paper matcher with atomic ledger/audit/outbox writes and idempotency."""

    def __init__(
        self,
        db_path: str,
        *,
        workspace_id: str = "default",
        commission_rate: float = 0.0,
        stamp_tax_rate: float = 0.0,
        min_commission: float = 5.0,
        slippage: float = 0.0,
    ) -> None:
        self._db_path = str(db_path)
        self.workspace_id = workspace_id
        self._commission_rate = Decimal(str(commission_rate))
        self._stamp_tax_rate = Decimal(str(stamp_tax_rate))
        self._min_commission = Decimal(str(min_commission))
        self._slippage = Decimal(str(slippage))
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        with get_connection(self._db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_id TEXT NOT NULL UNIQUE,
                    execution_run_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL DEFAULT 'default',
                    environment TEXT NOT NULL DEFAULT 'paper' CHECK(environment = 'paper'),
                    order_intent_key TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL DEFAULT '',
                    instrument TEXT NOT NULL,
                    side TEXT NOT NULL,
                    filled_price REAL NOT NULL,
                    filled_volume INTEGER NOT NULL,
                    filled_at TEXT NOT NULL,
                    commission REAL NOT NULL DEFAULT 0,
                    stamp_tax REAL NOT NULL DEFAULT 0,
                    slippage REAL NOT NULL DEFAULT 0,
                    permit_id TEXT NOT NULL DEFAULT '',
                    decision_id TEXT NOT NULL DEFAULT '',
                    fence_token TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(paper_ledger)").fetchall()}
            additions = {
                "workspace_id": "TEXT NOT NULL DEFAULT 'default'",
                "environment": "TEXT NOT NULL DEFAULT 'paper'",
                "idempotency_key": "TEXT NOT NULL DEFAULT ''",
                "commission": "REAL NOT NULL DEFAULT 0",
                "stamp_tax": "REAL NOT NULL DEFAULT 0",
                "slippage": "REAL NOT NULL DEFAULT 0",
                "permit_id": "TEXT NOT NULL DEFAULT ''",
                "decision_id": "TEXT NOT NULL DEFAULT ''",
                "fence_token": "TEXT NOT NULL DEFAULT ''",
            }
            for name, definition in additions.items():
                if name not in columns:
                    connection.execute(f"ALTER TABLE paper_ledger ADD COLUMN {name} {definition}")
            connection.execute("UPDATE paper_ledger SET idempotency_key = order_intent_key WHERE idempotency_key = '' OR idempotency_key IS NULL")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_ledger_run ON paper_ledger(execution_run_id, account_id, workspace_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_ledger_account ON paper_ledger(account_id, workspace_id, environment)")
            connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_ledger_idempotency ON paper_ledger(account_id, workspace_id, environment, idempotency_key)")
            connection.execute(
                """
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
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    published INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_outbox_published ON paper_outbox(published)")
            connection.commit()

    def execute_batch(
        self,
        batch: OrderIntentBatch,
        permit: ExecutionPermit,
        quotes: Mapping[str, QuoteSnapshot],
        *,
        require_authoritative: bool = False,
    ) -> list[Fill]:
        now = datetime.now(timezone.utc)
        if not permit.is_valid(now=now):
            self._audit_reject(permit, "permit_invalid")
            return []
        if permit.batch_id != batch.batch_id or permit.account_id != batch.account_id or permit.execution_run_id != batch.execution_run_id or permit.environment is not Environment.PAPER:
            self._audit_reject(permit, "permit_context_mismatch")
            return []
        if set(permit.evaluated_intent_keys) != set(batch.idempotency_keys):
            self._audit_reject(permit, "permit_coverage_mismatch")
            return []
        if require_authoritative and not self._permit_is_authoritative(permit, batch):
            self._audit_reject(permit, "permit_not_authoritative")
            return []

        approved = set(permit.idempotency_keys)
        existing = self._existing_keys(batch.account_id, batch.idempotency_keys)
        fills: list[Fill] = []
        for intent in batch.intents:
            if intent.idempotency_key not in approved or intent.idempotency_key in existing:
                continue
            quote = quotes.get(intent.instrument)
            if quote is None or quote.price <= 0:
                continue
            side = intent.side if isinstance(intent.side, Side) else Side(str(intent.side).lower().split(".")[-1])
            raw_price = Decimal(str(quote.price))
            fill_price = raw_price * (Decimal("1") + self._slippage if side is Side.BUY else Decimal("1") - self._slippage)
            volume = int(intent.quantity)
            amount = fill_price * volume
            commission = max(amount * self._commission_rate, self._min_commission) if self._commission_rate or self._min_commission else Decimal("0")
            stamp_tax = amount * self._stamp_tax_rate if side is Side.SELL else Decimal("0")
            fills.append(Fill(
                order_intent_key=intent.idempotency_key,
                instrument=intent.instrument,
                side=side.value,
                filled_price=float(fill_price),
                filled_volume=volume,
                trade_id=f"{permit.execution_run_id}:{intent.idempotency_key}",
                filled_at=now_beijing_iso(),
                execution_run_id=permit.execution_run_id,
                account_id=permit.account_id,
                commission=float(commission),
                stamp_tax=float(stamp_tax),
                slippage=float(abs(fill_price - raw_price)),
                workspace_id=self.workspace_id,
                environment="paper",
                permit_id=permit.permit_id,
                decision_id=permit.decision_id,
                fence_token=permit.fence_token,
            ))
        return self._commit_atomic(permit, fills) if fills else []

    def _existing_keys(self, account_id: str, keys: tuple[str, ...]) -> set[str]:
        if not keys:
            return set()
        placeholders = ",".join("?" for _ in keys)
        with get_connection(self._db_path) as connection:
            rows = connection.execute(f"SELECT idempotency_key FROM paper_ledger WHERE account_id = ? AND workspace_id = ? AND environment = 'paper' AND idempotency_key IN ({placeholders})", (account_id, self.workspace_id, *keys)).fetchall()
        return {row[0] for row in rows}

    def _permit_is_authoritative(self, permit: ExecutionPermit, batch: OrderIntentBatch) -> bool:
        try:
            with get_connection(self._db_path) as connection:
                row = connection.execute("SELECT execution_run_id, account_id, workspace_id, batch_id, fence_token, idempotency_keys_json, expires_at FROM paper_execution_permits WHERE permit_id = ?", (permit.permit_id,)).fetchone()
        except sqlite3.OperationalError:
            return False
        if row is None:
            return False
        try:
            keys = set(json.loads(row["idempotency_keys_json"]))
        except (TypeError, json.JSONDecodeError):
            return False
        return row["execution_run_id"] == batch.execution_run_id and row["account_id"] == batch.account_id and row["workspace_id"] == self.workspace_id and row["batch_id"] == batch.batch_id and row["fence_token"] == permit.fence_token and keys == set(permit.idempotency_keys) and row["expires_at"] == permit.expires_at.isoformat()

    def _commit_atomic(self, permit: ExecutionPermit, fills: list[Fill]) -> list[Fill]:
        with get_connection(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                persisted: list[Fill] = []
                for fill in fills:
                    existing = connection.execute("SELECT order_intent_key, instrument, side, filled_price, filled_volume, trade_id, filled_at, execution_run_id, account_id, commission, stamp_tax, slippage, workspace_id, environment, permit_id, decision_id, fence_token FROM paper_ledger WHERE account_id = ? AND workspace_id = ? AND environment = 'paper' AND idempotency_key = ?", (fill.account_id, fill.workspace_id, fill.order_intent_key)).fetchone()
                    if existing is not None:
                        persisted.append(Fill(*existing))
                        continue
                    connection.execute("INSERT INTO paper_ledger(trade_id, execution_run_id, account_id, workspace_id, environment, order_intent_key, idempotency_key, instrument, side, filled_price, filled_volume, filled_at, commission, stamp_tax, slippage, permit_id, decision_id, fence_token) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (fill.trade_id, fill.execution_run_id, fill.account_id, fill.workspace_id, fill.environment, fill.order_intent_key, fill.order_intent_key, fill.instrument, fill.side, fill.filled_price, fill.filled_volume, fill.filled_at, fill.commission, fill.stamp_tax, fill.slippage, fill.permit_id, fill.decision_id, fill.fence_token))
                    persisted.append(fill)
                    connection.execute("INSERT INTO paper_outbox(event_type, aggregate_id, payload) VALUES (?, ?, ?)", ("trade_filled", fill.execution_run_id, json.dumps({"trade_id": fill.trade_id, "instrument": fill.instrument, "side": fill.side, "price": fill.filled_price, "volume": fill.filled_volume}, sort_keys=True)))
                connection.execute("INSERT INTO paper_audit(execution_run_id, account_id, permit_fence, action, approved_count, rejected_count, filled_count, result) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (permit.execution_run_id, permit.account_id, permit.fence_token, "execute_batch", len(permit.idempotency_keys), len(permit.evaluated_intent_keys) - len(permit.idempotency_keys), len(persisted), "success"))
                connection.commit()
                return persisted
            except Exception:
                connection.rollback()
                raise

    def _audit_reject(self, permit: ExecutionPermit, reason: str) -> None:
        with get_connection(self._db_path) as connection:
            connection.execute("INSERT INTO paper_audit(execution_run_id, account_id, permit_fence, action, approved_count, rejected_count, filled_count, result) VALUES (?, ?, ?, ?, 0, ?, 0, ?)", (permit.execution_run_id, permit.account_id, permit.fence_token, "execute_batch", len(permit.evaluated_intent_keys), reason))
            connection.commit()

    def get_ledger(self, execution_run_id: str) -> list[Fill]:
        with get_connection(self._db_path) as connection:
            rows = connection.execute("SELECT order_intent_key, instrument, side, filled_price, filled_volume, trade_id, filled_at, execution_run_id, account_id, commission, stamp_tax, slippage, workspace_id, environment, permit_id, decision_id, fence_token FROM paper_ledger WHERE execution_run_id = ? ORDER BY id", (execution_run_id,)).fetchall()
        return [Fill(*row) for row in rows]

    def close(self) -> None:
        return None


__all__ = ["Fill", "PaperAdapter", "QuoteSnapshot"]
