from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIEW = ROOT / "dashboard/ui/src/views/ScreenerView.vue"
CLIENT = ROOT / "dashboard/ui/src/api/client.ts"


def test_screener_vue_covers_legacy_manual_and_candidate_workflows() -> None:
    source = VIEW.read_text(encoding="utf-8")

    for marker in (
        "api.screenerPresets()",
        "api.screenerFields()",
        "api.runScreenerPreset",
        "api.runScreener",
        "collectFilters",
        "addCondition",
        "exportCsv",
        "addToWatchlist",
        "addCodesToWatchlist",
        "导出 CSV",
        "全部加自选",
        "问财候选池",
        "导入条件筛选器",
    ):
        assert marker in source

    for field in ("pe_ratio", "pb_ratio", "market_cap", "turnover_rate", "change_pct"):
        assert field in source
    assert "候选只读" in source
    assert "不会创建自动推送资格、交易指令或实盘订单" in source


def test_screener_vue_covers_ai_model_status_training_and_prediction() -> None:
    source = VIEW.read_text(encoding="utf-8")
    client = CLIENT.read_text(encoding="utf-8")

    for marker in ("api.alphaModelStatus()", "api.alphaTrainGlobal", "api.alphaScreenAi", "训练全市场模型", "运行 AI 选股"):
        assert marker in source
    for path in ("/api/alpha/train-global", "/api/alpha/screen-ai?top_n=", "/api/screener/run-preset"):
        assert path in client
    assert "decision_effect: none" in source
    assert "未配置或数据不足时不会伪造结果" in source


def test_screener_vue_has_mobile_and_empty_state_hooks() -> None:
    source = (ROOT / "dashboard/ui/src/styles.css").read_text(encoding="utf-8")
    view = VIEW.read_text(encoding="utf-8")

    for marker in ("screener-boundary", "screener-condition-row", "screener-preset-list", "screener-table"):
        assert marker in source
    for marker in ("暂无候选", "没有匹配当前搜索词", "问财没有返回可展示候选", "候选只读"):
        assert marker in view
