from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_template() -> str:
    return (ROOT / "dashboard/templates/index.html").read_text(encoding="utf-8")


def read_styles() -> str:
    return (ROOT / "dashboard/static/style.css").read_text(encoding="utf-8")


def read_app_shell() -> str:
    return (ROOT / "dashboard/static/core/app-shell.js").read_text(encoding="utf-8")


def read_scripts_partial() -> str:
    return (ROOT / "dashboard/templates/partials/scripts.html").read_text(encoding="utf-8")


def test_shared_research_toolbar_groups_stock_dates_model_and_actions():
    template = read_template()

    assert 'class="page-header research-toolbar research-param-toolbar"' in template
    assert 'class="research-param-group research-param-stock"' in template
    assert 'class="research-param-group research-param-dates"' in template
    assert 'class="research-param-group research-param-model"' in template
    assert 'class="research-param-actions"' in template
    assert 'class="research-date-range"' in template
    assert 'class="research-date-separator"' in template

    for required in [
        'id="alpha-code-box"',
        'id="alpha-code"',
        'id="alpha-code-dropdown"',
        'id="alpha-start"',
        'id="alpha-end"',
        'id="alpha-model"',
        'data-app-role="alpha-analyze"',
        'data-app-role="alpha-optimize"',
    ]:
        assert required in template


def test_formula_basket_and_backtest_tabs_use_same_compact_research_form_surface():
    template = read_template()

    assert template.count("form-row research-tool-form research-form-grid") >= 3
    assert template.count('class="form-group min-w-sm research-tool-primary"') >= 2
    assert 'id="backtest-form" class="form-row research-tool-form research-form-grid research-backtest-form"' in template
    assert 'class="form-group min-w-md research-tool-primary"' in template
    assert 'class="compact-action-row research-tool-actions research-param-actions"' in template
    assert 'id="basket-backtest-draft"' in template
    assert 'data-execution-policy="manual_only"' in template
    assert 'data-execution-status="not_executed"' in template
    assert 'id="basket-backtest-draft-conditions"' in template
    assert 'id="basket-draft-audit-study"' in template
    assert 'data-alpha-action="basket-update-backtest-draft"' in template
    assert '计划回测' in template


def test_research_toolbar_styles_define_dense_terminal_controls():
    styles = read_styles()

    for selector in [
        ".research-param-toolbar",
        ".research-param-group",
        ".research-param-label",
        ".research-param-stock",
        ".research-date-range",
        ".research-date-separator",
        ".research-param-actions",
        ".research-form-grid",
        ".research-backtest-form",
        ".research-backtest-form .research-tool-primary",
        ".research-tool-primary",
        ".research-tool-submit",
        "@media (max-width: 760px)",
    ]:
        assert selector in styles
    assert "grid-template-columns: repeat(6, minmax(0, 1fr));" in styles
    assert "grid-column: span 2;" in styles


def test_research_subtab_visibility_hides_whole_model_group_and_action_group():
    app_shell = read_app_shell()

    assert "const modelGroup = modelSel?.closest('.research-param-model')" in app_shell
    assert "const actionGroup = analyzeBtn?.closest('.research-param-actions')" in app_shell
    assert "if (modelGroup) modelGroup.style.display = (subtab === 'model') ? '' : 'none';" in app_shell
    assert "if (actionGroup) actionGroup.style.display = (subtab === 'model') ? '' : 'none';" in app_shell


def test_research_toolbar_asset_versions_are_bumped_for_browser_cache():
    template = read_template()
    scripts = read_scripts_partial()

    assert "/static/style.css?v=84" in template
    assert "/static/core/app-shell.js?v=38" in scripts
    assert "/static/core/command-palette.js?v=2" in scripts
    assert "/static/app-ui-shell.js?v=46" in scripts


def test_mobile_research_subtabs_avoid_fixed_user_shell_bar():
    styles = read_styles()

    assert "@media (max-width: 640px)" in styles
    assert ".research-sub-tabs {" in styles
    assert "top: 56px;" in styles
    assert "z-index: 190;" in styles
    assert ".basket-backtest-draft {" in styles
    assert ".basket-draft-audit-study {" in styles
    assert ".basket-draft-study-metrics" in styles
    assert ".basket-draft-study-table table" in styles
    assert "scroll-margin-bottom: var(--mobile-bottom-nav-offset);" in styles
    assert "--mobile-bottom-nav-offset: calc(72px + env(safe-area-inset-bottom, 0px));" in styles
    assert "padding-bottom: var(--mobile-bottom-nav-offset);" in styles
    assert "bottom: calc(var(--mobile-bottom-nav-offset) + 12px);" in styles
