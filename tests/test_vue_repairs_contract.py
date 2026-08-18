from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "dashboard/ui/src"


def read_ui(path: str) -> str:
    return (UI / path).read_text(encoding="utf-8")


def test_auth_history_route_uses_vue_shell_and_request_preserves_json_headers() -> None:
    app_source = (ROOT / "dashboard/app.py").read_text(encoding="utf-8")
    client = read_ui("api/client.ts")

    assert '@app.get("/auth")' in app_source
    assert "return _vue_shell_response()" in app_source
    assert "const headers = new Headers({" in client
    assert "new Headers(init?.headers).forEach" in client
    assert "...init," in client
    assert "credentials: 'include'" in client
    assert "headers," in client


    source = read_ui("views/DecisionView.vue")

    assert "watch(() => app.market" in source
    assert "void load()" in source
    assert "const requestedMarket = app.market" in source
    assert "encodeURIComponent(requestedMarket)" in source
    assert "sequence !== loadSequence || requestedMarket !== app.market" in source


def test_research_loads_real_data_and_discards_stale_requests() -> None:
    source = read_ui("views/ResearchView.vue")
    client = read_ui("api/research.ts")

    assert "getKLineData(market.value as any, symbol.value, 'daily', 120, controller.signal)" in source
    assert "getTechnicalIndicators(market.value as any, symbol.value, controller.signal)" in source
    assert "getEvidence(market.value as any, symbol.value, controller.signal)" in source
    assert "controller?.abort()" in source
    assert "activeKey = key" in source
    assert "if (!isCurrent(key)) return" in source
    assert "response.klines" in client
    assert "fixed" not in source
    assert "65" not in read_ui("components/research/DecisionCard.vue")
    assert "数据加载中..." not in read_ui("components/research/EvidenceChain.vue")


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
