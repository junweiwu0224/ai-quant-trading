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
            assert.match(heatmap.innerHTML, /全量 496 · 展示 4/);
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
                    source: '本地市场新闻',
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
            assert.match(list.innerHTML, /本地市场新闻/);
            assert.match(list.innerHTML, /2026-06-06T23:20:00/);
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
            assert.equal(score.textContent, '+17');
            assert.match(score.title, /全市场广度/);
            assert.match(sources.innerHTML, /全市场广度/);
            assert.match(sources.innerHTML, /上涨占比 57%/);
            assert.match(sources.innerHTML, /涨跌比 1\.43/);
            assert.match(sources.innerHTML, /涨停\/跌停 96\/19/);
            assert.match(sources.innerHTML, /有效 5,515\/5,525/);
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
            assert.equal(score.textContent, '--');
            assert.match(sources.innerHTML, /广度不可用/);

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

            assert.equal(score.textContent, '+17');
            assert.match(sources.innerHTML, /全市场广度/);
            assert.match(sources.innerHTML, /有效 5,515\/5,525/);
            assert.doesNotMatch(sources.innerHTML, /广度不可用/);
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
            assert.deepEqual(calls, ['/api/signals/top?limit=50', '/api/signals/validation?top_n=50']);
            assert.match(panel.innerHTML, /验证摘要/);
            assert.match(panel.innerHTML, /样本 42 天/);
            assert.match(panel.innerHTML, /Top超额 \+1\.23%/);
            assert.match(panel.innerHTML, /胜率 58\.6%/);
            assert.match(panel.innerHTML, /Rank IC 0\.071/);
            assert.match(panel.innerHTML, /状态 验证偏正/);
            assert.match(panel.innerHTML, /可信口径/);
            assert.match(panel.innerHTML, /来源 历史预测缓存/);
            assert.match(panel.innerHTML, /覆盖 5,197 只/);
            assert.match(panel.innerHTML, /展示 Top 2/);
            assert.match(panel.innerHTML, /生成 2026-06-07T12:30:00/);
            assert.match(panel.innerHTML, /验证样本 42 天/);
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


def test_intelligence_load_retries_failed_signal_pool_after_other_modules_succeed():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        global.window = global;
        global.document = {
            readyState: 'complete',
            addEventListener: () => {},
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
            assert.deepEqual(first.map((item) => item.status), ['fulfilled', 'rejected']);
            assert.equal(Intelligence.state.loaded, false);
            assert.equal(signalCalls, 1);

            const second = await Intelligence.load();
            assert.deepEqual(second.map((item) => item.status), ['fulfilled']);
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


def test_intelligence_market_assets_are_versioned_and_styled():
    app_js = Path("dashboard/static/app.js").read_text(encoding="utf-8")
    styles = Path("dashboard/static/style.css").read_text(encoding="utf-8")
    scripts = Path("dashboard/templates/partials/scripts.html").read_text(encoding="utf-8")
    app_ui_shell = Path("dashboard/static/app-ui-shell.js").read_text(encoding="utf-8")
    service_worker = Path("dashboard/static/sw.js").read_text(encoding="utf-8")

    assert "/static/intelligence.js?v=5" in app_js
    assert "/static/intelligence-market.js?v=6" in app_js
    assert "/static/intelligence-iwencai.js?v=3" in app_js
    assert "/static/intelligence-signals.js?v=2" in app_js
    assert "/static/intelligence-qlib.js" not in app_js
    assert "/static/app.js?v=66" in scripts
    assert "/static/app-ui-shell.js?v=20" in scripts
    assert "/sw.js?v=27" in app_ui_shell
    assert "ai-quant-v98" in service_worker
    assert "/static/intelligence-signals.js" in service_worker
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
    assert "/static/core/app-shell.js?v=21" in scripts


def test_iwencai_ai_analysis_uses_focused_summary_rows_not_raw_fields():
    app_shell = Path("dashboard/static/core/app-shell.js").read_text(encoding="utf-8")
    iwencai = Path("dashboard/static/intelligence-iwencai.js").read_text(encoding="utf-8")

    assert "summaryRows" in iwencai
    assert "data.summaryRows" in app_shell
    assert "data.data.slice(0, 5)" not in app_shell
    assert "MARKET_CODE" not in app_shell
