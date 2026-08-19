from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_report_api_and_vue_expose_all_evidence_formats() -> None:
    router = (ROOT / "dashboard/routers/decisions.py").read_text(encoding="utf-8")
    view = (ROOT / "dashboard/ui/src/views/ReportsView.vue").read_text(encoding="utf-8")
    for format_name in ("json", "markdown", "pdf"):
        assert f"format={format_name}" in view
        assert f'"{format_name}"' in router


def test_system_navigation_keeps_reports_visible_and_live_trading_disabled() -> None:
    registry = (ROOT / "dashboard/ui/src/navigation/workflows.ts").read_text(encoding="utf-8")
    main = (ROOT / "dashboard/ui/src/components/MainContent.vue").read_text(encoding="utf-8")
    broker = (ROOT / "dashboard/ui/src/views/BrokerLiveView.vue").read_text(encoding="utf-8")

    for label in ("报告审计", "通知路由", "告警规则"):
        assert f"label: '{label}'" in registry
    assert "/app/broker" in main and "/app/settings" in main
    assert "禁止真实下单" in broker
