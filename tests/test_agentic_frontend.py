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
    assert 'agentic-workflow-steps' in html
    assert 'agentic-primary-action' in html
    assert 'data-agentic-next-action' in html
    assert 'data-agentic-sample-status' in html
    assert 'data-agentic-action="run-candidate-backtests"' in html
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


def test_agentic_strategy_lab_runs_candidate_batch_backtests():
    html = read_template()
    js = read_agentic_signals()

    assert 'data-agentic-action="run-candidate-backtests"' in html
    assert 'data-agentic-candidate-results' in html
    assert "/api/agentic/strategy/run-candidates" in js
    assert "runCandidateBacktests" in js
    assert "renderCandidateBacktestResults" in js


def test_agentic_candidate_backtest_styles_exist():
    styles = read_styles()

    for selector in [
        ".agentic-candidate-list",
        ".agentic-candidate-row",
        ".agentic-candidate-rank",
        ".agentic-candidate-metrics",
    ]:
        assert selector in styles



def test_agentic_candidate_rows_can_queue_promoted_strategy_for_paper():
    js = read_agentic_signals()

    assert 'data-agentic-action="queue-paper-strategy"' in js
    assert "/api/agentic/strategy/paper-candidates" in js
    assert "queuePaperStrategyCandidate" in js
    assert "promotion.promoted ?" in js


def test_agentic_paper_candidate_review_ui_is_registered():
    html = read_template()
    js = read_agentic_signals()

    assert 'data-agentic-paper-candidates' in html
    assert 'data-agentic-action="refresh-paper-candidates"' in html
    assert "loadPaperStrategyCandidates" in js
    assert "confirmPaperStrategyCandidate" in js
    assert "/api/agentic/strategy/paper-candidates" in js
    assert "/confirm" in js


def test_agentic_paper_flow_uses_plain_chinese_status_copy():
    js = read_agentic_signals()

    assert "paperStatusLabel" in js
    assert "等待你确认" in js
    assert "已进入模拟盘" in js
    assert "已写入订单" in js
    assert "下一步" in js
    assert "renderNextAgenticAction" in js


def test_agentic_review_limits_history_noise():
    js = read_agentic_signals()

    assert "AGENTIC_HISTORY_LIMIT" in js
    assert ".slice(0, AGENTIC_HISTORY_LIMIT)" in js


def test_agentic_paper_candidate_review_styles_exist():
    styles = read_styles()

    for selector in [
        ".agentic-paper-candidate-list",
        ".agentic-paper-candidate-row",
        ".agentic-paper-candidate-actions",
    ]:
        assert selector in styles


def test_agentic_active_paper_candidate_can_generate_execution_intent():
    js = read_agentic_signals()

    assert 'data-agentic-action="run-paper-strategy"' in js
    assert "runPaperStrategyCandidate" in js
    assert "/api/agentic/strategy/paper-executions" in js
    assert "loadPaperStrategyExecutions" in js
    assert "agentic-paper-execution-list" in read_styles()


def test_agentic_pending_execution_can_be_confirmed_from_frontend():
    js = read_agentic_signals()

    assert 'data-agentic-action="confirm-paper-execution"' in js
    assert "confirmPaperStrategyExecution" in js
    assert "/api/agentic/strategy/paper-executions" in js
    assert "risk_context" in js


def test_agentic_confirmed_execution_can_create_order_drafts_from_frontend():
    js = read_agentic_signals()

    assert 'data-agentic-action="create-order-drafts"' in js
    assert "createAgenticOrderDrafts" in js
    assert "/api/agentic/strategy/order-drafts" in js
    assert "loadAgenticOrderDrafts" in js
    assert "agentic-order-draft-list" in read_styles()


def test_agentic_confirmed_execution_can_submit_real_paper_orders_from_frontend():
    js = read_agentic_signals()

    assert 'data-agentic-action="submit-paper-orders"' in js
    assert "submitAgenticPaperOrders" in js
    assert "/paper-orders" in js
    assert "已写入模拟盘订单" in js


def test_agentic_frontend_shows_auth_prompt_for_unauthorized_api():
    js = read_agentic_signals()

    assert "agenticFetchJson" in js
    assert "请先登录后查看 Agent 策略实验台" in js
    assert "status === 401" in js
