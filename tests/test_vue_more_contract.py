from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "dashboard/ui/src"


def test_business_capabilities_are_not_owned_by_more_view() -> None:
    registry = (UI / "navigation/workflows.ts").read_text(encoding="utf-8")
    workspace_nav = (UI / "components/WorkspaceNav.vue").read_text(encoding="utf-8")

    assert not (UI / "views/MoreView.vue").exists()
    assert "WORKSPACE_DEFINITIONS" in registry
    for label in (
        "市场情报", "条件筛选", "Alpha 与因子", "策略工作台",
        "持仓优化", "模拟盘", "条件单", "通知路由", "告警规则",
    ):
        assert f"label: '{label}'" in registry
    assert "workspace.tabs" in workspace_nav


def test_more_routes_are_compatibility_redirects_only() -> None:
    router = (UI / "router.ts").read_text(encoding="utf-8")

    assert "component: () => import('./views/MoreView.vue')" not in router
    assert "{ path: '/app/more', redirect:" in router
    assert "{ path: '/app/more/:tool', redirect:" in router
    assert "legacy-more" in router
