from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_stock_detail_clears_stale_header_when_detail_api_fails():
    core = read("dashboard/static/stock-detail-core.js")

    assert "this._renderDetailPending(code, { stock: optionStock, name: optionName });" in core
    assert "_renderDetailUnavailable(code, error)" in core
    assert "本地基础资料暂未覆盖该股票" in core
    assert "this._renderDetailHeader({" in core
    assert "code: safeCode" in core


def test_market_radar_exposes_stable_table_and_stock_name_context():
    radar = read("dashboard/static/overview-radar.js")
    bootstrap = read("dashboard/static/app-bootstrap.js")

    assert 'id="overview-radar-table"' in radar
    assert 'data-testid="overview-radar-table"' in radar
    assert 'data-name="${App.escapeHTML(s.name || \'\')}"' in radar
    assert "const name = typeof link.dataset.name === 'string'" in bootstrap
    assert "name," in bootstrap


def test_data_scope_notes_are_visible_for_research_workbenches():
    template = read("dashboard/templates/index.html")
    datahub = read("dashboard/static/research-datahub.js")
    valuation = read("dashboard/static/research-valuation.js")

    assert 'id="overview-radar-coverage"' in template
    assert 'id="datahub-scope-note"' in template
    assert 'id="valuation-scope-note"' in template
    assert "当前账号自选，不代表全市场" in datahub
    assert "AI 信号候选池，未验证信号已降权" in datahub
    assert "机构预测 + AI信号覆盖池，不等同全量日线" in valuation
    assert "估值服务全市场扫描，非本地日线全量" in valuation


def test_open_paper_buy_defaults_to_trade_subtab_and_focuses_order_form():
    adapter = read("dashboard/static/core/business-adapter.js")

    assert "const PAPER_SUB_TAB_CANDIDATES = Object.freeze(['trade', 'console']);" in adapter
    assert "payload.activeTab = payload.activeTab || 'trade';" in adapter
    assert "document.getElementById('pt-order-form')?.scrollIntoView" in adapter


def test_changed_frontend_assets_are_cache_busted():
    app = read("dashboard/static/app.js")
    scripts = read("dashboard/templates/partials/scripts.html")
    template = read("dashboard/templates/index.html")
    search = read("dashboard/static/search.js")
    watchlist = read("dashboard/static/watchlist.js")
    workbench = read("dashboard/static/app-workbench.js")
    compare = read("dashboard/static/compare.js")
    paper_trading = read("dashboard/static/paper-trading.js")
    datahub = read("dashboard/static/research-datahub.js")
    valuation = read("dashboard/static/research-valuation.js")
    alpha = read("dashboard/static/alpha.js")
    alpha_tools = read("dashboard/static/alpha-tools.js")

    assert "/static/style.css?v=46" in template
    assert "/static/search.js?v=13" in scripts
    assert "/static/watchlist.js?v=9" in scripts
    assert "/static/app.js?v=59" in scripts
    assert "/static/app-stock-ops.js?v=4" in scripts
    assert "/static/core/business-adapter.js?v=4" in scripts
    assert "/static/app-ui-shell.js?v=19" in scripts
    assert "/static/app-workbench.js?v=2" in scripts
    assert "/static/openclaw-workbench.js?v=20" in scripts
    assert "/static/app-bootstrap.js?v=21" in scripts
    assert "/static/overview-radar.js?v=5" in scripts
    assert "/static/overview-radar.js?v=5" in app
    assert "/static/paper-trading.js?v=6" in app
    assert "/static/compare.js?v=5" in app
    assert "/static/alpha.js?v=5" in app
    assert "/static/alpha-tools.js?v=5" in app
    assert "/static/research-datahub.js?v=10" in app
    assert "/static/research-valuation.js?v=13" in app
    assert "/static/stock-detail-core.js?v=6" in app
    assert "/static/openclaw-workbench.js?v=20" in app

    assert "minQueryLength" in search
    assert "minQueryLength: 1" in watchlist
    assert "/api/stock/search?q=&limit=6000" not in workbench
    assert "/api/stock/search?q=&limit=6000" not in watchlist
    assert "/api/stock/search?limit=200" not in compare
    assert "App._allStocks" not in paper_trading
    assert "if (!q) return [];" in watchlist
    assert "emptyScope: 'watchlist'" in workbench
    assert "emptyScope: 'watchlist'" in datahub
    assert "emptyScope: 'watchlist'" in valuation
    assert "_fmtPeg(item.peg_next_year)" in datahub
    assert "_fmtQlib(item)" in datahub
    assert "_metaLine" not in datahub
    assert "datahub-stock-meta" in datahub
    assert "datahub-missing-badge" in datahub
    assert "inlineFilter" in search
    assert "sb-no-inline-filter" in search
    assert "initFormulaBasketPickers" in alpha
    assert "_alphaActionHandlersBound" in alpha
    assert "_alphaInitDone" not in alpha
    assert "new SearchBox('formula-code', 'formula-code-dropdown'" in alpha_tools
    assert "new MultiSearchBox('basket-code-input', 'basket-code-dropdown', 'basket-code-tags'" in alpha_tools
    assert "emptyScope: 'watchlist'" in alpha_tools
    assert "自选股为空，输入代码或名称搜索全市场" in alpha_tools
    assert "basket-use-watchlist" in template
    assert "basket-clear-candidates" in template
    assert "全市场选股" in template
    assert "basket-advanced-json" in template
