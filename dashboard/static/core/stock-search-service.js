(function attachStockSearchService(global) {
    'use strict';

    if (!global.IntentBus) {
        throw new Error('StockSearchService requires window.IntentBus');
    }

    if (!global.GlobalStockStore) {
        throw new Error('StockSearchService requires window.GlobalStockStore');
    }

    const SEARCH_EVENT_NAMES = Object.freeze({
        STARTED: 'stock-search:started',
        DEBOUNCING: 'stock-search:debouncing',
        SUCCEEDED: 'stock-search:succeeded',
        EMPTY: 'stock-search:empty',
        FAILED: 'stock-search:failed',
        CANCELLED: 'stock-search:cancelled',
        STALE_DISCARDED: 'stock-search:stale-discarded',
        SELECTION_RESOLVED: 'stock-search:selection-resolved',
        SELECTION_FAILED: 'stock-search:selection-failed',
        RESET: 'stock-search:reset',
    });

    const SEARCH_REASONS = Object.freeze({
        STARTED: 'search_started',
        DEBOUNCING: 'search_debouncing',
        SUCCEEDED: 'search_succeeded',
        EMPTY: 'search_empty',
        FAILED: 'search_failed',
        CANCELLED: 'search_cancelled',
        CLEARED: 'search_cleared',
        SELECTION_RESOLVED: 'selection_resolved',
        SELECTION_FAILED: 'selection_failed',
        RESET: 'reset',
    });

    const SEARCH_STATUS = Object.freeze({
        IDLE: 'idle',
        DEBOUNCING: 'debouncing',
        LOADING: 'loading',
        SUCCESS: 'success',
        EMPTY: 'empty',
        ERROR: 'error',
    });

    const CANCEL_REASONS = Object.freeze({
        REPLACED: 'replaced',
        MANUAL_CANCEL: 'manual_cancel',
        RESET: 'reset',
    });

    const SEARCH_SELECT_STRATEGY = Object.freeze({
        FIRST: 'first',
        EXACT_CODE: 'exact-code',
        EXACT_NAME: 'exact-name',
    });

    const DEFAULT_REQUEST_PREFIX = 'stock-search';
    const DEFAULT_LIMIT = 50;
    const DEFAULT_DEBOUNCE_MS = 300;

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

    function createSearchError(message, code) {
        const error = new Error(message);
        error.name = 'StockSearchServiceError';
        if (code) {
            error.code = code;
        }
        return error;
    }

    function createInitialState() {
        return {
            query: '',
            status: SEARCH_STATUS.IDLE,
            results: [],
            activeRequestId: null,
            activeRevision: null,
            lastCompletedRequestId: null,
            error: null,
            updatedAt: null,
        };
    }

    function getErrorMessage(error, fallbackMessage) {
        if (error instanceof Error) {
            return error.message || fallbackMessage;
        }

        if (typeof error === 'string' && error.trim()) {
            return error;
        }

        return fallbackMessage;
    }

    class StockSearchServiceImpl {
        constructor(intentBus, globalStockStore) {
            this._intentBus = intentBus;
            this._globalStockStore = globalStockStore;
            this._listeners = [];
            this._requestSequence = 0;
            this._state = createInitialState();
            this._adapter = {
                search: this._defaultSearchAdapter.bind(this),
            };
            this._pendingDebounceJob = null;
            this._requestControllers = new Map();
        }

        getState() {
            return this._snapshotState();
        }

        subscribe(listener) {
            if (typeof listener !== 'function') {
                throw createSearchError('Listener must be a function', 'INVALID_LISTENER');
            }

            this._listeners = [...this._listeners, listener];
            return () => {
                this._listeners = this._listeners.filter((item) => item !== listener);
            };
        }

        createRequestId(scope) {
            const safeScope = typeof scope === 'string' && scope.trim() ? scope.trim() : DEFAULT_REQUEST_PREFIX;
            this._requestSequence += 1;
            return `${safeScope}-${getNow()}-${this._requestSequence}`;
        }

        configureAdapter(adapter) {
            if (!isPlainObject(adapter) || typeof adapter.search !== 'function') {
                throw createSearchError('Adapter must provide a search function', 'INVALID_SEARCH_ADAPTER');
            }

            this._adapter = {
                search: adapter.search,
            };
        }

        async search(params) {
            const normalized = this._normalizeSearchParams(params);

            if (!normalized.query) {
                this._cancelPendingDebounce(CANCEL_REASONS.REPLACED, normalized.traceId, normalized.source);
                this._cancelInFlightRequest(CANCEL_REASONS.REPLACED, normalized.traceId, normalized.source);
                this._setState({
                    query: '',
                    status: SEARCH_STATUS.IDLE,
                    results: [],
                    activeRequestId: null,
                    error: null,
                    updatedAt: getNow(),
                }, SEARCH_REASONS.CLEARED, normalized.requestId);
                return {
                    ok: true,
                    accepted: true,
                    requestId: normalized.requestId,
                    status: 'empty',
                    results: [],
                    error: null,
                };
            }

            this._cancelPendingDebounce(CANCEL_REASONS.REPLACED, normalized.traceId, normalized.source);
            this._cancelInFlightRequest(CANCEL_REASONS.REPLACED, normalized.traceId, normalized.source);

            if (normalized.debounceMs > 0) {
                return this._scheduleDebouncedSearch(normalized);
            }

            return this._executeSearch(normalized);
        }

        cancelActiveSearch(params) {
            const normalized = this._normalizeCancelParams(params);
            const cancelledDebounceId = this._cancelPendingDebounce(normalized.reason, normalized.traceId, normalized.source);
            const cancelledActiveId = this._cancelInFlightRequest(normalized.reason, normalized.traceId, normalized.source);
            const cancelledRequestId = cancelledActiveId || cancelledDebounceId;

            if (cancelledRequestId) {
                this._setState({
                    activeRequestId: null,
                    status: SEARCH_STATUS.IDLE,
                    error: null,
                    updatedAt: getNow(),
                }, SEARCH_REASONS.CANCELLED, cancelledRequestId);
            }

            return {
                ok: true,
                cancelledRequestId,
            };
        }

        clearResults(params) {
            const normalized = this._normalizeSimpleParams(params);
            this._setState({
                results: [],
                error: null,
                status: SEARCH_STATUS.IDLE,
                activeRequestId: null,
                query: '',
                updatedAt: getNow(),
            }, SEARCH_REASONS.CLEARED, null);

            return {
                ok: true,
            };
        }

        async resolveSelection(params) {
            const normalized = this._normalizeSelectionParams(params);

            try {
                const result = this._globalStockStore.setActiveStock({
                    identity: {
                        code: normalized.item.code,
                        name: normalized.item.name,
                        market: normalized.item.market,
                        exchange: normalized.item.exchange,
                    },
                    source: normalized.source,
                    traceId: normalized.traceId,
                    requestId: normalized.requestId,
                    resetSlices: ['market', 'analysis', 'tradeContext'],
                    preserveUI: normalized.preserveUI,
                });

                if (!result || result.ok !== true) {
                    throw createSearchError('Failed to resolve stock selection', 'SELECTION_RESOLVE_FAILED');
                }

                this._setState({
                    activeRevision: result.revision,
                    error: null,
                    updatedAt: getNow(),
                }, SEARCH_REASONS.SELECTION_RESOLVED, normalized.requestId);

                this._emitEvent(SEARCH_EVENT_NAMES.SELECTION_RESOLVED, {
                    item: cloneValue(normalized.item),
                    traceId: normalized.traceId,
                    requestId: normalized.requestId,
                    source: normalized.source,
                    revision: result.revision,
                });

                return {
                    ok: true,
                    traceId: normalized.traceId,
                    requestId: normalized.requestId,
                    revision: result.revision,
                    state: result.state,
                };
            } catch (error) {
                const message = getErrorMessage(error, 'Failed to resolve stock selection');
                this._setState({
                    error: message,
                    updatedAt: getNow(),
                }, SEARCH_REASONS.SELECTION_FAILED, normalized.requestId);

                this._emitEvent(SEARCH_EVENT_NAMES.SELECTION_FAILED, {
                    item: cloneValue(normalized.item),
                    traceId: normalized.traceId,
                    requestId: normalized.requestId,
                    source: normalized.source,
                    error: message,
                });

                return {
                    ok: false,
                    traceId: normalized.traceId,
                    requestId: normalized.requestId,
                    revision: this._globalStockStore.getRevision(),
                    state: this._globalStockStore.getState(),
                    error: message,
                };
            }
        }

        async searchAndSelect(params) {
            const normalized = this._normalizeSearchAndSelectParams(params);
            const searchResult = await this.search({
                query: normalized.query,
                source: normalized.source,
                traceId: normalized.traceId,
                debounceMs: normalized.debounceMs,
                limit: normalized.limit,
                requestId: normalized.requestId,
            });

            if (!searchResult.accepted && searchResult.status === 'stale') {
                return {
                    ok: true,
                    accepted: false,
                    requestId: searchResult.requestId,
                    selected: null,
                    status: 'stale',
                    results: [],
                    error: null,
                };
            }

            if (searchResult.status === 'error') {
                return {
                    ok: false,
                    accepted: true,
                    requestId: searchResult.requestId,
                    selected: null,
                    status: 'error',
                    results: searchResult.results,
                    error: searchResult.error,
                };
            }

            if (searchResult.status === 'empty') {
                return {
                    ok: true,
                    accepted: true,
                    requestId: searchResult.requestId,
                    selected: null,
                    status: 'empty',
                    results: [],
                    error: null,
                };
            }

            const selected = this._selectResultItem(searchResult.results, normalized.query, normalized.strategy);
            if (!selected) {
                return {
                    ok: true,
                    accepted: true,
                    requestId: searchResult.requestId,
                    selected: null,
                    status: 'ambiguous',
                    results: searchResult.results,
                    error: null,
                };
            }

            const selectionResult = await this.resolveSelection({
                item: selected,
                source: normalized.source,
                traceId: normalized.traceId,
                requestId: searchResult.requestId,
                preserveUI: normalized.preserveUI,
            });

            if (!selectionResult.ok) {
                return {
                    ok: false,
                    accepted: true,
                    requestId: searchResult.requestId,
                    selected,
                    status: 'error',
                    results: searchResult.results,
                    error: selectionResult.error || 'Failed to resolve selection',
                };
            }

            return {
                ok: true,
                accepted: true,
                requestId: searchResult.requestId,
                selected,
                revision: selectionResult.revision,
                status: 'selected',
                results: searchResult.results,
                error: null,
            };
        }

        isRequestCurrent(requestId) {
            if (typeof requestId !== 'string' || requestId.trim() === '') {
                return false;
            }

            return this._state.activeRequestId === requestId.trim();
        }

        reset(params) {
            const normalized = this._normalizeSimpleParams(params);
            this._cancelPendingDebounce(CANCEL_REASONS.RESET, normalized.traceId, normalized.source);
            this._cancelInFlightRequest(CANCEL_REASONS.RESET, normalized.traceId, normalized.source);
            const nextState = createInitialState();
            nextState.updatedAt = getNow();
            this._setWholeState(nextState, SEARCH_REASONS.RESET, null);
            this._emitEvent(SEARCH_EVENT_NAMES.RESET, {
                traceId: normalized.traceId,
                source: normalized.source,
            });
            return {
                ok: true,
            };
        }

        _scheduleDebouncedSearch(normalized) {
            return new Promise((resolve) => {
                const timerId = setTimeout(() => {
                    if (!this._pendingDebounceJob || this._pendingDebounceJob.requestId !== normalized.requestId) {
                        resolve({
                            ok: true,
                            accepted: false,
                            requestId: normalized.requestId,
                            status: 'stale',
                            results: [],
                            error: null,
                        });
                        return;
                    }

                    this._pendingDebounceJob = null;
                    void this._executeSearch(normalized).then(resolve);
                }, normalized.debounceMs);

                this._pendingDebounceJob = {
                    requestId: normalized.requestId,
                    timerId,
                    resolve,
                    query: normalized.query,
                    traceId: normalized.traceId,
                    source: normalized.source,
                };

                this._setState({
                    query: normalized.query,
                    status: SEARCH_STATUS.DEBOUNCING,
                    activeRequestId: normalized.requestId,
                    activeRevision: this._globalStockStore.getRevision(),
                    error: null,
                    updatedAt: getNow(),
                }, SEARCH_REASONS.DEBOUNCING, normalized.requestId);

                this._emitEvent(SEARCH_EVENT_NAMES.DEBOUNCING, {
                    query: normalized.query,
                    requestId: normalized.requestId,
                    traceId: normalized.traceId,
                    source: normalized.source,
                    debounceMs: normalized.debounceMs,
                });
            });
        }

        async _executeSearch(normalized) {
            const controller = {
                requestId: normalized.requestId,
                query: normalized.query,
                traceId: normalized.traceId,
                source: normalized.source,
                resolveResult: null,
                settled: false,
            };
            this._requestControllers = new Map(this._requestControllers).set(normalized.requestId, controller);

            this._setState({
                query: normalized.query,
                status: SEARCH_STATUS.LOADING,
                activeRequestId: normalized.requestId,
                activeRevision: this._globalStockStore.getRevision(),
                error: null,
                updatedAt: getNow(),
            }, SEARCH_REASONS.STARTED, normalized.requestId);

            this._emitEvent(SEARCH_EVENT_NAMES.STARTED, {
                query: normalized.query,
                requestId: normalized.requestId,
                traceId: normalized.traceId,
                source: normalized.source,
                limit: normalized.limit,
            });

            try {
                const rawResults = await this._adapter.search({
                    query: normalized.query,
                    limit: normalized.limit,
                    requestId: normalized.requestId,
                    traceId: normalized.traceId,
                    source: normalized.source,
                });

                const results = this._normalizeSearchResults(rawResults);
                if (!this.isRequestCurrent(normalized.requestId)) {
                    this._emitEvent(SEARCH_EVENT_NAMES.STALE_DISCARDED, {
                        query: normalized.query,
                        requestId: normalized.requestId,
                        traceId: normalized.traceId,
                        source: normalized.source,
                        reason: 'stale_request',
                    });
                    this._deleteRequestController(normalized.requestId);
                    return {
                        ok: true,
                        accepted: false,
                        requestId: normalized.requestId,
                        status: 'stale',
                        results: [],
                        error: null,
                    };
                }

                const nextStatus = results.length > 0 ? SEARCH_STATUS.SUCCESS : SEARCH_STATUS.EMPTY;
                this._setState({
                    status: nextStatus,
                    results,
                    activeRequestId: normalized.requestId,
                    lastCompletedRequestId: normalized.requestId,
                    error: null,
                    updatedAt: getNow(),
                }, nextStatus === SEARCH_STATUS.SUCCESS ? SEARCH_REASONS.SUCCEEDED : SEARCH_REASONS.EMPTY, normalized.requestId);

                if (results.length > 0) {
                    this._emitEvent(SEARCH_EVENT_NAMES.SUCCEEDED, {
                        query: normalized.query,
                        requestId: normalized.requestId,
                        traceId: normalized.traceId,
                        source: normalized.source,
                        results: cloneValue(results),
                        count: results.length,
                    });
                } else {
                    this._emitEvent(SEARCH_EVENT_NAMES.EMPTY, {
                        query: normalized.query,
                        requestId: normalized.requestId,
                        traceId: normalized.traceId,
                        source: normalized.source,
                    });
                }

                this._deleteRequestController(normalized.requestId);
                return {
                    ok: true,
                    accepted: true,
                    requestId: normalized.requestId,
                    status: results.length > 0 ? 'success' : 'empty',
                    results,
                    error: null,
                };
            } catch (error) {
                const message = getErrorMessage(error, 'Stock search failed');
                if (!this.isRequestCurrent(normalized.requestId)) {
                    this._emitEvent(SEARCH_EVENT_NAMES.STALE_DISCARDED, {
                        query: normalized.query,
                        requestId: normalized.requestId,
                        traceId: normalized.traceId,
                        source: normalized.source,
                        reason: 'stale_request',
                    });
                    this._deleteRequestController(normalized.requestId);
                    return {
                        ok: true,
                        accepted: false,
                        requestId: normalized.requestId,
                        status: 'stale',
                        results: [],
                        error: null,
                    };
                }

                this._setState({
                    status: SEARCH_STATUS.ERROR,
                    error: message,
                    activeRequestId: normalized.requestId,
                    results: [],
                    updatedAt: getNow(),
                }, SEARCH_REASONS.FAILED, normalized.requestId);

                this._emitEvent(SEARCH_EVENT_NAMES.FAILED, {
                    query: normalized.query,
                    requestId: normalized.requestId,
                    traceId: normalized.traceId,
                    source: normalized.source,
                    error: message,
                });

                this._deleteRequestController(normalized.requestId);
                return {
                    ok: false,
                    accepted: true,
                    requestId: normalized.requestId,
                    status: 'error',
                    results: [],
                    error: message,
                };
            }
        }

        async _defaultSearchAdapter(params) {
            if (!global.App || typeof global.App.fetchJSON !== 'function') {
                throw createSearchError('Search adapter is not configured', 'SEARCH_ADAPTER_NOT_CONFIGURED');
            }

            const query = params.query ? `q=${encodeURIComponent(params.query)}` : 'q=';
            const limit = Number.isFinite(params.limit) && params.limit > 0 ? params.limit : DEFAULT_LIMIT;
            const response = await global.App.fetchJSON(`/api/stock/search?${query}&limit=${limit}`, { silent: true });
            return Array.isArray(response) ? response : [];
        }

        _normalizeSearchResults(rawResults) {
            if (!Array.isArray(rawResults)) {
                return [];
            }

            return rawResults
                .map((item) => this._normalizeResultItem(item))
                .filter(Boolean);
        }

        _normalizeResultItem(item) {
            if (!isPlainObject(item)) {
                return null;
            }

            const code = typeof item.code === 'string' ? item.code.trim() : '';
            if (!code) {
                return null;
            }

            const name = typeof item.name === 'string' && item.name.trim() ? item.name.trim() : code;
            const market = typeof item.market === 'string' && item.market.trim() ? item.market.trim() : null;
            const exchange = typeof item.exchange === 'string' && item.exchange.trim() ? item.exchange.trim() : null;
            const label = typeof item.label === 'string' && item.label.trim() ? item.label.trim() : `${code} ${name}`;
            const keywords = Array.isArray(item.keywords)
                ? item.keywords.map((entry) => String(entry)).filter((entry) => entry.trim() !== '')
                : [];

            return {
                code,
                name,
                market,
                exchange,
                label,
                keywords,
            };
        }

        _selectResultItem(results, query, strategy) {
            if (!Array.isArray(results) || results.length === 0) {
                return null;
            }

            if (strategy === SEARCH_SELECT_STRATEGY.FIRST) {
                return results[0];
            }

            const normalizedQuery = String(query || '').trim().toLowerCase();
            if (!normalizedQuery) {
                return results.length === 1 ? results[0] : null;
            }

            if (strategy === SEARCH_SELECT_STRATEGY.EXACT_CODE) {
                return results.find((item) => item.code.toLowerCase() === normalizedQuery) || null;
            }

            if (strategy === SEARCH_SELECT_STRATEGY.EXACT_NAME) {
                return results.find((item) => item.name.toLowerCase() === normalizedQuery) || null;
            }

            return results.length === 1 ? results[0] : null;
        }

        _cancelPendingDebounce(reason, traceId, source) {
            if (!this._pendingDebounceJob) {
                return null;
            }

            const job = this._pendingDebounceJob;
            clearTimeout(job.timerId);
            this._pendingDebounceJob = null;
            this._emitEvent(SEARCH_EVENT_NAMES.CANCELLED, {
                requestId: job.requestId,
                traceId: traceId ?? job.traceId ?? null,
                source: source ?? job.source ?? null,
                reason,
            });
            job.resolve({
                ok: true,
                accepted: false,
                requestId: job.requestId,
                status: 'stale',
                results: [],
                error: null,
            });
            return job.requestId;
        }

        _cancelInFlightRequest(reason, traceId, source) {
            const activeRequestId = this._state.activeRequestId;
            if (!activeRequestId) {
                return null;
            }

            const controller = this._requestControllers.get(activeRequestId);
            if (!controller || controller.settled) {
                return null;
            }

            controller.settled = true;
            this._requestControllers = new Map(this._requestControllers).set(activeRequestId, controller);
            this._emitEvent(SEARCH_EVENT_NAMES.CANCELLED, {
                requestId: activeRequestId,
                traceId: traceId ?? controller.traceId ?? null,
                source: source ?? controller.source ?? null,
                reason,
            });
            return activeRequestId;
        }

        _deleteRequestController(requestId) {
            if (!this._requestControllers.has(requestId)) {
                return;
            }

            const nextControllers = new Map(this._requestControllers);
            nextControllers.delete(requestId);
            this._requestControllers = nextControllers;
        }

        _setState(patch, reason, requestId) {
            const previousState = this._state;
            const nextState = {
                ...previousState,
                ...patch,
            };
            this._setWholeState(nextState, reason, requestId, previousState);
        }

        _setWholeState(nextState, reason, requestId, previousStateOverride) {
            const previousState = previousStateOverride || this._state;
            this._state = nextState;
            const payload = {
                state: this.getState(),
                previousState: this._createReadonlySnapshot(previousState),
                reason,
                requestId: requestId ?? null,
            };

            const listeners = this._listeners.slice();
            listeners.forEach((listener) => {
                try {
                    listener(payload);
                } catch (error) {
                    if (global.console && typeof global.console.error === 'function') {
                        global.console.error('[StockSearchService:subscribe]', error);
                    }
                }
            });
        }

        _emitEvent(eventName, payload) {
            this._intentBus.emit(eventName, cloneValue(payload));
        }

        _snapshotState() {
            return this._createReadonlySnapshot(this._state);
        }

        _createReadonlySnapshot(state) {
            return deepFreeze(cloneValue(state));
        }

        _normalizeSearchParams(params) {
            if (!isPlainObject(params)) {
                throw createSearchError('search params must be a plain object', 'INVALID_SEARCH_PARAMS');
            }

            const query = typeof params.query === 'string' ? params.query.trim() : '';
            const limit = Number.isFinite(Number(params.limit)) && Number(params.limit) > 0
                ? Number(params.limit)
                : DEFAULT_LIMIT;
            const debounceMs = Number.isFinite(Number(params.debounceMs)) && Number(params.debounceMs) >= 0
                ? Number(params.debounceMs)
                : DEFAULT_DEBOUNCE_MS;
            const requestId = typeof params.requestId === 'string' && params.requestId.trim()
                ? params.requestId.trim()
                : this.createRequestId(DEFAULT_REQUEST_PREFIX);

            return {
                query,
                source: typeof params.source === 'string' && params.source.trim() ? params.source.trim() : null,
                traceId: typeof params.traceId === 'string' && params.traceId.trim() ? params.traceId.trim() : null,
                debounceMs,
                limit,
                requestId,
            };
        }

        _normalizeCancelParams(params) {
            const safeParams = isPlainObject(params) ? params : {};
            const reason = Object.values(CANCEL_REASONS).includes(safeParams.reason)
                ? safeParams.reason
                : CANCEL_REASONS.MANUAL_CANCEL;
            return {
                reason,
                traceId: typeof safeParams.traceId === 'string' && safeParams.traceId.trim() ? safeParams.traceId.trim() : null,
                source: typeof safeParams.source === 'string' && safeParams.source.trim() ? safeParams.source.trim() : null,
            };
        }

        _normalizeSimpleParams(params) {
            const safeParams = isPlainObject(params) ? params : {};
            return {
                traceId: typeof safeParams.traceId === 'string' && safeParams.traceId.trim() ? safeParams.traceId.trim() : null,
                source: typeof safeParams.source === 'string' && safeParams.source.trim() ? safeParams.source.trim() : null,
            };
        }

        _normalizeSelectionParams(params) {
            if (!isPlainObject(params)) {
                throw createSearchError('resolveSelection params must be a plain object', 'INVALID_SELECTION_PARAMS');
            }

            const item = this._normalizeResultItem(params.item);
            if (!item) {
                throw createSearchError('resolveSelection item is invalid', 'INVALID_SELECTION_ITEM');
            }

            return {
                item,
                source: typeof params.source === 'string' && params.source.trim() ? params.source.trim() : null,
                traceId: typeof params.traceId === 'string' && params.traceId.trim() ? params.traceId.trim() : null,
                requestId: typeof params.requestId === 'string' && params.requestId.trim() ? params.requestId.trim() : null,
                preserveUI: params.preserveUI === true,
            };
        }

        _normalizeSearchAndSelectParams(params) {
            if (!isPlainObject(params)) {
                throw createSearchError('searchAndSelect params must be a plain object', 'INVALID_SEARCH_AND_SELECT_PARAMS');
            }

            const strategy = Object.values(SEARCH_SELECT_STRATEGY).includes(params.strategy)
                ? params.strategy
                : SEARCH_SELECT_STRATEGY.FIRST;

            return {
                query: typeof params.query === 'string' ? params.query.trim() : '',
                source: typeof params.source === 'string' && params.source.trim() ? params.source.trim() : null,
                traceId: typeof params.traceId === 'string' && params.traceId.trim() ? params.traceId.trim() : null,
                debounceMs: Number.isFinite(Number(params.debounceMs)) && Number(params.debounceMs) >= 0
                    ? Number(params.debounceMs)
                    : DEFAULT_DEBOUNCE_MS,
                limit: Number.isFinite(Number(params.limit)) && Number(params.limit) > 0
                    ? Number(params.limit)
                    : DEFAULT_LIMIT,
                strategy,
                requestId: typeof params.requestId === 'string' && params.requestId.trim()
                    ? params.requestId.trim()
                    : this.createRequestId(DEFAULT_REQUEST_PREFIX),
                preserveUI: params.preserveUI === true,
            };
        }
    }

    const stockSearchServiceInternal = new StockSearchServiceImpl(global.IntentBus, global.GlobalStockStore);
    const stockSearchServicePublicApi = Object.freeze({
        getState: stockSearchServiceInternal.getState.bind(stockSearchServiceInternal),
        subscribe: stockSearchServiceInternal.subscribe.bind(stockSearchServiceInternal),
        createRequestId: stockSearchServiceInternal.createRequestId.bind(stockSearchServiceInternal),
        configureAdapter: stockSearchServiceInternal.configureAdapter.bind(stockSearchServiceInternal),
        search: stockSearchServiceInternal.search.bind(stockSearchServiceInternal),
        cancelActiveSearch: stockSearchServiceInternal.cancelActiveSearch.bind(stockSearchServiceInternal),
        clearResults: stockSearchServiceInternal.clearResults.bind(stockSearchServiceInternal),
        resolveSelection: stockSearchServiceInternal.resolveSelection.bind(stockSearchServiceInternal),
        searchAndSelect: stockSearchServiceInternal.searchAndSelect.bind(stockSearchServiceInternal),
        isRequestCurrent: stockSearchServiceInternal.isRequestCurrent.bind(stockSearchServiceInternal),
        reset: stockSearchServiceInternal.reset.bind(stockSearchServiceInternal),
    });

    global.StockSearchService = stockSearchServicePublicApi;
})(window);
