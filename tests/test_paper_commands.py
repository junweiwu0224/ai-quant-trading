import pytest

from engine.operations_store import IdempotencyConflictError, OperationsStore
from engine.paper_commands import PaperCommandService, PaperCommandValidationError


def service(tmp_path):
    store = OperationsStore(tmp_path / "nested" / "operations.db")
    return store, PaperCommandService(store)


def test_start_command_is_idempotent_and_risk_is_always_enabled(tmp_path):
    store, commands = service(tmp_path)
    try:
        first = commands.enqueue_start(
            idempotency_key="start-1",
            account_id="paper-a",
            strategy="dual_ma",
            codes=["000001", "600519"],
            initial_cash=100_000,
        )
        replay = commands.enqueue_start(
            idempotency_key="start-1",
            account_id="paper-a",
            strategy="dual_ma",
            codes=["600519", "000001"],
            initial_cash=100_000,
        )
        assert replay == first
        assert first.command.kind == "paper.start"
        assert first.command.payload["enable_risk"] is True
        assert first.command.payload["account_id"] == "paper-a"
    finally:
        store.close()


def test_commands_reject_conflicts_and_invalid_inputs(tmp_path):
    store, commands = service(tmp_path)
    try:
        commands.enqueue_stop(idempotency_key="stop-1", account_id="paper-a")
        with pytest.raises(IdempotencyConflictError):
            commands.enqueue_reset(idempotency_key="stop-1", account_id="paper-a")
        with pytest.raises(PaperCommandValidationError):
            commands.enqueue_start(idempotency_key="bad-codes", codes=[])
        with pytest.raises(PaperCommandValidationError):
            commands.enqueue_start(idempotency_key="bad-account", account_id="../escape", codes=["000001"])
        with pytest.raises(PaperCommandValidationError):
            commands.enqueue_start(idempotency_key="bad-risk", codes=["000001"], params={"enable_risk": False})
        with pytest.raises(PaperCommandValidationError):
            commands.enqueue_start(idempotency_key="bad-cash", codes=["000001"], initial_cash=0)
    finally:
        store.close()


def test_stop_and_reset_have_distinct_typed_kinds_and_metadata(tmp_path):
    store, commands = service(tmp_path)
    try:
        stop = commands.enqueue_stop(idempotency_key="stop-1", account_id="paper-a", reason="operator stop")
        reset = commands.enqueue_reset(idempotency_key="reset-1", account_id="paper-a", reason="new run")
        assert stop.command.kind == "paper.stop"
        assert reset.command.kind == "paper.reset"
        assert stop.command.payload["reason"] == "operator stop"
        assert reset.command.payload["reason"] == "new run"
    finally:
        store.close()
