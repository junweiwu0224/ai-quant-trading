(function attachCommandPalette(global) {
    'use strict';

    if (!global.IntentBus) {
        throw new Error('CommandPalette requires window.IntentBus');
    }

    if (!global.GlobalStockStore) {
        throw new Error('CommandPalette requires window.GlobalStockStore');
    }

    if (!global.StockSearchService) {
        throw new Error('CommandPalette requires window.StockSearchService');
    }

    if (!global.LocalMCP) {
        throw new Error('CommandPalette requires window.LocalMCP');
    }

    const PALETTE_EVENT_NAMES = Object.freeze({
        OPENED: 'command-palette:opened',
        CLOSED: 'command-palette:closed',
        TOGGLED: 'command-palette:toggled',
        MODE_CHANGED: 'command-palette:mode-changed',
        QUERY_CHANGED: 'command-palette:query-changed',
        RESULTS_LOADING: 'command-palette:results-loading',
        RESULTS_UPDATED: 'command-palette:results-updated',
        RESULTS_FAILED: 'command-palette:results-failed',
        SELECTION_CHANGED: 'command-palette:selection-changed',
        EXECUTE_STARTED: 'command-palette:execute-started',
        EXECUTE_SUCCEEDED: 'command-palette:execute-succeeded',
        EXECUTE_FAILED: 'command-palette:execute-failed',
        MOUNTED: 'command-palette:mounted',
        UNMOUNTED: 'command-palette:unmounted',
        RESET: 'command-palette:reset',
    });

    const PALETTE_MODE = Object.freeze({
        MIXED: 'mixed',
        ACTION: 'action',
        STOCK: 'stock',
    });

    const SELECTION_DIRECTION = Object.freeze({
        NEXT: 'next',
        PREV: 'prev',
        FIRST: 'first',
        LAST: 'last',
    });

    const EXECUTION_STATUS = Object.freeze({
        SUCCESS: 'success',
        BLOCKED: 'blocked',
        NOT_FOUND: 'not_found',
        FAILED: 'failed',
        EMPTY_SELECTION: 'empty_selection',
    });

    const RESULT_KIND = Object.freeze({
        ACTION: 'action',
        STOCK: 'stock',
    });

    const DEFAULT_TRACE_PREFIX = 'command-palette';
    const DEFAULT_REQUEST_PREFIX = 'command-palette';
    const DEFAULT_SEARCH_DEBOUNCE_MS = 180;

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

    function createCommandPaletteError(message, code) {
        const error = new Error(message);
        error.name = 'CommandPaletteError';
        if (code) {
            error.code = code;
        }
        return error;
    }

    function getErrorShape(error, fallbackMessage) {
        if (error instanceof Error) {
            return {
                message: error.message || fallbackMessage,
                code: typeof error.code === 'string' ? error.code : null,
            };
        }

        if (typeof error === 'string' && error.trim()) {
            return {
                message: error,
                code: null,
            };
        }

        if (error && typeof error === 'object') {
            return {
                message: typeof error.message === 'string' && error.message ? error.message : fallbackMessage,
                code: typeof error.code === 'string' ? error.code : null,
            };
        }

        return {
            message: fallbackMessage,
            code: null,
        };
    }

    function createInitialState() {
        return {
            isOpen: false,
            mode: PALETTE_MODE.MIXED,
            query: '',
            selectedIndex: -1,
            isLoading: false,
            actionResults: [],
            stockResults: [],
            mergedResults: [],
            activeRequestId: null,
            error: null,
            meta: {
                openedAt: null,
                lastUpdatedAt: null,
            },
        };
    }

    class CommandPaletteImpl {
        constructor(intentBus, globalStockStore, stockSearchService, localMCP) {
            this._intentBus = intentBus;
            this._globalStockStore = globalStockStore;
            this._stockSearchService = stockSearchService;
            this._localMCP = localMCP;
            this._listeners = [];
            this._state = createInitialState();
            this._traceSequence = 0;
            this._requestSequence = 0;
            this._mountedElements = {
                root: null,
                input: null,
                list: null,
            };
            this._domListeners = {
                input: null,
                rootKeydown: null,
                rootClick: null,
                listClick: null,
            };
            this._keyboardTarget = null;
            this._keyboardHandler = null;
        }

        getState() {
            return this._snapshotState();
        }

        subscribe(listener) {
            if (typeof listener !== 'function') {
                throw createCommandPaletteError('Listener must be a function', 'INVALID_LISTENER');
            }

            this._listeners = [...this._listeners, listener];
            return () => {
                this._listeners = this._listeners.filter((item) => item !== listener);
            };
        }

        async open(params) {
            const normalized = this._normalizeOpenParams(params);
            const nextState = {
                isOpen: true,
                mode: normalized.mode,
                query: normalized.query,
                meta: {
                    ...this._state.meta,
                    openedAt: this._state.isOpen ? this._state.meta.openedAt : getNow(),
                    lastUpdatedAt: getNow(),
                },
                error: null,
            };
            this._setState(nextState);
            this._emitEvent(PALETTE_EVENT_NAMES.OPENED, {
                isOpen: true,
                mode: normalized.mode,
                query: normalized.query,
                source: normalized.source,
                traceId: normalized.traceId,
            });
            await this.refreshResults({
                source: normalized.source,
                traceId: normalized.traceId,
            });
            this._focusInput();
            return {
                ok: true,
                isOpen: true,
                mode: this._state.mode,
                query: this._state.query,
                traceId: normalized.traceId,
            };
        }

        close(params) {
            const normalized = this._normalizeCloseParams(params);
            this._cancelPendingSearch(normalized.source, normalized.traceId);
            const nextQuery = normalized.clearQuery ? '' : this._state.query;
            const nextActionResults = normalized.clearQuery ? [] : this._state.actionResults;
            const nextStockResults = normalized.clearQuery ? [] : this._state.stockResults;
            const nextMergedResults = normalized.clearQuery ? [] : this._state.mergedResults;
            this._setState({
                isOpen: false,
                query: nextQuery,
                actionResults: nextActionResults,
                stockResults: nextStockResults,
                mergedResults: nextMergedResults,
                selectedIndex: this._clampSelectedIndex(this._state.selectedIndex, nextMergedResults.length),
                isLoading: false,
                activeRequestId: null,
                error: null,
                meta: {
                    ...this._state.meta,
                    lastUpdatedAt: getNow(),
                },
            });
            this._emitEvent(PALETTE_EVENT_NAMES.CLOSED, {
                isOpen: false,
                query: this._state.query,
                source: normalized.source,
                traceId: normalized.traceId,
            });
            return {
                ok: true,
                isOpen: false,
                query: this._state.query,
                traceId: normalized.traceId,
            };
        }

        async toggle(params) {
            const normalized = this._normalizeToggleParams(params);
            let result;
            if (this._state.isOpen) {
                result = this.close({
                    clearQuery: false,
                    source: normalized.source,
                    traceId: normalized.traceId,
                });
            } else {
                result = await this.open({
                    mode: normalized.mode,
                    query: this._state.query,
                    source: normalized.source,
                    traceId: normalized.traceId,
                });
            }

            this._emitEvent(PALETTE_EVENT_NAMES.TOGGLED, {
                isOpen: this._state.isOpen,
                mode: this._state.mode,
                source: normalized.source,
                traceId: normalized.traceId,
            });

            return {
                ok: true,
                isOpen: this._state.isOpen,
                mode: this._state.mode,
                traceId: normalized.traceId,
                result,
            };
        }

        async setMode(params) {
            const normalized = this._normalizeSetModeParams(params);
            this._setState({
                mode: normalized.mode,
                selectedIndex: -1,
                error: null,
                meta: {
                    ...this._state.meta,
                    lastUpdatedAt: getNow(),
                },
            });
            this._emitEvent(PALETTE_EVENT_NAMES.MODE_CHANGED, {
                mode: normalized.mode,
                source: normalized.source,
                traceId: normalized.traceId,
            });
            if (this._state.isOpen) {
                await this.refreshResults({
                    source: normalized.source,
                    traceId: normalized.traceId,
                });
            }
            return {
                ok: true,
                mode: this._state.mode,
                traceId: normalized.traceId,
            };
        }

        async setQuery(params) {
            const normalized = this._normalizeSetQueryParams(params);
            this._setState({
                query: normalized.query,
                activeRequestId: normalized.requestId,
                isLoading: this._state.isOpen,
                error: null,
                meta: {
                    ...this._state.meta,
                    lastUpdatedAt: getNow(),
                },
            });
            this._emitEvent(PALETTE_EVENT_NAMES.QUERY_CHANGED, {
                query: normalized.query,
                requestId: normalized.requestId,
                source: normalized.source,
                traceId: normalized.traceId,
            });
            if (this._state.isOpen) {
                await this.refreshResults({
                    source: normalized.source,
                    traceId: normalized.traceId,
                    requestId: normalized.requestId,
                });
            }
            return {
                ok: true,
                query: this._state.query,
                requestId: normalized.requestId,
                traceId: normalized.traceId,
            };
        }

        async refreshResults(params) {
            const normalized = this._normalizeRefreshParams(params);
            const requestId = normalized.requestId || this._createRequestId(DEFAULT_REQUEST_PREFIX);
            const snapshotMode = this._state.mode;
            const snapshotQuery = this._state.query;

            this._setState({
                isLoading: true,
                activeRequestId: requestId,
                error: null,
                meta: {
                    ...this._state.meta,
                    lastUpdatedAt: getNow(),
                },
            });
            this._emitEvent(PALETTE_EVENT_NAMES.RESULTS_LOADING, {
                mode: snapshotMode,
                query: snapshotQuery,
                requestId,
                source: normalized.source,
                traceId: normalized.traceId,
            });

            try {
                const actionResults = this._buildActionResults(snapshotMode, snapshotQuery);
                const stockResults = await this._loadStockResults({
                    mode: snapshotMode,
                    query: snapshotQuery,
                    requestId,
                    source: normalized.source,
                    traceId: normalized.traceId,
                });

                if (this._state.activeRequestId !== requestId) {
                    return {
                        ok: true,
                        requestId,
                        traceId: normalized.traceId,
                        actionCount: 0,
                        stockCount: 0,
                        mergedCount: 0,
                        error: null,
                    };
                }

                const mergedResults = this._buildMergedResults(snapshotMode, actionResults, stockResults);
                const selectedIndex = this._resolveSelectedIndex(mergedResults.length);

                this._setState({
                    actionResults,
                    stockResults,
                    mergedResults,
                    selectedIndex,
                    isLoading: false,
                    activeRequestId: requestId,
                    error: null,
                    meta: {
                        ...this._state.meta,
                        lastUpdatedAt: getNow(),
                    },
                });
                this._emitEvent(PALETTE_EVENT_NAMES.RESULTS_UPDATED, {
                    mode: snapshotMode,
                    query: snapshotQuery,
                    requestId,
                    source: normalized.source,
                    traceId: normalized.traceId,
                    actionCount: actionResults.length,
                    stockCount: stockResults.length,
                    mergedCount: mergedResults.length,
                });
                this._emitSelectionChanged(normalized.source, normalized.traceId);

                return {
                    ok: true,
                    requestId,
                    traceId: normalized.traceId,
                    actionCount: actionResults.length,
                    stockCount: stockResults.length,
                    mergedCount: mergedResults.length,
                    error: null,
                };
            } catch (error) {
                if (this._state.activeRequestId !== requestId) {
                    return {
                        ok: true,
                        requestId,
                        traceId: normalized.traceId,
                        actionCount: 0,
                        stockCount: 0,
                        mergedCount: 0,
                        error: null,
                    };
                }

                const errorShape = getErrorShape(error, 'Failed to refresh command palette results');
                this._setState({
                    actionResults: snapshotMode === PALETTE_MODE.STOCK ? [] : this._state.actionResults,
                    stockResults: snapshotMode === PALETTE_MODE.ACTION ? [] : this._state.stockResults,
                    mergedResults: [],
                    selectedIndex: -1,
                    isLoading: false,
                    activeRequestId: requestId,
                    error: errorShape,
                    meta: {
                        ...this._state.meta,
                        lastUpdatedAt: getNow(),
                    },
                });
                this._emitEvent(PALETTE_EVENT_NAMES.RESULTS_FAILED, {
                    mode: snapshotMode,
                    query: snapshotQuery,
                    requestId,
                    source: normalized.source,
                    traceId: normalized.traceId,
                    error: cloneValue(errorShape),
                });
                this._emitSelectionChanged(normalized.source, normalized.traceId);

                return {
                    ok: false,
                    requestId,
                    traceId: normalized.traceId,
                    actionCount: 0,
                    stockCount: 0,
                    mergedCount: 0,
                    error: errorShape,
                };
            }
        }

        moveSelection(params) {
            const normalized = this._normalizeMoveSelectionParams(params);
            const total = this._state.mergedResults.length;
            if (total === 0) {
                return {
                    ok: false,
                    selectedIndex: -1,
                    selectedItem: null,
                    traceId: normalized.traceId,
                };
            }

            let nextIndex = this._state.selectedIndex;
            if (normalized.direction === SELECTION_DIRECTION.FIRST) {
                nextIndex = 0;
            } else if (normalized.direction === SELECTION_DIRECTION.LAST) {
                nextIndex = total - 1;
            } else if (normalized.direction === SELECTION_DIRECTION.NEXT) {
                nextIndex = this._state.selectedIndex < 0 ? 0 : (this._state.selectedIndex + 1) % total;
            } else if (normalized.direction === SELECTION_DIRECTION.PREV) {
                nextIndex = this._state.selectedIndex < 0 ? total - 1 : (this._state.selectedIndex - 1 + total) % total;
            }

            this._setState({
                selectedIndex: nextIndex,
                meta: {
                    ...this._state.meta,
                    lastUpdatedAt: getNow(),
                },
            });
            this._emitSelectionChanged(normalized.source, normalized.traceId);

            return {
                ok: true,
                selectedIndex: this._state.selectedIndex,
                selectedItem: this.getSelectedItem(),
                traceId: normalized.traceId,
            };
        }

        getSelectedItem() {
            const item = this._state.mergedResults[this._state.selectedIndex] || null;
            return item ? this._snapshotValue(item) : null;
        }

        selectIndex(params) {
            const normalized = this._normalizeSelectIndexParams(params);
            if (this._state.mergedResults.length === 0) {
                this._setState({
                    selectedIndex: -1,
                });
                this._emitSelectionChanged(normalized.source, normalized.traceId);
                return {
                    ok: false,
                    selectedIndex: -1,
                    selectedItem: null,
                    traceId: normalized.traceId,
                };
            }

            const nextIndex = this._clampSelectedIndex(normalized.index, this._state.mergedResults.length);
            this._setState({
                selectedIndex: nextIndex,
                meta: {
                    ...this._state.meta,
                    lastUpdatedAt: getNow(),
                },
            });
            this._emitSelectionChanged(normalized.source, normalized.traceId);

            return {
                ok: true,
                selectedIndex: this._state.selectedIndex,
                selectedItem: this.getSelectedItem(),
                traceId: normalized.traceId,
            };
        }

        async executeSelection(params) {
            const normalized = this._normalizeExecuteSelectionParams(params);
            const selectedItem = this._state.mergedResults[this._state.selectedIndex] || null;
            if (!selectedItem) {
                return {
                    ok: false,
                    kind: null,
                    traceId: normalized.traceId,
                    requestId: normalized.requestId,
                    status: EXECUTION_STATUS.EMPTY_SELECTION,
                    result: null,
                    error: null,
                };
            }

            return this.executeItem({
                item: selectedItem,
                closeOnSuccess: normalized.closeOnSuccess,
                source: normalized.source,
                traceId: normalized.traceId,
                requestId: normalized.requestId,
            });
        }

        async executeItem(params) {
            const normalized = this._normalizeExecuteItemParams(params);
            this._emitEvent(PALETTE_EVENT_NAMES.EXECUTE_STARTED, {
                item: cloneValue(normalized.item),
                kind: normalized.item.kind,
                source: normalized.source,
                traceId: normalized.traceId,
                requestId: normalized.requestId,
            });

            try {
                if (normalized.item.kind === RESULT_KIND.ACTION) {
                    const actionResult = await this._localMCP.invoke({
                        toolId: normalized.item.id,
                        input: normalized.item.metadata ? cloneValue(normalized.item.metadata) : null,
                        source: normalized.source,
                        traceId: normalized.traceId,
                        requestId: normalized.requestId,
                    });
                    const result = {
                        ok: actionResult.ok,
                        kind: RESULT_KIND.ACTION,
                        traceId: actionResult.traceId,
                        requestId: actionResult.requestId,
                        status: actionResult.status,
                        result: actionResult.output,
                        error: actionResult.error ? cloneValue(actionResult.error) : null,
                    };
                    this._emitExecutionResult(result, normalized.item, normalized.source);
                    if (result.ok && normalized.closeOnSuccess) {
                        this.close({
                            clearQuery: false,
                            source: normalized.source,
                            traceId: normalized.traceId,
                        });
                    }
                    return result;
                }

                const selectionResult = await this._stockSearchService.resolveSelection({
                    item: {
                        code: normalized.item.code,
                        name: normalized.item.name,
                        market: normalized.item.market,
                        exchange: normalized.item.exchange,
                    },
                    source: normalized.source,
                    traceId: normalized.traceId,
                    requestId: normalized.requestId,
                    preserveUI: true,
                });
                const result = {
                    ok: selectionResult.ok,
                    kind: RESULT_KIND.STOCK,
                    traceId: selectionResult.traceId,
                    requestId: selectionResult.requestId,
                    status: selectionResult.ok ? EXECUTION_STATUS.SUCCESS : EXECUTION_STATUS.FAILED,
                    result: selectionResult.ok ? {
                        revision: selectionResult.revision,
                        state: selectionResult.state,
                    } : null,
                    error: selectionResult.ok ? null : {
                        message: selectionResult.error || 'Failed to select stock',
                        code: null,
                    },
                };
                this._emitExecutionResult(result, normalized.item, normalized.source);
                if (result.ok && normalized.closeOnSuccess) {
                    this.close({
                        clearQuery: false,
                        source: normalized.source,
                        traceId: normalized.traceId,
                    });
                }
                return result;
            } catch (error) {
                const errorShape = getErrorShape(error, 'Failed to execute command palette item');
                const result = {
                    ok: false,
                    kind: normalized.item.kind,
                    traceId: normalized.traceId,
                    requestId: normalized.requestId,
                    status: EXECUTION_STATUS.FAILED,
                    result: null,
                    error: errorShape,
                };
                this._emitExecutionResult(result, normalized.item, normalized.source);
                return result;
            }
        }

        attachKeyboardShortcuts(params) {
            const normalized = this._normalizeAttachKeyboardParams(params);
            this.detachKeyboardShortcuts();
            this._keyboardTarget = normalized.target;
            this._keyboardHandler = this._handleGlobalKeydown.bind(this);
            this._keyboardTarget.addEventListener('keydown', this._keyboardHandler);
            return {
                ok: true,
            };
        }

        detachKeyboardShortcuts() {
            if (this._keyboardTarget && this._keyboardHandler) {
                this._keyboardTarget.removeEventListener('keydown', this._keyboardHandler);
            }
            this._keyboardTarget = null;
            this._keyboardHandler = null;
            return {
                ok: true,
            };
        }

        mount(params) {
            const normalized = this._normalizeMountParams(params);
            this.unmount();
            this._mountedElements = {
                root: normalized.root,
                input: normalized.input,
                list: normalized.list,
            };

            if (normalized.input) {
                this._domListeners.input = (event) => {
                    void this.setQuery({
                        query: event.target.value,
                        source: 'command-palette:input',
                    });
                };
                normalized.input.addEventListener('input', this._domListeners.input);
            }

            if (normalized.root) {
                this._domListeners.rootKeydown = (event) => {
                    void this._handlePaletteKeydown(event);
                };
                normalized.root.addEventListener('keydown', this._domListeners.rootKeydown);
                this._domListeners.rootClick = (event) => {
                    if (event.target !== normalized.root) {
                        return;
                    }
                    this.close({
                        clearQuery: false,
                        source: 'command-palette:backdrop',
                    });
                };
                normalized.root.addEventListener('click', this._domListeners.rootClick);
            }

            if (normalized.list) {
                this._domListeners.listClick = (event) => {
                    const target = event.target.closest('[data-command-palette-index]');
                    if (!target) {
                        return;
                    }
                    const index = Number(target.getAttribute('data-command-palette-index'));
                    if (!Number.isFinite(index)) {
                        return;
                    }
                    this.selectIndex({
                        index,
                        source: 'command-palette:list',
                    });
                    void this.executeSelection({
                        closeOnSuccess: true,
                        source: 'command-palette:list',
                    });
                };
                normalized.list.addEventListener('click', this._domListeners.listClick);
            }

            this._syncMountedDom();
            this._emitEvent(PALETTE_EVENT_NAMES.MOUNTED, {
                isOpen: this._state.isOpen,
            });
            return {
                ok: true,
            };
        }

        unmount() {
            const { root, input, list } = this._mountedElements;
            if (input && this._domListeners.input) {
                input.removeEventListener('input', this._domListeners.input);
            }
            if (root && this._domListeners.rootKeydown) {
                root.removeEventListener('keydown', this._domListeners.rootKeydown);
            }
            if (root && this._domListeners.rootClick) {
                root.removeEventListener('click', this._domListeners.rootClick);
            }
            if (list && this._domListeners.listClick) {
                list.removeEventListener('click', this._domListeners.listClick);
            }
            this._mountedElements = {
                root: null,
                input: null,
                list: null,
            };
            this._domListeners = {
                input: null,
                rootKeydown: null,
                rootClick: null,
                listClick: null,
            };
            this._emitEvent(PALETTE_EVENT_NAMES.UNMOUNTED, {
                ok: true,
            });
            return {
                ok: true,
            };
        }

        reset() {
            this._cancelPendingSearch('command-palette:reset', this._createTraceId(DEFAULT_TRACE_PREFIX));
            const nextState = createInitialState();
            nextState.meta.lastUpdatedAt = getNow();
            this._setWholeState(nextState);
            this._emitEvent(PALETTE_EVENT_NAMES.RESET, {
                ok: true,
            });
            return {
                ok: true,
            };
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
            this._syncMountedDom();
        }

        _setState(partialState) {
            const nextState = {
                ...this._state,
                ...partialState,
                meta: partialState.meta ? {
                    ...this._state.meta,
                    ...partialState.meta,
                } : this._state.meta,
            };
            this._state = nextState;
            this._notifyListeners();
            this._syncMountedDom();
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

        _emitSelectionChanged(source, traceId) {
            this._emitEvent(PALETTE_EVENT_NAMES.SELECTION_CHANGED, {
                selectedIndex: this._state.selectedIndex,
                selectedItem: this._state.mergedResults[this._state.selectedIndex]
                    ? cloneValue(this._state.mergedResults[this._state.selectedIndex])
                    : null,
                source,
                traceId,
            });
        }

        _emitExecutionResult(result, item, source) {
            if (result.ok) {
                this._emitEvent(PALETTE_EVENT_NAMES.EXECUTE_SUCCEEDED, {
                    item: cloneValue(item),
                    kind: result.kind,
                    traceId: result.traceId,
                    requestId: result.requestId,
                    source,
                    status: result.status,
                });
                return;
            }

            this._emitEvent(PALETTE_EVENT_NAMES.EXECUTE_FAILED, {
                item: cloneValue(item),
                kind: result.kind,
                traceId: result.traceId,
                requestId: result.requestId,
                source,
                status: result.status,
                error: cloneValue(result.error),
            });
        }

        _buildActionResults(mode, query) {
            if (mode === PALETTE_MODE.STOCK) {
                return [];
            }

            return this._localMCP.listTools({
                query,
                visibleOnly: true,
                enabledOnly: false,
            }).map((tool) => {
                return this._snapshotValue({
                    kind: RESULT_KIND.ACTION,
                    id: tool.id,
                    title: tool.title,
                    description: tool.description,
                    category: tool.category,
                    keywords: cloneValue(tool.keywords || []),
                    enabled: tool.enabled === true,
                    visible: tool.visible === true,
                    metadata: cloneValue(tool.metadata),
                });
            });
        }

        async _loadStockResults(params) {
            if (params.mode === PALETTE_MODE.ACTION) {
                return [];
            }

            const result = await this._stockSearchService.search({
                query: params.query,
                source: params.source,
                traceId: params.traceId,
                requestId: params.requestId,
                debounceMs: DEFAULT_SEARCH_DEBOUNCE_MS,
            });

            if (result.status === 'stale') {
                return [];
            }

            if (result.status === 'error') {
                throw createCommandPaletteError(result.error || 'Stock search failed', 'STOCK_SEARCH_FAILED');
            }

            return Array.isArray(result.results)
                ? result.results.map((item) => {
                    return this._snapshotValue({
                        kind: RESULT_KIND.STOCK,
                        code: item.code,
                        name: item.name,
                        market: item.market,
                        exchange: item.exchange,
                        sector: null,
                        metadata: {
                            label: item.label || `${item.code} ${item.name}`,
                            keywords: cloneValue(item.keywords || []),
                        },
                    });
                })
                : [];
        }

        _buildMergedResults(mode, actionResults, stockResults) {
            if (mode === PALETTE_MODE.ACTION) {
                return actionResults;
            }
            if (mode === PALETTE_MODE.STOCK) {
                return stockResults;
            }
            return [...actionResults, ...stockResults];
        }

        _resolveSelectedIndex(resultLength) {
            if (resultLength <= 0) {
                return -1;
            }
            if (this._state.selectedIndex < 0) {
                return 0;
            }
            return this._clampSelectedIndex(this._state.selectedIndex, resultLength);
        }

        _clampSelectedIndex(index, total) {
            if (total <= 0) {
                return -1;
            }
            if (!Number.isFinite(Number(index))) {
                return 0;
            }
            const safeIndex = Number(index);
            if (safeIndex < 0) {
                return 0;
            }
            if (safeIndex >= total) {
                return total - 1;
            }
            return safeIndex;
        }

        _createTraceId(prefix) {
            const safePrefix = typeof prefix === 'string' && prefix.trim() ? prefix.trim() : DEFAULT_TRACE_PREFIX;
            if (typeof this._intentBus.createTraceId === 'function') {
                return this._intentBus.createTraceId(safePrefix);
            }
            this._traceSequence += 1;
            return `${safePrefix}-${getNow()}-${this._traceSequence}`;
        }

        _createRequestId(prefix) {
            const safePrefix = typeof prefix === 'string' && prefix.trim() ? prefix.trim() : DEFAULT_REQUEST_PREFIX;
            this._requestSequence += 1;
            return `${safePrefix}-${getNow()}-${this._requestSequence}`;
        }

        _cancelPendingSearch(source, traceId) {
            this._stockSearchService.cancelActiveSearch({
                reason: 'manual_cancel',
                source,
                traceId,
            });
        }

        _focusInput() {
            const input = this._mountedElements.input;
            if (input && typeof input.focus === 'function') {
                input.focus();
            }
        }

        _syncMountedDom() {
            const { root, input, list } = this._mountedElements;
            if (root) {
                root.hidden = this._state.isOpen !== true;
                root.dataset.paletteOpen = this._state.isOpen ? 'true' : 'false';
                root.dataset.paletteMode = this._state.mode;
            }
            if (input) {
                input.value = this._state.query;
                input.setAttribute('aria-expanded', this._state.isOpen ? 'true' : 'false');
            }
            if (list) {
                list.dataset.resultCount = String(this._state.mergedResults.length);
                list.dataset.selectedIndex = String(this._state.selectedIndex);
            }
        }

        _handleGlobalKeydown(event) {
            const key = typeof event.key === 'string' ? event.key.toLowerCase() : '';
            const isToggleShortcut = event.altKey === true && key === 'p';
            if (isToggleShortcut) {
                event.preventDefault();
                void this.toggle({
                    source: 'command-palette:shortcut',
                });
                return;
            }

            if (!this._state.isOpen) {
                return;
            }

            const root = this._mountedElements.root;
            if (event.defaultPrevented || (root && event.target instanceof Node && root.contains(event.target))) {
                return;
            }

            void this._handlePaletteKeydown(event);
        }

        async _handlePaletteKeydown(event) {
            if (!this._state.isOpen) {
                return;
            }

            if (event.key === 'Escape') {
                event.preventDefault();
                event.stopPropagation();
                this.close({
                    clearQuery: false,
                    source: 'command-palette:keyboard',
                });
                return;
            }

            if (event.key === 'ArrowDown') {
                event.preventDefault();
                event.stopPropagation();
                this.moveSelection({
                    direction: SELECTION_DIRECTION.NEXT,
                    source: 'command-palette:keyboard',
                });
                return;
            }

            if (event.key === 'ArrowUp') {
                event.preventDefault();
                event.stopPropagation();
                this.moveSelection({
                    direction: SELECTION_DIRECTION.PREV,
                    source: 'command-palette:keyboard',
                });
                return;
            }

            if (event.key === 'Enter') {
                event.preventDefault();
                event.stopPropagation();
                await this.executeSelection({
                    closeOnSuccess: true,
                    source: 'command-palette:keyboard',
                });
            }
        }

        _normalizeOpenParams(params) {
            const safeParams = isPlainObject(params) ? params : {};
            return {
                mode: this._normalizeMode(safeParams.mode),
                query: typeof safeParams.query === 'string' ? safeParams.query : this._state.query,
                source: typeof safeParams.source === 'string' && safeParams.source.trim() ? safeParams.source.trim() : null,
                traceId: typeof safeParams.traceId === 'string' && safeParams.traceId.trim()
                    ? safeParams.traceId.trim()
                    : this._createTraceId(DEFAULT_TRACE_PREFIX),
            };
        }

        _normalizeCloseParams(params) {
            const safeParams = isPlainObject(params) ? params : {};
            return {
                clearQuery: safeParams.clearQuery === true,
                source: typeof safeParams.source === 'string' && safeParams.source.trim() ? safeParams.source.trim() : null,
                traceId: typeof safeParams.traceId === 'string' && safeParams.traceId.trim()
                    ? safeParams.traceId.trim()
                    : this._createTraceId(DEFAULT_TRACE_PREFIX),
            };
        }

        _normalizeToggleParams(params) {
            const safeParams = isPlainObject(params) ? params : {};
            return {
                mode: this._normalizeMode(safeParams.mode),
                source: typeof safeParams.source === 'string' && safeParams.source.trim() ? safeParams.source.trim() : null,
                traceId: typeof safeParams.traceId === 'string' && safeParams.traceId.trim()
                    ? safeParams.traceId.trim()
                    : this._createTraceId(DEFAULT_TRACE_PREFIX),
            };
        }

        _normalizeSetModeParams(params) {
            if (!isPlainObject(params)) {
                throw createCommandPaletteError('setMode params must be a plain object', 'INVALID_SET_MODE_PARAMS');
            }
            return {
                mode: this._normalizeMode(params.mode),
                source: typeof params.source === 'string' && params.source.trim() ? params.source.trim() : null,
                traceId: typeof params.traceId === 'string' && params.traceId.trim()
                    ? params.traceId.trim()
                    : this._createTraceId(DEFAULT_TRACE_PREFIX),
            };
        }

        _normalizeSetQueryParams(params) {
            if (!isPlainObject(params)) {
                throw createCommandPaletteError('setQuery params must be a plain object', 'INVALID_SET_QUERY_PARAMS');
            }
            return {
                query: typeof params.query === 'string' ? params.query : '',
                requestId: typeof params.requestId === 'string' && params.requestId.trim()
                    ? params.requestId.trim()
                    : this._createRequestId(DEFAULT_REQUEST_PREFIX),
                source: typeof params.source === 'string' && params.source.trim() ? params.source.trim() : null,
                traceId: typeof params.traceId === 'string' && params.traceId.trim()
                    ? params.traceId.trim()
                    : this._createTraceId(DEFAULT_TRACE_PREFIX),
            };
        }

        _normalizeRefreshParams(params) {
            const safeParams = isPlainObject(params) ? params : {};
            return {
                requestId: typeof safeParams.requestId === 'string' && safeParams.requestId.trim() ? safeParams.requestId.trim() : null,
                source: typeof safeParams.source === 'string' && safeParams.source.trim() ? safeParams.source.trim() : null,
                traceId: typeof safeParams.traceId === 'string' && safeParams.traceId.trim()
                    ? safeParams.traceId.trim()
                    : this._createTraceId(DEFAULT_TRACE_PREFIX),
            };
        }

        _normalizeMoveSelectionParams(params) {
            if (!isPlainObject(params)) {
                throw createCommandPaletteError('moveSelection params must be a plain object', 'INVALID_MOVE_SELECTION_PARAMS');
            }
            const direction = typeof params.direction === 'string' ? params.direction.trim() : '';
            if (!Object.values(SELECTION_DIRECTION).includes(direction)) {
                throw createCommandPaletteError('Invalid selection direction', 'INVALID_SELECTION_DIRECTION');
            }
            return {
                direction,
                source: typeof params.source === 'string' && params.source.trim() ? params.source.trim() : null,
                traceId: typeof params.traceId === 'string' && params.traceId.trim()
                    ? params.traceId.trim()
                    : this._createTraceId(DEFAULT_TRACE_PREFIX),
            };
        }

        _normalizeSelectIndexParams(params) {
            if (!isPlainObject(params)) {
                throw createCommandPaletteError('selectIndex params must be a plain object', 'INVALID_SELECT_INDEX_PARAMS');
            }
            return {
                index: Number(params.index),
                source: typeof params.source === 'string' && params.source.trim() ? params.source.trim() : null,
                traceId: typeof params.traceId === 'string' && params.traceId.trim()
                    ? params.traceId.trim()
                    : this._createTraceId(DEFAULT_TRACE_PREFIX),
            };
        }

        _normalizeExecuteSelectionParams(params) {
            const safeParams = isPlainObject(params) ? params : {};
            return {
                closeOnSuccess: safeParams.closeOnSuccess !== false,
                source: typeof safeParams.source === 'string' && safeParams.source.trim() ? safeParams.source.trim() : null,
                traceId: typeof safeParams.traceId === 'string' && safeParams.traceId.trim()
                    ? safeParams.traceId.trim()
                    : this._createTraceId(DEFAULT_TRACE_PREFIX),
                requestId: typeof safeParams.requestId === 'string' && safeParams.requestId.trim()
                    ? safeParams.requestId.trim()
                    : this._createRequestId(DEFAULT_REQUEST_PREFIX),
            };
        }

        _normalizeExecuteItemParams(params) {
            if (!isPlainObject(params)) {
                throw createCommandPaletteError('executeItem params must be a plain object', 'INVALID_EXECUTE_ITEM_PARAMS');
            }
            const item = this._normalizeResultItem(params.item);
            return {
                item,
                closeOnSuccess: params.closeOnSuccess !== false,
                source: typeof params.source === 'string' && params.source.trim() ? params.source.trim() : null,
                traceId: typeof params.traceId === 'string' && params.traceId.trim()
                    ? params.traceId.trim()
                    : this._createTraceId(DEFAULT_TRACE_PREFIX),
                requestId: typeof params.requestId === 'string' && params.requestId.trim()
                    ? params.requestId.trim()
                    : this._createRequestId(DEFAULT_REQUEST_PREFIX),
            };
        }

        _normalizeAttachKeyboardParams(params) {
            const safeParams = isPlainObject(params) ? params : {};
            const target = safeParams.target || global.document;
            if (!target || typeof target.addEventListener !== 'function' || typeof target.removeEventListener !== 'function') {
                throw createCommandPaletteError('Keyboard target must be an EventTarget', 'INVALID_KEYBOARD_TARGET');
            }
            return {
                target,
            };
        }

        _normalizeMountParams(params) {
            if (!isPlainObject(params) || !params.root || typeof params.root.addEventListener !== 'function') {
                throw createCommandPaletteError('mount requires a valid root element', 'INVALID_MOUNT_PARAMS');
            }
            return {
                root: params.root,
                input: params.input && typeof params.input.addEventListener === 'function' ? params.input : null,
                list: params.list && typeof params.list.addEventListener === 'function' ? params.list : null,
            };
        }

        _normalizeResultItem(item) {
            if (!isPlainObject(item) || typeof item.kind !== 'string') {
                throw createCommandPaletteError('Invalid result item', 'INVALID_RESULT_ITEM');
            }

            if (item.kind === RESULT_KIND.ACTION) {
                const id = typeof item.id === 'string' ? item.id.trim() : '';
                if (!id) {
                    throw createCommandPaletteError('Action item requires id', 'INVALID_ACTION_ITEM');
                }
                return {
                    kind: RESULT_KIND.ACTION,
                    id,
                    title: typeof item.title === 'string' ? item.title : id,
                    description: typeof item.description === 'string' ? item.description : null,
                    category: typeof item.category === 'string' ? item.category : null,
                    keywords: Array.isArray(item.keywords) ? item.keywords.map((entry) => String(entry)) : [],
                    enabled: item.enabled === true,
                    visible: item.visible !== false,
                    metadata: isPlainObject(item.metadata) ? cloneValue(item.metadata) : null,
                };
            }

            if (item.kind === RESULT_KIND.STOCK) {
                const code = typeof item.code === 'string' ? item.code.trim() : '';
                if (!code) {
                    throw createCommandPaletteError('Stock item requires code', 'INVALID_STOCK_ITEM');
                }
                return {
                    kind: RESULT_KIND.STOCK,
                    code,
                    name: typeof item.name === 'string' && item.name.trim() ? item.name.trim() : code,
                    market: typeof item.market === 'string' && item.market.trim() ? item.market.trim() : null,
                    exchange: typeof item.exchange === 'string' && item.exchange.trim() ? item.exchange.trim() : null,
                    sector: typeof item.sector === 'string' && item.sector.trim() ? item.sector.trim() : null,
                    metadata: isPlainObject(item.metadata) ? cloneValue(item.metadata) : null,
                };
            }

            throw createCommandPaletteError('Unsupported result item kind', 'INVALID_RESULT_ITEM_KIND');
        }

        _normalizeMode(mode) {
            if (typeof mode !== 'string' || !mode.trim()) {
                return this._state.mode;
            }
            const normalizedMode = mode.trim();
            if (!Object.values(PALETTE_MODE).includes(normalizedMode)) {
                throw createCommandPaletteError('Invalid command palette mode', 'INVALID_PALETTE_MODE');
            }
            return normalizedMode;
        }
    }

    const commandPaletteInternal = new CommandPaletteImpl(
        global.IntentBus,
        global.GlobalStockStore,
        global.StockSearchService,
        global.LocalMCP
    );

    const commandPalettePublicApi = Object.freeze({
        getState: commandPaletteInternal.getState.bind(commandPaletteInternal),
        subscribe: commandPaletteInternal.subscribe.bind(commandPaletteInternal),
        open: commandPaletteInternal.open.bind(commandPaletteInternal),
        close: commandPaletteInternal.close.bind(commandPaletteInternal),
        toggle: commandPaletteInternal.toggle.bind(commandPaletteInternal),
        setMode: commandPaletteInternal.setMode.bind(commandPaletteInternal),
        setQuery: commandPaletteInternal.setQuery.bind(commandPaletteInternal),
        refreshResults: commandPaletteInternal.refreshResults.bind(commandPaletteInternal),
        moveSelection: commandPaletteInternal.moveSelection.bind(commandPaletteInternal),
        getSelectedItem: commandPaletteInternal.getSelectedItem.bind(commandPaletteInternal),
        selectIndex: commandPaletteInternal.selectIndex.bind(commandPaletteInternal),
        executeSelection: commandPaletteInternal.executeSelection.bind(commandPaletteInternal),
        executeItem: commandPaletteInternal.executeItem.bind(commandPaletteInternal),
        attachKeyboardShortcuts: commandPaletteInternal.attachKeyboardShortcuts.bind(commandPaletteInternal),
        detachKeyboardShortcuts: commandPaletteInternal.detachKeyboardShortcuts.bind(commandPaletteInternal),
        mount: commandPaletteInternal.mount.bind(commandPaletteInternal),
        unmount: commandPaletteInternal.unmount.bind(commandPaletteInternal),
        reset: commandPaletteInternal.reset.bind(commandPaletteInternal),
    });

    global.CommandPalette = commandPalettePublicApi;
})(window);
