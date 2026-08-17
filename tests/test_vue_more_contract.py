from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_more_view_has_auditable_full_migration_matrix() -> None:
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
    assert "外部写操作不由此页面隐式触发" in source


def test_more_view_links_each_matrix_row_to_the_functional_vue_workflow() -> None:
    source = (ROOT / "dashboard/ui/src/views/MoreView.vue").read_text(encoding="utf-8")

    assert "status: 'compatibility'" not in source
    assert ':to="tool.route"' in source
    assert ':to="`/app/more/${tool.key}`"' not in source
    assert "api.get(" not in source
    assert 'v-if="selected"' not in source
    assert "打开 Vue 工作流" in source

    for route in (
        "/app/decision",
        "/app/research/CN/600519",
        "/app/validation",
        "/app/reports",
        "/app/more/screener",
        "/app/more/portfolio-risk",
        "/app/more/paper",
        "/app/more/conditional-orders",
        "/app/more/agents",
        "/app/more/broker-live",
    ):
        assert route in source
