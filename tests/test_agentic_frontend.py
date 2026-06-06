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
        ".agentic-signal-filter",
        ".agentic-signal-list",
        ".agentic-signal-card",
        ".agentic-signal-actions",
        ".agentic-signal-empty",
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

    assert 'data-agentic-paper-candidates' in js
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


def test_agentic_candidate_summary_explains_rejection_causes():
    js = read_agentic_signals()

    assert "buildCandidateDiagnosis" in js
    assert "产生交易为 0" in js
    assert "预测覆盖不足" in js
    assert "策略条件在样本内没有触发" in js
    assert "Sharpe 没达标" in js
    assert "agentic-diagnosis-list" in js


def test_agentic_strategy_lab_explains_candidate_logic_and_stock_names():
    html = read_template()
    js = read_agentic_signals()

    assert "候选依据" in html
    assert "本地日线覆盖" in html
    assert "formatStockLabel" in js
    assert "formatStockList" in js
    assert "stock_names" in js


def test_agentic_strategy_lab_presents_signal_as_baseline_not_decision_engine():
    html = read_template()
    js = read_agentic_signals()

    assert "AI 信号只是基线因子" in html
    assert "不是最终裁判" in html
    assert "renderGateChecks" in js
    assert "gate_checks" in js
    assert "数据质量" in js
    assert "回测表现" in js
    assert "风控边界" in js


def test_agentic_review_limits_history_noise():
    js = read_agentic_signals()

    assert "AGENTIC_HISTORY_LIMIT" in js
    assert ".slice(0, AGENTIC_HISTORY_LIMIT)" in js


def test_agentic_workbench_separates_current_action_from_history():
    html = read_template()
    js = read_agentic_signals()

    assert "agentic-current-action" in html
    assert "agentic-history-panel" in html
    assert "data-agentic-current-action" in html
    assert "data-agentic-history" in html
    assert "renderCurrentAgenticAction" in js
    assert "renderAgenticHistory" in js
    assert "currentActionItem" in js
    assert "historyItems" in js
    assert "新候选已生成，先确认是否进入模拟盘" in js
    review = html.split('data-agentic-current-action', 1)[1].split('id="agentic-signal-pool"', 1)[0]
    assert 'data-agentic-paper-candidates' not in review
    assert 'data-agentic-paper-executions' not in review
    assert 'data-agentic-order-drafts' not in review
    assert "renderPaperStrategyCandidates(history.candidates)" in js
    assert "renderPaperStrategyExecutions(history.executions)" in js
    assert "renderAgenticOrderDrafts(history.drafts)" in js


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
