"""Session gate behavior."""
import asyncio
import importlib
import os

from starlette.requests import Request
from fastapi import HTTPException
from starlette.responses import Response
from fastapi.testclient import TestClient
import pytest

from dashboard.app import APIKeyMiddleware, app


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


def _request(path: str) -> Request:
    raw_path = path.encode("ascii")
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": raw_path,
            "query_string": b"",
            "root_path": "",
            "headers": [],
            "client": ("test", 1),
            "server": ("test", 80),
        }
    )


def test_api_key_middleware_keeps_public_report_shell_and_assets_anonymous(monkeypatch):
    """A share link must remain usable when the private API key gate is enabled."""

    app_module = importlib.import_module("dashboard.app")
    monkeypatch.setattr(app_module, "is_valid_api_key", lambda _candidate: False)
    middleware = APIKeyMiddleware(lambda _scope, _receive, _send: None)

    async def call_next(_request):
        return Response("ok")

    for path in (
        "/report/share-token",
        "/api/decisions/shared/share-token",
        "/app/assets/index.js",
    ):
        response = asyncio.run(middleware.dispatch(_request(path), call_next))
        assert response.status_code == 200, path

    for path in ("/report/share-token/extra", "/api/decisions/reports/report-1"):
        response = asyncio.run(middleware.dispatch(_request(path), call_next))
        assert response.status_code == 401, path

    # The shell must be reachable before authentication so Vue can render the
    # login/register flow; its API requests remain protected by the session gate.
    response = asyncio.run(middleware.dispatch(_request("/app/decision"), call_next))
    assert response.status_code == 200


def test_share_page_validates_token_before_serving_vue_shell(monkeypatch):
    app_module = importlib.import_module("dashboard.app")

    async def reject(_token):
        raise HTTPException(404, "missing")

    monkeypatch.setattr(app_module.decisions, "get_shared_report", reject)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(app_module.shared_report("missing-token"))

    assert getattr(caught.value, "status_code", None) == 404
