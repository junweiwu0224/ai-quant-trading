import asyncio

from dashboard import openclaw_tools
from dashboard.routers import openclaw as openclaw_router


def test_watchlist_add_creates_research_memory(monkeypatch):
    account = {
        "user": {"id": "user-1"},
        "workspace": {"id": "workspace-1", "openclaw_workspace_id": "ocw_workspace_1"},
        "permissions": {"write_watchlist": True},
    }
    created = []

    monkeypatch.setattr(
        openclaw_tools.storage,
        "add_to_watchlist",
        lambda code, workspace_id: True,
    )
    monkeypatch.setattr(
        openclaw_tools.account_store,
        "record_audit",
        lambda *args, **kwargs: {"id": "audit-1"},
    )
    monkeypatch.setattr(
        openclaw_tools.account_store,
        "create_memory",
        lambda **kwargs: created.append(kwargs) or {"id": "memory-1", **kwargs},
    )

    asyncio.run(
        openclaw_tools.invoke_system_tool(
            account,
            "quant.watchlist.add",
            {"code": "600519", "reason": "关注高股息和稳健现金流"},
        )
    )

    assert len(created) == 1
    memory = created[0]
    assert memory["workspace_id"] == "workspace-1"
    assert memory["user_id"] == "user-1"
    assert memory["code"] == "600519"
    assert "加入自选" in memory["title"]
    assert "关注高股息和稳健现金流" in memory["content"]
    assert "watchlist" in memory["tags"]
    assert memory["source"] == "openclaw:auto"


def test_watchlist_add_records_audit(monkeypatch):
    account = {
        "user": {"id": "user-1"},
        "workspace": {"id": "workspace-1", "openclaw_workspace_id": "ocw_workspace_1"},
        "permissions": {"write_watchlist": True},
    }
    audits = []

    monkeypatch.setattr(
        openclaw_tools.storage,
        "add_to_watchlist",
        lambda code, workspace_id: True,
    )
    monkeypatch.setattr(
        openclaw_tools.account_store,
        "record_audit",
        lambda *args, **kwargs: audits.append((args, kwargs)) or {"id": "audit-1"},
    )
    monkeypatch.setattr(
        openclaw_tools.account_store,
        "create_memory",
        lambda **kwargs: {"id": "memory-1", **kwargs},
    )

    asyncio.run(
        openclaw_tools.invoke_system_tool(
            account,
            "quant.watchlist.add",
            {"code": "600519", "reason": "关注高股息和稳健现金流"},
        )
    )

    assert audits
    event, kwargs = audits[0]
    assert event[0] == "openclaw.system_tool.invoke"
    assert kwargs["tool_name"] == "quant.watchlist.add"
    assert kwargs["status"] == "ok"


def test_auto_record_research_memory_tracks_report_actions(monkeypatch):
    account = {
        "user": {"id": "user-1"},
        "workspace": {"id": "workspace-1", "openclaw_workspace_id": "ocw_workspace_1"},
        "permissions": {},
    }
    created = []

    monkeypatch.setattr(
        openclaw_tools.account_store,
        "create_memory",
        lambda **kwargs: created.append(kwargs) or {"id": "memory-1", **kwargs},
    )

    openclaw_tools._auto_record_research_memory(
        account,
        "quant.report.open",
        {"trade_date": "2026-05-23"},
        {"report": {"trade_date": "2026-05-23", "title": "2026-05-23 模拟盘收益日报"}},
    )

    assert len(created) == 1
    memory = created[0]
    assert memory["source"] == "openclaw:auto"
    assert "report" in memory["tags"] or "daily_report" in memory["tags"]
    assert "2026-05-23" in memory["content"]


def test_watchlist_chat_action_preserves_user_reason(monkeypatch):
    account = {
        "user": {"id": "user-1"},
        "workspace": {"id": "workspace-1", "openclaw_workspace_id": "ocw_workspace_1"},
        "permissions": {"chat": True, "write_watchlist": True},
    }
    captured = []

    async def fake_invoke_system_tool(account, tool_name, arguments):
        captured.append((tool_name, arguments))
        return {"success": True, "tool": tool_name, "result": {"code": arguments["code"]}}

    monkeypatch.setattr(openclaw_router, "invoke_system_tool", fake_invoke_system_tool)

    response = asyncio.run(
        openclaw_router.chat(
            openclaw_router.ChatRequest(message="把 000001 加入自选，原因是测试自动记忆链路"),
            account=account,
        )
    )

    assert response["mode"] == "system-action"
    assert captured[0][0] == "quant.watchlist.add"
    assert captured[0][1]["code"] == "000001"
    assert "测试自动记忆链路" in captured[0][1]["reason"]
