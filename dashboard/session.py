"""Session helpers for invite-code user accounts."""
from __future__ import annotations

import os

from fastapi import Cookie, Depends, HTTPException, Request, Response, WebSocket

from dashboard.account_store import account_store

SESSION_COOKIE = "quant_session"

def session_cookie_options(max_age: int | None = None) -> dict:
    secure = os.getenv("APP_ENV", "development").lower() == "production"
    opts = {
        "httponly": True,
        "samesite": "lax",
        "secure": secure,
        "path": "/",
    }
    if max_age is not None:
        opts["max_age"] = max_age
    return opts


def set_session_cookie(response: Response, token: str, max_age: int) -> None:
    response.set_cookie(SESSION_COOKIE, token, **session_cookie_options(max_age=max_age))


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="lax")


async def optional_account(
    quant_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict | None:
    return account_store.get_user_by_session(quant_session or "")


async def optional_websocket_account(ws: WebSocket) -> dict | None:
    return account_store.get_user_by_session(ws.cookies.get(SESSION_COOKIE, ""))


async def current_account(account: dict | None = Depends(optional_account)) -> dict:
    if not account:
        raise HTTPException(status_code=401, detail="请先登录")
    return account


def require_permission(account: dict, permission_key: str) -> None:
    permissions = account.get("permissions") or {}
    if not permissions.get(permission_key):
        raise HTTPException(status_code=403, detail=f"缺少权限: {permission_key}")


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else ""
