import subprocess
import textwrap


def run_node(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["node", "-e", script],
        check=False,
        capture_output=True,
        text=True,
    )


def test_api_client_formats_fastapi_validation_detail():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const toasts = [];
        global.window = { App: { toast: (message) => toasts.push(message) } };
        Object.defineProperty(global, 'navigator', {
            value: { onLine: true },
            configurable: true,
        });
        global.Headers = Headers;
        global.fetch = async () => ({
            ok: false,
            status: 422,
            text: async () => JSON.stringify({
                detail: [{
                    type: 'string_too_short',
                    loc: ['body', 'username'],
                    msg: 'String should have at least 3 characters',
                    ctx: { min_length: 3 },
                }],
            }),
        });

        vm.runInThisContext(fs.readFileSync('dashboard/static/core/api-client.js', 'utf8'));

        (async () => {
            let message = '';
            try {
                await window.APIClient.fetchJSON('/api/account/register');
            } catch (error) {
                message = error.message;
            }
            assert.match(message, /请求参数校验失败/);
            assert.match(message, /用户名至少需要 3 个字符/);
            assert.doesNotMatch(message, /\[object Object\]/);
            assert.deepEqual(toasts, [message]);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_register_payload_validation_rejects_short_username():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        global.document = {};
        global.navigator = {};
        global.localStorage = { getItem: () => null, setItem: () => {} };
        global.window = {
            matchMedia: () => ({ matches: false }),
            addEventListener: () => {},
        };
        global.globalThis = global;
        global.App = {
            escapeHTML: (value) => String(value ?? ''),
            toast: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/app-ui-shell.js', 'utf8'));

        const message = App._validateRegisterPayload({
            username: '1',
            password: '12345678',
            invite_code: 'LOCAL1',
            display_name: '',
            email: '',
        });

        assert.equal(message, '用户名至少需要 3 个字符');
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_authenticated_session_initializes_overview_widgets_after_auth_gate():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const calls = [];
        global.window = global;
        global.addEventListener = () => {};
        global.document = {
            addEventListener: () => {},
            getElementById: () => null,
            hidden: false,
            body: { classList: { add: () => {}, toggle: () => {} } },
        };
        global.location = { hash: '#overview' };
        global.globalThis = global;
        global.localStorage = { getItem: () => null, setItem: () => {} };
        global.ENABLE_WORKSPACE_V2 = false;
        global.PollManager = { pauseAll: () => {}, resumeAll: () => {}, destroy: () => {} };
        global.Watchlist = { init: () => calls.push('watchlist:init') };
        global.RealtimeQuotes = {
            onUpdate: () => calls.push('realtime:onUpdate'),
            connect: () => calls.push('realtime:connect'),
        };

        global.App = {
            ensureBundle: async (name) => calls.push(`bundle:${name}`),
            loadOverview: async () => calls.push('overview:load'),
            _syncTabFromHash: () => calls.push('tab:sync'),
            _startMarketRefresh: () => calls.push('market:start'),
            _setTabTitle: () => {},
            fetchJSON: async () => ({}),
            toast: () => {},
        };
        global.App.OverviewRadar = { init: async () => calls.push('radar:init') };
        global.App.Alerts = { init: async () => calls.push('alerts:init') };

        vm.runInThisContext(fs.readFileSync('dashboard/static/app-bootstrap.js', 'utf8'));
        App.setDefaultDate = () => calls.push('date:default');

        (async () => {
            await App._activateAuthenticatedSession();
            assert.ok(calls.includes('overview:load'));
            assert.ok(calls.includes('radar:init'));
            assert.ok(calls.includes('alerts:init'));
            assert.equal(calls.filter((item) => item === 'bundle:overview').length, 0);
            const firstCount = calls.filter((item) => item === 'radar:init' || item === 'alerts:init').length;

            await App._initOverviewWidgets();
            const secondCount = calls.filter((item) => item === 'radar:init' || item === 'alerts:init').length;
            assert.equal(firstCount, 2);
            assert.equal(secondCount, 2);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_switch_tab_action_can_open_research_datahub_subtab():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        let clickHandler = null;
        const calls = [];
        const event = {
            prevented: false,
            preventDefault() { this.prevented = true; },
            target: {
                closest(selector) {
                    if (selector === '[data-app-action="switch-tab"]') {
                        return { dataset: { tab: 'research', subtab: 'datahub' } };
                    }
                    return null;
                },
            },
        };

        global.window = global;
        global.addEventListener = () => {};
        global.document = {
            addEventListener: (name, handler) => {
                if (name === 'click') clickHandler = handler;
            },
            getElementById: () => null,
            querySelector: () => null,
            hidden: false,
            body: { classList: { add: () => {}, toggle: () => {} } },
        };
        global.location = { hash: '#overview' };
        global.globalThis = global;
        global.localStorage = { getItem: () => null, setItem: () => {} };
        global.ENABLE_WORKSPACE_V2 = false;
        global.PollManager = { pauseAll: () => {}, resumeAll: () => {}, destroy: () => {} };
        global.Watchlist = { init: () => {} };
        global.RealtimeQuotes = { onUpdate: () => {}, connect: () => {} };
        global.Utils = { todayBeijing: () => '2026-05-26', _bjOpts: {} };
        global.App = {
            _appShellBound: false,
            _setAuthGate: () => {},
            _syncTabFromHash: () => {},
            _startMarketRefresh: () => {},
            _setTabTitle: () => {},
            bindTabs: () => {},
            bindStaticActions: () => {},
            _initTableSorting: () => {},
            _initCommandPalette: () => {},
            _initGlobalShortcuts: () => {},
            _initPWA: () => {},
            switchTab: async (tab, options) => calls.push({ tab, options }),
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/app-bootstrap.js', 'utf8'));
        App.setDefaultDate = () => {};
        App._startAuthenticatedApp();

        assert.equal(typeof clickHandler, 'function');
        clickHandler(event);
        assert.equal(event.prevented, true);
        assert.deepEqual(calls, [{ tab: 'research', options: { subtab: 'datahub' } }]);
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_switch_tab_honors_requested_research_subtab():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        const activated = [];
        const panel = {
            id: 'tab-research',
            classList: { contains: () => true, toggle: () => {} },
            setAttribute: () => {},
            removeAttribute: () => {},
        };

        global.window = global;
        global.dispatchEvent = () => {};
        global.document = {
            title: '',
            getElementById: (id) => id === 'tab-research' ? panel : null,
            querySelectorAll: (selector) => selector === '.tab-panel' ? [panel] : [],
            querySelector: (selector) => {
                if (selector === '.research-sub-tab.active') return { dataset: { subtab: 'valuation' } };
                return null;
            },
        };
        global.location = { hash: '#overview' };
        global.history = { replaceState: () => {} };
        global.requestAnimationFrame = (fn) => fn();
        global.Event = function Event(name) { this.name = name; };
        global.App = {
            _tabAlias: {},
            _tabCache: {},
            ensureBundle: async () => {},
            bindBacktest: () => {},
            bindOptimize: () => {},
            bindSensitivity: () => {},
            bindStrategyChips: () => {},
            _initResearchSubTabs: () => {},
            _startMarketRefresh: () => {},
            _stopMarketRefresh: () => {},
        };

        vm.runInThisContext(fs.readFileSync('dashboard/static/core/app-shell.js', 'utf8'));
        App._activateResearchSubTab = async (subtab) => activated.push(subtab);

        (async () => {
            await App.switchTab('research', { subtab: 'datahub' });
            assert.deepEqual(activated, ['datahub']);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr


def test_research_subtab_click_activates_requested_panel_without_reverting():
    script = textwrap.dedent(
        r"""
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const vm = require('node:vm');

        function makeClassList(initial = []) {
            const values = new Set(initial);
            return {
                add: (...classes) => classes.forEach((item) => values.add(item)),
                remove: (...classes) => classes.forEach((item) => values.delete(item)),
                contains: (item) => values.has(item),
                toggle: (item, force) => {
                    if (force === undefined ? !values.has(item) : force) {
                        values.add(item);
                    } else {
                        values.delete(item);
                    }
                },
            };
        }

        const handlers = {};
        const buttons = {
            valuation: {
                dataset: { subtab: 'valuation' },
                classList: makeClassList(['active']),
                attributes: { 'aria-selected': 'true' },
                addEventListener: (name, handler) => { handlers.valuation = handler; },
                setAttribute(name, value) { this.attributes[name] = value; },
            },
            datahub: {
                dataset: { subtab: 'datahub' },
                classList: makeClassList(),
                attributes: { 'aria-selected': 'false' },
                addEventListener: (name, handler) => { handlers.datahub = handler; },
                setAttribute(name, value) { this.attributes[name] = value; },
            },
        };
        const panels = {
            valuation: { id: 'research-panel-valuation', classList: makeClassList(['active']) },
            datahub: { id: 'research-panel-datahub', classList: makeClassList() },
        };
        const calls = [];

        global.window = global;
        global.dispatchEvent = () => {};
        global.document = {
            getElementById: (id) => {
                if (id === 'research-panel-valuation') return panels.valuation;
                if (id === 'research-panel-datahub') return panels.datahub;
                if (id === 'tab-research') return { querySelector: () => null };
                return null;
            },
            querySelectorAll: (selector) => {
                if (selector === '.research-sub-tab') return Object.values(buttons);
                if (selector === '.research-sub-panel') return Object.values(panels);
                return [];
            },
            querySelector: (selector) => {
                if (selector === '.research-sub-tab.active') return buttons.valuation;
                if (selector === '#tab-research > .page-header') return null;
                return null;
            },
        };
        global.requestAnimationFrame = (fn) => fn();
        global.Event = function Event(name) { this.name = name; };
        global.App = {
            _researchMoved: true,
            _researchTabsInited: false,
            _researchSession: {},
            _tabCache: {},
            _getLegacyActionButton: () => null,
            _getResearchHeaderActionButton: () => null,
            ensureBundle: async (name) => calls.push(`bundle:${name}`),
        };
        global.ResearchDataHub = { init: () => calls.push('datahub:init') };

        vm.runInThisContext(fs.readFileSync('dashboard/static/core/app-shell.js', 'utf8'));

        (async () => {
            App._initResearchSubTabs();
            assert.equal(typeof handlers.datahub, 'function');
            await handlers.datahub();

            assert.equal(App._researchActiveSubtab, 'datahub');
            assert.equal(buttons.datahub.classList.contains('active'), true);
            assert.equal(buttons.valuation.classList.contains('active'), false);
            assert.equal(panels.datahub.classList.contains('active'), true);
            assert.equal(panels.valuation.classList.contains('active'), false);
            assert.deepEqual(calls, ['bundle:research', 'datahub:init']);
        })().catch((error) => {
            console.error(error);
            process.exit(1);
        });
        """
    )

    result = run_node(script)

    assert result.returncode == 0, result.stderr
