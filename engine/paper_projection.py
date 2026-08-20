"""SQLite-backed Paper projections rebuilt exclusively from ``paper_ledger``.

The ledger is immutable execution evidence.  Everything in this module is a
rebuildable read model; projection failures create a reconciliation case and
never modify ledger rows.  The implementation intentionally stays SQLite-only
so isolated restore and deterministic replay use the same code path.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence

from engine.execution_protocol import Environment, Side
from utils.db import get_connection


class ProjectionError(RuntimeError):
    """Raised when authoritative ledger data cannot be folded safely."""


class ReconciliationRequired(ProjectionError):
    """Raised when a projection or runtime diverges from immutable facts."""


PROJECTION_VERSION = "paper-ledger-v1"
RECONCILIATION_STATUSES = frozenset({"open", "acknowledged", "resolved", "blocked"})


@dataclass(frozen=True)
class LedgerFold:
    account_id: str
    workspace_id: str
    environment: str
    execution_run_id: str | None
    initial_cash: Decimal
    cash: Decimal
    positions: Mapping[str, Decimal]
    avg_prices: Mapping[str, Decimal]
    today_buys: frozenset[str]
    realized_pnl: Decimal
    total_commission: Decimal
    total_stamp_tax: Decimal
    ledger_count: int
    last_ledger_id: int | None
    last_filled_at: str | None

    @property
    def position_cost(self) -> Decimal:
        return sum((self.avg_prices[code] * quantity for code, quantity in self.positions.items()), Decimal("0"))

    @property
    def content_hash(self) -> str:
        payload = {
            "account_id": self.account_id,
            "workspace_id": self.workspace_id,
            "environment": self.environment,
            "execution_run_id": self.execution_run_id,
            "initial_cash": str(self.initial_cash),
            "cash": str(self.cash),
            "positions": {key: str(value) for key, value in sorted(self.positions.items())},
            "avg_prices": {key: str(value) for key, value in sorted(self.avg_prices.items())},
            "today_buys": sorted(self.today_buys),
            "realized_pnl": str(self.realized_pnl),
            "ledger_count": self.ledger_count,
            "last_ledger_id": self.last_ledger_id,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _decimal(value: Any, field: str) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ProjectionError(f"{field} is not numeric") from exc
    if not result.is_finite():
        raise ProjectionError(f"{field} is not finite")
    return result


def _side(value: Any) -> Side:
    normalized = str(value).strip().lower().split(".")[-1]
    try:
        return Side(normalized)
    except ValueError as exc:
        raise ProjectionError(f"unsupported ledger side: {value!r}") from exc


def _utc(value: datetime | str | None = None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ProjectionError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def fold_ledger(
    rows: Sequence[Mapping[str, Any]],
    *,
    account_id: str,
    workspace_id: str = "default",
    environment: str = "paper",
    execution_run_id: str | None = None,
    initial_cash: Decimal | float | int = Decimal("50000"),
    now: datetime | str | None = None,
) -> LedgerFold:
    """Fold ledger rows deterministically into account state.

    Rows must already be scoped to one account/workspace/environment.  The
    explicit checks here prevent a malformed restore from silently combining
    accounts or runs.
    """
    if environment != Environment.PAPER.value:
        raise ProjectionError("only paper projections are supported")
    current = _utc(now)
    initial = _decimal(initial_cash, "initial_cash")
    cash = initial
    positions: dict[str, Decimal] = {}
    avg_prices: dict[str, Decimal] = {}
    today_buys: set[str] = set()
    realized = Decimal("0")
    commission_total = Decimal("0")
    stamp_total = Decimal("0")
    last_id: int | None = None
    last_filled_at: str | None = None

    for row in rows:
        if row["account_id"] != account_id or row["workspace_id"] != workspace_id or row["environment"] != environment:
            raise ProjectionError("ledger row crosses projection scope")
        row_run = row.get("execution_run_id") if hasattr(row, "get") else row["execution_run_id"]
        if execution_run_id is not None and row_run != execution_run_id:
            raise ProjectionError("ledger row crosses execution run scope")
        instrument = str(row["instrument"] or "").strip()
        if not instrument:
            raise ProjectionError("ledger instrument is empty")
        price = _decimal(row["filled_price"], "filled_price")
        volume = _decimal(row["filled_volume"], "filled_volume")
        if price <= 0 or volume <= 0 or volume != volume.to_integral_value():
            raise ProjectionError("ledger fill has invalid price or volume")
        fee = _decimal(row["commission"] or 0, "commission")
        tax = _decimal(row["stamp_tax"] or 0, "stamp_tax")
        side = _side(row["side"])
        if side is Side.BUY:
            old_quantity = positions.get(instrument, Decimal("0"))
            old_average = avg_prices.get(instrument, Decimal("0"))
            new_quantity = old_quantity + volume
            avg_prices[instrument] = ((old_average * old_quantity) + (price * volume)) / new_quantity
            positions[instrument] = new_quantity
            cash -= price * volume + fee
            try:
                if _utc(row["filled_at"]).date() == current.date():
                    today_buys.add(instrument)
            except (KeyError, TypeError, ValueError):
                raise ProjectionError("ledger filled_at is invalid")
        else:
            old_quantity = positions.get(instrument, Decimal("0"))
            if volume > old_quantity:
                raise ProjectionError(f"ledger sell exceeds position for {instrument}")
            average = avg_prices.get(instrument, Decimal("0"))
            realized += (price - average) * volume - fee - tax
            cash += price * volume - fee - tax
            remaining = old_quantity - volume
            if remaining <= 0:
                positions.pop(instrument, None)
                avg_prices.pop(instrument, None)
            else:
                positions[instrument] = remaining
        commission_total += fee
        stamp_total += tax
        raw_id = row.get("id") if hasattr(row, "get") else row["id"]
        last_id = int(raw_id) if raw_id is not None else last_id
        last_filled_at = str(row["filled_at"])

    return LedgerFold(
        account_id=account_id,
        workspace_id=workspace_id,
        environment=environment,
        execution_run_id=execution_run_id,
        initial_cash=initial,
        cash=cash,
        positions=dict(positions),
        avg_prices=dict(avg_prices),
        today_buys=frozenset(today_buys),
        realized_pnl=realized,
        total_commission=commission_total,
        total_stamp_tax=stamp_total,
        ledger_count=len(rows),
        last_ledger_id=last_id,
        last_filled_at=last_filled_at,
    )


def ensure_projection_schema(db_path: str | Path, connection: sqlite3.Connection | None = None) -> None:
    """Create scoped projection and reconciliation tables idempotently."""
    if connection is not None:
        _ensure_projection_schema_connection(connection)
        connection.commit()
        return
    with get_connection(db_path) as owned_connection:
        _ensure_projection_schema_connection(owned_connection)
        owned_connection.commit()


def _ensure_projection_schema_connection(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS paper_positions_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            environment TEXT NOT NULL CHECK(environment = 'paper'),
            execution_run_id TEXT NOT NULL,
            code TEXT NOT NULL,
            volume INTEGER NOT NULL,
            avg_price REAL NOT NULL,
            current_price REAL NOT NULL DEFAULT 0,
            market_value REAL NOT NULL DEFAULT 0,
            unrealized_pnl REAL NOT NULL DEFAULT 0,
            unrealized_pnl_pct REAL NOT NULL DEFAULT 0,
            source_ledger_id INTEGER,
            projection_version TEXT NOT NULL,
            marked_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(workspace_id, account_id, environment, execution_run_id, code)
        );
        CREATE TABLE IF NOT EXISTS paper_trades_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ledger_id INTEGER NOT NULL,
            workspace_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            environment TEXT NOT NULL CHECK(environment = 'paper'),
            execution_run_id TEXT NOT NULL,
            trade_id TEXT NOT NULL,
            code TEXT NOT NULL,
            direction TEXT NOT NULL,
            price REAL NOT NULL,
            volume INTEGER NOT NULL,
            commission REAL NOT NULL DEFAULT 0,
            stamp_tax REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            UNIQUE(workspace_id, account_id, environment, execution_run_id, ledger_id)
        );
        CREATE TABLE IF NOT EXISTS paper_equity_curve_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            environment TEXT NOT NULL CHECK(environment = 'paper'),
            execution_run_id TEXT NOT NULL,
            ledger_id INTEGER,
            timestamp TEXT NOT NULL,
            equity REAL NOT NULL,
            cash REAL NOT NULL,
            market_value REAL NOT NULL,
            drawdown REAL NOT NULL DEFAULT 0,
            projection_version TEXT NOT NULL,
            UNIQUE(workspace_id, account_id, environment, execution_run_id, ledger_id, timestamp)
        );
        CREATE TABLE IF NOT EXISTS paper_performance_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            environment TEXT NOT NULL CHECK(environment = 'paper'),
            execution_run_id TEXT NOT NULL,
            date TEXT NOT NULL,
            total_equity REAL NOT NULL,
            daily_return REAL NOT NULL DEFAULT 0,
            cumulative_return REAL NOT NULL DEFAULT 0,
            max_drawdown REAL NOT NULL DEFAULT 0,
            total_trades INTEGER NOT NULL DEFAULT 0,
            winning_trades INTEGER NOT NULL DEFAULT 0,
            losing_trades INTEGER NOT NULL DEFAULT 0,
            projection_version TEXT NOT NULL,
            UNIQUE(workspace_id, account_id, environment, execution_run_id, date)
        );
        CREATE TABLE IF NOT EXISTS paper_position_controls (
            workspace_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            environment TEXT NOT NULL CHECK(environment = 'paper'),
            execution_run_id TEXT NOT NULL,
            code TEXT NOT NULL,
            stop_loss_price REAL,
            take_profit_price REAL,
            max_position_pct REAL NOT NULL DEFAULT 0.3,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(workspace_id, account_id, environment, execution_run_id, code)
        );
        CREATE TABLE IF NOT EXISTS paper_projection_checkpoints (
            projection_name TEXT NOT NULL,
            workspace_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            environment TEXT NOT NULL CHECK(environment = 'paper'),
            execution_run_id TEXT NOT NULL,
            last_ledger_id INTEGER,
            ledger_count INTEGER NOT NULL,
            content_hash TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('ready', 'rebuilding', 'failed', 'reconciliation_required')),
            updated_at TEXT NOT NULL,
            PRIMARY KEY(projection_name, workspace_id, account_id, environment, execution_run_id)
        );
        CREATE TABLE IF NOT EXISTS paper_reconciliations (
            reconciliation_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            environment TEXT NOT NULL CHECK(environment = 'paper'),
            execution_run_id TEXT NOT NULL,
            category TEXT NOT NULL,
            source_reference TEXT NOT NULL,
            expected_hash TEXT,
            observed_hash TEXT,
            reason TEXT NOT NULL,
            owner_id TEXT,
            fence_token TEXT,
            status TEXT NOT NULL CHECK(status IN ('open', 'acknowledged', 'resolved', 'blocked')),
            created_at TEXT NOT NULL,
            acknowledged_at TEXT,
            resolved_at TEXT
        );
        CREATE TABLE IF NOT EXISTS paper_reconciliation_events (
            event_id TEXT PRIMARY KEY,
            reconciliation_id TEXT NOT NULL,
            from_status TEXT,
            to_status TEXT NOT NULL,
            reason TEXT NOT NULL,
            owner_id TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_paper_recon_events_case ON paper_reconciliation_events(reconciliation_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_paper_recon_scope ON paper_reconciliations(workspace_id, account_id, execution_run_id, status);
        """
    )




def _ledger_rows(connection: sqlite3.Connection, account_id: str, workspace_id: str, execution_run_id: str | None) -> list[sqlite3.Row]:
    params: list[Any] = [account_id, workspace_id, Environment.PAPER.value]
    where = "account_id = ? AND workspace_id = ? AND environment = ?"
    if execution_run_id is not None:
        where += " AND execution_run_id = ?"
        params.append(execution_run_id)
    return connection.execute(f"SELECT * FROM paper_ledger WHERE {where} ORDER BY id", params).fetchall()


def _current_quote_price(quotes: Mapping[str, Any] | None, code: str, fallback: Decimal) -> Decimal:
    if not quotes or code not in quotes:
        return fallback
    value = quotes[code]
    if hasattr(value, "price"):
        value = value.price
    elif isinstance(value, Mapping):
        value = value.get("price", fallback)
    return _decimal(value, f"quote[{code}]")


def load_ledger_fold(
    db_path: str | Path,
    *,
    account_id: str,
    workspace_id: str = "default",
    execution_run_id: str | None = None,
    initial_cash: Decimal | float | int = Decimal("50000"),
    now: datetime | str | None = None,
) -> LedgerFold:
    ensure_projection_schema(db_path)
    with get_connection(db_path) as connection:
        rows = _ledger_rows(connection, account_id, workspace_id, execution_run_id)
    return fold_ledger(rows, account_id=account_id, workspace_id=workspace_id, execution_run_id=execution_run_id, initial_cash=initial_cash, now=now)

def rebuild_account_projections(
    db_path: str | Path,
    *,
    account_id: str,
    workspace_id: str = "default",
    execution_run_id: str,
    initial_cash: Decimal | float | int = Decimal("50000"),
    quotes: Mapping[str, Any] | None = None,
    now: datetime | str | None = None,
    projection_version: str = PROJECTION_VERSION,
) -> LedgerFold:
    """Rebuild all V2 read models from immutable ledger rows in one transaction."""
    ensure_projection_schema(db_path)
    marked_at = _utc(now).isoformat()
    with get_connection(db_path) as connection:
        rows = _ledger_rows(connection, account_id, workspace_id, execution_run_id)
        folded = fold_ledger(rows, account_id=account_id, workspace_id=workspace_id, execution_run_id=execution_run_id, initial_cash=initial_cash, now=now)
        scope = (workspace_id, account_id, Environment.PAPER.value, execution_run_id)
        connection.execute("BEGIN IMMEDIATE")
        try:
            for table in ("paper_positions_v2", "paper_trades_v2", "paper_equity_curve_v2", "paper_performance_v2"):
                connection.execute(f"DELETE FROM {table} WHERE workspace_id = ? AND account_id = ? AND environment = ? AND execution_run_id = ?", scope)
            for code, quantity in folded.positions.items():
                average = folded.avg_prices[code]
                current = _current_quote_price(quotes, code, average)
                value = current * quantity
                pnl = (current - average) * quantity
                connection.execute("INSERT INTO paper_positions_v2(workspace_id, account_id, environment, execution_run_id, code, volume, avg_price, current_price, market_value, unrealized_pnl, unrealized_pnl_pct, source_ledger_id, projection_version, marked_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (*scope, code, int(quantity), float(average), float(current), float(value), float(pnl), float((current / average - 1) if average else 0), folded.last_ledger_id, projection_version, marked_at, marked_at))
            for row in rows:
                connection.execute("INSERT INTO paper_trades_v2(ledger_id, workspace_id, account_id, environment, execution_run_id, trade_id, code, direction, price, volume, commission, stamp_tax, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (row["id"], row["workspace_id"], row["account_id"], row["environment"], row["execution_run_id"], row["trade_id"], row["instrument"], str(row["side"]).lower().split(".")[-1], row["filled_price"], row["filled_volume"], row["commission"] or 0, row["stamp_tax"] or 0, row["filled_at"]))
            current_market = sum((_current_quote_price(quotes, code, average) * quantity for code, quantity in folded.positions.items()), Decimal("0"))
            equity = folded.cash + current_market
            connection.execute("INSERT INTO paper_equity_curve_v2(workspace_id, account_id, environment, execution_run_id, ledger_id, timestamp, equity, cash, market_value, drawdown, projection_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (*scope, folded.last_ledger_id, marked_at, float(equity), float(folded.cash), float(current_market), 0.0, projection_version))
            trade_count = len(rows)
            wins = 0
            losses = 0
            for row in rows:
                if str(row["side"]).lower().split(".")[-1] == "sell":
                    wins += 1 if row["filled_price"] > 0 else 0
                    losses += 0 if row["filled_price"] > 0 else 1
            day = marked_at[:10]
            connection.execute("INSERT INTO paper_performance_v2(workspace_id, account_id, environment, execution_run_id, date, total_equity, daily_return, cumulative_return, max_drawdown, total_trades, winning_trades, losing_trades, projection_version) VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, ?, ?, ?, ?)", (*scope, day, float(equity), trade_count, wins, losses, projection_version))
            connection.execute("INSERT OR REPLACE INTO paper_projection_checkpoints(projection_name, workspace_id, account_id, environment, execution_run_id, last_ledger_id, ledger_count, content_hash, status, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ready', ?)", ("paper", *scope, folded.last_ledger_id, folded.ledger_count, folded.content_hash, marked_at))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return folded


def open_reconciliation(
    db_path: str | Path,
    *,
    account_id: str,
    workspace_id: str = "default",
    execution_run_id: str,
    category: str,
    reason: str,
    source_reference: str = "paper_ledger",
    expected_hash: str | None = None,
    observed_hash: str | None = None,
    owner_id: str | None = None,
    fence_token: str | None = None,
    reconciliation_id: str | None = None,
) -> str:
    ensure_projection_schema(db_path)
    current = _utc().isoformat()
    reconciliation_id = reconciliation_id or f"recon-{account_id}-{execution_run_id}-{hashlib.sha256((category + reason + current).encode()).hexdigest()[:16]}"
    with get_connection(db_path) as connection:
        connection.execute("INSERT OR IGNORE INTO paper_reconciliations(reconciliation_id, workspace_id, account_id, environment, execution_run_id, category, source_reference, expected_hash, observed_hash, reason, owner_id, fence_token, status, created_at) VALUES (?, ?, ?, 'paper', ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)", (reconciliation_id, workspace_id, account_id, execution_run_id, category, source_reference, expected_hash, observed_hash, reason, owner_id, fence_token, current))
        connection.execute("INSERT OR IGNORE INTO paper_reconciliation_events(event_id, reconciliation_id, from_status, to_status, reason, owner_id, created_at) VALUES (?, ?, NULL, 'open', ?, ?, ?)", (f"{reconciliation_id}:open", reconciliation_id, reason, owner_id, current))
        connection.execute("INSERT OR REPLACE INTO paper_projection_checkpoints(projection_name, workspace_id, account_id, environment, execution_run_id, last_ledger_id, ledger_count, content_hash, status, updated_at) SELECT 'paper', workspace_id, account_id, environment, execution_run_id, last_ledger_id, ledger_count, content_hash, 'reconciliation_required', ? FROM paper_projection_checkpoints WHERE workspace_id = ? AND account_id = ? AND environment = 'paper' AND execution_run_id = ?", (current, workspace_id, account_id, execution_run_id))
        connection.commit()
    return reconciliation_id


def reconcile_account(db_path: str | Path, *, account_id: str, workspace_id: str = "default", execution_run_id: str, initial_cash: Decimal | float | int = Decimal("50000"), now: datetime | str | None = None) -> dict[str, Any]:
    ensure_projection_schema(db_path)
    with get_connection(db_path) as connection:
        rows = _ledger_rows(connection, account_id, workspace_id, execution_run_id)
        folded = fold_ledger(rows, account_id=account_id, workspace_id=workspace_id, execution_run_id=execution_run_id, initial_cash=initial_cash, now=now)
        checkpoint = connection.execute("SELECT * FROM paper_projection_checkpoints WHERE projection_name = 'paper' AND workspace_id = ? AND account_id = ? AND environment = 'paper' AND execution_run_id = ?", (workspace_id, account_id, execution_run_id)).fetchone()
        positions = connection.execute("SELECT code, volume, avg_price FROM paper_positions_v2 WHERE workspace_id = ? AND account_id = ? AND environment = 'paper' AND execution_run_id = ? ORDER BY code", (workspace_id, account_id, execution_run_id)).fetchall()
        observed = {row["code"]: (Decimal(str(row["volume"])), Decimal(str(row["avg_price"]))) for row in positions}
        expected = {code: (quantity, folded.avg_prices[code]) for code, quantity in folded.positions.items()}
        categories: list[str] = []
        if observed != expected:
            categories.append("projection_position_divergence")
        if checkpoint is None or int(checkpoint["ledger_count"]) != folded.ledger_count or checkpoint["content_hash"] != folded.content_hash:
            categories.append("projection_checkpoint_divergence")
        if categories:
            case = open_reconciliation(db_path, account_id=account_id, workspace_id=workspace_id, execution_run_id=execution_run_id, category=categories[0], reason=";".join(categories), expected_hash=folded.content_hash, observed_hash=checkpoint["content_hash"] if checkpoint else None)
            return {"status": "reconciliation_required", "categories": categories, "reconciliation_id": case, "ledger_count": folded.ledger_count}
        return {"status": "consistent", "categories": [], "ledger_count": folded.ledger_count, "content_hash": folded.content_hash}


def list_reconciliations(db_path: str | Path, *, account_id: str | None = None, workspace_id: str | None = None, execution_run_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
    ensure_projection_schema(db_path)
    clauses: list[str] = []
    params: list[Any] = []
    for field, value in (("account_id", account_id), ("workspace_id", workspace_id), ("execution_run_id", execution_run_id), ("status", status)):
        if value is not None:
            clauses.append(f"{field} = ?")
            params.append(value)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    with get_connection(db_path) as connection:
        rows = connection.execute(f"SELECT * FROM paper_reconciliations {where} ORDER BY created_at DESC", params).fetchall()
    return [dict(row) for row in rows]


def transition_reconciliation(db_path: str | Path, reconciliation_id: str, target_status: str, *, owner_id: str | None = None) -> dict[str, Any]:
    if target_status not in RECONCILIATION_STATUSES:
        raise ValueError(f"unsupported reconciliation status: {target_status}")
    now = _utc().isoformat()
    with get_connection(db_path) as connection:
        row = connection.execute("SELECT * FROM paper_reconciliations WHERE reconciliation_id = ?", (reconciliation_id,)).fetchone()
        if row is None:
            raise ReconciliationRequired(f"reconciliation case not found: {reconciliation_id}")
        current = row["status"]
        legal = {"open": {"acknowledged", "resolved", "blocked"}, "acknowledged": {"resolved", "blocked"}, "blocked": {"acknowledged", "resolved"}, "resolved": set()}
        if target_status != current and target_status not in legal.get(current, set()):
            raise ReconciliationRequired(f"illegal reconciliation transition {current} -> {target_status}")
        connection.execute("UPDATE paper_reconciliations SET status = ?, owner_id = COALESCE(?, owner_id), acknowledged_at = CASE WHEN ? = 'acknowledged' THEN ? ELSE acknowledged_at END, resolved_at = CASE WHEN ? = 'resolved' THEN ? ELSE resolved_at END WHERE reconciliation_id = ?", (target_status, owner_id, target_status, now, target_status, now, reconciliation_id))
        event_id = f"{reconciliation_id}:{hashlib.sha256((current + target_status + str(owner_id)).encode()).hexdigest()[:16]}"
        connection.execute("INSERT OR IGNORE INTO paper_reconciliation_events(event_id, reconciliation_id, from_status, to_status, reason, owner_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (event_id, reconciliation_id, current, target_status, f"transition {current} -> {target_status}", owner_id, now))
        connection.commit()
        return dict(connection.execute("SELECT * FROM paper_reconciliations WHERE reconciliation_id = ?", (reconciliation_id,)).fetchone())


__all__ = ["LedgerFold", "ProjectionError", "ReconciliationRequired", "PROJECTION_VERSION", "RECONCILIATION_STATUSES", "ensure_projection_schema", "fold_ledger", "load_ledger_fold", "rebuild_account_projections", "open_reconciliation", "reconcile_account", "list_reconciliations", "transition_reconciliation"]
