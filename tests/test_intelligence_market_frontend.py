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

    assert "/static/intelligence-market.js?v=2" in app_js
    assert ".intel-treemap" in styles
    assert ".intel-hotspot-status" in styles
    assert ".intel-hotspot-evidence" in styles
