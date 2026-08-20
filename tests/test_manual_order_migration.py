"""测试手动订单 V2 迁移（统一执行协议）"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from engine.execution_protocol import (
    Environment,
    ExecutionPermit,
    OrderIntent,
    OrderIntentBatch,
    Side,
)
from engine.paper_commands import PaperCommandClient


def test_enqueue_manual_order_buy(tmp_path: Path):
    """测试提交买单"""
    db_path = tmp_path / "operations.db"
    client = PaperCommandClient(operations_db=db_path)

    idempotency_key = "test_buy_order_1"
    acceptance = client.enqueue_manual_order(
        instrument="000001.SZ",
        side=Side.BUY,
        quantity=100,
        execution_run_id="manual",
        account_id="paper-default",
        idempotency_key=idempotency_key,
    )

    assert acceptance.command.idempotency_key == idempotency_key
    assert acceptance.command.kind == "paper_execute_batch"
    assert acceptance.task.status == "queued"

    # 验证 command 已写入
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT * FROM commands WHERE id = ?", (acceptance.command.id,)
    )
    row = cursor.fetchone()
    conn.close()

    assert row is not None
    assert row["kind"] == "paper_execute_batch"
    assert row["idempotency_key"] == idempotency_key


def test_enqueue_manual_order_sell(tmp_path: Path):
    """测试提交卖单"""
    db_path = tmp_path / "operations.db"
    client = PaperCommandClient(operations_db=db_path)

    idempotency_key = "test_sell_order_1"
    acceptance = client.enqueue_manual_order(
        instrument="600000.SH",
        side=Side.SELL,
        quantity=200,
        execution_run_id="manual",
        account_id="paper-default",
        idempotency_key=idempotency_key,
    )

    assert acceptance.command.id is not None

    # 验证 payload 包含 batch 和 permit
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT * FROM commands WHERE id = ?", (acceptance.command.id,)
    )
    row = cursor.fetchone()
    conn.close()

    assert row is not None
    payload = json.loads(row["payload_json"])
    assert "batch_dict" in payload
    assert "permit_dict" in payload

    # 验证 batch
    batch_dict = payload["batch_dict"]
    assert len(batch_dict["intents"]) == 1

    intent = batch_dict["intents"][0]
    assert intent["instrument"] == "600000.SH"
    assert intent["side"] == "sell"
    assert intent["quantity"] == 200.0


def test_enqueue_manual_order_idempotency(tmp_path: Path):
    """测试幂等性：重复提交相同订单"""
    db_path = tmp_path / "operations.db"
    client = PaperCommandClient(operations_db=db_path)

    idempotency_key = "duplicate_test"
    acceptance1 = client.enqueue_manual_order(
        instrument="000001.SZ",
        side=Side.BUY,
        quantity=100,
        execution_run_id="manual",
        account_id="paper-default",
        idempotency_key=idempotency_key,
    )

    # 第二次调用：因为包含时间戳，payload 不同，会抛出 IdempotencyConflictError
    from engine.operations_store import IdempotencyConflictError
    
    with pytest.raises(IdempotencyConflictError):
        client.enqueue_manual_order(
            instrument="000001.SZ",
            side=Side.BUY,
            quantity=100,
            execution_run_id="manual",
            account_id="paper-default",
            idempotency_key=idempotency_key,
        )

    # 验证第一次接受的 command
    assert acceptance1.command.idempotency_key == idempotency_key


def test_enqueue_manual_order_batch_structure(tmp_path: Path):
    """测试批次结构正确性"""
    db_path = tmp_path / "operations.db"
    client = PaperCommandClient(operations_db=db_path)

    idempotency_key = "test_batch_structure"

    acceptance = client.enqueue_manual_order(
        instrument="600519.SH",
        side=Side.BUY,
        quantity=50,
        execution_run_id="manual",
        account_id="paper-default",
        idempotency_key=idempotency_key,
    )

    # 读取 payload 并重构 batch
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT * FROM commands WHERE id = ?", (acceptance.command.id,)
    )
    row = cursor.fetchone()
    conn.close()

    payload = json.loads(row["payload_json"])
    batch_dict = payload["batch_dict"]
    batch = OrderIntentBatch(
        batch_id=batch_dict["batch_id"],
        intents=tuple(
            OrderIntent(**intent_dict) for intent_dict in batch_dict["intents"]
        ),
    )

    assert len(batch.intents) == 1

    intent = batch.intents[0]
    assert intent.instrument == "600519.SH"
    assert intent.side == Side.BUY
    assert intent.quantity == 50
    assert intent.execution_run_id == "manual"
    assert intent.account_id == "paper-default"
    assert intent.environment == Environment.PAPER
    assert intent.idempotency_key == idempotency_key


def test_enqueue_manual_order_permit_structure(tmp_path: Path):
    """测试 permit 结构正确性"""
    db_path = tmp_path / "operations.db"
    client = PaperCommandClient(operations_db=db_path)

    idempotency_key = "test_permit_structure"

    acceptance = client.enqueue_manual_order(
        instrument="000001.SZ",
        side=Side.SELL,
        quantity=300,
        execution_run_id="manual",
        account_id="paper-default",
        idempotency_key=idempotency_key,
    )

    # 读取 payload 并重构 permit
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT * FROM commands WHERE id = ?", (acceptance.command.id,)
    )
    row = cursor.fetchone()
    conn.close()

    payload = json.loads(row["payload_json"])
    permit_dict = payload["permit_dict"]

    # 验证 permit 字段
    assert idempotency_key in permit_dict["idempotency_keys"]
    assert idempotency_key in permit_dict["evaluated_intent_keys"]
    assert permit_dict["fence_token"] == "1"
    # expiry 是字符串，需要解析
    expiry = datetime.fromisoformat(permit_dict["expires_at"])
    assert expiry > datetime.now(timezone.utc)
