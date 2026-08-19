from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "dashboard/ui/src"


def read_ui(path: str) -> str:
    return (UI / path).read_text(encoding="utf-8")


def test_paper_api_uses_real_envelopes_and_no_client_mock() -> None:
    api = read_ui("api/client.ts")
    view = read_ui("views/PaperRiskView.vue")
    assert "/api/paper/orders" in api
    assert "/api/paper/positions" in api
    assert "/api/paper/trades-v2" in api
    assert "mockAccount" not in api
    assert "alert(" not in view
    assert "api.createPaperOrder" in view
    assert "模拟盘与风控执行" in view


def test_portfolio_optimization_uses_real_api_without_demo_holdings() -> None:
    api = read_ui("api/portfolio.ts")
    view = read_ui("views/more/PortfolioOptView.vue")

    assert "/api/portfolio-opt/methods" in api
    assert "/api/portfolio-opt/optimize" in api
    assert "mockAnalysis" not in api
    assert "贵州茅台" not in view
    assert "可视化功能开发中" not in view
    assert "不会自动调仓或创建订单" in view


def test_ai_runtime_legacy_route_opens_canonical_ai_settings_tab() -> None:
    source = read_ui("views/AgentOpsView.vue")
    assert "queryTab" in source
    assert "activeTab.value = String(queryTab) as WorkbenchTab" in source


def test_unrouted_mock_workbenches_are_removed() -> None:
    removed = (
        "views/more/AIRuntimeView.vue",
        "views/more/RiskMonitorView.vue",
        "views/more/StrategyWorkbenchView.vue",
        "views/more/AlphaFactorsView.vue",
        "views/more/ConditionalOrdersView.vue",
        "views/more/PaperTradingView.vue",
        "views/more/AgentOpsView.vue",
        "components/ai/TokenUsagePanel.vue",
        "components/research/BacktestPreview.vue",
        "composables/useTokenUsage.ts",
        "stores/decision.ts",
        "utils/tokenUsageDemo.ts",
        "api/agent.ts",
        "api/aiRuntime.ts",
        "api/risk.ts",
        "api/strategy.ts",
        "api/alpha.ts",
        "api/orders.ts",
    )
    for path in removed:
        assert not (UI / path).exists(), path


def test_decision_links_set_research_context_on_click() -> None:
    source = read_ui("views/DecisionView.vue")
    assert "useResearchContextStore" in source
    assert "function selectResearch" in source
    assert "researchContext.setInstrument" in source
    assert "@click=\"selectResearch" in source
    assert "function researchPath" in source


def test_navigation_uses_one_registry_and_keeps_more_as_compatibility_only() -> None:
    registry = read_ui("navigation/workflows.ts")
    sidebar = read_ui("components/Sidebar.vue")
    mobile = read_ui("components/MobileNav.vue")
    main = read_ui("components/MainContent.vue")
    workspace_nav = read_ui("components/WorkspaceNav.vue")
    router = read_ui("router.ts")

    for marker in ("PRIMARY_WORKFLOWS", "MOBILE_WORKFLOWS", "COMMAND_WORKFLOWS", "WORKSPACE_DEFINITIONS"):
        assert marker in registry
    assert "PRIMARY_WORKFLOWS" in sidebar
    assert "MOBILE_WORKFLOWS" in mobile
    assert "COMMAND_WORKFLOWS" in main
    assert "WorkspaceNav" in main
    assert 'class="icon-button ai-global-link"' in main
    assert "workspaceForPath" in workspace_nav
    assert ".topbar-actions .ai-global-link" in read_ui("styles.css")
    for route in (
        "/app/workflows",
        "/app/research/screener",
        "/app/research/alpha",
        "/app/research/formula-basket",
        "/app/strategy",
        "/app/portfolio-risk",
        "/app/portfolio",
        "/app/risk",
        "/app/paper",
        "/app/conditional-orders",
        "/app/ai",
        "/app/ai/runtime",
        "/app/alerts",
        "/app/broker",
    ):
        assert route in router
    assert "component: () => import('./views/MoreView.vue')" not in router
    assert "redirect: '/app/workflows'" in router
    assert "legacy-risk" in router
    assert "legacy-ai-runtime" in router
