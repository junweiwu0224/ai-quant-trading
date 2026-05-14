(function attachRightRailController(global) {
    'use strict';

    if (!global.IntentBus) {
        throw new Error('RightRailController requires window.IntentBus');
    }

    if (!global.GlobalStockStore) {
        throw new Error('RightRailController requires window.GlobalStockStore');
    }

    const RAIL_EVENT_NAMES = Object.freeze({
        OPENED: 'right-rail:opened',
        CLOSED: 'right-rail:closed',
        TOGGLED: 'right-rail:toggled',
        DISPLAY_MODE_CHANGED: 'right-rail:display-mode-changed',
        PANEL_ACTIVATED: 'right-rail:panel-activated',
        PANEL_DEACTIVATED: 'right-rail:panel-deactivated',
        PANEL_PARAMS_CHANGED: 'right-rail:panel-params-changed',
        CONTEXT_SYNCED: 'right-rail:context-synced',
        CONTEXT_CLEARED: 'right-rail:context-cleared',
        WIDTH_CHANGED: 'right-rail:width-changed',
        MOUNTED: 'right-rail:mounted',
        UNMOUNTED: 'right-rail:unmounted',
        RESET: 'right-rail:reset',
    });

    const DISPLAY_MODE = Object.freeze({
        HIDDEN: 'hidden',
        OVERLAY: 'overlay',
        PINNED: 'pinned',
    });

    const DEFAULT_TRACE_PREFIX = 'right-rail';

    function getNow() {
        return Date.now();
    }

    function isPlainObject(value) {
        return Object.prototype.toString.call(value) === '[object Object]';
    }

    function cloneValue(value) {
        if (value === null || value === undefined) {
            return value;
        }

        if (Array.isArray(value)) {
            return value.map((item) => cloneValue(item));
        }

        if (value instanceof Date) {
            return new Date(value.getTime());
        }

        if (isPlainObject(value)) {
            const entries = Object.entries(value).map(([key, entryValue]) => [key, cloneValue(entryValue)]);
            return Object.fromEntries(entries);
        }

        return value;
    }

    function deepFreeze(value) {
        if (!value || typeof value !== 'object' || Object.isFrozen(value)) {
            return value;
        }

        Object.freeze(value);
        Object.keys(value).forEach((key) => {
            deepFreeze(value[key]);
        });
        return value;
    }

    function createRightRailError(message, code) {
        const error = new Error(message);
        error.name = 'RightRailControllerError';
        if (code) {
            error.code = code;
        }
        return error;
    }

    function createInitialState() {
        return {
            isOpen: false,
            displayMode: DISPLAY_MODE.HIDDEN,
            activePanelId: null,
            panelParams: null,
            context: {
                stock: {
                    code: null,
                    name: null,
                    market: null,
                    exchange: null,
                },
                revision: 0,
                source: null,
                traceId: null,
            },
            ui: {
                width: null,
                isMounted: false,
                lastUserActionAt: null,
            },
            meta: {
                openedAt: null,
                lastUpdatedAt: null,
            },
        };
    }

    class RightRailControllerImpl {
        constructor(intentBus, globalStockStore) {
            this._intentBus = intentBus;
            this._globalStockStore = globalStockStore;
            this._listeners = [];
            this._state = createInitialState();
            this._traceSequence = 0;
            this._mountedRoot = null;
            this._storeUnsubscribe = this._globalStockStore.subscribe((storeState) => {
                this._handleStoreChange(storeState);
            });
            this.syncStockContext({
                source: 'right-rail:init',
                traceId: this._createTraceId(DEFAULT_TRACE_PREFIX),
            });
        }

        getState() {
            return this._snapshotState();
        }

        subscribe(listener) {
            if (typeof listener !== 'function') {
                throw createRightRailError('Listener must be a function', 'INVALID_LISTENER');
            }

            this._listeners = [...this._listeners, listener];
            return () => {
                this._listeners = this._listeners.filter((item) => item !== listener);
            };
        }

        open(params) {
            const normalized = this._normalizeOpenParams(params);
            const nextDisplayMode = normalized.displayMode || (this._state.displayMode === DISPLAY_MODE.HIDDEN ? DISPLAY_MODE.OVERLAY : this._state.displayMode);
            const nextPanelId = normalized.panelId == null ? this._state.activePanelId : normalized.panelId;
            const nextPanelParams = normalized.panelId == null && normalized.panelParams == null
                ? this._state.panelParams
                : cloneValue(normalized.panelParams);

            this._setState({
                isOpen: true,
                displayMode: nextDisplayMode,
                activePanelId: nextPanelId,
                panelParams: nextPanelParams,
                ui: {
                    ...this._state.ui,
                    lastUserActionAt: getNow(),
                },
                meta: {
                    ...this._state.meta,
                    openedAt: this._state.isOpen ? this._state.meta.openedAt : getNow(),
                    lastUpdatedAt: getNow(),
                },
            });
            this._syncMountedDom();
            this._emitEvent(RAIL_EVENT_NAMES.OPENED, {
                isOpen: true,
                displayMode: nextDisplayMode,
                activePanelId: nextPanelId,
                source: normalized.source,
                traceId: normalized.traceId,
            });

            return {
                ok: true,
                isOpen: true,
                displayMode: this._state.displayMode,
                activePanelId: this._state.activePanelId,
                traceId: normalized.traceId,
            };
        }

        close(params) {
            const normalized = this._normalizeCloseParams(params);
            const nextPanelId = normalized.preservePanel ? this._state.activePanelId : null;
            const nextPanelParams = normalized.preservePanel ? this._state.panelParams : null;

            this._setState({
                isOpen: false,
                displayMode: DISPLAY_MODE.HIDDEN,
                activePanelId: nextPanelId,
                panelParams: nextPanelParams,
                ui: {
                    ...this._state.ui,
                    lastUserActionAt: getNow(),
                },
                meta: {
                    ...this._state.meta,
                    lastUpdatedAt: getNow(),
                },
            });
            this._syncMountedDom();
            this._emitEvent(RAIL_EVENT_NAMES.CLOSED, {
                isOpen: false,
                activePanelId: this._state.activePanelId,
                source: normalized.source,
                traceId: normalized.traceId,
            });

            return {
                ok: true,
                isOpen: false,
                displayMode: DISPLAY_MODE.HIDDEN,
                activePanelId: this._state.activePanelId,
                traceId: normalized.traceId,
            };
        }

        toggle(params) {
            const normalized = this._normalizeToggleParams(params);
            const result = this._state.isOpen
                ? this.close({
                    preservePanel: normalized.panelId == null,
                    source: normalized.source,
                    traceId: normalized.traceId,
                })
                : this.open({
                    panelId: normalized.panelId,
                    panelParams: null,
                    displayMode: normalized.displayMode,
                    source: normalized.source,
                    traceId: normalized.traceId,
                });

            this._emitEvent(RAIL_EVENT_NAMES.TOGGLED, {
                isOpen: this._state.isOpen,
                displayMode: this._state.displayMode,
                activePanelId: this._state.activePanelId,
                source: normalized.source,
                traceId: normalized.traceId,
            });

            return {
                ok: true,
                isOpen: this._state.isOpen,
                displayMode: this._state.displayMode,
                activePanelId: this._state.activePanelId,
                traceId: normalized.traceId,
                result,
            };
        }

        setDisplayMode(params) {
            const normalized = this._normalizeSetDisplayModeParams(params);
            const nextIsOpen = normalized.displayMode !== DISPLAY_MODE.HIDDEN;

            this._setState({
                isOpen: nextIsOpen,
                displayMode: normalized.displayMode,
                ui: {
                    ...this._state.ui,
                    lastUserActionAt: getNow(),
                },
                meta: {
                    ...this._state.meta,
                    openedAt: nextIsOpen && !this._state.isOpen ? getNow() : this._state.meta.openedAt,
                    lastUpdatedAt: getNow(),
                },
            });
            this._syncMountedDom();
            this._emitEvent(RAIL_EVENT_NAMES.DISPLAY_MODE_CHANGED, {
                isOpen: this._state.isOpen,
                displayMode: this._state.displayMode,
                source: normalized.source,
                traceId: normalized.traceId,
            });

            return {
                ok: true,
                isOpen: this._state.isOpen,
                displayMode: this._state.displayMode,
                traceId: normalized.traceId,
            };
        }

        activatePanel(params) {
            const normalized = this._normalizeActivatePanelParams(params);
            const shouldOpen = normalized.autoOpen !== false;
            const nextDisplayMode = normalized.displayMode
                || (shouldOpen && this._state.displayMode === DISPLAY_MODE.HIDDEN ? DISPLAY_MODE.OVERLAY : this._state.displayMode);

            this._setState({
                activePanelId: normalized.panelId,
                panelParams: cloneValue(normalized.panelParams),
                isOpen: shouldOpen ? true : this._state.isOpen,
                displayMode: shouldOpen ? nextDisplayMode : this._state.displayMode,
                ui: {
                    ...this._state.ui,
                    lastUserActionAt: getNow(),
                },
                meta: {
                    ...this._state.meta,
                    openedAt: shouldOpen && !this._state.isOpen ? getNow() : this._state.meta.openedAt,
                    lastUpdatedAt: getNow(),
                },
            });
            this._syncMountedDom();
            this._emitEvent(RAIL_EVENT_NAMES.PANEL_ACTIVATED, {
                activePanelId: this._state.activePanelId,
                panelParams: cloneValue(this._state.panelParams),
                isOpen: this._state.isOpen,
                displayMode: this._state.displayMode,
                source: normalized.source,
                traceId: normalized.traceId,
            });

            return {
                ok: true,
                activePanelId: this._state.activePanelId,
                panelParams: cloneValue(this._state.panelParams),
                isOpen: this._state.isOpen,
                displayMode: this._state.displayMode,
                traceId: normalized.traceId,
            };
        }

        deactivatePanel(params) {
            const normalized = this._normalizeDeactivatePanelParams(params);
            const nextIsOpen = normalized.closeRail ? false : this._state.isOpen;
            const nextDisplayMode = normalized.closeRail ? DISPLAY_MODE.HIDDEN : this._state.displayMode;

            this._setState({
                activePanelId: null,
                panelParams: null,
                isOpen: nextIsOpen,
                displayMode: nextDisplayMode,
                ui: {
                    ...this._state.ui,
                    lastUserActionAt: getNow(),
                },
                meta: {
                    ...this._state.meta,
                    lastUpdatedAt: getNow(),
                },
            });
            this._syncMountedDom();
            this._emitEvent(RAIL_EVENT_NAMES.PANEL_DEACTIVATED, {
                isOpen: this._state.isOpen,
                displayMode: this._state.displayMode,
                source: normalized.source,
                traceId: normalized.traceId,
            });

            return {
                ok: true,
                activePanelId: null,
                isOpen: this._state.isOpen,
                displayMode: this._state.displayMode,
                traceId: normalized.traceId,
            };
        }

        setPanelParams(params) {
            const normalized = this._normalizeSetPanelParamsParams(params);
            this._setState({
                panelParams: cloneValue(normalized.panelParams),
                ui: {
                    ...this._state.ui,
                    lastUserActionAt: getNow(),
                },
                meta: {
                    ...this._state.meta,
                    lastUpdatedAt: getNow(),
                },
            });
            this._emitEvent(RAIL_EVENT_NAMES.PANEL_PARAMS_CHANGED, {
                activePanelId: this._state.activePanelId,
                panelParams: cloneValue(this._state.panelParams),
                source: normalized.source,
                traceId: normalized.traceId,
            });

            return {
                ok: true,
                activePanelId: this._state.activePanelId,
                panelParams: cloneValue(this._state.panelParams),
                traceId: normalized.traceId,
            };
        }

        syncStockContext(params) {
            const normalized = this._normalizeSimpleParams(params);
            const storeState = this._globalStockStore.getState();
            const revision = this._globalStockStore.getRevision();
            const nextContext = {
                stock: {
                    code: storeState.identity.code,
                    name: storeState.identity.name,
                    market: storeState.identity.market,
                    exchange: storeState.identity.exchange,
                },
                revision,
                source: normalized.source,
                traceId: normalized.traceId,
            };

            this._setState({
                context: nextContext,
                meta: {
                    ...this._state.meta,
                    lastUpdatedAt: getNow(),
                },
            });
            this._emitEvent(RAIL_EVENT_NAMES.CONTEXT_SYNCED, {
                context: cloneValue(nextContext),
                source: normalized.source,
                traceId: normalized.traceId,
            });

            return {
                ok: true,
                context: this._snapshotValue(this._state.context),
                traceId: normalized.traceId,
            };
        }

        clearContext(params) {
            const normalized = this._normalizeSimpleParams(params);
            const nextContext = {
                stock: {
                    code: null,
                    name: null,
                    market: null,
                    exchange: null,
                },
                revision: this._globalStockStore.getRevision(),
                source: normalized.source,
                traceId: normalized.traceId,
            };

            this._setState({
                context: nextContext,
                meta: {
                    ...this._state.meta,
                    lastUpdatedAt: getNow(),
                },
            });
            this._emitEvent(RAIL_EVENT_NAMES.CONTEXT_CLEARED, {
                context: cloneValue(nextContext),
                source: normalized.source,
                traceId: normalized.traceId,
            });

            return {
                ok: true,
                context: this._snapshotValue(this._state.context),
                traceId: normalized.traceId,
            };
        }

        setWidth(params) {
            const normalized = this._normalizeSetWidthParams(params);
            this._setState({
                ui: {
                    ...this._state.ui,
                    width: normalized.width,
                    lastUserActionAt: getNow(),
                },
                meta: {
                    ...this._state.meta,
                    lastUpdatedAt: getNow(),
                },
            });
            this._syncMountedDom();
            this._emitEvent(RAIL_EVENT_NAMES.WIDTH_CHANGED, {
                width: this._state.ui.width,
                source: normalized.source,
                traceId: normalized.traceId,
            });

            return {
                ok: true,
                width: this._state.ui.width,
                traceId: normalized.traceId,
            };
        }

        mount(params) {
            const normalized = this._normalizeMountParams(params);
            this._mountedRoot = normalized.root;
            this._setState({
                ui: {
                    ...this._state.ui,
                    isMounted: true,
                },
                meta: {
                    ...this._state.meta,
                    lastUpdatedAt: getNow(),
                },
            });
            this._syncMountedDom();
            this._emitEvent(RAIL_EVENT_NAMES.MOUNTED, {
                isMounted: true,
            });
            return {
                ok: true,
            };
        }

        unmount() {
            this._mountedRoot = null;
            this._setState({
                ui: {
                    ...this._state.ui,
                    isMounted: false,
                },
                meta: {
                    ...this._state.meta,
                    lastUpdatedAt: getNow(),
                },
            });
            this._emitEvent(RAIL_EVENT_NAMES.UNMOUNTED, {
                isMounted: false,
            });
            return {
                ok: true,
            };
        }

        createTraceId(prefix) {
            return this._createTraceId(prefix);
        }

        reset() {
            const nextState = createInitialState();
            nextState.ui.isMounted = this._state.ui.isMounted;
            nextState.ui.width = this._state.ui.width;
            nextState.meta.lastUpdatedAt = getNow();
            this._setWholeState(nextState);
            this.syncStockContext({
                source: 'right-rail:reset',
                traceId: this._createTraceId(DEFAULT_TRACE_PREFIX),
            });
            this._syncMountedDom();
            this._emitEvent(RAIL_EVENT_NAMES.RESET, {
                ok: true,
            });
            return {
                ok: true,
            };
        }

        _handleStoreChange(storeState) {
            if (!storeState || !storeState.identity || !storeState.meta) {
                return;
            }

            const nextStock = {
                code: storeState.identity.code,
                name: storeState.identity.name,
                market: storeState.identity.market,
                exchange: storeState.identity.exchange,
            };
            const hasContextChanged = nextStock.code !== this._state.context.stock.code
                || nextStock.name !== this._state.context.stock.name
                || nextStock.market !== this._state.context.stock.market
                || nextStock.exchange !== this._state.context.stock.exchange
                || storeState.meta.revision !== this._state.context.revision;

            if (!hasContextChanged) {
                return;
            }

            this.syncStockContext({
                source: 'global-stock-store',
                traceId: storeState.meta.lastIntentTraceId || this._createTraceId(DEFAULT_TRACE_PREFIX),
            });
        }

        _snapshotState() {
            return this._snapshotValue(this._state);
        }

        _snapshotValue(value) {
            return deepFreeze(cloneValue(value));
        }

        _setWholeState(nextState) {
            this._state = nextState;
            this._notifyListeners();
        }

        _setState(partialState) {
            const nextState = {
                ...this._state,
                ...partialState,
                context: partialState.context ? {
                    ...this._state.context,
                    ...partialState.context,
                    stock: partialState.context.stock ? {
                        ...this._state.context.stock,
                        ...partialState.context.stock,
                    } : this._state.context.stock,
                } : this._state.context,
                ui: partialState.ui ? {
                    ...this._state.ui,
                    ...partialState.ui,
                } : this._state.ui,
                meta: partialState.meta ? {
                    ...this._state.meta,
                    ...partialState.meta,
                } : this._state.meta,
            };
            this._state = nextState;
            this._notifyListeners();
        }

        _notifyListeners() {
            const snapshot = this._snapshotState();
            this._listeners.forEach((listener) => {
                listener(snapshot);
            });
        }

        _emitEvent(eventName, payload) {
            this._intentBus.emit(eventName, cloneValue(payload));
        }

        _syncMountedDom() {
            if (!this._mountedRoot) {
                return;
            }

            this._mountedRoot.hidden = this._state.isOpen !== true;
            this._mountedRoot.dataset.railOpen = this._state.isOpen ? 'true' : 'false';
            this._mountedRoot.dataset.railMode = this._state.displayMode;
            this._mountedRoot.dataset.railPanel = this._state.activePanelId || '';
            if (this._state.ui.width != null) {
                this._mountedRoot.style.width = `${this._state.ui.width}px`;
            } else {
                this._mountedRoot.style.width = '';
            }
        }

        _createTraceId(prefix) {
            const safePrefix = typeof prefix === 'string' && prefix.trim() ? prefix.trim() : DEFAULT_TRACE_PREFIX;
            if (typeof this._intentBus.createTraceId === 'function') {
                return this._intentBus.createTraceId(safePrefix);
            }
            this._traceSequence += 1;
            return `${safePrefix}-${getNow()}-${this._traceSequence}`;
        }

        _normalizeDisplayMode(displayMode, allowHidden) {
            const normalizedDisplayMode = typeof displayMode === 'string' ? displayMode.trim() : '';
            const allowedModes = allowHidden
                ? [DISPLAY_MODE.HIDDEN, DISPLAY_MODE.OVERLAY, DISPLAY_MODE.PINNED]
                : [DISPLAY_MODE.OVERLAY, DISPLAY_MODE.PINNED];

            if (!normalizedDisplayMode) {
                return null;
            }

            if (!allowedModes.includes(normalizedDisplayMode)) {
                throw createRightRailError('Invalid display mode', 'INVALID_DISPLAY_MODE');
            }

            return normalizedDisplayMode;
        }

        _normalizePanelId(panelId, allowNull) {
            if (panelId == null && allowNull) {
                return null;
            }

            const normalizedPanelId = typeof panelId === 'string' ? panelId.trim() : '';
            if (!normalizedPanelId) {
                throw createRightRailError('Panel ID is required', 'INVALID_PANEL_ID');
            }
            return normalizedPanelId;
        }

        _normalizeSimpleParams(params) {
            const safeParams = isPlainObject(params) ? params : {};
            return {
                source: typeof safeParams.source === 'string' && safeParams.source.trim() ? safeParams.source.trim() : null,
                traceId: typeof safeParams.traceId === 'string' && safeParams.traceId.trim()
                    ? safeParams.traceId.trim()
                    : this._createTraceId(DEFAULT_TRACE_PREFIX),
            };
        }

        _normalizeOpenParams(params) {
            const safeParams = isPlainObject(params) ? params : {};
            return {
                panelId: safeParams.panelId == null ? null : this._normalizePanelId(safeParams.panelId, false),
                panelParams: isPlainObject(safeParams.panelParams) ? cloneValue(safeParams.panelParams) : null,
                displayMode: this._normalizeDisplayMode(safeParams.displayMode, false),
                source: typeof safeParams.source === 'string' && safeParams.source.trim() ? safeParams.source.trim() : null,
                traceId: typeof safeParams.traceId === 'string' && safeParams.traceId.trim()
                    ? safeParams.traceId.trim()
                    : this._createTraceId(DEFAULT_TRACE_PREFIX),
            };
        }

        _normalizeCloseParams(params) {
            const safeParams = isPlainObject(params) ? params : {};
            return {
                preservePanel: safeParams.preservePanel === true,
                source: typeof safeParams.source === 'string' && safeParams.source.trim() ? safeParams.source.trim() : null,
                traceId: typeof safeParams.traceId === 'string' && safeParams.traceId.trim()
                    ? safeParams.traceId.trim()
                    : this._createTraceId(DEFAULT_TRACE_PREFIX),
            };
        }

        _normalizeToggleParams(params) {
            const safeParams = isPlainObject(params) ? params : {};
            return {
                panelId: safeParams.panelId == null ? null : this._normalizePanelId(safeParams.panelId, false),
                displayMode: this._normalizeDisplayMode(safeParams.displayMode, false),
                source: typeof safeParams.source === 'string' && safeParams.source.trim() ? safeParams.source.trim() : null,
                traceId: typeof safeParams.traceId === 'string' && safeParams.traceId.trim()
                    ? safeParams.traceId.trim()
                    : this._createTraceId(DEFAULT_TRACE_PREFIX),
            };
        }

        _normalizeSetDisplayModeParams(params) {
            if (!isPlainObject(params)) {
                throw createRightRailError('setDisplayMode params must be a plain object', 'INVALID_SET_DISPLAY_MODE_PARAMS');
            }
            return {
                displayMode: this._normalizeDisplayMode(params.displayMode, true),
                source: typeof params.source === 'string' && params.source.trim() ? params.source.trim() : null,
                traceId: typeof params.traceId === 'string' && params.traceId.trim()
                    ? params.traceId.trim()
                    : this._createTraceId(DEFAULT_TRACE_PREFIX),
            };
        }

        _normalizeActivatePanelParams(params) {
            if (!isPlainObject(params)) {
                throw createRightRailError('activatePanel params must be a plain object', 'INVALID_ACTIVATE_PANEL_PARAMS');
            }
            return {
                panelId: this._normalizePanelId(params.panelId, false),
                panelParams: isPlainObject(params.panelParams) ? cloneValue(params.panelParams) : null,
                autoOpen: params.autoOpen !== false,
                displayMode: this._normalizeDisplayMode(params.displayMode, false),
                source: typeof params.source === 'string' && params.source.trim() ? params.source.trim() : null,
                traceId: typeof params.traceId === 'string' && params.traceId.trim()
                    ? params.traceId.trim()
                    : this._createTraceId(DEFAULT_TRACE_PREFIX),
            };
        }

        _normalizeDeactivatePanelParams(params) {
            const safeParams = isPlainObject(params) ? params : {};
            return {
                closeRail: safeParams.closeRail === true,
                source: typeof safeParams.source === 'string' && safeParams.source.trim() ? safeParams.source.trim() : null,
                traceId: typeof safeParams.traceId === 'string' && safeParams.traceId.trim()
                    ? safeParams.traceId.trim()
                    : this._createTraceId(DEFAULT_TRACE_PREFIX),
            };
        }

        _normalizeSetPanelParamsParams(params) {
            if (!isPlainObject(params)) {
                throw createRightRailError('setPanelParams params must be a plain object', 'INVALID_SET_PANEL_PARAMS');
            }
            return {
                panelParams: isPlainObject(params.panelParams) ? cloneValue(params.panelParams) : null,
                source: typeof params.source === 'string' && params.source.trim() ? params.source.trim() : null,
                traceId: typeof params.traceId === 'string' && params.traceId.trim()
                    ? params.traceId.trim()
                    : this._createTraceId(DEFAULT_TRACE_PREFIX),
            };
        }

        _normalizeSetWidthParams(params) {
            if (!isPlainObject(params)) {
                throw createRightRailError('setWidth params must be a plain object', 'INVALID_SET_WIDTH_PARAMS');
            }
            const width = params.width == null ? null : Number(params.width);
            if (width != null && (!Number.isFinite(width) || width <= 0)) {
                throw createRightRailError('Width must be a positive number or null', 'INVALID_WIDTH');
            }
            return {
                width,
                source: typeof params.source === 'string' && params.source.trim() ? params.source.trim() : null,
                traceId: typeof params.traceId === 'string' && params.traceId.trim()
                    ? params.traceId.trim()
                    : this._createTraceId(DEFAULT_TRACE_PREFIX),
            };
        }

        _normalizeMountParams(params) {
            if (!isPlainObject(params) || !params.root || typeof params.root.setAttribute !== 'function') {
                throw createRightRailError('mount requires a valid root element', 'INVALID_MOUNT_PARAMS');
            }
            return {
                root: params.root,
            };
        }
    }

    const rightRailControllerInternal = new RightRailControllerImpl(global.IntentBus, global.GlobalStockStore);
    const rightRailControllerPublicApi = Object.freeze({
        getState: rightRailControllerInternal.getState.bind(rightRailControllerInternal),
        subscribe: rightRailControllerInternal.subscribe.bind(rightRailControllerInternal),
        open: rightRailControllerInternal.open.bind(rightRailControllerInternal),
        close: rightRailControllerInternal.close.bind(rightRailControllerInternal),
        toggle: rightRailControllerInternal.toggle.bind(rightRailControllerInternal),
        setDisplayMode: rightRailControllerInternal.setDisplayMode.bind(rightRailControllerInternal),
        activatePanel: rightRailControllerInternal.activatePanel.bind(rightRailControllerInternal),
        deactivatePanel: rightRailControllerInternal.deactivatePanel.bind(rightRailControllerInternal),
        setPanelParams: rightRailControllerInternal.setPanelParams.bind(rightRailControllerInternal),
        syncStockContext: rightRailControllerInternal.syncStockContext.bind(rightRailControllerInternal),
        clearContext: rightRailControllerInternal.clearContext.bind(rightRailControllerInternal),
        setWidth: rightRailControllerInternal.setWidth.bind(rightRailControllerInternal),
        mount: rightRailControllerInternal.mount.bind(rightRailControllerInternal),
        unmount: rightRailControllerInternal.unmount.bind(rightRailControllerInternal),
        createTraceId: rightRailControllerInternal.createTraceId.bind(rightRailControllerInternal),
        reset: rightRailControllerInternal.reset.bind(rightRailControllerInternal),
    });

    global.RightRailController = rightRailControllerPublicApi;
})(window);
