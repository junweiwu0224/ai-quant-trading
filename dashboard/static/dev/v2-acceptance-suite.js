#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const STATIC_DIR = path.resolve(__dirname, '..');
const CORE_FILES = Object.freeze([
    'core/intent-bus.js',
    'core/global-stock-store.js',
    'core/action-registry.js',
    'core/degraded-mode.js',
    'core/right-rail-controller.js',
    'core/panel-lifecycle.js',
    'core/local-mcp.js',
    'core/stock-search-service.js',
    'core/stock-actions.js',
    'core/business-adapter.js',
    'core/command-palette.js',
]);
const AUDIT_STOCK_CODE = '600519';
const SUITE_SOURCE = 'v2-acceptance-suite';
const INVALID_NUMERIC_CODE = 123456;
const WATCHLIST_GUARD_REASON = 'stock_code_required';
const WATCHLIST_GUARD_CODE = 'STOCK_CODE_REQUIRED';
const WATCHLIST_WRITE_API_PATTERN = /\/api\/watchlist/;
const WATCHLIST_WRITE_PATTERN = /(?:fetch|fetchJSON)\s*\([\s\S]{0,260}?\/api\/watchlist[\s\S]{0,360}?method:\s*['"](?:POST|DELETE)['"]/g;
const WATCHLIST_COMMIT_METHOD_PATTERN = /async\s+_commitWatchlist(?:Add|Remove)\s*\([\s\S]*?\n    },/g;

function makeElement() {
    return {
        style: {},
        value: '',
        innerHTML: '',
        textContent: '',
        className: '',
        hidden: false,
        dataset: {},
        children: [],
        classList: {
            toggle() {},
            add() {},
            remove() {},
            contains() {
                return false;
            },
        },
        setAttribute() {},
        getAttribute() {
            return null;
        },
        dispatchEvent() {},
        appendChild() {},
        querySelector() {
            return null;
        },
        querySelectorAll() {
            return [];
        },
        addEventListener() {},
        removeEventListener() {},
        focus() {},
        click() {},
    };
}

function createWindowObject() {
    const listeners = {};
    const windowObject = {
        console,
        setTimeout,
        clearTimeout,
        requestAnimationFrame(callback) {
            return setTimeout(callback, 0);
        },
        cancelAnimationFrame(timerId) {
            clearTimeout(timerId);
        },
        navigator: { onLine: true },
        addEventListener(eventName, handler) {
            listeners[eventName] = listeners[eventName] || [];
            listeners[eventName].push(handler);
        },
        removeEventListener(eventName, handler) {
            const currentHandlers = listeners[eventName] || [];
            listeners[eventName] = currentHandlers.filter((item) => item !== handler);
        },
        dispatchBrowserEvent(eventName) {
            (listeners[eventName] || []).slice().forEach((handler) => handler());
        },
    };

    windowObject.window = windowObject;
    windowObject.self = windowObject;
    windowObject.globalThis = windowObject;
    windowObject.Event = function Event(type, init) {
        this.type = type;
        this.bubbles = init && init.bubbles;
    };
    windowObject.document = {
        documentElement: makeElement(),
        body: makeElement(),
        getElementById() {
            return makeElement();
        },
        querySelector() {
            return null;
        },
        querySelectorAll() {
            return [];
        },
        createElement() {
            return makeElement();
        },
    };
    windowObject.MutationObserver = function MutationObserver() {
        this.observe = function observe() {};
        this.disconnect = function disconnect() {};
    };
    windowObject.SearchBox = function SearchBox() {
        this.setDataSource = function setDataSource() {};
        this.onSelect = function onSelect() {};
        this.setValue = function setValue() {};
    };
    windowObject.App = {
        _lastTab: null,
        _lastWatchlistCode: null,
        switchTab(tabName) {
            this._lastTab = tabName;
        },
        addToWatchlist: async function addToWatchlist(code) {
            this._lastWatchlistCode = code;
            return {
                ok: true,
                code,
            };
        },
        toast() {},
        watchlistCache: [],
        closeOffcanvas() {},
        escapeHTML(value) {
            return String(value);
        },
    };
    windowObject.StockDetail = {
        _lastOpenCode: null,
        async open(code) {
            this._lastOpenCode = code;
            return { ok: true, code };
        },
    };
    windowObject.PaperTrading = {
        _loadQuotePreview() {},
    };

    return windowObject;
}

function loadCoreFiles(windowObject) {
    const context = vm.createContext(windowObject);
    CORE_FILES.forEach((relativePath) => {
        const absolutePath = path.join(STATIC_DIR, relativePath);
        const code = fs.readFileSync(absolutePath, 'utf8');
        vm.runInContext(code, context, { filename: relativePath });
    });
}

function createRecorder() {
    const results = [];

    function pass(name, detail) {
        const safeDetail = detail || '';
        results.push({ ok: true, name, detail: safeDetail });
        console.log(`[PASS] ${name}${safeDetail ? ` - ${safeDetail}` : ''}`);
    }

    function fail(name, detail) {
        const safeDetail = detail || 'unknown error';
        results.push({ ok: false, name, detail: safeDetail });
        console.error(`[FAIL: ${safeDetail}] ${name}`);
    }

    return {
        results,
        pass,
        fail,
    };
}

function createWatchlistPreconditions() {
    return [
        {
            type: 'stock_code_required',
            reason: WATCHLIST_GUARD_REASON,
            code: WATCHLIST_GUARD_CODE,
        },
    ];
}

function cloneValue(value) {
    if (value == null) {
        return value;
    }

    return JSON.parse(JSON.stringify(value));
}

function isPlainObject(value) {
    return Object.prototype.toString.call(value) === '[object Object]';
}

function extractCode(value) {
    const candidates = [
        value,
        value && value.payload,
        value && value.input,
        value && value.stock,
        value && value.builtPayload,
        value && value.builtPayload && value.builtPayload.stock,
    ];

    for (const candidate of candidates) {
        if (!candidate) {
            continue;
        }

        if (typeof candidate === 'string' && candidate.trim()) {
            return candidate.trim();
        }

        if (isPlainObject(candidate) && typeof candidate.code === 'string' && candidate.code.trim()) {
            return candidate.code.trim();
        }
    }

    return '';
}

function createWatchlistActionDefinition(actionId, title, keywords, handler) {
    const preconditions = createWatchlistPreconditions();
    return {
        id: actionId,
        title,
        category: 'stock',
        description: title,
        keywords: keywords.slice(),
        enabled: true,
        visible: true,
        metadata: {
            actionId,
            riskLevel: 'medium',
            preconditions: cloneValue(preconditions),
            input: {
                required: ['code'],
                code: 'string',
            },
        },
        guard(context) {
            const code = extractCode(context);
            if (code) {
                return { ok: true, reason: null, code: null };
            }
            return {
                ok: false,
                reason: WATCHLIST_GUARD_REASON,
                code: WATCHLIST_GUARD_CODE,
            };
        },
        buildPayload(context) {
            const code = extractCode(context);
            if (!code) {
                throw new Error('Stock code is required');
            }
            return {
                stock: { code },
                preconditions: cloneValue(preconditions),
            };
        },
        handler,
    };
}

function registerV2AcceptanceActions(windowObject, recorder) {
    const registry = windowObject.ActionRegistry;
    if (!registry || typeof registry.register !== 'function' || typeof registry.has !== 'function') {
        recorder.fail('action registry available', 'register/has missing');
        return { traceProbe: { captured: null } };
    }

    const traceProbe = {
        captured: null,
        handler(context) {
            this.captured = {
                traceId: context.traceId,
                requestId: context.requestId,
                source: context.source,
                payload: cloneValue(context.payload),
                builtPayload: cloneValue(context.builtPayload),
            };
            return {
                ok: true,
                traceId: context.traceId,
                requestId: context.requestId,
                source: context.source,
            };
        },
    };

    const paletteProbe = {
        captured: null,
        handler(context) {
            this.captured = {
                traceId: context.traceId,
                requestId: context.requestId,
                source: context.source,
                payload: cloneValue(context.payload),
                metadata: cloneValue(context.metadata),
            };
            return {
                ok: true,
                code: context.payload && context.payload.code,
                traceId: context.traceId,
                requestId: context.requestId,
                source: context.source,
            };
        },
    };

    if (!registry.has('probe_trace_action')) {
        registry.register(
            createWatchlistActionDefinition(
                'probe_trace_action',
                'Trace 穿透探针',
                ['trace', 'probe', 'diagnostic'],
                async (context) => traceProbe.handler(context)
            )
        );
    }

    if (!registry.has('palette_probe_action')) {
        registry.register({
            id: 'palette_probe_action',
            title: 'Palette Probe Action',
            description: 'Command palette execution probe',
            category: 'stock',
            keywords: ['palette-probe', 'command', 'probe'],
            visible: true,
            enabled: true,
            metadata: { code: AUDIT_STOCK_CODE, suite: SUITE_SOURCE },
            guard(context) {
                const code = context && context.payload && typeof context.payload.code === 'string' ? context.payload.code.trim() : '';
                return code ? { ok: true } : { ok: false, reason: WATCHLIST_GUARD_REASON, code: WATCHLIST_GUARD_CODE };
            },
            handler(context) {
                return paletteProbe.handler(context);
            },
        });
    }

    return { traceProbe, paletteProbe };
}

async function assertWatchlistActionShape(windowObject, action, expectedId, expectedCategory) {
    if (!action || action.id !== expectedId) {
        return { ok: false, reason: 'missing_or_wrong_id' };
    }

    if (typeof action.category !== 'string' || !action.category.trim()) {
        return { ok: false, reason: 'missing_category' };
    }

    if (action.category !== expectedCategory) {
        return { ok: false, reason: `category_mismatch:${action.category}` };
    }

    if (!Array.isArray(action.keywords) || action.keywords.length === 0) {
        return { ok: false, reason: 'missing_keywords' };
    }

    const hasWatchlistKeyword = action.keywords.some((keyword) => {
        return typeof keyword === 'string' && (keyword.includes('watchlist') || keyword.includes('自选'));
    });
    if (!hasWatchlistKeyword) {
        return { ok: false, reason: 'watchlist_keywords_missing' };
    }

    const invalidCases = [
        {
            label: 'missing code',
            input: {},
        },
        {
            label: 'numeric code',
            input: { code: INVALID_NUMERIC_CODE },
        },
    ];

    for (const invalidCase of invalidCases) {
        const result = await windowObject.LocalMCP.canInvoke({
            toolId: expectedId,
            input: invalidCase.input,
            source: SUITE_SOURCE,
            traceId: windowObject.LocalMCP.createTraceId(SUITE_SOURCE),
            requestId: `${expectedId}-${invalidCase.label.replace(/\s+/g, '-')}`,
        });
        if (!(result.ok === true && result.callable === false && result.reason === WATCHLIST_GUARD_REASON && result.code === WATCHLIST_GUARD_CODE)) {
            return {
                ok: false,
                reason: `invalid_input_not_blocked:${invalidCase.label}`,
                detail: JSON.stringify(result),
            };
        }
    }

    const validResult = await windowObject.LocalMCP.canInvoke({
        toolId: expectedId,
        input: { code: AUDIT_STOCK_CODE },
        source: SUITE_SOURCE,
        traceId: windowObject.LocalMCP.createTraceId(SUITE_SOURCE),
        requestId: `${expectedId}-valid`,
    });
    if (!(validResult.ok === true && validResult.callable === true)) {
        return {
            ok: false,
            reason: 'valid_input_not_callable',
            detail: JSON.stringify(validResult),
        };
    }

    if (action.metadata && action.metadata.input) {
        const inputSchema = action.metadata.input;
        if (inputSchema.code !== 'string') {
            return { ok: false, reason: 'input_schema_code_not_string' };
        }
        if (!Array.isArray(inputSchema.required) || !inputSchema.required.includes('code')) {
            return { ok: false, reason: 'input_schema_required_code_missing' };
        }
    }

    return { ok: true };
}

function assertInvocationShape(result, expectedStatus) {
    if (!result || result.status !== expectedStatus) {
        return { ok: false, reason: `expected_${expectedStatus}` };
    }
    return { ok: true };
}

async function auditCoreMounts(windowObject, recorder) {
    const required = [
        'IntentBus',
        'GlobalStockStore',
        'ActionRegistry',
        'DegradedModeManager',
        'RightRailController',
        'PanelLifecycle',
        'LocalMCP',
        'StockSearchService',
        'StockActions',
        'BusinessAdapter',
        'CommandPalette',
    ];

    required.forEach((key) => {
        if (windowObject[key]) {
            recorder.pass(`${key} mounted`);
            return;
        }
        recorder.fail(`${key} mounted`, 'missing');
    });
}

async function auditActionContracts(windowObject, recorder) {
    const addAction = windowObject.ActionRegistry.get('add_to_watchlist');
    const removeAction = windowObject.ActionRegistry.get('remove_from_watchlist');
    const expectedCategory = addAction && typeof addAction.category === 'string' ? addAction.category : 'stock';

    const addShape = await assertWatchlistActionShape(windowObject, addAction, 'add_to_watchlist', expectedCategory);
    const removeShape = await assertWatchlistActionShape(windowObject, removeAction, 'remove_from_watchlist', expectedCategory);

    if (addShape.ok) {
        recorder.pass('add_to_watchlist schema', 'category + keywords + code:string behavioral guard');
    } else {
        recorder.fail('add_to_watchlist schema', addShape.detail || addShape.reason);
    }

    if (removeShape.ok) {
        recorder.pass('remove_from_watchlist schema', 'category + keywords + code:string behavioral guard');
    } else {
        recorder.fail('remove_from_watchlist schema', removeShape.detail || removeShape.reason);
    }

    const addMeta = addAction && addAction.metadata ? addAction.metadata.preconditions : null;
    const removeMeta = removeAction && removeAction.metadata ? removeAction.metadata.preconditions : null;
    if (JSON.stringify(addMeta) === JSON.stringify(removeMeta)) {
        recorder.pass('watchlist action preconditions are symmetric');
    } else {
        recorder.fail('watchlist action preconditions are symmetric', 'precondition mismatch');
    }

    const addSchema = addAction && addAction.metadata ? addAction.metadata.input || null : null;
    const removeSchema = removeAction && removeAction.metadata ? removeAction.metadata.input || null : null;
    if (removeSchema && removeSchema.code === 'string' && Array.isArray(removeSchema.required) && removeSchema.required.includes('code')) {
        recorder.pass('remove_from_watchlist input schema declared', 'required(code:string)');
    } else {
        recorder.fail('remove_from_watchlist input schema declared', 'schema missing');
    }

    if (!addSchema || JSON.stringify(addSchema) === JSON.stringify(removeSchema)) {
        recorder.pass('watchlist action input schema compatible', addSchema ? 'explicit symmetry' : 'add_to_watchlist uses behavioral guard');
    } else {
        recorder.fail('watchlist action input schema compatible', 'schema mismatch');
    }
}

async function auditTracePropagation(windowObject, recorder, traceProbe) {
    const traceId = windowObject.LocalMCP.createTraceId(SUITE_SOURCE);
    const requestId = 'v2-acceptance-request';

    const result = await windowObject.LocalMCP.invoke({
        toolId: 'probe_trace_action',
        input: { code: AUDIT_STOCK_CODE },
        source: SUITE_SOURCE,
        traceId,
        requestId,
    });

    const statusCheck = assertInvocationShape(result, 'success');
    if (!statusCheck.ok) {
        recorder.fail('trace propagation invoke', statusCheck.reason);
        return;
    }

    if (result.traceId === traceId && result.requestId === requestId && result.source === SUITE_SOURCE) {
        recorder.pass('trace propagation invoke', `traceId=${traceId}`);
    } else {
        recorder.fail('trace propagation invoke', `trace/request/source mismatch: ${JSON.stringify(result)}`);
    }

    const captured = traceProbe.captured;
    if (
        captured &&
        captured.traceId === traceId &&
        captured.requestId === requestId &&
        captured.source === SUITE_SOURCE
    ) {
        recorder.pass('trace propagation to action handler', `traceId=${captured.traceId}`);
    } else {
        recorder.fail('trace propagation to action handler', '末端 action 未完整接收 trace/request/source');
    }
}

async function auditCommandPaletteActionFlow(windowObject, recorder, paletteProbe) {
    const palette = windowObject.CommandPalette;
    const traceId = 'v2-palette-trace';
    const requestId = 'v2-palette-request';

    windowObject.StockSearchService.configureAdapter({
        search() {
            return Promise.resolve([
                {
                    code: AUDIT_STOCK_CODE,
                    name: '贵州茅台',
                    market: 'SH',
                    exchange: 'SSE',
                    label: `${AUDIT_STOCK_CODE} 贵州茅台`,
                    keywords: [AUDIT_STOCK_CODE, '贵州茅台'],
                },
            ]);
        },
    });

    await palette.open({ mode: 'mixed', query: AUDIT_STOCK_CODE, source: SUITE_SOURCE, traceId: 'v2-palette-stock-query' });
    const stockState = palette.getState();
    const stockCodes = stockState.stockResults.map((item) => item.code);
    if (stockCodes.includes(AUDIT_STOCK_CODE)) {
        recorder.pass('command palette builds stock candidates');
    } else {
        recorder.fail('command palette builds stock candidates', JSON.stringify({ stockCodes }));
    }

    await palette.setQuery({ query: 'palette-probe', source: SUITE_SOURCE, traceId, requestId: 'v2-palette-action-query' });
    const state = palette.getState();
    const actionIds = state.actionResults.map((item) => item.id);
    if (actionIds.includes('palette_probe_action')) {
        recorder.pass('command palette builds action candidates');
    } else {
        recorder.fail('command palette builds action candidates', JSON.stringify({ actionIds }));
    }

    const probeItemIndex = state.mergedResults.findIndex((item) => item.kind === 'action' && item.id === 'palette_probe_action');
    const selected = palette.selectIndex({ index: probeItemIndex, source: SUITE_SOURCE, traceId });
    if (selected.ok === true && selected.selectedItem && selected.selectedItem.id === 'palette_probe_action') {
        recorder.pass('command palette selects action candidate');
    } else {
        recorder.fail('command palette selects action candidate', JSON.stringify(selected));
    }

    const canInvoke = await windowObject.LocalMCP.canInvoke({
        toolId: 'palette_probe_action',
        input: { code: AUDIT_STOCK_CODE },
        source: SUITE_SOURCE,
        traceId,
        requestId,
    });
    if (canInvoke.ok === true && canInvoke.callable === true) {
        recorder.pass('command palette candidate is invokable through LocalMCP');
    } else {
        recorder.fail('command palette candidate is invokable through LocalMCP', JSON.stringify(canInvoke));
    }

    const executeResult = await palette.executeSelection({
        closeOnSuccess: false,
        source: SUITE_SOURCE,
        traceId,
        requestId,
    });
    const captured = paletteProbe.captured;
    if (
        executeResult.ok === true
        && executeResult.status === 'success'
        && captured
        && captured.traceId === traceId
        && captured.requestId === requestId
        && captured.source === SUITE_SOURCE
        && captured.payload
        && captured.payload.code === AUDIT_STOCK_CODE
    ) {
        recorder.pass('command palette executes action through LocalMCP with trace');
    } else {
        recorder.fail('command palette executes action through LocalMCP with trace', JSON.stringify({ executeResult, captured }));
    }

    windowObject.ActionRegistry.setEnabled({ actionId: 'palette_probe_action', enabled: false });
    const disabledResult = await palette.executeItem({
        item: selected.selectedItem,
        closeOnSuccess: false,
        source: SUITE_SOURCE,
        traceId: 'v2-palette-disabled',
        requestId: 'v2-palette-disabled-request',
    });
    if (disabledResult.ok === false && disabledResult.status === 'blocked') {
        recorder.pass('command palette respects disabled LocalMCP action');
    } else {
        recorder.fail('command palette respects disabled LocalMCP action', JSON.stringify(disabledResult));
    }
    windowObject.ActionRegistry.setEnabled({ actionId: 'palette_probe_action', enabled: true });

    const missingResult = await palette.executeItem({
        item: {
            kind: 'action',
            id: 'missing_palette_action',
            title: 'Missing Palette Action',
            metadata: { code: AUDIT_STOCK_CODE },
        },
        closeOnSuccess: false,
        source: SUITE_SOURCE,
        traceId: 'v2-palette-missing',
        requestId: 'v2-palette-missing-request',
    });
    if (missingResult.ok === false && missingResult.status === 'not_found') {
        recorder.pass('command palette reports missing LocalMCP action');
    } else {
        recorder.fail('command palette reports missing LocalMCP action', JSON.stringify(missingResult));
    }
}

async function auditDegradedWriteProtection(windowObject, recorder) {
    windowObject.DegradedModeManager.setDegradedState('network-offline', {
        domain: 'network',
        level: 'critical',
        mode: 'blocked',
        reason: 'V2 acceptance offline simulation',
        source: 'manual',
        affects: {
            actions: ['remove_from_watchlist'],
        },
    });

    const addAction = windowObject.ActionRegistry.get('add_to_watchlist');
    const removeAction = windowObject.ActionRegistry.get('remove_from_watchlist');
    if (addAction && addAction.enabled === false && removeAction && removeAction.enabled === false) {
        recorder.pass('offline disables watchlist writes', 'add/remove_from_watchlist are disabled');
    } else {
        recorder.fail('offline disables watchlist writes', 'write actions remain enabled');
    }

    const canAdd = await windowObject.LocalMCP.canInvoke({
        toolId: 'add_to_watchlist',
        input: { code: AUDIT_STOCK_CODE },
        source: SUITE_SOURCE,
        traceId: windowObject.LocalMCP.createTraceId(SUITE_SOURCE),
        requestId: 'v2-acceptance-add-offline',
    });
    const canRemove = await windowObject.LocalMCP.canInvoke({
        toolId: 'remove_from_watchlist',
        input: { code: AUDIT_STOCK_CODE },
        source: SUITE_SOURCE,
        traceId: windowObject.LocalMCP.createTraceId(SUITE_SOURCE),
        requestId: 'v2-acceptance-remove-offline',
    });

    if (canAdd.ok === true && canAdd.callable === false && canAdd.reason === 'action_disabled') {
        recorder.pass('offline blocks add_to_watchlist canInvoke');
    } else {
        recorder.fail('offline blocks add_to_watchlist canInvoke', JSON.stringify(canAdd));
    }

    if (canRemove.ok === true && canRemove.callable === false && canRemove.reason === 'action_disabled') {
        recorder.pass('offline blocks remove_from_watchlist canInvoke');
    } else {
        recorder.fail('offline blocks remove_from_watchlist canInvoke', JSON.stringify(canRemove));
    }

    let invokeAdd;
    try {
        invokeAdd = await windowObject.LocalMCP.invoke({
            toolId: 'add_to_watchlist',
            input: { code: AUDIT_STOCK_CODE },
            source: SUITE_SOURCE,
            traceId: windowObject.LocalMCP.createTraceId(SUITE_SOURCE),
            requestId: 'v2-acceptance-add-invoke',
        });
    } catch (error) {
        recorder.fail('offline invoke add_to_watchlist blocked', `unexpected throw: ${error.message}`);
    }

    let invokeRemove;
    try {
        invokeRemove = await windowObject.LocalMCP.invoke({
            toolId: 'remove_from_watchlist',
            input: { code: AUDIT_STOCK_CODE },
            source: SUITE_SOURCE,
            traceId: windowObject.LocalMCP.createTraceId(SUITE_SOURCE),
            requestId: 'v2-acceptance-remove-invoke',
        });
    } catch (error) {
        recorder.fail('offline invoke remove_from_watchlist blocked', `unexpected throw: ${error.message}`);
    }

    if (invokeAdd && invokeAdd.status === 'blocked' && invokeAdd.reason === 'action_disabled') {
        recorder.pass('offline invoke add_to_watchlist blocked');
    } else if (invokeAdd) {
        recorder.fail('offline invoke add_to_watchlist blocked', JSON.stringify(invokeAdd));
    }

    if (invokeRemove && invokeRemove.status === 'blocked' && invokeRemove.reason === 'action_disabled') {
        recorder.pass('offline invoke remove_from_watchlist blocked');
    } else if (invokeRemove) {
        recorder.fail('offline invoke remove_from_watchlist blocked', JSON.stringify(invokeRemove));
    }

    windowObject.DegradedModeManager.recoverState('network-offline', {
        source: 'manual',
        reason: 'V2 acceptance cleanup',
        silent: true,
    });

    const recoveredAdd = windowObject.ActionRegistry.get('add_to_watchlist');
    const recoveredRemove = windowObject.ActionRegistry.get('remove_from_watchlist');
    if (recoveredAdd && recoveredAdd.enabled === true && recoveredRemove && recoveredRemove.enabled === true) {
        recorder.pass('offline recovery restores watchlist writes');
    } else {
        recorder.fail('offline recovery restores watchlist writes', 'actions not restored');
    }
}

function createPanelLifecycleProbe(panelId, sink) {
    return {
        id: panelId,
        title: `Probe ${panelId}`,
        order: 1,
        metadata: { suite: SUITE_SOURCE },
        mount(context) {
            sink.push({ panelId, phase: 'mount', code: context.activeStock.code || null });
            return {
                activate(activateContext) {
                    sink.push({ panelId, phase: 'activate', code: activateContext.activeStock.code || null });
                },
                update(updateContext) {
                    sink.push({ panelId, phase: 'update', code: updateContext.activeStock.code || null });
                },
                deactivate(deactivateContext) {
                    sink.push({ panelId, phase: 'deactivate', code: deactivateContext.activeStock.code || null });
                },
                unmount(unmountContext) {
                    sink.push({ panelId, phase: 'unmount', code: unmountContext.activeStock.code || null });
                },
                destroy(destroyContext) {
                    sink.push({ panelId, phase: 'destroy', code: destroyContext.activeStock.code || null });
                },
            };
        },
    };
}

function hasLifecycleEvent(events, panelId, phase, code) {
    return events.some((event) => {
        return event.panelId === panelId
            && event.phase === phase
            && (code === undefined || event.code === code);
    });
}

async function auditRightRailPanelLifecycle(windowObject, recorder) {
    const rail = windowObject.RightRailController;
    const lifecycle = windowObject.PanelLifecycle;
    const events = [];
    const root = makeElement();

    rail.reset();
    await lifecycle.reset();
    lifecycle.mountRoot({ root, source: SUITE_SOURCE, traceId: lifecycle.createTraceId(SUITE_SOURCE) });
    lifecycle.registerMany([
        createPanelLifecycleProbe('probe-stock-panel', events),
        createPanelLifecycleProbe('probe-news-panel', events),
    ]);

    windowObject.GlobalStockStore.setActiveStock({
        identity: { code: '600000', name: '浦发银行' },
        source: SUITE_SOURCE,
        traceId: 'v2-panel-stock-a',
    });
    rail.activatePanel({
        panelId: 'probe-stock-panel',
        panelParams: { code: '600000' },
        source: SUITE_SOURCE,
        traceId: 'v2-panel-open-a',
    });
    await lifecycle.syncWithRail({ source: SUITE_SOURCE, traceId: 'v2-panel-sync-a' });

    const firstState = lifecycle.getState();
    if (rail.getState().isOpen === true && firstState.activePanelId === 'probe-stock-panel' && firstState.mountedPanelId === 'probe-stock-panel') {
        recorder.pass('right rail opens and mounts active panel');
    } else {
        recorder.fail('right rail opens and mounts active panel', JSON.stringify({ rail: rail.getState(), lifecycle: firstState }));
    }

    windowObject.GlobalStockStore.setActiveStock({
        identity: { code: '600519', name: '贵州茅台' },
        source: SUITE_SOURCE,
        traceId: 'v2-panel-stock-b',
    });
    rail.activatePanel({
        panelId: 'probe-stock-panel',
        panelParams: { code: '600519' },
        source: SUITE_SOURCE,
        traceId: 'v2-panel-open-b',
    });
    await lifecycle.syncWithRail({ source: SUITE_SOURCE, traceId: 'v2-panel-sync-b' });

    const stockMountCount = events.filter((event) => event.panelId === 'probe-stock-panel' && event.phase === 'mount').length;
    if (stockMountCount === 1 && hasLifecycleEvent(events, 'probe-stock-panel', 'update', '600519')) {
        recorder.pass('right rail reuses mounted panel across stock switches');
    } else {
        recorder.fail('right rail reuses mounted panel across stock switches', JSON.stringify(events));
    }

    rail.activatePanel({
        panelId: 'probe-news-panel',
        panelParams: { code: '600519' },
        source: SUITE_SOURCE,
        traceId: 'v2-panel-open-news',
    });
    await lifecycle.syncWithRail({ source: SUITE_SOURCE, traceId: 'v2-panel-sync-news' });

    const secondState = lifecycle.getState();
    if (
        secondState.mountedPanelId === 'probe-news-panel'
        && hasLifecycleEvent(events, 'probe-stock-panel', 'deactivate')
        && hasLifecycleEvent(events, 'probe-stock-panel', 'unmount')
        && hasLifecycleEvent(events, 'probe-news-panel', 'mount')
        && hasLifecycleEvent(events, 'probe-news-panel', 'activate')
    ) {
        recorder.pass('right rail swaps panels with deactivate and unmount');
    } else {
        recorder.fail('right rail swaps panels with deactivate and unmount', JSON.stringify({ state: secondState, events }));
    }

    rail.deactivatePanel({ closeRail: true, source: SUITE_SOURCE, traceId: 'v2-panel-close' });
    await lifecycle.syncWithRail({ source: SUITE_SOURCE, traceId: 'v2-panel-sync-close' });

    const closedState = lifecycle.getState();
    if (rail.getState().isOpen === false && closedState.activePanelId === null && closedState.mountedPanelId === null) {
        recorder.pass('right rail close deactivates and unmounts panel');
    } else {
        recorder.fail('right rail close deactivates and unmounts panel', JSON.stringify({ rail: rail.getState(), lifecycle: closedState }));
    }

    rail.activatePanel({
        panelId: 'missing-panel',
        panelParams: { code: '600519' },
        source: SUITE_SOURCE,
        traceId: 'v2-panel-missing',
    });
    await lifecycle.syncWithRail({ source: SUITE_SOURCE, traceId: 'v2-panel-sync-missing' });

    const missingState = lifecycle.getState();
    if (missingState.lastError && missingState.lastError.code === 'PANEL_NOT_REGISTERED') {
        recorder.pass('panel lifecycle reports missing active panel');
    } else {
        recorder.fail('panel lifecycle reports missing active panel', JSON.stringify(missingState.lastError));
    }
}

function listStaticFiles(directory, prefix = '') {
    return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
        if (entry.name === 'dev' || entry.name === '.claude') {
            return [];
        }

        const entryPath = path.join(directory, entry.name);
        const relativePath = prefix ? `${prefix}/${entry.name}` : entry.name;
        if (entry.isDirectory()) {
            return listStaticFiles(entryPath, relativePath);
        }
        return entry.isFile() && entry.name.endsWith('.js') ? [relativePath] : [];
    });
}

function isAllowedWatchlistWrite(relativePath, source, match) {
    if (relativePath !== 'app.js') {
        return false;
    }

    return (source.match(WATCHLIST_COMMIT_METHOD_PATTERN) || []).some((methodSource) => methodSource.includes(match));
}

function auditWatchlistWriteEntrypoints(recorder) {
    const violations = listStaticFiles(STATIC_DIR).flatMap((relativePath) => {
        const source = fs.readFileSync(path.join(STATIC_DIR, relativePath), 'utf8');
        if (!WATCHLIST_WRITE_API_PATTERN.test(source)) {
            return [];
        }

        const matches = source.match(WATCHLIST_WRITE_PATTERN) || [];
        return matches
            .filter((match) => !isAllowedWatchlistWrite(relativePath, source, match))
            .map(() => relativePath);
    });

    if (violations.length === 0) {
        recorder.pass('watchlist writes are confined to app commit methods');
    } else {
        recorder.fail('watchlist writes are confined to app commit methods', [...new Set(violations)].join(', '));
    }
}

function auditLegacyFallbacks(windowObject, recorder) {
    const appSource = fs.readFileSync(path.join(STATIC_DIR, 'app.js'), 'utf8');
    const legacyFallbackMarkers = [
        '_openStockDetailLegacy',
        'LEGACY_FALLBACK_OPEN_DETAIL',
        'LEGACY_FALLBACK_ADD_WATCHLIST',
        'LEGACY_FALLBACK_FAILED',
    ];
    const matchedFallbackMarkers = legacyFallbackMarkers.filter((marker) => appSource.includes(marker));
    if (matchedFallbackMarkers.length === 0) {
        recorder.pass('app stock actions have no legacy fallback markers');
    } else {
        recorder.fail('app stock actions have no legacy fallback markers', matchedFallbackMarkers.join(', '));
    }

    if (windowObject.ActionRegistry.has('remove_from_watchlist')) {
        recorder.pass('remove_from_watchlist registered');
    } else {
        recorder.fail('remove_from_watchlist registered', 'missing');
    }
}

async function runAcceptanceSuite() {
    const recorder = createRecorder();
    const windowObject = createWindowObject();

    loadCoreFiles(windowObject);
    const { traceProbe, paletteProbe } = registerV2AcceptanceActions(windowObject, recorder);
    windowObject.DegradedModeManager.init();

    console.group('V2.1 Architecture Acceptance Suite');

    await auditCoreMounts(windowObject, recorder);
    await auditActionContracts(windowObject, recorder);
    await auditTracePropagation(windowObject, recorder, traceProbe);
    await auditCommandPaletteActionFlow(windowObject, recorder, paletteProbe);
    await auditDegradedWriteProtection(windowObject, recorder);
    await auditRightRailPanelLifecycle(windowObject, recorder);
    auditWatchlistWriteEntrypoints(recorder);
    auditLegacyFallbacks(windowObject, recorder);

    const verdict = recorder.results.every((item) => item.ok) ? '交付合格' : '存在风险';
    console.log(`V2.1 骨架总评：[${verdict}]`);
    console.groupEnd();

    return {
        results: recorder.results,
        verdict,
    };
}

if (require.main === module) {
    runAcceptanceSuite()
        .then(({ verdict }) => {
            if (verdict !== '交付合格') {
                process.exitCode = 1;
            }
        })
        .catch((error) => {
            console.error('[FATAL]', error && error.stack ? error.stack : error);
            process.exitCode = 1;
        });
}

module.exports = {
    runAcceptanceSuite,
};
