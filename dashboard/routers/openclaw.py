"""Full OpenClaw service integration surface."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from alpha import nl_strategy
from config.settings import OPENCLAW_CHAT_TIMEOUT, OPENCLAW_ENABLE_LOCAL_FALLBACK
from dashboard.account_store import account_store, iso_now
from dashboard.auth import api_key_enabled, is_valid_api_key, request_api_key
from dashboard.openclaw_gateway import openclaw_gateway
from dashboard.openclaw_service import openclaw_service_manager
from dashboard.openclaw_tools import SYSTEM_TOOLS, TOOL_MAP, invoke_system_tool
from dashboard.session import current_account, require_permission
from data.storage.storage import DataStorage

router = APIRouter()
conversation_store = DataStorage()

CONFIRMATION_TTL_SECONDS = 300
CONFIRMATION_PERMISSION_KEYS = {
    "quant.paper.order": "write_paper_trade",
    "quant.paper.close_position": "write_paper_trade",
    "quant.skill.record": "manage_skills",
}
_CONFIRMATION_SECRET = hashlib.sha256(
    (
        os.getenv("QUANT_CONFIRM_SECRET")
        or os.getenv("QUANT_SYSTEM_API_KEY")
        or os.getenv("OPENCLAW_API_KEY")
        or "openclaw-confirmation-secret"
    ).encode("utf-8")
).digest()


class ToolInvokeRequest(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    native: bool = False
    confirmed: bool = False
    confirmation_token: str = Field("", max_length=1200)


class MemoryCreateRequest(BaseModel):
    title: str = Field("", max_length=160)
    content: str = Field(..., min_length=1)
    code: str = Field("", max_length=12)
    tags: list[str] = Field(default_factory=list)
    source: str = "manual"


class SkillRecordRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    version: str = Field("", max_length=60)
    status: str = Field("installed", max_length=40)
    source: str = Field("", max_length=300)
    permissions: list[str] = Field(default_factory=list)


class DailyReportGenerateRequest(BaseModel):
    trade_date: str = Field("", max_length=20)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    history: list[ChatMessage] = Field(default_factory=list)


class ConversationSaveRequest(BaseModel):
    id: str = Field(..., min_length=1, max_length=120)
    title: str = Field("新对话", max_length=200)
    messages: list[ChatMessage] = Field(default_factory=list)


class BridgeToolInvokeRequest(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    args: dict[str, Any] = Field(default_factory=dict)
    workspace_id: str = Field("", max_length=120)
    sessionKey: str = Field("", max_length=120)
    confirmed: bool = False
    confirmation_token: str = Field("", max_length=1200)


def _require_bridge_api_key(request: Request) -> None:
    if not api_key_enabled():
        raise HTTPException(status_code=503, detail="QUANT_SYSTEM_API_KEY 未配置，OpenClaw Bridge 暂不可用")
    if not is_valid_api_key(request_api_key(request)):
        raise HTTPException(status_code=401, detail="无效的 OpenClaw Bridge API Key")


def _bridge_account(request: Request, workspace_id: str = "") -> dict:
    openclaw_workspace_id = (
        workspace_id
        or request.headers.get("X-OpenClaw-Workspace", "")
        or request.query_params.get("workspace_id", "")
        or request.query_params.get("sessionKey", "")
    ).strip()
    if not openclaw_workspace_id:
        raise HTTPException(status_code=400, detail="缺少 OpenClaw workspace_id")
    account = account_store.get_user_bundle_by_openclaw_workspace_id(openclaw_workspace_id)
    if not account:
        raise HTTPException(status_code=404, detail="OpenClaw 工作区不存在")
    return account


def _skill_command_prefix(message: str) -> str:
    text = (message or "").lstrip()
    for prefix in ("/skill", "@skill", "!skill"):
        if text.startswith(prefix):
            return prefix
    return ""


def _parse_skill_command(message: str) -> dict[str, Any] | None:
    text = (message or "").strip()
    prefix = _skill_command_prefix(text)
    if not prefix:
        return None
    body = text[len(prefix):].strip()
    if not body:
        return {"command": "list", "raw": text}
    parts = body.split()
    command = parts[0].lower()
    if command == "record":
        command = "install"
    if command not in {"install", "approve", "deny", "list"}:
        return None
    return {
        "command": command,
        "args": parts[1:],
        "raw": text,
    }


def _parse_skill_kv(args: list[str]) -> tuple[str, dict[str, str]]:
    values: dict[str, str] = {}
    free: list[str] = []
    for token in args:
        if "=" in token:
            key, value = token.split("=", 1)
            values[key.strip().lower().lstrip("-")] = value.strip()
        elif token.startswith("--") and len(token) > 2:
            values[token[2:].strip().lower()] = "true"
        else:
            free.append(token)
    return " ".join(free).strip(), values


def _skill_command_target(args: list[str]) -> tuple[str, str]:
    rest, values = _parse_skill_kv(args)
    target = values.get("id") or values.get("request_id") or values.get("skill") or values.get("name") or ""
    note = rest
    if not target and rest:
        parts = rest.split()
        target = parts[0]
        note = " ".join(parts[1:]).strip()
    return target.strip(), note


def _skill_command_summary(request_row: dict | None) -> dict[str, Any]:
    if not request_row:
        return {}
    return {
        "id": request_row.get("id"),
        "skill_name": request_row.get("skill_name"),
        "status": request_row.get("status"),
        "version": request_row.get("version", ""),
        "source": request_row.get("source", ""),
        "reason": request_row.get("reason", ""),
        "note": request_row.get("note", ""),
        "decided_by_user_id": request_row.get("decided_by_user_id"),
        "decided_at": request_row.get("decided_at"),
    }


def _recent_skill_command_history(account: dict, limit: int = 10) -> list[dict[str, Any]]:
    return [
        _skill_command_summary(item)
        for item in account_store.list_skill_install_requests(
            account["workspace"]["id"],
            limit=limit,
        )
    ]


def _skill_lookup_request(account: dict, target: str, status: str | None = "pending") -> dict | None:
    if not target:
        return None
    workspace_id = account["workspace"]["id"]
    row = account_store.get_skill_install_request(target, workspace_id=workspace_id)
    if row:
        if status is None or row.get("status") == status:
            return row
        return row
    row = account_store.get_latest_skill_install_request(workspace_id, target, status=status)
    if row:
        return row
    return account_store.get_latest_skill_install_request(workspace_id, target, status=None)


def _skill_command_list(account: dict, args: list[str]) -> dict[str, Any]:
    rest, values = _parse_skill_kv(args)
    status = values.get("status") or values.get("state") or ""
    skill_name = values.get("skill") or values.get("name") or rest.strip()
    items = account_store.list_skill_install_requests(
        account["workspace"]["id"],
        status=status or None,
        limit=30,
    )
    if skill_name:
        items = [item for item in items if item.get("skill_name") == skill_name or item.get("id") == skill_name]
    return {
        "success": True,
        "mode": "skill-command",
        "command": "list",
        "content": f"技能请求 {len(items)} 条。",
        "request": None,
        "items": items,
    }


async def _handle_skill_command(account: dict, command: dict[str, Any]) -> dict[str, Any]:
    require_permission(account, "manage_skills")
    action = command.get("command")
    args = list(command.get("args") or [])
    raw = str(command.get("raw") or "").strip()

    if action == "list":
        return _skill_command_list(account, args)

    if action == "install":
        rest, values = _parse_skill_kv(args)
        skill_name = values.get("skill") or values.get("name") or ""
        note = values.get("note") or values.get("reason") or ""
        if not skill_name:
            parts = rest.split()
            skill_name = parts[0] if parts else ""
            note = note or " ".join(parts[1:]).strip()
        if not skill_name:
            raise HTTPException(status_code=400, detail="Skill 名称不能为空")
        request_row = account_store.create_skill_install_request(
            workspace_id=account["workspace"]["id"],
            user_id=account["user"]["id"],
            skill_name=skill_name,
            version=values.get("version", ""),
            source=values.get("source", ""),
            reason=values.get("reason", note),
            note=note,
        )
        account_store.record_audit(
            "openclaw.skill.request",
            user_id=account["user"]["id"],
            workspace_id=account["workspace"]["id"],
            target_type="skill_install_request",
            target_id=request_row["id"],
            status="pending",
            metadata={"request": _skill_command_summary(request_row), "raw": raw},
        )
        return {
            "success": True,
            "mode": "skill-command",
            "command": "install",
            "content": f"{skill_name} 已提交请求。",
            "request": request_row,
            "result": {"status": "pending"},
        }

    target, rest = _skill_command_target(args)
    if not target:
        raise HTTPException(status_code=400, detail="请提供 Skill 名称或请求 ID")
    request_row = _skill_lookup_request(account, target)
    if not request_row:
        raise HTTPException(status_code=404, detail="Skill 请求不存在")
    if request_row.get("status") != "pending":
        raise HTTPException(status_code=409, detail="Skill 请求已处理")
    note = rest.strip()
    status = "approved" if action == "approve" else "denied"
    decided_at = iso_now()
    updated = account_store.update_skill_install_request(
        request_row["id"],
        account["workspace"]["id"],
        status=status,
        reason=note or request_row.get("reason", ""),
        note=note or request_row.get("note", ""),
        decided_by_user_id=account["user"]["id"],
        decided_at=decided_at,
    )
    account_store.record_audit(
        f"openclaw.skill.{action}",
        user_id=account["user"]["id"],
        workspace_id=account["workspace"]["id"],
        target_type="skill_install_request",
        target_id=request_row["id"],
        status=status,
        metadata={"request": _skill_command_summary(updated), "raw": raw},
    )
    if action == "approve":
        skill = account_store.upsert_skill(
            workspace_id=account["workspace"]["id"],
            name=request_row["skill_name"],
            version=request_row.get("version", ""),
            status="installed",
            source=request_row.get("source", ""),
            permissions=[],
        )
        return {
            "success": True,
            "mode": "skill-command",
            "command": "approve",
            "content": f"{request_row['skill_name']} 已批准。",
            "request": updated,
            "result": {"status": "approved", "skill": skill},
        }
    return {
        "success": True,
        "mode": "skill-command",
        "command": "deny",
        "content": f"{request_row['skill_name']} 已拒绝。",
        "request": updated,
        "result": {"status": "denied"},
    }


@router.get("/status")
async def status(account: dict = Depends(current_account)):
    health = await openclaw_gateway.health(account["workspace"]["openclaw_workspace_id"])
    workspace_settings = account["workspace"].get("settings", {})
    return {
        "success": True,
        "mode": "full-external-service",
        "service": health,
        "workspace": account["workspace"],
        "setup_completed": bool(workspace_settings.get("openclaw_setup_completed", False)),
        "permissions": account["permissions"],
        "panel_url": openclaw_gateway.panel_url(
            account["workspace"]["openclaw_workspace_id"],
            account["user"]["id"],
        ),
        "embed_url": openclaw_gateway.panel_url(
            account["workspace"]["openclaw_workspace_id"],
            account["user"]["id"],
            embed=True,
        ),
        "bridge": openclaw_gateway.bridge_metadata(account["workspace"]["openclaw_workspace_id"]),
        "managed_service": openclaw_service_manager.status(),
        "skill_command_history": _recent_skill_command_history(account),
    }


@router.get("/service/status")
async def service_status(account: dict = Depends(current_account)):
    require_permission(account, "manage_workspace")
    return {"success": True, "service": openclaw_service_manager.status()}


@router.post("/service/start")
async def service_start(account: dict = Depends(current_account)):
    require_permission(account, "manage_workspace")
    return {"success": True, "service": await openclaw_service_manager.start()}


@router.post("/service/stop")
async def service_stop(account: dict = Depends(current_account)):
    require_permission(account, "manage_workspace")
    return {"success": True, "service": await openclaw_service_manager.stop()}


@router.post("/service/restart")
async def service_restart(account: dict = Depends(current_account)):
    require_permission(account, "manage_workspace")
    return {"success": True, "service": await openclaw_service_manager.restart()}


@router.get("/panel")
async def panel(account: dict = Depends(current_account)):
    require_permission(account, "chat")
    return {
        "success": True,
        "url": openclaw_gateway.panel_url(
            account["workspace"]["openclaw_workspace_id"],
            account["user"]["id"],
        ),
        "embed_url": openclaw_gateway.panel_url(
            account["workspace"]["openclaw_workspace_id"],
            account["user"]["id"],
            embed=True,
        ),
        "workspace_id": account["workspace"]["openclaw_workspace_id"],
        "mode": account["workspace"].get("settings", {}).get("native_panel_mode", "iframe"),
    }


@router.get("/setup")
async def setup_state(account: dict = Depends(current_account)):
    settings = account["workspace"].get("settings", {})
    return {
        "success": True,
        "setup_completed": bool(settings.get("openclaw_setup_completed", False)),
        "workspace": account["workspace"],
        "permissions": account["permissions"],
        "service": openclaw_service_manager.status(),
        "panel_url": openclaw_gateway.panel_url(
            account["workspace"]["openclaw_workspace_id"],
            account["user"]["id"],
        ),
        "skill_command_history": _recent_skill_command_history(account),
    }


class SetupCompleteRequest(BaseModel):
    setup_completed: bool = True
    native_panel_mode: str = Field("iframe", max_length=32)
    service_mode: str = Field("managed", max_length=32)


@router.post("/setup/complete")
async def setup_complete(req: SetupCompleteRequest, account: dict = Depends(current_account)):
    require_permission(account, "manage_workspace")
    settings = {
        **account["workspace"].get("settings", {}),
        "openclaw_setup_completed": bool(req.setup_completed),
        "native_panel_mode": req.native_panel_mode or "iframe",
        "openclaw_service_mode": req.service_mode or "managed",
    }
    workspace = account_store.update_workspace_settings(account["workspace"]["id"], settings)
    account_store.record_audit(
        "openclaw.setup.complete",
        user_id=account["user"]["id"],
        workspace_id=account["workspace"]["id"],
        target_type="workspace",
        target_id=account["workspace"]["id"],
        metadata=settings,
    )
    return {"success": True, "workspace": workspace}


@router.post("/chat")
async def chat(req: ChatRequest, account: dict = Depends(current_account)):
    require_permission(account, "chat")
    history = [
        {"role": item.role, "content": item.content}
        for item in req.history[-20:]
        if item.role in {"user", "assistant"} and item.content
    ]
    skill_command = _parse_skill_command(req.message)
    if skill_command:
        return await _handle_skill_command(account, skill_command)
    detected_action = _detect_direct_action(req.message, history)
    if detected_action:
        tool_name = detected_action["tool"]
        arguments = detected_action.get("arguments") or {}
        if detected_action.get("confirm_required") and _tool_confirmation_required(account, tool_name):
            content, actions = _build_pending_confirmation(account, tool_name, arguments)
            account_store.record_audit(
                "openclaw.chat.tool_pending",
                user_id=account["user"]["id"],
                workspace_id=account["workspace"]["id"],
                target_type="tool",
                target_id=tool_name,
                tool_name=tool_name,
                status="pending_confirmation",
                metadata={"arguments": arguments},
            )
            return {
                "success": True,
                "mode": "system-action-pending",
                "content": content,
                "actions": actions,
                "detected_action": detected_action,
            }
        try:
            tool_result = await invoke_system_tool(account, tool_name, arguments)
        except HTTPException as exc:
            account_store.record_audit(
                "openclaw.chat.system_action_error",
                user_id=account["user"]["id"],
                workspace_id=account["workspace"]["id"],
                target_type="tool",
                target_id=tool_name,
                tool_name=tool_name,
                status="error",
                reason=str(exc.detail),
                metadata={"arguments": arguments},
            )
            return {
                "success": True,
                "mode": "system-action-error",
                "content": f"{TOOL_MAP.get(tool_name, {}).get('label', tool_name)} 执行失败：{exc.detail}",
                "error": str(exc.detail),
                "detected_action": detected_action,
            }
        content, actions = _format_action_response(tool_name, tool_result, arguments)
        return {
            "success": True,
            "mode": "system-action",
            "content": content,
            "actions": actions,
            "tool_result": tool_result,
            "detected_action": detected_action,
        }

    messages = [*history, {"role": "user", "content": req.message}]
    try:
        native = await asyncio.wait_for(
            openclaw_gateway.chat(
                workspace_id=account["workspace"]["openclaw_workspace_id"],
                messages=messages,
                user_id=account["user"]["id"],
            ),
            timeout=OPENCLAW_CHAT_TIMEOUT,
        )
    except Exception as exc:
        native = {"ok": False, "error": str(exc)}
    if native.get("ok"):
        answer = _extract_native_chat_text(native.get("data"))
        if answer:
            account_store.record_audit(
                "openclaw.chat.native",
                user_id=account["user"]["id"],
                workspace_id=account["workspace"]["id"],
                target_type="chat",
                target_id=account["workspace"]["openclaw_workspace_id"],
                status="ok",
                metadata={"endpoint": native.get("endpoint")},
            )
            return {"success": True, "mode": "native", "content": answer, "native": native}

    if not OPENCLAW_ENABLE_LOCAL_FALLBACK:
        reason = str(native.get("error") or native.get("status_code") or "OpenClaw 未返回有效内容")
        account_store.record_audit(
            "openclaw.chat.native_error",
            user_id=account["user"]["id"],
            workspace_id=account["workspace"]["id"],
            target_type="chat",
            target_id=account["workspace"]["openclaw_workspace_id"],
            status="error",
            reason=reason,
            metadata={"native": native},
        )
        return {
            "success": True,
            "mode": "native-error",
            "content": "龙虾原生服务这次没有返回有效回复，请稍后重试或到龙虾设置页查看服务日志。",
            "native": native,
        }

    try:
        fallback = ""
        stream = await asyncio.wait_for(nl_strategy.chat(req.message, history=history), timeout=5.0)

        async def collect() -> str:
            text = ""
            async for token in stream:
                text += token
            return text

        fallback = await asyncio.wait_for(collect(), timeout=20.0)
        mode = "local-llm"
        content = fallback or "我现在可以先用平台内置量化助手回答；完整 OpenClaw 原生服务还没有连接。"
    except Exception as exc:
        mode = "offline"
        content = (
            "OpenClaw 原生服务还没有连接，本地 LLM 也未配置成功。"
            "你可以先启动 OpenClaw Gateway，或配置 OPENAI_API_KEY 后继续聊天。"
        )
        account_store.record_audit(
            "openclaw.chat.fallback_error",
            user_id=account["user"]["id"],
            workspace_id=account["workspace"]["id"],
            target_type="chat",
            target_id=account["workspace"]["openclaw_workspace_id"],
            status="error",
            reason=str(exc),
        )
        return {"success": True, "mode": mode, "content": content, "error": str(exc), "native": native}

    account_store.record_audit(
        "openclaw.chat.fallback",
        user_id=account["user"]["id"],
        workspace_id=account["workspace"]["id"],
        target_type="chat",
        target_id=account["workspace"]["openclaw_workspace_id"],
        status="ok",
        reason=str(native.get("error") or ""),
    )
    return {"success": True, "mode": mode, "content": content, "native": native}


@router.get("/conversations")
async def list_conversations(account: dict = Depends(current_account)):
    workspace_id = account["workspace"]["id"]
    return {
        "success": True,
        "items": conversation_store.list_conversations(workspace_id=workspace_id, surface="openclaw"),
    }


@router.get("/conversations/{conv_id}")
async def get_conversation(conv_id: str, account: dict = Depends(current_account)):
    workspace_id = account["workspace"]["id"]
    conv = conversation_store.get_conversation(conv_id, workspace_id=workspace_id, surface="openclaw")
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    return {"success": True, "data": conv}


@router.post("/conversations")
async def save_conversation(req: ConversationSaveRequest, account: dict = Depends(current_account)):
    workspace_id = account["workspace"]["id"]
    msgs = [{"role": m.role, "content": m.content} for m in req.messages]
    conversation_store.save_conversation(
        req.id,
        req.title,
        msgs,
        workspace_id=workspace_id,
        surface="openclaw",
    )
    return {"success": True}


@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: str, account: dict = Depends(current_account)):
    workspace_id = account["workspace"]["id"]
    ok = conversation_store.delete_conversation(conv_id, workspace_id=workspace_id, surface="openclaw")
    return {"success": True, "removed": ok}


def _extract_native_chat_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        return ""
    for key in ("content", "message", "text", "answer", "response"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"].strip()
            if isinstance(first.get("text"), str):
                return first["text"].strip()
    data = payload.get("data")
    if data is not payload:
        return _extract_native_chat_text(data)
    return ""


def _extract_recent_code(history: list[dict[str, str]]) -> str:
    for item in reversed(history[-20:]):
        content = str(item.get("content") or "")
        match = re.search(r"(?<!\d)(\d{6})(?!\d)", content)
        if match:
            return match.group(1)
    return ""


def _extract_price(text: str) -> float | None:
    match = re.search(r"(?:价格|价位|限价|以)\s*[:：]?\s*(\d+(?:\.\d+)?)", text)
    if match:
        try:
            return float(match.group(1))
        except Exception:
            return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*元", text)
    if match:
        try:
            return float(match.group(1))
        except Exception:
            return None
    return None


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _arguments_hash(arguments: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(arguments or {}).encode("utf-8")).hexdigest()


def _make_confirmation_token(account: dict, tool_name: str, arguments: dict[str, Any]) -> str:
    payload = {
        "user_id": account["user"]["id"],
        "workspace_id": account["workspace"]["id"],
        "tool": tool_name,
        "args_sha": _arguments_hash(arguments),
        "exp": int(time.time()) + CONFIRMATION_TTL_SECONDS,
        "nonce": secrets.token_urlsafe(10),
    }
    body = _b64url(_canonical_json(payload).encode("utf-8"))
    signature = _b64url(hmac.new(_CONFIRMATION_SECRET, body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{signature}"


def _verify_confirmation_token(account: dict, tool_name: str, arguments: dict[str, Any], token: str) -> bool:
    try:
        body, signature = token.split(".", 1)
    except ValueError:
        return False
    expected = _b64url(hmac.new(_CONFIRMATION_SECRET, body.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        return False
    try:
        payload = json.loads(_b64url_decode(body).decode("utf-8"))
    except Exception:
        return False
    if int(payload.get("exp") or 0) < int(time.time()):
        return False
    return (
        payload.get("user_id") == account["user"]["id"]
        and payload.get("workspace_id") == account["workspace"]["id"]
        and payload.get("tool") == tool_name
        and payload.get("args_sha") == _arguments_hash(arguments)
    )


def _tool_confirmation_required(account: dict, tool_name: str) -> bool:
    tool = TOOL_MAP.get(tool_name) or {}
    if not tool.get("confirm"):
        return False
    settings = account.get("workspace", {}).get("settings") or {}
    confirmations = settings.get("tool_confirmations") or {}
    permission_key = CONFIRMATION_PERMISSION_KEYS.get(tool_name, tool.get("permission", ""))
    if permission_key in confirmations:
        return bool(confirmations[permission_key])
    return True


def _require_tool_confirmation(account: dict, tool_name: str, arguments: dict[str, Any], confirmed: bool, token: str) -> None:
    if not _tool_confirmation_required(account, tool_name):
        return
    if not confirmed or not _verify_confirmation_token(account, tool_name, arguments, token):
        raise HTTPException(status_code=409, detail="这个工具需要用户在龙虾确认卡中确认后才能执行")


def _extract_volume(text: str) -> int | None:
    match = re.search(r"(\d+)\s*股", text)
    if match:
        try:
            return max(100, int(match.group(1)) // 100 * 100)
        except Exception:
            return None
    match = re.search(r"(\d+)\s*手", text)
    if match:
        try:
            return max(100, int(match.group(1)) * 100)
        except Exception:
            return None
    match = re.search(r"(\d+)\s*张", text)
    if match:
        try:
            return max(100, int(match.group(1)) * 100)
        except Exception:
            return None
    return None


def _detect_direction(text: str) -> str:
    if any(token in text for token in ("卖出", "平仓", "清仓", "减仓")):
        return "sell"
    if any(token in text for token in ("买入", "买进", "加仓", "下单")):
        return "buy"
    return "buy"


def _extract_action_reason(text: str) -> str:
    match = re.search(r"(?:原因是|理由是|因为|由于|关注理由[:：]?|下单原因[:：]?)\s*(.+)$", text)
    if match:
        return match.group(1).strip()[:300]
    return text[:200]


def _detect_direct_action(message: str, history: list[dict[str, str]]) -> dict[str, Any] | None:
    text = (message or "").strip()
    if not text:
        return None
    code = re.search(r"(?<!\d)(\d{6})(?!\d)", text)
    stock_code = code.group(1) if code else _extract_recent_code(history)

    if any(token in text for token in ("生成日报", "收益日报", "日报")):
        return {
            "tool": "quant.report.generate_daily",
            "arguments": {},
            "confirm_required": False,
        }

    if any(token in text for token in ("模拟盘摘要", "模拟盘状态", "持仓", "收益情况", "复盘")) and not any(token in text for token in ("日报", "生成日报")):
        return {
            "tool": "quant.paper.summary",
            "arguments": {},
            "confirm_required": False,
        }

    if any(token in text for token in ("数据底座", "数据快照", "数据状态")):
        return {
            "tool": "quant.data.snapshot",
            "arguments": {},
            "confirm_required": False,
        }

    if any(token in text for token in ("Qlib", "信号", "预测Top", "预测池", "Top")):
        return {
            "tool": "quant.signals.top",
            "arguments": {},
            "confirm_required": False,
        }

    if any(token in text for token in ("估值", "PEG", "研报")) and stock_code:
        return {
            "tool": "quant.valuation.peg",
            "arguments": {"code": stock_code},
            "confirm_required": False,
        }

    if any(token in text for token in ("移出自选", "删除自选", "取消自选", "从自选移除")) and stock_code:
        return {
            "tool": "quant.watchlist.remove",
            "arguments": {"code": stock_code, "reason": _extract_action_reason(text)},
            "confirm_required": False,
        }

    if any(token in text for token in ("加入自选", "加自选", "加入自選", "自选")) and stock_code:
        return {
            "tool": "quant.watchlist.add",
            "arguments": {"code": stock_code, "reason": _extract_action_reason(text)},
            "confirm_required": False,
        }

    if any(token in text for token in ("打开", "详情", "打开详情", "股票详情")) and stock_code:
        return {
            "tool": "quant.stock.open",
            "arguments": {"code": stock_code, "reason": _extract_action_reason(text)},
            "confirm_required": False,
        }

    if any(token in text for token in ("平仓", "清仓", "卖出持仓", "全部卖出")) and stock_code:
        volume = _extract_volume(text)
        return {
            "tool": "quant.paper.close_position",
            "arguments": {
                "code": stock_code,
                "volume": volume,
                "reason": text[:200],
            },
            "confirm_required": True,
        }

    if any(token in text for token in ("模拟买入", "模拟卖出", "模拟下单", "买入", "卖出", "下单")) and stock_code:
        price = _extract_price(text)
        volume = _extract_volume(text) or 100
        direction = _detect_direction(text)
        return {
            "tool": "quant.paper.order",
            "arguments": {
                "code": stock_code,
                "direction": direction,
                "volume": volume,
                "order_type": "limit" if price is not None else "market",
                "price": price,
                "reason": text[:200],
            },
            "confirm_required": True,
        }

    return None


def _fmt_money(value: Any) -> str:
    try:
        return f"{float(value):,.2f}"
    except Exception:
        return "--"


def _report_display_title(title: str, trade_date: str) -> str:
    title = str(title or "").strip() or "模拟盘收益日报"
    prefix = f"{trade_date} "
    if trade_date and title.startswith(prefix):
        stripped = title[len(prefix):].strip()
        return stripped or title
    return title


def _fmt_percent(value: Any) -> str:
    try:
        return f"{float(value) * 100:.2f}%"
    except Exception:
        return "--"


def _format_action_response(tool_name: str, result: dict[str, Any], arguments: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    payload = result.get("result") if isinstance(result, dict) else {}
    payload = payload if isinstance(payload, dict) else {}
    actions: list[dict[str, Any]] = []
    content = "已执行。"
    code = str(arguments.get("code") or payload.get("code") or "").strip()

    if tool_name == "quant.watchlist.add":
        added = payload.get("added")
        message = payload.get("message") or ("添加成功" if added else "已在自选股中")
        content = f"{code} {message}。".strip()
        if code:
            actions.append({"tool": "quant.stock.open", "label": "打开详情", "arguments": {"code": code}})
            actions.append({"tool": "quant.watchlist.list", "label": "查看自选", "arguments": {}})
    elif tool_name == "quant.watchlist.remove":
        removed = payload.get("removed")
        content = f"{code} {'已移出自选' if removed else '未在自选中'}。".strip()
        actions.append({"tool": "quant.watchlist.list", "label": "查看自选", "arguments": {}})
    elif tool_name == "quant.stock.open":
        name = str(payload.get("name") or "").strip()
        content = f"已打开 {code}{(' ' + name) if name else ''} 的股票详情。".strip()
        if code:
            actions.append({"tool": "quant.watchlist.add", "label": "加入自选", "arguments": {"code": code}})
            actions.append({"tool": "quant.valuation.peg", "label": "查看估值", "arguments": {"code": code}})
    elif tool_name == "quant.paper.summary":
        metrics = payload.get("metrics") or {}
        positions = payload.get("positions") or []
        recent_orders = payload.get("recent_orders") or []
        total_equity = metrics.get("total_equity")
        daily_return = metrics.get("daily_return")
        cumulative_return = metrics.get("cumulative_return")
        max_drawdown = metrics.get("max_drawdown")
        content = (
            "模拟盘摘要："
            f"总权益 {_fmt_money(total_equity)}，"
            f"当日收益 {_fmt_percent(daily_return)}，"
            f"累计收益 {_fmt_percent(cumulative_return)}，"
            f"最大回撤 {_fmt_percent(max_drawdown)}，"
            f"持仓 {len(positions)} 个，"
            f"最近订单 {len(recent_orders)} 笔。"
        )
        actions.append({"tool": "quant.report.generate_daily", "label": "生成日报", "arguments": {}})
    elif tool_name in {"quant.paper.order", "quant.paper.close_position"}:
        order = payload.get("order") or {}
        order_code = str(order.get("code") or arguments.get("code") or code).strip()
        direction = str(order.get("direction") or arguments.get("direction") or "buy").strip()
        volume = int(order.get("volume") or arguments.get("volume") or 0)
        direction_label = "买入" if direction == "buy" else "卖出"
        action_label = "平仓" if tool_name == "quant.paper.close_position" else direction_label
        price = order.get("price")
        price_text = f"，价格 {_fmt_money(price)}" if price not in (None, "") else ""
        order_id = str(order.get("order_id") or "").strip()
        order_text = f"，订单号 {order_id}" if order_id else ""
        content = f"{order_code} 模拟盘{action_label} {volume} 股已提交{price_text}{order_text}。".strip()
        if order_code:
            actions.append({"tool": "quant.paper.summary", "label": "查看摘要", "arguments": {}})
            actions.append({"tool": "quant.stock.open", "label": "打开详情", "arguments": {"code": order_code}})
    elif tool_name == "quant.report.generate_daily":
        report = payload.get("report") or {}
        trade_date = str(report.get("trade_date") or arguments.get("trade_date") or "").strip()
        title = _report_display_title(report.get("title") or "模拟盘收益日报", trade_date)
        content = f"{trade_date + ' ' if trade_date else ''}{title}已生成。"
        actions.append({"tool": "quant.paper.summary", "label": "查看摘要", "arguments": {}})
        if trade_date:
            actions.append({"tool": "quant.report.open", "label": "查看日报", "arguments": {"trade_date": trade_date}})
    elif tool_name == "quant.report.open":
        report = payload.get("report") or {}
        trade_date = str(report.get("trade_date") or arguments.get("trade_date") or "").strip()
        title = _report_display_title(report.get("title") or "模拟盘收益日报", trade_date)
        content = f"{trade_date + ' ' if trade_date else ''}{title}已打开。"
        if trade_date:
            actions.append({"tool": "quant.report.generate_daily", "label": "重新生成", "arguments": {"trade_date": trade_date}})
    elif tool_name == "quant.watchlist.list":
        items = payload.get("items") or []
        preview = []
        for item in items[:5]:
            code = str(item.get("code") or "").strip()
            name = str(item.get("name") or "").strip()
            preview.append(f"{code}{(' ' + name) if name else ''}".strip())
        content = "自选股：" + ("，".join(preview) if preview else "暂无自选股")
        for item in items[:3]:
            code = str(item.get("code") or "").strip()
            if code:
                actions.append({"tool": "quant.stock.open", "label": f"打开 {code}", "arguments": {"code": code}})
    elif tool_name == "quant.valuation.peg":
        content = f"{code} 的估值快照已生成。"
        if code:
            actions.append({"tool": "quant.stock.open", "label": "打开详情", "arguments": {"code": code}})
    elif tool_name == "quant.data.snapshot":
        quote = payload.get("quote") or {}
        content = (
            "数据底座："
            f"股票 {payload.get('stock_count', '--')} 只，"
            f"自选 {payload.get('watchlist_count', '--')} 只，"
            f"行情订阅 {quote.get('subscriptions', '--')} 条。"
        )
    elif tool_name in {"quant.signals.top", "quant.qlib.top"}:
        total = payload.get("total", 0)
        content = f"AI 信号池已返回，共 {total} 只。"
        predictions = payload.get("predictions") or []
        first = predictions[0] if predictions else {}
        first_code = str(first.get("code") or "").strip()
        if first_code:
            actions.append({"tool": "quant.stock.open", "label": f"打开 {first_code}", "arguments": {"code": first_code}})
    else:
        content = f"{tool_name} 已执行。"

    return content, actions


def _build_pending_confirmation(account: dict, tool_name: str, arguments: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    code = str(arguments.get("code") or "").strip()
    if tool_name == "quant.paper.order":
        direction = str(arguments.get("direction") or "buy").strip()
        volume = int(arguments.get("volume") or 100)
        direction_label = "买入" if direction == "buy" else "卖出"
        order_type = str(arguments.get("order_type") or "market").strip()
        order_type_label = "限价" if order_type == "limit" else "市价"
        price = arguments.get("price")
        price_text = f"，价格 {_fmt_money(price)}" if price not in (None, "") else ""
        code_text = f" {code}" if code else ""
        content = f"已识别到模拟盘{direction_label}{code_text} {volume} 股，{order_type_label}{price_text}。请在确认卡中核对后执行。"
        token = _make_confirmation_token(account, tool_name, arguments)
        return content.strip(), [
            {
                "tool": tool_name,
                "label": "确认模拟下单",
                "arguments": arguments,
                "confirm": True,
                "confirmation_token": token,
                "confirmation": {
                    "title": "确认模拟盘下单",
                    "risk": "仅写入模拟盘，不会连接实盘。确认后会创建待撮合订单，请核对方向、数量和价格。",
                    "expires_in": CONFIRMATION_TTL_SECONDS,
                    "items": [
                        {"label": "股票", "value": code or "--"},
                        {"label": "方向", "value": direction_label},
                        {"label": "数量", "value": f"{volume} 股"},
                        {"label": "类型", "value": order_type_label},
                        {"label": "价格", "value": _fmt_money(price) if price not in (None, "") else "市价"},
                    ],
                },
            }
        ]
    if tool_name == "quant.paper.close_position":
        volume = arguments.get("volume")
        volume_text = f"{int(volume)} 股" if volume else "全部可平仓位"
        content = f"已识别到模拟盘平仓 {code or '--'}，数量 {volume_text}。请在确认卡中核对后执行。"
        token = _make_confirmation_token(account, tool_name, arguments)
        return content.strip(), [
            {
                "tool": tool_name,
                "label": "确认模拟平仓",
                "arguments": arguments,
                "confirm": True,
                "confirmation_token": token,
                "confirmation": {
                    "title": "确认模拟盘平仓",
                    "risk": "仅写入模拟盘，不会连接实盘。确认后会创建卖出平仓订单。",
                    "expires_in": CONFIRMATION_TTL_SECONDS,
                    "items": [
                        {"label": "股票", "value": code or "--"},
                        {"label": "方向", "value": "卖出平仓"},
                        {"label": "数量", "value": volume_text},
                    ],
                },
            }
        ]
    return "需要确认后才能继续。", []


@router.get("/bridge/tools")
async def bridge_tools(request: Request):
    _require_bridge_api_key(request)
    account = _bridge_account(request)
    permissions = account.get("permissions") or {}
    return {
        "success": True,
        "workspace_id": account["workspace"]["openclaw_workspace_id"],
        "tools": [
            {
                **tool,
                "allowed": bool(permissions.get(tool["permission"])),
            }
            for tool in SYSTEM_TOOLS
        ],
    }


@router.post("/bridge/tools/invoke")
async def bridge_invoke_tool(req: BridgeToolInvokeRequest, request: Request):
    _require_bridge_api_key(request)
    account = _bridge_account(request, req.workspace_id or req.sessionKey)
    if req.tool not in TOOL_MAP:
        raise HTTPException(status_code=404, detail="工具不存在")
    arguments = req.arguments or req.args
    _require_tool_confirmation(account, req.tool, arguments, req.confirmed, req.confirmation_token)
    result = await invoke_system_tool(account, req.tool, arguments)
    content, actions = _format_action_response(req.tool, result, arguments)
    return {**result, "content": content, "actions": actions}


@router.get("/tools")
async def tools(account: dict = Depends(current_account)):
    native = await openclaw_gateway.list_native_tools(account["workspace"]["openclaw_workspace_id"])
    allowed = []
    permissions = account.get("permissions") or {}
    for tool in SYSTEM_TOOLS:
        item = dict(tool)
        item["allowed"] = bool(permissions.get(tool["permission"]))
        allowed.append(item)
    return {
        "success": True,
        "system_tools": allowed,
        "native_tools": native,
    }


@router.post("/tools/invoke")
async def invoke_tool(req: ToolInvokeRequest, account: dict = Depends(current_account)):
    if req.native:
        require_permission(account, "manage_skills")
        result = await openclaw_gateway.invoke_native_tool(
            workspace_id=account["workspace"]["openclaw_workspace_id"],
            tool_name=req.tool,
            arguments=req.arguments,
            session_key=account["workspace"]["openclaw_workspace_id"],
        )
        account_store.record_audit(
            "openclaw.native_tool.invoke",
            user_id=account["user"]["id"],
            workspace_id=account["workspace"]["id"],
            target_type="native_tool",
            target_id=req.tool,
            tool_name=req.tool,
            status="ok" if result.get("ok") else "error",
            reason=str(result.get("error") or ""),
            metadata={"arguments": req.arguments, "endpoint": result.get("endpoint")},
        )
        return {"success": bool(result.get("ok")), "native": True, "result": result}

    if req.tool not in TOOL_MAP:
        raise HTTPException(status_code=404, detail="工具不存在")
    _require_tool_confirmation(account, req.tool, req.arguments, req.confirmed, req.confirmation_token)
    result = await invoke_system_tool(account, req.tool, req.arguments)
    content, actions = _format_action_response(req.tool, result, req.arguments)
    return {**result, "content": content, "actions": actions}


@router.get("/memories")
async def memories(query: str = "", limit: int = 50, account: dict = Depends(current_account)):
    require_permission(account, "chat")
    return {
        "success": True,
        "items": account_store.list_memories(account["workspace"]["id"], query=query, limit=limit),
    }


@router.post("/memories")
async def create_memory(req: MemoryCreateRequest, account: dict = Depends(current_account)):
    require_permission(account, "chat")
    memory = account_store.create_memory(
        user_id=account["user"]["id"],
        workspace_id=account["workspace"]["id"],
        title=req.title or req.content[:40],
        content=req.content,
        code=req.code,
        tags=req.tags,
        source=req.source,
    )
    account_store.record_audit(
        "memory.create",
        user_id=account["user"]["id"],
        workspace_id=account["workspace"]["id"],
        target_type="research_memory",
        target_id=memory["id"],
        metadata={"code": req.code, "tags": req.tags},
    )
    return {"success": True, "memory": memory}


@router.delete("/memories/{memory_id}")
async def delete_memory(memory_id: str, account: dict = Depends(current_account)):
    require_permission(account, "chat")
    removed = account_store.delete_memory(account["workspace"]["id"], memory_id)
    account_store.record_audit(
        "memory.delete",
        user_id=account["user"]["id"],
        workspace_id=account["workspace"]["id"],
        target_type="research_memory",
        target_id=memory_id,
        status="ok" if removed else "not_found",
    )
    return {"success": True, "removed": removed}


@router.get("/reports/daily")
async def daily_reports(limit: int = 30, account: dict = Depends(current_account)):
    require_permission(account, "read_portfolio")
    return {
        "success": True,
        "items": account_store.list_daily_reports(account["workspace"]["id"], limit=limit),
    }


@router.post("/reports/daily/generate")
async def generate_daily_report(req: DailyReportGenerateRequest, account: dict = Depends(current_account)):
    require_permission(account, "read_portfolio")
    result = await invoke_system_tool(
        account,
        "quant.report.generate_daily",
        {"trade_date": req.trade_date} if req.trade_date else {},
    )
    return result


@router.get("/skills")
async def skills(account: dict = Depends(current_account)):
    require_permission(account, "manage_skills")
    workspace_id = account["workspace"]["id"]
    return {
        "success": True,
        "items": account_store.list_skills(workspace_id),
        "history": account_store.list_skill_install_requests(workspace_id, limit=30),
    }


@router.post("/skills")
async def record_skill(req: SkillRecordRequest, account: dict = Depends(current_account)):
    require_permission(account, "manage_skills")
    skill = account_store.upsert_skill(
        workspace_id=account["workspace"]["id"],
        name=req.name,
        version=req.version,
        status=req.status,
        source=req.source,
        permissions=req.permissions,
    )
    account_store.record_audit(
        "openclaw.skill.record",
        user_id=account["user"]["id"],
        workspace_id=account["workspace"]["id"],
        target_type="skill",
        target_id=req.name,
        metadata={"version": req.version, "status": req.status, "permissions": req.permissions},
    )
    return {"success": True, "skill": skill}
