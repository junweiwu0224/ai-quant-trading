(function attachGlobalStockStore(global) {
    'use strict';

    if (!global.IntentBus) {
        throw new Error('GlobalStockStore requires window.IntentBus');
    }

    const STORE_EVENT_NAMES = Object.freeze({
        CHANGED: 'stock-store:changed',
        ACTIVE_CHANGED: 'stock-store:active-changed',
        SLICE_PATCHED: 'stock-store:slice-patched',
        REQUEST_REGISTERED: 'stock-store:request-registered',
        REQUEST_REJECTED: 'stock-store:request-rejected',
        RESET: 'stock-store:reset',
    });

    const STORE_REASONS = Object.freeze({
        SET_ACTIVE_STOCK: 'set_active_stock',
        PATCH_MARKET: 'patch_market',
        PATCH_ANALYSIS: 'patch_analysis',
        PATCH_TRADE_CONTEXT: 'patch_trade_context',
        PATCH_UI: 'patch_ui',
        SET_LOADING: 'set_loading',
        SET_ERROR: 'set_error',
        REGISTER_REQUEST: 'register_request',
        CLEAR_SLICE: 'clear_slice',
        RESET: 'reset',
    });

    const REJECTION_REASONS = Object.freeze({
        STALE_REQUEST: 'stale_request',
        REVISION_MISMATCH: 'revision_mismatch',
        NO_ACTIVE_STOCK: 'no_active_stock',
        INVALID_PATCH: 'invalid_patch',
    });

    const REQUEST_SCOPES = Object.freeze(['identity', 'market', 'analysis', 'tradeContext']);
    const PATCHABLE_SLICES = Object.freeze(['market', 'analysis', 'tradeContext', 'ui']);
    const CLEARABLE_SLICES = Object.freeze(['market', 'analysis', 'tradeContext']);
    const DEFAULT_REQUEST_PREFIX = 'stock-request';

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

    function createStoreError(message, code) {
        const error = new Error(message);
        error.name = 'GlobalStockStoreError';
        if (code) {
            error.code = code;
        }
        return error;
    }

    function createInitialState() {
        return {
            identity: {
                code: null,
                name: null,
                market: null,
                exchange: null,
            },
            market: {
                price: null,
                change: null,
                changePct: null,
                volume: null,
                amount: null,
                turnoverRate: null,
                amplitude: null,
                high: null,
                low: null,
                open: null,
                prevClose: null,
                updatedAt: null,
            },
            analysis: {
                score: null,
                signals: [],
                tags: [],
                factors: null,
                updatedAt: null,
            },
            tradeContext: {
                positionQty: null,
                availableQty: null,
                avgCost: null,
                pnl: null,
                pnlPct: null,
                watchlisted: false,
                strategyIds: [],
                updatedAt: null,
            },
            ui: {
                source: null,
                activePanel: null,
                isOpen: false,
                displayMode: 'hidden',
                width: null,
                panelParams: null,
                mountedPanelId: null,
                rootMounted: false,
                activePeriod: null,
                compareList: [],
                loading: {
                    identity: false,
                    market: false,
                    analysis: false,
                    tradeContext: false,
                },
                errors: {
                    identity: null,
                    market: null,
                    analysis: null,
                    tradeContext: null,
                },
            },
            meta: {
                revision: 0,
                activeRequestId: null,
                requestIds: {
                    identity: null,
                    market: null,
                    analysis: null,
                    tradeContext: null,
                },
                updatedAt: null,
                lastIntentTraceId: null,
            },
        };
    }

    class GlobalStockStoreImpl {
        constructor(intentBus) {
            this._intentBus = intentBus;
            this._listeners = [];
            this._requestSequence = 0;
            this._state = createInitialState();
        }

        getState() {
            return this._snapshotState();
        }

        getRevision() {
            return this._state.meta.revision;
        }

        subscribe(listener) {
            if (typeof listener !== 'function') {
                throw createStoreError('Listener must be a function', 'INVALID_LISTENER');
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

        setActiveStock(params) {
            const normalized = this._normalizeSetActiveStockParams(params);
            const previousState = this._state;
            const nextRevision = previousState.meta.revision + 1;
            const nextUpdatedAt = getNow();
            const nextRequestIds = this._buildRequestIdsForActiveStock(normalized.requestId);
            const nextUi = normalized.preserveUI
                ? {
                    ...previousState.ui,
                    source: normalized.source,
                    loading: { ...previousState.ui.loading },
                    errors: { ...previousState.ui.errors },
                    compareList: cloneValue(previousState.ui.compareList),
                }
                : this._buildResetUiState(normalized.source);
            const nextState = {
                identity: {
                    code: normalized.identity.code,
                    name: normalized.identity.name,
                    market: normalized.identity.market,
                    exchange: normalized.identity.exchange,
                },
                market: normalized.resetSlices.includes('market') ? createInitialState().market : cloneValue(previousState.market),
                analysis: normalized.resetSlices.includes('analysis') ? createInitialState().analysis : cloneValue(previousState.analysis),
                tradeContext: normalized.resetSlices.includes('tradeContext') ? createInitialState().tradeContext : cloneValue(previousState.tradeContext),
                ui: normalized.resetSlices.includes('ui') ? this._buildResetUiState(normalized.source) : nextUi,
                meta: {
                    revision: nextRevision,
                    activeRequestId: normalized.requestId,
                    requestIds: nextRequestIds,
                    updatedAt: nextUpdatedAt,
                    lastIntentTraceId: normalized.traceId,
                },
            };

            this._applyStateChange({
                nextState,
                previousState,
                changedSlices: ['identity', 'market', 'analysis', 'tradeContext', 'ui', 'meta'],
                reason: STORE_REASONS.SET_ACTIVE_STOCK,
                traceId: normalized.traceId,
                requestId: normalized.requestId,
                source: normalized.source,
            });

            this._emitStoreEvent(STORE_EVENT_NAMES.ACTIVE_CHANGED, {
                traceId: normalized.traceId,
                requestId: normalized.requestId,
                revision: nextRevision,
                identity: cloneValue(nextState.identity),
                source: normalized.source,
            });

            return {
                ok: true,
                revision: nextRevision,
                requestId: normalized.requestId,
                traceId: normalized.traceId,
                state: this.getState(),
            };
        }

        patchMarket(params) {
            return this._patchSliceOrReject('market', STORE_REASONS.PATCH_MARKET, params);
        }

        patchAnalysis(params) {
            return this._patchSliceOrReject('analysis', STORE_REASONS.PATCH_ANALYSIS, params);
        }

        patchTradeContext(params) {
            return this._patchSliceOrReject('tradeContext', STORE_REASONS.PATCH_TRADE_CONTEXT, params);
        }

        patchUI(params) {
            let normalized;
            try {
                normalized = this._normalizeUiPatchParams(params);
            } catch (error) {
                if (error && error.name === 'GlobalStockStoreError') {
                    return this._buildUiPatchRejectedResult(REJECTION_REASONS.INVALID_PATCH);
                }
                throw error;
            }
            const revisionCheck = this._validateRevision(normalized.expectedRevision);
            if (!revisionCheck.ok) {
                return this._buildUiPatchRejectedResult(REJECTION_REASONS.REVISION_MISMATCH);
            }

            const previousState = this._state;
            const nextRevision = previousState.meta.revision + 1;
            const nextUpdatedAt = getNow();
            const nextState = {
                ...previousState,
                ui: this._mergeSlice(previousState.ui, normalized.patch),
                meta: {
                    ...previousState.meta,
                    revision: nextRevision,
                    updatedAt: nextUpdatedAt,
                    lastIntentTraceId: normalized.traceId,
                },
            };

            this._applyStateChange({
                nextState,
                previousState,
                changedSlices: ['ui', 'meta'],
                reason: STORE_REASONS.PATCH_UI,
                traceId: normalized.traceId,
                requestId: null,
                source: normalized.source,
            });

            this._emitStoreEvent(STORE_EVENT_NAMES.SLICE_PATCHED, {
                traceId: normalized.traceId,
                requestId: null,
                revision: nextRevision,
                slice: 'ui',
                source: normalized.source,
            });

            return {
                ok: true,
                accepted: true,
                revision: nextRevision,
                state: this.getState(),
            };
        }

        setLoading(params) {
            const normalized = this._normalizeLoadingParams(params);
            const previousState = this._state;
            const nextRevision = previousState.meta.revision + 1;
            const nextUpdatedAt = getNow();
            const nextUi = {
                ...previousState.ui,
                loading: {
                    ...previousState.ui.loading,
                    [normalized.slice]: normalized.value,
                },
            };
            const nextState = {
                ...previousState,
                ui: nextUi,
                meta: {
                    ...previousState.meta,
                    revision: nextRevision,
                    updatedAt: nextUpdatedAt,
                    lastIntentTraceId: normalized.traceId,
                },
            };

            this._applyStateChange({
                nextState,
                previousState,
                changedSlices: ['ui', 'meta'],
                reason: STORE_REASONS.SET_LOADING,
                traceId: normalized.traceId,
                requestId: normalized.requestId,
                source: normalized.source,
            });

            return {
                ok: true,
                revision: nextRevision,
                state: this.getState(),
            };
        }

        setError(params) {
            const normalized = this._normalizeErrorParams(params);
            const previousState = this._state;
            const nextRevision = previousState.meta.revision + 1;
            const nextUpdatedAt = getNow();
            const nextUi = {
                ...previousState.ui,
                errors: {
                    ...previousState.ui.errors,
                    [normalized.slice]: normalized.message,
                },
            };
            const nextState = {
                ...previousState,
                ui: nextUi,
                meta: {
                    ...previousState.meta,
                    revision: nextRevision,
                    updatedAt: nextUpdatedAt,
                    lastIntentTraceId: normalized.traceId,
                },
            };

            this._applyStateChange({
                nextState,
                previousState,
                changedSlices: ['ui', 'meta'],
                reason: STORE_REASONS.SET_ERROR,
                traceId: normalized.traceId,
                requestId: normalized.requestId,
                source: normalized.source,
            });

            return {
                ok: true,
                revision: nextRevision,
                state: this.getState(),
            };
        }

        registerRequest(params) {
            const normalized = this._normalizeRegisterRequestParams(params);
            if (!this._hasActiveStock()) {
                return this._buildRequestRegistrationRejectedResult(normalized, REJECTION_REASONS.NO_ACTIVE_STOCK);
            }

            const revisionCheck = this._validateRevision(normalized.expectedRevision);
            if (!revisionCheck.ok) {
                return this._buildRequestRegistrationRejectedResult(normalized, REJECTION_REASONS.REVISION_MISMATCH);
            }

            const previousState = this._state;
            const nextRevision = previousState.meta.revision + 1;
            const nextUpdatedAt = getNow();
            const nextRequestIds = {
                ...previousState.meta.requestIds,
                [normalized.slice]: normalized.requestId,
            };
            const nextState = {
                ...previousState,
                meta: {
                    ...previousState.meta,
                    revision: nextRevision,
                    activeRequestId: normalized.requestId,
                    requestIds: nextRequestIds,
                    updatedAt: nextUpdatedAt,
                    lastIntentTraceId: normalized.traceId,
                },
            };

            this._applyStateChange({
                nextState,
                previousState,
                changedSlices: ['meta'],
                reason: STORE_REASONS.REGISTER_REQUEST,
                traceId: normalized.traceId,
                requestId: normalized.requestId,
                source: normalized.source,
            });

            this._emitStoreEvent(STORE_EVENT_NAMES.REQUEST_REGISTERED, {
                traceId: normalized.traceId,
                revision: nextRevision,
                slice: normalized.slice,
                requestId: normalized.requestId,
                source: normalized.source,
            });

            return {
                ok: true,
                accepted: true,
                revision: nextRevision,
                requestId: normalized.requestId,
                state: this.getState(),
            };
        }

        isRequestCurrent(params) {
            const normalized = this._normalizeRequestLookupParams(params);
            return this._state.meta.requestIds[normalized.slice] === normalized.requestId;
        }

        clearSlice(params) {
            const normalized = this._normalizeClearSliceParams(params);
            const revisionCheck = this._validateRevision(normalized.expectedRevision);
            if (!revisionCheck.ok) {
                return this._buildClearSliceRejectedResult(REJECTION_REASONS.REVISION_MISMATCH);
            }

            const previousState = this._state;
            const nextRevision = previousState.meta.revision + 1;
            const nextUpdatedAt = getNow();
            const initialState = createInitialState();
            const nextRequestIds = {
                ...previousState.meta.requestIds,
                [normalized.slice]: null,
            };
            const nextState = {
                ...previousState,
                [normalized.slice]: cloneValue(initialState[normalized.slice]),
                meta: {
                    ...previousState.meta,
                    revision: nextRevision,
                    requestIds: nextRequestIds,
                    updatedAt: nextUpdatedAt,
                    lastIntentTraceId: normalized.traceId,
                },
            };

            this._applyStateChange({
                nextState,
                previousState,
                changedSlices: [normalized.slice, 'meta'],
                reason: STORE_REASONS.CLEAR_SLICE,
                traceId: normalized.traceId,
                requestId: null,
                source: normalized.source,
            });

            return {
                ok: true,
                accepted: true,
                revision: nextRevision,
                state: this.getState(),
            };
        }

        reset(params) {
            const normalized = this._normalizeResetParams(params);
            const previousState = this._state;
            const nextRevision = previousState.meta.revision + 1;
            const nextUpdatedAt = getNow();
            const resetState = createInitialState();
            const nextState = {
                ...resetState,
                meta: {
                    ...resetState.meta,
                    revision: nextRevision,
                    updatedAt: nextUpdatedAt,
                    lastIntentTraceId: normalized.traceId,
                },
            };

            this._applyStateChange({
                nextState,
                previousState,
                changedSlices: ['identity', 'market', 'analysis', 'tradeContext', 'ui', 'meta'],
                reason: STORE_REASONS.RESET,
                traceId: normalized.traceId,
                requestId: null,
                source: normalized.source,
            });

            this._emitStoreEvent(STORE_EVENT_NAMES.RESET, {
                traceId: normalized.traceId,
                revision: nextRevision,
                source: normalized.source,
            });

            return {
                ok: true,
                revision: nextRevision,
                state: this.getState(),
            };
        }

        _patchSliceOrReject(slice, reason, params) {
            try {
                return this._patchSlice(slice, reason, params);
            } catch (error) {
                if (error && error.name === 'GlobalStockStoreError') {
                    const requestId = typeof params?.requestId === 'string' && params.requestId.trim() ? params.requestId.trim() : null;
                    const traceId = typeof params?.traceId === 'string' && params.traceId.trim() ? params.traceId.trim() : null;
                    const source = typeof params?.source === 'string' && params.source.trim() ? params.source.trim() : null;
                    return this._buildSlicePatchRejectedResult(slice, requestId, REJECTION_REASONS.INVALID_PATCH, traceId, source);
                }
                throw error;
            }
        }

        _patchSlice(slice, reason, params) {
            const normalized = this._normalizeSlicePatchParams(slice, params);
            if (!this._hasActiveStock()) {
                return this._buildSlicePatchRejectedResult(slice, normalized.requestId, REJECTION_REASONS.NO_ACTIVE_STOCK);
            }

            const revisionCheck = this._validateRevision(normalized.expectedRevision);
            if (!revisionCheck.ok) {
                return this._buildSlicePatchRejectedResult(slice, normalized.requestId, REJECTION_REASONS.REVISION_MISMATCH, normalized.traceId, normalized.source);
            }

            if (!this.isRequestCurrent({ slice, requestId: normalized.requestId })) {
                return this._buildSlicePatchRejectedResult(slice, normalized.requestId, REJECTION_REASONS.STALE_REQUEST, normalized.traceId, normalized.source);
            }

            const previousState = this._state;
            const nextRevision = previousState.meta.revision + 1;
            const nextUpdatedAt = getNow();
            const mergedSlice = this._mergeSlice(previousState[slice], normalized.patch);
            const nextState = {
                ...previousState,
                [slice]: mergedSlice,
                meta: {
                    ...previousState.meta,
                    revision: nextRevision,
                    updatedAt: nextUpdatedAt,
                    lastIntentTraceId: normalized.traceId,
                },
            };

            this._applyStateChange({
                nextState,
                previousState,
                changedSlices: [slice, 'meta'],
                reason,
                traceId: normalized.traceId,
                requestId: normalized.requestId,
                source: normalized.source,
            });

            this._emitStoreEvent(STORE_EVENT_NAMES.SLICE_PATCHED, {
                traceId: normalized.traceId,
                requestId: normalized.requestId,
                revision: nextRevision,
                slice,
                source: normalized.source,
            });

            return {
                ok: true,
                accepted: true,
                revision: nextRevision,
                requestId: normalized.requestId,
                state: this.getState(),
            };
        }

        _applyStateChange(change) {
            this._state = change.nextState;

            const payload = {
                state: this.getState(),
                previousState: this._createReadonlySnapshot(change.previousState),
                revision: change.nextState.meta.revision,
                changedSlices: change.changedSlices.slice(),
                traceId: change.traceId ?? null,
                requestId: change.requestId ?? null,
                reason: change.reason,
            };

            this._emitStoreEvent(STORE_EVENT_NAMES.CHANGED, {
                traceId: change.traceId ?? null,
                requestId: change.requestId ?? null,
                revision: change.nextState.meta.revision,
                previousRevision: change.previousState.meta.revision,
                changedSlices: change.changedSlices.slice(),
                reason: change.reason,
                state: this.getState(),
            });

            const listeners = this._listeners.slice();
            listeners.forEach((listener) => {
                try {
                    listener(payload);
                } catch (error) {
                    if (global.console && typeof global.console.error === 'function') {
                        global.console.error('[GlobalStockStore:subscribe]', error);
                    }
                }
            });
        }

        _emitStoreEvent(eventName, payload) {
            this._intentBus.emit(eventName, cloneValue(payload));
        }

        _snapshotState() {
            return this._createReadonlySnapshot(this._state);
        }

        _createReadonlySnapshot(state) {
            return deepFreeze(cloneValue(state));
        }

        _buildRequestIdsForActiveStock(activeRequestId) {
            return {
                identity: activeRequestId,
                market: null,
                analysis: null,
                tradeContext: null,
            };
        }

        _buildResetUiState(source) {
            const initialUi = createInitialState().ui;
            return {
                ...initialUi,
                loading: { ...initialUi.loading },
                errors: { ...initialUi.errors },
                compareList: cloneValue(initialUi.compareList),
                source: source,
            };
        }

        _mergeSlice(currentSlice, patch) {
            const baseSlice = cloneValue(currentSlice);
            const patchClone = cloneValue(patch);
            return this._mergeDeep(baseSlice, patchClone);
        }

        _mergeDeep(target, patch) {
            if (!isPlainObject(target) || !isPlainObject(patch)) {
                return cloneValue(patch);
            }

            const nextTarget = { ...target };
            Object.keys(patch).forEach((key) => {
                const currentValue = target[key];
                const patchValue = patch[key];
                if (isPlainObject(currentValue) && isPlainObject(patchValue)) {
                    nextTarget[key] = this._mergeDeep(currentValue, patchValue);
                    return;
                }
                nextTarget[key] = cloneValue(patchValue);
            });
            return nextTarget;
        }

        _hasActiveStock() {
            return typeof this._state.identity.code === 'string' && this._state.identity.code.trim() !== '';
        }

        _validateRevision(expectedRevision) {
            if (expectedRevision == null) {
                return { ok: true };
            }

            return {
                ok: expectedRevision === this._state.meta.revision,
            };
        }

        _normalizeSetActiveStockParams(params) {
            if (!isPlainObject(params)) {
                throw createStoreError('setActiveStock params must be a plain object', 'INVALID_SET_ACTIVE_STOCK_PARAMS');
            }

            const identity = isPlainObject(params.identity) ? params.identity : null;
            const code = typeof identity?.code === 'string' ? identity.code.trim() : '';
            if (!code) {
                throw createStoreError('setActiveStock identity.code is required', 'INVALID_ACTIVE_STOCK_CODE');
            }

            const resetSlices = Array.isArray(params.resetSlices)
                ? params.resetSlices.filter((slice) => ['market', 'analysis', 'tradeContext', 'ui'].includes(slice))
                : ['market', 'analysis', 'tradeContext'];

            return {
                identity: {
                    code,
                    name: typeof identity.name === 'string' ? identity.name.trim() || null : null,
                    market: typeof identity.market === 'string' ? identity.market.trim() || null : null,
                    exchange: typeof identity.exchange === 'string' ? identity.exchange.trim() || null : null,
                },
                source: typeof params.source === 'string' && params.source.trim() ? params.source.trim() : null,
                traceId: typeof params.traceId === 'string' && params.traceId.trim() ? params.traceId.trim() : null,
                requestId: typeof params.requestId === 'string' && params.requestId.trim() ? params.requestId.trim() : null,
                resetSlices,
                preserveUI: params.preserveUI === true,
            };
        }

        _normalizeSlicePatchParams(slice, params) {
            if (!PATCHABLE_SLICES.includes(slice) || slice === 'ui') {
                throw createStoreError(`Unsupported patch slice: ${slice}`, 'INVALID_PATCH_SLICE');
            }

            if (!isPlainObject(params)) {
                throw createStoreError(`${slice} patch params must be a plain object`, 'INVALID_PATCH_PARAMS');
            }

            if (!isPlainObject(params.patch)) {
                throw createStoreError(`${slice} patch must be a plain object`, 'INVALID_PATCH_OBJECT');
            }

            const requestId = typeof params.requestId === 'string' ? params.requestId.trim() : '';
            if (!requestId) {
                throw createStoreError(`${slice} patch requestId is required`, 'INVALID_REQUEST_ID');
            }

            return {
                patch: cloneValue(params.patch),
                requestId,
                traceId: typeof params.traceId === 'string' && params.traceId.trim() ? params.traceId.trim() : null,
                expectedRevision: params.expectedRevision == null ? null : Number(params.expectedRevision),
                source: typeof params.source === 'string' && params.source.trim() ? params.source.trim() : null,
            };
        }

        _normalizeUiPatchParams(params) {
            if (!isPlainObject(params)) {
                throw createStoreError('patchUI params must be a plain object', 'INVALID_UI_PATCH_PARAMS');
            }

            if (!isPlainObject(params.patch)) {
                throw createStoreError('patchUI patch must be a plain object', 'INVALID_UI_PATCH_OBJECT');
            }

            return {
                patch: cloneValue(params.patch),
                traceId: typeof params.traceId === 'string' && params.traceId.trim() ? params.traceId.trim() : null,
                source: typeof params.source === 'string' && params.source.trim() ? params.source.trim() : null,
                expectedRevision: params.expectedRevision == null ? null : Number(params.expectedRevision),
            };
        }

        _normalizeLoadingParams(params) {
            if (!isPlainObject(params)) {
                throw createStoreError('setLoading params must be a plain object', 'INVALID_LOADING_PARAMS');
            }

            if (!REQUEST_SCOPES.includes(params.slice)) {
                throw createStoreError('setLoading slice is invalid', 'INVALID_LOADING_SLICE');
            }

            return {
                slice: params.slice,
                value: params.value === true,
                requestId: typeof params.requestId === 'string' && params.requestId.trim() ? params.requestId.trim() : null,
                traceId: typeof params.traceId === 'string' && params.traceId.trim() ? params.traceId.trim() : null,
                source: typeof params.source === 'string' && params.source.trim() ? params.source.trim() : null,
            };
        }

        _normalizeErrorParams(params) {
            if (!isPlainObject(params)) {
                throw createStoreError('setError params must be a plain object', 'INVALID_ERROR_PARAMS');
            }

            if (!REQUEST_SCOPES.includes(params.slice)) {
                throw createStoreError('setError slice is invalid', 'INVALID_ERROR_SLICE');
            }

            return {
                slice: params.slice,
                message: params.message == null ? null : String(params.message),
                requestId: typeof params.requestId === 'string' && params.requestId.trim() ? params.requestId.trim() : null,
                traceId: typeof params.traceId === 'string' && params.traceId.trim() ? params.traceId.trim() : null,
                source: typeof params.source === 'string' && params.source.trim() ? params.source.trim() : null,
            };
        }

        _normalizeRegisterRequestParams(params) {
            if (!isPlainObject(params)) {
                throw createStoreError('registerRequest params must be a plain object', 'INVALID_REGISTER_REQUEST_PARAMS');
            }

            if (!REQUEST_SCOPES.includes(params.slice)) {
                throw createStoreError('registerRequest slice is invalid', 'INVALID_REGISTER_REQUEST_SLICE');
            }

            const requestId = typeof params.requestId === 'string' ? params.requestId.trim() : '';
            if (!requestId) {
                throw createStoreError('registerRequest requestId is required', 'INVALID_REGISTER_REQUEST_ID');
            }

            return {
                slice: params.slice,
                requestId,
                traceId: typeof params.traceId === 'string' && params.traceId.trim() ? params.traceId.trim() : null,
                source: typeof params.source === 'string' && params.source.trim() ? params.source.trim() : null,
                expectedRevision: params.expectedRevision == null ? null : Number(params.expectedRevision),
            };
        }

        _normalizeRequestLookupParams(params) {
            if (!isPlainObject(params)) {
                throw createStoreError('isRequestCurrent params must be a plain object', 'INVALID_REQUEST_LOOKUP_PARAMS');
            }

            if (!REQUEST_SCOPES.includes(params.slice)) {
                throw createStoreError('isRequestCurrent slice is invalid', 'INVALID_REQUEST_LOOKUP_SLICE');
            }

            const requestId = typeof params.requestId === 'string' ? params.requestId.trim() : '';
            if (!requestId) {
                throw createStoreError('isRequestCurrent requestId is required', 'INVALID_REQUEST_LOOKUP_ID');
            }

            return {
                slice: params.slice,
                requestId,
            };
        }

        _normalizeClearSliceParams(params) {
            if (!isPlainObject(params)) {
                throw createStoreError('clearSlice params must be a plain object', 'INVALID_CLEAR_SLICE_PARAMS');
            }

            if (!CLEARABLE_SLICES.includes(params.slice)) {
                throw createStoreError('clearSlice slice is invalid', 'INVALID_CLEAR_SLICE_NAME');
            }

            return {
                slice: params.slice,
                traceId: typeof params.traceId === 'string' && params.traceId.trim() ? params.traceId.trim() : null,
                source: typeof params.source === 'string' && params.source.trim() ? params.source.trim() : null,
                expectedRevision: params.expectedRevision == null ? null : Number(params.expectedRevision),
            };
        }

        _normalizeResetParams(params) {
            const safeParams = isPlainObject(params) ? params : {};
            return {
                traceId: typeof safeParams.traceId === 'string' && safeParams.traceId.trim() ? safeParams.traceId.trim() : null,
                source: typeof safeParams.source === 'string' && safeParams.source.trim() ? safeParams.source.trim() : null,
            };
        }

        _buildSlicePatchRejectedResult(slice, requestId, reason, traceId, source) {
            this._emitStoreEvent(STORE_EVENT_NAMES.REQUEST_REJECTED, {
                traceId: traceId ?? null,
                requestId,
                revision: this._state.meta.revision,
                slice,
                reason,
                source: source ?? null,
            });

            return {
                ok: true,
                accepted: false,
                reason,
                revision: this._state.meta.revision,
                requestId,
                state: this.getState(),
            };
        }

        _buildUiPatchRejectedResult(reason) {
            return {
                ok: true,
                accepted: false,
                reason,
                revision: this._state.meta.revision,
                state: this.getState(),
            };
        }

        _buildRequestRegistrationRejectedResult(normalized, reason) {
            this._emitStoreEvent(STORE_EVENT_NAMES.REQUEST_REJECTED, {
                traceId: normalized.traceId,
                requestId: normalized.requestId,
                revision: this._state.meta.revision,
                slice: normalized.slice,
                reason,
                source: normalized.source,
            });

            return {
                ok: true,
                accepted: false,
                reason,
                revision: this._state.meta.revision,
                requestId: normalized.requestId,
                state: this.getState(),
            };
        }

        _buildClearSliceRejectedResult(reason) {
            return {
                ok: true,
                accepted: false,
                reason,
                revision: this._state.meta.revision,
                state: this.getState(),
            };
        }
    }

    const globalStockStoreInternal = new GlobalStockStoreImpl(global.IntentBus);
    const globalStockStorePublicApi = Object.freeze({
        getState: globalStockStoreInternal.getState.bind(globalStockStoreInternal),
        getRevision: globalStockStoreInternal.getRevision.bind(globalStockStoreInternal),
        subscribe: globalStockStoreInternal.subscribe.bind(globalStockStoreInternal),
        createRequestId: globalStockStoreInternal.createRequestId.bind(globalStockStoreInternal),
        setActiveStock: globalStockStoreInternal.setActiveStock.bind(globalStockStoreInternal),
        patchMarket: globalStockStoreInternal.patchMarket.bind(globalStockStoreInternal),
        patchAnalysis: globalStockStoreInternal.patchAnalysis.bind(globalStockStoreInternal),
        patchTradeContext: globalStockStoreInternal.patchTradeContext.bind(globalStockStoreInternal),
        patchUI: globalStockStoreInternal.patchUI.bind(globalStockStoreInternal),
        setLoading: globalStockStoreInternal.setLoading.bind(globalStockStoreInternal),
        setError: globalStockStoreInternal.setError.bind(globalStockStoreInternal),
        registerRequest: globalStockStoreInternal.registerRequest.bind(globalStockStoreInternal),
        isRequestCurrent: globalStockStoreInternal.isRequestCurrent.bind(globalStockStoreInternal),
        clearSlice: globalStockStoreInternal.clearSlice.bind(globalStockStoreInternal),
        reset: globalStockStoreInternal.reset.bind(globalStockStoreInternal),
    });

    global.GlobalStockStore = globalStockStorePublicApi;
})(window);
