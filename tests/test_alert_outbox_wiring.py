from pathlib import Path


def test_realtime_quote_alert_engine_constructs_with_durable_outbox():
    source = (
        Path(__file__).resolve().parents[1] / "dashboard" / "routers" / "realtime_quotes.py"
    ).read_text()
    assert "SQLiteOutbox" in source
    assert 'DB_DIR / "events.db"' in source
    assert "AlertEngine(outbox=_alert_outbox)" in source
    assert "configure_broadcast_loop" in source
    assert "NotificationDispatcher" in (Path(__file__).resolve().parents[1] / "dashboard" / "app.py").read_text()
    assert "call_soon_threadsafe" in source
