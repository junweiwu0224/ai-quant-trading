from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "dashboard/ui/src"


def read_ui(path: str) -> str:
    return (UI / path).read_text(encoding="utf-8")


def test_research_api_normalizes_object_klines_without_fake_zeroes() -> None:
    source = read_ui("api/research.ts")
    assert "Array.isArray(response.klines)" in source
    assert "finiteNumber(item.open)" in source
    assert "Number(kline[1])" not in source
    assert "source?: string; asOf?: string; error?: string" in source
    assert "`/api/stock/kline/${encodeURIComponent(symbol)}`" in source
    assert "/api/decisions/research/" not in source


def test_intelligence_does_not_offer_cn_iwencai_for_non_cn_markets() -> None:
    source = read_ui("views/IntelligenceView.vue")
    assert "const iwencaiSupported = computed(() => selectedMarket.value === 'CN')" in source
    assert 'v-if="iwencaiSupported"' in source
    assert "当前市场请进入手动标的研究" in source


def test_research_api_preserves_source_specific_evidence_failures() -> None:
    source = read_ui("api/research.ts")
    assert "Array.isArray(news.news)" in source
    assert "news.success === false" in source
    assert "source: 'news', status: 'unavailable'" in source
    assert "source: 'reports', status: 'unavailable'" in source
    assert "return { evidence, sources }" in source


def test_research_api_reads_daily_indicators_and_health_query_scope() -> None:
    research = read_ui("api/research.ts")
    market = read_ui("api/market.ts")
    assert "daily.ma5" in research
    assert "daily.ma10" in research
    assert "daily.ma20" in research
    assert "daily.ma60" in research
    assert "export async function getDataHealth(fast: boolean = false)" in market
    assert "params.symbol" not in market


def test_research_state_panel_has_explicit_unavailable_state() -> None:
    source = read_ui("components/research/ResearchStatePanel.vue")
    assert "state: 'loading' | 'available' | 'partial' | 'unavailable'" in source
    assert "数据不可用" in source
    assert "v-if=\"error\"" in source
