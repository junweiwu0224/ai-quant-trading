import asyncio

import httpx

from dashboard import openclaw_service
from dashboard.openclaw_gateway import OpenClawGateway
from dashboard.openclaw_service import OpenClawServiceManager


def test_gateway_headers_include_auth_and_workspace_session_keys():
    gateway = OpenClawGateway(base_url="http://openclaw.local", api_key="secret-token")

    headers = gateway._headers("workspace-123")

    assert headers["Authorization"] == "Bearer secret-token"
    assert headers["X-API-Key"] == "secret-token"
    assert headers["X-OpenClaw-Workspace"] == "workspace-123"
    assert headers["x-openclaw-session-key"] == "workspace-123"


def test_gateway_headers_omit_optional_auth_and_workspace_when_blank():
    gateway = OpenClawGateway(base_url="http://openclaw.local", api_key="")

    headers = gateway._headers()

    assert headers == {"Content-Type": "application/json"}


def test_service_status_reports_external_without_starting_process(monkeypatch):
    monkeypatch.setattr(openclaw_service, "OPENCLAW_MANAGED", False)
    manager = OpenClawServiceManager()
    monkeypatch.setattr(manager, "installed", lambda: True)
    monkeypatch.setattr(manager, "port_open", lambda: True)
    monkeypatch.setattr(manager, "_process_running", lambda: False)
    monkeypatch.setattr(manager, "recent_logs", lambda max_chars=6000: "")

    status = manager.status()

    assert status["managed"] is False
    assert status["state"] == "external"
    assert status["running"] is True
    assert status["process_running"] is False


def test_service_status_reports_managed_running_starting_and_failed(monkeypatch):
    monkeypatch.setattr(openclaw_service, "OPENCLAW_MANAGED", True)
    manager = OpenClawServiceManager()
    monkeypatch.setattr(manager, "installed", lambda: True)
    monkeypatch.setattr(manager, "recent_logs", lambda max_chars=6000: "")

    monkeypatch.setattr(manager, "port_open", lambda: True)
    monkeypatch.setattr(manager, "_process_running", lambda: False)
    assert manager.status()["state"] == "running"

    monkeypatch.setattr(manager, "port_open", lambda: False)
    monkeypatch.setattr(manager, "_process_running", lambda: True)
    assert manager.status()["state"] == "starting"

    monkeypatch.setattr(manager, "_process_running", lambda: False)
    manager.last_error = "boom"
    failed = manager.status()
    assert failed["state"] == "failed"
    assert failed["last_error"] == "boom"


def test_health_probe_order_falls_through_gateway_endpoints(monkeypatch):
    gateway = OpenClawGateway(base_url="http://openclaw.local:18789", api_key="secret-token")
    calls = []

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers):
            calls.append(url)
            status_code = 200 if url.endswith("/") else 404
            return httpx.Response(status_code, json={"path": url.rsplit("/", 1)[-1]})

    monkeypatch.setattr(gateway, "_tcp_probe", lambda host, port: asyncio.sleep(0, result=(True, "")))
    monkeypatch.setattr("dashboard.openclaw_gateway.httpx.AsyncClient", FakeAsyncClient)

    result = asyncio.run(gateway.health("workspace-123"))

    assert calls == [
        "http://openclaw.local:18789/readyz",
        "http://openclaw.local:18789/healthz",
        "http://openclaw.local:18789/v1/models",
        "http://openclaw.local:18789/",
    ]
    assert result["ok"] is True
    assert result["endpoint"] == "/"


def test_native_tool_probe_order(monkeypatch):
    gateway = OpenClawGateway(base_url="http://openclaw.local:18789", api_key="secret-token")
    list_calls = []
    invoke_calls = []

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers):
            list_calls.append(url)
            status_code = 200 if url.endswith("/v1/tools") else 404
            return httpx.Response(status_code, json={"tools": []})

        async def post(self, url, headers, json):
            invoke_calls.append((url, json))
            status_code = 200 if url.endswith("/v1/tools/invoke") else 404
            return httpx.Response(status_code, json={"ok": True})

    monkeypatch.setattr("dashboard.openclaw_gateway.httpx.AsyncClient", FakeAsyncClient)

    list_result = asyncio.run(gateway.list_native_tools("workspace-123"))
    invoke_result = asyncio.run(
        gateway.invoke_native_tool("workspace-123", "quant.echo", {"message": "hi"})
    )

    assert list_calls == [
        "http://openclaw.local:18789/tools",
        "http://openclaw.local:18789/api/tools",
        "http://openclaw.local:18789/v1/tools",
    ]
    assert [call[0] for call in invoke_calls] == [
        "http://openclaw.local:18789/tools/invoke",
        "http://openclaw.local:18789/api/tools/invoke",
        "http://openclaw.local:18789/v1/tools/invoke",
    ]
    assert invoke_calls[-1][1]["sessionKey"] == "workspace-123"
    assert list_result["endpoint"] == "/v1/tools"
    assert invoke_result["endpoint"] == "/v1/tools/invoke"
