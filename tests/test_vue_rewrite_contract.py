"""Regression contracts for the dashboard rewrite's structural safety boundaries."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "dashboard" / "ui" / "src"


def read(path: str) -> str:
    return (UI / path).read_text(encoding="utf-8")


def test_primary_navigation_is_exactly_five_workspaces() -> None:
    registry = read("navigation/workflows.ts")
    mobile = read("components/MobileNav.vue")
    sidebar = read("components/Sidebar.vue")

    for workspace_id in ("decision", "research", "validation", "portfolio", "reports"):
        assert f"workspace: '{workspace_id}'" in registry
    assert "id: 'more'" in registry
    assert "primary: true, mobile: true" in registry
    assert "workspaceForPath" in sidebar
    assert "theme-btn" not in mobile
    assert "toggleTheme" not in mobile
    assert "repeat(5" in mobile or "repeat(5" in read("styles/shell.css")


def test_workspace_modules_are_visible_without_more_directory() -> None:
    registry = read("navigation/workflows.ts")
    nav = read("components/WorkspaceNav.vue")

    assert "WORKSPACE_DEFINITIONS" in registry
    for label in ("市场情报", "条件筛选", "Alpha 与因子", "模拟盘", "通知路由", "告警规则"):
        assert f"label: '{label}'" in registry
    assert "workspaceForPath" in nav
    assert "工作区模块" in nav



def test_decision_trace_uses_frozen_result_fields_and_keeps_delivery_separate() -> None:
    decision = read("views/DecisionView.vue")

    for field in ("current.snapshot", "current.version", "current.run", "current.report", "current.eligibility"):
        assert field in decision
    for node in ("输入快照", "数据质量", "策略版本", "验证", "资格", "冻结结论", "报告", "投递"):
        assert node in decision
    assert "前往通知审计确认" in decision


def test_authenticated_report_detail_route_keeps_evidence_and_delivery_audit() -> None:
    router = read("router.ts")
    reports = read("views/ReportsView.vue")
    detail = read("views/ReportDetailView.vue")

    assert "'/app/reports/:id'" in router
    assert "/app/reports/${encodeURIComponent(report.id)}" in reports
    assert "report-mobile-toggle" in reports and "report-mobile-open" in reports
    assert "loadedReport.share_link?.id" in detail
    assert "noticeState" in reports
    for marker in ("/api/decisions/reports/", "/deliveries", "冻结输入", "确定性决策", "AI 研究解释", "投递审计", "撤销分享"):
        assert marker in detail


def test_query_changes_do_not_remount_the_workspace_page() -> None:
    shell = read("components/MainContent.vue")

    assert "routedComponent.fullPath" not in shell
    assert "routedComponent.name || routedComponent.path" in shell


def test_validation_recovers_instrument_from_url_context() -> None:
    validation = read("views/ValidationView.vue")

    assert "hydrateInstrumentFromRoute" in validation
    assert "route.query.market" in validation
    assert "route.query.symbol" in validation
    assert "contextStore.setInstrument" in validation


def test_validation_requires_explicit_eligibility_and_collapses_advanced_inputs() -> None:
    validation = read("views/ValidationView.vue")

    assert "contextStore.context.eligibility?.eligible === true" in validation
    assert "eligibility?.eligible !== false" not in validation
    assert '<details class="validation-advanced">' in validation
    assert "noticeState" in validation


def test_service_worker_never_caches_authenticated_api_responses() -> None:
    worker = (ROOT / "dashboard" / "static" / "sw.js").read_text(encoding="utf-8")

    assert "networkOnly(event.request)" in worker
    assert "async function networkOnly" in worker
    assert "cache.put(request, response.clone())" not in worker.split("async function networkOnly", 1)[1].split("async function networkFirst", 1)[0]


def test_mobile_drawer_isolates_background_and_focuses_close_action() -> None:
    shell = read("components/AppShell.vue")
    sidebar = read("components/Sidebar.vue")

    assert ':inert="menuOpen || undefined"' in shell
    assert '#mobile-navigation [aria-label="关闭导航"]' in shell
    assert "visibility: hidden" in sidebar
    assert ".sidebar.open" in sidebar and "visibility: visible" in sidebar


def test_command_palette_traps_focus_and_restores_trigger() -> None:
    shell = read("components/MainContent.vue")

    assert 'ref="palettePanel"' in shell
    assert "event.key === 'Tab'" in shell
    assert "last.focus()" in shell and "first.focus()" in shell
    assert "paletteTrigger.value?.focus()" in shell


def test_workspace_bar_projects_existing_account_and_research_context() -> None:
    shell = read("components/MainContent.vue")

    assert "useResearchContextStore" in shell
    assert 'class="workspace-bar"' in shell
    assert "researchContext.context.freshness" in shell
    assert "researchContext.context.eligibility?.eligible === true" in shell
    assert "workspace-bar-secondary" in shell
    assert "researchContext.context.market !== nextMarket" in shell
    assert "researchContext.clear()" in shell


def test_notification_feedback_and_delivery_statuses_remain_distinct() -> None:
    notifications = read("views/NotificationsView.vue")
    reports = read("views/ReportsView.vue")
    async_state = read("components/base/AsyncState.vue")

    assert "noticeState" in notifications
    assert ":state=\"noticeState || 'error'\"" in notifications
    assert "Promise.allSettled" in notifications
    assert "blocked_external: '外部投递关闭'" in notifications
    assert "status === 'delivered'" in reports
    assert "status === 'sent'" not in reports
    assert ":role=\"state === 'error' ? 'alert' : 'status'\"" in async_state


def test_decision_command_timeout_never_returns_an_unfinished_result() -> None:
    client = read("api/client.ts")
    validation = read("views/ValidationView.vue")

    assert "throw new ApiError(`决策命令等待超时" in client
    assert "if (command.status !== 'completed')" in validation


def test_logout_clears_workspace_scoped_research_context() -> None:
    app_store = read("stores/app.ts")

    clear_account = app_store.split("function clearAccount()", 1)[1].split("  applyTheme()", 1)[0]
    assert "useResearchContextStore().clear()" in clear_account
