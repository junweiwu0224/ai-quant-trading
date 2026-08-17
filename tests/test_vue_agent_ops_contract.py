from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIEW = ROOT / "dashboard/ui/src/views/AgentOpsView.vue"
CLIENT = ROOT / "dashboard/ui/src/api/client.ts"


def test_agent_ops_exposes_reference_flow_and_dsa_review_workflow() -> None:
    source = VIEW.read_text(encoding="utf-8")

    for api_call in ("api.aiTaskFlow", "api.aiReportFlow", "api.aiTask", "api.aiReport", "api.aiChatStream"):
        assert api_call in source
    for label in ("运行拓扑", "运行事件", "DSA 结构化复核", "能力矩阵", "最近尝试", "human review only"):
        assert label in source
    for block in (
        "core_conclusion",
        "data_perspective",
        "intelligence",
        "battle_plan",
        "phase_decision",
        "signal_attribution",
        "agent_disagreement_explanation",
    ):
        assert block in source
    assert "自动推送资格" in source
    assert "不改变确定性决策" in source
    assert "provider 已真实验证" in source
    assert "configured_recent_failure" in source
    assert "external_kline_fallback" in source
    assert "仅人工研究" in source
    assert "openclaw" not in source.lower()


def test_agent_ops_client_contract_carries_readiness_attempts_and_flow_edges() -> None:
    source = CLIENT.read_text(encoding="utf-8")

    for field in ("AIProviderReadiness", "AIProviderAttempt", "RunFlowNode", "RunFlowEdge", "RunFlowEvent", "DSAPhaseDecision"):
        assert field in source
    for path in ("/api/ai/tasks/${encodeURIComponent(taskId)}/flow", "/api/ai/reports/${encodeURIComponent(reportId)}/flow"):
        assert path in source
