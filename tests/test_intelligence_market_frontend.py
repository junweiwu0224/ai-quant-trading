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

    assert '<div class="signal-bar-score" id="signal-bar-score">加载中</div>' in template
    assert '等待全市场广度' in template
    assert '<span class="badge badge-sm" id="intel-news-count">--</span>' in template
    assert '<span class="badge badge-sm" id="intel-news-count">0</span>' not in template
    assert '<div class="signal-bar-score" id="signal-bar-score">--</div>' not in template


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
                    news: [
                        {
                            title: '近三个月车规级存储芯片价格暴涨180%',
                            time: '2026-06-06 22:42:26',
                            source: '东方财富快讯',
                            sentiment: 0.3,
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
            assert.match(list.innerHTML, /东方财富滚动快讯/);
            assert.match(list.innerHTML, /东方财富快讯/);
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
            assert.match(sources.innerHTML, /上涨占比 57%/);
            assert.match(sources.innerHTML, /涨跌比 1\.43/);
            assert.match(sources.innerHTML, /涨停\/跌停 96\/19/);
            assert.match(sources.innerHTML, /样本 5,515\/5,525/);
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
                        predictions: [
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
            assert.match(panel.innerHTML, /验证摘要/);
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
            assert.match(panel.innerHTML, /来源 local_momentum/);
            assert.match(panel.innerHTML, /模型 local_momentum_v1/);
            assert.match(panel.innerHTML, /兼容缓存 历史预测缓存 \(legacy_qlib\)/);
            assert.match(panel.innerHTML, /覆盖 5,197 只/);
            assert.match(panel.innerHTML, /展示 Top 2/);
            assert.match(panel.innerHTML, /生成 2026-06-07T12:30:00/);
            assert.match(panel.innerHTML, /验证样本 42 天/);
            assert.match(panel.innerHTML, /title="历史验证偏正"/);
            assert.match(panel.innerHTML, /<td class="qlib-td qlib-td-ic">验证偏正<\/td>/);
            assert.match(panel.innerHTML, /信号日期: 2026-06-05/);
            assert.doesNotMatch(panel.innerHTML, /qlib LightGBM/i);
            assert.doesNotMatch(panel.innerHTML, />validated_positive</);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_intelligence_signal_pool_rows_use_provider_validation_when_record_unverified():
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
            assert.match(panel.innerHTML, /<td class="qlib-td qlib-td-ic">未验证<\/td>/);

            await Intelligence.state.signalValidationLoadingPromise;
            assert.match(panel.innerHTML, /全市场 5,197 只 · Top 1 · 验证中性/);
            assert.match(panel.innerHTML, /状态 验证中性/);
            assert.match(panel.innerHTML, /<td class="qlib-td qlib-td-ic">验证中性<\/td>/);
            assert.doesNotMatch(panel.innerHTML, /<td class="qlib-td qlib-td-ic">未验证<\/td>/);
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


def test_intelligence_market_assets_are_versioned_and_styled():
    app_js = Path("dashboard/static/app.js").read_text(encoding="utf-8")
    styles = Path("dashboard/static/style.css").read_text(encoding="utf-8")
    scripts = Path("dashboard/templates/partials/scripts.html").read_text(encoding="utf-8")
    app_ui_shell = Path("dashboard/static/app-ui-shell.js").read_text(encoding="utf-8")
    service_worker = Path("dashboard/static/sw.js").read_text(encoding="utf-8")

    assert "/static/intelligence.js?v=6" in app_js
    assert "/static/intelligence-market.js?v=12" in app_js
    assert "/static/intelligence-iwencai.js?v=3" in app_js
    assert "/static/intelligence-signals.js?v=8" in app_js
    assert "/static/intelligence-qlib.js" not in app_js
    assert "/static/app.js?v=77" in scripts
    assert "/static/app-ui-shell.js?v=26" in scripts
    assert "/sw.js?v=41" in app_ui_shell
    assert "ai-quant-v124" in service_worker
    static_assets_body = service_worker.split("const STATIC_ASSETS = [", 1)[1].split("];", 1)[0]
    assert "/static/intelligence-signals.js" not in static_assets_body
    assert "/static/intelligence-qlib.js" not in service_worker
    assert ".intel-treemap" in styles
    assert ".intel-hotspot-status" in styles
    assert ".intel-hotspot-evidence" in styles
    assert ".intel-sent-meta" in styles


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
    assert "/static/core/app-shell.js?v=25" in scripts


def test_iwencai_ai_analysis_uses_focused_summary_rows_not_raw_fields():
    app_shell = Path("dashboard/static/core/app-shell.js").read_text(encoding="utf-8")
    iwencai = Path("dashboard/static/intelligence-iwencai.js").read_text(encoding="utf-8")

    assert "summaryRows" in iwencai
    assert "data.summaryRows" in app_shell
    assert "data.data.slice(0, 5)" not in app_shell
    assert "MARKET_CODE" not in app_shell
