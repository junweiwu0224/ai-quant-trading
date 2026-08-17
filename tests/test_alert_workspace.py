import asyncio
import json
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from dashboard.app import app
from dashboard.routers import alerts as alerts_router
from dashboard.session import optional_account
from data.storage import DataStorage
from engine.alert_engine import AlertEngine, AlertRule
from engine.events.outbox import SQLiteOutbox


def _account(workspace_id: str) -> dict:
    return {
        "user": {"id": f"user-{workspace_id}"},
        "workspace": {"id": workspace_id},
        "permissions": {},
    }


def _quote(price: float = 10.0):
    return SimpleNamespace(price=price, name="测试股票")


def _rule(rule_id: int, workspace_id: str) -> AlertRule:
    return AlertRule(
        id=rule_id,
        code="000001",
        condition="price_above",
        threshold=9.0,
        cooldown=0,
        workspace_id=workspace_id,
    )


def test_alert_rule_migration_adds_workspace_and_scopes_legacy_rows(tmp_path, monkeypatch):
    database = tmp_path / "alerts-legacy.db"
    connection = sqlite3.connect(database)
    connection.execute(
        """
        CREATE TABLE alert_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            condition TEXT NOT NULL,
            threshold REAL NOT NULL,
            enabled INTEGER DEFAULT 1,
            name TEXT DEFAULT '',
            cooldown INTEGER DEFAULT 300,
            webhook_url TEXT DEFAULT '',
            created_at TEXT
        )
        """
    )
    connection.execute(
        "INSERT INTO alert_rules(code, condition, threshold) VALUES ('000001', 'price_above', 9)"
    )
    connection.commit()
    connection.close()

    storage = DataStorage(f"sqlite:///{database}")
    columns = {
        row[1]
        for row in sqlite3.connect(database).execute("PRAGMA table_info(alert_rules)").fetchall()
    }
    assert "workspace_id" in columns
    assert storage.get_alert_rules(workspace_id="default")[0]["workspace_id"] == "default"

    monkeypatch.setenv("APP_ENV", "production")
    try:
        storage.get_alert_rules()
    except ValueError as exc:
        assert "workspace_id is required" in str(exc)
    else:
        raise AssertionError("unnamed alert reads must fail closed outside test mode")


def test_production_legacy_alert_rules_are_quarantined_until_explicitly_migrated(tmp_path, monkeypatch):
    from data.storage.storage import ALERT_LEGACY_UNASSIGNED_WORKSPACE_ID

    monkeypatch.setenv("APP_ENV", "production")
    database = tmp_path / "alerts-production-legacy.db"
    connection = sqlite3.connect(database)
    connection.execute(
        """
        CREATE TABLE alert_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            condition TEXT NOT NULL,
            threshold REAL NOT NULL,
            enabled INTEGER DEFAULT 1,
            name TEXT DEFAULT '',
            cooldown INTEGER DEFAULT 300,
            webhook_url TEXT DEFAULT '',
            created_at TEXT
        )
        """
    )
    connection.execute(
        "INSERT INTO alert_rules(code, condition, threshold) VALUES ('000001', 'price_above', 9)"
    )
    connection.commit()
    connection.close()

    storage = DataStorage(f"sqlite:///{database}")
    row = sqlite3.connect(database).execute(
        "SELECT workspace_id FROM alert_rules WHERE id = 1"
    ).fetchone()
    assert row == (ALERT_LEGACY_UNASSIGNED_WORKSPACE_ID,)
    assert storage.get_alert_rules(workspace_id="workspace-a") == []
    assert storage.get_alert_workspace_ids() == []

    assert storage.migrate_legacy_alert_rules([1], workspace_id="workspace-a") == 1
    assert storage.get_alert_rules(workspace_id="workspace-a")[0]["workspace_id"] == "workspace-a"


def test_alert_api_scopes_crud_reads_and_writes_by_workspace(tmp_path, monkeypatch):
    storage = DataStorage(f"sqlite:///{tmp_path / 'alerts.db'}")
    monkeypatch.setattr(alerts_router, "storage", storage)
    monkeypatch.setattr(alerts_router, "_reload_engine", lambda _workspace_id=None: None)

    current_account = {"value": _account("workspace-a")}
    app.dependency_overrides[optional_account] = lambda: current_account["value"]
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/alerts/rules",
                json={
                    "code": "000001",
                    "condition": "price_above",
                    "threshold": 9,
                    "name": "A only",
                },
            )
            assert created.status_code == 200
            rule_id = created.json()["id"]

            assert client.get("/api/alerts/rules").json()["rules"][0]["workspace_id"] == "workspace-a"

            current_account["value"] = _account("workspace-b")
            assert client.get("/api/alerts/rules").json()["rules"] == []
            assert client.put(
                f"/api/alerts/rules/{rule_id}",
                json={"name": "must not change"},
            ).json()["success"] is False
            assert client.delete(f"/api/alerts/rules/{rule_id}").json()["success"] is False

            created_b = client.post(
                "/api/alerts/rules",
                json={
                    "code": "000001",
                    "condition": "price_above",
                    "threshold": 9,
                    "name": "B only",
                },
            )
            assert created_b.status_code == 200
            assert [item["name"] for item in client.get("/api/alerts/rules").json()["rules"]] == ["B only"]

            current_account["value"] = _account("workspace-a")
            assert [item["name"] for item in client.get("/api/alerts/rules").json()["rules"]] == ["A only"]
    finally:
        app.dependency_overrides.pop(optional_account, None)


def test_alert_routes_fail_closed_without_workspace_outside_test(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")

    with pytest.raises(HTTPException) as caught:
        alerts_router._workspace_id(None)

    assert caught.value.status_code == 401


def test_alert_engines_isolate_history_and_outbox_events_by_workspace():
    outbox = SQLiteOutbox(sqlite3.connect(":memory:"))
    engine_a = AlertEngine(outbox=outbox, workspace_id="workspace-a")
    engine_b = AlertEngine(outbox=outbox, workspace_id="workspace-b")
    engine_a.set_rules([_rule(1, "workspace-a"), _rule(2, "workspace-b")])
    engine_b.set_rules([_rule(1, "workspace-a"), _rule(2, "workspace-b")])

    assert len(engine_a.check({"000001": _quote()})) == 1
    assert len(engine_b.check({"000001": _quote()})) == 1
    assert engine_a.get_recent_alerts()[0]["workspace_id"] == "workspace-a"
    assert engine_b.get_recent_alerts()[0]["workspace_id"] == "workspace-b"

    events = outbox.claim(consumer="test-alert-workspaces", limit=10)
    assert {event.event.payload["workspace_id"] for event in events} == {
        "workspace-a",
        "workspace-b",
    }
    assert len({event.event.idempotency_key for event in events}) == 2
    assert {event.event.aggregate_id for event in events} == {
        "workspace-a:1:000001",
        "workspace-b:2:000001",
    }


def test_alert_history_route_reads_only_the_current_workspace(monkeypatch):
    from dashboard.routers import realtime_quotes

    engine_a = AlertEngine(workspace_id="workspace-a")
    engine_b = AlertEngine(workspace_id="workspace-b")
    engine_a.set_rules([_rule(1, "workspace-a")])
    engine_b.set_rules([_rule(2, "workspace-b")])
    engine_a.check({"000001": _quote()})
    engine_b.check({"000001": _quote()})
    engines = {"workspace-a": engine_a, "workspace-b": engine_b}
    monkeypatch.setattr(
        realtime_quotes,
        "_get_alert_engine",
        lambda workspace_id=None: engines[workspace_id],
    )

    history_a = asyncio.run(alerts_router.get_history(account=_account("workspace-a")))
    history_b = asyncio.run(alerts_router.get_history(account=_account("workspace-b")))

    assert [item["workspace_id"] for item in history_a["alerts"]] == ["workspace-a"]
    assert [item["workspace_id"] for item in history_b["alerts"]] == ["workspace-b"]


def test_alert_websocket_broadcast_filters_by_connection_workspace(monkeypatch):
    from dashboard.routers import realtime_quotes

    engine_a = AlertEngine(workspace_id="workspace-a")
    engine_b = AlertEngine(workspace_id="workspace-b")
    engine_a.set_rules([_rule(1, "workspace-a")])
    engine_b.set_rules([_rule(2, "workspace-b")])
    triggered = [
        *engine_a.check({"000001": _quote()}),
        *engine_b.check({"000001": _quote()}),
    ]

    class FakeWebSocket:
        def __init__(self):
            self.messages = []

        async def send_text(self, payload):
            self.messages.append(json.loads(payload))

    websocket_a = FakeWebSocket()
    websocket_b = FakeWebSocket()
    monkeypatch.setattr(realtime_quotes, "_active_connections", [websocket_a, websocket_b])
    monkeypatch.setattr(
        realtime_quotes,
        "_connection_workspaces",
        {websocket_a: "workspace-a", websocket_b: "workspace-b"},
    )

    asyncio.run(realtime_quotes._broadcast_alerts(triggered))

    assert websocket_a.messages[0]["data"][0]["workspace_id"] == "workspace-a"
    assert websocket_b.messages[0]["data"][0]["workspace_id"] == "workspace-b"


def test_realtime_trigger_checks_each_workspace_engine_without_cross_trigger(monkeypatch):
    from dashboard.routers import realtime_quotes

    engine_a = AlertEngine(workspace_id="workspace-a")
    engine_b = AlertEngine(workspace_id="workspace-b")
    engine_a.set_rules([_rule(1, "workspace-a")])
    engine_b.set_rules([_rule(2, "workspace-b")])
    engines = {"workspace-a": engine_a, "workspace-b": engine_b}

    class NoopConditionalOrders:
        def handle_alerts(self, alerts, quotes):
            return []

    monkeypatch.setattr(realtime_quotes, "_alert_engines", engines)
    monkeypatch.setattr(realtime_quotes, "_alert_engine", engine_b)
    monkeypatch.setattr(realtime_quotes, "_alert_workspace_ids", lambda: set(engines))
    monkeypatch.setattr(
        realtime_quotes,
        "_get_alert_engine",
        lambda workspace_id=None: engines[workspace_id],
    )
    monkeypatch.setattr(
        realtime_quotes,
        "_get_conditional_order_engine",
        lambda: NoopConditionalOrders(),
    )
    monkeypatch.setattr(realtime_quotes, "_broadcast_loop", None)

    realtime_quotes._sync_broadcast({"000001": _quote()})

    assert [item["workspace_id"] for item in engine_a.get_recent_alerts()] == ["workspace-a"]
    assert [item["workspace_id"] for item in engine_b.get_recent_alerts()] == ["workspace-b"]
