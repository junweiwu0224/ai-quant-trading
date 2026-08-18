from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "dashboard/ui/src"


def read_ui(path: str) -> str:
    return (UI / path).read_text(encoding="utf-8")


def test_paper_api_uses_real_envelopes_and_no_client_mock() -> None:
    api = read_ui("api/paper.ts")
    view = read_ui("views/more/PaperTradingView.vue")
    assert "/api/paper/orders" in api
    assert "/api/paper/positions" in api
    assert "/api/paper/trades-v2" in api
    assert "Math.random" not in api
    assert "mockAccount" not in api
    assert "alert(" not in view
    assert "createPaperTrade" in view
    assert "Paper Engine" in view


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
    router = read_ui("router.ts")

    for marker in ("PRIMARY_WORKFLOWS", "MOBILE_WORKFLOWS", "COMMAND_WORKFLOWS"):
        assert marker in registry
    assert "PRIMARY_WORKFLOWS" in sidebar
    assert "MOBILE_WORKFLOWS" in mobile
    assert "COMMAND_WORKFLOWS" in main
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


def test_market_store_does_not_invent_numeric_values_or_mix_market_caches() -> None:
    source = read_ui("stores/market.ts")

    assert "type NullableNumber = number | null" in source
    assert "function normalizedTimestamp" in source
    assert "function cacheKey(market: MarketCode, symbol: string)" in source
    assert "cacheKey(market, symbol)" in source
    assert "timestamp * 1000" not in source
    assert "open: 0" not in source
    assert "high: 0" not in source
    assert "low: 0" not in source
    assert "preClose: 0" not in source
