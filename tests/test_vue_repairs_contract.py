from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "dashboard/ui/src"


def read_ui(path: str) -> str:
    return (UI / path).read_text(encoding="utf-8")


def test_decision_reloads_and_discards_stale_market_results() -> None:
    source = read_ui("views/DecisionView.vue")

    assert "watch(() => app.market" in source
    assert "void load()" in source
    assert "const requestedMarket = app.market" in source
    assert "encodeURIComponent(requestedMarket)" in source
    assert "sequence !== loadSequence || requestedMarket !== app.market" in source


def test_research_gates_a_share_legacy_requests_on_the_route_capability() -> None:
    source = read_ui("views/ResearchView.vue")
    client = read_ui("api/client.ts")

    assert "api.decisionResearch(requestedMarket, requestedSymbol)" in source
    assert "const canLoadLegacyResearch = computed(() => market.value === 'CN' && capabilityMatchesRoute.value)" in source
    assert "if (!canLoadLegacyResearch.value)" in source
    assert "已停止调用 A 股数据接口" in source
    assert "clearResearchData()" in source
    assert "marketPath(" in client
    assert "api.stockQuote(requestedSymbol, requestedMarket)" in source
    assert "api.stockKline(requestedSymbol, period.value, count.value, requestedMarket)" in source
    assert "api.stockQuote(symbol.value)" not in source
    assert "api.stockKline(symbol.value, period.value, count.value)" not in source


def test_reports_expose_share_link_lifecycle_and_revoke_entry() -> None:
    reports = read_ui("views/ReportsView.vue")
    client = read_ui("api/client.ts")
    shared = read_ui("views/SharedReportView.vue")

    for marker in ("share_link_id", "share_created_at", "shareState", "已过期", "已撤销", "revokeShare(report)"):
        assert marker in reports
    assert "revokeShareLink(linkId: string)" in client
    assert "/api/decisions/share-links/${encodeURIComponent(linkId)}" in client
    assert "有效期至 {{ report.expires_at || '不可用' }}" in shared
    assert "链接已过期" in shared


def test_mobile_surface_keeps_touch_targets_and_narrow_layouts_usable() -> None:
    source = read_ui("styles.css")

    assert "@media (pointer: coarse)" in source
    assert ".button, .icon-button, .field-select, .market-select select, .workspace-tabs button { min-height: 44px; }" in source
    assert ".report-row { flex-direction: column; }" in source
    assert "env(safe-area-inset-bottom)" in source
    assert ".table-scroll { max-width: 100%; overflow-x: auto;" in source
