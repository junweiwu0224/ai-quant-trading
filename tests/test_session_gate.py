"""Session gate behavior."""
import importlib
import os

from fastapi.testclient import TestClient

from dashboard.app import app


def test_session_gate_allows_api_requests_in_test_environment(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")

    with TestClient(app) as client:
        response = client.get("/api/system/status")

    assert response.status_code == 200


def test_settings_respect_existing_app_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")

    import config.settings as settings

    importlib.reload(settings)

    assert os.environ["APP_ENV"] == "test"
