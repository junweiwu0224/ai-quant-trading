(function attachActionRegistry(global) {
    'use strict';

    if (!global.IntentBus) {
        throw new Error('ActionRegistry requires window.IntentBus');
    }

    if (!global.GlobalStockStore) {
        throw new Error('ActionRegistry requires window.GlobalStockStore');
    }

    const REGISTRY_EVENT_NAMES = Object.freeze({
        REGISTERED: 'action-registry:registered',
        UNREGISTERED: 'action-registry:unregistered',
        CHANGED: 'action-registry:changed',
        EXECUTE_STARTED: 'action-registry:execute-started',
        EXECUTE_BLOCKED: 'action-registry:execute-blocked',
        EXECUTE_SUCCEEDED: 'action-registry:execute-succeeded',
        EXECUTE_FAILED: 'action-registry:execute-failed',
        NOT_FOUND: 'action-registry:not-found',
        RESET: 'action-registry:reset',
    });

    const REGISTRY_REASONS = Object.freeze({
        REPLACE: 'replace',
        SET_ENABLED: 'set_enabled',
        BULK_REGISTER: 'bulk_register',
    });

    const ACTION_STATUS = Object.freeze({
        SUCCESS: 'success',
        BLOCKED: 'blocked',
        NOT_FOUND: 'not_found',
        FAILED: 'failed',
    });

    const DEFAULT_TRACE_PREFIX = 'action';

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

    function createRegistryError(message, code) {
        const error = new Error(message);
        error.name = 'ActionRegistryError';
        if (code) {
            error.code = code;
        }
        return error;
    }

    function getErrorShape(error, fallbackMessage) {
        if (error instanceof Error) {
            return {
                message: error.message || fallbackMessage,
                name: error.name || 'Error',
                code: typeof error.code === 'string' ? error.code : null,
            };
        }

        if (typeof error === 'string' && error.trim()) {
            return {
                message: error,
                name: 'Error',
                code: null,
            };
        }

        if (error && typeof error === 'object') {
            return {
                message: typeof error.message === 'string' && error.message ? error.message : fallbackMessage,
                name: typeof error.name === 'string' && error.name ? error.name : 'Error',
                code: typeof error.code === 'string' ? error.code : null,
            };
        }

        return {
            message: fallbackMessage,
            name: 'Error',
            code: null,
        };
    }

    class ActionRegistryImpl {
        constructor(intentBus, globalStockStore) {
            this._intentBus = intentBus;
            this._globalStockStore = globalStockStore;
            this._actions = new Map();
            this._traceSequence = 0;
        }

        register(actionDefinition) {
            const normalized = this._normalizeActionDefinition(actionDefinition);
            if (this._actions.has(normalized.id)) {
                throw createRegistryError(`Action already registered: ${normalized.id}`, 'ACTION_ALREADY_REGISTERED');
            }

            this._actions = new Map(this._actions).set(normalized.id, normalized);
            this._emitEvent(REGISTRY_EVENT_NAMES.REGISTERED, {
                actionId: normalized.id,
                category: normalized.category,
                title: normalized.title,
            });
            this._emitEvent(REGISTRY_EVENT_NAMES.CHANGED, {
                actionId: normalized.id,
                reason: 'register',
            });

            return {
                ok: true,
                actionId: normalized.id,
            };
        }

        registerMany(actionDefinitions) {
            if (!Array.isArray(actionDefinitions)) {
                throw createRegistryError('registerMany expects an array', 'INVALID_REGISTER_MANY_INPUT');
            }

            const normalizedDefinitions = actionDefinitions.map((actionDefinition) => {
                return this._normalizeActionDefinition(actionDefinition);
            });

            const nextActions = new Map(this._actions);
            const duplicateIds = [];

            normalizedDefinitions.forEach((actionDefinition) => {
                if (nextActions.has(actionDefinition.id)) {
                    duplicateIds.push(actionDefinition.id);
                    return;
                }

                nextActions.set(actionDefinition.id, actionDefinition);
            });

            if (duplicateIds.length > 0) {
                throw createRegistryError(
                    `Action already registered: ${duplicateIds.join(', ')}`,
                    'ACTION_ALREADY_REGISTERED'
                );
            }

            this._actions = nextActions;

            const registered = normalizedDefinitions.map((actionDefinition) => actionDefinition.id);
            registered.forEach((actionId) => {
                const action = this._actions.get(actionId);
                this._emitEvent(REGISTRY_EVENT_NAMES.REGISTERED, {
                    actionId,
                    category: action.category,
                    title: action.title,
                });
            });

            this._emitEvent(REGISTRY_EVENT_NAMES.CHANGED, {
                reason: REGISTRY_REASONS.BULK_REGISTER,
                actionIds: cloneValue(registered),
            });

            return {
                ok: true,
                registered,
                rejected: [],
            };
        }

        replace(actionDefinition) {
            const normalized = this._normalizeActionDefinition(actionDefinition);
            this._actions = new Map(this._actions).set(normalized.id, normalized);
            this._emitEvent(REGISTRY_EVENT_NAMES.REGISTERED, {
                actionId: normalized.id,
                category: normalized.category,
                title: normalized.title,
            });
            this._emitEvent(REGISTRY_EVENT_NAMES.CHANGED, {
                actionId: normalized.id,
                reason: REGISTRY_REASONS.REPLACE,
            });

            return {
                ok: true,
                actionId: normalized.id,
            };
        }

        unregister(actionId) {
            const normalizedActionId = this._normalizeActionId(actionId);
            if (!this._actions.has(normalizedActionId)) {
                return {
                    ok: false,
                    actionId: normalizedActionId,
                    reason: 'action_not_found',
                    code: 'ACTION_NOT_FOUND',
                };
            }

            const nextActions = new Map(this._actions);
            nextActions.delete(normalizedActionId);
            this._actions = nextActions;
            this._emitEvent(REGISTRY_EVENT_NAMES.UNREGISTERED, {
                actionId: normalizedActionId,
            });
            this._emitEvent(REGISTRY_EVENT_NAMES.CHANGED, {
                actionId: normalizedActionId,
                reason: 'unregister',
            });

            return {
                ok: true,
                actionId: normalizedActionId,
            };
        }

        get(actionId) {
            const normalizedActionId = this._normalizeActionId(actionId);
            const action = this._actions.get(normalizedActionId);
            return action ? this._snapshotAction(action) : null;
        }

        list(filters) {
            const normalizedFilters = this._normalizeListFilters(filters);
            return Array.from(this._actions.values())
                .filter((action) => this._matchesFilters(action, normalizedFilters))
                .map((action) => this._snapshotAction(action));
        }

        has(actionId) {
            const normalizedActionId = this._normalizeActionId(actionId);
            return this._actions.has(normalizedActionId);
        }

        setEnabled(params) {
            const normalized = this._normalizeSetEnabledParams(params);
            const action = this._actions.get(normalized.actionId);
            if (!action) {
                throw createRegistryError(`Action not found: ${normalized.actionId}`, 'ACTION_NOT_FOUND');
            }

            const nextAction = {
                ...action,
                enabled: normalized.enabled,
            };
            this._actions = new Map(this._actions).set(normalized.actionId, nextAction);
            this._emitEvent(REGISTRY_EVENT_NAMES.CHANGED, {
                actionId: normalized.actionId,
                reason: REGISTRY_REASONS.SET_ENABLED,
            });

            return {
                ok: true,
                actionId: normalized.actionId,
                enabled: normalized.enabled,
            };
        }

        async execute(params) {
            const normalized = this._normalizeExecuteParams(params);
            const startedAt = getNow();
            const action = this._actions.get(normalized.actionId);

            if (!action) {
                this._emitEvent(REGISTRY_EVENT_NAMES.NOT_FOUND, {
                    actionId: normalized.actionId,
                    traceId: normalized.traceId,
                    requestId: normalized.requestId,
                    source: normalized.source,
                });
                const finishedAt = getNow();
                return {
                    ok: false,
                    actionId: normalized.actionId,
                    traceId: normalized.traceId,
                    requestId: normalized.requestId,
                    source: normalized.source,
                    status: ACTION_STATUS.NOT_FOUND,
                    reason: 'action_not_found',
                    code: 'ACTION_NOT_FOUND',
                    result: undefined,
                    error: null,
                    startedAt,
                    finishedAt,
                    durationMs: finishedAt - startedAt,
                };
            }

            const context = this.buildContext({
                actionId: normalized.actionId,
                payload: normalized.payload,
                source: normalized.source,
                traceId: normalized.traceId,
                requestId: normalized.requestId,
                metadata: normalized.metadata,
                startedAt,
            });

            this._emitEvent(REGISTRY_EVENT_NAMES.EXECUTE_STARTED, {
                actionId: normalized.actionId,
                traceId: context.traceId,
                requestId: context.requestId,
                source: context.source,
                revision: context.revision,
                payload: cloneValue(context.payload),
            });

            const guardResult = await this._evaluateGuard(action, context);
            if (!guardResult.ok) {
                const finishedAt = getNow();
                this._emitEvent(REGISTRY_EVENT_NAMES.EXECUTE_BLOCKED, {
                    actionId: normalized.actionId,
                    traceId: context.traceId,
                    requestId: context.requestId,
                    source: context.source,
                    reason: guardResult.reason,
                    code: guardResult.code,
                });
                return {
                    ok: false,
                    actionId: normalized.actionId,
                    traceId: context.traceId,
                    requestId: context.requestId,
                    source: context.source,
                    status: ACTION_STATUS.BLOCKED,
                    reason: guardResult.reason,
                    code: guardResult.code,
                    result: undefined,
                    error: null,
                    startedAt,
                    finishedAt,
                    durationMs: finishedAt - startedAt,
                };
            }

            let executableContext;

            try {
                executableContext = this._buildExecutableContext(action, context);
            } catch (error) {
                const finishedAt = getNow();
                const errorShape = getErrorShape(error, 'Action payload build failed');
                this._emitEvent(REGISTRY_EVENT_NAMES.EXECUTE_FAILED, {
                    actionId: normalized.actionId,
                    traceId: context.traceId,
                    requestId: context.requestId,
                    source: context.source,
                    revision: context.revision,
                    error: errorShape,
                    durationMs: finishedAt - startedAt,
                });
                return {
                    ok: false,
                    actionId: normalized.actionId,
                    traceId: context.traceId,
                    requestId: context.requestId,
                    source: context.source,
                    status: ACTION_STATUS.FAILED,
                    reason: 'action_payload_build_failed',
                    code: errorShape.code,
                    result: undefined,
                    error: errorShape,
                    startedAt,
                    finishedAt,
                    durationMs: finishedAt - startedAt,
                };
            }

            try {
                const result = await action.handler(executableContext);
                const finishedAt = getNow();
                this._emitEvent(REGISTRY_EVENT_NAMES.EXECUTE_SUCCEEDED, {
                    actionId: normalized.actionId,
                    traceId: executableContext.traceId,
                    requestId: executableContext.requestId,
                    source: executableContext.source,
                    revision: executableContext.revision,
                    result: cloneValue(result),
                    durationMs: finishedAt - startedAt,
                });
                return {
                    ok: true,
                    actionId: normalized.actionId,
                    traceId: executableContext.traceId,
                    requestId: executableContext.requestId,
                    source: executableContext.source,
                    status: ACTION_STATUS.SUCCESS,
                    reason: null,
                    code: null,
                    result,
                    error: null,
                    startedAt,
                    finishedAt,
                    durationMs: finishedAt - startedAt,
                };
            } catch (error) {
                const finishedAt = getNow();
                const errorShape = getErrorShape(error, 'Action execution failed');
                this._emitEvent(REGISTRY_EVENT_NAMES.EXECUTE_FAILED, {
                    actionId: normalized.actionId,
                    traceId: executableContext.traceId,
                    requestId: executableContext.requestId,
                    source: executableContext.source,
                    revision: executableContext.revision,
                    error: errorShape,
                    durationMs: finishedAt - startedAt,
                });
                return {
                    ok: false,
                    actionId: normalized.actionId,
                    traceId: executableContext.traceId,
                    requestId: executableContext.requestId,
                    source: executableContext.source,
                    status: ACTION_STATUS.FAILED,
                    reason: 'action_execution_failed',
                    code: errorShape.code,
                    result: undefined,
                    error: errorShape,
                    startedAt,
                    finishedAt,
                    durationMs: finishedAt - startedAt,
                };
            }
        }

        async canExecute(params) {
            const normalized = this._normalizeExecuteParams(params);
            const action = this._actions.get(normalized.actionId);
            if (!action) {
                return {
                    ok: false,
                    executable: false,
                    actionId: normalized.actionId,
                    reason: 'action_not_found',
                    code: 'ACTION_NOT_FOUND',
                };
            }

            const context = this.buildContext({
                actionId: normalized.actionId,
                payload: normalized.payload,
                source: normalized.source,
                traceId: normalized.traceId,
                requestId: normalized.requestId,
                metadata: normalized.metadata,
            });

            try {
                const guardResult = await this._evaluateGuard(action, context);
                return {
                    ok: true,
                    executable: guardResult.ok,
                    actionId: normalized.actionId,
                    reason: guardResult.ok ? null : guardResult.reason,
                    code: guardResult.ok ? null : guardResult.code,
                };
            } catch (error) {
                const errorShape = getErrorShape(error, 'Action guard failed');
                return {
                    ok: false,
                    executable: false,
                    actionId: normalized.actionId,
                    reason: 'guard_execution_failed',
                    code: errorShape.code || 'GUARD_EXECUTION_FAILED',
                    error: errorShape,
                };
            }
        }

        buildContext(params) {
            const normalized = this._normalizeContextParams(params);
            const stockState = this._globalStockStore.getState();
            const revision = this._globalStockStore.getRevision();
            const activeStock = {
                code: stockState.identity.code,
                name: stockState.identity.name,
                market: stockState.identity.market,
                exchange: stockState.identity.exchange,
            };

            return deepFreeze({
                actionId: normalized.actionId,
                traceId: normalized.traceId,
                requestId: normalized.requestId,
                source: normalized.source,
                stockState,
                activeStock,
                payload: cloneValue(normalized.payload),
                builtPayload: null,
                metadata: cloneValue(normalized.metadata),
                revision,
                startedAt: normalized.startedAt ?? getNow(),
            });
        }

        reset() {
            const countBeforeReset = this._actions.size;
            this._actions = new Map();
            this._emitEvent(REGISTRY_EVENT_NAMES.RESET, {
                countBeforeReset,
            });
            return {
                ok: true,
            };
        }

        async _evaluateGuard(action, context) {
            if (action.enabled !== true) {
                return {
                    ok: false,
                    reason: 'action_disabled',
                    code: 'ACTION_DISABLED',
                };
            }

            if (typeof action.guard !== 'function') {
                return { ok: true, reason: null, code: null };
            }

            try {
                const guardResult = await action.guard(context);
                return this._normalizeGuardResult(guardResult);
            } catch (error) {
                const errorShape = getErrorShape(error, 'Action guard failed');
                return {
                    ok: false,
                    reason: 'guard_execution_failed',
                    code: errorShape.code || 'GUARD_EXECUTION_FAILED',
                    error: errorShape,
                };
            }
        }

        _buildExecutableContext(action, context) {
            const builtPayload = typeof action.buildPayload === 'function'
                ? action.buildPayload(context)
                : null;

            return deepFreeze({
                ...cloneValue(context),
                builtPayload: cloneValue(builtPayload),
            });
        }

        _normalizeGuardResult(guardResult) {
            if (guardResult === true) {
                return { ok: true, reason: null, code: null };
            }

            if (guardResult === false) {
                return {
                    ok: false,
                    reason: 'guard_blocked',
                    code: 'GUARD_BLOCKED',
                };
            }

            if (!isPlainObject(guardResult)) {
                return { ok: true, reason: null, code: null };
            }

            return {
                ok: guardResult.ok === true,
                reason: typeof guardResult.reason === 'string' ? guardResult.reason : null,
                code: typeof guardResult.code === 'string' ? guardResult.code : null,
            };
        }

        _matchesFilters(action, filters) {
            if (filters.category && action.category !== filters.category) {
                return false;
            }

            if (filters.visibleOnly && action.visible !== true) {
                return false;
            }

            if (filters.enabledOnly && action.enabled !== true) {
                return false;
            }

            if (!filters.query) {
                return true;
            }

            const query = filters.query;
            const haystack = [
                action.id,
                action.title,
                action.description || '',
                action.category || '',
                ...(Array.isArray(action.keywords) ? action.keywords : []),
            ].join(' ').toLowerCase();

            return haystack.includes(query);
        }

        _snapshotAction(action) {
            return deepFreeze(cloneValue({
                id: action.id,
                title: action.title,
                description: action.description,
                category: action.category,
                keywords: cloneValue(action.keywords),
                icon: action.icon,
                enabled: action.enabled,
                visible: action.visible,
                guard: action.guard,
                handler: action.handler,
                buildPayload: action.buildPayload,
                metadata: cloneValue(action.metadata),
            }));
        }

        _emitEvent(eventName, payload) {
            this._intentBus.emit(eventName, cloneValue(payload));
        }

        _normalizeActionDefinition(actionDefinition) {
            if (!isPlainObject(actionDefinition)) {
                throw createRegistryError('Action definition must be a plain object', 'INVALID_ACTION_DEFINITION');
            }

            const id = this._normalizeActionId(actionDefinition.id);
            const title = typeof actionDefinition.title === 'string' ? actionDefinition.title.trim() : '';
            if (!title) {
                throw createRegistryError('Action title is required', 'INVALID_ACTION_TITLE');
            }

            if (typeof actionDefinition.handler !== 'function') {
                throw createRegistryError('Action handler is required', 'INVALID_ACTION_HANDLER');
            }

            if (actionDefinition.guard != null && typeof actionDefinition.guard !== 'function') {
                throw createRegistryError('Action guard must be a function', 'INVALID_ACTION_GUARD');
            }

            if (actionDefinition.buildPayload != null && typeof actionDefinition.buildPayload !== 'function') {
                throw createRegistryError('Action buildPayload must be a function', 'INVALID_ACTION_BUILD_PAYLOAD');
            }

            return {
                id,
                title,
                description: typeof actionDefinition.description === 'string' && actionDefinition.description.trim()
                    ? actionDefinition.description.trim()
                    : null,
                category: typeof actionDefinition.category === 'string' && actionDefinition.category.trim()
                    ? actionDefinition.category.trim()
                    : null,
                keywords: Array.isArray(actionDefinition.keywords)
                    ? actionDefinition.keywords.map((item) => String(item)).filter((item) => item.trim() !== '')
                    : [],
                icon: typeof actionDefinition.icon === 'string' && actionDefinition.icon.trim()
                    ? actionDefinition.icon.trim()
                    : null,
                enabled: actionDefinition.enabled !== false,
                visible: actionDefinition.visible !== false,
                guard: actionDefinition.guard || null,
                handler: actionDefinition.handler,
                buildPayload: actionDefinition.buildPayload || null,
                metadata: isPlainObject(actionDefinition.metadata) ? cloneValue(actionDefinition.metadata) : null,
            };
        }

        _normalizeActionId(actionId) {
            const normalizedActionId = typeof actionId === 'string' ? actionId.trim() : '';
            if (!normalizedActionId) {
                throw createRegistryError('Action ID is required', 'INVALID_ACTION_ID');
            }
            return normalizedActionId;
        }

        _normalizeListFilters(filters) {
            const safeFilters = isPlainObject(filters) ? filters : {};
            return {
                category: typeof safeFilters.category === 'string' && safeFilters.category.trim()
                    ? safeFilters.category.trim()
                    : null,
                visibleOnly: safeFilters.visibleOnly === true,
                enabledOnly: safeFilters.enabledOnly === true,
                query: typeof safeFilters.query === 'string' && safeFilters.query.trim()
                    ? safeFilters.query.trim().toLowerCase()
                    : null,
            };
        }

        _normalizeSetEnabledParams(params) {
            if (!isPlainObject(params)) {
                throw createRegistryError('setEnabled params must be a plain object', 'INVALID_SET_ENABLED_PARAMS');
            }

            return {
                actionId: this._normalizeActionId(params.actionId),
                enabled: params.enabled === true,
            };
        }

        _normalizeExecuteParams(params) {
            if (!isPlainObject(params)) {
                throw createRegistryError('execute params must be a plain object', 'INVALID_EXECUTE_PARAMS');
            }

            return {
                actionId: this._normalizeActionId(params.actionId),
                payload: isPlainObject(params.payload) ? cloneValue(params.payload) : (params.payload == null ? null : cloneValue(params.payload)),
                source: typeof params.source === 'string' && params.source.trim() ? params.source.trim() : null,
                traceId: typeof params.traceId === 'string' && params.traceId.trim()
                    ? params.traceId.trim()
                    : this._createTraceId(DEFAULT_TRACE_PREFIX),
                requestId: typeof params.requestId === 'string' && params.requestId.trim() ? params.requestId.trim() : null,
                metadata: isPlainObject(params.metadata) ? cloneValue(params.metadata) : null,
            };
        }

        _normalizeContextParams(params) {
            const safeParams = isPlainObject(params) ? params : {};
            return {
                actionId: safeParams.actionId == null ? null : this._normalizeActionId(safeParams.actionId),
                payload: safeParams.payload == null ? null : cloneValue(safeParams.payload),
                source: typeof safeParams.source === 'string' && safeParams.source.trim() ? safeParams.source.trim() : null,
                traceId: typeof safeParams.traceId === 'string' && safeParams.traceId.trim()
                    ? safeParams.traceId.trim()
                    : this._createTraceId(DEFAULT_TRACE_PREFIX),
                requestId: typeof safeParams.requestId === 'string' && safeParams.requestId.trim() ? safeParams.requestId.trim() : null,
                metadata: isPlainObject(safeParams.metadata) ? cloneValue(safeParams.metadata) : null,
                startedAt: Number.isFinite(Number(safeParams.startedAt)) ? Number(safeParams.startedAt) : null,
            };
        }

        _createTraceId(prefix) {
            const safePrefix = typeof prefix === 'string' && prefix.trim() ? prefix.trim() : DEFAULT_TRACE_PREFIX;
            this._traceSequence += 1;
            return `${safePrefix}-${getNow()}-${this._traceSequence}`;
        }
    }

    const actionRegistryInternal = new ActionRegistryImpl(global.IntentBus, global.GlobalStockStore);
    const actionRegistryPublicApi = Object.freeze({
        register: actionRegistryInternal.register.bind(actionRegistryInternal),
        registerMany: actionRegistryInternal.registerMany.bind(actionRegistryInternal),
        replace: actionRegistryInternal.replace.bind(actionRegistryInternal),
        unregister: actionRegistryInternal.unregister.bind(actionRegistryInternal),
        get: actionRegistryInternal.get.bind(actionRegistryInternal),
        list: actionRegistryInternal.list.bind(actionRegistryInternal),
        has: actionRegistryInternal.has.bind(actionRegistryInternal),
        setEnabled: actionRegistryInternal.setEnabled.bind(actionRegistryInternal),
        execute: actionRegistryInternal.execute.bind(actionRegistryInternal),
        canExecute: actionRegistryInternal.canExecute.bind(actionRegistryInternal),
        buildContext: actionRegistryInternal.buildContext.bind(actionRegistryInternal),
        reset: actionRegistryInternal.reset.bind(actionRegistryInternal),
    });

    global.ActionRegistry = actionRegistryPublicApi;
})(window);
