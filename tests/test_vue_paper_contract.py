from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "dashboard/ui/src"


def read_ui(path: str) -> str:
    return (UI / path).read_text(encoding="utf-8")


def _read_paper_all() -> str:
    """Read the orchestrator, composable, and all sub-components."""
    parts = [
        read_ui("views/PaperRiskView.vue"),
        read_ui("composables/usePaperFormat.ts"),
        read_ui("components/paper/PaperContextPanel.vue"),
        read_ui("components/paper/PaperControlPanel.vue"),
        read_ui("components/paper/PaperOrderPanel.vue"),
        read_ui("components/paper/PaperPositionPanel.vue"),
        read_ui("components/paper/PaperPerformancePanel.vue"),
        read_ui("components/paper/PaperRiskPanel.vue"),
    ]
    return "\n".join(parts)


def test_paper_workspace_keeps_legacy_api_and_explicit_v2_fallbacks() -> None:
    api = read_ui("api/client.ts")
    all_paper = _read_paper_all()

    assert "/api/paper/status" in api
    assert "/api/paper/start" in api
    assert "/api/paper/stop" in api
    assert "/api/paper/orders" in api
    assert "canOperate" in all_paper
    assert "reconciliationRequired" in all_paper
    assert "v2Context.controlsBlocked" in all_paper
    assert "v2Context.load" in all_paper
    assert "!canOperate" in all_paper
    assert "execution_run_id" in all_paper
    assert "ExecutionRun" in all_paper
    assert "未绑定" in all_paper
    assert "兼容模式" in all_paper
    assert "account_id" in all_paper
    assert "最终风控" in all_paper
    assert "最终 RiskGate" in all_paper
    assert "对账" in all_paper
    assert "恢复" in all_paper


def test_paper_workspace_has_live_disabled_guard_and_worker_aware_copy() -> None:
    all_paper = _read_paper_all()

    assert "<strong>Live 已禁用</strong>" in all_paper
    assert "actionFeedback" in all_paper
    assert "actionError" in all_paper
    assert 'role="alert"' in all_paper
    assert 'role="status"' in all_paper
    assert 'role="tablist"' in all_paper
    assert 'role="tab"' in all_paper
    assert "aria-selected" in all_paper
    assert "api.createPaperOrder" in all_paper
    assert "api.stopPaper" in all_paper


def test_paper_sub_components_are_imported_in_orchestrator() -> None:
    view = read_ui("views/PaperRiskView.vue")

    assert "PaperContextPanel" in view
    assert "PaperControlPanel" in view
    assert "PaperOrderPanel" in view
    assert "PaperPositionPanel" in view
    assert "PaperPerformancePanel" in view
    assert "PaperRiskPanel" in view
