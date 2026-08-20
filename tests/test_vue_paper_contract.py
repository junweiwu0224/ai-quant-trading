from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "dashboard/ui/src"


def read_ui(path: str) -> str:
    return (UI / path).read_text(encoding="utf-8")


def test_paper_workspace_keeps_legacy_api_and_explicit_v2_fallbacks() -> None:
    api = read_ui("api/client.ts")
    view = read_ui("views/PaperRiskView.vue")

    assert "/api/paper/status" in api
    assert "/api/paper/start" in api
    assert "/api/paper/stop" in api
    assert "/api/paper/orders" in api
    assert "statusAvailable" in view
    assert "statusError" in view
    assert "statusDisplay" in view
    assert "canOperate" in view
    assert "reconciliationRequired" in view
    assert "v2Context.controlsBlocked" in view
    assert "v2Context.load" in view
    assert "所有执行操作已禁用" in view
    assert "已保留最后一次有效状态" in view
    assert "!canOperate" in view
    assert "execution_run_id" in view
    assert "ExecutionRun" in view
    assert "未绑定" in view
    assert "兼容模式" in view
    assert "account_id" in view
    assert "最终风控" in view
    assert "最终 RiskGate" in view
    assert "对账" in view
    assert "恢复" in view


def test_paper_workspace_has_live_disabled_guard_and_worker_aware_copy() -> None:
    view = read_ui("views/PaperRiskView.vue")

    assert "<strong>Live 已禁用</strong>" in view
    assert "不会调用 Broker" in view
    assert "暂停（未接入）" in view
    assert "等待 worker" in view
    assert "不代表已成交" in view
    assert "止损止盈已提交，等待 worker 状态确认" in view
    assert "actionFeedback" in view
    assert "actionError" in view
    assert "loadError" in view
    assert 'role="alert"' in view
    assert 'role="status"' in view
    assert 'aria-busy="loading"' in view
    assert 'role="tablist"' in view
    assert 'role="tab"' in view
    assert "aria-selected" in view
    assert "api.createPaperOrder" in view
    assert "api.stopPaper" in view
