"""Tests for Paper command client."""

from pathlib import Path

import pytest

from engine.operations_store import IdempotencyConflictError, OperationsStore
from engine.paper_commands import PaperCommandClient


@pytest.fixture
def operations_db(tmp_path: Path) -> Path:
    """Create a temporary operations database."""
    db_path = tmp_path / "operations.db"
    store = OperationsStore(str(db_path))
    store.close()
    return db_path


@pytest.fixture
def client(operations_db: Path) -> PaperCommandClient:
    """Create a Paper command client."""
    client = PaperCommandClient(str(operations_db))
    yield client
    client.close()


def test_enqueue_start_success(client: PaperCommandClient) -> None:
    """Test enqueueing a paper_start command."""
    acceptance = client.enqueue_start(
        account_id="test-account",
        strategy_name="dual_ma",
        codes=["000001.SZ"],
        interval_seconds=60,
        initial_cash=100_000.0,
    )
    assert acceptance.command.kind == "paper_start"
    assert acceptance.command.payload["account_id"] == "test-account"
    assert acceptance.command.payload["strategy_name"] == "dual_ma"
    assert acceptance.command.payload["codes"] == ["000001.SZ"]
    assert acceptance.task.status == "queued"


def test_enqueue_start_empty_codes(client: PaperCommandClient) -> None:
    """Test that empty codes are rejected."""
    with pytest.raises(ValueError, match="codes cannot be empty"):
        client.enqueue_start(
            account_id="test-account",
            strategy_name="dual_ma",
            codes=[],
        )


def test_enqueue_start_invalid_account_id(client: PaperCommandClient) -> None:
    """Test that invalid account_id is rejected."""
    with pytest.raises(ValueError, match="invalid account_id"):
        client.enqueue_start(
            account_id="test/account",
            strategy_name="dual_ma",
            codes=["000001.SZ"],
        )


def test_enqueue_start_idempotent(client: PaperCommandClient) -> None:
    """Test that same idempotency key returns same command."""
    acceptance1 = client.enqueue_start(
        account_id="test-account",
        strategy_name="dual_ma",
        codes=["000001.SZ"],
        idempotency_key="start-1",
    )
    acceptance2 = client.enqueue_start(
        account_id="test-account",
        strategy_name="dual_ma",
        codes=["000001.SZ"],
        idempotency_key="start-1",
    )
    assert acceptance1.command.id == acceptance2.command.id
    assert acceptance1.task.id == acceptance2.task.id


def test_enqueue_start_idempotency_conflict(client: PaperCommandClient) -> None:
    """Test that same key with different payload raises conflict."""
    client.enqueue_start(
        account_id="test-account",
        strategy_name="dual_ma",
        codes=["000001.SZ"],
        idempotency_key="start-conflict",
    )
    with pytest.raises(IdempotencyConflictError):
        client.enqueue_start(
            account_id="test-account",
            strategy_name="different_strategy",
            codes=["000002.SZ"],
            idempotency_key="start-conflict",
        )


def test_enqueue_stop_success(client: PaperCommandClient) -> None:
    """Test enqueueing a paper_stop command."""
    acceptance = client.enqueue_stop(
        account_id="test-account",
        reason="maintenance",
    )
    assert acceptance.command.kind == "paper_stop"
    assert acceptance.command.payload["account_id"] == "test-account"
    assert acceptance.command.payload["reason"] == "maintenance"
    assert acceptance.task.status == "queued"


def test_enqueue_reset_success(client: PaperCommandClient) -> None:
    """Test enqueueing a paper_reset command."""
    acceptance = client.enqueue_reset(
        account_id="test-account",
        initial_cash=200_000.0,
        reason="reset_test",
    )
    assert acceptance.command.kind == "paper_reset"
    assert acceptance.command.payload["account_id"] == "test-account"
    assert acceptance.command.payload["initial_cash"] == 200_000.0
    assert acceptance.task.status == "queued"


def test_enqueue_adjust_position_success(client: PaperCommandClient) -> None:
    """Test enqueueing a paper_adjust_position command."""
    acceptance = client.enqueue_adjust_position(
        account_id="test-account",
        code="000001.SZ",
        direction="buy",
        volume=100,
    )
    assert acceptance.command.kind == "paper_adjust_position"
    assert acceptance.command.payload["code"] == "000001.SZ"
    assert acceptance.command.payload["direction"] == "buy"
    assert acceptance.command.payload["volume"] == 100


def test_enqueue_adjust_position_invalid_direction(
    client: PaperCommandClient,
) -> None:
    """Test that invalid direction is rejected."""
    with pytest.raises(ValueError, match="direction must be buy or sell"):
        client.enqueue_adjust_position(
            account_id="test-account",
            code="000001.SZ",
            direction="invalid",
            volume=100,
        )
