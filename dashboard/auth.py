"""Shared API key authentication helpers."""
import os
import secrets
from typing import Optional

from fastapi import Request, WebSocket

API_KEY_ENV = "QUANT_SYSTEM_API_KEY"
API_KEY_HEADER = "X-API-Key"


def configured_api_key() -> str:
    """Return the configured API key, or an empty string when auth is disabled."""
    return os.environ.get(API_KEY_ENV, "")


def api_key_enabled() -> bool:
    return bool(configured_api_key())


def _bearer_token(value: str) -> str:
    prefix = "Bearer "
    return value[len(prefix):].strip() if value.startswith(prefix) else ""


def is_valid_api_key(candidate: Optional[str]) -> bool:
    expected = configured_api_key()
    if not expected:
        return True
    if not candidate:
        return False
    return secrets.compare_digest(candidate, expected)


def request_api_key(request: Request) -> str:
    return (
        request.headers.get(API_KEY_HEADER)
        or _bearer_token(request.headers.get("Authorization", ""))
        or ""
    )


def websocket_api_key(ws: WebSocket) -> str:
    return (
        ws.headers.get(API_KEY_HEADER)
        or _bearer_token(ws.headers.get("Authorization", ""))
        or ws.query_params.get("api_key")
        or ws.query_params.get("token")
        or ""
    )


async def close_unauthorized_websocket(ws: WebSocket):
    await ws.close(code=1008, reason="Invalid API key")
