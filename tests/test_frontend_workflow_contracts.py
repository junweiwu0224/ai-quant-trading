import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def run_node(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["node", "-e", script],
        check=False,
        capture_output=True,
        text=True,
    )


def test_stock_detail_clears_stale_header_when_detail_api_fails():
    core = read("dashboard/static/stock-detail-core.js")

    assert "this._renderDetailPending(code, { stock: optionStock, name: optionName });" in core
    assert "_renderDetailUnavailable(code, error)" in core
    assert "本地基础资料暂未覆盖该股票" in core
    assert "this._renderDetailHeader({" in core
    assert "code: safeCode" in core


def test_market_radar_exposes_stable_table_and_stock_name_context():
    radar = read("dashboard/static/overview-radar.js")
    bootstrap = read("dashboard/static/app-bootstrap.js")

    assert 'id="overview-radar-table"' in radar
    assert 'data-testid="overview-radar-table"' in radar
    assert 'data-name="${App.escapeHTML(s.name || \'\')}"' in radar
    assert "const name = typeof link.dataset.name === 'string'" in bootstrap
    assert "name," in bootstrap


def test_data_scope_notes_are_visible_for_research_workbenches():
    template = read("dashboard/templates/index.html")
    datahub = read("dashboard/static/research-datahub.js")
    valuation = read("dashboard/static/research-valuation.js")

    assert 'id="overview-radar-coverage"' in template
    assert 'id="datahub-scope-note"' in template
    assert 'id="valuation-scope-note"' in template
    assert "当前账号自选，不代表全市场" in datahub
    assert "AI 信号候选池，未验证信号已降权" in datahub
    assert "机构预测 + AI信号覆盖池，不等同全量日线" in valuation
    assert "估值服务全市场扫描，非本地日线全量" in valuation


def test_signal_engine_is_primary_frontend_semantics():
    app = read("dashboard/static/app.js")
    scripts = read("dashboard/templates/partials/scripts.html")
    template = read("dashboard/templates/index.html")
    datahub = read("dashboard/static/research-datahub.js")
    valuation = read("dashboard/static/research-valuation.js")
    overview = read("dashboard/static/overview.js")
    paper = read("dashboard/static/paper.js")
    manager = read("strategy/manager.py")
    backtest = read("dashboard/routers/backtest.py")
    paper_control = read("dashboard/routers/paper_control.py")
    signal_strategy = read("strategy/qlib_signal.py")
    dashboard_app = read("dashboard/app.py")
    qlib_router = read("dashboard/routers/qlib.py")

    assert "/static/intelligence-signals.js?v=3" in app
    assert "/static/intelligence-qlib.js" not in app
    assert "/static/app.js?v=66" in scripts

    assert 'data-ov-opportunity-scope="signal" aria-pressed="true">AI信号 Top</button>' in template
    assert '<option value="signal">AI 信号 Top</option>' in template
    assert '<option value="signal" selected>AI信号覆盖池</option>' in template
    assert 'ML 信号策略 (qlib)' not in template
    assert 'title="重新训练 qlib ML 模型"' not in template

    assert "_overviewOpportunityScope: 'signal'" in overview
    assert "scope === 'qlib' ? 'signal' : scope" in overview
    assert "query.set('scope', requestedScope)" in overview
    assert "scope === 'signal'" in datahub
    assert "scope === 'signal'" in valuation
    assert "trainSignalModel" in paper
    assert "开始刷新 AI 信号模型" in paper
    assert "qlib 训练" not in paper
    assert "基于 AI 信号分数" in manager
    assert "qlib 预测缓存不存在" not in backtest
    assert "qlib 训练" not in backtest
    assert "AI 信号缓存不存在" in backtest
    assert "qlib 服务不可用" not in signal_strategy
    assert "从 qlib 服务加载" not in signal_strategy
    assert "AI 信号服务不可用" in signal_strategy
    assert "qlib_signal 需要从 qlib 服务加载预测分数" not in paper_control
    assert "qlib_signal 兼容 ID 使用 AI 信号服务加载分数" in paper_control
    assert 'tags=["qlib 预测"]' not in dashboard_app
    assert 'tags=["AI 信号兼容接口"]' in dashboard_app
    assert "Qlib 服务健康检查" not in qlib_router
    assert "读取 Qlib 日线覆盖同步状态" not in qlib_router
    assert "AI 信号兼容接口健康检查" in qlib_router


def test_research_datahub_scope_note_prioritizes_signal_validation_quality():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const note = { innerHTML: '' };
        const scope = { value: 'signal' };

        global.window = global;
        global.document = {
            getElementById: (id) => {
                if (id === 'datahub-scope-note') return note;
                if (id === 'datahub-scope') return scope;
                return null;
            },
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
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/research-datahub.js', 'utf8'));

        ResearchDataHub._renderScopeNote({
            total: 10,
            valuation_coverage_pct: 40,
            signal_coverage_pct: 80,
            qlib_coverage_pct: 80,
            signal_quality: {
                label: '未验证',
                sample_days: 0,
                penalty_applied: true,
                message: '历史样本不足，AI信号已降权',
            },
        }, []);

        assert.match(note.innerHTML, /AI信号覆盖 80%/);
        assert.match(note.innerHTML, /未验证/);
        assert.match(note.innerHTML, /已降权/);
        assert.doesNotMatch(note.innerHTML, /Qlib覆盖/);
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_open_paper_buy_defaults_to_trade_subtab_and_focuses_order_form():
    adapter = read("dashboard/static/core/business-adapter.js")

    assert "const PAPER_SUB_TAB_CANDIDATES = Object.freeze(['trade', 'console']);" in adapter
    assert "payload.activeTab = payload.activeTab || 'trade';" in adapter
    assert "document.getElementById('pt-order-form')?.scrollIntoView" in adapter


def test_changed_frontend_assets_are_cache_busted():
    app = read("dashboard/static/app.js")
    scripts = read("dashboard/templates/partials/scripts.html")
    template = read("dashboard/templates/index.html")
    search = read("dashboard/static/search.js")
    watchlist = read("dashboard/static/watchlist.js")
    workbench = read("dashboard/static/app-workbench.js")
    compare = read("dashboard/static/compare.js")
    paper_trading = read("dashboard/static/paper-trading.js")
    datahub = read("dashboard/static/research-datahub.js")
    valuation = read("dashboard/static/research-valuation.js")
    alpha = read("dashboard/static/alpha.js")
    alpha_tools = read("dashboard/static/alpha-tools.js")

    assert "/static/style.css?v=47" in template
    assert "/static/search.js?v=13" in scripts
    assert "/static/watchlist.js?v=9" in scripts
    assert "/static/app.js?v=66" in scripts
    assert "/static/app-stock-ops.js?v=4" in scripts
    assert "/static/core/business-adapter.js?v=4" in scripts
    assert "/static/core/app-shell.js?v=21" in scripts
    assert "/static/app-ui-shell.js?v=20" in scripts
    assert "/static/app-workbench.js?v=2" in scripts
    assert "/static/openclaw-conversations.js?v=3" in scripts
    assert "/static/openclaw-workbench.js?v=26" in scripts
    assert "/static/app-bootstrap.js?v=21" in scripts
    assert "/static/overview.js?v=18" in scripts
    assert "/static/overview.js?v=18" in app
    assert "/static/alerts.js?v=4" in scripts
    assert "/static/alerts.js?v=4" in app
    assert "/static/overview-radar.js?v=6" in scripts
    assert "/static/overview-radar.js?v=6" in app
    assert "/static/paper.js?v=9" in app
    assert "/static/paper-trading.js?v=6" in app
    assert "/static/compare.js?v=5" in app
    assert "/static/alpha.js?v=5" in app
    assert "/static/alpha-tools.js?v=5" in app
    assert "/static/research-datahub.js?v=12" in app
    assert "/static/research-valuation.js?v=15" in app
    assert "/static/stock-detail-core.js?v=6" in app
    assert "/static/openclaw-conversations.js?v=3" in app
    assert "/static/openclaw-workbench.js?v=26" in app
    assert "/static/intelligence.js?v=5" in app

    assert "minQueryLength" in search
    assert "minQueryLength: 1" in watchlist
    assert "/api/stock/search?q=&limit=6000" not in workbench
    assert "/api/stock/search?q=&limit=6000" not in watchlist
    assert "/api/stock/search?limit=200" not in compare
    assert "App._allStocks" not in paper_trading
    assert "if (!q) return [];" in watchlist
    assert "emptyScope: 'watchlist'" in workbench
    assert "emptyScope: 'watchlist'" in datahub
    assert "emptyScope: 'watchlist'" in valuation
    assert "_fmtPeg(item.peg_next_year)" in datahub
    assert "_fmtQlib(item)" in datahub
    assert "_metaLine" not in datahub
    assert "datahub-stock-meta" in datahub
    assert "datahub-missing-badge" in datahub
    assert "inlineFilter" in search
    assert "sb-no-inline-filter" in search
    assert "initFormulaBasketPickers" in alpha
    assert "_alphaActionHandlersBound" in alpha
    assert "_alphaInitDone" not in alpha
    assert "new SearchBox('formula-code', 'formula-code-dropdown'" in alpha_tools
    assert "new MultiSearchBox('basket-code-input', 'basket-code-dropdown', 'basket-code-tags'" in alpha_tools
    assert "emptyScope: 'watchlist'" in alpha_tools
    assert "自选股为空，输入代码或名称搜索全市场" in alpha_tools
    assert "basket-use-watchlist" in template
    assert "basket-clear-candidates" in template
    assert "全市场选股" in template
    assert "basket-advanced-json" in template


def test_hash_sync_initializes_default_tab_when_cache_is_empty():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const calls = [];
        const panel = {
            id: 'tab-overview',
            classList: { contains: () => true, toggle: () => {} },
            setAttribute: () => {},
            removeAttribute: () => {},
        };

        global.window = global;
        global.dispatchEvent = () => {};
        global.document = {
            getElementById: (id) => id === 'tab-overview' ? panel : null,
            querySelectorAll: () => [],
            querySelector: () => null,
        };
        global.location = { hash: '#overview' };
        global.history = { replaceState: () => {} };
        global.requestAnimationFrame = (fn) => fn();
        global.Event = function Event(name) { this.name = name; };
        global.App = {
            currentTab: 'overview',
            _tabAlias: {},
            _tabCache: {},
            loadOverview: () => calls.push('loadOverview'),
            _startMarketRefresh: () => calls.push('startMarketRefresh'),
            _stopMarketRefresh: () => calls.push('stopMarketRefresh'),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/core/app-shell.js', 'utf8'));

        App._syncTabFromHash();

        setImmediate(() => {
            assert.ok(calls.includes('loadOverview'));
            assert.ok(App._tabCache.overview);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_alerts_ignores_navigation_fetch_abort_noise():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const errors = [];
        const listeners = {};
        global.window = {
            addEventListener: (name, handler) => { listeners[name] = handler; },
        };
        global.globalThis = global;
        global.__AUTH_GATE_REQUIRED__ = true;
        global.document = {
            readyState: 'complete',
            visibilityState: 'hidden',
            getElementById: () => null,
            querySelector: () => null,
            addEventListener: () => {},
        };
        global.console = { ...console, error: (...args) => errors.push(args.join(' ')) };
        global.App = {
            fetchJSON: async () => { throw new TypeError('Failed to fetch'); },
            toast: () => {},
            escapeHTML: (value) => String(value ?? ''),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/alerts.js', 'utf8'));
        if (listeners.pagehide) listeners.pagehide();

        (async () => {
            await App.Alerts.loadRules();
            assert.deepEqual(errors, []);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_alerts_treats_startup_timeout_as_soft_state():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const errors = [];
        global.window = { addEventListener: () => {} };
        global.globalThis = global;
        global.__AUTH_GATE_REQUIRED__ = true;
        global.document = {
            readyState: 'complete',
            visibilityState: 'visible',
            getElementById: () => null,
            querySelector: () => null,
            addEventListener: () => {},
        };
        global.console = { ...console, error: (...args) => errors.push(args.join(' ')), warn: () => {} };
        global.App = {
            fetchJSON: async () => { throw new Error('请求超时'); },
            toast: () => {},
            escapeHTML: (value) => String(value ?? ''),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/alerts.js', 'utf8'));

        (async () => {
            await App.Alerts.loadRules();
            assert.deepEqual(errors, []);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_overview_radar_timeout_renders_soft_placeholder():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const container = { innerHTML: '' };
        const overviewPanel = { classList: { contains: (name) => name === 'active' } };
        global.window = { LocalMCP: null };
        global.globalThis = global;
        global.__AUTH_GATE_REQUIRED__ = true;
        global.document = {
            readyState: 'complete',
            addEventListener: () => {},
            querySelectorAll: () => [],
            getElementById: (id) => {
                if (id === 'radar-content') return container;
                if (id === 'tab-overview') return overviewPanel;
                return null;
            },
        };
        global.App = {
            fetchJSON: async () => { throw new Error('请求超时'); },
            escapeHTML: (value) => String(value ?? ''),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/overview-radar.js', 'utf8'));

        (async () => {
            await App.OverviewRadar.loadRadar();
            assert.match(container.innerHTML, /市场雷达暂未返回/);
            assert.doesNotMatch(container.innerHTML, /请求超时|加载失败/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_openclaw_settings_renders_even_when_conversation_init_fails():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const settingsRoot = {
            innerHTML: '',
            querySelector: () => null,
            querySelectorAll: () => [],
        };

        global.window = global;
        global.globalThis = global;
        global.location = { origin: 'http://127.0.0.1:8001' };
        global.requestAnimationFrame = (fn) => fn();
        global.document = {
            addEventListener: () => {},
            getElementById: (id) => id === 'openclaw-settings-workbench' ? settingsRoot : null,
            body: { appendChild: () => {} },
        };
        global.OpenClawConversations = {
            init: async () => { throw new Error('conversation unavailable'); },
            render: () => {},
        };
        global.App = {
            _accountState: {
                authenticated: true,
                user: { id: 'u1', username: 'tester', display_name: 'Tester', role: 'user' },
                workspace: { id: 'w1', name: 'Workspace', openclaw_workspace_id: 'ocw_1', settings: {} },
                permissions: {},
            },
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;'),
            fetchJSON: async () => null,
            _setAuthGate: () => {},
            toast: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/openclaw-workbench.js', 'utf8'));

        (async () => {
            await OpenClawWorkbench.init('openclaw-settings');
            assert.match(settingsRoot.innerHTML, /openclaw-settings-profile/);
            assert.match(settingsRoot.innerHTML, /API Key \/ 安全/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_openclaw_restores_active_conversation_before_slow_status_payloads():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const elements = {};
        function makeElement(id) {
            return elements[id] || (elements[id] = {
                id,
                value: '',
                innerHTML: '',
                scrollTop: 0,
                scrollHeight: 0,
                classList: { toggle: () => {}, remove: () => {} },
                querySelector: () => null,
                querySelectorAll: () => [],
            });
        }
        const root = makeElement('openclaw-workbench');
        Object.defineProperty(root, 'innerHTML', {
            get() { return this._html || ''; },
            set(value) {
                this._html = value;
                makeElement('openclaw-messages');
                makeElement('openclaw-input');
                makeElement('openclaw-composer-hint');
                makeElement('openclaw-chat-subtitle');
                makeElement('openclaw-conversation-rail');
            },
        });

        global.window = global;
        global.globalThis = global;
        global.document = {
            addEventListener: () => {},
            getElementById: (id) => elements[id] || null,
            querySelector: (selector) => selector === '.openclaw-chat-shell'
                ? { classList: { toggle: () => {} } }
                : null,
            querySelectorAll: () => [],
        };
        global.OpenClawConversations = {
            render: () => {},
            getActiveConversationId: () => 'oc_1',
        };
        global.App = {
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;'),
            fetchJSON: async (url) => {
                if (String(url).includes('/api/openclaw/conversations/oc_1')) {
                    return {
                        success: true,
                        data: {
                            id: 'oc_1',
                            messages: [
                                { role: 'user', content: '今天 600519 怎么样' },
                                { role: 'assistant', content: '回复：今天 600519 怎么样' },
                            ],
                        },
                    };
                }
                return new Promise(() => {});
            },
            toast: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/openclaw-workbench.js', 'utf8'));
        void OpenClawWorkbench.refresh('openclaw');

        setTimeout(() => {
            try {
                assert.match(elements['openclaw-messages'].innerHTML, /600519/);
            } catch (error) {
                console.error(error);
                process.exit(1);
            }
        }, 30);
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_openclaw_refresh_preserves_skill_command_draft_and_hint():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const elements = {};
        function makeElement(id) {
            return elements[id] || (elements[id] = {
                id,
                value: '',
                innerHTML: '',
                scrollTop: 0,
                scrollHeight: 0,
                classList: { toggle: () => {}, remove: () => {} },
                querySelector: () => null,
                querySelectorAll: () => [],
            });
        }
        const root = makeElement('openclaw-workbench');
        makeElement('openclaw-input').value = '/skill record openclaw';
        Object.defineProperty(root, 'innerHTML', {
            get() { return this._html || ''; },
            set(value) {
                this._html = value;
                elements['openclaw-messages'] = makeElement('openclaw-messages');
                elements['openclaw-input'] = {
                    ...makeElement('openclaw-input'),
                    value: '',
                    innerHTML: '',
                    classList: { toggle: () => {}, remove: () => {} },
                    querySelector: () => null,
                    querySelectorAll: () => [],
                };
                makeElement('openclaw-composer-hint');
                makeElement('openclaw-chat-subtitle');
                makeElement('openclaw-conversation-rail');
            },
        });

        global.window = global;
        global.globalThis = global;
        global.document = {
            addEventListener: () => {},
            getElementById: (id) => elements[id] || null,
            querySelector: (selector) => selector === '.openclaw-chat-shell'
                ? { classList: { toggle: () => {} } }
                : null,
            querySelectorAll: () => [],
        };
        global.OpenClawConversations = {
            render: () => {},
            getActiveConversationId: () => '',
        };
        global.App = {
            escapeHTML: (value) => String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;'),
            fetchJSON: async () => null,
            toast: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/openclaw-workbench.js', 'utf8'));

        (async () => {
            await OpenClawWorkbench.refresh('openclaw');
            assert.equal(elements['openclaw-input'].value, '/skill record openclaw');
            assert.match(elements['openclaw-composer-hint'].innerHTML, /技能命令/);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_realtime_websocket_initial_sends_are_disconnect_guarded():
    source = read("dashboard/routers/realtime_quotes.py")

    assert "async def _safe_ws_send_text" in source
    assert "except (WebSocketDisconnect, ClientDisconnected)" in source
    assert "await _safe_ws_send_text(ws, json.dumps({" in source
    assert "if not await _safe_ws_send_text(ws, json.dumps({" in source
