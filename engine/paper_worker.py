"""PaperWorker: sole owner and executor of Paper trading commands.

This worker consumes Paper commands from OperationsStore, holds exclusive
account-level leases, and delegates execution to PaperEngine. It is the
only entry point for Paper execution in V2 architecture.
"""

from __future__ import annotations

import signal
import sys
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from loguru import logger

from data.collector.quote_service import get_quote_service
from engine.adapters.paper_adapter import PaperAdapter, QuoteSnapshot as AdapterQuoteSnapshot
from engine.execution_protocol import OrderIntentBatch, OrderIntent
from engine.risk_gate import RiskGate, RiskPolicy, QuoteSnapshot as RiskQuoteSnapshot, rebuild_account_snapshot
from engine.research_facts import ResearchFactsStore
from engine.operations_store import (
    Attempt,
    LeaseLostError,
    OperationsStore,
    TaskNotClaimableError,
)
from engine.paper_engine import PaperConfig, PaperEngine
from engine.paper_ownership import PaperOwnership
from strategy.base import BaseStrategy
from strategy.dual_ma import DualMAStrategy


@dataclass
class PaperWorkerConfig:
    """Configuration for PaperWorker."""

    operations_db: str | Path
    lease_db: str | Path
    poll_interval_seconds: float = 5.0
    lease_ttl_seconds: float = 30.0
    task_lease_seconds: float = 300.0
    worker_id: str | None = None
    paper_db: str | Path | None = None
    workspace_id: str = "default"


class PaperWorker:
    """Sole Paper execution owner: claims tasks, holds leases, executes commands."""

    def __init__(self, config: PaperWorkerConfig):
        self.config = config
        self.worker_id = config.worker_id or f"paper-worker-{time.time_ns()}"
        self.operations = OperationsStore(config.operations_db)
        self.paper_db = str(config.paper_db or config.operations_db)
        self.facts = ResearchFactsStore(self.paper_db)
        self.running = False
        self._engines: dict[str, PaperEngine] = {}
        self._ownerships: dict[str, PaperOwnership] = {}
        self._stop_requested = False

    def start(self) -> None:
        """Start the worker loop."""
        self.running = True
        logger.info(f"PaperWorker {self.worker_id} starting")

        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        while self.running and not self._stop_requested:
            try:
                self._poll_and_execute()
            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt")
                break
            except Exception as e:
                logger.error(f"Worker loop error: {e}", exc_info=True)

            time.sleep(self.config.poll_interval_seconds)

        self._cleanup()
        logger.info("PaperWorker stopped")

    def stop(self) -> None:
        """Request worker to stop."""
        self.running = False
        self._stop_requested = True

    def _handle_signal(self, signum: int, _frame: Any) -> None:
        logger.info(f"Received signal {signum}, stopping worker")
        self.stop()

    def _poll_and_execute(self) -> None:
        """Poll for a task and execute it."""
        try:
            attempt = self.operations.claim_task(
                self.worker_id,
                lease_seconds=self.config.task_lease_seconds,
                allowed_kinds=[
                    "paper_start",
                    "paper_stop",
                    "paper_adjust_position",
                    "execute_manual_order",
                    "paper_execute_batch",
                ],
            )
        except TaskNotClaimableError:
            return

        logger.info(f"Claimed task {attempt.task_id}, attempt {attempt.id}")

        try:
            task = self.operations.get_task(attempt.task_id)
            if task is None:
                raise RuntimeError(f"Task {attempt.task_id} not found")
            command = self.operations.get_command(task.command_id)
            if command is None:
                raise RuntimeError(f"Command {task.command_id} not found")
            self._execute_command(attempt, command.kind, command.payload)
        except LeaseLostError:
            logger.warning(f"Lease lost for task {attempt.task_id}")
        except Exception as e:
            logger.error(f"Task {attempt.task_id} failed: {e}", exc_info=True)
            self.operations.fail_attempt(
                attempt.id,
                owner_id=self.worker_id,
                fence=attempt.fence,
                lease_token=attempt.lease_token,
                error=str(e),
            )

    def _execute_command(self, attempt: Attempt, kind: str, payload: dict[str, Any]) -> None:
        """Execute a single command."""
        if kind == "paper_start":
            self._handle_start(attempt, payload)
        elif kind == "paper_stop":
            self._handle_stop(attempt, payload)
        elif kind == "paper_adjust_position":
            self._handle_adjust_position(attempt, payload)
        elif kind in {"execute_manual_order", "paper_execute_batch"}:
            self._handle_execute_manual_order(attempt, payload)
        else:
            raise ValueError(f"Unknown command kind: {kind}")

    def _handle_start(self, attempt: Attempt, payload: dict[str, Any]) -> None:
        """Handle paper_start command: acquire lease and start PaperEngine."""
        account_id = payload.get("account_id", "paper-default")
        strategy_name = payload.get("strategy_name", payload.get("strategy", "dual_ma"))
        codes = payload.get("codes", [])
        initial_cash = payload.get("initial_cash", 1_000_000)
        interval_seconds = payload.get("interval_seconds", 30)

        if account_id in self._engines:
            self.operations.succeed_attempt(
                attempt.id,
                owner_id=self.worker_id,
                fence=attempt.fence,
                lease_token=attempt.lease_token,
            )
            logger.info(f"Account {account_id} already running")
            return

        # Acquire account-level Paper lease
        ownership = PaperOwnership(
            self.config.lease_db,
            account_id=account_id,
            owner_id=self.worker_id,
            ttl_seconds=self.config.lease_ttl_seconds,
        )
        lease = ownership.acquire()
        if lease is None:
            error = f"Account {account_id} is already owned by another worker"
            self.operations.fail_attempt(
                attempt.id,
                owner_id=self.worker_id,
                fence=attempt.fence,
                lease_token=attempt.lease_token,
                error=error,
            )
            ownership.close()
            raise RuntimeError(error)

        # Create strategy
        strategy = self._create_strategy(strategy_name)

        # Create PaperEngine
        config = PaperConfig(
            initial_cash=initial_cash,
            interval_seconds=interval_seconds,
            enable_risk=True,
            db_path=self.paper_db,
        )
        execution_run = self.facts.ensure_paper_run(
            account_id=account_id,
            workspace_id=self.config.workspace_id,
            strategy_id=strategy_name,
            codes=codes,
            initial_cash=initial_cash,
        )
        engine = PaperEngine(
            strategy=strategy,
            codes=codes,
            config=config,
            account_id=account_id,
            workspace_id=self.config.workspace_id,
            execution_run_id=execution_run.execution_run_id,
        )
        engine.strategy_name = strategy_name

        # Start heartbeat renewal
        ownership.start_renewal(on_lost=lambda: self._handle_lease_lost(account_id))

        # Store engine and ownership
        self._engines[account_id] = engine
        self._ownerships[account_id] = ownership

        # Mark task as succeeded
        self.operations.succeed_attempt(
            attempt.id,
            owner_id=self.worker_id,
            fence=attempt.fence,
            lease_token=attempt.lease_token,
        )

        logger.info(f"Started Paper engine for account {account_id}")

    def _handle_stop(self, attempt: Attempt, payload: dict[str, Any]) -> None:
        """Handle paper_stop command: stop PaperEngine and release lease."""
        account_id = payload.get("account_id", "paper-default")

        engine = self._engines.pop(account_id, None)
        ownership = self._ownerships.pop(account_id, None)

        if engine:
            engine.stop()
            logger.info(f"Stopped Paper engine for account {account_id}")

        if ownership:
            ownership.release()
            ownership.close()
            logger.info(f"Released lease for account {account_id}")

        self.operations.succeed_attempt(
            attempt.id,
            owner_id=self.worker_id,
            fence=attempt.fence,
            lease_token=attempt.lease_token,
        )

    def _handle_adjust_position(self, attempt: Attempt, payload: dict[str, Any]) -> None:
        """Block the legacy direct portfolio mutation path."""
        error = "paper_adjust_position is disabled; submit a paper_execute_batch command"
        self.operations.fail_attempt(
            attempt.id,
            owner_id=self.worker_id,
            fence=attempt.fence,
            lease_token=attempt.lease_token,
            error=error,
        )
        raise RuntimeError(error)

    def _handle_execute_manual_order(self, attempt: Attempt, payload: dict[str, Any]) -> None:
        """Re-evaluate an advisory batch immediately before execution."""
        batch_dict = payload.get("batch_dict")
        if not batch_dict:
            raise ValueError("Missing batch_dict in payload")
        proposed_batch = OrderIntentBatch.from_dict(batch_dict)
        run = self.facts.get_execution_run(proposed_batch.execution_run_id)
        if run is None:
            run = self.facts.ensure_paper_run(
                account_id=proposed_batch.account_id,
                workspace_id=self.config.workspace_id,
                codes=[intent.instrument for intent in proposed_batch.intents],
                execution_run_id=proposed_batch.execution_run_id,
            )
        intents = tuple(
            OrderIntent(
                execution_run_id=run.execution_run_id,
                account_id=proposed_batch.account_id,
                environment="paper",
                instrument=intent.instrument,
                side=intent.side,
                quantity=intent.quantity,
                idempotency_key=intent.idempotency_key,
                emergency=intent.emergency,
            )
            for intent in proposed_batch.intents
        )
        batch = OrderIntentBatch(batch_id=proposed_batch.batch_id, intents=intents)
        raw_quotes = payload.get("quotes")
        if raw_quotes is None:
            raw_quotes = get_quote_service().get_all_quotes()
        latest = {
            code: self._quote_from_value(code, value)
            for code, value in raw_quotes.items()
        }
        risk_quotes = {
            code: RiskQuoteSnapshot(
                instrument=quote.instrument,
                price=Decimal(str(quote.price)),
                timestamp=quote.timestamp,
                industry=quote.industry,
                limit_up=quote.limit_up,
                limit_down=quote.limit_down,
                is_suspended=quote.is_suspended,
            )
            for code, quote in latest.items()
        }
        account = rebuild_account_snapshot(
            self.paper_db,
            proposed_batch.account_id,
            self.config.workspace_id,
        )
        current_values = {
            code: quantity * risk_quotes[code].price
            for code, quantity in account.positions.items()
            if code in risk_quotes
        }
        account = replace(
            account,
            position_values=current_values,
            total_equity=account.cash + sum(current_values.values(), Decimal("0")),
        )
        gate = RiskGate(db_path=self.paper_db)
        _, permit = gate.authorize(
            batch,
            account,
            risk_quotes,
            fence_token=account.fence_token,
            execution_run_id=run.execution_run_id,
        )
        if permit is None:
            self.operations.succeed_attempt(
                attempt.id,
                owner_id=self.worker_id,
                fence=attempt.fence,
                lease_token=attempt.lease_token,
            )
            return
        adapter = PaperAdapter(db_path=self.paper_db, workspace_id=self.config.workspace_id)
        try:
            adapter_quotes = {
                code: AdapterQuoteSnapshot(
                    instrument=quote.instrument,
                    price=quote.price,
                    timestamp=quote.timestamp.isoformat(),
                    industry=quote.industry,
                    limit_up=float(quote.limit_up) if quote.limit_up is not None else None,
                    limit_down=float(quote.limit_down) if quote.limit_down is not None else None,
                    is_suspended=quote.is_suspended,
                )
                for code, quote in latest.items()
            }
            adapter.execute_batch(batch, permit, adapter_quotes, require_authoritative=True)
            self.operations.succeed_attempt(
                attempt.id,
                owner_id=self.worker_id,
                fence=attempt.fence,
                lease_token=attempt.lease_token,
            )
        except Exception as exc:
            self.operations.fail_attempt(
                attempt.id,
                owner_id=self.worker_id,
                fence=attempt.fence,
                lease_token=attempt.lease_token,
                error=str(exc),
            )
            raise
        finally:
            adapter.close()

    @staticmethod
    def _quote_from_value(code: str, value: Any) -> AdapterQuoteSnapshot:
        from datetime import datetime, timezone
        if isinstance(value, AdapterQuoteSnapshot):
            return value
        if isinstance(value, dict):
            price = value.get("price", 0)
            timestamp = value.get("timestamp")
            industry = value.get("industry", "")
            limit_up = value.get("limit_up")
            limit_down = value.get("limit_down")
            suspended = value.get("is_suspended", False)
        else:
            price = value.price
            timestamp = value.timestamp
            industry = getattr(value, "industry", "") or ""
            limit_up = getattr(value, "limit_up", None)
            limit_down = getattr(value, "limit_down", None)
            suspended = bool(getattr(value, "is_suspended", False))
        if isinstance(timestamp, (int, float)):
            timestamp = datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
        timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        return AdapterQuoteSnapshot(
            instrument=code,
            price=float(price),
            timestamp=str(timestamp),
            industry=str(industry),
            limit_up=float(limit_up) if limit_up is not None else None,
            limit_down=float(limit_down) if limit_down is not None else None,
            is_suspended=bool(suspended),
        )

    def _handle_lease_lost(self, account_id: str) -> None:
        """Handle lease loss: stop the engine and clean up."""
        logger.warning(f"Lease lost for account {account_id}, stopping engine")
        engine = self._engines.pop(account_id, None)
        if engine:
            engine.stop()
        ownership = self._ownerships.pop(account_id, None)
        if ownership:
            ownership.close()

    def _create_strategy(self, strategy_name: str) -> BaseStrategy:
        """Create a strategy instance by name."""
        # Only DualMAStrategy for now; expand as needed
        if strategy_name == "dual_ma":
            return DualMAStrategy()
        raise ValueError(f"Unknown strategy: {strategy_name}")

    def _cleanup(self) -> None:
        """Clean up all running engines and leases."""
        for account_id in list(self._engines.keys()):
            engine = self._engines.pop(account_id, None)
            if engine:
                engine.stop()
            ownership = self._ownerships.pop(account_id, None)
            if ownership:
                ownership.release()
                ownership.close()
        self.operations.close()


def main() -> None:
    """CLI entry point for PaperWorker."""
    import click
    from config.logging import setup_logging
    from config.settings import DB_DIR

    @click.command()
    @click.option("--operations-db", default=str(DB_DIR / "operations.db"), help="Operations database path")
    @click.option("--lease-db", default=str(DB_DIR / "worker_leases.db"), help="Lease database path")
    @click.option("--poll-interval", default=5.0, help="Poll interval in seconds")
    @click.option("--worker-id", default=None, help="Worker identifier")
    def cli(operations_db: str, lease_db: str, poll_interval: float, worker_id: str | None) -> None:
        """Start PaperWorker as sole Paper execution owner."""
        setup_logging()
        config = PaperWorkerConfig(
            operations_db=operations_db,
            lease_db=lease_db,
            poll_interval_seconds=poll_interval,
            worker_id=worker_id,
        )
        worker = PaperWorker(config)
        worker.start()

    cli()


if __name__ == "__main__":
    main()
