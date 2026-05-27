import subprocess
import textwrap
from pathlib import Path


def run_node(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["node", "-e", script],
        check=False,
        capture_output=True,
        text=True,
    )


def test_overview_opportunity_query_and_rendering():
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
                value: '',
                dataset: {},
                classList: {
                    add: () => {},
                    remove: () => {},
                    toggle: () => {},
                },
                addEventListener: () => {},
                querySelector: () => null,
                querySelectorAll: () => [],
            };
        }

        const elements = {
            'ov-opportunity-table': makeElement('ov-opportunity-table'),
            'ov-opportunity-hint': makeElement('ov-opportunity-hint'),
            'ov-opportunity-status': makeElement('ov-opportunity-status'),
        };
        const tbody = makeElement('ov-opportunity-tbody');
        elements['ov-opportunity-table'].querySelector = (selector) => selector === 'tbody' ? tbody : null;

        global.window = {
            dispatchEvent: () => {},
            addEventListener: () => {},
        };
        global.requestAnimationFrame = (fn) => fn();
        global.Event = function Event(name) { this.name = name; };
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: (selector) => selector === '#ov-opportunity-table tbody' ? tbody : null,
            querySelectorAll: () => [],
            addEventListener: () => {},
        };
        global.location = { hash: '#overview' };
        global.App = {
            watchlistCache: [{ code: '300750' }],
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
            fetchJSON: async () => ({ items: [], summary: {} }),
            toast: () => {},
            switchTab: async () => {},
            addToWatchlist: async () => {},
        };
        global.Watchlist = {
            render: () => {},
            setSelectedItems: () => {},
        };
        global.Utils = {
            formatBeijingTime: (value) => value,
            skeletonRows: () => '',
            todayBeijing: () => '2026-05-26',
            _bjOpts: {},
        };
        global.ChartFactory = { line: () => {}, showEmpty: () => {} };
        global.RealtimeQuotes = { getStatus: () => 'disconnected', getAllQuotes: () => ({}) };
        global.PollManager = { register: () => {}, cancel: () => {} };

        vm.runInThisContext(fs.readFileSync('dashboard/static/overview.js', 'utf8'));

        assert.equal(App._buildOverviewOpportunityQuery('watchlist').toString(), 'scope=watchlist&limit=8&fast=true');
        assert.equal(App._buildOverviewOpportunityQuery('qlib').toString(), 'scope=qlib&limit=8&fast=true');
        assert.equal(App._buildOverviewOpportunityQuery('default').toString(), 'scope=watchlist&limit=8&fast=true&force_fallback=true');

        App._renderOverviewOpportunityData({
            items: [{
                matrix_rank: 1,
                code: '300750',
                name: '宁德时代',
                industry: '电气设备',
                decision_score: 88,
                decision_label: '重点研究',
                peg_next_year: 0.91,
                risk_level: '中',
                reason_tags: ['PEG≤1', 'AI覆盖'],
                risk_tags: ['短线涨幅过热'],
                next_actions: ['进重点池', '打开估值详情'],
            }],
            summary: {
                total: 1,
                valuation_coverage_pct: 100,
                qlib_coverage_pct: 0,
                qlib_status: 'offline',
                qlib_cache_age_label: '无缓存',
                generated_at: '2026-05-26T18:00:00',
                fast_mode: true,
            },
        }, true);

        assert.match(elements['ov-opportunity-status'].innerHTML, /候选 1 只/);
        assert.match(elements['ov-opportunity-status'].innerHTML, /估值 100%/);
        assert.match(elements['ov-opportunity-status'].innerHTML, /Qlib 离线/);
        assert.match(tbody.innerHTML, /PEG≤1/);
        assert.match(tbody.innerHTML, /短线涨幅过热/);
        assert.match(tbody.innerHTML, /opportunity-evidence-tags/);
        assert.match(tbody.innerHTML, /opportunity-risk-tags/);
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_overview_opportunity_ignores_stale_full_response():
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
                dataset: {},
                classList: {
                    add: () => {},
                    remove: () => {},
                    toggle: () => {},
                },
                addEventListener: () => {},
                querySelector: () => null,
                querySelectorAll: () => [],
                setAttribute: () => {},
            };
        }

        const elements = {
            'ov-opportunity-table': makeElement('ov-opportunity-table'),
            'ov-opportunity-hint': makeElement('ov-opportunity-hint'),
            'ov-opportunity-status': makeElement('ov-opportunity-status'),
        };
        const tbody = makeElement('ov-opportunity-tbody');
        elements['ov-opportunity-table'].querySelector = (selector) => selector === 'tbody' ? tbody : null;

        global.window = { dispatchEvent: () => {}, addEventListener: () => {} };
        global.requestAnimationFrame = (fn) => fn();
        global.Event = function Event(name) { this.name = name; };
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: (selector) => selector === '#ov-opportunity-table tbody' ? tbody : null,
            querySelectorAll: () => [],
            addEventListener: () => {},
        };
        global.location = { hash: '#overview' };
        global.App = {
            _overviewOpportunityScope: 'qlib',
            watchlistCache: [{ code: '300750' }],
            escapeHTML: (value) => String(value ?? ''),
            fetchJSON: async () => ({ items: [], summary: {} }),
            toast: () => {},
            switchTab: async () => {},
            addToWatchlist: async () => {},
        };
        global.Watchlist = { render: () => {}, setSelectedItems: () => {} };
        global.Utils = { formatBeijingTime: (value) => value, skeletonRows: () => '', todayBeijing: () => '2026-05-26', _bjOpts: {} };
        global.ChartFactory = { line: () => {}, showEmpty: () => {} };
        global.RealtimeQuotes = { getStatus: () => 'disconnected', getAllQuotes: () => ({}) };
        global.PollManager = { register: () => {}, cancel: () => {} };

        vm.runInThisContext(fs.readFileSync('dashboard/static/overview.js', 'utf8'));

        const requestId = App._beginOverviewOpportunityRequest('qlib');
        App._overviewOpportunityScope = 'default';
        App._renderOverviewOpportunityData({
            items: [{
                matrix_rank: 1,
                code: '600519',
                name: '贵州茅台',
                decision_score: 80,
                decision_label: '旧范围',
                risk_level: '低',
                reason_tags: ['旧 Qlib'],
                risk_tags: [],
                next_actions: [],
            }],
            summary: { total: 1 },
        }, false, { scope: 'qlib', requestId });

        assert.equal(tbody.innerHTML, '');
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_overview_opportunity_template_and_styles_are_present():
    template = Path("dashboard/templates/index.html").read_text(encoding="utf-8")
    styles = Path("dashboard/static/style.css").read_text(encoding="utf-8")
    scripts = Path("dashboard/templates/partials/scripts.html").read_text(encoding="utf-8")

    assert 'id="ov-opportunity-status"' in template
    assert 'data-ov-opportunity-scope="watchlist"' in template
    assert 'data-ov-opportunity-scope="qlib"' in template
    assert 'data-ov-opportunity-scope="default"' in template
    assert ".opportunity-status-strip" in styles
    assert ".opportunity-scope-toggle" in styles
    assert ".opportunity-evidence-tags" in styles
    assert "/static/overview.js?v=12" in scripts
