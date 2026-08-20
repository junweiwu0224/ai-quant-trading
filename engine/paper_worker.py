"""PaperWorker: sole owner and executor of Paper trading commands.

This worker consumes Paper commands from OperationsStore, holds exclusive
account-level leases, and delegates execution to PaperEngine. It is the
only entry point for Paper execution in V2 architecture.
"""

from __future__ import annotations

import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from engine.adapters.paper_adapter import PaperAdapter
from engine.execution_protocol import OrderIntentBatch, ExecutionPermit
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


class PaperWorker:
    """Sole Paper execution owner: claims tasks, holds leases, executes commands."""

    def __init__(self, config: PaperWorkerConfig):
        self.config = config
        self.worker_id = config.worker_id or f"paper-worker-{time.time_ns()}"
        self.operations = OperationsStore(config.operations_db)
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
        elif kind == "execute_manual_order":
            self._handle_execute_manual_order(attempt, payload)
        else:
            raise ValueError(f"Unknown command kind: {kind}")

    def _handle_start(self, attempt: Attempt, payload: dict[str, Any]) -> None:
        """Handle paper_start command: acquire lease and start PaperEngine."""
        account_id = payload.get("account_id", "paper-default")
        strategy_name = payload.get("strategy", "dual_ma")
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
        )
        engine = PaperEngine(strategy=strategy, codes=codes, config=config)
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
        """Handle paper_adjust_position command: delegate to PaperEngine."""
        account_id = payload.get("account_id", "paper-default")
        code = payload.get("code")
        direction = payload.get("direction")
        volume = payload.get("volume")

        engine = self._engines.get(account_id)
        if engine is None:
            error = f"Account {account_id} is not running"
            self.operations.fail_attempt(
                attempt.id,
                owner_id=self.worker_id,
                fence=attempt.fence,
                lease_token=attempt.lease_token,
                error=error,
            )
            raise RuntimeError(error)

        # Delegate to PaperEngine's portfolio/strategy
        # (In full V2, this would construct OrderIntentBatch and go through RiskGate)
        try:
            engine.portfolio.place_order(code, direction, volume)
            self.operations.succeed_attempt(
                attempt.id,
                owner_id=self.worker_id,
                fence=attempt.fence,
                lease_token=attempt.lease_token,
            )
            logger.info(f"Adjusted position for {account_id}: {code} {direction} {volume}")
        except Exception as e:
            self.operations.fail_attempt(
                attempt.id,
                owner_id=self.worker_id,
                fence=attempt.fence,
                lease_token=attempt.lease_token,
                error=str(e),
            )
            raise

    def _handle_execute_manual_order(self, attempt: Attempt, payload: dict[str, Any]) -> None:
        """Handle execute_manual_order command: V2 unified protocol execution."""
        batch_dict = payload.get("batch_dict")
        permit_dict = payload.get("permit_dict")

        if not batch_dict or not permit_dict:
            error = "Missing batch_dict or permit_dict in payload"
            self.operations.fail_attempt(
                attempt.id,
                owner_id=self.worker_id,
                fence=attempt.fence,
                lease_token=attempt.lease_token,
                error=error,
            )
            raise ValueError(error)

        # Reconstruct batch and permit from dicts
        batch = OrderIntentBatch.from_dict(batch_dict)
        permit = ExecutionPermit.from_dict(permit_dict)

        # Create PaperAdapter and execute
        adapter = PaperAdapter(db_path=self.config.operations_db)
        try:
            fills = adapter.execute_batch(batch=batch, permit=permit)
            self.operations.succeed_attempt(
                attempt.id,
                owner_id=self.worker_id,
                fence=attempt.fence,
                lease_token=attempt.lease_token,
            )
            logger.info(
                f"Executed manual order batch {batch.batch_id}: "
                f"{len(fills)} fills, {sum(f.quantity for f in fills)} total qty"
            )
        except Exception as e:
            self.operations.fail_attempt(
                attempt.id,
                owner_id=self.worker_id,
                fence=attempt.fence,
                lease_token=attempt.lease_token,
                error=str(e),
            )
            raise
        finally:
            adapter.close()

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
