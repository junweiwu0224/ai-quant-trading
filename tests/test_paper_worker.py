"""Tests for PaperWorker as sole Paper execution owner."""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from engine.operations_store import OperationsStore
from engine.paper_worker import PaperWorker, PaperWorkerConfig


@pytest.fixture
def operations_db(tmp_path: Path) -> Path:
    """Create a temporary operations database."""
    db_path = tmp_path / "operations.db"
    store = OperationsStore(str(db_path))
    store.close()
    return db_path


@pytest.fixture
def lease_db(tmp_path: Path) -> Path:
    """Create a temporary lease database."""
    return tmp_path / "leases.db"


@pytest.fixture
def worker_config(operations_db: Path, lease_db: Path) -> PaperWorkerConfig:
    """Create a PaperWorker configuration."""
    return PaperWorkerConfig(
        operations_db=str(operations_db),
        lease_db=str(lease_db),
        poll_interval_seconds=0.1,
        lease_ttl_seconds=10.0,
        task_lease_seconds=5.0,
        worker_id="test-worker",
    )


def test_worker_initialization(worker_config: PaperWorkerConfig) -> None:
    """Test PaperWorker initializes correctly."""
    worker = PaperWorker(worker_config)
    assert worker.config == worker_config
    assert worker.running is False
    assert worker._engines == {}
    assert worker._ownerships == {}


def test_worker_claims_paper_start_command(
    worker_config: PaperWorkerConfig, operations_db: Path
) -> None:
    """Test PaperWorker claims and executes paper_start command."""
    with patch("engine.paper_worker.PaperEngine") as mock_engine_class:
        mock_engine = MagicMock()
        mock_engine_class.return_value = mock_engine

        # Enqueue a paper_start command
        store = OperationsStore(str(operations_db))
        acceptance = store.accept_command(
            kind="paper_start",
            payload={
                "account_id": "test-account",
                "strategy_name": "dual_ma",
                "codes": ["000001.SZ"],
            },
            idempotency_key="test-start-1",
        )
        command_id = acceptance.command.id
        store.close()

        worker = PaperWorker(worker_config)
        worker._poll_and_execute()

        # Verify engine was created
        assert "test-account" in worker._engines
        assert worker._ownerships.get("test-account") is not None


def test_worker_only_claims_paper_commands(
    worker_config: PaperWorkerConfig, operations_db: Path
) -> None:
    """Test that PaperWorker only claims paper_* commands."""
    # Enqueue a non-paper command
    store = OperationsStore(str(operations_db))
    acceptance = store.accept_command(
        kind="backtest_run",
        payload={"strategy": "test"},
        idempotency_key="test-backtest-1",
    )
    command_id = acceptance.command.id
    store.close()

    worker = PaperWorker(worker_config)

    # Run one poll cycle
    worker._poll_and_execute()

    # Verify no engines were created
    assert len(worker._engines) == 0


def test_worker_handles_paper_stop_command(
    worker_config: PaperWorkerConfig, operations_db: Path
) -> None:
    """Test PaperWorker handles paper_stop command."""
    with patch("engine.paper_worker.PaperEngine") as mock_engine_class:
        mock_engine = MagicMock()
        mock_engine_class.return_value = mock_engine

        store = OperationsStore(str(operations_db))

        # Start first
        start_acceptance = store.accept_command(
            kind="paper_start",
            payload={
                "account_id": "test-account",
                "strategy_name": "dual_ma",
                "codes": ["000001.SZ"],
            },
            idempotency_key="test-start-stop-1",
        )

        worker = PaperWorker(worker_config)
        worker._poll_and_execute()

        assert "test-account" in worker._engines

        # Now stop
        stop_acceptance = store.accept_command(
            kind="paper_stop",
            payload={"account_id": "test-account"},
            idempotency_key="test-stop-1",
        )
        store.close()

        worker._poll_and_execute()

        # Verify engine was stopped and removed
        assert "test-account" not in worker._engines
        mock_engine.stop.assert_called_once()


def test_worker_concurrent_claim_protection(
    worker_config: PaperWorkerConfig, operations_db: Path, lease_db: Path
) -> None:
    """Test that only one worker can claim a task."""
    # Enqueue a command
    store = OperationsStore(str(operations_db))
    acceptance = store.accept_command(
        kind="paper_start",
        payload={
            "account_id": "test-account",
            "strategy_name": "dual_ma",
            "codes": ["000001.SZ"],
        },
        idempotency_key="test-concurrent",
    )
    command_id = acceptance.command.id
    store.close()

    with patch("engine.paper_worker.PaperEngine") as mock_engine_class:
        mock_engine = MagicMock()
        mock_engine_class.return_value = mock_engine

        # Create two workers
        worker1 = PaperWorker(worker_config)

        worker2_config = PaperWorkerConfig(
            operations_db=str(operations_db),
            lease_db=str(lease_db),
            poll_interval_seconds=0.1,
            lease_ttl_seconds=10.0,
            task_lease_seconds=5.0,
            worker_id="test-worker-2",
        )
        worker2 = PaperWorker(worker2_config)

        # Worker1 claims first
        worker1._poll_and_execute()

        # Worker2 tries to claim - should get nothing
        worker2._poll_and_execute()

        # Only worker1 should have the engine
        assert len(worker1._engines) == 1
        assert len(worker2._engines) == 0
