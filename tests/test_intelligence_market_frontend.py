import subprocess
import textwrap
from pathlib import Path


def run_node(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["node", "-e", script],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_intelligence_heatmap_renders_weighted_treemap():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id) {
            return {
                id,
                innerHTML: '',
                textContent: '',
                offsetWidth: 720,
                classList: { add: () => {}, remove: () => {}, toggle: () => {} },
                addEventListener: () => {},
            };
        }

        const heatmap = makeElement('intel-heatmap');
        const elements = { 'intel-heatmap': heatmap };

        global.window = global;
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: () => null,
            addEventListener: () => {},
        };
        global.App = {
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
            fetchJSON: async (url) => {
                assert.equal(url, '/api/market/heatmap');
                return {
                    success: true,
                    timestamp: '2026-05-26 10:31:00',
                    sectors: [
                        { name: '银行', change_pct: 0.12, total_mv: 90000, up_count: 18, down_count: 10, leader: '工商银行' },
                        { name: '有色金属', change_pct: 2.34, total_mv: 40000, up_count: 42, down_count: 6, leader: '紫金矿业' },
                        { name: '半导体', change_pct: -1.45, total_mv: 30000, up_count: 9, down_count: 36, leader: '中芯国际' },
                        { name: '医药生物', change_pct: 0.52, total_mv: 20000, up_count: 21, down_count: 18, leader: '恒瑞医药' },
                    ],
                };
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));

        (async () => {
            await Intelligence.loadHeatmap();
            assert.match(heatmap.innerHTML, /intel-treemap/);
            assert.match(heatmap.innerHTML, /intel-treemap-tile/);
            assert.match(heatmap.innerHTML, /grid-column: span 18/);
            assert.match(heatmap.innerHTML, /银行/);
            assert.match(heatmap.innerHTML, /有色金属/);
            assert.match(heatmap.innerHTML, /上涨 3/);
            assert.match(heatmap.innerHTML, /下跌 1/);
            assert.doesNotMatch(heatmap.innerHTML, /class="heatmap-grid"/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_hotspot_shows_source_status_and_attribution_evidence():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id) {
            return {
                id,
                innerHTML: '',
                textContent: '',
                classList: { add: () => {}, remove: () => {}, toggle: () => {} },
                addEventListener: () => {},
            };
        }

        const hotspot = makeElement('intel-hotspot');
        const elements = { 'intel-hotspot': hotspot };

        global.window = global;
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: () => null,
            addEventListener: () => {},
        };
        global.App = {
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
            fetchJSON: async (url) => {
                assert.equal(url, '/api/market/hotspot');
                return {
                    success: true,
                    stale: true,
                    timestamp: '2026-05-26 10:30:00',
                    partial_errors: ['concept'],
                    summary: '今日热点：先进封装(+2.4%)、黄金概念(+1.3%)',
                    hot_concepts: [
                        { name: '先进封装', change_pct: 2.36, leader: '长电科技', leader_change: 6.2, stock_count: 36, up_count: 20, down_count: 16 },
                        { name: '黄金概念', change_pct: 1.32, leader: '紫金矿业', leader_change: 3.1, stock_count: 22, up_count: 18, down_count: 3 },
                    ],
                    hot_industries: [
                        { name: '工业金属', change_pct: 1.76, leader: '铜陵有色', up_count: 24, down_count: 5 },
                    ],
                    fund_flow: [
                        { name: '有色金属', main_net_inflow: 12.35, main_net_inflow_pct: 4.8 },
                    ],
                };
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));

        (async () => {
            await Intelligence.loadHotspot();
            assert.match(hotspot.innerHTML, /今日热点：先进封装/);
            assert.match(hotspot.innerHTML, /缓存数据/);
            assert.match(hotspot.innerHTML, /2026-05-26 10:30:00/);
            assert.match(hotspot.innerHTML, /数据源异常/);
            assert.match(hotspot.innerHTML, /热点概念/);
            assert.match(hotspot.innerHTML, /行业共振/);
            assert.match(hotspot.innerHTML, /主力净流入/);
            assert.match(hotspot.innerHTML, /长电科技/);
            assert.match(hotspot.innerHTML, /上涨20/);
            assert.match(hotspot.innerHTML, /有色金属/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_market_assets_are_versioned_and_styled():
    app_js = Path("dashboard/static/app.js").read_text(encoding="utf-8")
    styles = Path("dashboard/static/style.css").read_text(encoding="utf-8")
    scripts = Path("dashboard/templates/partials/scripts.html").read_text(encoding="utf-8")
    app_ui_shell = Path("dashboard/static/app-ui-shell.js").read_text(encoding="utf-8")
    service_worker = Path("dashboard/static/sw.js").read_text(encoding="utf-8")

    assert "/static/intelligence-market.js?v=2" in app_js
    assert "/static/intelligence-iwencai.js?v=3" in app_js
    assert "/static/app.js?v=52" in scripts
    assert "/static/app-ui-shell.js?v=12" in scripts
    assert "/sw.js?v=13" in app_ui_shell
    assert "ai-quant-v82" in service_worker
    assert ".intel-treemap" in styles
    assert ".intel-hotspot-status" in styles
    assert ".intel-hotspot-evidence" in styles


def test_iwencai_normalizes_exchange_suffix_codes_and_renders_focused_result_table():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id) {
            return {
                id,
                value: '电网设备',
                innerHTML: '',
                textContent: '',
                classList: { add: () => {}, remove: () => {}, toggle: () => {} },
                addEventListener: () => {},
            };
        }

        const input = makeElement('intel-iwencai-input');
        const button = makeElement('intel-iwencai-btn');
        const result = makeElement('intel-iwencai-result');
        const elements = {
            'intel-iwencai-input': input,
            'intel-iwencai-btn': button,
            'intel-iwencai-result': result,
        };

        global.window = global;
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: () => null,
            addEventListener: () => {},
            readyState: 'complete',
        };
        global.App = {
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
            fetchJSON: async (url) => {
                assert.equal(url, '/api/llm/iwencai');
                return {
                    success: true,
                    total: 100,
                    data: [
                        {
                            '股票代码': '605066.SH',
                            '股票简称': '天正电气',
                            '最新价': 8.01,
                            '最新涨跌幅': 10.027472527472522,
                            '所属同花顺行业': '电力设备-电网设备-输变电设备',
                            '最新DDE大单净额[20260527]': 116381140,
                            '所属概念': '电力物联网;智能电网;物联网;人工智能;工业互联网',
                            '市盈率(PE)[20260527]': 52.3051,
                            MARKET_CODE: 17,
                            CODE: '605066',
                        },
                    ],
                };
            },
            on: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-iwencai.js', 'utf8'));

        (async () => {
            await Intelligence.runIwencai();
            assert.match(result.innerHTML, /iwencai-focused-table/);
            assert.match(result.innerHTML, /data-code="605066"/);
            assert.doesNotMatch(result.innerHTML, /data-code="605066\.SH"/);
            assert.doesNotMatch(result.innerHTML, />605066\.SH</);
            assert.match(result.innerHTML, /天正电气/);
            assert.match(result.innerHTML, /\+10\.03%/);
            assert.match(result.innerHTML, /1\.16亿/);
            assert.match(result.innerHTML, /智能电网/);
            assert.doesNotMatch(result.innerHTML, /MARKET_CODE/);
            assert.deepEqual(Intelligence.state.iwencaiActionState.pool, ['605066']);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_iwencai_table_header_uses_non_overlapping_sticky_layout():
    styles = Path("dashboard/static/style.css").read_text(encoding="utf-8")

    assert ".iwencai-table-wrap" in styles
    assert "isolation: isolate" in styles
    assert "border-collapse: separate" in styles
    assert "border-spacing: 0" in styles
    assert "box-shadow: 0 1px 0" in styles


def test_iwencai_send_to_screener_opens_research_screener_directly():
    app_shell = Path("dashboard/static/core/app-shell.js").read_text(encoding="utf-8")
    screener_ai = Path("dashboard/static/screener-ai.js").read_text(encoding="utf-8")
    scripts = Path("dashboard/templates/partials/scripts.html").read_text(encoding="utf-8")

    assert "await this.switchTab('research', { subtab: 'screener' })" in app_shell
    assert 'querySelector(\'.research-sub-tab[data-subtab="screener"]\')?.click()' not in app_shell
    assert "codes: codes.slice(0, 100)" in screener_ai
    assert "this.renderResult(data, `问财: ${query}`)" in screener_ai
    assert "/static/core/app-shell.js?v=19" in scripts


def test_iwencai_ai_analysis_uses_focused_summary_rows_not_raw_fields():
    app_shell = Path("dashboard/static/core/app-shell.js").read_text(encoding="utf-8")
    iwencai = Path("dashboard/static/intelligence-iwencai.js").read_text(encoding="utf-8")

    assert "summaryRows" in iwencai
    assert "data.summaryRows" in app_shell
    assert "data.data.slice(0, 5)" not in app_shell
    assert "MARKET_CODE" not in app_shell
