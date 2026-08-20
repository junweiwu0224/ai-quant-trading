from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from engine.paper_projection import fold_ledger, rebuild_account_projections, reconcile_account
from engine.research_facts import ResearchFactsStore
from engine.risk_gate import ensure_paper_account


def _run(db: Path, account: str, workspace: str, cash: float = 10_000.0) -> str:
    return ResearchFactsStore(db).ensure_paper_run(account_id=account, workspace_id=workspace, codes=["000001"], initial_cash=cash).execution_run_id


def _ledger(db: Path, run: str, account: str, workspace: str, rows: list[tuple[str, str, float, int, float, float]]) -> None:
    ensure_paper_account(db, account, workspace, 10_000)
    with sqlite3.connect(db) as connection:
        for index, (side, code, price, volume, commission, tax) in enumerate(rows, 1):
            connection.execute("INSERT INTO paper_ledger(trade_id, execution_run_id, account_id, workspace_id, environment, order_intent_key, idempotency_key, instrument, side, filled_price, filled_volume, commission, stamp_tax, filled_at) VALUES (?, ?, ?, ?, 'paper', ?, ?, ?, ?, ?, ?, ?, ?, ?)", (f"trade-{index}-{run}", run, account, workspace, f"key-{index}-{run}", f"key-{index}-{run}", code, side, price, volume, commission, tax, datetime.now(timezone.utc).isoformat()))
        connection.commit()


def test_fold_buy_sell_cash_average_and_t1(tmp_path: Path):
    rows = [
        {"id": 1, "account_id": "a", "workspace_id": "w", "environment": "paper", "execution_run_id": "run", "instrument": "000001", "side": "buy", "filled_price": 10, "filled_volume": 100, "commission": 5, "stamp_tax": 0, "filled_at": datetime.now(timezone.utc).isoformat()},
        {"id": 2, "account_id": "a", "workspace_id": "w", "environment": "paper", "execution_run_id": "run", "instrument": "000001", "side": "buy", "filled_price": 12, "filled_volume": 100, "commission": 5, "stamp_tax": 0, "filled_at": datetime.now(timezone.utc).isoformat()},
    ]
    folded = fold_ledger(rows, account_id="a", workspace_id="w", execution_run_id="run", initial_cash=10_000)
    assert folded.cash == 7790
    assert folded.positions["000001"] == 200
    assert folded.avg_prices["000001"] == 11
    assert "000001" in folded.today_buys


def test_projection_rebuild_isolated_and_recoverable(tmp_path: Path):
    db = tmp_path / "paper.db"
    run_a = _run(db, "a", "w")
    run_b = _run(db, "b", "w")
    _ledger(db, run_a, "a", "w", [("buy", "000001", 10, 100, 5, 0)])
    _ledger(db, run_b, "b", "w", [("buy", "000002", 20, 100, 5, 0)])
    rebuild_account_projections(db, account_id="a", workspace_id="w", execution_run_id=run_a, initial_cash=10_000)
    rebuild_account_projections(db, account_id="b", workspace_id="w", execution_run_id=run_b, initial_cash=10_000)
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT code FROM paper_positions_v2 WHERE account_id = 'a'").fetchone()[0] == "000001"
        connection.execute("DELETE FROM paper_positions_v2 WHERE account_id = 'a'")
        connection.commit()
    rebuild_account_projections(db, account_id="a", workspace_id="w", execution_run_id=run_a, initial_cash=10_000)
    assert reconcile_account(db, account_id="a", workspace_id="w", execution_run_id=run_a, initial_cash=10_000)["status"] == "consistent"
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM paper_ledger WHERE account_id = 'a'").fetchone()[0] == 1
        assert connection.execute("SELECT code FROM paper_positions_v2 WHERE account_id = 'b'").fetchone()[0] == "000002"


def test_projection_divergence_opens_reconciliation(tmp_path: Path):
    db = tmp_path / "paper.db"
    run = _run(db, "a", "w")
    _ledger(db, run, "a", "w", [("buy", "000001", 10, 100, 5, 0)])
    rebuild_account_projections(db, account_id="a", workspace_id="w", execution_run_id=run, initial_cash=10_000)
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE paper_positions_v2 SET volume = 1 WHERE account_id = 'a'")
        connection.commit()
    result = reconcile_account(db, account_id="a", workspace_id="w", execution_run_id=run, initial_cash=10_000)
    assert result["status"] == "reconciliation_required"
    assert "projection_position_divergence" in result["categories"]
