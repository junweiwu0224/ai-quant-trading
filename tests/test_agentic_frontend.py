from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_template() -> str:
    return (ROOT / "dashboard/templates/index.html").read_text(encoding="utf-8")


def read_scripts() -> str:
    return (ROOT / "dashboard/templates/partials/scripts.html").read_text(encoding="utf-8")


def read_agentic_signals() -> str:
    return (ROOT / "dashboard/static/agentic-signals.js").read_text(encoding="utf-8")


def read_styles() -> str:
    return (ROOT / "dashboard/static/style.css").read_text(encoding="utf-8")


def test_agentic_signal_pool_container_and_script_are_registered():
    html = read_template()
    scripts = read_scripts()

    assert 'data-subtab="agentic"' in html
    assert 'id="research-panel-agentic"' in html
    assert 'id="agentic-signal-pool"' in html
    assert 'data-agentic-signal-list' in html
    assert 'agentic-signals.js' in scripts


def test_agentic_signal_frontend_fetches_signal_api():
    js = read_agentic_signals()

    assert "/api/agentic/signals" in js
    assert "renderSignalCard" in js
    assert "data-agentic-action=\"promote-paper\"" in js
    assert "window.AgenticSignals" in js


def test_agentic_signal_styles_exist():
    styles = read_styles()

    for selector in [
        ".agentic-signal-toolbar",
        ".agentic-signal-list",
        ".agentic-signal-card",
        ".agentic-signal-actions",
    ]:
        assert selector in styles


def test_agentic_strategy_lab_ui_is_registered():
    html = read_template()

    assert 'id="agentic-strategy-lab"' in html
    assert 'data-agentic-sample-status' in html
    assert 'data-agentic-action="run-sample-backtest"' in html
    assert 'data-agentic-backtest-result' in html


def test_agentic_strategy_lab_fetches_sample_and_runs_backtest():
    js = read_agentic_signals()

    assert "/api/agentic/backtest-sample" in js
    assert "/api/agentic/strategy/run-backtest" in js
    assert "buildDefaultStrategyDSL" in js
    assert "runSampleBacktest" in js


def test_agentic_strategy_lab_styles_exist():
    styles = read_styles()

    for selector in [
        ".agentic-strategy-lab",
        ".agentic-sample-grid",
        ".agentic-sample-pill",
        ".agentic-backtest-result",
    ]:
        assert selector in styles
