from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_report_api_and_vue_expose_all_evidence_formats() -> None:
    router = (ROOT / "dashboard/routers/decisions.py").read_text(encoding="utf-8")
    view = (ROOT / "dashboard/ui/src/views/ReportsView.vue").read_text(encoding="utf-8")
    for format_name in ("json", "markdown", "pdf"):
        assert f"format={format_name}" in view
        assert f'"{format_name}"' in router


def test_more_view_maps_legacy_capabilities_and_marks_live_trading_disabled() -> None:
    source = (ROOT / "dashboard/ui/src/views/MoreView.vue").read_text(encoding="utf-8")
    for key in (
        "conditional-orders",
        "screener",
        "portfolio-risk",
        "strategies-backtest",
        "alpha-factors",
        "formula-basket",
        "paper",
        "agents",
        "broker-live",
    ):
        assert f"key: '{key}'" in source
    for field in ("api:", "route:", "historicalPath:", "capability:", "mobile:"):
        assert field in source
    assert "capability: 'disabled'" in source
    assert "真实下单" in source
