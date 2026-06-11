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

        assert.equal(App._overviewOpportunityScope, 'signal');
        assert.equal(App._buildOverviewOpportunityQuery('watchlist').toString(), 'scope=watchlist&limit=8&fast=true');
        assert.equal(App._buildOverviewOpportunityQuery('signal').toString(), 'scope=signal&limit=8&fast=true');
        assert.equal(App._buildOverviewOpportunityQuery('qlib').toString(), 'scope=signal&limit=8&fast=true');
        assert.equal(App._buildOverviewOpportunityQuery('default').toString(), 'scope=signal&limit=8&fast=true');

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
                reason_tags: ['PEG≤1', '信号覆盖'],
                risk_tags: ['短线涨幅过热'],
                next_actions: ['进重点池', '打开估值详情'],
            }],
            summary: {
                total: 1,
                valuation_coverage_pct: 100,
                qlib_coverage_pct: 0,
                qlib_status: 'offline',
                qlib_cache_age_label: '无缓存',
                signal_quality: {
                    label: '未验证',
                    sample_days: 0,
                    penalty_applied: true,
                    message: '历史样本不足，AI信号已降权',
                },
                generated_at: '2026-05-26T18:00:00',
                fast_mode: true,
            },
        }, true);

        assert.match(elements['ov-opportunity-status'].innerHTML, /候选 1 只/);
        assert.match(elements['ov-opportunity-status'].innerHTML, /估值 100%/);
        assert.match(elements['ov-opportunity-status'].innerHTML, /AI信号 离线/);
        assert.match(elements['ov-opportunity-status'].innerHTML, /信号质量 未验证/);
        assert.match(elements['ov-opportunity-status'].innerHTML, /样本 0 天/);
        assert.match(elements['ov-opportunity-status'].innerHTML, /已降权/);
        assert.match(tbody.innerHTML, /PEG≤1/);
        assert.match(tbody.innerHTML, /短线涨幅过热/);
        assert.match(tbody.innerHTML, /opportunity-evidence-tags/);
        assert.match(tbody.innerHTML, /opportunity-risk-tags/);

        App._renderOverviewOpportunityStatus({
            total: 2,
            valuation_coverage_pct: 50,
            qlib_coverage_pct: 100,
            qlib_status: 'fresh',
            qlib_cache_age_label: '5分钟',
            qlib_sync_status: {
                success: false,
                success_count: 2,
                fail_count: 1,
                target_count: 3,
                finished_at: '2026-05-27T16:41:05',
            },
        }, 2, false);

        assert.match(elements['ov-opportunity-status'].innerHTML, /同步 2\/3/);
        assert.match(elements['ov-opportunity-status'].innerHTML, /失败 1/);
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_overview_opportunity_renders_all_returned_preview_rows():
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

        const items = Array.from({ length: 8 }, (_, idx) => ({
            matrix_rank: idx + 1,
            code: `00000${idx}`.slice(-6),
            name: `股票${idx + 1}`,
            decision_score: 60 + idx,
            decision_label: '可跟踪',
            risk_level: '中',
            reason_tags: ['信号候选'],
            risk_tags: ['AI未验证'],
            next_actions: ['加入自选跟踪'],
        }));
        App._renderOverviewOpportunityData({
            items,
            summary: {
                total: 8,
                signal_coverage_pct: 100,
                signal_status: 'online',
                signal_quality: { label: '未验证', sample_days: 0, penalty_applied: true },
                fast_mode: true,
            },
        }, true);

        assert.equal((tbody.innerHTML.match(/<tr>/g) || []).length, 8);
        assert.match(tbody.innerHTML, /股票8/);
        assert.match(elements['ov-opportunity-status'].innerHTML, /候选 8 只/);
    """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_overview_opportunity_next_actions_are_grouped_by_workflow_intent():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        global.App = {
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/overview.js', 'utf8'));

        const html = App._renderOpportunityRow({
            matrix_rank: 1,
            code: '300750',
            name: '宁德时代',
            decision_score: 85,
            decision_label: '重点研究',
            risk_level: '中',
            reason_tags: ['PEG≤1'],
            risk_tags: ['AI未验证'],
            next_actions: ['补看同业估值', '继续观察', '模拟小仓验证', '问龙虾生成交易计划'],
        });

        assert.match(html, /datahub-action-tag action-data[^>]*>补看同业估值/);
        assert.match(html, /datahub-action-tag action-watch[^>]*>继续观察/);
        assert.match(html, /datahub-action-tag action-trade[^>]*>模拟小仓验证/);
        assert.match(html, /datahub-action-tag action-research[^>]*>问龙虾生成交易计划/);
        assert.doesNotMatch(html, /datahub-next-tag/);
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_overview_opportunity_row_keeps_stock_meta_compact():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        global.App = {
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/overview.js', 'utf8'));

        const html = App._renderOpportunityRow({
            matrix_rank: 1,
            code: '600396',
            name: '华电辽能',
            industry: '电力、热力、燃气及水生产和供应业-电力、热力生产和供应业',
            decision_score: 74,
            decision_label: '可跟踪',
            peg_next_year: 0.83,
            risk_level: '中',
            reason_tags: ['PEG≤1', '高增长', '信号候选'],
            risk_tags: ['AI未验证'],
            next_actions: ['继续观察'],
        });

        assert.match(html, /class="[^"]*opportunity-stock-meta/);
        assert.match(html, />600396 · 电力、热力、燃气及水生产和供应业</);
        assert.match(html, /title="电力、热力、燃气及水生产和供应业-电力、热力生产和供应业"/);
        assert.doesNotMatch(html, />600396 电力、热力、燃气及水生产和供应业-电力、热力生产和供应业</);
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
            _overviewOpportunityScope: 'signal',
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

        const requestId = App._beginOverviewOpportunityRequest('signal');
        App._overviewOpportunityScope = 'default';
        App._renderOverviewOpportunityData({
            items: [{
                matrix_rank: 1,
                code: '600519',
                name: '贵州茅台',
                decision_score: 80,
                decision_label: '旧范围',
                risk_level: '低',
                reason_tags: ['旧信号'],
                risk_tags: [],
                next_actions: [],
            }],
            summary: { total: 1 },
        }, false, { scope: 'signal', requestId });

        assert.equal(tbody.innerHTML, '');
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_overview_opportunity_fast_timeout_falls_back_to_full_request():
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
        const calls = [];
        global.App = {
            _overviewOpportunityScope: 'signal',
            watchlistCache: [{ code: '300750' }],
            escapeHTML: (value) => String(value ?? ''),
            fetchJSON: async (url) => {
                calls.push(url);
                if (url.includes('fast=true')) throw new Error('请求超时');
                return {
                    items: [{
                        matrix_rank: 1,
                        code: '300750',
                        name: '宁德时代',
                        decision_score: 88,
                        decision_label: '补载成功',
                        risk_level: '低',
                        reason_tags: ['完整估值'],
                        risk_tags: [],
                        next_actions: [],
                    }],
                    summary: { total: 1, signal_quality: { label: '验证中性', sample_days: 259 } },
                };
            },
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

        (async () => {
            await App._loadOverviewOpportunities();
            assert.equal(calls.length, 2);
            assert.match(calls[0], /fast=true/);
            assert.match(calls[1], /max_wait_sec=6/);
            assert.match(tbody.innerHTML, /补载成功/);
            assert.doesNotMatch(tbody.innerHTML, /机会池加载失败/);
            assert.match(elements['ov-opportunity-status'].innerHTML, /候选 1 只/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_overview_load_starts_opportunities_after_watchlist_before_slow_snapshot():
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
                style: {},
            };
        }

        const ids = [
            'ov-equity', 'ov-daily-pnl', 'ov-cum-return', 'ov-max-dd', 'ov-sharpe',
            'ov-position-count', 'ov-stock-count', 'ov-latest-date', 'ov-paper-status',
            'ov-ai-status', 'ov-opportunity-table', 'ov-opportunity-hint', 'ov-opportunity-status',
        ];
        const elements = Object.fromEntries(ids.map((id) => [id, makeElement(id)]));
        const tbody = makeElement('ov-opportunity-tbody');
        elements['ov-opportunity-table'].querySelector = (selector) => selector === 'tbody' ? tbody : null;

        global.window = { dispatchEvent: () => {}, addEventListener: () => {} };
        global.requestAnimationFrame = (fn) => fn();
        global.Event = function Event(name) { this.name = name; };
        global.document = {
            getElementById: (id) => elements[id] || makeElement(id),
            querySelector: (selector) => selector === '#ov-opportunity-table tbody' ? tbody : null,
            querySelectorAll: () => [],
            addEventListener: () => {},
        };
        global.location = { hash: '#overview' };
        let releaseSnapshot;
        const calls = [];
        global.App = {
            _overviewOpportunityScope: 'signal',
            escapeHTML: (value) => String(value ?? ''),
            fmt: (value) => String(value ?? '--'),
            _showOverviewSkeletons: () => {},
            _renderMetric: () => {},
            _renderPctMetric: () => {},
            _checkSignalHealth: () => {},
            _loadDataHubHealth: () => {},
            _updateQuoteStatus: () => {},
            _updateMarketPhase: () => {},
            _registerOverviewTimers: () => {},
            _renderPositions: () => {},
            _loadOverviewSecondary: async () => {},
            _updateDataFreshness: () => {},
            _bindOverviewOpportunityActions: () => {},
            _buildWatchlistIndex: () => {},
            _getLegacyActionButton: () => null,
            toast: () => {},
            switchTab: async () => {},
            addToWatchlist: async () => {},
            fetchJSON: async (url) => {
                calls.push(url);
                if (url === '/api/watchlist') return [{ code: '300750' }];
                if (url.startsWith('/api/datahub/decision-matrix')) {
                    return { items: [], summary: { total: 0, signal_quality: { label: '未验证' } } };
                }
                if (url === '/api/portfolio/snapshot') {
                    return await new Promise((resolve) => {
                        releaseSnapshot = () => resolve({ total_equity: 0, positions: [] });
                    });
                }
                if (url === '/api/portfolio/trades/recent?limit=20') return [];
                if (url === '/api/system/status') return { db_stats: {}, paper_running: false, ai_model: '--' };
                return {};
            },
        };
        global.Watchlist = { render: () => {}, setSelectedItems: () => {} };
        global.Utils = { formatBeijingTime: (value) => value, skeletonRows: () => '', todayBeijing: () => '2026-05-26', _bjOpts: {} };
        global.ChartFactory = { line: () => {}, showEmpty: () => {} };
        global.RealtimeQuotes = { getStatus: () => 'disconnected', getAllQuotes: () => ({}) };
        global.PollManager = { register: () => {}, cancel: () => {} };

        vm.runInThisContext(fs.readFileSync('dashboard/static/overview.js', 'utf8'));
        App._overviewOpportunityResultKey = 'signal';

        (async () => {
            const pending = App.loadOverview();
            await Promise.resolve();
            await Promise.resolve();
            assert.ok(calls.includes('/api/watchlist'));
            assert.ok(calls.some((url) => url.startsWith('/api/datahub/decision-matrix?scope=signal&limit=8&fast=true')));
            assert.ok(!calls.includes('/api/portfolio/equity-history'));
            releaseSnapshot();
            await pending;
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_overview_opportunity_refresh_failure_preserves_previous_rows():
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
        tbody.innerHTML = '<tr><td>旧机会</td></tr>';
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
            _overviewOpportunityScope: 'signal',
            _overviewOpportunityItems: [{ code: '300750', name: '宁德时代' }],
            watchlistCache: [{ code: '300750' }],
            escapeHTML: (value) => String(value ?? ''),
            fetchJSON: async () => { throw new Error('请求超时'); },
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
        App._overviewOpportunityResultKey = 'signal';

        (async () => {
            await App._loadOverviewOpportunities();
            assert.match(tbody.innerHTML, /旧机会/);
            assert.doesNotMatch(tbody.innerHTML, /机会池加载失败/);
            assert.match(elements['ov-opportunity-status'].innerHTML, /刷新超时/);
            assert.match(elements['ov-opportunity-status'].innerHTML, /保留上次结果/);
            assert.match(elements['ov-opportunity-hint'].textContent, /保留上次机会池结果/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_overview_opportunity_full_timeout_preserves_previous_rows_and_tries_default_fallback():
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
        tbody.innerHTML = '<tr><td>旧机会</td></tr>';
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
        const calls = [];
        global.App = {
            _overviewOpportunityScope: 'signal',
            _overviewOpportunityItems: [{ code: '300750', name: '宁德时代' }],
            watchlistCache: [{ code: '300750' }],
            escapeHTML: (value) => String(value ?? ''),
            fetchJSON: async (url) => {
                calls.push(url);
                throw new Error('请求超时');
            },
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
        App._overviewOpportunityResultKey = 'signal';

        (async () => {
            await App._loadOverviewOpportunities();
            assert.equal(calls.length, 3);
            assert.match(calls[0], /fast=true/);
            assert.match(calls[1], /max_wait_sec=6/);
            assert.match(calls[2], /force_fallback=true/);
            assert.match(tbody.innerHTML, /旧机会/);
            assert.doesNotMatch(tbody.innerHTML, /机会池加载失败/);
            assert.match(elements['ov-opportunity-status'].innerHTML, /刷新超时/);
            assert.match(elements['ov-opportunity-status'].innerHTML, /保留上次结果/);
            assert.match(elements['ov-opportunity-hint'].textContent, /保留上次机会池结果/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_overview_opportunity_full_timeout_uses_default_candidates_without_previous_rows():
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
        const calls = [];
        global.App = {
            _overviewOpportunityScope: 'signal',
            watchlistCache: [{ code: '300750' }],
            escapeHTML: (value) => String(value ?? ''),
            fetchJSON: async (url) => {
                calls.push(url);
                if (url.includes('force_fallback=true')) {
                    return {
                        items: [{
                            matrix_rank: 1,
                            code: '600519',
                            name: '贵州茅台',
                            decision_score: 61,
                            decision_label: '降级预览',
                            risk_level: '中',
                            reason_tags: ['默认候选'],
                            risk_tags: ['数据源超时'],
                            next_actions: ['稍后刷新'],
                        }],
                        summary: {
                            total: 1,
                            used_fallback: true,
                            fallback_reason: 'client_timeout_default',
                            signal_quality: { label: '未验证', sample_days: 0, penalty_applied: true },
                        },
                    };
                }
                throw new Error('请求超时');
            },
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

        (async () => {
            await App._loadOverviewOpportunities();
            assert.equal(calls.length, 3);
            assert.match(calls[2], /force_fallback=true/);
            assert.match(tbody.innerHTML, /贵州茅台/);
            assert.doesNotMatch(tbody.innerHTML, /机会池加载失败/);
            assert.match(elements['ov-opportunity-status'].innerHTML, /范围 默认候选/);
            assert.match(elements['ov-opportunity-hint'].textContent, /降级预览/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_overview_opportunity_background_full_failure_marks_fast_preview_degraded():
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
                className: '',
                classList: { add: () => {}, remove: () => {}, toggle: () => {} },
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
            'ov-opportunity-trust': makeElement('ov-opportunity-trust'),
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
        const calls = [];
        global.App = {
            _overviewOpportunityScope: 'signal',
            watchlistCache: [{ code: '300750' }],
            escapeHTML: (value) => String(value ?? ''),
            fetchJSON: async (url) => {
                calls.push(url);
                if (url.includes('fast=true')) {
                    return {
                        items: [{
                            matrix_rank: 1,
                            code: '300750',
                            name: '宁德时代',
                            decision_score: 74,
                            decision_label: '快速预览',
                            risk_level: '中',
                            reason_tags: ['AI候选'],
                            risk_tags: ['AI未验证'],
                            next_actions: ['打开完整矩阵'],
                        }],
                        summary: {
                            total: 1,
                            signal_quality: { label: '未验证', sample_days: 0, penalty_applied: true },
                            fast_mode: true,
                        },
                    };
                }
                throw new Error('完整估值超时');
            },
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

        (async () => {
            await App._loadOverviewOpportunities();
            await Promise.resolve();
            await Promise.resolve();
            assert.equal(calls.length, 2);
            assert.match(tbody.innerHTML, /宁德时代/);
            assert.doesNotMatch(tbody.innerHTML, /机会池加载失败/);
            assert.match(elements['ov-opportunity-status'].innerHTML, /完整估值补载失败/);
            assert.match(elements['ov-opportunity-status'].innerHTML, /保留快速预览/);
            assert.match(elements['ov-opportunity-hint'].textContent, /完整估值补载失败/);
            assert.match(elements['ov-opportunity-hint'].textContent, /完整估值超时/);
            assert.match(elements['ov-opportunity-trust'].innerHTML, /需复核/);
            assert.match(elements['ov-opportunity-trust'].innerHTML, /保留快速预览/);
            assert.match(elements['ov-opportunity-trust'].className, /trust-review/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_overview_opportunity_does_not_preserve_rows_after_scope_change():
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
        tbody.innerHTML = '<tr><td>旧信号机会</td></tr>';
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
            watchlistCache: [{ code: '600519' }],
            escapeHTML: (value) => String(value ?? ''),
            fetchJSON: async () => { throw new Error('请求超时'); },
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
        App._overviewOpportunityScope = 'watchlist';
        App._overviewOpportunityItems = [{ code: '300750', name: '宁德时代' }];
        App._overviewOpportunityResultKey = 'signal';

        (async () => {
            await App._loadOverviewOpportunities();
            assert.doesNotMatch(tbody.innerHTML, /旧信号机会/);
            assert.match(tbody.innerHTML, /本地应急/);
            assert.match(tbody.innerHTML, /沪深300ETF/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_overview_opportunity_stale_fallback_failure_does_not_overwrite_new_request():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const status = { innerHTML: '新请求状态' };
        const hint = { textContent: '新请求提示' };
        const tbody = { innerHTML: '<tr><td>新请求结果</td></tr>' };
        global.window = { dispatchEvent: () => {}, addEventListener: () => {} };
        global.requestAnimationFrame = (fn) => fn();
        global.Event = function Event(name) { this.name = name; };
        global.document = {
            getElementById: (id) => id === 'ov-opportunity-status' ? status : id === 'ov-opportunity-hint' ? hint : null,
            querySelector: (selector) => selector === '#ov-opportunity-table tbody' ? tbody : null,
            querySelectorAll: () => [],
            addEventListener: () => {},
        };
        global.location = { hash: '#overview' };
        global.App = {
            _overviewOpportunityScope: 'watchlist',
            _overviewOpportunityActiveScope: 'watchlist',
            _overviewOpportunityRequestId: 2,
            _overviewOpportunityItems: [{ code: '300750' }],
            _overviewOpportunityResultKey: 'signal',
            watchlistCache: [{ code: '600519' }],
            escapeHTML: (value) => String(value ?? ''),
            fetchJSON: async () => { throw new Error('请求超时'); },
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

        (async () => {
            await App._loadOverviewOpportunitiesFallback('signal', 1, new Error('请求超时'), true);
            assert.equal(status.innerHTML, '新请求状态');
            assert.equal(hint.textContent, '新请求提示');
            assert.match(tbody.innerHTML, /新请求结果/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_overview_opportunity_empty_watchlist_stays_on_watchlist_without_fetching():
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
            watchlistCache: [],
            escapeHTML: (value) => String(value ?? ''),
            fetchJSON: async () => {
                throw new Error('empty watchlist should not fetch decision matrix');
            },
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

        App._setOverviewOpportunityScope('watchlist');

        assert.equal(App._overviewOpportunityScope, 'watchlist');
        assert.match(tbody.innerHTML, /请先添加股票到自选/);
        assert.match(elements['ov-opportunity-status'].innerHTML, /范围 自选/);
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_overview_opportunity_status_prefers_signal_sync_status():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const status = { innerHTML: '' };
        global.window = { dispatchEvent: () => {}, addEventListener: () => {} };
        global.requestAnimationFrame = (fn) => fn();
        global.Event = function Event(name) { this.name = name; };
        global.document = {
            getElementById: (id) => id === 'ov-opportunity-status' ? status : null,
            querySelector: () => null,
            querySelectorAll: () => [],
            addEventListener: () => {},
        };
        global.location = { hash: '#overview' };
        global.App = {
            _overviewOpportunityScope: 'signal',
            watchlistCache: [],
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

        App._renderOverviewOpportunityStatus({
            total: 3,
            signal_status: 'fresh',
            signal_coverage_pct: 66.7,
            signal_sync_status: {
                success_count: 2,
                fail_count: 1,
                target_count: 3,
            },
            qlib_sync_status: {
                success_count: 9,
                fail_count: 0,
                target_count: 9,
            },
            signal_quality: { label: '验证中性', sample_days: 12, penalty_applied: false },
        }, 3, false);

        assert.match(status.innerHTML, /同步 2\/3/);
        assert.match(status.innerHTML, /失败 1/);
        assert.match(status.innerHTML, /信号覆盖 67%/);
        assert.doesNotMatch(status.innerHTML, /AI覆盖 67%/);
        assert.doesNotMatch(status.innerHTML, /同步 9\/9/);
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_overview_opportunity_status_renders_source_time_and_coverage_notes():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const status = { innerHTML: '' };
        global.window = { dispatchEvent: () => {}, addEventListener: () => {} };
        global.requestAnimationFrame = (fn) => fn();
        global.Event = function Event(name) { this.name = name; };
        global.document = {
            getElementById: (id) => id === 'ov-opportunity-status' ? status : null,
            querySelector: () => null,
            querySelectorAll: () => [],
            addEventListener: () => {},
        };
        global.location = { hash: '#overview' };
        global.App = {
            _overviewOpportunityScope: 'signal',
            watchlistCache: [],
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

        App._renderOverviewOpportunityStatus({
            total: 8,
            universe: 'signal_top',
            source: 'signal_engine',
            generated_at: '2026-06-10T10:11:12',
            effective_count: 50,
            total_count: 5197,
            coverage_note: '机构预测覆盖池，不等同全量日线',
            source_unavailable: true,
            stale: true,
            stale_reason: 'signal_cache_unavailable',
            signal_status: 'offline',
            signal_coverage_pct: 0,
            valuation_coverage_pct: 25,
            signal_quality: { label: '未验证', sample_days: 0, penalty_applied: true },
        }, 8, true);

        assert.match(status.innerHTML, /来源 Signal Engine/);
        assert.match(status.innerHTML, /更新 2026-06-10T10:11:12/);
        assert.match(status.innerHTML, /有效 50\/5,197/);
        assert.match(status.innerHTML, /非全量/);
        assert.match(status.innerHTML, /数据源异常/);
        assert.match(status.innerHTML, /缓存数据/);
        assert.match(status.innerHTML, /原因 signal_cache_unavailable/);
        assert.match(status.innerHTML, /机构预测覆盖池，不等同全量日线/);
    """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_overview_opportunity_all_timeouts_use_local_emergency_preview_without_previous_rows():
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
        const calls = [];
        global.App = {
            _overviewOpportunityScope: 'signal',
            watchlistCache: [{ code: '300750' }],
            escapeHTML: (value) => String(value ?? ''),
            fetchJSON: async (url) => {
                calls.push(url);
                throw new Error('请求超时');
            },
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

        (async () => {
            await App._loadOverviewOpportunities();
            assert.equal(calls.length, 3);
            assert.match(calls[0], /fast=true/);
            assert.match(calls[1], /max_wait_sec=6/);
            assert.match(calls[2], /force_fallback=true/);
            assert.match(tbody.innerHTML, /本地应急/);
            assert.match(tbody.innerHTML, /沪深300ETF/);
            assert.match(tbody.innerHTML, /300ETF/);
            assert.doesNotMatch(tbody.innerHTML, />0\.00<\/td>/);
            assert.match(elements['ov-opportunity-status'].innerHTML, /范围 本地应急/);
            assert.match(elements['ov-opportunity-status'].innerHTML, /快速预览/);
            assert.match(elements['ov-opportunity-hint'].textContent, /本地应急机会池/);
            assert.doesNotMatch(tbody.innerHTML, /机会池加载失败/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_overview_opportunity_trust_panel_marks_real_default_and_emergency_states():
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
                className: '',
                disabled: false,
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
            'ov-opportunity-trust': makeElement('ov-opportunity-trust'),
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
            _overviewOpportunityScope: 'signal',
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
        global.Watchlist = { render: () => {}, setSelectedItems: () => {} };
        global.Utils = { formatBeijingTime: (value) => value, skeletonRows: () => '', todayBeijing: () => '2026-05-26', _bjOpts: {} };
        global.ChartFactory = { line: () => {}, showEmpty: () => {} };
        global.RealtimeQuotes = { getStatus: () => 'disconnected', getAllQuotes: () => ({}) };
        global.PollManager = { register: () => {}, cancel: () => {} };

        vm.runInThisContext(fs.readFileSync('dashboard/static/overview.js', 'utf8'));

        const realItem = {
            matrix_rank: 1,
            code: '300750',
            name: '宁德时代',
            decision_score: 88,
            decision_label: '重点研究',
            risk_level: '中',
            reason_tags: ['PEG≤1'],
            risk_tags: [],
            next_actions: ['进重点池'],
        };

        App._renderOverviewOpportunityData({
            items: [realItem],
            summary: {
                total: 1,
                signal_status: 'fresh',
                signal_coverage_pct: 100,
                valuation_coverage_pct: 100,
                signal_quality: { label: '验证中性', sample_days: 30, penalty_applied: false },
            },
        }, false);
        assert.match(elements['ov-opportunity-trust'].innerHTML, /真实合成/);
        assert.match(elements['ov-opportunity-trust'].innerHTML, /可进入研发复核/);
        assert.match(elements['ov-opportunity-trust'].innerHTML, /data-ov-opportunity-refresh/);
        assert.match(elements['ov-opportunity-trust'].innerHTML, /data-subtab="datahub"/);

        App._renderOverviewOpportunityData({
            items: [realItem],
            summary: {
                total: 1,
                used_fallback: true,
                fallback_reason: 'client_timeout_default',
                signal_quality: { label: '未验证', sample_days: 0, penalty_applied: true },
            },
        }, true);
        assert.match(elements['ov-opportunity-trust'].innerHTML, /降级预览/);
        assert.match(elements['ov-opportunity-trust'].innerHTML, /默认候选/);
        assert.match(elements['ov-opportunity-trust'].innerHTML, /先刷新或打开完整矩阵/);

        App._renderOverviewOpportunityLocalEmergency(new Error('请求超时'));
        assert.match(elements['ov-opportunity-trust'].innerHTML, /本地应急/);
        assert.match(elements['ov-opportunity-trust'].innerHTML, /不可作为真实信号/);
        assert.match(elements['ov-opportunity-trust'].className, /trust-emergency/);
        assert.doesNotMatch(tbody.innerHTML, /小仓|模拟|买入|交易/);
        assert.match(tbody.innerHTML, /稍后刷新/);
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_overview_opportunity_trust_panel_marks_low_coverage_real_data_as_needs_review():
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
                className: '',
                classList: { add: () => {}, remove: () => {}, toggle: () => {} },
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
            'ov-opportunity-trust': makeElement('ov-opportunity-trust'),
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
            _overviewOpportunityScope: 'signal',
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

        App._renderOverviewOpportunityData({
            items: [{
                matrix_rank: 1,
                code: '300750',
                name: '宁德时代',
                decision_score: 88,
                decision_label: '可跟踪',
                risk_level: '中',
                reason_tags: ['AI候选'],
                risk_tags: ['AI未验证'],
                next_actions: ['打开完整矩阵'],
            }],
            summary: {
                total: 8,
                valuation_coverage_pct: 0,
                signal_coverage_pct: 100,
                signal_status: 'fresh',
                signal_quality: { label: '未验证', sample_days: 0, penalty_applied: true },
                fast_mode: true,
            },
        }, true);

        assert.match(elements['ov-opportunity-trust'].innerHTML, /需复核/);
        assert.match(elements['ov-opportunity-trust'].innerHTML, /估值覆盖不足/);
        assert.match(elements['ov-opportunity-trust'].innerHTML, /信号未验证/);
        assert.match(elements['ov-opportunity-trust'].className, /trust-review/);
        assert.doesNotMatch(elements['ov-opportunity-trust'].className, /trust-real/);
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_overview_opportunity_openclaw_prompt_keeps_signal_trust_boundary():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        global.window = { dispatchEvent: () => {}, addEventListener: () => {} };
        global.requestAnimationFrame = (fn) => fn();
        global.Event = function Event(name) { this.name = name; };
        global.document = {
            getElementById: () => null,
            querySelector: () => null,
            querySelectorAll: () => [],
            addEventListener: () => {},
        };
        global.location = { hash: '#overview' };
        const sent = [];
        let activeTab = '';
        global.App = {
            _overviewOpportunityItems: [{
                code: '300750',
                name: '宁德时代',
                decision_score: 74,
                decision_label: '可跟踪',
                risk_level: '中',
                risk_tags: ['AI未验证'],
                next_actions: ['继续观察', '补齐缺失数据'],
                signal_rank: 2,
                signal_score: 0.998,
                signal_provider: 'local_momentum',
                signal_confidence: 'unverified',
                signal_quality: { label: '未验证', sample_days: 0, penalty_applied: true },
            }],
            escapeHTML: (value) => String(value ?? ''),
            fetchJSON: async () => ({ items: [], summary: {} }),
            toast: () => {},
            switchTab: async (tab) => { activeTab = tab; },
            addToWatchlist: async () => {},
        };
        global.Watchlist = { render: () => {}, setSelectedItems: () => {} };
        global.Utils = { formatBeijingTime: (value) => value, skeletonRows: () => '', todayBeijing: () => '2026-05-26', _bjOpts: {} };
        global.ChartFactory = { line: () => {}, showEmpty: () => {} };
        global.RealtimeQuotes = { getStatus: () => 'disconnected', getAllQuotes: () => ({}) };
        global.PollManager = { register: () => {}, cancel: () => {} };
        global.OpenClawWorkbench = {
            maybeInitForTab: async () => {},
            send: async (prompt) => { sent.push(prompt); },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/overview.js', 'utf8'));

        (async () => {
            await App._askOpportunityOpenClaw('300750');
            assert.equal(activeTab, 'openclaw');
            assert.equal(sent.length, 1);
            const prompt = sent[0];
            assert.match(prompt, /AI未验证/);
            assert.match(prompt, /样本 0 天/);
            assert.match(prompt, /已降权/);
            assert.match(prompt, /本地动量信号/);
            assert.match(prompt, /仅供观察/);
            assert.match(prompt, /不要给实盘下单建议/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_overview_opportunity_trust_refresh_button_reloads_current_pool():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        let panelClick = null;
        function makeElement(id) {
            return {
                id,
                innerHTML: '',
                textContent: '',
                dataset: {},
                className: '',
                disabled: false,
                classList: {
                    add: () => {},
                    remove: () => {},
                    toggle: () => {},
                },
                addEventListener: (event, handler) => {
                    if (id === 'ov-opportunity-trust' && event === 'click') panelClick = handler;
                },
                querySelector: () => null,
                querySelectorAll: () => [],
                setAttribute: () => {},
            };
        }

        const elements = {
            'ov-opportunity-table': makeElement('ov-opportunity-table'),
            'ov-opportunity-hint': makeElement('ov-opportunity-hint'),
            'ov-opportunity-status': makeElement('ov-opportunity-status'),
            'ov-opportunity-trust': makeElement('ov-opportunity-trust'),
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
            _overviewOpportunityScope: 'signal',
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

        let reloads = 0;
        App._loadOverviewOpportunities = async () => { reloads += 1; };
        App._bindOverviewOpportunityActions();
        assert.equal(typeof panelClick, 'function');

        (async () => {
            const refreshBtn = { disabled: false };
            await panelClick({
                preventDefault: () => {},
                target: {
                    closest: (selector) => selector === '[data-ov-opportunity-refresh]' ? refreshBtn : null,
                },
            });

            assert.equal(reloads, 1);
            assert.equal(refreshBtn.disabled, false);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_overview_opportunity_template_and_styles_are_present():
    template = Path("dashboard/templates/index.html").read_text(encoding="utf-8")
    styles = Path("dashboard/static/style.css").read_text(encoding="utf-8")
    scripts = Path("dashboard/templates/partials/scripts.html").read_text(encoding="utf-8")
    overview_js = Path("dashboard/static/overview.js").read_text(encoding="utf-8")

    assert 'id="ov-opportunity-status"' in template
    assert 'data-ov-opportunity-scope="watchlist"' in template
    assert 'data-ov-opportunity-scope="signal"' in template
    assert 'data-ov-opportunity-scope="qlib"' not in template
    assert 'data-ov-opportunity-scope="default"' not in template
    assert 'data-ov-opportunity-scope="signal" aria-pressed="true">AI信号 Top</button>' in template
    assert 'data-ov-opportunity-scope="watchlist" aria-pressed="false">自选</button>' in template
    assert 'id="ov-opportunity-trust"' in template
    assert 'data-ov-opportunity-refresh' in overview_js
    assert 'data-subtab="datahub"' in overview_js
    assert ".opportunity-status-strip" in styles
    assert ".opportunity-trust-panel" in styles
    assert ".opportunity-trust-badge" in styles
    assert ".opportunity-scope-toggle" in styles
    assert ".opportunity-evidence-tags" in styles
    assert "/static/overview.js?v=32" in scripts
    assert "/api/signals/health?fast=true" in overview_js
    assert "/api/datahub/health?fast=true" in overview_js
