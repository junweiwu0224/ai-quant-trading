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


def test_intelligence_template_initial_state_is_loading_not_zero_or_dash():
    template = Path("dashboard/templates/index.html").read_text(encoding="utf-8")

    assert '<div class="signal-bar-label">市场广度</div>' in template
    assert '<div class="signal-bar-label">市场信号</div>' not in template
    assert '<div class="signal-bar-score" id="signal-bar-score">加载中</div>' in template
    assert '等待全市场广度' in template
    assert '<span class="badge badge-sm" id="intel-news-count">--</span>' in template
    assert '<span class="badge badge-sm" id="intel-news-count">0</span>' not in template
    assert '<div class="signal-bar-score" id="signal-bar-score">--</div>' not in template


def test_intelligence_signal_mimo_prompt_stays_observation_only():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        let clickHandler = null;
        const mimoButton = {
            dataset: {
                code: '300750',
                name: '宁德时代',
                score: '0.998',
                industry: '电力设备',
            },
        };
        global.window = global;
        global.document = {
            addEventListener: (event, handler) => {
                if (event === 'click') clickHandler = handler;
            },
        };
        const emitted = [];
        global.App = {
            registerContext: () => {},
            emit: (event, payload) => emitted.push({ event, payload }),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence.js', 'utf8'));

        Intelligence.bindDelegatedActions();
        assert.equal(typeof clickHandler, 'function');
        clickHandler({
            preventDefault: () => {},
            stopPropagation: () => {},
            target: {
                closest: (selector) => selector === '.qlib-btn-mimo' ? mimoButton : null,
            },
        });

        assert.equal(emitted.length, 1);
        assert.equal(emitted[0].event, 'iwencai:analyze');
        const query = emitted[0].payload.query;
        assert.match(query, /模拟盘观察计划/);
        assert.match(query, /风险点/);
        assert.match(query, /验证条件/);
        assert.match(query, /仅供观察/);
        assert.match(query, /不要给实盘下单建议/);
        assert.doesNotMatch(query, /止损位/);
        assert.doesNotMatch(query, /目标位/);
        assert.doesNotMatch(query, /如果买入/);
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_market_entry_map_declares_universe_explanation_and_status():
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
                assert.equal(url, '/api/market/heatmap?fast=true');
                return {
                    success: true,
                    fast: true,
                    local_fallback: true,
                    source: 'local_stock_daily',
                    universe: 'local_stock_daily_coverage_pool',
                    generated_at: '2026-06-10T09:30:00',
                    total: 2,
                    up_count: 2,
                    down_count: 0,
                    flat_count: 0,
                    avg_change_pct: 1.75,
                    coverage_note: '本地 stock_daily 覆盖池，按行业聚合',
                    sectors: [
                        { name: '银行', change_pct: 1.0, total_mv: 0, stock_count: 42, up_count: 41, down_count: 1, leader: '平安银行' },
                        { name: '电池', change_pct: 2.5, total_mv: 0, stock_count: 8, up_count: 8, down_count: 0, leader: '宁德时代' },
                    ],
                };
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));

        (async () => {
            await Intelligence.loadHeatmap();
            assert.match(heatmap.innerHTML, /intel-market-entry-map/);
            assert.match(heatmap.innerHTML, /本地覆盖池/);
            assert.match(heatmap.innerHTML, /指数/);
            assert.match(heatmap.innerHTML, /板块\/主题/);
            assert.match(heatmap.innerHTML, /资金流/);
            assert.match(heatmap.innerHTML, /universe/);
            assert.match(heatmap.innerHTML, /local_stock_daily_coverage_pool/);
            assert.match(heatmap.innerHTML, /解释变量/);
            assert.match(heatmap.innerHTML, /扩散和成分股/);
            assert.match(heatmap.innerHTML, /状态/);
            assert.match(heatmap.innerHTML, /待接入/);
            assert.match(heatmap.innerHTML, /来源 本地日线覆盖池/);
            assert.match(heatmap.innerHTML, /更新 2026-06-10T09:30:00/);
            assert.match(heatmap.innerHTML, /本地 stock_daily 覆盖池，按行业聚合/);
            assert.match(heatmap.innerHTML, /data-market-entry="capital-flow" data-status="deferred"/);
            assert.match(heatmap.innerHTML, /资金流入口待接入，当前不渲染为股票表/);
            assert.match(heatmap.innerHTML, /intel-treemap/);
            const capitalFlowEntry = heatmap.innerHTML.match(/<button[^>]*data-market-entry="capital-flow"[\s\S]*?<\/button>/)?.[0] || '';
            assert.match(capitalFlowEntry, /状态 待接入/);
            assert.doesNotMatch(capitalFlowEntry, /data-intel-action/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


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
                assert.equal(url, '/api/market/heatmap?fast=true');
                return {
                    success: true,
                    total: 496,
                    up_count: 350,
                    down_count: 144,
                    flat_count: 2,
                    avg_change_pct: 0.18,
                    source: 'eastmoney_sector_board',
                    timestamp: '2026-05-26 10:31:00',
                    generated_at: '2026-05-26T10:31:00',
                    coverage_note: '东方财富行业板块全量分页快照，热力图按市值权重展示',
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
            assert.match(heatmap.innerHTML, /上涨 350/);
            assert.match(heatmap.innerHTML, /下跌 144/);
            assert.match(heatmap.innerHTML, /平盘 2/);
            assert.match(heatmap.innerHTML, /全量板块 496 · 当前展示 4/);
            assert.match(heatmap.innerHTML, /口径 按板块总市值权重展示 Top 32/);
            assert.match(heatmap.innerHTML, /来源 东方财富行业板块/);
            assert.match(heatmap.innerHTML, /更新 2026-05-26T10:31:00/);
            assert.match(heatmap.innerHTML, /东方财富行业板块全量分页快照/);
            assert.doesNotMatch(heatmap.innerHTML, /class="heatmap-grid"/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_heatmap_does_not_assign_readonly_dom_dataset():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id) {
            const element = {
                id,
                innerHTML: '',
                textContent: '',
                offsetWidth: 720,
                classList: { add: () => {}, remove: () => {}, toggle: () => {} },
                addEventListener: () => {},
            };
            Object.defineProperty(element, 'dataset', {
                get() {
                    return this._dataset || (this._dataset = {});
                },
            });
            return element;
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
                assert.equal(url, '/api/market/heatmap?fast=true');
                return {
                    success: true,
                    source: 'local_stock_daily',
                    generated_at: '2026-06-10T09:30:00',
                    total: 1,
                    up_count: 1,
                    down_count: 0,
                    flat_count: 0,
                    avg_change_pct: 1.2,
                    sectors: [
                        { name: '银行', change_pct: 1.2, stock_count: 42, up_count: 41, down_count: 1, leader: '平安银行' },
                    ],
                };
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));

        (async () => {
            await Intelligence.loadHeatmap();
            assert.equal(heatmap.dataset.sectorDrilldownBound, '1');
            assert.match(heatmap.innerHTML, /intel-market-entry-map/);
            assert.match(heatmap.innerHTML, /intel-treemap-tile/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_heatmap_renders_local_fast_rows_without_market_value():
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
                assert.equal(url, '/api/market/heatmap?fast=true');
                return {
                    success: true,
                    fast: true,
                    local_fallback: true,
                    source: 'local_stock_daily',
                    total: 2,
                    up_count: 2,
                    down_count: 0,
                    flat_count: 0,
                    avg_change_pct: 1.75,
                    coverage_note: '本地 stock_daily 覆盖池，按行业聚合',
                    sectors: [
                        { name: '银行', change_pct: 1.0, total_mv: 0, stock_count: 42, up_count: 41, down_count: 1, leader: '平安银行' },
                        { name: '电池', change_pct: 2.5, total_mv: 0, stock_count: 8, up_count: 8, down_count: 0, leader: '宁德时代' },
                    ],
                };
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));

        (async () => {
            await Intelligence.loadHeatmap();
            assert.match(heatmap.innerHTML, /intel-treemap/);
            assert.match(heatmap.innerHTML, /intel-treemap-tile/);
            assert.match(heatmap.innerHTML, /银行/);
            assert.match(heatmap.innerHTML, /电池/);
            assert.match(heatmap.innerHTML, /42只 · 41↑ 1↓/);
            assert.match(heatmap.innerHTML, /8只 · 8↑ 0↓/);
            assert.match(heatmap.innerHTML, /口径 本地覆盖股数权重展示 Top 32/);
            assert.match(heatmap.innerHTML, /来源 本地日线覆盖池/);
            assert.doesNotMatch(heatmap.innerHTML, /暂无热力数据/);
            assert.doesNotMatch(heatmap.innerHTML, /0亿 · 41↑ 1↓/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_heatmap_click_renders_sector_members_and_opens_stock_with_pool_context():
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
                offsetWidth: 720,
                classList: { add: () => {}, remove: () => {}, toggle: () => {} },
                addEventListener(event, handler) {
                    if (event === 'click') this.clickHandler = handler;
                },
                querySelector: () => null,
            };
        }

        const heatmap = makeElement('intel-heatmap');
        const elements = { 'intel-heatmap': heatmap };
        const fetchCalls = [];
        let opened = null;

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
                fetchCalls.push(url);
                if (url === '/api/market/heatmap?fast=true') {
                    return {
                        success: true,
                        fast: true,
                        local_fallback: true,
                        source: 'local_stock_daily',
                        total: 1,
                        coverage_note: '本地 stock_daily 覆盖池，按行业聚合',
                        sectors: [
                            { name: '银行', change_pct: 1.0, total_mv: 0, stock_count: 2, up_count: 1, down_count: 1, leader: '平安银行', grouping: 'industry' },
                        ],
                    };
                }
                if (url === '/api/market/sector-members?name=%E9%93%B6%E8%A1%8C&grouping=industry&limit=30') {
                    return {
                        success: true,
                        sector_name: '银行',
                        source: 'local_stock_daily',
                        universe: 'local_stock_daily_coverage_pool',
                        total_count: 2,
                        effective_count: 2,
                        display_count: 2,
                        generated_at: '2026-06-05T15:00:00',
                        coverage_note: '本地 stock_daily 覆盖池行业成分',
                        source_context: {
                            source: 'market:sector-heatmap',
                            sourceLabel: '板块',
                            context_type: 'sector',
                            sector_name: '银行',
                        },
                        evidence_context: {
                            summary: {
                                direction: '多空均衡',
                                member_count: 2,
                                display_count: 2,
                                avg_change_pct: 0.5,
                                up_count: 1,
                                down_count: 1,
                                flat_count: 0,
                                leader: { code: '000001', name: '平安银行', change_pct: 2.0 },
                            },
                            liquidity: {
                                total_amount: 3000000000,
                                total_amount_yi: 30,
                                top_amount_member: { code: '600000', name: '浦发银行', amount: 2000000000 },
                                coverage_note: '以本地 stock_daily amount 作为量能代理',
                            },
                            signal_overlap: {
                                count: 1,
                                provider: 'local_momentum',
                                model_version: 'local_momentum_v1',
                                latest_date: '2026-06-05',
                                items: [
                                    { code: '000001', name: '平安银行', signal_score: 0.91, signal_confidence: 'validated_positive' },
                                ],
                            },
                            news_research: {
                                status: 'missing',
                                items: [],
                                missing_reason: '板块级新闻/研报证据尚未接入',
                            },
                            related_index: {
                                status: 'missing',
                                items: [],
                                missing_reason: '本地行业口径暂未映射关联指数',
                            },
                            next_actions: [
                                { id: 'send_screener', label: '发送到选股器' },
                                { id: 'open_stock', label: '打开成分股工作台' },
                                { id: 'draft_backtest', label: '生成板块篮子回测草案', status: 'deferred' },
                            ],
                        },
                        members: [
                            { code: '000001', name: '平安银行', price: 11.2, change_pct: 2.0, amount: 1000000000, sector_name: '银行' },
                            { code: '600000', name: '浦发银行', price: 8.5, change_pct: -1.0, amount: 2000000000, sector_name: '银行' },
                        ],
                    };
                }
                throw new Error(`unexpected url: ${url}`);
            },
            openStockDetail: async (code, options) => { opened = { code, options }; },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));

        (async () => {
            await Intelligence.loadHeatmap();
            assert.match(heatmap.innerHTML, /data-intel-action="select-sector"/);

            heatmap.clickHandler({
                preventDefault: () => {},
                target: {
                    closest: (selector) => {
                        if (selector === '[data-intel-action="select-sector"]') {
                            return { dataset: { sectorName: '银行', grouping: 'industry' } };
                        }
                        return null;
                    },
                },
            });
            await Intelligence.state.latestSectorMembersPromise;

            assert.deepEqual(fetchCalls, [
                '/api/market/heatmap?fast=true',
                '/api/market/sector-members?name=%E9%93%B6%E8%A1%8C&grouping=industry&limit=30',
            ]);
            assert.match(heatmap.innerHTML, /板块成分/);
            assert.match(heatmap.innerHTML, /银行/);
            assert.match(heatmap.innerHTML, /平安银行/);
            assert.match(heatmap.innerHTML, /浦发银行/);
            assert.match(heatmap.innerHTML, /有效 2\/2/);
            assert.match(heatmap.innerHTML, /class="intel-sector-evidence"/);
            assert.match(heatmap.innerHTML, /板块摘要/);
            assert.match(heatmap.innerHTML, /多空均衡/);
            assert.match(heatmap.innerHTML, /量能代理/);
            assert.match(heatmap.innerHTML, /成交额代理 30\.0亿/);
            assert.match(heatmap.innerHTML, /Signal 重叠/);
            assert.match(heatmap.innerHTML, /信号重叠 1只 · 验证偏正/);
            assert.match(heatmap.innerHTML, /新闻\/研报/);
            assert.match(heatmap.innerHTML, /板块级新闻\/研报证据尚未接入/);
            assert.match(heatmap.innerHTML, /关联指数/);
            assert.match(heatmap.innerHTML, /本地行业口径暂未映射关联指数/);
            assert.match(heatmap.innerHTML, /后续动作/);
            assert.match(heatmap.innerHTML, /发送到选股器/);
            assert.doesNotMatch(heatmap.innerHTML, /AI覆盖/);
            assert.doesNotMatch(heatmap.innerHTML, /AI信号分/);
            assert.doesNotMatch(heatmap.innerHTML, /预测/);
            assert.doesNotMatch(heatmap.innerHTML, /上涨概率/);
            assert.doesNotMatch(heatmap.innerHTML, /买入/);
            assert.doesNotMatch(heatmap.innerHTML, /强烈看多/);
            assert.match(heatmap.innerHTML, /data-intel-action="open-sector-stock"/);

            heatmap.clickHandler({
                preventDefault: () => {},
                target: {
                    closest: (selector) => {
                        if (selector === '[data-intel-action="select-sector"]') return null;
                        if (selector === '[data-intel-action="open-sector-stock"]') {
                            return { dataset: { code: '000001' } };
                        }
                        return null;
                    },
                },
            });

            assert.equal(opened.code, '000001');
            assert.equal(opened.options.source, 'market:sector-heatmap');
            assert.equal(opened.options.sector_name, '银行');
            assert.equal(opened.options.contextList.length, 2);
            assert.equal(opened.options.contextList[0].name, '平安银行');
            assert.equal(opened.options.source_context.context_type, 'sector');
            assert.equal(opened.options.source_context.sector_name, '银行');
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_heatmap_shows_soft_placeholder_when_fast_request_is_slow():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id) {
            return {
                id,
                innerHTML: '<div class="skeleton-block skeleton-pulse"></div>',
                textContent: '',
                dataset: {},
                offsetWidth: 720,
                classList: { add: () => {}, remove: () => {}, toggle: () => {} },
                addEventListener: () => {},
                querySelector(selector) {
                    if (selector === '.intel-heatmap-loading' && this.innerHTML.includes('intel-heatmap-loading')) {
                        return {};
                    }
                    return null;
                },
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
            fetchJSON: async () => new Promise(() => {}),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));
        Intelligence.state = { heatmapSoftTimeoutMs: 25 };

        (async () => {
            const result = await Promise.race([
                Intelligence.loadHeatmap().then(() => 'resolved'),
                new Promise((resolve) => setTimeout(() => resolve('timeout'), 80)),
            ]);
            assert.equal(result, 'resolved');
            assert.match(heatmap.innerHTML, /后台更新中/);
            assert.doesNotMatch(heatmap.innerHTML, /skeleton-block/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_heatmap_fallback_replaces_slow_placeholder_with_tiles():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id) {
            return {
                id,
                innerHTML: '<div class="skeleton-block skeleton-pulse"></div>',
                textContent: '',
                dataset: {},
                offsetWidth: 720,
                classList: { add: () => {}, remove: () => {}, toggle: () => {} },
                addEventListener: () => {},
                querySelector(selector) {
                    if (selector === '.intel-heatmap-loading' && this.innerHTML.includes('intel-heatmap-loading')) {
                        return {};
                    }
                    return null;
                },
            };
        }

        const heatmap = makeElement('intel-heatmap');
        const elements = { 'intel-heatmap': heatmap };
        const calls = [];

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
                calls.push(url);
                if (calls.length === 1) {
                    return new Promise(() => {});
                }
                return {
                    success: true,
                    fast: true,
                    local_fallback: true,
                    source: 'local_stock_daily',
                    total: 2,
                    up_count: 1,
                    down_count: 1,
                    flat_count: 0,
                    avg_change_pct: 0.4,
                    coverage_note: '本地 stock_daily 覆盖池，按交易板块聚合',
                    sectors: [
                        { name: '沪主板', change_pct: 0.9, total_mv: 0, stock_count: 1705, up_count: 964, down_count: 688, leader: '曙光股份' },
                        { name: '科创板', change_pct: -0.3, total_mv: 0, stock_count: 610, up_count: 296, down_count: 311, leader: '中船特气' },
                    ],
                };
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));
        Intelligence.state = { heatmapSoftTimeoutMs: 20, heatmapFallbackDelayMs: 30 };

        (async () => {
            await Intelligence.loadHeatmap();
            assert.match(heatmap.innerHTML, /后台更新中/);

            await new Promise((resolve) => setTimeout(resolve, 90));
            assert.deepEqual(calls, ['/api/market/heatmap?fast=true', '/api/market/heatmap?fast=true']);
            assert.match(heatmap.innerHTML, /intel-treemap/);
            assert.match(heatmap.innerHTML, /沪主板/);
            assert.match(heatmap.innerHTML, /科创板/);
            assert.doesNotMatch(heatmap.innerHTML, /后台更新中/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_sentiment_renders_full_market_breadth_counts():
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

        const sentiment = makeElement('intel-sentiment');
        const sentimentHeader = makeElement('intel-sentiment-header');
        sentimentHeader.innerHTML = '市场情绪';
        const elements = { 'intel-sentiment': sentiment };

        global.window = global;
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: (selector) => selector === '.intel-sentiment-card h3' ? sentimentHeader : null,
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
                assert.equal(url, '/api/market/breadth');
                return {
                    success: true,
                    source: 'local_stock_daily',
                    stock_count: 5525,
                    total_stocks: 5525,
                    effective_count: 5515,
                    up_count: 2310,
                    down_count: 2860,
                    flat_count: 355,
                    limit_up: 68,
                    limit_down: 21,
                    latest_date: '2026-06-05',
                    ignored_latest_date: '2026-06-08',
                    ignored_latest_date_covered: 15,
                    ignored_latest_date_coverage_pct: 0.27,
                    min_selected_date_coverage_pct: 80,
                };
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));

        (async () => {
            await Intelligence.loadSentiment();
            assert.match(sentiment.innerHTML, /上涨/);
            assert.match(sentiment.innerHTML, /2,310/);
            assert.match(sentiment.innerHTML, /2,860/);
            assert.match(sentiment.innerHTML, /上涨占比/);
            assert.match(sentiment.innerHTML, /有效\/全量 5,515\/5,525/);
            assert.match(sentiment.innerHTML, /来源 本地日线覆盖池/);
            assert.match(sentiment.innerHTML, /口径 全市场上涨下跌广度/);
            assert.match(sentiment.innerHTML, /公式 \(上涨-下跌\)\/\(上涨\+下跌\+平盘\)/);
            assert.match(sentiment.innerHTML, /平盘 355/);
            assert.match(sentiment.innerHTML, /未更新 10/);
            assert.match(sentiment.innerHTML, /涨停 68/);
            assert.match(sentiment.innerHTML, /跌停 21/);
            assert.match(sentiment.innerHTML, /2026-06-05/);
            assert.match(sentiment.innerHTML, /已忽略 2026-06-08 零散样本 15 只/);
            assert.match(sentiment.innerHTML, /低于 80% 覆盖阈值/);
            assert.match(sentimentHeader.innerHTML, /市场情绪/);
            assert.match(sentimentHeader.innerHTML, /偏空/);
            assert.match(sentimentHeader.innerHTML, /-10/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_sentiment_marks_direction_unreliable_when_breadth_sample_is_tiny():
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

        const sentiment = makeElement('intel-sentiment');
        const sentimentHeader = makeElement('intel-sentiment-header');
        sentimentHeader.innerHTML = '市场情绪';
        const elements = { 'intel-sentiment': sentiment };

        global.window = global;
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: (selector) => selector === '.intel-sentiment-card h3' ? sentimentHeader : null,
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
                assert.equal(url, '/api/market/breadth');
                return {
                    success: true,
                    source: 'local_stock_daily',
                    stock_count: 5525,
                    total_stocks: 5525,
                    effective_count: 15,
                    up_count: 2,
                    down_count: 13,
                    flat_count: 0,
                    limit_up: 0,
                    limit_down: 0,
                    latest_date: '2026-06-08',
                };
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));

        (async () => {
            await Intelligence.loadSentiment();
            assert.match(sentimentHeader.innerHTML, /覆盖不足/);
            assert.match(sentimentHeader.innerHTML, /样本 15\/5,525/);
            assert.doesNotMatch(sentimentHeader.innerHTML, /偏空/);
            assert.doesNotMatch(sentimentHeader.innerHTML, /-73/);
            assert.match(sentiment.innerHTML, /覆盖不足，方向仅供参考/);
            assert.match(sentiment.innerHTML, /有效\/全量 15\/5,525/);
            assert.match(sentiment.innerHTML, /未更新 5,510/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_news_renders_source_and_count():
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

        const list = makeElement('intel-news-list');
        const count = makeElement('intel-news-count');
        const timestamp = makeElement('intel-timestamp');
        const elements = {
            'intel-news-list': list,
            'intel-news-count': count,
            'intel-timestamp': timestamp,
        };

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
                assert.equal(url, '/api/market/news');
                return {
                    success: true,
                    timestamp: '2026-06-06T23:20:00',
                    source: '东方财富快讯',
                    coverage_note: '东方财富滚动快讯，按时间倒序展示',
                    ranking: {
                        method: 'actionable_value',
                        description: '按个股关联、主题关联、情绪强度和来源可信度综合排序',
                    },
                    news: [
                        {
                            title: '近三个月车规级存储芯片价格暴涨180%',
                            time: '2026-06-06 22:42:26',
                            source: '东方财富快讯',
                            sentiment: 0.3,
                            value_score: 4.2,
                            value_reasons: ['关联主题', '情绪显著'],
                        },
                    ],
                };
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));

        (async () => {
            await Intelligence.loadNews();
            assert.equal(String(count.textContent), '1');
            assert.equal(timestamp.textContent, '2026-06-06T23:20:00');
            assert.match(list.innerHTML, /新闻源 东方财富快讯/);
            assert.match(list.innerHTML, /更新 2026-06-06T23:20:00/);
            assert.match(list.innerHTML, /展示 1 条/);
            assert.match(list.innerHTML, /价值摘要/);
            assert.match(list.innerHTML, /排序 价值优先/);
            assert.match(list.innerHTML, /按个股关联、主题关联、情绪强度和来源可信度综合排序/);
            assert.match(list.innerHTML, /关联新闻 0\/1 条/);
            assert.match(list.innerHTML, /关联股票 0 只/);
            assert.match(list.innerHTML, /情绪 正1 中0 负0/);
            assert.match(list.innerHTML, /东方财富滚动快讯/);
            assert.match(list.innerHTML, /东方财富快讯/);
            assert.match(list.innerHTML, /价值 4\.2/);
            assert.match(list.innerHTML, /关联主题/);
            assert.match(list.innerHTML, /情绪显著/);
            assert.match(list.innerHTML, /近三个月车规级存储芯片价格暴涨180%/);
            assert.match(list.innerHTML, /2026-06-06 22:42:26/);
            assert.doesNotMatch(list.innerHTML, /暂无新闻/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_news_does_not_override_market_sentiment_header():
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

        const list = makeElement('intel-news-list');
        const count = makeElement('intel-news-count');
        const timestamp = makeElement('intel-timestamp');
        const sentimentHeader = makeElement('intel-sentiment-header');
        sentimentHeader.innerHTML = '市场情绪 <span class="text-up">偏多 (+17)</span>';
        const elements = {
            'intel-news-list': list,
            'intel-news-count': count,
            'intel-timestamp': timestamp,
        };

        global.window = global;
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: (selector) => selector === '.intel-sentiment-card h3' ? sentimentHeader : null,
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
                assert.equal(url, '/api/market/news');
                return {
                    success: true,
                    timestamp: '2026-06-06T23:20:00',
                    source: '东方财富快讯',
                    overall_sentiment: -0.43,
                    news: [
                        { title: '宏观扰动升温', time: '2026-06-06 22:42:26', source: '东方财富快讯', sentiment: -0.4 },
                    ],
                };
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));

        (async () => {
            await Intelligence.loadNews();
            assert.match(list.innerHTML, /新闻源 东方财富快讯/);
            assert.match(sentimentHeader.innerHTML, /偏多/);
            assert.match(sentimentHeader.innerHTML, /\+17/);
            assert.doesNotMatch(sentimentHeader.innerHTML, /偏空/);
            assert.doesNotMatch(sentimentHeader.innerHTML, /-0\.43/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_news_empty_state_keeps_timestamp_and_source_context():
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

        const list = makeElement('intel-news-list');
        const count = makeElement('intel-news-count');
        const timestamp = makeElement('intel-timestamp');
        const elements = {
            'intel-news-list': list,
            'intel-news-count': count,
            'intel-timestamp': timestamp,
        };

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
                assert.equal(url, '/api/market/news');
                return {
                    success: true,
                    timestamp: '2026-06-06T23:20:00',
                    generated_at: '2026-06-06T23:21:00',
                    source: 'eastmoney_news',
                    coverage_note: '东方财富滚动快讯，当前接口返回空列表',
                    stale: true,
                    news: [],
                };
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));

        (async () => {
            await Intelligence.loadNews();
            assert.equal(String(count.textContent), '0');
            assert.equal(timestamp.textContent, '2026-06-06T23:20:00');
            assert.match(list.innerHTML, /暂无市场新闻/);
            assert.match(list.innerHTML, /新闻源 东方财富快讯/);
            assert.match(list.innerHTML, /2026-06-06T23:20:00/);
            assert.match(list.innerHTML, /生成 2026-06-06T23:21:00/);
            assert.match(list.innerHTML, /缓存数据/);
            assert.match(list.innerHTML, /东方财富滚动快讯，当前接口返回空列表/);
            assert.doesNotMatch(list.innerHTML, /加载失败/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_news_source_unavailable_uses_human_source_label():
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

        const list = makeElement('intel-news-list');
        const count = makeElement('intel-news-count');
        const timestamp = makeElement('intel-timestamp');
        const elements = {
            'intel-news-list': list,
            'intel-news-count': count,
            'intel-timestamp': timestamp,
        };

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
                assert.equal(url, '/api/market/news');
                return {
                    success: true,
                    timestamp: '2026-06-08T15:30:00',
                    generated_at: '2026-06-08T15:30:01',
                    source: 'market_news_multi_source',
                    coverage_note: '多源市场新闻聚合，当前新闻源无可用记录',
                    source_unavailable: true,
                    stale: true,
                    stale_reason: 'no_news_source',
                    news: [],
                    sources: [],
                };
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));

        (async () => {
            await Intelligence.loadNews();
            assert.equal(String(count.textContent), '0');
            assert.match(list.innerHTML, /新闻源 市场新闻聚合/);
            assert.match(list.innerHTML, /数据源异常/);
            assert.match(list.innerHTML, /缓存数据/);
            assert.match(list.innerHTML, /原因 no_news_source/);
            assert.match(list.innerHTML, /多源市场新闻聚合，当前新闻源无可用记录/);
            assert.doesNotMatch(list.innerHTML, /market_news_multi_source/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_news_retries_once_after_transient_failure():
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

        const list = makeElement('intel-news-list');
        const count = makeElement('intel-news-count');
        const elements = {
            'intel-news-list': list,
            'intel-news-count': count,
        };
        let calls = 0;

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
                assert.equal(url, '/api/market/news');
                calls += 1;
                if (calls === 1) {
                    throw new Error('请求超时');
                }
                return {
                    success: true,
                    timestamp: '2026-06-06T23:20:00',
                    source: 'eastmoney_news',
                    news: [
                        { title: '政策催化带动板块活跃', time: '2026-06-06 22:42:26', source: '东方财富快讯', sentiment: 0.2 },
                    ],
                };
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));

        (async () => {
            await Intelligence.loadNews();
            assert.equal(calls, 2);
            assert.equal(String(count.textContent), '1');
            assert.match(list.innerHTML, /政策催化带动板块活跃/);
            assert.doesNotMatch(list.innerHTML, /加载失败/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_signal_bar_uses_full_market_breadth_only():
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
                style: {},
                title: '',
                classList: { add: () => {}, remove: () => {}, toggle: () => {} },
                addEventListener: () => {},
            };
        }

        const bar = makeElement('signal-bar');
        const marker = makeElement('signal-bar-marker');
        const score = makeElement('signal-bar-score');
        const sources = makeElement('signal-bar-sources');
        const elements = {
            'signal-bar': bar,
            'signal-bar-marker': marker,
            'signal-bar-score': score,
            'signal-bar-sources': sources,
        };
        const calls = [];

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
                calls.push(url);
                assert.equal(url, '/api/market/breadth');
                return {
                    success: true,
                    up_count: 2982,
                    down_count: 2089,
                    flat_count: 124,
                    effective_count: 5515,
                    stock_count: 5525,
                    limit_up: 96,
                    limit_down: 19,
                    latest_date: '2026-06-05',
                    ignored_latest_date: '2026-06-08',
                    ignored_latest_date_covered: 15,
                    min_selected_date_coverage_pct: 80,
                };
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));
        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-signals.js', 'utf8'));

        (async () => {
            await Intelligence.loadSignalBar();
            assert.deepEqual(calls, ['/api/market/breadth']);
            assert.equal(score.textContent, '广度分 +17');
            assert.match(score.title, /全市场广度分/);
            assert.match(score.title, /\(上涨 2,982 - 下跌 2,089\) \/ 分类样本 5,195/);
            assert.match(sources.innerHTML, /来源 本地日线覆盖池/);
            assert.match(sources.innerHTML, /口径 全市场广度/);
            assert.match(sources.innerHTML, /公式 \(上涨-下跌\)\/\(上涨\+下跌\+平盘\)/);
            assert.match(sources.innerHTML, /含义 涨跌广度净占比 \+17%/);
            assert.match(sources.innerHTML, /上涨占比 57%/);
            assert.match(sources.innerHTML, /涨跌比 1\.43/);
            assert.match(sources.innerHTML, /涨停\/跌停 96\/19/);
            assert.match(sources.innerHTML, /样本 5,515\/5,525/);
            assert.match(sources.innerHTML, /交易日 2026-06-05/);
            assert.match(sources.innerHTML, /忽略 2026-06-08 零散样本 15 只/);
            const markerPct = Number(marker.style.left.replace('%', ''));
            assert.ok(markerPct > 58.5 && markerPct < 58.7);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_signal_bar_marks_breadth_score_unreliable_when_sample_is_tiny():
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
                style: {},
                title: '',
                classList: { add: () => {}, remove: () => {}, toggle: () => {} },
                addEventListener: () => {},
            };
        }

        const marker = makeElement('signal-bar-marker');
        const score = makeElement('signal-bar-score');
        const sources = makeElement('signal-bar-sources');
        const elements = {
            'signal-bar': makeElement('signal-bar'),
            'signal-bar-marker': marker,
            'signal-bar-score': score,
            'signal-bar-sources': sources,
        };

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
                assert.equal(url, '/api/market/breadth');
                return {
                    success: true,
                    up_count: 2,
                    down_count: 13,
                    flat_count: 0,
                    effective_count: 15,
                    stock_count: 5525,
                    limit_up: 0,
                    limit_down: 0,
                };
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));
        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-signals.js', 'utf8'));

        (async () => {
            await Intelligence.loadSignalBar();
            assert.equal(score.textContent, '样本不足');
            assert.match(score.title, /覆盖不足/);
            assert.match(score.title, /原始广度分 -73/);
            assert.equal(marker.style.left, '50%');
            assert.match(sources.innerHTML, /覆盖不足，方向仅供参考/);
            assert.match(sources.innerHTML, /样本 15\/5,525/);
            assert.match(sources.innerHTML, /原始广度分 -73/);
            assert.notEqual(score.textContent, '广度分 -73');
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_signal_bar_recovers_when_shared_breadth_arrives_after_timeout():
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
                style: {},
                title: '',
                classList: { add: () => {}, remove: () => {}, toggle: () => {} },
                addEventListener: () => {},
            };
        }

        const marker = makeElement('signal-bar-marker');
        const score = makeElement('signal-bar-score');
        const sources = makeElement('signal-bar-sources');
        const elements = {
            'signal-bar': makeElement('signal-bar'),
            'signal-bar-marker': marker,
            'signal-bar-score': score,
            'signal-bar-sources': sources,
        };
        let resolveBreadth;
        const breadthPromise = new Promise((resolve) => { resolveBreadth = resolve; });

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
                assert.equal(url, '/api/market/breadth');
                return breadthPromise;
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));
        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-signals.js', 'utf8'));

        (async () => {
            const loading = Intelligence.loadSignalBar();
            await new Promise((resolve) => setTimeout(resolve, 1600));
            assert.equal(score.textContent, '计算中');
            assert.match(sources.innerHTML, /全市场广度计算中/);

            resolveBreadth({
                success: true,
                up_count: 2982,
                down_count: 2089,
                flat_count: 124,
                effective_count: 5515,
                stock_count: 5525,
                limit_up: 96,
                limit_down: 19,
            });
            await loading;
            await new Promise((resolve) => setTimeout(resolve, 0));

            assert.equal(score.textContent, '广度分 +17');
            assert.match(sources.innerHTML, /口径 全市场广度/);
            assert.match(sources.innerHTML, /样本 5,515\/5,525/);
            assert.doesNotMatch(sources.innerHTML, /全市场广度计算中/);
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


def test_intelligence_news_summarizes_value_by_stock_links_and_sentiment_mix():
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

        const list = makeElement('intel-news-list');
        const count = makeElement('intel-news-count');
        const elements = {
            'intel-news-list': list,
            'intel-news-count': count,
        };

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
                assert.equal(url, '/api/market/news');
                return {
                    success: true,
                    timestamp: '2026-06-08T23:55:00',
                    source: 'market_news_multi_source',
                    coverage_note: '多源市场新闻聚合：东方财富快讯',
                    linked_news_count: 2,
                    linked_stock_count: 2,
                    topic_count: 3,
                    news: [
                        {
                            title: '存储芯片价格上涨',
                            time: '2026-06-08 23:30:00',
                            source: '东方财富快讯',
                            sentiment: 0.4,
                            stocks: [{ code: '000021', name: '深科技' }, { code: '600584', name: '长电科技' }],
                            topics: [{ name: '半导体', match: 'industry', stock_count: 120 }],
                        },
                        {
                            title: '海外并购估值承压',
                            time: '2026-06-08 23:20:00',
                            source: '东方财富快讯',
                            sentiment: -0.35,
                            stocks: [{ code: '600584', name: '长电科技' }],
                        },
                        {
                            title: '宏观数据平稳',
                            time: '2026-06-08 23:10:00',
                            source: '东方财富快讯',
                            sentiment: 0.05,
                            stocks: [],
                        },
                    ],
                };
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));

        (async () => {
            await Intelligence.loadNews();
            assert.equal(String(count.textContent), '3');
            assert.match(list.innerHTML, /价值摘要/);
            assert.match(list.innerHTML, /关联新闻 2\/3 条/);
            assert.match(list.innerHTML, /关联股票 2 只/);
            assert.match(list.innerHTML, /主题 3 个/);
            assert.match(list.innerHTML, /情绪 正1 中1 负1/);
            assert.match(list.innerHTML, /深科技/);
            assert.match(list.innerHTML, /长电科技/);
            assert.match(list.innerHTML, /半导体/);
            assert.doesNotMatch(list.innerHTML, /undefined/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_news_shows_partial_source_errors_when_news_is_available():
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

        const list = makeElement('intel-news-list');
        const count = makeElement('intel-news-count');
        const elements = {
            'intel-news-list': list,
            'intel-news-count': count,
        };

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
                assert.equal(url, '/api/market/news');
                return {
                    success: true,
                    timestamp: '2026-06-09T17:48:39',
                    generated_at: '2026-06-09T17:48:41',
                    source: 'market_news_multi_source',
                    coverage_note: '多源市场新闻聚合：东方财富快讯',
                    partial_errors: [
                        'stock_zh_a_alerts_cls: timeout',
                        'news_cctv: service unavailable',
                    ],
                    news: [
                        {
                            title: '算力硬件方向活跃',
                            time: '2026-06-09 17:30:00',
                            source: '东方财富快讯',
                            sentiment: 0.3,
                            value_score: 4.5,
                            value_reasons: ['关联主题'],
                        },
                    ],
                };
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));

        (async () => {
            await Intelligence.loadNews();
            assert.equal(String(count.textContent), '1');
            assert.match(list.innerHTML, /新闻源 市场新闻聚合/);
            assert.match(list.innerHTML, /展示 1 条/);
            assert.match(list.innerHTML, /部分新闻源异常 2 个/);
            assert.match(list.innerHTML, /stock_zh_a_alerts_cls: timeout/);
            assert.match(list.innerHTML, /news_cctv: service unavailable/);
            assert.match(list.innerHTML, /算力硬件方向活跃/);
            assert.doesNotMatch(list.innerHTML, /undefined/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_news_tags_render_as_actionable_controls():
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

        const list = makeElement('intel-news-list');
        const count = makeElement('intel-news-count');
        const elements = {
            'intel-news-list': list,
            'intel-news-count': count,
        };

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
                assert.equal(url, '/api/market/news');
                return {
                    success: true,
                    timestamp: '2026-06-08T23:55:00',
                    source: 'market_news_multi_source',
                    news: [
                        {
                            title: '存储芯片价格上涨',
                            time: '2026-06-08 23:30:00',
                            source: '东方财富快讯',
                            sentiment: 0.4,
                            stocks: [{ code: '000021', name: '深科技' }],
                            topics: [{ name: '半导体', match: 'industry', stock_count: 120 }],
                        },
                    ],
                };
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));

        (async () => {
            await Intelligence.loadNews();
            assert.match(list.innerHTML, /<button[^>]+type="button"[^>]+data-intel-action="open-news-stock"/);
            assert.match(list.innerHTML, /data-code="000021"/);
            assert.match(list.innerHTML, /data-name="深科技"/);
            assert.match(list.innerHTML, /aria-label="打开深科技详情"/);
            assert.match(list.innerHTML, /title="打开深科技详情"/);
            assert.match(list.innerHTML, /<button[^>]+type="button"[^>]+data-intel-action="query-hotspot"/);
            assert.match(list.innerHTML, /data-concept="半导体"/);
            assert.match(list.innerHTML, /data-source="intelligence:news-topic"/);
            assert.match(list.innerHTML, /aria-label="用问财检索半导体"/);
            assert.match(list.innerHTML, /title="用问财检索半导体"/);
            assert.doesNotMatch(list.innerHTML, /<span class="intel-news-tag/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_news_renders_actionable_topic_clusters():
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

        const list = makeElement('intel-news-list');
        const count = makeElement('intel-news-count');
        const elements = {
            'intel-news-list': list,
            'intel-news-count': count,
        };

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
                assert.equal(url, '/api/market/news');
                return {
                    success: true,
                    timestamp: '2026-06-08T23:55:00',
                    source: 'market_news_multi_source',
                    news: [
                        {
                            title: '存储芯片价格上涨',
                            time: '2026-06-08 23:30:00',
                            source: '东方财富快讯',
                            sentiment: 0.6,
                            stocks: [{ code: '000021', name: '深科技' }, { code: '600584', name: '长电科技' }],
                            topics: [{ name: '半导体', match: 'industry', stock_count: 120 }],
                        },
                        {
                            title: '先进封装订单升温',
                            time: '2026-06-08 23:20:00',
                            source: '东方财富快讯',
                            sentiment: 0.2,
                            stocks: [{ code: '600584', name: '长电科技' }],
                            topics: [{ name: '半导体', match: 'concept' }, { name: '先进封装', match: 'concept' }],
                        },
                        {
                            title: '券商并购预期升温',
                            time: '2026-06-08 23:10:00',
                            source: '东方财富快讯',
                            sentiment: -0.4,
                            stocks: [{ code: '601059', name: '信达证券' }],
                            topics: [{ name: '证券', match: 'industry' }],
                        },
                    ],
                };
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));

        (async () => {
            await Intelligence.loadNews();
            assert.equal(String(count.textContent), '3');
            assert.match(list.innerHTML, /可行动主题/);
            assert.match(list.innerHTML, /class="intel-news-topic-board"/);
            assert.match(list.innerHTML, /半导体/);
            assert.match(list.innerHTML, /2条新闻/);
            assert.match(list.innerHTML, /2只股票/);
            assert.match(list.innerHTML, /情绪 \+0\.40/);
            assert.match(list.innerHTML, /存储芯片价格上涨/);
            assert.match(list.innerHTML, /先进封装/);
            assert.match(list.innerHTML, /证券/);
            assert.match(list.innerHTML, /<button[^>]+class="intel-topic-card-title"[^>]+data-intel-action="query-hotspot"[^>]+data-concept="半导体"/);
            assert.match(list.innerHTML, /<button[^>]+class="intel-topic-stock"[^>]+data-intel-action="open-news-stock"[^>]+data-code="600584"[^>]*>长电科技<\/button>/);
            assert.doesNotMatch(list.innerHTML, /undefined/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_news_topic_board_refreshes_with_ai_signal_overlap_without_refetching_news():
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
                querySelector: () => null,
            };
        }

        const list = makeElement('intel-news-list');
        const count = makeElement('intel-news-count');
        const signalPanel = makeElement('intel-ml-pred');
        const elements = {
            'intel-news-list': list,
            'intel-news-count': count,
            'intel-ml-pred': signalPanel,
        };
        const calls = [];

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
                calls.push(url);
                if (url === '/api/market/news') {
                    return {
                        success: true,
                        timestamp: '2026-06-08T15:30:00',
                        source: 'market_news_multi_source',
                        news: [
                            {
                                title: '半导体先进封装订单回暖',
                                time: '2026-06-08 15:20:00',
                                source: '东方财富快讯',
                                sentiment: 0.62,
                                stocks: [
                                    { code: '600584', name: '长电科技' },
                                    { code: '000021', name: '深科技' },
                                ],
                                topics: [{ name: '半导体' }, { name: '先进封装' }],
                            },
                            {
                                title: '机器人产业链催化延续',
                                time: '2026-06-08 15:10:00',
                                source: '财联社',
                                sentiment: 0.35,
                                stocks: [{ code: '002747', name: '埃斯顿' }],
                                topics: [{ name: '机器人' }],
                            },
                        ],
                    };
                }
                if (url === '/api/signals/top?limit=50') {
                    return {
                        success: true,
                        date: '2026-06-05',
                        total: 5197,
                        provider: 'local_momentum',
                        model_version: 'local_momentum_v1',
                        signals: [
                            { code: '600584', name: '长电科技', score: 0.914, price: 31.2, amount: 120000000, signal_confidence: 'validated_positive' },
                        ],
                    };
                }
                if (url === '/api/signals/validation?top_n=50') {
                    return { success: true, confidence: 'validated_positive', sample_days: 30, metrics: { '1d': {} } };
                }
                throw new Error(`unexpected url: ${url}`);
            },
            toast: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));
        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-signals.js', 'utf8'));

        (async () => {
            await Intelligence.loadNews();
            assert.deepEqual(calls, ['/api/market/news']);
            assert.match(list.innerHTML, /class="intel-news-topic-board"/);
            assert.match(list.innerHTML, /半导体/);
            assert.doesNotMatch(list.innerHTML, /AI覆盖/);

            await Intelligence.loadMLPredictions();
            assert.deepEqual(calls, ['/api/market/news', '/api/signals/top?limit=50']);
            assert.match(list.innerHTML, /信号重叠 1只 · 待验证/);
            assert.match(list.innerHTML, /class="intel-topic-ai-badge"/);
            assert.match(list.innerHTML, /data-ai-score="0\.914"/);
            assert.match(list.innerHTML, /长电科技<span class="intel-topic-stock-ai">信号 0\.914<\/span>/);
            assert.match(list.innerHTML, /title="打开长电科技详情，AI候选信号分0\.914，待历史验证"/);
            assert.doesNotMatch(list.innerHTML, /深科技<span class="intel-topic-stock-ai"/);
            assert.doesNotMatch(list.innerHTML, /AI信号分0\.914/);
            assert.equal(calls.filter((url) => url === '/api/market/news').length, 1);

            await Intelligence.state.signalValidationLoadingPromise;
            assert.match(list.innerHTML, /信号重叠 1只 · 验证偏正/);
            assert.match(list.innerHTML, /title="打开长电科技详情，AI候选信号分0\.914，验证偏正"/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_news_topic_board_keeps_unverified_signal_overlap_out_of_ai_coverage():
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
                querySelector: () => null,
            };
        }

        const list = makeElement('intel-news-list');
        const signalPanel = makeElement('intel-ml-pred');
        const elements = {
            'intel-news-list': list,
            'intel-news-count': makeElement('intel-news-count'),
            'intel-ml-pred': signalPanel,
        };

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
                if (url === '/api/market/news') {
                    return {
                        success: true,
                        timestamp: '2026-06-08T15:30:00',
                        source: 'market_news_multi_source',
                        news: [
                            {
                                title: '半导体先进封装订单回暖',
                                time: '2026-06-08 15:20:00',
                                source: '东方财富快讯',
                                sentiment: 0.62,
                                stocks: [{ code: '600584', name: '长电科技' }],
                                topics: [{ name: '半导体' }],
                            },
                        ],
                    };
                }
                if (url === '/api/signals/top?limit=50') {
                    return {
                        success: true,
                        date: '2026-06-05',
                        total: 5197,
                        provider: 'local_momentum',
                        model_version: 'local_momentum_v1',
                        signals: [
                            { code: '600584', name: '长电科技', score: 0.914, price: 31.2, signal_confidence: 'unverified' },
                        ],
                    };
                }
                if (url === '/api/signals/validation?top_n=50') {
                    return { success: true, confidence: 'validated_neutral', sample_days: 1, metrics: { '1d': {} } };
                }
                throw new Error(`unexpected url: ${url}`);
            },
            toast: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));
        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-signals.js', 'utf8'));

        (async () => {
            await Intelligence.loadNews();
            await Intelligence.loadMLPredictions();
            assert.match(list.innerHTML, /信号重叠 1只 · 待验证/);
            assert.match(list.innerHTML, /长电科技<span class="intel-topic-stock-ai">信号 0\.914<\/span>/);
            assert.match(list.innerHTML, /新闻主题: 半导体 · 信号重叠 1只 · 待验证/);
            assert.doesNotMatch(list.innerHTML, /AI覆盖/);
            assert.doesNotMatch(list.innerHTML, /AI信号分/);

            await Intelligence.state.signalValidationLoadingPromise;
            assert.match(list.innerHTML, /信号重叠 1只 · 样本不足/);
            assert.doesNotMatch(list.innerHTML, /AI覆盖/);
            assert.doesNotMatch(list.innerHTML, /AI信号分/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_news_topic_board_can_send_ai_prioritized_pool_to_screener():
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
                querySelector: () => null,
            };
        }

        const listeners = {};
        const emitted = [];
        const list = makeElement('intel-news-list');
        const count = makeElement('intel-news-count');
        const signalPanel = makeElement('intel-ml-pred');
        const elements = {
            'intel-news-list': list,
            'intel-news-count': count,
            'intel-ml-pred': signalPanel,
        };
        const calls = [];

        global.window = global;
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: () => null,
            addEventListener: (event, handler) => { listeners[event] = handler; },
        };
        global.App = {
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
            fetchJSON: async (url) => {
                calls.push(url);
                if (url === '/api/market/news') {
                    return {
                        success: true,
                        timestamp: '2026-06-08T15:30:00',
                        source: 'market_news_multi_source',
                        news: [
                            {
                                title: '半导体先进封装订单回暖',
                                time: '2026-06-08 15:20:00',
                                source: '东方财富快讯',
                                sentiment: 0.62,
                                stocks: [
                                    { code: '000021', name: '深科技' },
                                    { code: '600584', name: '长电科技' },
                                ],
                                topics: [{ name: '半导体' }, { name: '先进封装' }],
                            },
                            {
                                title: '半导体设备订单扩张',
                                time: '2026-06-08 15:10:00',
                                source: '财联社',
                                sentiment: 0.35,
                                stocks: [{ code: '688012', name: '中微公司' }],
                                topics: [{ name: '半导体' }],
                            },
                        ],
                    };
                }
                if (url === '/api/signals/top?limit=50') {
                    return {
                        success: true,
                        date: '2026-06-05',
                        total: 5197,
                        provider: 'local_momentum',
                        model_version: 'local_momentum_v1',
                        signals: [
                            { code: '600584', name: '长电科技', score: 0.914, signal_confidence: 'validated_positive' },
                        ],
                    };
                }
                if (url === '/api/signals/validation?top_n=50') {
                    return { success: true, confidence: 'validated_positive', sample_days: 30, metrics: { '1d': {} } };
                }
                throw new Error(`unexpected url: ${url}`);
            },
            emit: (event, payload) => { emitted.push({ event, payload }); },
            toast: () => {},
            registerContext: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence.js', 'utf8'));
        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));
        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-signals.js', 'utf8'));

        (async () => {
            Intelligence.bindDelegatedActions();
            await Intelligence.loadNews();
            await Intelligence.loadMLPredictions();
            await Intelligence.state.signalValidationLoadingPromise;

            assert.match(list.innerHTML, /data-intel-action="send-topic-screener"/);
            assert.match(list.innerHTML, /data-concept="半导体"/);
            assert.match(list.innerHTML, /data-pool="600584,000021,688012"/);
            assert.match(list.innerHTML, /新闻主题: 半导体 · 信号重叠 1只 · 验证偏正/);
            assert.equal(calls.filter((url) => url === '/api/market/news').length, 1);

            const sendButton = {
                dataset: {
                    concept: '半导体',
                    pool: '600584,000021,688012',
                    query: '新闻主题: 半导体 · 信号重叠 1只 · 验证偏正',
                },
                closest: (selector) => selector === '[data-intel-action="send-topic-screener"]' ? sendButton : null,
            };
            let prevented = 0;
            listeners.click({
                target: sendButton,
                preventDefault: () => { prevented += 1; },
            });

            assert.equal(prevented, 1);
            assert.deepEqual(emitted, [
                {
                    event: 'iwencai:send-to-screener',
                    payload: {
                        pool: ['600584', '000021', '688012'],
                        query: '新闻主题: 半导体 · 信号重叠 1只 · 验证偏正',
                        source_context: {
                            source: 'intelligence:news-topic-board',
                            sourceLabel: '新闻主题',
                            context_type: 'news_topic',
                            concept: '半导体',
                            raw_query: '半导体',
                            query: '新闻主题: 半导体 · 信号重叠 1只 · 验证偏正',
                            action: 'send_screener',
                            result_pool_id: 'intelligence:news-topic-board:半导体',
                            rank_reason: '新闻主题: 半导体 · 信号重叠 1只 · 验证偏正',
                            result_total: 3,
                            candidate_codes: ['600584', '000021', '688012'],
                        },
                    },
                },
            ]);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_news_topic_board_clears_ai_overlap_when_signal_pool_is_empty():
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
                querySelector: () => null,
            };
        }

        const list = makeElement('intel-news-list');
        const signalPanel = makeElement('intel-ml-pred');
        const elements = {
            'intel-news-list': list,
            'intel-news-count': makeElement('intel-news-count'),
            'intel-ml-pred': signalPanel,
        };
        const calls = [];
        let signalCall = 0;

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
                calls.push(url);
                if (url === '/api/market/news') {
                    return {
                        success: true,
                        timestamp: '2026-06-08T15:30:00',
                        source: 'market_news_multi_source',
                        news: [
                            {
                                title: '半导体先进封装订单回暖',
                                time: '2026-06-08 15:20:00',
                                source: '东方财富快讯',
                                sentiment: 0.62,
                                stocks: [{ code: '600584', name: '长电科技' }],
                                topics: [{ name: '半导体' }],
                            },
                        ],
                    };
                }
                if (url === '/api/signals/top?limit=50') {
                    signalCall += 1;
                    return signalCall === 1
                        ? {
                            success: true,
                            date: '2026-06-05',
                            total: 5197,
                            provider: 'local_momentum',
                            model_version: 'local_momentum_v1',
                            signals: [
                                { code: '600584', name: '长电科技', score: 0.914, signal_confidence: 'validated_positive' },
                            ],
                        }
                        : {
                            success: true,
                            date: '2026-06-06',
                            total: 5197,
                            provider: 'local_momentum',
                            model_version: 'local_momentum_v1',
                            signals: [],
                        };
                }
                if (url === '/api/signals/validation?top_n=50') {
                    return { success: true, confidence: 'validated_positive', sample_days: 30, metrics: { '1d': {} } };
                }
                throw new Error(`unexpected url: ${url}`);
            },
            toast: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));
        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-signals.js', 'utf8'));

        (async () => {
            await Intelligence.loadNews();
            await Intelligence.loadMLPredictions();
            assert.match(list.innerHTML, /信号重叠 1只 · 待验证/);
            await Intelligence.state.signalValidationLoadingPromise;

            await Intelligence.loadMLPredictions();
            assert.match(signalPanel.innerHTML, /暂无信号数据/);
            assert.doesNotMatch(list.innerHTML, /AI覆盖/);
            assert.doesNotMatch(list.innerHTML, /intel-topic-stock-ai/);
            assert.equal(calls.filter((url) => url === '/api/market/news').length, 1);
            assert.equal(Intelligence.state.signalTopIndex.size, 0);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_delegated_news_actions_keep_research_context():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const listeners = {};
        const opened = [];
        const emitted = [];

        global.window = global;
        global.document = {
            addEventListener: (event, handler) => { listeners[event] = handler; },
            getElementById: () => null,
            querySelector: () => null,
        };
        global.App = {
            openStockDetail: (code, options) => { opened.push({ code, options }); },
            emit: (event, payload) => { emitted.push({ event, payload }); },
            registerContext: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence.js', 'utf8'));
        Intelligence.bindDelegatedActions();

        let prevented = 0;
        const stockTag = {
            dataset: { code: '000021', name: '深科技' },
            closest: (selector) => selector === '[data-intel-action="open-news-stock"]' ? stockTag : null,
        };
        listeners.click({
            target: stockTag,
            preventDefault: () => { prevented += 1; },
        });

        const topicTag = {
            dataset: { concept: '半导体', source: 'intelligence:news-topic' },
            closest: (selector) => {
                if (selector === '[data-intel-action="open-news-stock"]') return null;
                if (selector === '[data-intel-action="query-hotspot"]') return topicTag;
                return null;
            },
        };
        listeners.click({
            target: topicTag,
            preventDefault: () => { prevented += 1; },
        });

        assert.equal(prevented, 2);
        assert.deepEqual(opened, [
            { code: '000021', options: { source: 'intelligence:news-tag', name: '深科技' } },
        ]);
        assert.deepEqual(emitted, [
            {
                event: 'hotspot:query-iwencai',
                payload: {
                    concept: '半导体',
                    source: 'intelligence:news-topic',
                    source_context: {
                        source: 'intelligence:news-topic',
                        sourceLabel: '新闻主题',
                        context_type: 'news_topic',
                        concept: '半导体',
                        raw_query: '半导体',
                        query: '半导体',
                        action: 'query_iwencai',
                        result_pool_id: 'intelligence:news-topic:半导体',
                        rank_reason: '新闻主题: 半导体',
                    },
                },
            },
        ]);
    """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_signal_pool_renders_validation_summary():
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
                querySelector: () => null,
            };
        }

        const panel = makeElement('intel-ml-pred');
        const elements = { 'intel-ml-pred': panel };
        const calls = [];

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
                calls.push(url);
                if (url === '/api/signals/top?limit=50') {
                    return {
                        success: true,
                        date: '2026-06-05',
                        total: 5197,
                        provider: 'local_momentum',
                        model_version: 'local_momentum_v1',
                        raw_source: 'legacy_qlib',
                        generated_at: '2026-06-07T12:30:00',
                        signals: [
                            { code: '600519', name: '贵州茅台', score: 0.91, price: 1600, amount: 100000000, signal_confidence: 'validated_positive' },
                            { code: '000001', name: '平安银行', score: 0.75, price: 12.3, amount: 80000000, signal_confidence: 'validated_positive' },
                        ],
                    };
                }
                if (url === '/api/signals/validation?top_n=50') {
                    return {
                        success: true,
                        confidence: 'validated_positive',
                        sample_days: 42,
                        metrics: {
                            '1d': {
                                top_excess_return_pct: 1.23,
                                hit_rate_pct: 58.6,
                                rank_ic: 0.071,
                            },
                        },
                    };
                }
                throw new Error(`unexpected url: ${url}`);
            },
            toast: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-signals.js', 'utf8'));

        (async () => {
            await Intelligence.loadMLPredictions();
            assert.deepEqual(calls, ['/api/signals/top?limit=50']);
            assert.match(panel.innerHTML, /AI 信号池/);
            assert.match(panel.innerHTML, /Top 50 历史回测摘要/);
            assert.match(panel.innerHTML, /状态 未验证/);
            assert.match(panel.innerHTML, /历史验证后台更新中/);

            await Intelligence.state.signalValidationLoadingPromise;
            assert.deepEqual(calls, ['/api/signals/top?limit=50', '/api/signals/validation?top_n=50']);
            assert.match(panel.innerHTML, /样本 42 天/);
            assert.match(panel.innerHTML, /Top超额 \+1\.23%/);
            assert.match(panel.innerHTML, /胜率 58\.6%/);
            assert.match(panel.innerHTML, /Rank IC 0\.071/);
            assert.match(panel.innerHTML, /状态 验证偏正/);
            assert.match(panel.innerHTML, /可信口径/);
            assert.match(panel.innerHTML, /来源 本地动量信号/);
            assert.match(panel.innerHTML, /模型 基线动量模型/);
            assert.doesNotMatch(panel.innerHTML, /local_momentum/);
            assert.doesNotMatch(panel.innerHTML, /local_momentum_v1/);
            assert.match(panel.innerHTML, /兼容缓存 历史兼容信号缓存/);
            assert.doesNotMatch(panel.innerHTML, /legacy_qlib/);
            assert.doesNotMatch(panel.innerHTML, /历史预测缓存/);
            assert.match(panel.innerHTML, /覆盖 5,197 只/);
            assert.match(panel.innerHTML, /展示 Top 2/);
            assert.match(panel.innerHTML, /生成 2026-06-07T12:30:00/);
            assert.match(panel.innerHTML, /验证样本 42 天/);
            assert.match(panel.innerHTML, /池级状态 验证偏正/);
            assert.match(panel.innerHTML, /<td class="qlib-td qlib-td-ic" title="仅代表 Top 50 信号池历史验证，不代表单股验证">池级非单股<\/td>/);
            assert.doesNotMatch(panel.innerHTML, /title="历史验证偏正"/);
            assert.doesNotMatch(panel.innerHTML, /qlib-diamond/);
            assert.doesNotMatch(panel.innerHTML, /<td class="qlib-td qlib-td-ic">验证偏正<\/td>/);
            assert.doesNotMatch(panel.innerHTML, /<td class="qlib-td qlib-td-ic">池级验证<\/td>/);
            assert.match(panel.innerHTML, /信号日期: 2026-06-05/);
            assert.doesNotMatch(panel.innerHTML, /qlib LightGBM/i);
            assert.doesNotMatch(panel.innerHTML, /暂无预测数据/);
            assert.doesNotMatch(panel.innerHTML, />validated_positive</);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_signal_pool_warns_when_provider_validation_sample_is_tiny():
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
                querySelector: () => null,
            };
        }

        const panel = makeElement('intel-ml-pred');
        const elements = { 'intel-ml-pred': panel };

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
                if (url === '/api/signals/top?limit=50') {
                    return {
                        success: true,
                        date: '2026-06-05',
                        total: 5197,
                        provider: 'local_momentum',
                        model_version: 'local_momentum_v1',
                        raw_source: 'legacy_qlib',
                        predictions: [
                            { code: '600519', name: '贵州茅台', score: 0.91, price: 1600, signal_confidence: 'unverified' },
                        ],
                    };
                }
                if (url === '/api/signals/validation?top_n=50') {
                    return {
                        success: true,
                        confidence: 'validated_neutral',
                        sample_days: 1,
                        metrics: { '1d': { top_excess_return_pct: 0.0, hit_rate_pct: 13.3, rank_ic: -0.329 } },
                    };
                }
                throw new Error(`unexpected url: ${url}`);
            },
            toast: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-signals.js', 'utf8'));

        (async () => {
            await Intelligence.loadMLPredictions();
            await Intelligence.state.signalValidationLoadingPromise;

            assert.match(panel.innerHTML, /全市场 5,197 只 · Top 1 · 样本不足/);
            assert.match(panel.innerHTML, /池级验证样本不足/);
            assert.match(panel.innerHTML, /样本 1\/20 天/);
            assert.match(panel.innerHTML, /仅供观察，不适合作为交易依据/);
            assert.match(panel.innerHTML, /Top超额 \+0\.00%/);
            assert.match(panel.innerHTML, /Rank IC -0\.329/);
            assert.match(panel.innerHTML, /<td class="qlib-td qlib-td-ic" title="单条信号尚未通过独立历史验证">未验证<\/td>/);
            assert.doesNotMatch(panel.innerHTML, /<td class="qlib-td qlib-td-ic">验证中性<\/td>/);
            assert.doesNotMatch(panel.innerHTML, /qlib-diamond/);
            assert.match(panel.innerHTML, /信号排名前5%/);
            assert.match(panel.innerHTML, /候选分/);
            assert.doesNotMatch(panel.innerHTML, /强动能/);
            assert.doesNotMatch(panel.innerHTML, /预测力/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_signal_pool_rows_show_pool_level_validation_without_single_stock_claim():
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
                querySelector: () => null,
            };
        }

        const panel = makeElement('intel-ml-pred');
        const elements = { 'intel-ml-pred': panel };

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
                if (url === '/api/signals/top?limit=50') {
                    return {
                        success: true,
                        date: '2026-06-05',
                        total: 5197,
                        provider: 'local_momentum',
                        model_version: 'local_momentum_v1',
                        raw_source: 'legacy_qlib',
                        predictions: [
                            { code: '600519', name: '贵州茅台', score: 0.91, price: 1600, signal_confidence: 'unverified' },
                        ],
                    };
                }
                if (url === '/api/signals/validation?top_n=50') {
                    return {
                        success: true,
                        confidence: 'validated_neutral',
                        sample_days: 259,
                        metrics: { '1d': { top_excess_return_pct: 0.16, hit_rate_pct: 48, rank_ic: -0.038 } },
                    };
                }
                throw new Error(`unexpected url: ${url}`);
            },
            toast: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-signals.js', 'utf8'));

        (async () => {
            await Intelligence.loadMLPredictions();
            assert.match(panel.innerHTML, /全市场 5,197 只 · Top 1 · 未验证/);
            assert.match(panel.innerHTML, /状态 未验证/);
            assert.match(panel.innerHTML, /<td class="qlib-td qlib-td-ic" title="单条信号尚未通过独立历史验证">未验证<\/td>/);

            await Intelligence.state.signalValidationLoadingPromise;
            assert.match(panel.innerHTML, /全市场 5,197 只 · Top 1 · 验证中性/);
            assert.match(panel.innerHTML, /池级状态 验证中性/);
            assert.match(panel.innerHTML, /<td class="qlib-td qlib-td-ic" title="仅代表 Top 50 信号池历史验证，不代表单股验证">池级非单股<\/td>/);
            assert.doesNotMatch(panel.innerHTML, /<td class="qlib-td qlib-td-ic">验证中性<\/td>/);
            assert.doesNotMatch(panel.innerHTML, /<td class="qlib-td qlib-td-ic">未验证<\/td>/);
            assert.doesNotMatch(panel.innerHTML, /<td class="qlib-td qlib-td-ic">池级验证<\/td>/);
            assert.doesNotMatch(panel.innerHTML, /title="信号池已通过历史验证"/);
            assert.doesNotMatch(panel.innerHTML, /qlib-diamond/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_signal_pool_rows_keep_table_shape_when_industry_is_missing():
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
                querySelector: () => null,
            };
        }

        const panel = makeElement('intel-ml-pred');
        const elements = { 'intel-ml-pred': panel };

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
                if (url === '/api/signals/top?limit=50') {
                    return {
                        success: true,
                        date: '2026-06-05',
                        total: 5197,
                        provider: 'local_momentum',
                        model_version: 'local_momentum_v1',
                        signals: [
                            { code: '600519', name: '贵州茅台', industry: '', score: 0.91, price: '1600.50', amount: '100000000', signal_confidence: 'validated_positive' },
                            { code: '000001', name: '平安银行', score: 0.75, price: 12.3, amount: 80000000, signal_confidence: 'validated_positive' },
                        ],
                    };
                }
                if (url === '/api/signals/validation?top_n=50') {
                    return { success: true, confidence: 'validated_positive', sample_days: 42, metrics: { '1d': {} } };
                }
                throw new Error(`unexpected url: ${url}`);
            },
            toast: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-signals.js', 'utf8'));

        (async () => {
            await Intelligence.loadMLPredictions();
            await Intelligence.state.signalValidationLoadingPromise;

            const body = panel.innerHTML;
            const rows = body.match(/<tr class="qlib-row[\s\S]*?<\/tr>/g) || [];
            assert.equal(rows.length, 2);
            for (const row of rows) {
                assert.equal((row.match(/<td class="qlib-td/g) || []).length, 9);
            }
            assert.match(body, /<span class="qlib-industry-tag muted">行业未标注<\/span>/);
            assert.match(body, /data-industry="行业未标注"/);
            assert.match(body, /行业标注 0\/2/);
            assert.match(body, /行业缺失 2 只/);
            assert.match(body, /1600\.50/);
            assert.doesNotMatch(body, /<span class="qlib-industry-tag">--<\/span>/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_signal_pool_prefers_sector_for_compact_industry_label():
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
                querySelector: () => null,
            };
        }

        const panel = makeElement('intel-ml-pred');
        global.window = global;
        global.document = {
            getElementById: (id) => id === 'intel-ml-pred' ? panel : null,
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
                if (url === '/api/signals/top?limit=50') {
                    return {
                        success: true,
                        date: '2026-06-05',
                        total: 5197,
                        provider: 'local_momentum',
                        model_version: 'local_momentum_v1',
                        signals: [{
                            code: '600396',
                            name: '华电辽能',
                            industry: '电力、热力、燃气及水生产和供应业-电力、热力生产和供应业',
                            sector: '电力',
                            score: 0.91,
                            signal_confidence: 'unverified',
                        }],
                    };
                }
                if (url === '/api/signals/validation?top_n=50') {
                    return { success: true, confidence: 'unverified', sample_days: 0, metrics: { '1d': {} } };
                }
                throw new Error(`unexpected url: ${url}`);
            },
            toast: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-signals.js', 'utf8'));

        (async () => {
            await Intelligence.loadMLPredictions();

            const body = panel.innerHTML;
            assert.match(body, /<span class="qlib-industry-tag" title="电力、热力、燃气及水生产和供应业-电力、热力生产和供应业">电力<\/span>/);
            assert.match(body, /data-industry="电力"/);
            assert.doesNotMatch(body, />电力、热力、/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_signal_pool_uses_specific_industry_segment_when_sector_missing():
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
                querySelector: () => null,
            };
        }

        const panel = makeElement('intel-ml-pred');
        global.window = global;
        global.document = {
            getElementById: (id) => id === 'intel-ml-pred' ? panel : null,
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
                if (url === '/api/signals/top?limit=50') {
                    return {
                        success: true,
                        date: '2026-06-05',
                        total: 5197,
                        provider: 'local_momentum',
                        model_version: 'local_momentum_v1',
                        signals: [{
                            code: '688146',
                            name: '中船特气',
                            industry: '制造业-计算机、通信和其他电子设备制造业',
                            score: 0.91,
                            signal_confidence: 'unverified',
                        }],
                    };
                }
                if (url === '/api/signals/validation?top_n=50') {
                    return { success: true, confidence: 'unverified', sample_days: 0, metrics: { '1d': {} } };
                }
                throw new Error(`unexpected url: ${url}`);
            },
            toast: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-signals.js', 'utf8'));

        (async () => {
            await Intelligence.loadMLPredictions();

            const body = panel.innerHTML;
            assert.match(body, /title="制造业-计算机、通信和其他电子设备制造业">计算机、通信<\/span>/);
            assert.match(body, /data-industry="计算机、通信"/);
            assert.doesNotMatch(body, />制造业<\/span>/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_signal_pool_compacts_supply_industry_without_mid_word_cutoff():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const panel = { innerHTML: '', addEventListener: () => {}, querySelector: () => null };
        global.window = global;
        global.document = {
            getElementById: (id) => id === 'intel-ml-pred' ? panel : null,
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
                if (url === '/api/signals/top?limit=50') {
                    return {
                        success: true,
                        date: '2026-06-05',
                        total: 5197,
                        provider: 'local_momentum',
                        model_version: 'local_momentum_v1',
                        signals: [{
                            code: '600396',
                            name: '华电辽能',
                            industry: '电力、热力、燃气及水生产和供应业-电力、热力生产和供应业',
                            score: 0.91,
                            signal_confidence: 'unverified',
                        }],
                    };
                }
                if (url === '/api/signals/validation?top_n=50') {
                    return { success: true, confidence: 'unverified', sample_days: 0, metrics: { '1d': {} } };
                }
                throw new Error(`unexpected url: ${url}`);
            },
            toast: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-signals.js', 'utf8'));

        (async () => {
            await Intelligence.loadMLPredictions();

            const body = panel.innerHTML;
            assert.match(body, /title="电力、热力、燃气及水生产和供应业-电力、热力生产和供应业">电力、热力生产供应<\/span>/);
            assert.doesNotMatch(body, />电力、热力生产和<\/span>/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_signal_pool_first_paint_does_not_request_slow_validation():
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
                querySelector: () => null,
            };
        }

        const panel = makeElement('intel-ml-pred');
        const elements = { 'intel-ml-pred': panel };
        const calls = [];

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
                calls.push(url);
                if (url === '/api/signals/validation?top_n=50') {
                    await new Promise(() => {});
                }
                if (url === '/api/signals/top?limit=50') {
                    return {
                        success: true,
                        date: '2026-06-05',
                        total: 5197,
                        provider: 'local_momentum',
                        model_version: 'local_momentum_v1',
                        raw_source: 'legacy_qlib',
                        generated_at: '2026-06-07T12:30:00',
                        predictions: [
                            { code: '600519', name: '贵州茅台', score: 0.91, price: 1600, signal_confidence: 'unverified' },
                        ],
                    };
                }
                throw new Error(`unexpected url: ${url}`);
            },
            toast: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-signals.js', 'utf8'));

        (async () => {
            const result = await Promise.race([
                Intelligence.loadMLPredictions().then(() => 'loaded'),
                new Promise((resolve) => setTimeout(() => resolve('timeout'), 25)),
            ]);
            assert.equal(result, 'loaded');
            assert.deepEqual(calls, ['/api/signals/top?limit=50']);
            assert.match(panel.innerHTML, /AI 信号池/);
            assert.match(panel.innerHTML, /状态 未验证/);
            assert.doesNotMatch(panel.innerHTML, /预测加载失败/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_load_does_not_block_market_modules_on_slow_signal_pool():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        global.window = global;
        global.document = {
            readyState: 'complete',
            addEventListener: () => {},
            getElementById: () => null,
        };
        global.__AUTH_GATE_REQUIRED__ = false;
        global.App = {
            registerContext: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence.js', 'utf8'));

        const calls = [];
        let resolveSignal;
        Intelligence.loadSentiment = async () => calls.push('sentiment');
        Intelligence.loadNews = async () => calls.push('news');
        Intelligence.loadHeatmap = async () => calls.push('heatmap');
        Intelligence.loadHotspot = async () => calls.push('hotspot');
        Intelligence.loadMLPredictions = async () => {
            calls.push('signals:start');
            await new Promise((resolve) => { resolveSignal = resolve; });
            calls.push('signals:done');
        };
        Intelligence.loadSignalBar = async () => calls.push('signalBar');

        (async () => {
            const result = await Intelligence.load();
            assert.deepEqual(result.map((item) => item.status), ['fulfilled', 'fulfilled', 'fulfilled', 'fulfilled']);
            assert.ok(calls.includes('sentiment'));
            assert.ok(calls.includes('news'));
            assert.ok(calls.includes('heatmap'));
            assert.ok(calls.includes('hotspot'));
            assert.ok(calls.includes('signals:start'));
            assert.equal(Intelligence.state.marketLoaded, true);
            assert.equal(Intelligence.state.loaded, false);

            resolveSignal();
            await Intelligence.state.backgroundLoadingPromise;
            assert.ok(calls.includes('signals:done'));
            assert.equal(Intelligence.state.loaded, true);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_load_retries_real_sentiment_failure_after_error_state():
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

        const sentiment = makeElement('intel-sentiment');
        const elements = { 'intel-sentiment': sentiment };
        let breadthCalls = 0;

        global.window = global;
        global.document = {
            readyState: 'complete',
            addEventListener: () => {},
            getElementById: (id) => elements[id] || null,
            querySelector: () => null,
        };
        global.__AUTH_GATE_REQUIRED__ = false;
        global.App = {
            registerContext: () => {},
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
            fetchJSON: async (url) => {
                if (url !== '/api/market/breadth') {
                    throw new Error(`unexpected url: ${url}`);
                }
                breadthCalls += 1;
                if (breadthCalls === 1) {
                    throw new Error('请求超时');
                }
                return {
                    success: true,
                    source: 'local_stock_daily',
                    stock_count: 5525,
                    effective_count: 5515,
                    up_count: 2982,
                    down_count: 2089,
                    flat_count: 124,
                    limit_up: 96,
                    limit_down: 19,
                    latest_date: '2026-06-05',
                };
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence.js', 'utf8'));
        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));

        (async () => {
            const first = await Intelligence.load();
            assert.equal(first[0].status, 'rejected');
            assert.equal(Intelligence.state.loadedModules.sentiment, undefined);
            assert.equal(Intelligence.state.marketLoaded, false);
            assert.match(sentiment.innerHTML, /加载失败/);

            const second = await Intelligence.load();
            assert.equal(second[0].status, 'fulfilled');
            assert.equal(breadthCalls, 2);
            assert.equal(Intelligence.state.loadedModules.sentiment, true);
            assert.equal(Intelligence.state.marketLoaded, true);
            assert.match(sentiment.innerHTML, /上涨/);
            assert.doesNotMatch(sentiment.innerHTML, /加载失败/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_load_retries_failed_signal_pool_after_market_modules_succeed():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        global.window = global;
        global.document = {
            readyState: 'complete',
            addEventListener: () => {},
            getElementById: () => null,
        };
        global.__AUTH_GATE_REQUIRED__ = false;
        global.App = {
            registerContext: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence.js', 'utf8'));

        let newsCalls = 0;
        let signalCalls = 0;
        Intelligence.loadNews = async () => {
            newsCalls += 1;
        };
        Intelligence.loadMLPredictions = async () => {
            signalCalls += 1;
            if (signalCalls === 1) {
                throw new Error('temporary signal failure');
            }
        };

        (async () => {
            const first = await Intelligence.load();
            await Intelligence.state.backgroundLoadingPromise;
            assert.deepEqual(first.map((item) => item.status), ['fulfilled']);
            assert.equal(Intelligence.state.marketLoaded, true);
            assert.equal(Intelligence.state.loaded, false);
            assert.equal(signalCalls, 1);

            const second = await Intelligence.load();
            await Intelligence.state.backgroundLoadingPromise;
            assert.deepEqual(second.map((item) => item.status), []);
            assert.equal(signalCalls, 2);
            assert.equal(newsCalls, 1);
            assert.equal(Intelligence.state.loaded, true);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_load_runs_late_market_loader_after_bundle_attaches_it():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        global.window = global;
        global.document = {
            readyState: 'complete',
            addEventListener: () => {},
            getElementById: () => null,
        };
        global.__AUTH_GATE_REQUIRED__ = false;
        global.App = {
            registerContext: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence.js', 'utf8'));

        const calls = [];
        Intelligence.loadSentiment = async () => calls.push('sentiment');
        Intelligence.loadNews = async () => calls.push('news');
        Intelligence.loadHotspot = async () => calls.push('hotspot');

        (async () => {
            const first = await Intelligence.load();
            assert.deepEqual(first.map((item) => item.status), ['fulfilled', 'fulfilled', 'fulfilled']);
            assert.equal(Intelligence.state.marketLoaded, true);
            assert.equal(Intelligence.state.loadedModules.heatmap, undefined);
            assert.deepEqual(calls, ['sentiment', 'news', 'hotspot']);

            Intelligence.loadHeatmap = async () => calls.push('heatmap');
            const second = await Intelligence.load();

            assert.deepEqual(second.map((item) => item.status), ['fulfilled']);
            assert.ok(calls.includes('heatmap'));
            assert.equal(Intelligence.state.loadedModules.heatmap, true);
            assert.equal(Intelligence.state.marketLoaded, true);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_market_bundle_wakes_active_intelligence_page_after_late_attach():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id) {
            return {
                id,
                innerHTML: '<div class="skeleton-block skeleton-pulse"></div>',
                textContent: '',
                dataset: {},
                offsetWidth: 720,
                classList: {
                    _classes: new Set(id === 'tab-intelligence' ? ['active'] : []),
                    contains(name) { return this._classes.has(name); },
                    add(name) { this._classes.add(name); },
                    remove(name) { this._classes.delete(name); },
                    toggle(name, force) {
                        if (force === true) this._classes.add(name);
                        else if (force === false) this._classes.delete(name);
                        else if (this._classes.has(name)) this._classes.delete(name);
                        else this._classes.add(name);
                    },
                },
                addEventListener: () => {},
                querySelector: () => null,
            };
        }

        const heatmap = makeElement('intel-heatmap');
        const tab = makeElement('tab-intelligence');
        const elements = { 'intel-heatmap': heatmap, 'tab-intelligence': tab };
        const calls = [];

        global.window = global;
        global.document = {
            readyState: 'complete',
            addEventListener: () => {},
            getElementById: (id) => elements[id] || null,
            querySelector: (selector) => {
                if (selector === '.nav-link.active') return { dataset: { tab: 'intelligence' } };
                return null;
            },
        };
        global.__AUTH_GATE_REQUIRED__ = false;
        global.App = {
            currentTab: 'intelligence',
            registerContext: () => {},
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
            fetchJSON: async (url) => {
                calls.push(url);
                if (url !== '/api/market/heatmap?fast=true') {
                    return { success: true, news: [], hot_concepts: [] };
                }
                return {
                    success: true,
                    local_fallback: true,
                    source: 'local_stock_daily',
                    universe: 'local_stock_daily_coverage_pool',
                    generated_at: '2026-06-10T09:30:00',
                    total: 1,
                    up_count: 1,
                    down_count: 0,
                    flat_count: 0,
                    avg_change_pct: 1.2,
                    sectors: [
                        { name: '银行', change_pct: 1.2, stock_count: 42, up_count: 41, down_count: 1, leader: '平安银行' },
                    ],
                };
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence.js', 'utf8'));
        Intelligence.loadSentiment = async () => {};
        Intelligence.loadNews = async () => {};
        Intelligence.loadHotspot = async () => {};

        (async () => {
            await Intelligence.load();
            assert.equal(Intelligence.state.marketLoaded, true);
            assert.equal(Intelligence.state.loadedModules.heatmap, undefined);
            assert.deepEqual(calls, []);
            assert.match(heatmap.innerHTML, /skeleton-block/);

            vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));
            await Intelligence.state.marketBundleWakePromise;

            assert.ok(calls.includes('/api/market/heatmap?fast=true'));
            assert.equal(Intelligence.state.loadedModules.heatmap, true);
            assert.equal(Intelligence.state.marketLoaded, true);
            assert.match(heatmap.innerHTML, /intel-market-entry-map/);
            assert.match(heatmap.innerHTML, /intel-treemap-tile/);
            assert.doesNotMatch(heatmap.innerHTML, /skeleton-block/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_market_bundle_wakes_when_intelligence_tab_becomes_active_later():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id, active = false) {
            return {
                id,
                innerHTML: '<div class="skeleton-block skeleton-pulse"></div>',
                textContent: '',
                dataset: {},
                offsetWidth: 720,
                classList: {
                    _classes: new Set(active ? ['active'] : []),
                    contains(name) { return this._classes.has(name); },
                    add(name) { this._classes.add(name); },
                    remove(name) { this._classes.delete(name); },
                    toggle(name, force) {
                        if (force === true) this._classes.add(name);
                        else if (force === false) this._classes.delete(name);
                        else if (this._classes.has(name)) this._classes.delete(name);
                        else this._classes.add(name);
                    },
                },
                addEventListener: () => {},
                querySelector: () => null,
            };
        }

        const eventHandlers = {};
        const heatmap = makeElement('intel-heatmap');
        const tab = makeElement('tab-intelligence', false);
        const elements = { 'intel-heatmap': heatmap, 'tab-intelligence': tab };
        const calls = [];

        global.window = global;
        global.addEventListener = (event, handler) => {
            (eventHandlers[event] ||= []).push(handler);
        };
        global.dispatchEvent = (event) => {
            for (const handler of eventHandlers[event.type] || []) handler(event);
        };
        global.Event = class Event {
            constructor(type) { this.type = type; }
        };
        global.document = {
            readyState: 'complete',
            addEventListener: () => {},
            getElementById: (id) => elements[id] || null,
            querySelector: (selector) => {
                if (selector === '.nav-link.active') return { dataset: { tab: 'overview' } };
                return null;
            },
        };
        global.__AUTH_GATE_REQUIRED__ = false;
        global.App = {
            currentTab: 'overview',
            registerContext: () => {},
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
            fetchJSON: async (url) => {
                calls.push(url);
                assert.equal(url, '/api/market/heatmap?fast=true');
                return {
                    success: true,
                    local_fallback: true,
                    source: 'local_stock_daily',
                    universe: 'local_stock_daily_coverage_pool',
                    generated_at: '2026-06-10T09:30:00',
                    total: 1,
                    up_count: 1,
                    down_count: 0,
                    flat_count: 0,
                    avg_change_pct: 1.2,
                    sectors: [
                        { name: '银行', change_pct: 1.2, stock_count: 42, up_count: 41, down_count: 1, leader: '平安银行' },
                    ],
                };
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence.js', 'utf8'));
        Intelligence.loadSentiment = async () => {};
        Intelligence.loadNews = async () => {};
        Intelligence.loadHotspot = async () => {};

        (async () => {
            await Intelligence.load();
            assert.equal(Intelligence.state.marketLoaded, true);
            assert.equal(Intelligence.state.loadedModules.heatmap, undefined);

            vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));
            assert.equal(Intelligence.state.marketBundleWakePromise, undefined);
            assert.deepEqual(calls, []);

            App.currentTab = 'intelligence';
            tab.classList.add('active');
            document.querySelector = (selector) => {
                if (selector === '.nav-link.active') return { dataset: { tab: 'intelligence' } };
                return null;
            };
            window.dispatchEvent(new Event('aiq:intelligence-tab-active'));
            await Intelligence.state.marketBundleWakePromise;

            assert.ok(calls.includes('/api/market/heatmap?fast=true'));
            assert.equal(Intelligence.state.loadedModules.heatmap, true);
            assert.match(heatmap.innerHTML, /intel-market-entry-map/);
            assert.doesNotMatch(heatmap.innerHTML, /skeleton-block/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_market_bundle_wake_does_not_depend_on_general_loader_retry():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id) {
            return {
                id,
                innerHTML: '<div class="skeleton-block skeleton-pulse"></div>',
                textContent: '',
                dataset: {},
                offsetWidth: 720,
                classList: {
                    contains: (name) => name === 'active',
                    add: () => {},
                    remove: () => {},
                    toggle: () => {},
                },
                addEventListener: () => {},
                querySelector: () => null,
            };
        }

        const heatmap = makeElement('intel-heatmap');
        const elements = { 'intel-heatmap': heatmap, 'tab-intelligence': makeElement('tab-intelligence') };
        const calls = [];

        global.window = global;
        global.addEventListener = () => {};
        global.document = {
            readyState: 'complete',
            addEventListener: () => {},
            getElementById: (id) => elements[id] || null,
            querySelector: (selector) => {
                if (selector === '.nav-link.active') return { dataset: { tab: 'intelligence' } };
                return null;
            },
        };
        global.__AUTH_GATE_REQUIRED__ = false;
        global.App = {
            currentTab: 'intelligence',
            registerContext: () => {},
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
            fetchJSON: async (url) => {
                calls.push(url);
                assert.equal(url, '/api/market/heatmap?fast=true');
                return {
                    success: true,
                    local_fallback: true,
                    source: 'local_stock_daily',
                    generated_at: '2026-06-10T09:30:00',
                    total: 1,
                    up_count: 1,
                    down_count: 0,
                    flat_count: 0,
                    avg_change_pct: 1.2,
                    sectors: [
                        { name: '银行', change_pct: 1.2, stock_count: 42, up_count: 41, down_count: 1, leader: '平安银行' },
                    ],
                };
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence.js', 'utf8'));
        Intelligence.state.loadedModules = { sentiment: true, news: true, hotspot: true };
        Intelligence.state.marketLoaded = false;
        Intelligence.state.loadingPromise = Promise.resolve([]);
        Intelligence.load = async () => {
            calls.push('general-load');
            return [];
        };

        (async () => {
            vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));
            await Intelligence.state.marketBundleWakePromise;

            assert.ok(calls.includes('/api/market/heatmap?fast=true'));
            assert.equal(calls.includes('general-load'), false);
            assert.equal(Intelligence.state.loadedModules.heatmap, true);
            assert.equal(Intelligence.state.marketLoaded, true);
            assert.equal(Intelligence.state.marketBundleWakePromise, null);
            assert.match(heatmap.innerHTML, /intel-market-entry-map/);
            assert.doesNotMatch(heatmap.innerHTML, /skeleton-block/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_hotspot_retries_once_after_transient_failure():
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
        let calls = 0;

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
                calls += 1;
                if (calls === 1) {
                    throw new Error('请求超时');
                }
                return {
                    success: true,
                    timestamp: '2026-05-26 10:30:00',
                    partial_errors: ['concept', 'industry', 'fund_flow'],
                    summary: '暂无热点数据',
                    hot_concepts: [],
                    hot_industries: [],
                    fund_flow: [],
                };
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));

        (async () => {
            await Intelligence.loadHotspot();
            assert.equal(calls, 2);
            assert.match(hotspot.innerHTML, /暂无热点数据/);
            assert.match(hotspot.innerHTML, /数据源异常/);
            assert.match(hotspot.innerHTML, /暂无数据/);
            assert.doesNotMatch(hotspot.innerHTML, /加载失败/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_hotspot_source_unavailable_shows_trust_context():
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
                    source: 'hotspot_attribution',
                    provider: 'hotspot_attribution',
                    source_unavailable: true,
                    stale: true,
                    stale_reason: 'hotspot_source_unavailable',
                    generated_at: '2026-06-10T10:00:00',
                    timestamp: '2026-06-10T10:00:00',
                    coverage_note: '热点归因源不可用，当前无可用热点数据',
                    partial_errors: ['hotspot unavailable'],
                    summary: '暂无热点数据',
                    hot_concepts: [],
                    hot_industries: [],
                    fund_flow: [],
                };
            },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-market.js', 'utf8'));

        (async () => {
            await Intelligence.loadHotspot();
            assert.match(hotspot.innerHTML, /暂无热点数据/);
            assert.match(hotspot.innerHTML, /热点归因/);
            assert.match(hotspot.innerHTML, /数据源异常/);
            assert.match(hotspot.innerHTML, /热点归因源不可用/);
            assert.match(hotspot.innerHTML, /2026-06-10T10:00:00/);
            assert.match(hotspot.innerHTML, /暂无数据/);
            assert.doesNotMatch(hotspot.innerHTML, /加载失败/);
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

    assert "/static/intelligence.js?v=17" in app_js
    assert "/static/intelligence-market.js?v=27" in app_js
    assert "/static/intelligence-iwencai.js?v=14" in app_js
    assert "/static/intelligence-signals.js?v=20" in app_js
    assert "/static/intelligence-qlib.js" not in app_js
    assert "/static/app.js?v=133" in scripts
    assert "/static/core/command-palette.js?v=2" in scripts
    assert "/static/app-ui-shell.js?v=45" in scripts
    assert "/sw.js?v=74" in app_ui_shell
    assert "ai-quant-v181" in service_worker
    static_assets_body = service_worker.split("const STATIC_ASSETS = [", 1)[1].split("];", 1)[0]
    assert "/static/intelligence-signals.js" not in static_assets_body
    assert "/static/intelligence-qlib.js" not in service_worker
    assert ".intel-treemap" in styles
    assert ".intel-market-entry-map" in styles
    assert ".intel-sector-members" in styles
    assert ".intel-sector-members-head > div" in styles
    assert ".intel-sector-evidence" in styles
    assert ".intel-sector-evidence-grid" in styles
    assert ".intel-sector-evidence-section" in styles
    assert ".intel-sector-evidence-tags" in styles
    assert ".intel-sector-evidence-action-row" in styles
    assert "overflow-wrap: anywhere" in styles
    assert "grid-template-columns: repeat(auto-fit, minmax(min(178px, 100%), 1fr))" in styles
    assert ".intel-sector-evidence-grid {\n        grid-template-columns: 1fr;" in styles
    assert ".intel-sector-member-row" in styles
    assert ".intel-hotspot-status" in styles
    assert ".intel-hotspot-evidence" in styles
    assert ".intel-sent-meta" in styles
    assert "grid-template-columns: minmax(0, 35fr) minmax(0, 65fr)" in styles
    assert ".intel-right-top" in styles and "grid-template-columns: repeat(2, minmax(0, 1fr))" in styles
    assert ".intel-hotspot-card" in styles and ".intel-heatmap-card" in styles
    assert ".intel-hotspot-summary" in styles and "overflow-wrap: anywhere" in styles
    assert ".intel-news-meta" in styles and "flex-wrap: wrap" in styles
    assert ".intel-news-tag:hover" in styles
    assert ".intel-news-topic-board" in styles
    assert "grid-template-columns: repeat(auto-fit, minmax(min(220px, 100%), 1fr))" in styles
    assert ".intel-topic-stock" in styles


def test_legacy_intelligence_qlib_asset_uses_signal_wording_only():
    legacy_asset = Path("dashboard/static/intelligence-qlib.js").read_text(encoding="utf-8")

    assert "Legacy intelligence qlib shim" in legacy_asset
    assert "loadBundleForPage?.('signals')" in legacy_asset
    assert "async loadMLPredictions()" not in legacy_asset
    assert "Object.assign(Intelligence" not in legacy_asset
    assert "qlib-diamond" not in legacy_asset
    assert "信号已通过历史验证" not in legacy_asset
    assert "validated_positive" not in legacy_asset
    assert "qlib LightGBM" not in legacy_asset
    assert "暂无预测数据" not in legacy_asset
    assert "预测加载失败" not in legacy_asset
    assert "历史预测缓存" not in legacy_asset
    assert "强动能" not in legacy_asset
    assert "中动能" not in legacy_asset
    assert "弱动能" not in legacy_asset


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
            assert.doesNotMatch(result.innerHTML, /class="stock-link iwencai-code"/);
            assert.doesNotMatch(result.innerHTML, /data-code="605066\.SH"/);
            assert.doesNotMatch(result.innerHTML, />605066\.SH</);
            assert.match(result.innerHTML, /天正电气/);
            assert.match(result.innerHTML, /\+10\.03%/);
            assert.match(result.innerHTML, /1\.16亿/);
            assert.match(result.innerHTML, /智能电网/);
            assert.doesNotMatch(result.innerHTML, /MARKET_CODE/);
            assert.match(result.innerHTML, /未验证/);
            assert.match(result.innerHTML, /legacy 响应未提供候选行级证据/);
            assert.deepEqual(Intelligence.state.iwencaiActionState.pool, []);
            assert.equal(Intelligence.state.iwencaiActionState.candidates[0].code, '605066');
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_iwencai_renders_task_router_conditions_buckets_and_source_context():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id) {
            return {
                id,
                value: '高股息 低估值 近5日放量',
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
            fetchJSON: async () => ({
                success: true,
                schema_version: 'iwencai_task_router_v1',
                query: '高股息 低估值 近5日放量',
                selected_bucket: 'candidates',
                status: 'partial_result',
                total: 137,
                intent: { type: 'natural_language_screener', confidence: 0.86, reason: '多条件自然语言选股' },
                parsed_conditions: [
                    {
                        raw_text: '高股息',
                        field: '股息率',
                        op: 'rank',
                        value: '高',
                        window: 'latest',
                        status: 'ready',
                        evidence: { hit_count: 473, hit_count_status: 'verified', evidence_level: 'provider_field', source_field: '股息率' },
                    },
                    { raw_text: '低估值', field: '估值', op: 'low', value: '低', window: 'latest', hit_count: 583, hit_count_status: 'verified', source_field: '市盈率', status: 'ready' },
                    {
                        raw_text: '近5日放量',
                        field: '成交量',
                        op: 'volume_up',
                        value: '放量',
                        window: '5d',
                        status: 'degraded_data',
                        evidence: { hit_count: null, hit_count_status: 'missing_source_field', missing_reason: '结果字段中缺少可验证该条件的来源字段', evidence_level: 'none' },
                    },
                ],
                buckets: [
                    {
                        id: 'candidates',
                        name: '候选股票',
                        count: 137,
                        items: [
                            {
                                code: '600000',
                                name: '浦发银行',
                                price: 8.5,
                                change_pct: 1.2,
                                industry: '银行-股份制银行',
                                concept: '高股息;低估值',
                            },
                        ],
                    },
                    { id: 'themes', name: '板块主题', count: 2, items: [{ name: '银行', description: '高股息集中' }] },
                ],
                actions: [
                    { id: 'open_stock', enabled: true },
                    { id: 'analyze', enabled: true },
                ],
                data: [
                    {
                        '股票代码': '600000.SH',
                        '股票简称': '浦发银行',
                        '最新价': 8.5,
                        '最新涨跌幅': 1.2,
                        '所属同花顺行业': '银行-股份制银行',
                        '所属概念': '高股息;低估值',
                        '市盈率': 5.2,
                    },
                ],
                source_status: {
                    provider: 'backend-iwencai',
                    status: 'partial',
                    data_as_of: '2026-06-12T09:30:00+08:00',
                    cache_status: 'fresh',
                },
                provider_evidence: {
                    schema_version: 'iwencai_provider_evidence_v1',
                    summary_status: 'partial',
                    field_coverage_status: 'partial',
                    write_actions_allowed: false,
                    candidate_validation: { verified: 0, partial: 1, unverified: 0, missing: 0, actionable: 0 },
                    condition_status_counts: { verified: 2, missing_source_field: 1 },
                    blocked_write_actions: ['create_basket', 'draft_backtest'],
                    degradation: { type: 'partial_source_failure', reason: '部分条件缺少可验证字段' },
                },
                source_context: {
                    result_pool_id: 'iwencai:test-pool',
                    provider: 'backend-iwencai',
                    data_as_of: '2026-06-12T09:30:00+08:00',
                    cache_status: 'fresh',
                    data_status: 'partial',
                },
            }),
            on: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-iwencai.js', 'utf8'));

        (async () => {
            await Intelligence.runIwencai({
                source_context: {
                    source: 'global_search',
                    result_pool_id: 'origin-pool',
                    provider: 'origin-provider',
                    data_as_of: 'old',
                    cache_status: 'cached',
                },
            });
            assert.match(result.innerHTML, /问财任务路由/);
            assert.match(result.innerHTML, /natural_language_screener/);
            assert.match(result.innerHTML, /置信度 86%/);
            assert.match(result.innerHTML, /高股息/);
            assert.match(result.innerHTML, /473 只/);
            assert.match(result.innerHTML, /源字段 股息率/);
            assert.match(result.innerHTML, /结果字段中缺少可验证该条件的来源字段/);
            assert.match(result.innerHTML, /data-bucket-id="themes"/);
            assert.doesNotMatch(result.innerHTML, /data-bucket-id="news"/);
            assert.doesNotMatch(result.innerHTML, /等待新闻\/公告证据接入/);
            assert.doesNotMatch(result.innerHTML, /data-intel-action="iwencai-create-basket"/);
            assert.doesNotMatch(result.innerHTML, /data-intel-action="iwencai-draft-backtest"/);
            assert.match(result.innerHTML, /浦发银行/);
            assert.match(result.innerHTML, /data-code="600000"/);
            assert.equal(Intelligence.state.iwencaiActionState.source_context.intent_type, 'natural_language_screener');
            assert.equal(Intelligence.state.iwencaiActionState.source_context.selected_bucket, 'candidates');
            assert.equal(Intelligence.state.iwencaiActionState.source_context.result_pool_id, 'iwencai:test-pool');
            assert.equal(Intelligence.state.iwencaiActionState.source_context.provider, 'backend-iwencai');
            assert.equal(Intelligence.state.iwencaiActionState.source_context.data_as_of, '2026-06-12T09:30:00+08:00');
            assert.equal(Intelligence.state.iwencaiActionState.source_context.cache_status, 'fresh');
            assert.equal(Intelligence.state.iwencaiActionState.source_context.origin_context.result_pool_id, 'origin-pool');
            assert.equal(Intelligence.state.iwencaiActionState.source_context.condition_evidence['高股息'].source_field, '股息率');
            assert.equal(Intelligence.state.iwencaiActionState.source_context.condition_evidence['近5日放量'].hit_count_status, 'missing_source_field');
            assert.equal(Intelligence.state.iwencaiActionState.source_context.parsed_conditions[0].evidence_level, 'provider_field');
            assert.equal(Intelligence.state.iwencaiActionState.provider_evidence.summary_status, 'partial');
            assert.equal(Intelligence.state.iwencaiActionState.provider_evidence.write_actions_allowed, false);
            assert.equal(Intelligence.state.iwencaiActionState.source_context.provider_evidence.field_coverage_status, 'partial');
            assert.equal(Intelligence.state.iwencaiActionState.contextList[0].sourceLabel, '问财');

            Intelligence.selectIwencaiBucket('themes');
            assert.match(result.innerHTML, /银行/);
            assert.equal(Intelligence.state.iwencaiActionState.source_context.selected_bucket, 'themes');
            assert.equal(Intelligence.state.iwencaiActionState.source_context.result_pool_id, 'iwencai:test-pool');
            assert.equal(Intelligence.state.iwencaiActionState.source_context.provider, 'backend-iwencai');
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_iwencai_backend_empty_schema_does_not_fallback_to_frontend_inference():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        global.window = global;
        global.document = {
            getElementById: () => null,
            querySelector: () => null,
            addEventListener: () => {},
            readyState: 'loading',
        };
        global.App = {
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-iwencai.js', 'utf8'));

        const viewModel = Intelligence._buildIwencaiTaskViewModel({
            success: true,
            schema_version: 'iwencai_task_router_v1',
            status: 'no_match',
            total: 0,
            data: [],
            parsed_conditions: [],
            buckets: [
                { id: 'candidates', name: '候选股票', status: 'no_match', count: 0, items: [] },
            ],
            actions: [{ id: 'open_stock', enabled: false }],
            source_context: { result_pool_id: 'backend-empty-pool' },
        }, '高股息低估值近5日放量');

        assert.deepEqual(viewModel.parsed_conditions, []);
        assert.deepEqual(viewModel.buckets.map((bucket) => bucket.id), ['candidates']);
        assert.equal(viewModel.actions.length, 0);
        assert.equal(viewModel.source_context.result_pool_id, 'backend-empty-pool');
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_iwencai_fallback_parser_splits_no_space_chinese_conditions():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        global.window = global;
        global.document = {
            getElementById: () => null,
            querySelector: () => null,
            addEventListener: () => {},
            readyState: 'loading',
        };
        global.App = {
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-iwencai.js', 'utf8'));

        const viewModel = Intelligence._buildIwencaiTaskViewModel({
            success: true,
            total: 2,
            data: [
                { '股票代码': '600000.SH', '股票简称': '浦发银行' },
                { '股票代码': '000001.SZ', '股票简称': '平安银行' },
            ],
        }, '高股息低估值近5日放量');

        assert.deepEqual(viewModel.parsed_conditions.map((item) => item.raw_text), ['高股息', '低估值', '近5日放量']);
        assert.deepEqual(viewModel.parsed_conditions.map((item) => item.field), ['股息率', '估值', '成交量']);
        assert.equal(viewModel.parsed_conditions[2].window, '5d');
        assert.equal(viewModel.source_context.rank_reason, '问财条件: 高股息 / 低估值 / 近5日放量');
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_iwencai_actions_gate_rendering_and_click_handlers():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        let clickHandler = null;
        function makeElement(id) {
            return {
                id,
                value: '高股息低估值近5日放量',
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

        const emitted = [];
        let opened = null;
        let addAllCalled = false;
        global.window = global;
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: () => null,
            addEventListener: (event, handler) => {
                if (event === 'click') clickHandler = handler;
            },
            readyState: 'complete',
        };
        global.App = {
            registerContext: () => {},
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
            fetchJSON: async () => ({
                success: true,
                total: 1,
                actions: ['open_stock'],
                data: [{ '股票代码': '600000.SH', '股票简称': '浦发银行' }],
            }),
            emit: (event, payload) => emitted.push({ event, payload }),
            openStockDetail: (code, options) => { opened = { code, options }; },
            addAllToWatchlist: () => { addAllCalled = true; },
            on: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-iwencai.js', 'utf8'));
        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence.js', 'utf8'));

        (async () => {
            await Intelligence.runIwencai();
            assert.match(result.innerHTML, /data-intel-action="iwencai-open-stock"/);
            assert.doesNotMatch(result.innerHTML, /data-intel-action="iwencai-create-basket"/);
            assert.doesNotMatch(result.innerHTML, /data-intel-action="iwencai-draft-backtest"/);
            assert.doesNotMatch(result.innerHTML, /data-intel-action="iwencai-analyze"/);
            assert.doesNotMatch(result.innerHTML, /data-intel-action="iwencai-add-watchlist"/);

            const blockedBasket = {
                dataset: {},
                closest: (selector) => selector === '[data-intel-action="iwencai-create-basket"]' ? blockedBasket : null,
            };
            clickHandler({ target: blockedBasket, preventDefault: () => {} });
            assert.equal(emitted.length, 0);

            const blockedAnalyze = {
                dataset: {},
                closest: (selector) => selector === '[data-intel-action="iwencai-analyze"]' ? blockedAnalyze : null,
            };
            clickHandler({ target: blockedAnalyze, preventDefault: () => {} });
            assert.equal(emitted.length, 0);
            assert.equal(addAllCalled, false);

            const openButton = {
                dataset: { code: '600000' },
                closest: (selector) => selector === '[data-intel-action="iwencai-open-stock"]' ? openButton : null,
            };
            clickHandler({ target: openButton, preventDefault: () => {} });
            assert.equal(opened.code, '600000');
            assert.equal(opened.options.source_context.result_pool_id.startsWith('iwencai:'), true);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_iwencai_open_stock_action_preserves_task_router_source_context():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        let clickHandler = null;
        let opened = null;
        global.window = global;
        global.document = {
            getElementById: () => null,
            querySelector: () => null,
            addEventListener: (event, handler) => {
                if (event === 'click') clickHandler = handler;
            },
            readyState: 'complete',
        };
        global.App = {
            registerContext: () => {},
            escapeHTML: (value) => String(value ?? ''),
            openStockDetail: (code, options) => { opened = { code, options }; },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-iwencai.js', 'utf8'));
        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence.js', 'utf8'));

        Intelligence.state.iwencaiActionState = {
            query: '高股息 低估值 近5日放量',
            source_context: {
                source: 'iwencai',
                sourceLabel: '问财',
                context_type: 'iwencai',
                intent_type: 'natural_language_screener',
                selected_bucket: 'candidates',
                result_pool_id: 'iwencai:test-pool',
                rank_reason: '问财条件: 高股息 / 低估值 / 近5日放量',
                parsed_conditions: [{ raw_text: '高股息', hit_count: 473 }],
            },
            contextList: [
                { code: '600000', name: '浦发银行', sourceLabel: '问财', context_type: 'iwencai' },
                { code: '000001', name: '平安银行', sourceLabel: '问财', context_type: 'iwencai' },
            ],
            candidates: [
                { code: '600000', name: '浦发银行', price: 8.5, changePct: 1.2 },
            ],
        };

        const button = {
            dataset: { code: '600000' },
            closest: (selector) => selector === '[data-intel-action="iwencai-open-stock"]' ? button : null,
        };
        clickHandler({
            target: button,
            preventDefault: () => {},
        });

        assert.equal(opened.code, '600000');
        assert.equal(opened.options.source, 'iwencai');
        assert.equal(opened.options.sourceLabel, '问财');
        assert.equal(opened.options.context_type, 'iwencai');
        assert.equal(opened.options.query, '高股息 低估值 近5日放量');
        assert.equal(opened.options.contextList.length, 2);
        assert.equal(opened.options.source_context.intent_type, 'natural_language_screener');
        assert.equal(opened.options.source_context.result_pool_id, 'iwencai:test-pool');
        assert.equal(opened.options.preferDirectOpen, true);
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_iwencai_candidate_row_provenance_renders_and_flows_to_actions():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id) {
            return {
                id,
                value: '高股息 低估值 放量',
                innerHTML: '',
                textContent: '',
                classList: { add: () => {}, remove: () => {}, toggle: () => {} },
                addEventListener: () => {},
            };
        }

        let clickHandler = null;
        let opened = null;
        let watchlistPayload = null;
        const emitted = [];
        const input = makeElement('intel-iwencai-input');
        const result = makeElement('intel-iwencai-result');
        const elements = {
            'intel-iwencai-input': input,
            'intel-iwencai-btn': makeElement('intel-iwencai-btn'),
            'intel-iwencai-result': result,
        };

        const verifiedProvenance = {
            result_pool_id: 'iwencai:row-test',
            row_id: 'iwencai:row-test:row:verified',
            code: '600000',
            name: '浦发银行',
            rank: 1,
            provider: 'iwencai',
            data_as_of: '2026-06-12T09:30:00+08:00',
            cache_status: 'live_request',
            validation_status: 'verified',
            evidence_level: 'provider_field',
            matched_conditions: [
                { raw_text: '高股息', field: '股息率', source_field: '股息率', value: '5.1', evidence_level: 'provider_field' },
                { raw_text: '低估值', field: '估值', source_field: '市盈率', value: '5.2', evidence_level: 'provider_field' },
            ],
            missing_conditions: [],
            source_fields: [
                { field: '股息率', value: '5.1', condition: '高股息' },
                { field: '市盈率', value: '5.2', condition: '低估值' },
            ],
        };
        const partialProvenance = {
            result_pool_id: 'iwencai:row-test',
            row_id: 'iwencai:row-test:row:partial',
            code: '000001',
            name: '平安银行',
            rank: 2,
            provider: 'iwencai',
            data_as_of: '2026-06-12T09:30:00+08:00',
            cache_status: 'live_request',
            validation_status: 'partial',
            evidence_level: 'partial_provider_field',
            matched_conditions: [
                { raw_text: '低估值', field: '估值', source_field: '市盈率', value: '6.3', evidence_level: 'provider_field' },
            ],
            missing_conditions: [
                { raw_text: '高股息', field: '股息率', hit_count_status: 'missing_row_value', missing_reason: '该候选行缺少可验证的条件字段取值' },
            ],
            source_fields: [
                { field: '市盈率', value: '6.3', condition: '低估值' },
            ],
            missing_reason: '该候选行缺少可验证的条件字段取值',
        };

        global.window = global;
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: () => null,
            addEventListener: (event, handler) => {
                if (event === 'click') clickHandler = handler;
            },
            readyState: 'complete',
        };
        global.App = {
            registerContext: () => {},
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
            fetchJSON: async () => ({
                success: true,
                status: 'result_ready',
                total: 2,
                actions: ['open_stock', 'add_watchlist', 'send_screener', 'analyze', 'ask_ai', 'create_basket', 'draft_backtest'],
                data: [
                    { '股票代码': '600000.SH', '股票简称': '浦发银行', '股息率': 5.1, '市盈率': 5.2, candidate_provenance: verifiedProvenance },
                    { '股票代码': '000001.SZ', '股票简称': '平安银行', '股息率': '', '市盈率': 6.3, candidate_provenance: partialProvenance },
                ],
                buckets: [
                    {
                        id: 'candidates',
                        name: '候选股票',
                        count: 2,
                        items: [
                            { code: '600000', name: '浦发银行', candidate_provenance: verifiedProvenance },
                            { code: '000001', name: '平安银行', candidate_provenance: partialProvenance },
                        ],
                    },
                ],
                parsed_conditions: [
                    { raw_text: '高股息', field: '股息率', hit_count: 1, hit_count_status: 'verified', source_field: '股息率', source_fields: ['股息率'], status: 'ready' },
                    { raw_text: '低估值', field: '估值', hit_count: 2, hit_count_status: 'verified', source_field: '市盈率', source_fields: ['市盈率'], status: 'ready' },
                ],
                source_context: {
                    source: 'global_search',
                    sourceLabel: '全局搜索',
                    context_type: 'iwencai',
                    result_pool_id: 'iwencai:row-test',
                    provider: 'iwencai',
                    data_as_of: '2026-06-12T09:30:00+08:00',
                    cache_status: 'live_request',
                    data_status: 'ok',
                },
            }),
            emit: (event, payload) => emitted.push({ event, payload }),
            openStockDetail: (code, options) => { opened = { code, options }; },
            addToWatchlist: (code, options) => { watchlistPayload = { code, options }; },
            on: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-iwencai.js', 'utf8'));
        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence.js', 'utf8'));

        (async () => {
            const viewModel = await Intelligence.runIwencai();
            assert.match(result.innerHTML, /已验证/);
            assert.match(result.innerHTML, /部分验证/);
            assert.match(result.innerHTML, /源字段 股息率 \/ 市盈率/);
            assert.match(result.innerHTML, /该候选行缺少可验证的条件字段取值/);
            assert.doesNotMatch(result.innerHTML, />undefined</);
            assert.deepEqual(Intelligence.state.iwencaiActionState.pool, ['600000']);
            assert.deepEqual(Intelligence.state.iwencaiActionState.watchlistCodes, ['600000']);
            assert.equal(Intelligence.state.iwencaiActionState.excludedCandidates[0].code, '000001');
            assert.equal(viewModel.contextList[0].source_context.row_evidence.validation_status, 'verified');
            assert.equal(viewModel.contextList[1].source_context.row_evidence.validation_status, 'partial');
            assert.equal(Intelligence.state.iwencaiActionState.requestGeneration, 1);
            assert.equal(Intelligence.state.iwencaiActionState.source_context.request_generation, 1);
            assert.match(result.innerHTML, /data-request-generation="1"/);

            const openButton = {
                dataset: { code: '600000', resultPoolId: 'iwencai:row-test', rowEvidenceId: 'iwencai:row-test:row:verified', requestGeneration: '1' },
                closest: (selector) => selector === '[data-intel-action="iwencai-open-stock"]' ? openButton : null,
            };
            clickHandler({ target: openButton, preventDefault: () => {} });
            assert.equal(opened.code, '600000');
            assert.equal(opened.options.source_context.row_evidence.validation_status, 'verified');
            assert.equal(opened.options.source_context.row_evidence_id, 'iwencai:row-test:row:verified');

            const staleButton = {
                dataset: { code: '600000', resultPoolId: 'iwencai:old-pool', rowEvidenceId: 'iwencai:old-pool:row:old' },
                closest: (selector) => selector === '[data-intel-action="iwencai-add-one-watchlist"]' ? staleButton : null,
            };
            clickHandler({ target: staleButton, preventDefault: () => {} });
            assert.equal(watchlistPayload, null);

            const addVerified = {
                dataset: { code: '600000', resultPoolId: 'iwencai:row-test', rowEvidenceId: 'iwencai:row-test:row:verified', requestGeneration: '1' },
                closest: (selector) => selector === '[data-intel-action="iwencai-add-one-watchlist"]' ? addVerified : null,
            };
            clickHandler({ target: addVerified, preventDefault: () => {} });
            assert.equal(watchlistPayload.code, '600000');
            assert.equal(watchlistPayload.options.metadata.row_evidence.validation_status, 'verified');

            const oldGenerationWatchlist = {
                dataset: { code: '600000', resultPoolId: 'iwencai:row-test', rowEvidenceId: 'iwencai:row-test:row:verified', requestGeneration: '999' },
                closest: (selector) => selector === '[data-intel-action="iwencai-add-one-watchlist"]' ? oldGenerationWatchlist : null,
            };
            watchlistPayload = null;
            clickHandler({ target: oldGenerationWatchlist, preventDefault: () => {} });
            assert.equal(watchlistPayload, null);

            const addPartial = {
                dataset: { code: '000001', resultPoolId: 'iwencai:row-test', rowEvidenceId: 'iwencai:row-test:row:partial' },
                closest: (selector) => selector === '[data-intel-action="iwencai-add-one-watchlist"]' ? addPartial : null,
            };
            watchlistPayload = null;
            clickHandler({ target: addPartial, preventDefault: () => {} });
            assert.equal(watchlistPayload, null);

            const askPartial = {
                dataset: { code: '000001', resultPoolId: 'iwencai:row-test', rowEvidenceId: 'iwencai:row-test:row:partial' },
                closest: (selector) => selector === '[data-intel-action="iwencai-ask-ai"]' ? askPartial : null,
            };
            clickHandler({ target: askPartial, preventDefault: () => {} });
            assert.equal(emitted.at(-1).event, 'iwencai:analyze');
            assert.equal(emitted.at(-1).payload.source_context.row_evidence.validation_status, 'partial');

            const basketButton = {
                dataset: { requestGeneration: '1' },
                closest: (selector) => selector === '[data-intel-action="iwencai-create-basket"]' ? basketButton : null,
            };
            clickHandler({ target: basketButton, preventDefault: () => {} });
            const basketEvent = emitted.at(-1);
            assert.equal(basketEvent.event, 'iwencai:create-basket');
            assert.deepEqual(basketEvent.payload.candidates.map((row) => row.code), ['600000']);
            assert.equal(basketEvent.payload.candidates[0].rowEvidence.raw.validation_status, 'verified');

            const oldGenerationBasket = {
                dataset: { requestGeneration: '999' },
                closest: (selector) => selector === '[data-intel-action="iwencai-create-basket"]' ? oldGenerationBasket : null,
            };
            clickHandler({ target: oldGenerationBasket, preventDefault: () => {} });
            assert.equal(emitted.at(-1), basketEvent);

            const draftButton = {
                dataset: { requestGeneration: '1' },
                closest: (selector) => selector === '[data-intel-action="iwencai-draft-backtest"]' ? draftButton : null,
            };
            clickHandler({ target: draftButton, preventDefault: () => {} });
            const draftEvent = emitted.at(-1);
            assert.equal(draftEvent.event, 'iwencai:draft-backtest');
            assert.deepEqual(draftEvent.payload.candidates.map((row) => row.code), ['600000']);
            assert.equal(draftEvent.payload.candidates[0].rowEvidence.raw.validation_status, 'verified');
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_iwencai_partial_only_rows_do_not_render_or_trigger_pool_actions():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id) {
            return {
                id,
                value: '高股息 低估值',
                innerHTML: '',
                textContent: '',
                classList: { add: () => {}, remove: () => {}, toggle: () => {} },
                addEventListener: () => {},
            };
        }

        let clickHandler = null;
        const input = makeElement('intel-iwencai-input');
        const result = makeElement('intel-iwencai-result');
        const elements = {
            'intel-iwencai-input': input,
            'intel-iwencai-btn': makeElement('intel-iwencai-btn'),
            'intel-iwencai-result': result,
        };
        const partialProvenance = {
            result_pool_id: 'iwencai:partial-only',
            row_id: 'iwencai:partial-only:row:1',
            code: '000001',
            name: '平安银行',
            rank: 1,
            provider: 'iwencai',
            data_as_of: '2026-06-12T09:30:00+08:00',
            cache_status: 'live_request',
            validation_status: 'partial',
            evidence_level: 'partial_provider_field',
            matched_conditions: [
                { raw_text: '低估值', field: '估值', source_field: '市盈率', value: '6.3' },
            ],
            missing_conditions: [
                { raw_text: '高股息', field: '股息率', missing_reason: '该候选行缺少可验证的条件字段取值' },
            ],
            source_fields: [{ field: '市盈率', value: '6.3', condition: '低估值' }],
            missing_reason: '该候选行缺少可验证的条件字段取值',
        };

        global.window = global;
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: () => null,
            addEventListener: (event, handler) => {
                if (event === 'click') clickHandler = handler;
            },
            readyState: 'complete',
        };
        const emitted = [];
        global.App = {
            registerContext: () => {},
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
            fetchJSON: async () => ({
                success: true,
                status: 'result_ready',
                total: 1,
                actions: ['open_stock', 'add_watchlist', 'send_screener', 'analyze', 'ask_ai', 'create_basket', 'draft_backtest'],
                data: [
                    { '股票代码': '000001.SZ', '股票简称': '平安银行', '市盈率': 6.3, candidate_provenance: partialProvenance },
                ],
                buckets: [
                    { id: 'candidates', name: '候选股票', count: 1, items: [{ code: '000001', name: '平安银行', candidate_provenance: partialProvenance }] },
                ],
                parsed_conditions: [
                    { raw_text: '高股息', field: '股息率', hit_count: 1, hit_count_status: 'verified', source_field: '股息率', source_fields: ['股息率'], status: 'ready' },
                    { raw_text: '低估值', field: '估值', hit_count: 1, hit_count_status: 'verified', source_field: '市盈率', source_fields: ['市盈率'], status: 'ready' },
                ],
                source_context: {
                    source: 'global_search',
                    context_type: 'iwencai',
                    result_pool_id: 'iwencai:partial-only',
                    provider: 'iwencai',
                    data_as_of: '2026-06-12T09:30:00+08:00',
                    cache_status: 'live_request',
                    data_status: 'ok',
                },
            }),
            emit: (event, payload) => emitted.push({ event, payload }),
            on: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-iwencai.js', 'utf8'));
        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence.js', 'utf8'));

        (async () => {
            await Intelligence.runIwencai();
            assert.match(result.innerHTML, /部分验证/);
            assert.doesNotMatch(result.innerHTML, /data-intel-action="iwencai-send-screener"/);
            assert.doesNotMatch(result.innerHTML, /data-intel-action="iwencai-add-watchlist"/);
            assert.doesNotMatch(result.innerHTML, /data-intel-action="iwencai-create-basket"/);
            assert.doesNotMatch(result.innerHTML, /data-intel-action="iwencai-draft-backtest"/);
            assert.deepEqual(Intelligence.state.iwencaiActionState.pool, []);
            assert.deepEqual(Intelligence.state.iwencaiActionState.watchlistCodes, []);
            assert.equal(Intelligence.state.iwencaiActionState.actionableCandidates.length, 0);
            assert.equal(Intelligence.state.iwencaiActionState.excludedCandidates[0].code, '000001');

            const staleBasket = {
                closest: (selector) => selector === '[data-intel-action="iwencai-create-basket"]' ? staleBasket : null,
            };
            clickHandler({ target: staleBasket, preventDefault: () => {} });
            assert.equal(emitted.length, 0);

            const staleDraft = {
                closest: (selector) => selector === '[data-intel-action="iwencai-draft-backtest"]' ? staleDraft : null,
            };
            clickHandler({ target: staleDraft, preventDefault: () => {} });
            assert.equal(emitted.length, 0);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_iwencai_stale_slow_response_cannot_overwrite_latest_query_state():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeElement(id) {
            return {
                id,
                value: '',
                innerHTML: '',
                textContent: '',
                classList: { add: () => {}, remove: () => {}, toggle: () => {} },
                addEventListener: () => {},
            };
        }

        function provenance(poolId, code, name) {
            return {
                result_pool_id: poolId,
                row_id: `${poolId}:row:${code}`,
                code,
                name,
                rank: 1,
                provider: 'iwencai',
                data_as_of: '2026-06-12T09:30:00+08:00',
                cache_status: 'live_request',
                validation_status: 'verified',
                evidence_level: 'provider_field',
                matched_conditions: [{ raw_text: '高股息', field: '股息率', source_field: '股息率', value: '5.1' }],
                missing_conditions: [],
                source_fields: [{ field: '股息率', value: '5.1', condition: '高股息' }],
            };
        }

        function responseFor(query, poolId, code, name) {
            const rowEvidence = provenance(poolId, code, name);
            return {
                success: true,
                status: 'result_ready',
                total: 1,
                query,
                selected_bucket: 'candidates',
                actions: ['open_stock', 'add_watchlist', 'send_screener', 'analyze', 'ask_ai', 'create_basket', 'draft_backtest'],
                parsed_conditions: [
                    { raw_text: '高股息', field: '股息率', hit_count: 1, hit_count_status: 'verified', source_field: '股息率', source_fields: ['股息率'], status: 'ready' },
                ],
                data: [
                    { '股票代码': `${code}.SH`, '股票简称': name, '股息率': 5.1, candidate_provenance: rowEvidence },
                ],
                buckets: [
                    { id: 'candidates', name: '候选股票', count: 1, items: [{ code, name, candidate_provenance: rowEvidence }] },
                ],
                source_status: { provider: 'iwencai', status: 'ok', provider_status: 'ok', data_as_of: '2026-06-12T09:30:00+08:00', cache_status: 'live_request' },
                source_context: {
                    source: 'qa_race',
                    context_type: 'iwencai',
                    result_pool_id: poolId,
                    provider: 'iwencai',
                    data_as_of: '2026-06-12T09:30:00+08:00',
                    cache_status: 'live_request',
                    data_status: 'ok',
                },
            };
        }

        const input = makeElement('intel-iwencai-input');
        const result = makeElement('intel-iwencai-result');
        const elements = {
            'intel-iwencai-input': input,
            'intel-iwencai-btn': makeElement('intel-iwencai-btn'),
            'intel-iwencai-result': result,
        };
        const requests = [];
        global.window = global;
        global.document = {
            getElementById: (id) => elements[id] || null,
            querySelector: () => null,
            addEventListener: () => {},
            readyState: 'complete',
        };
        global.App = {
            registerContext: () => {},
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
            fetchJSON: async (url, opts) => {
                assert.equal(url, '/api/llm/iwencai');
                let resolve;
                const promise = new Promise((done) => { resolve = done; });
                requests.push({ body: JSON.parse(opts.body), signal: opts.signal, resolve });
                return promise;
            },
            on: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-iwencai.js', 'utf8'));

        (async () => {
            input.value = '第一条慢查询';
            const first = Intelligence.runIwencai();
            assert.match(result.innerHTML, /解析中/);
            assert.equal(Intelligence.state.iwencaiActionState.request_status, 'pending');
            assert.equal(requests.length, 1);

            input.value = '第二条新查询';
            const second = Intelligence.runIwencai();
            assert.equal(requests.length, 2);
            assert.equal(requests[0].signal.aborted, true);
            assert.equal(requests[1].signal.aborted, false);

            requests[1].resolve(responseFor('第二条新查询', 'iwencai:new-pool', '600001', '新结果'));
            const secondVm = await second;
            assert.equal(secondVm.query, '第二条新查询');
            assert.match(result.innerHTML, /新结果/);
            assert.doesNotMatch(result.innerHTML, /旧结果/);
            assert.deepEqual(Intelligence.state.iwencaiActionState.pool, ['600001']);
            assert.equal(Intelligence.state.iwencaiActionState.query, '第二条新查询');
            assert.equal(Intelligence.state.iwencaiActionState.source_context.result_pool_id, 'iwencai:new-pool');
            assert.equal(Intelligence.state.iwencaiActionState.source_context.request_generation, 2);
            assert.equal(Intelligence.state.iwencaiActionState.source_context.request_status, 'completed');

            requests[0].resolve(responseFor('第一条慢查询', 'iwencai:old-pool', '600000', '旧结果'));
            const firstVm = await first;
            assert.equal(firstVm.query, '第二条新查询');
            assert.match(result.innerHTML, /新结果/);
            assert.doesNotMatch(result.innerHTML, /旧结果/);
            assert.deepEqual(Intelligence.state.iwencaiActionState.pool, ['600001']);
            assert.equal(Intelligence.state.iwencaiActionState.source_context.result_pool_id, 'iwencai:new-pool');
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_iwencai_task_router_status_states_render_distinct_badges():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        global.window = global;
        global.document = {
            getElementById: () => null,
            querySelector: () => null,
            addEventListener: () => {},
            readyState: 'loading',
        };
        global.App = {
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;'),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/intelligence-iwencai.js', 'utf8'));

        const statuses = {
            parsing: '解析中',
            routed: '已路由',
            bucket_pending: '分桶加载中',
            result_ready: '结果就绪',
            partial_result: '部分结果',
            needs_disambiguation: '需要澄清',
            no_match: '无匹配',
            degraded_data: '数据降级',
            requires_confirmation: '需要确认',
            failed: '失败',
        };

        for (const [status, label] of Object.entries(statuses)) {
            const vmResult = Intelligence._buildIwencaiTaskViewModel({
                success: status !== 'failed',
                status,
                total: status === 'no_match' ? 0 : 1,
                intent: { type: 'natural_language_screener', confidence: 0.5, reason: '状态测试' },
                parsed_conditions: [
                    status === 'degraded_data'
                        ? { raw_text: '近5日放量', field: '成交量', status: 'degraded_data', unavailable_reason: '命中数待回填' }
                        : { raw_text: '高股息', field: '股息率', hit_count: 473, status: 'ready' },
                ],
                data: status === 'no_match' ? [] : [{ '股票代码': '600000.SH', '股票简称': '浦发银行' }],
            }, '高股息');
            const html = (() => {
                const el = { innerHTML: '' };
                global.document.getElementById = (id) => id === 'intel-iwencai-result' ? el : null;
                Intelligence.state.iwencaiResult = { query: '高股息', data: vmResult.data, summaryRows: vmResult.summaryRows, viewModel: vmResult };
                Intelligence.state.iwencaiActionState = { viewModel: vmResult };
                Intelligence.selectIwencaiBucket(vmResult.selected_bucket);
                return el.innerHTML;
            })();
            assert.match(html, new RegExp(`status-${status}`));
            assert.match(html, new RegExp(label));
            if (status === 'degraded_data') assert.match(html, /命中数待回填/);
            if (status === 'no_match') assert.match(html, /暂无候选股票/);
        }
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


def test_hidden_right_rail_drawers_do_not_translate_outside_mobile_viewport():
    styles = Path("dashboard/static/style.css").read_text(encoding="utf-8")

    assert ".offcanvas:not(.active)" in styles
    assert ".copilot-sidebar:not(.active)" in styles
    assert "transform: none" in styles
    assert "visibility: hidden" in styles
    assert "pointer-events: none" in styles


def test_iwencai_send_to_screener_opens_research_screener_directly():
    app_shell = Path("dashboard/static/core/app-shell.js").read_text(encoding="utf-8")
    screener_ai = Path("dashboard/static/screener-ai.js").read_text(encoding="utf-8")
    scripts = Path("dashboard/templates/partials/scripts.html").read_text(encoding="utf-8")

    assert "await this.switchTab('research', { subtab: 'screener' })" in app_shell
    assert 'querySelector(\'.research-sub-tab[data-subtab="screener"]\')?.click()' not in app_shell
    assert "codes: codes.slice(0, 100)" in screener_ai
    assert "this.renderResult(data, `问财: ${query}`)" in screener_ai
    assert "/static/core/app-shell.js?v=38" in scripts


def test_iwencai_basket_draft_routes_to_research_basket_without_auto_backtest():
    app_shell = Path("dashboard/static/core/app-shell.js").read_text(encoding="utf-8")

    assert "this.on('iwencai:create-basket'" in app_shell
    assert "this.on('iwencai:draft-backtest'" in app_shell
    assert "await this.loadScript?.('/static/alpha.js?v=6')" in app_shell
    assert "await this.loadScript?.('/static/alpha-tools.js?v=13')" in app_shell
    assert "await this.switchTab('research', { subtab: 'basket', skipBundle: true, applySession: false })" in app_shell
    assert "if (options.skipBundle !== true)" in app_shell
    assert "if (!skipBundle)" in app_shell
    assert "App._setBasketCandidates(normalized)" in app_shell
    assert "App.renderBasketBacktestDraft(normalizedDraft)" in app_shell
    assert "textarea.dataset.sourceContext" in app_shell
    assert "textarea.dataset.backtestDraft" in app_shell
    assert "execution_policy: 'manual_only'" in app_shell
    assert "execution_status: 'not_executed'" in app_shell
    assert "allowed_actions: ['view', 'edit', 'run_backtest_after_confirmation']" in app_shell
    assert "backtest_draft: normalizedDraft" in app_shell
    assert "loadBasketBacktest()" not in app_shell
    draft_handler = app_shell.split("this.on('iwencai:draft-backtest'", 1)[1].split("this.on('data:portfolio-updated'", 1)[0]
    forbidden = [
        "/api/alpha/basket/backtest",
        "/api/backtest/ws/run",
        "/api/paper/",
        "/api/broker",
        "paper-orders",
        "loadBasketBacktest(",
    ]
    for marker in forbidden:
        assert marker not in draft_handler


def test_iwencai_app_shell_preserves_source_context_and_ignores_empty_basket_pool():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const handlers = {};
        const switched = [];
        const toasts = [];
        let screenerPayload = null;
        let llmPrompt = '';
        let setBasketCalled = false;
        let renderedDraft = null;
        let loadBasketBacktestCalled = false;
        const postJSONCalls = [];
        const fetchJSONCalls = [];
        const loadedScripts = [];
        const basketTextarea = { value: '[{"code":"600519"}]', dataset: { sourceContext: 'old' } };

        global.window = global;
        global.location = { hash: '' };
        global.requestAnimationFrame = (fn) => fn();
        global.setTimeout = (fn) => { fn(); return 0; };
        global.document = {
            title: '',
            getElementById: (id) => id === 'basket-candidates' ? basketTextarea : null,
            querySelector: () => null,
        };
        global.App = {
            _tabCache: {},
            _tabAlias: {},
            currentTab: 'intelligence',
            on: (event, handler) => { handlers[event] = handler; },
            ensureBundle: async () => {},
            loadScript: async (src) => { loadedScripts.push(src); },
            switchTab: async (tab, opts) => { switched.push({ tab, opts }); },
            toast: (message, type) => { toasts.push({ message, type }); },
            fetchJSON: async (url, options = {}) => {
                fetchJSONCalls.push({ url, options });
                assert.equal(url, '/api/openclaw/tools/invoke');
                const body = JSON.parse(options.body || '{}');
                assert.doesNotMatch(options.body || '', /raw_payload/);
                assert.doesNotMatch(options.body || '', /SHOULD_NOT_LEAK/);
                assert.doesNotMatch(options.body || '', /cookie/);
                assert.equal(body.tool, 'quant.iwencai.evidence.review');
                assert.equal(body.native, undefined);
                assert.equal(body.arguments.source_context.provider_evidence.summary_status, 'degraded');
                assert.equal(options.silent, true);
                return {
                    success: true,
                    tool: 'quant.iwencai.evidence.review',
                    permission: 'read_market',
                    result: {
                        schema_version: 'iwencai_evidence_review_v1',
                        input_trust: 'caller_supplied_not_live_provider',
                        review_status: 'degraded_review',
                        evidence_status: {
                            present: true,
                            schema_version: 'iwencai_provider_evidence_v1',
                            summary_status: 'degraded',
                            provider: 'iwencai',
                            provider_status: 'schema_drift',
                            data_status: 'degraded_data',
                            cache_status: 'stale_cache',
                            result_pool_id: 'iwencai:test-pool',
                            candidate_count: 2,
                            reported_total: 2,
                            field_coverage_status: 'schema_drift',
                        },
                        condition_validation: { status_counts: { verified: 1, schema_drift: 1 } },
                        candidate_validation: { verified: 1, partial: 1, actionable: 0 },
                        degradation: {
                            type: 'schema_drift',
                            reason: 'review reason token=SHOULD_NOT_LEAK',
                            next_action: '保持只读解释',
                            cache_status: 'stale_cache',
                            response_type: 'DataFrame:schema_vNext',
                            schema_signature: '股票代码|Bearer SHOULD_NOT_LEAK',
                        },
                        write_action_gate: {
                            allowed_by_review_tool: false,
                            evidence_allows_write_actions: false,
                            requires_separate_tool_and_confirmation: false,
                            reason: 'read_only_review_tool',
                            enabled_write_actions: [],
                            blocked_write_actions: ['create_basket', 'draft_backtest'],
                        },
                        recommended_safe_next_actions: ['保持只读解释，并把降级原因展示给用户。'],
                    },
                };
            },
            Screener: {
                init: () => {},
                renderFromPool: (codes, query, sourceContext) => {
                    screenerPayload = { codes, query, sourceContext };
                },
            },
            LLM: {
                openCopilot: () => {},
                sendQuick: (prompt) => { llmPrompt = prompt; },
            },
            _setBasketCandidates: () => { setBasketCalled = true; },
            renderBasketBacktestDraft: (draft) => { renderedDraft = draft; },
            loadBasketBacktest: () => { loadBasketBacktestCalled = true; },
            postJSON: (url, body) => { postJSONCalls.push({ url, body }); },
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/core/app-shell.js', 'utf8'));
        App._initV2Events();
        App.switchTab = async (tab, opts) => { switched.push({ tab, opts }); };

            const sourceContext = {
                source: 'iwencai',
                result_pool_id: 'iwencai:test-pool',
                selected_bucket: 'candidates',
                intent_type: 'natural_language_screener',
                parsed_conditions: [{ raw_text: '高股息', hit_count: 473 }, { raw_text: '低估值', hit_count: 583 }],
                condition_hit_count: { '高股息': 473, '低估值': 583 },
                provider_evidence: {
                    schema_version: 'iwencai_provider_evidence_v1',
                    summary_status: 'degraded',
                    field_coverage_status: 'schema_drift',
                    provider: 'iwencai',
                    provider_status: 'schema_drift',
                    data_status: 'degraded_data',
                    cache_status: 'stale_cache',
                    candidate_count: 2,
                    reported_total: 2,
                    condition_status_counts: { verified: 1, schema_drift: 1 },
                    candidate_validation: { verified: 1, partial: 1, actionable: 0 },
                    write_actions_allowed: false,
                    enabled_write_actions: ['open_stock'],
                    blocked_write_actions: ['create_basket', 'draft_backtest', 'send_screener'],
                    degradation: {
                        type: 'schema_drift',
                        reason: '字段结构变化 token=SHOULD_NOT_LEAK',
                        next_action: '只读解释，禁止生成篮子',
                        cache_status: 'stale_cache',
                        retry_after_seconds: 12,
                        response_type: 'DataFrame:schema_vNext',
                        schema_signature: '股票代码|Bearer SHOULD_NOT_LEAK',
                    },
                    raw_payload: {
                        cookie: 'SHOULD_NOT_LEAK',
                    },
                },
            };
            const verifiedProvenance = {
                result_pool_id: 'iwencai:test-pool',
                row_id: 'iwencai:test-pool:row:600000',
                code: '600000',
                name: '浦发银行',
                rank: 1,
                provider: 'iwencai',
                data_as_of: '2026-06-12T09:30:00+08:00',
                cache_status: 'live_request',
                validation_status: 'verified',
                evidence_level: 'provider_field',
                matched_conditions: [{ raw_text: '高股息', field: '股息率', source_field: '股息率', value: '5.1' }],
                missing_conditions: [],
                source_fields: [{ field: '股息率', value: '5.1', condition: '高股息' }],
                raw_field_map: { cookie: 'must not copy through candidate sanitizer' },
            };

        (async () => {
            await handlers['iwencai:send-to-screener']({ pool: ['600000', '600000', '000001'], query: '高股息', source_context: sourceContext });
            assert.deepEqual(screenerPayload.codes, ['600000', '000001']);
            assert.equal(screenerPayload.query, '高股息');
            assert.equal(screenerPayload.sourceContext.result_pool_id, 'iwencai:test-pool');

            await handlers['iwencai:analyze']({
                query: '高股息',
                data: { summaryRows: [{ code: '600000', name: '浦发银行' }] },
                source_context: sourceContext,
            });
            assert.match(llmPrompt, /来源上下文/);
            assert.match(llmPrompt, /iwencai:test-pool/);
            assert.match(llmPrompt, /高股息/);
            assert.match(llmPrompt, /condition_hit_count/);
            assert.match(llmPrompt, /provider_evidence/);
            assert.match(llmPrompt, /openclaw_evidence_review/);
            assert.match(llmPrompt, /degraded_review/);
            assert.match(llmPrompt, /allowed_by_review_tool":false/);
            assert.match(llmPrompt, /read_only_review_tool/);
            assert.match(llmPrompt, /schema_drift/);
            assert.match(llmPrompt, /write_actions_allowed":false/);
            assert.match(llmPrompt, /blocked_write_actions/);
            assert.match(llmPrompt, /只读解释，禁止生成篮子/);
            assert.doesNotMatch(llmPrompt, /SHOULD_NOT_LEAK/);
            assert.doesNotMatch(llmPrompt, /raw_payload/);
            assert.doesNotMatch(llmPrompt, /cookie/);
            assert.equal(fetchJSONCalls.length, 1);

            const beforeSwitchCount = switched.length;
            await handlers['iwencai:create-basket']({ query: '空池', candidates: [], source_context: sourceContext });
            assert.equal(switched.length, beforeSwitchCount);
            assert.equal(setBasketCalled, false);
            assert.equal(basketTextarea.value, '[{"code":"600519"}]');
            assert.equal(basketTextarea.dataset.sourceContext, 'old');
            assert.equal(toasts.at(-1).type, 'warning');

            const eventGroupContext = {
                source: 'overview:opportunity',
                sourceLabel: 'AI信号',
                event_group: {
                    stock_code: '300308',
                    stock_name: '中际旭创',
                    event_date: '2026-06-10',
                    event_count: 4,
                    raw_count: 5,
                    event_types: ['capital_flow', 'announcement', 'research_report'],
                    primary_event_id: 'capital-1',
                    event_titles: ['主力资金净流入', '签订重大合同'],
                    dedupe_policy: '重复转载只计一次',
                    rank_reason: '2026-06-10 同日事件组',
                },
            };
            const backtestDraft = {
                status: 'executed',
                requires_confirmation: false,
                execution_status: 'executed',
                allowed_actions: ['view', 'run_live_trade'],
                conditions: {
                    event_date: '2026-06-10',
                    entry_rule: '次一交易日开盘',
                    holding_periods: [1, 3, 5],
                },
            };
            await handlers['iwencai:analyze']({
                query: '中际旭创 事件组',
                data: {
                    event_group: eventGroupContext.event_group,
                    event_group_diagnosis: {
                        summary: '4 个独立事件 / 5 条原始证据',
                        counter_evidence: '重复转载 1 条',
                        missing_evidence: '缺少回测验证',
                        confidence: 'low',
                        signal_direction: 'event_catalyst_needs_backtest',
                    },
                },
                source_context: eventGroupContext,
            });
            assert.match(llmPrompt, /event_group/);
            assert.match(llmPrompt, /重复转载 1 条/);
            assert.match(llmPrompt, /中际旭创/);

            await handlers['iwencai:draft-backtest']({
                query: '中际旭创 事件组',
                candidates: [{ code: '300308', name: '中际旭创' }],
                source_context: eventGroupContext,
                backtest_draft: backtestDraft,
            });
            assert.equal(setBasketCalled, true);
            assert.deepEqual(loadedScripts, ['/static/alpha.js?v=6', '/static/alpha-tools.js?v=13']);
            assert.deepEqual(switched.at(-1), { tab: 'research', opts: { subtab: 'basket', skipBundle: true, applySession: false } });
            assert.match(basketTextarea.dataset.sourceContext, /stock_code/);
            assert.match(basketTextarea.dataset.backtestDraft, /requires_confirmation/);
            assert.match(basketTextarea.dataset.backtestDraft, /manual_only/);
            assert.equal(App._iwencaiBasketDraft.draftMode, 'backtest');
            assert.equal(App._iwencaiBasketDraft.backtest_draft.requires_confirmation, true);
            assert.equal(App._iwencaiBasketDraft.backtest_draft.conditions.event_date, '2026-06-10');
            assert.equal(App._iwencaiBasketDraft.backtest_draft.execution_policy, 'manual_only');
            assert.equal(App._iwencaiBasketDraft.backtest_draft.execution_status, 'not_executed');
            assert.deepEqual(App._iwencaiBasketDraft.backtest_draft.allowed_actions, ['view', 'edit', 'run_backtest_after_confirmation']);
            assert.equal(App._iwencaiBasketDraft.backtest_draft.source_context.event_group.stock_name, '中际旭创');
            assert.equal(renderedDraft.execution_policy, 'manual_only');
            assert.equal(renderedDraft.execution_status, 'not_executed');
            assert.equal(loadBasketBacktestCalled, false);
            assert.equal(postJSONCalls.length, 0);
            assert.match(toasts.at(-1).message, /手动执行计划回测/);

            renderedDraft = null;
            await handlers['iwencai:draft-backtest']({
                query: '高股息 低估值 近5日放量',
                candidates: [{ code: '600000', name: '浦发银行', candidate_provenance: verifiedProvenance }, { code: '000001', name: '平安银行' }],
                source_context: sourceContext,
            });
            assert.equal(App._iwencaiBasketDraft.draftMode, 'backtest');
            assert.equal(App._iwencaiBasketDraft.backtest_draft.draft_type, 'iwencai_basket_backtest_draft');
            assert.equal(App._iwencaiBasketDraft.backtest_draft.conditions.candidate_count, 2);
            assert.match(App._iwencaiBasketDraft.backtest_draft.conditions.hypothesis, /高股息/);
            assert.equal(App._iwencaiBasketDraft.backtest_draft.requires_confirmation, true);
            assert.equal(App._iwencaiBasketDraft.backtest_draft.execution_status, 'not_executed');
            assert.deepEqual(App._iwencaiBasketDraft.backtest_draft.allowed_actions, ['view', 'edit', 'run_backtest_after_confirmation']);
            assert.equal(renderedDraft.draft_type, 'iwencai_basket_backtest_draft');
            assert.equal(App._iwencaiBasketDraft.candidates[0].candidate_provenance.row_id, 'iwencai:test-pool:row:600000');
            assert.equal(App._iwencaiBasketDraft.candidates[0].row_evidence_status, 'verified');
            assert.equal(App._iwencaiBasketDraft.candidates[0].candidate_provenance.raw_field_map, undefined);
            assert.equal(loadBasketBacktestCalled, false);
            assert.equal(postJSONCalls.length, 0);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_iwencai_ai_analysis_uses_focused_summary_rows_not_raw_fields():
    app_shell = Path("dashboard/static/core/app-shell.js").read_text(encoding="utf-8")
    iwencai = Path("dashboard/static/intelligence-iwencai.js").read_text(encoding="utf-8")

    assert "summaryRows" in iwencai
    assert "data.summaryRows" in app_shell
    assert "data.data.slice(0, 5)" not in app_shell
    assert "MARKET_CODE" not in app_shell
