"""Invite-code user account and workspace APIs."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from dashboard.account_store import INVITE_CODE_LEN, account_store
from dashboard.session import (
    clear_session_cookie,
    client_ip,
    current_account,
    optional_account,
    require_permission,
    set_session_cookie,
)

router = APIRouter()


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=8, max_length=128)
    invite_code: str = Field(..., min_length=INVITE_CODE_LEN, max_length=INVITE_CODE_LEN)
    display_name: str | None = Field(None, max_length=60)
    email: str | None = Field(None, max_length=120)


class LoginRequest(BaseModel):
    username: str
    password: str


class InviteCreateRequest(BaseModel):
    code: str | None = Field(None, min_length=INVITE_CODE_LEN, max_length=INVITE_CODE_LEN)
    max_uses: int = Field(1, ge=1, le=500)
    note: str = Field("", max_length=200)
    expires_at: str | None = None


class PermissionUpdateRequest(BaseModel):
    permission_key: str
    allowed: bool


class WorkspaceSettingsRequest(BaseModel):
    settings: dict = Field(default_factory=dict)


class WorkspaceRenameRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)


@router.get("/me")
async def me(account: dict | None = Depends(optional_account)):
    return {
        "authenticated": bool(account),
        **(account or {}),
    }


@router.post("/register")
async def register(req: RegisterRequest, request: Request, response: Response):
    try:
        account = account_store.create_user(
            username=req.username,
            password=req.password,
            invite_code=req.invite_code,
            display_name=req.display_name,
            email=req.email,
        )
        token, session_meta = account_store.create_session(
            account["user"]["id"],
            user_agent=request.headers.get("user-agent", ""),
            ip_address=client_ip(request),
        )
        set_session_cookie(response, token, max_age=14 * 24 * 3600)
        account_store.record_audit(
            "auth.login",
            user_id=account["user"]["id"],
            workspace_id=account["workspace"]["id"],
            target_type="user",
            target_id=account["user"]["id"],
            reason="login after registration",
        )
        return {"success": True, "authenticated": True, **account, "session": session_meta}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/login")
async def login(req: LoginRequest, request: Request, response: Response):
    account = account_store.authenticate(req.username, req.password)
    if not account:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token, session_meta = account_store.create_session(
        account["user"]["id"],
        user_agent=request.headers.get("user-agent", ""),
        ip_address=client_ip(request),
    )
    set_session_cookie(response, token, max_age=14 * 24 * 3600)
    account_store.record_audit(
        "auth.login",
        user_id=account["user"]["id"],
        workspace_id=account["workspace"]["id"],
        target_type="user",
        target_id=account["user"]["id"],
    )
    return {"success": True, "authenticated": True, **account, "session": session_meta}


@router.post("/logout")
async def logout(response: Response, request: Request):
    token = request.cookies.get("quant_session", "")
    account_store.revoke_session(token)
    clear_session_cookie(response)
    return {"success": True}


@router.get("/workspace")
async def workspace(account: dict = Depends(current_account)):
    return {
        "success": True,
        "user": account["user"],
        "workspace": account["workspace"],
        "permissions": account["permissions"],
    }


@router.put("/workspace/settings")
async def update_workspace_settings(
    req: WorkspaceSettingsRequest,
    account: dict = Depends(current_account),
):
    require_permission(account, "manage_workspace")
    workspace = account_store.update_workspace_settings(account["workspace"]["id"], req.settings)
    account_store.record_audit(
        "workspace.settings.update",
        user_id=account["user"]["id"],
        workspace_id=account["workspace"]["id"],
        target_type="workspace",
        target_id=account["workspace"]["id"],
        metadata=req.settings,
    )
    return {"success": True, "workspace": workspace}


@router.put("/workspace/name")
async def update_workspace_name(
    req: WorkspaceRenameRequest,
    account: dict = Depends(current_account),
):
    require_permission(account, "manage_workspace")
    workspace = account_store.update_workspace_name(account["workspace"]["id"], req.name)
    account_store.record_audit(
        "workspace.name.update",
        user_id=account["user"]["id"],
        workspace_id=account["workspace"]["id"],
        target_type="workspace",
        target_id=account["workspace"]["id"],
        metadata={"name": req.name},
    )
    return {"success": True, "workspace": workspace}


@router.get("/permissions")
async def get_permissions(account: dict = Depends(current_account)):
    return {"success": True, "permissions": account_store.get_permissions(account["workspace"]["id"])}


@router.put("/permissions")
async def update_permission(req: PermissionUpdateRequest, account: dict = Depends(current_account)):
    require_permission(account, "admin")
    permissions = account_store.set_permission(
        account["workspace"]["id"],
        req.permission_key,
        req.allowed,
    )
    account_store.record_audit(
        "permission.update",
        user_id=account["user"]["id"],
        workspace_id=account["workspace"]["id"],
        target_type="permission",
        target_id=req.permission_key,
        metadata={"allowed": req.allowed},
    )
    return {"success": True, "permissions": permissions}


@router.get("/audit")
async def audit_logs(limit: int = 100, account: dict = Depends(current_account)):
    require_permission(account, "manage_workspace")
    return {
        "success": True,
        "items": account_store.list_audit_logs(account["workspace"]["id"], limit=limit),
    }


@router.get("/invites")
async def invite_codes(account: dict = Depends(current_account)):
    require_permission(account, "admin")
    return {"success": True, "items": account_store.list_invite_codes()}


@router.post("/invites")
async def create_invite(req: InviteCreateRequest, account: dict = Depends(current_account)):
    require_permission(account, "admin")
    try:
        invite = account_store.create_invite_code(
            created_by_user_id=account["user"]["id"],
            code=req.code,
            max_uses=req.max_uses,
            note=req.note,
            expires_at=req.expires_at,
        )
        account_store.record_audit(
            "invite.create",
            user_id=account["user"]["id"],
            workspace_id=account["workspace"]["id"],
            target_type="invite_code",
            target_id=invite["code_hash"],
            metadata={"max_uses": req.max_uses},
        )
        return {"success": True, "invite": invite}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
