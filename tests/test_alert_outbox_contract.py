from pathlib import Path


def test_alert_engine_has_optional_outbox_seam_and_publishes_domain_event():
    source = (Path(__file__).resolve().parents[1] / "engine" / "alert_engine.py").read_text()
    assert "class AlertEventOutbox(Protocol)" in source
    assert '"market.alert.triggered"' in source
    assert "self._outbox.publish" in source
    assert "self._lock = threading.RLock()" in source
    assert "只有事件成功落入 durable outbox 后才提交冷却状态" in source
