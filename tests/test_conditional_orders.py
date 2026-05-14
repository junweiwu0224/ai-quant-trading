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


def test_handle_alerts_creates_one_paper_order_for_enabled_rule(engine):
    rule = engine.create_rule(
        alert_rule_id=1,
        code="000001",
        direction="buy",
        order_type="market",
        volume=100,
        max_amount=2000,
        cooldown=300,
        enabled=True,
    )

    events = engine.handle_alerts([make_alert()], {"000001": make_quote(price=10.0)})

    assert len(events) == 1
    assert events[0].action == "created_order"
    assert events[0].order_id

    orders = engine.order_manager.get_orders()
    assert orders["total"] == 1
    item = orders["items"][0]
    assert item["code"] == "000001"
    assert item["direction"] == "buy"
    assert item["strategy_name"] == "conditional_order"
    assert f"条件单#{rule.id}" in item["signal_reason"]


def test_handle_alerts_respects_cooldown_idempotency(engine):
    engine.create_rule(
        alert_rule_id=1,
        code="000001",
        direction="buy",
        order_type="market",
        volume=100,
        max_amount=2000,
        cooldown=300,
        enabled=True,
    )

    first = engine.handle_alerts([make_alert()], {"000001": make_quote(price=10.0)})
    second = engine.handle_alerts([make_alert()], {"000001": make_quote(price=10.0)})

    assert first[0].action == "created_order"
    assert second[0].action == "skipped"
    assert engine.order_manager.get_orders()["total"] == 1


def test_disabled_rule_does_not_create_order(engine):
    engine.create_rule(
        alert_rule_id=1,
        code="000001",
        direction="buy",
        order_type="market",
        volume=100,
        enabled=False,
    )

    events = engine.handle_alerts([make_alert()], {"000001": make_quote(price=10.0)})

    assert events == []
    assert engine.order_manager.get_orders()["total"] == 0


def test_buy_rule_rejects_when_max_amount_exceeded(engine):
    engine.create_rule(
        alert_rule_id=1,
        code="000001",
        direction="buy",
        order_type="market",
        volume=1000,
        max_amount=2000,
        enabled=True,
    )

    events = engine.handle_alerts([make_alert()], {"000001": make_quote(price=10.0)})

    assert events[0].action == "rejected"
    assert "最大下单金额" in events[0].reason
    assert engine.order_manager.get_orders()["total"] == 0


def test_sell_rule_rejects_without_position(engine):
    engine.create_rule(
        alert_rule_id=1,
        code="000001",
        direction="sell",
        order_type="market",
        volume=100,
        enabled=True,
    )

    events = engine.handle_alerts([make_alert()], {"000001": make_quote(price=10.0)})

    assert events[0].action == "rejected"
    assert "持仓不足" in events[0].reason
    assert engine.order_manager.get_orders()["total"] == 0


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
