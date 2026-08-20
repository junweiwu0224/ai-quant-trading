import json
import sqlite3
from pathlib import Path
import types

import pytest

from engine.paper_runtime import (
    PAPER_RUNTIME_STATUSES,
    PaperRuntimeConflictError,
    PaperRuntimeStore,
    PaperRuntimeValidationError,
)


def create(store: PaperRuntimeStore, *, account_id: str = "paper-a", **changes):
    fields = {
        "account_id": account_id,
        "run_id": "run-1",
        "status": "starting",
        "config": {"z": 1, "nested": {"b": True, "a": "x"}},
        "owner_id": "owner-a",
        "ownership_fence": "fence-1",
    }
    fields.update(changes)
    return store.create(**fields)


def test_schema_is_idempotent_and_database_uses_wal_and_busy_timeout(tmp_path: Path):
    database = tmp_path / "nested" / "paper.db"
    first = PaperRuntimeStore(database)
    second = PaperRuntimeStore(database)
    try:
        with sqlite3.connect(database) as connection:
            assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
            assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
            tables = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            ).fetchall()
        assert tables == [("paper_runtime",)]
        assert first.list() == []
        assert second.list() == []
    finally:
        del first, second


def test_instances_see_committed_create_and_update(tmp_path: Path):
    first = PaperRuntimeStore(tmp_path / "paper.db")
    second = PaperRuntimeStore(tmp_path / "paper.db")
    created = create(first)
    try:
        assert second.get("paper-a") == created
        updated = second.update("paper-a", 1, status="running")
        assert first.get("paper-a") == updated
        assert updated.version == 2
    finally:
        del first, second


def test_config_roundtrip_is_canonical_json(tmp_path: Path):
    database = tmp_path / "paper.db"
    store = PaperRuntimeStore(database)
    try:
        record = create(store, config={"z": [2, 1], "a": {"z": 0, "b": None}})
        with sqlite3.connect(database) as connection:
            encoded = connection.execute(
                "SELECT config_json FROM paper_runtime WHERE account_id = ?", ("paper-a",)
            ).fetchone()[0]
        assert encoded == '{"a":{"b":null,"z":0},"z":[2,1]}'
        assert json.loads(encoded) == record.config
        assert store.get("paper-a").config == {"z": [2, 1], "a": {"z": 0, "b": None}}
    finally:
        del store


def test_account_and_path_validation(tmp_path: Path):
    database = tmp_path / "new" / "paper.db"
    store = PaperRuntimeStore(database)
    try:
        for account_id in ("", "../escape", "a/b", "a\\b", ".", ".."):
            with pytest.raises(PaperRuntimeValidationError):
                create(store, account_id=account_id)
        with pytest.raises(PaperRuntimeValidationError):
            create(store, run_id="")
        with pytest.raises(PaperRuntimeValidationError):
            create(store, owner_id="")
        with pytest.raises(PaperRuntimeValidationError):
            create(store, ownership_fence="")
    finally:
        del store
    with pytest.raises(ValueError):
        PaperRuntimeStore("")
    with pytest.raises(ValueError):
        PaperRuntimeStore(tmp_path)


def test_create_conflict_and_stale_update_do_not_lose_writes(tmp_path: Path):
    first = PaperRuntimeStore(tmp_path / "paper.db")
    second = PaperRuntimeStore(tmp_path / "paper.db")
    try:
        original = create(first)
        with pytest.raises(PaperRuntimeConflictError):
            create(second)
        committed = first.update("paper-a", original.version, status="running")
        with pytest.raises(PaperRuntimeConflictError):
            second.update("paper-a", original.version, status="failed")
        assert second.get("paper-a") == committed
        assert committed.status == "running"
        assert committed.version == original.version + 1
    finally:
        del first, second


def test_status_vocabulary_is_explicit(tmp_path: Path):
    store = PaperRuntimeStore(tmp_path / "paper.db")
    try:
        for status in PAPER_RUNTIME_STATUSES:
            record = create(store, account_id=f"account-{status}", status=status)
            assert record.status == status
        with pytest.raises(PaperRuntimeValidationError):
            create(store, account_id="account-invalid", status="queued")
        with pytest.raises(PaperRuntimeValidationError):
            store.update("account-starting", 1, status="authoritative")
    finally:
        del store


def test_update_supports_changed_mapping_and_atomically_increments_version(tmp_path: Path):
    store = PaperRuntimeStore(tmp_path / "paper.db", now=lambda: 123.5)
    try:
        created = create(store)
        updated = store.update(
            "paper-a",
            expected_version=created.version,
            changed={"config": {"new": True}, "last_task_id": "task-1", "error": None},
        )
        assert updated.version == created.version + 1
        assert updated.updated_at == 123.5
        assert updated.config == {"new": True}
        assert updated.last_task_id == "task-1"
        assert updated.error is None
        assert store.get("paper-a").version == 2
    finally:
        del store


def test_invalid_config_and_corrupt_stored_data_fail_closed(tmp_path: Path):
    database = tmp_path / "paper.db"
    store = PaperRuntimeStore(database)
    try:
        for config in ([], "text", None, {"bad": {1, 2}}, {"bad": float("nan")}):
            with pytest.raises(PaperRuntimeValidationError):
                create(store, account_id=f"bad-{len(store.list())}", config=config)
        create(store)
        with sqlite3.connect(database) as connection:
            connection.execute(
                "UPDATE paper_runtime SET config_json = ? WHERE account_id = ?",
                ("[]", "paper-a"),
            )
            connection.commit()
        with pytest.raises(PaperRuntimeValidationError):
            store.get("paper-a")
        with sqlite3.connect(database) as connection:
            connection.execute(
                "UPDATE paper_runtime SET config_json = ? WHERE account_id = ?",
                (sqlite3.Binary(b'{"valid":true}'), "paper-a"),
            )
            connection.commit()
        with pytest.raises(PaperRuntimeValidationError):
            store.get("paper-a")
    finally:
        del store


def test_store_does_not_create_trading_or_order_tables(tmp_path: Path):
    database = tmp_path / "paper.db"
    store = PaperRuntimeStore(database)
    try:
        create(store)
        with sqlite3.connect(database) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        assert tables == {"paper_runtime"}
        assert not hasattr(store, "delete")
        assert not hasattr(store, "reset")
    finally:
        del store


def test_update_enforces_ownership_fence(tmp_path: Path) -> None:
    """Test that update() WHERE clause includes ownership_fence to prevent stale owner writes."""
    store = PaperRuntimeStore(database=tmp_path / "runtime.db")
    store.create(
        account_id="test_account",
        run_id="run_1",
        status="running",
        config={"strategy": "alpha"},
        owner_id="worker_a",
        ownership_fence="fence_1",
    )
    record = store.get("test_account")
    assert record is not None
    # Simulate lease reclaim by directly updating the database (bypassing validation)
    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "runtime.db"))
    conn.execute(
        "UPDATE paper_runtime SET ownership_fence = ?, owner_id = ?, version = version + 1 WHERE account_id = ?",
        ("fence_2", "worker_b", "test_account"),
    )
    conn.commit()
    conn.close()
    # Old owner with stale fence tries to update status
    with pytest.raises(PaperRuntimeConflictError):
        store.update(
            account_id="test_account",
            expected_version=record.version + 1,
            expected_ownership_fence="fence_1",  # Stale fence
            status="stopped",
        )


def test_config_immutability(tmp_path: Path) -> None:
    """Test that PaperRuntimeRecord.config is deeply immutable."""
    store = PaperRuntimeStore(database=tmp_path / "runtime.db")
    store.create(
        account_id="test_account",
        run_id="run_1",
        status="running",
        config={"strategy": "alpha", "params": {"window": 20}},
        owner_id="worker_a",
        ownership_fence="fence_1",
    )
    record = store.get("test_account")
    assert record is not None
    # config should be MappingProxyType
    assert isinstance(record.config, types.MappingProxyType)
    with pytest.raises(TypeError):
        record.config["strategy"] = "beta"  # type: ignore


def test_stored_json_rejects_nan_infinity(tmp_path: Path) -> None:
    """Test that _record_from_row rejects NaN/Infinity in stored config."""
    import sqlite3
    db_path = tmp_path / "runtime.db"
    store = PaperRuntimeStore(database=db_path)
    # Manually insert a record with NaN
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO paper_runtime (
            account_id, run_id, status, config_json, owner_id, ownership_fence,
            last_task_id, error, version, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("test_account", "run_1", "running", '{"value": NaN}', "worker_a", "fence_1", None, None, 1, 1.0),
    )
    conn.commit()
    conn.close()
    # get() should raise validation error
    with pytest.raises(PaperRuntimeValidationError, match="NaN or Infinity"):
        store.get("test_account")
