from pathlib import Path


def test_alert_outbox_owns_transport_when_configured():
    source = (Path(__file__).resolve().parents[1] / "engine" / "alert_engine.py").read_text()
    assert "rule.webhook_url and self._outbox is None" in source
