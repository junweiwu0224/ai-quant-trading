from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "dashboard/ui/src"


def read_view(name: str) -> str:
    return (UI / "views" / name).read_text(encoding="utf-8")


def test_research_view_covers_real_data_edges_and_explicit_write_edges() -> None:
    source = read_view("ResearchView.vue")
    research_api = (UI / "api" / "research.ts").read_text(encoding="utf-8")

    for api_call in ("getKLineData", "getTechnicalIndicators", "getEvidence"):
        assert api_call in source
    decision = (UI / "components" / "research" / "DecisionCard.vue").read_text(encoding="utf-8")
    state_panel = (UI / "components" / "research" / "ResearchStatePanel.vue").read_text(encoding="utf-8")
    assert "数据不可用" in state_panel
    assert "当前无法生成确定性结论" in decision
    assert "进入验证并继承当前股票" in source
    assert "这不是交易指令" in decision
    assert "response.klines" in research_api
    assert "source-specific" not in source


def test_validation_view_renders_all_secondary_results_and_keeps_eligibility_separate() -> None:
    source = read_view("ValidationView.vue")

    for field_id in ("validation-train-ratio", "validation-simulations"):
        assert f'id="{field_id}"' in source
    for label in ("月度收益", "回撤曲线", "持仓周期", "绩效归因"):
        assert label in source
    for analysis_name in ("returns", "trades", "turnover", "weekday", "holding-period", "attribution"):
        assert f"'{analysis_name}'" in source
    for endpoint in (
        "api.backtestRun",
        "api.backtestMonthlyReturns",
        "api.backtestDrawdown",
        "api.backtestOutOfSample",
        "api.backtestMonteCarlo",
        "api.backtestAnalysis",
    ):
        assert endpoint in source
    assert "/validate`" in source
    assert "/preview`" in source
    assert "不会直接变成订单或自动推送资格" in source


def test_alpha_view_has_single_mode_authority_and_manual_formula_basket_actions() -> None:
    source = read_view("AlphaFactorsView.vue")

    assert "const mode = computed<Mode>(() => activeMode.value)" in source
    assert "activeMode.value = path.endsWith('/formula-basket') ? 'formula' : 'alpha'" in source
    for endpoint in (
        "api.alphaPredict",
        "api.alphaPerformance",
        "api.alphaFactorEval",
        "api.alphaWalkForward",
        "api.formulaEvaluate",
        "api.formulaScreen",
        "api.basketPlan",
        "api.basketBacktest",
    ):
        assert endpoint in source
    assert "显式运行" in source
    assert "不会产生真实订单" in source


def test_router_exposes_native_vue_research_validation_and_alpha_routes() -> None:
    source = (UI / "router.ts").read_text(encoding="utf-8")

    for route in (
        "/app/research/:market/:symbol",
        "/app/validation",
        "/app/research/alpha",
        "/app/research/formula-basket",
    ):
        assert f"path: '{route}'" in source
