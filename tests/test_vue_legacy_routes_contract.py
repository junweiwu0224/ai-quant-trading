import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "dashboard/ui/src/router.ts"
APP = ROOT / "dashboard/app.py"


EXPECTED_LEGACY_ROUTES = {
    "overview": "/app/decision",
    "intelligence": "/app/intelligence",
    "positions": "/app/portfolio-risk",
    "ai-advice": "/app/ai",
    "backtest": "/app/validation",
    "strategy-research": "/app/research/alpha",
    "paper": "/app/paper",
    "alerts": "/app/alerts",
    "settings": "/app/settings",
    "research": "/app/research",
    "trade": "/app/portfolio-risk",
    "strategy-admin": "/app/strategy",
    "screener": "/app/research/screener",
    "agent": "/app/ai",
    "reports": "/app/reports",
    "stock-detail": "/app/research",
}


def route_entry(source: str, key: str) -> str:
    key_literal = key if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", key) else repr(key)
    match = re.search(rf"^\s*{re.escape(key_literal)}:\s*'([^']+)'", source, re.MULTILINE)
    assert match, f"legacy hash route {key!r} is not declared"
    return match.group(1)


def test_legacy_hash_entries_redirect_to_explicit_vue_routes():
    source = ROUTER.read_text(encoding="utf-8")

    for legacy_hash, vue_route in EXPECTED_LEGACY_ROUTES.items():
        assert route_entry(source, legacy_hash) == vue_route
        assert vue_route.startswith("/app/")

    assert "openclaw" not in source.lower()


def test_stock_detail_legacy_hash_keeps_code_market_and_source_context():
    source = ROUTER.read_text(encoding="utf-8")

    assert "const hash = to.hash.replace(/^#/, '')" in source
    assert "const { route: legacyRoute, query: legacyQuery } = parseLegacyHash(hash)" in source
    assert "if (legacyRoute === 'stock-detail') return stockDetailRedirect(to, legacyQuery)" in source
    assert "new URLSearchParams(queryPart)" in source
    assert "legacyQuery.get('code')" in source
    assert "legacyQuery.get('market')" in source
    assert "legacyQuery.get('source')" in source
    assert "query: { code, market, source }" in source
    assert "`/app/research/${market}/${encodeURIComponent(code)}`" in source
    assert "path: '/app/stock-detail', redirect: (to: RouteLocationGeneric) => stockDetailRedirect(to, new URLSearchParams())" in source


def test_root_query_context_is_forwarded_to_the_vue_shell_before_legacy_html():
    source = APP.read_text(encoding="utf-8")

    assert "request.query_params.get('code') or request.query_params.get('symbol')" in source
    assert "request.url.query" in source
    assert 'RedirectResponse(f"/app/decision?{request.url.query}")' in source


def test_more_aliases_land_on_functional_vue_workflows():
    source = ROUTER.read_text(encoding="utf-8")

    for alias in (
        "/app/more/market-radar",
        "/app/more/watchlists-alerts",
        "/app/more/stock-detail",
        "/app/more/strategies-backtest",
        "/app/more/daily-briefs",
    ):
        assert f"path: '{alias}'" in source
    assert "stockDetailRedirect(to, new URLSearchParams())" in source
