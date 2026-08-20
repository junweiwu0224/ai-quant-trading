import sqlite3
import time
from pathlib import Path

import pytest

from data.collector.quote_service import QuoteData
from engine.alert_engine import Alert
from engine.migrate import init_database


def make_quote(code: str = "000001", price: float = 10.0) -> QuoteData:
    return QuoteData(
        code=code,
        name="测试股票",
        price=price,
        open=price,
        high=price * 1.02,
        low=price * 0.98,
        pre_close=price,
        volume=100000,
        amount=price * 100000,
        change_pct=0.0,
        timestamp=time.time(),
    )


def make_alert(rule_id: int = 1, code: str = "000001", current_value: float = 10.0) -> Alert:
    return Alert(
        rule_id=rule_id,
        code=code,
        name="测试股票",
        condition="price_above",
        threshold=9.5,
        current_value=current_value,
        message="测试股票 价格突破 9.5，当前 10.00",
        timestamp=1700000000.0,
    )


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    path = tmp_path / "paper_trading.db"
    init_database(str(path))
    return str(path)


@pytest.fixture
def engine(db_path: str):
    from engine.conditional_order import ConditionalOrderEngine

    return ConditionalOrderEngine(db_path=db_path)


def test_migration_creates_conditional_order_tables(db_path: str):
    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    finally:
        conn.close()

    assert "conditional_orders" in tables
    assert "conditional_order_events" in tables


def test_create_rule_persists_disabled_by_default(engine):
    rule = engine.create_rule(
        alert_rule_id=1,
        code="000001",
        direction="buy",
        order_type="market",
        volume=100,
        max_amount=2000,
        cooldown=120,
    )

    assert rule.id > 0
    assert rule.enabled is False
    assert rule.max_amount == 2000
    assert engine.list_rules()[0].id == rule.id


# REMOVED: 此测试依赖旧的 OrderManager.create_order() 路径
# Phase 2 已迁移到 PaperCommandClient + PaperWorker
# 新的迁移测试见 test_conditional_order_migration.py


# REMOVED: 此测试依赖旧的 OrderManager.create_order() 路径
# Phase 2 已迁移到 PaperCommandClient + PaperWorker
# 新的迁移测试见 test_conditional_order_migration.py


# REMOVED: 此测试依赖旧的 OrderManager.get_orders()
# 新实现通过 command 入队，订单由 PaperWorker 异步处理


# REMOVED: 此测试依赖旧的预检查逻辑
# Phase 2 迁移后，风控检查在 RiskGate 中（Phase 3 实现）


# REMOVED: 此测试依赖旧的预检查逻辑
# Phase 2 迁移后，风控检查在 RiskGate 中（Phase 3 实现）


def test_router_crud_endpoints(monkeypatch, db_path: str):
    from fastapi.testclient import TestClient

    from dashboard.app import app
    from dashboard.routers import conditional_orders
    from engine.conditional_order import ConditionalOrderEngine

    monkeypatch.setattr(
        conditional_orders,
        "_engine",
        ConditionalOrderEngine(db_path=db_path),
    )

    with TestClient(app) as client:
        create_resp = client.post("/api/conditional-orders/rules", json={
            "alert_rule_id": 1,
            "code": "000001",
            "direction": "buy",
            "order_type": "market",
            "volume": 100,
            "max_amount": 2000,
            "cooldown": 120,
            "enabled": False,
        })
        assert create_resp.status_code == 200
        created = create_resp.json()["data"]
        assert created["enabled"] is False

        list_resp = client.get("/api/conditional-orders/rules")
        assert list_resp.status_code == 200
        assert list_resp.json()["data"][0]["id"] == created["id"]

        update_resp = client.put(
            f"/api/conditional-orders/rules/{created['id']}",
            json={"enabled": True},
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["data"]["enabled"] is True

        events_resp = client.get("/api/conditional-orders/events")
        assert events_resp.status_code == 200
        assert events_resp.json()["data"] == []

        delete_resp = client.delete(f"/api/conditional-orders/rules/{created['id']}")
        assert delete_resp.status_code == 200
        assert delete_resp.json()["success"] is True
