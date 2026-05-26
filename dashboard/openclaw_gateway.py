"""Adapter for a full external OpenClaw Gateway service."""
from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

from config.settings import OPENCLAW_API_KEY, OPENCLAW_GATEWAY_URL, OPENCLAW_WEB_URL


class OpenClawGateway:
    """Thin HTTP adapter; OpenClaw itself stays a native external service."""

    def __init__(self, base_url: str = OPENCLAW_GATEWAY_URL, api_key: str = OPENCLAW_API_KEY):
        self.base_url = (base_url or "").rstrip("/")
        self.web_url = (OPENCLAW_WEB_URL or base_url or "").rstrip("/")
        self.api_key = api_key or ""

    def _headers(self, workspace_id: str = "") -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            headers["X-API-Key"] = self.api_key
        if workspace_id:
            headers["X-OpenClaw-Workspace"] = workspace_id
            headers["x-openclaw-session-key"] = workspace_id
            headers["x-openclaw-message-channel"] = "quant-dashboard"
        return headers

    def panel_url(self, workspace_id: str, user_id: str, *, embed: bool = False) -> str:
        if not self.web_url:
            return ""
        query = {"workspace": workspace_id, "user": user_id}
        if embed:
            query["embed"] = "1"
        return self._with_query(self.web_url, query)

    def bridge_metadata(self, workspace_id: str) -> dict[str, Any]:
        return {
            "tool_manifest_url": "/api/openclaw/bridge/tools",
            "tool_invoke_url": "/api/openclaw/bridge/tools/invoke",
            "auth": "X-API-Key or Authorization: Bearer <QUANT_SYSTEM_API_KEY>",
            "workspace_header": "X-OpenClaw-Workspace",
            "workspace_id": workspace_id,
        }

    async def health(self, workspace_id: str = "") -> dict[str, Any]:
        if not self.base_url:
            return {"ok": False, "configured": False, "error": "OPENCLAW_GATEWAY_URL 未配置"}
        parsed = urlparse(self.base_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        tcp_ok, tcp_error = await self._tcp_probe(host, port)
        if not tcp_ok:
            return {
                "ok": False,
                "configured": True,
                "transport": "tcp",
                "host": host,
                "port": port,
                "status_code": None,
                "endpoint": "",
                "error": tcp_error or "OpenClaw Gateway 未启动",
                "hint": "请启动完整 OpenClaw Gateway，例如 openclaw gateway start --port 18789。",
            }

        urls = ["/readyz", "/healthz", "/v1/models", "/"]
        async with httpx.AsyncClient(timeout=4.0) as client:
            last_error = ""
            for path in urls:
                try:
                    resp = await client.get(
                        f"{self.base_url}{path}",
                        headers=self._headers(workspace_id),
                    )
                    if resp.status_code < 500:
                        if resp.status_code == 404:
                            last_error = f"HTTP {resp.status_code}"
                            continue
                        payload = self._safe_json(resp)
                        ok = resp.status_code < 400
                        if path == "/readyz" and not ok:
                            last_error = f"HTTP {resp.status_code}"
                            continue
                        return {
                            "ok": ok,
                            "configured": True,
                            "transport": "http",
                            "host": host,
                            "port": port,
                            "status_code": resp.status_code,
                            "endpoint": path,
                            "data": payload,
                        }
                    last_error = f"HTTP {resp.status_code}"
                except Exception as exc:
                    last_error = str(exc)
        return {
            "ok": False,
            "configured": True,
            "transport": "http",
            "host": host,
            "port": port,
            "status_code": None,
            "endpoint": "",
            "error": last_error or "OpenClaw Gateway 不可达",
        }

    async def list_native_tools(self, workspace_id: str = "") -> dict[str, Any]:
        if not self.base_url:
            return {"ok": False, "tools": [], "error": "OPENCLAW_GATEWAY_URL 未配置"}
        async with httpx.AsyncClient(timeout=8.0) as client:
            for path in ("/tools", "/api/tools", "/v1/tools"):
                try:
                    resp = await client.get(
                        f"{self.base_url}{path}",
                        headers=self._headers(workspace_id),
                    )
                    if resp.status_code == 404:
                        continue
                    return {
                        "ok": resp.status_code < 400,
                        "status_code": resp.status_code,
                        "endpoint": path,
                        "data": self._safe_json(resp),
                    }
                except Exception as exc:
                    return {"ok": False, "tools": [], "error": str(exc)}
        return {"ok": False, "tools": [], "error": "OpenClaw 工具端点未发现"}

    async def invoke_native_tool(
        self,
        workspace_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        session_key: str = "",
    ) -> dict[str, Any]:
        if not self.base_url:
            return {"ok": False, "error": "OPENCLAW_GATEWAY_URL 未配置"}
        payload = {
            "tool": tool_name,
            "args": arguments or {},
            "sessionKey": session_key or workspace_id,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            for path in ("/tools/invoke", "/api/tools/invoke", "/v1/tools/invoke"):
                try:
                    resp = await client.post(
                        f"{self.base_url}{path}",
                        headers=self._headers(workspace_id),
                        json=payload,
                    )
                    if resp.status_code == 404:
                        continue
                    return {
                        "ok": resp.status_code < 400,
                        "status_code": resp.status_code,
                        "endpoint": path,
                        "data": self._safe_json(resp),
                    }
                except Exception as exc:
                    return {"ok": False, "error": str(exc)}
        return {"ok": False, "error": "OpenClaw 工具调用端点未发现"}

    async def chat(
        self,
        workspace_id: str,
        messages: list[dict[str, str]],
        user_id: str = "",
    ) -> dict[str, Any]:
        if not self.base_url:
            return {"ok": False, "error": "OPENCLAW_GATEWAY_URL 未配置"}
        payload = {
            "model": "openclaw/default",
            "messages": messages,
            "user_id": user_id,
            "user": workspace_id or user_id or "quant-dashboard",
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=45.0) as client:
            for path in ("/v1/chat/completions", "/v1/responses", "/chat", "/api/chat", "/v1/chat"):
                try:
                    request_payload = payload
                    if path == "/v1/responses":
                        request_payload = {
                            "model": "openclaw/default",
                            "input": messages[-1]["content"] if messages else "",
                            "user": workspace_id or user_id or "quant-dashboard",
                            "stream": False,
                        }
                    resp = await client.post(
                        f"{self.base_url}{path}",
                        headers=self._headers(workspace_id),
                        json=request_payload,
                    )
                    if resp.status_code == 404:
                        continue
                    data = self._safe_json(resp)
                    return {
                        "ok": resp.status_code < 400,
                        "status_code": resp.status_code,
                        "endpoint": path,
                        "data": data,
                    }
                except Exception as exc:
                    return {"ok": False, "error": str(exc)}
        return {"ok": False, "error": "OpenClaw 聊天端点未发现"}

    def _safe_json(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except Exception:
            return {"text": response.text[:2000]}

    async def _tcp_probe(self, host: str, port: int) -> tuple[bool, str]:
        writer = None
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=1.5)
            return True, ""
        except Exception as exc:
            return False, str(exc)
        finally:
            if writer:
                writer.close()
                await writer.wait_closed()

    def _with_query(self, url: str, query: dict[str, str]) -> str:
        parsed = urlparse(url)
        existing = dict(parse_qsl(parsed.query, keep_blank_values=True))
        merged = {**existing, **query}
        return urlunparse(parsed._replace(query=urlencode(merged)))


openclaw_gateway = OpenClawGateway()
