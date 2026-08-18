"""Shared API key authentication helpers."""
import json
import os
import secrets
from typing import Any, Optional

from fastapi import Request, WebSocket

API_KEY_ENV = "QUANT_SYSTEM_API_KEY"
API_KEYS_ENV = "QUANT_SYSTEM_API_KEYS"
API_KEY_USER_ENV = "QUANT_SYSTEM_API_KEY_USER_ID"
API_KEY_WORKSPACE_ENV = "QUANT_SYSTEM_API_KEY_WORKSPACE_ID"
API_KEY_HEADER = "X-API-Key"


def configured_api_key() -> str:
    """Return the configured API key, or an empty string when auth is disabled."""
    return os.environ.get(API_KEY_ENV, "")


def api_key_enabled() -> bool:
    return bool(configured_api_key() or os.environ.get(API_KEYS_ENV, ""))


def _configured_key_records() -> dict[str, dict[str, str]]:
    """Return key-to-principal mappings without exposing key material."""
    raw = os.environ.get(API_KEYS_ENV, "").strip()
    records: dict[str, dict[str, str]] = {}
    if raw:
        try:
            decoded = json.loads(raw)
            if isinstance(decoded, dict):
                for key, value in decoded.items():
                    if isinstance(value, dict):
                        records[str(key)] = {
                            name: str(value.get(name) or "").strip()
                            for name in ("user_id", "workspace_id")
                        }
                    elif isinstance(value, str):
                        records[str(key)] = {"user_id": value.strip(), "workspace_id": ""}
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    legacy = configured_api_key()
    if legacy:
        records.setdefault(legacy, {
            "user_id": os.environ.get(API_KEY_USER_ENV, "").strip(),
            "workspace_id": os.environ.get(API_KEY_WORKSPACE_ENV, "").strip(),
        })
    return records


def api_key_principal(candidate: Optional[str]) -> dict[str, str] | None:
    if not candidate:
        return None
    for configured, principal in _configured_key_records().items():
        if secrets.compare_digest(candidate, configured):
            return dict(principal)
    return None


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
