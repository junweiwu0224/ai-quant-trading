import asyncio

import pytest

from dashboard import openclaw_tools
from dashboard.routers import openclaw as openclaw_router


APPROVED_BRIDGE_TOOLS = {
    "quant.watchlist.add",
    "quant.watchlist.remove",
    "quant.watchlist.list",
    "quant.stock.open",
    "quant.paper.order",
    "quant.paper.close_position",
    "quant.paper.summary",
    "quant.valuation.peg",
    "quant.data.snapshot",
    "quant.signals.top",
    "quant.qlib.top",
    "quant.report.generate_daily",
    "quant.report.open",
    "quant.skill.record",
}


def _bridge_headers():
    return {"X-API-Key": "bridge-secret", "X-OpenClaw-Workspace": "ocw_workspace_1"}


def test_system_tools_list_is_limited_to_approved_names():
    assert {tool["name"] for tool in openclaw_tools.SYSTEM_TOOLS} == APPROVED_BRIDGE_TOOLS


def test_qlib_bridge_tool_is_labeled_as_signal_compatibility():
    tool = next(item for item in openclaw_tools.SYSTEM_TOOLS if item["name"] == "quant.qlib.top")

    assert tool["label"] == "AI 信号 Top"
    assert "Qlib" not in tool["label"]
    assert "兼容旧调用" in tool["description"]
    assert "Signal Engine" in tool["description"]


def test_bridge_tools_lists_approved_tools_with_allowed_flags(client, monkeypatch):
    monkeypatch.setenv("QUANT_SYSTEM_API_KEY", "bridge-secret")
    monkeypatch.setattr(
        openclaw_router.account_store,
        "get_user_bundle_by_openclaw_workspace_id",
        lambda workspace_id: {
            "user": {"id": "user-1"},
            "workspace": {"id": "workspace-1", "openclaw_workspace_id": workspace_id},
            "permissions": {
                "write_watchlist": True,
                "read_market": False,
                "write_paper_trade": True,
                "read_portfolio": True,
                "manage_skills": True,
                "chat": False,
            },
        },
    )

    resp = client.get("/api/openclaw/bridge/tools", headers=_bridge_headers())

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["workspace_id"] == "ocw_workspace_1"
    assert {tool["name"] for tool in body["tools"]} == APPROVED_BRIDGE_TOOLS
    assert all("allowed" in tool for tool in body["tools"])
    allowed_map = {tool["name"]: tool["allowed"] for tool in body["tools"]}
    assert allowed_map["quant.watchlist.add"] is True
    assert allowed_map["quant.stock.open"] is False
    assert allowed_map["quant.skill.record"] is True


def test_bridge_tools_rejects_invalid_api_key(client, monkeypatch):
    monkeypatch.setenv("QUANT_SYSTEM_API_KEY", "bridge-secret")

    resp = client.get(
        "/api/openclaw/bridge/tools",
        headers={"X-API-Key": "wrong", "X-OpenClaw-Workspace": "ocw_workspace_1"},
    )

    assert resp.status_code == 401


def test_bridge_tools_rejects_missing_workspace(client, monkeypatch):
    monkeypatch.setenv("QUANT_SYSTEM_API_KEY", "bridge-secret")

    resp = client.get("/api/openclaw/bridge/tools", headers={"X-API-Key": "bridge-secret"})

    assert resp.status_code == 400


def test_bridge_tools_rejects_unknown_workspace(client, monkeypatch):
    monkeypatch.setenv("QUANT_SYSTEM_API_KEY", "bridge-secret")
    monkeypatch.setattr(
        openclaw_router.account_store,
        "get_user_bundle_by_openclaw_workspace_id",
        lambda workspace_id: None,
    )

    resp = client.get("/api/openclaw/bridge/tools", headers=_bridge_headers())

    assert resp.status_code == 404


def test_bridge_invoke_runs_approved_tool_for_workspace(client, monkeypatch):
    monkeypatch.setenv("QUANT_SYSTEM_API_KEY", "bridge-secret")
    monkeypatch.setattr(
        openclaw_router.account_store,
        "get_user_bundle_by_openclaw_workspace_id",
        lambda workspace_id: {
            "user": {"id": "user-1"},
            "workspace": {"id": "workspace-1", "openclaw_workspace_id": workspace_id},
            "permissions": {"write_watchlist": True},
        },
    )
    monkeypatch.setattr(openclaw_tools.storage, "add_to_watchlist", lambda code, workspace_id: True)
    monkeypatch.setattr(
        openclaw_tools.account_store,
        "record_audit",
        lambda *args, **kwargs: {"id": "audit-1"},
    )
    monkeypatch.setattr(
        openclaw_tools.account_store,
        "create_memory",
        lambda **kwargs: {"id": "memory-1", **kwargs},
    )

    resp = client.post(
        "/api/openclaw/bridge/tools/invoke",
        headers=_bridge_headers(),
        json={"tool": "quant.watchlist.add", "arguments": {"code": "600519"}},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["tool"] == "quant.watchlist.add"
    assert body["result"]["added"] is True


def test_bridge_invoke_rejects_unknown_tool(client, monkeypatch):
    monkeypatch.setenv("QUANT_SYSTEM_API_KEY", "bridge-secret")
    monkeypatch.setattr(
        openclaw_router.account_store,
        "get_user_bundle_by_openclaw_workspace_id",
        lambda workspace_id: {
            "user": {"id": "user-1"},
            "workspace": {"id": "workspace-1", "openclaw_workspace_id": workspace_id},
            "permissions": {"write_watchlist": True},
        },
    )

    resp = client.post(
        "/api/openclaw/bridge/tools/invoke",
        headers=_bridge_headers(),
        json={"tool": "quant.nope", "arguments": {}},
    )

    assert resp.status_code == 404


@pytest.mark.parametrize(
    "tool,arguments",
    [
        ("quant.paper.order", {"code": "600519", "direction": "buy", "volume": 100, "order_type": "market"}),
        ("quant.paper.close_position", {"code": "600519"}),
        ("quant.skill.record", {"name": "openclaw"}),
    ],
)
def test_bridge_invoke_requires_confirmation(client, monkeypatch, tool, arguments):
    monkeypatch.setenv("QUANT_SYSTEM_API_KEY", "bridge-secret")
    monkeypatch.setattr(
        openclaw_router.account_store,
        "get_user_bundle_by_openclaw_workspace_id",
        lambda workspace_id: {
            "user": {"id": "user-1"},
            "workspace": {"id": "workspace-1", "openclaw_workspace_id": workspace_id},
            "permissions": {
                "write_paper_trade": True,
                "manage_skills": True,
            },
        },
    )

    resp = client.post(
        "/api/openclaw/bridge/tools/invoke",
        headers=_bridge_headers(),
        json={"tool": tool, "arguments": arguments},
    )

    assert resp.status_code == 409


def test_bridge_invoke_honors_workspace_confirmation_settings(client, monkeypatch):
    monkeypatch.setenv("QUANT_SYSTEM_API_KEY", "bridge-secret")
    monkeypatch.setattr(
        openclaw_router.account_store,
        "get_user_bundle_by_openclaw_workspace_id",
        lambda workspace_id: {
            "user": {"id": "user-1"},
            "workspace": {
                "id": "workspace-1",
                "openclaw_workspace_id": workspace_id,
                "settings": {
                    "tool_confirmations": {
                        "write_paper_trade": False,
                        "manage_skills": False,
                    }
                },
            },
            "permissions": {
                "write_paper_trade": True,
                "manage_skills": True,
            },
        },
    )
    invoked = []
    monkeypatch.setattr(
        openclaw_tools.account_store,
        "record_audit",
        lambda *args, **kwargs: {"id": "audit-1"},
    )
    monkeypatch.setattr(
        openclaw_tools.order_manager,
        "create_order",
        lambda **kwargs: invoked.append(kwargs) or type("Order", (), {"to_dict": lambda self: {"code": kwargs["code"]}})(),
    )

    resp = client.post(
        "/api/openclaw/bridge/tools/invoke",
        headers=_bridge_headers(),
        json={"tool": "quant.paper.order", "arguments": {"code": "600519", "direction": "buy", "volume": 100, "order_type": "market"}},
    )

    assert resp.status_code == 200
    assert invoked


def test_chat_honors_workspace_confirmation_settings(monkeypatch):
    async def fake_invoke_system_tool(account, tool_name, arguments):
        return {
            "success": True,
            "tool": tool_name,
            "result": {
                "order": {
                    "code": arguments["code"],
                    "direction": arguments["direction"],
                    "volume": arguments["volume"],
                    "order_type": arguments["order_type"],
                }
            },
        }

    monkeypatch.setattr(openclaw_router, "invoke_system_tool", fake_invoke_system_tool)

    account = {
        "user": {"id": "user-1"},
        "workspace": {
            "id": "workspace-1",
            "openclaw_workspace_id": "ocw_workspace_1",
            "settings": {
                "tool_confirmations": {
                    "write_paper_trade": False,
                    "manage_skills": True,
                }
            },
        },
        "permissions": {"chat": True, "write_paper_trade": True},
    }

    response = asyncio.run(
        openclaw_router.chat(
            openclaw_router.ChatRequest(message="模拟买入 600519 100 股"),
            account=account,
        )
    )

    assert response["mode"] == "system-action"
