"""Authoritative batch RiskGate for Paper execution.

The API may provide an advisory permit for compatibility, but only this module
may create the final permit used by the PaperAdapter. It evaluates the latest
SQLite ledger/account facts and current quote snapshots in one worker-owned
step.
"""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping

from engine.execution_protocol import (
    Environment,
    ExecutionPermit,
    OrderIntentBatch,
    RiskDecision,
    RiskDecisionStatus,
    Side,
)
from engine.research_facts import ExecutionRunBlockedError, ResearchFactsStore
from utils.db import get_connection


class RiskGateError(ValueError):
    """Base class for fail-closed risk evaluation errors."""


class RiskContextMismatch(RiskGateError):
    """Raised when an order batch does not match the account/run context."""


def _decimal(value: Any, field: str = "value") -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise RiskGateError(f"{field} must be a valid number") from exc
    if not result.is_finite():
        raise RiskGateError(f"{field} must be finite")
    return result


def _utc(value: datetime | str | None = None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None or value.utcoffset() is None:
        raise RiskGateError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _side(value: Any) -> Side:
    if isinstance(value, Side):
        return value
    normalized = str(value).strip().lower().split(".")[-1]
    return Side(normalized)


@dataclass(frozen=True, slots=True)
class QuoteSnapshot:
    """Latest quote plus the fields required by final risk checks."""

    instrument: str
    price: Decimal | float | int
    timestamp: datetime | str
    industry: str = ""
    limit_up: Decimal | float | int | None = None
    limit_down: Decimal | float | int | None = None
    is_suspended: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "price", _decimal(self.price, "price"))
        object.__setattr__(self, "timestamp", _utc(self.timestamp))
        if self.limit_up is not None:
            object.__setattr__(self, "limit_up", _decimal(self.limit_up, "limit_up"))
        if self.limit_down is not None:
            object.__setattr__(self, "limit_down", _decimal(self.limit_down, "limit_down"))
        if self.price <= 0:
            raise RiskGateError("quote price must be positive")


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    """Latest account facts reconstructed from the authoritative ledger."""

    account_id: str
    workspace_id: str
    environment: Environment
    initial_cash: Decimal
    cash: Decimal
    total_equity: Decimal
    positions: Mapping[str, Decimal]
    position_values: Mapping[str, Decimal]
    avg_prices: Mapping[str, Decimal]
    today_buys: frozenset[str]
    industry_values: Mapping[str, Decimal]
    fence_token: str = "1"

    def __post_init__(self) -> None:
        if self.environment is not Environment.PAPER:
            raise RiskContextMismatch("only paper accounts are executable in V2")
        initial_cash = _decimal(self.initial_cash, "initial_cash")
        cash = _decimal(self.cash, "cash")
        total_equity = _decimal(self.total_equity, "total_equity")
        object.__setattr__(self, "initial_cash", initial_cash)
        object.__setattr__(self, "cash", cash)
        object.__setattr__(self, "total_equity", total_equity)
        if initial_cash < 0:
            raise RiskGateError("initial_cash cannot be negative")


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    policy_version: str = "risk-v3"
    max_single_position_pct: Decimal = Decimal("0.20")
    max_industry_pct: Decimal = Decimal("0.40")
    max_total_position_pct: Decimal = Decimal("0.95")
    commission_rate: Decimal = Decimal("0.0003")
    stamp_tax_rate: Decimal = Decimal("0.001")
    min_commission: Decimal = Decimal("5")
    slippage: Decimal = Decimal("0.002")
    lot_size: int = 100
    max_quote_age_seconds: int = 120

    def __post_init__(self) -> None:
        if not self.policy_version.strip():
            raise RiskGateError("policy_version must not be empty")
        for name in ("max_single_position_pct", "max_industry_pct", "max_total_position_pct"):
            value = _decimal(getattr(self, name), name)
            if value < 0 or value > 1:
                raise RiskGateError(f"{name} must be between 0 and 1")
        if self.lot_size <= 0 or self.max_quote_age_seconds <= 0:
            raise RiskGateError("lot_size and max_quote_age_seconds must be positive")


class RiskGate:
    """Final batch gate. The adapter must receive a permit from ``authorize``."""

    def __init__(self, policy: RiskPolicy | None = None, *, db_path: str | Path | None = None):
        self.policy = policy or RiskPolicy()
        self.db_path = str(db_path) if db_path is not None else None
        if self.db_path:
            self._ensure_tables()

    def _ensure_tables(self) -> None:
        with get_connection(self.db_path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS paper_risk_decisions (
                    decision_id TEXT PRIMARY KEY,
                    execution_run_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    batch_id TEXT NOT NULL,
                    policy_version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    evaluated_intent_keys_json TEXT NOT NULL,
                    approved_intent_keys_json TEXT NOT NULL,
                    rejected_intent_keys_json TEXT NOT NULL,
                    reasons_json TEXT NOT NULL,
                    evaluated_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS paper_execution_permits (
                    permit_id TEXT PRIMARY KEY,
                    decision_id TEXT NOT NULL REFERENCES paper_risk_decisions(decision_id),
                    execution_run_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    batch_id TEXT NOT NULL,
                    fence_token TEXT NOT NULL,
                    idempotency_keys_json TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_risk_decisions_run ON paper_risk_decisions(execution_run_id, account_id);
                CREATE INDEX IF NOT EXISTS idx_permits_batch ON paper_execution_permits(batch_id, account_id);
                """
            )
            connection.commit()

    def check_batch(
        self,
        batch: OrderIntentBatch,
        account: AccountSnapshot,
        quotes: Mapping[str, QuoteSnapshot],
        *,
        now: datetime | None = None,
    ) -> RiskDecision:
        current = _utc(now)
        if batch.environment is not Environment.PAPER or account.environment is not Environment.PAPER:
            raise RiskContextMismatch("live execution is disabled")
        if batch.account_id != account.account_id:
            raise RiskContextMismatch("batch/account mismatch")
        if batch.execution_run_id == "":
            raise RiskContextMismatch("execution_run_id is required")
        approved: list[str] = []
        rejected: list[str] = []
        reasons: list[str] = []
        cash = account.cash
        positions = {key: _decimal(value, "position") for key, value in account.positions.items()}
        values = {key: _decimal(value, "position_value") for key, value in account.position_values.items()}
        industries = {key: _decimal(value, "industry_value") for key, value in account.industry_values.items()}
        projected_total = sum(values.values(), Decimal("0"))

        for intent in batch.intents:
            key = intent.idempotency_key
            instrument = intent.instrument
            quantity = _decimal(intent.quantity, "quantity")
            try:
                side = _side(intent.side)
            except ValueError:
                rejected.append(key)
                reasons.append(f"{instrument}: invalid side")
                continue
            quote = quotes.get(instrument)
            if quote is None:
                rejected.append(key)
                reasons.append(f"{instrument}: latest quote unavailable")
                continue
            if (current - quote.timestamp).total_seconds() > self.policy.max_quote_age_seconds:
                rejected.append(key)
                reasons.append(f"{instrument}: quote is stale")
                continue
            if quote.is_suspended:
                rejected.append(key)
                reasons.append(f"{instrument}: trading suspended")
                continue
            if quantity <= 0 or quantity != quantity.to_integral_value():
                rejected.append(key)
                reasons.append(f"{instrument}: quantity must be a positive integer")
                continue
            if quantity % self.policy.lot_size != 0:
                rejected.append(key)
                reasons.append(f"{instrument}: quantity must be a multiple of {self.policy.lot_size}")
                continue
            if side is Side.BUY and quote.limit_up is not None and quote.price > quote.limit_up:
                rejected.append(key)
                reasons.append(f"{instrument}: buy price exceeds limit-up")
                continue
            if side is Side.SELL and quote.limit_down is not None and quote.price < quote.limit_down:
                rejected.append(key)
                reasons.append(f"{instrument}: sell price is below limit-down")
                continue
            if side is Side.SELL and instrument in account.today_buys and not getattr(intent, "emergency", False):
                rejected.append(key)
                reasons.append(f"{instrument}: T+1 prevents same-day sale")
                continue

            if side is Side.BUY:
                execution_price = quote.price * (Decimal("1") + self.policy.slippage)
                amount = execution_price * quantity
                commission = max(amount * self.policy.commission_rate, self.policy.min_commission)
                total_cost = amount + commission
                if cash < total_cost:
                    rejected.append(key)
                    reasons.append(f"{instrument}: insufficient cash")
                    continue
                old_value = values.get(instrument, Decimal("0"))
                new_value = old_value + amount
                industry = quote.industry or "__unknown__"
                new_industry = industries.get(industry, Decimal("0")) + amount
                emergency = bool(getattr(intent, "emergency", False))
                if account.total_equity <= 0:
                    rejected.append(key)
                    reasons.append(f"{instrument}: account equity is not positive")
                    continue
                if not emergency and new_value / account.total_equity > self.policy.max_single_position_pct:
                    rejected.append(key)
                    reasons.append(f"{instrument}: single-position limit exceeded")
                    continue
                if not emergency and new_industry / account.total_equity > self.policy.max_industry_pct:
                    rejected.append(key)
                    reasons.append(f"{instrument}: industry limit exceeded")
                    continue
                if not emergency and (projected_total + amount) / account.total_equity > self.policy.max_total_position_pct:
                    rejected.append(key)
                    reasons.append(f"{instrument}: total-position limit exceeded")
                    continue
                approved.append(key)
                cash -= total_cost
                positions[instrument] = positions.get(instrument, Decimal("0")) + quantity
                values[instrument] = new_value
                industries[industry] = new_industry
                projected_total += amount
            else:
                current_position = positions.get(instrument, Decimal("0"))
                if current_position < quantity:
                    rejected.append(key)
                    reasons.append(f"{instrument}: sell quantity exceeds position")
                    continue
                execution_price = quote.price * (Decimal("1") - self.policy.slippage)
                amount = execution_price * quantity
                commission = max(amount * self.policy.commission_rate, self.policy.min_commission)
                proceeds = amount - commission - amount * self.policy.stamp_tax_rate
                approved.append(key)
                cash += proceeds
                positions[instrument] = current_position - quantity
                old_value = values.get(instrument, Decimal("0"))
                reduction = min(old_value, quote.price * quantity)
                values[instrument] = max(Decimal("0"), old_value - reduction)
                projected_total = max(Decimal("0"), projected_total - reduction)
                industry = quote.industry or "__unknown__"
                industries[industry] = max(Decimal("0"), industries.get(industry, Decimal("0")) - reduction)

        if len(approved) == len(batch.intents):
            status = RiskDecisionStatus.APPROVED
        elif approved:
            status = RiskDecisionStatus.PARTIALLY_APPROVED
        else:
            status = RiskDecisionStatus.REJECTED
        return RiskDecision.from_batch(batch, decision_id=f"risk-{batch.batch_id}-{uuid.uuid4().hex[:8]}", policy_version=self.policy.policy_version, evaluated_at=current, status=status, approved_intent_keys=approved, rejected_intent_keys=rejected, reasons=reasons)

    def authorize(
        self,
        batch: OrderIntentBatch,
        account: AccountSnapshot,
        quotes: Mapping[str, QuoteSnapshot],
        *,
        fence_token: str,
        execution_run_id: str | None = None,
        now: datetime | None = None,
        ttl_seconds: int = 30,
    ) -> tuple[RiskDecision, ExecutionPermit | None]:
        if execution_run_id and batch.execution_run_id != execution_run_id:
            raise RiskContextMismatch("execution run mismatch")
        if self.db_path:
            ResearchFactsStore(self.db_path).validate_execution_run(batch.execution_run_id, now=now)
        decision = self.check_batch(batch, account, quotes, now=now)
        if decision.status is RiskDecisionStatus.REJECTED:
            self._persist_decision(decision, account.workspace_id)
            return decision, None
        current = _utc(now)
        permit = ExecutionPermit.from_decision(decision, permit_id=f"permit-{decision.decision_id}", expires_at=current.replace(microsecond=0) + __import__("datetime").timedelta(seconds=ttl_seconds), fence_token=fence_token, now=current)
        if self.db_path:
            self._persist_decision(decision, account.workspace_id)
            self._persist_permit(permit, account.workspace_id, current)
        return decision, permit

    def _persist_decision(self, decision: RiskDecision, workspace_id: str) -> None:
        if not self.db_path:
            return
        with get_connection(self.db_path) as connection:
            connection.execute("INSERT OR IGNORE INTO paper_risk_decisions(decision_id, execution_run_id, account_id, workspace_id, batch_id, policy_version, status, evaluated_intent_keys_json, approved_intent_keys_json, rejected_intent_keys_json, reasons_json, evaluated_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (decision.decision_id, decision.execution_run_id, decision.account_id, workspace_id, decision.batch_id, decision.policy_version, decision.status.value, __import__("json").dumps(decision.evaluated_intent_keys), __import__("json").dumps(decision.approved_intent_keys), __import__("json").dumps(decision.rejected_intent_keys), __import__("json").dumps(decision.reasons), decision.evaluated_at.isoformat(), _utc().isoformat()))
            connection.commit()

    def _persist_permit(self, permit: ExecutionPermit, workspace_id: str, created_at: datetime) -> None:
        with get_connection(self.db_path) as connection:
            connection.execute("INSERT OR REPLACE INTO paper_execution_permits(permit_id, decision_id, execution_run_id, account_id, workspace_id, batch_id, fence_token, idempotency_keys_json, expires_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (permit.permit_id, permit.decision_id, permit.execution_run_id, permit.account_id, workspace_id, permit.batch_id, permit.fence_token, __import__("json").dumps(permit.idempotency_keys), permit.expires_at.isoformat(), created_at.isoformat()))
            connection.commit()


def ensure_paper_account(db_path: str | Path, account_id: str, workspace_id: str = "default", initial_cash: Decimal | float = Decimal("50000")) -> None:
    with get_connection(db_path) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS paper_ledger (id INTEGER PRIMARY KEY AUTOINCREMENT, trade_id TEXT NOT NULL UNIQUE, execution_run_id TEXT NOT NULL, account_id TEXT NOT NULL, workspace_id TEXT NOT NULL DEFAULT 'default', environment TEXT NOT NULL DEFAULT 'paper' CHECK(environment = 'paper'), order_intent_key TEXT NOT NULL, idempotency_key TEXT NOT NULL, instrument TEXT NOT NULL, side TEXT NOT NULL, filled_price REAL NOT NULL, filled_volume INTEGER NOT NULL, commission REAL NOT NULL DEFAULT 0, stamp_tax REAL NOT NULL DEFAULT 0, slippage REAL NOT NULL DEFAULT 0, permit_id TEXT NOT NULL DEFAULT '', decision_id TEXT NOT NULL DEFAULT '', fence_token TEXT NOT NULL DEFAULT '', filled_at TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')))")
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_ledger_idempotency ON paper_ledger(account_id, workspace_id, environment, idempotency_key)")
        connection.execute("CREATE TABLE IF NOT EXISTS paper_accounts(account_id TEXT NOT NULL, workspace_id TEXT NOT NULL, environment TEXT NOT NULL CHECK(environment='paper'), initial_cash REAL NOT NULL, fence_token TEXT NOT NULL DEFAULT '1', PRIMARY KEY(workspace_id, account_id, environment))")
        connection.execute("INSERT OR IGNORE INTO paper_accounts(account_id, workspace_id, environment, initial_cash, fence_token) VALUES (?, ?, 'paper', ?, '1')", (account_id, workspace_id, float(initial_cash)))
        connection.commit()


def rebuild_account_snapshot(db_path: str | Path, account_id: str, workspace_id: str = "default", *, now: datetime | None = None, initial_cash: Decimal | float = Decimal("50000")) -> AccountSnapshot:
    ensure_paper_account(db_path, account_id, workspace_id, initial_cash)
    current = _utc(now)
    with get_connection(db_path) as connection:
        account = connection.execute("SELECT initial_cash, fence_token FROM paper_accounts WHERE account_id = ? AND workspace_id = ? AND environment = 'paper'", (account_id, workspace_id)).fetchone()
        if account is None:
            raise RiskGateError("paper account is not configured")
        rows = connection.execute("SELECT instrument, side, filled_price, filled_volume, commission, stamp_tax, filled_at FROM paper_ledger WHERE account_id = ? AND workspace_id = ? AND environment = 'paper' ORDER BY id", (account_id, workspace_id)).fetchall()
    initial = _decimal(account["initial_cash"], "initial_cash")
    cash = initial
    positions: dict[str, Decimal] = {}
    avg_prices: dict[str, Decimal] = {}
    today_buys: set[str] = set()
    for row in rows:
        instrument = row["instrument"]
        side = _side(row["side"])
        price = _decimal(row["filled_price"], "filled_price")
        volume = _decimal(row["filled_volume"], "filled_volume")
        commission = _decimal(row["commission"] or 0, "commission")
        stamp_tax = _decimal(row["stamp_tax"] or 0, "stamp_tax")
        if side is Side.BUY:
            cash -= price * volume + commission
            old = positions.get(instrument, Decimal("0"))
            avg_prices[instrument] = ((avg_prices.get(instrument, price) * old) + price * volume) / (old + volume)
            positions[instrument] = old + volume
            if _utc(row["filled_at"]).date() == current.date():
                today_buys.add(instrument)
        else:
            cash += price * volume - commission - stamp_tax
            positions[instrument] = positions.get(instrument, Decimal("0")) - volume
            if positions[instrument] <= 0:
                positions.pop(instrument, None)
                avg_prices.pop(instrument, None)
    position_values = {instrument: avg_prices[instrument] * quantity for instrument, quantity in positions.items()}
    total_equity = cash + sum(position_values.values(), Decimal("0"))
    return AccountSnapshot(account_id, workspace_id, Environment.PAPER, initial, cash, total_equity, positions, position_values, avg_prices, frozenset(today_buys), {}, str(account["fence_token"]))


__all__ = ["AccountSnapshot", "QuoteSnapshot", "RiskGate", "RiskGateError", "RiskPolicy", "RiskContextMismatch", "ensure_paper_account", "rebuild_account_snapshot"]
