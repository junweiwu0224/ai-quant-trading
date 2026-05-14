(function attachLocalMCP(global) {
    'use strict';

    if (!global.IntentBus) {
        throw new Error('LocalMCP requires window.IntentBus');
    }

    if (!global.GlobalStockStore) {
        throw new Error('LocalMCP requires window.GlobalStockStore');
    }

    if (!global.ActionRegistry) {
        throw new Error('LocalMCP requires window.ActionRegistry');
    }

    const MCP_EVENT_NAMES = Object.freeze({
        INVOKE_STARTED: 'local-mcp:invoke-started',
        INVOKE_BLOCKED: 'local-mcp:invoke-blocked',
        INVOKE_SUCCEEDED: 'local-mcp:invoke-succeeded',
        INVOKE_FAILED: 'local-mcp:invoke-failed',
        TOOL_NOT_FOUND: 'local-mcp:tool-not-found',
        RESET: 'local-mcp:reset',
    });

    const INVOCATION_STATUS = Object.freeze({
        SUCCESS: 'success',
        BLOCKED: 'blocked',
        NOT_FOUND: 'not_found',
        FAILED: 'failed',
    });

    const DEFAULT_TRACE_PREFIX = 'local-mcp';

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

    function createLocalMCPError(message, code) {
        const error = new Error(message);
        error.name = 'LocalMCPError';
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

    class LocalMCPImpl {
        constructor(intentBus, globalStockStore, actionRegistry) {
            this._intentBus = intentBus;
            this._globalStockStore = globalStockStore;
            this._actionRegistry = actionRegistry;
            this._traceSequence = 0;
        }

        listTools(filters) {
            const tools = this._actionRegistry.list(this._normalizeListFilters(filters));
            return tools.map((tool) => this._toToolSnapshot(tool));
        }

        getTool(toolId) {
            const normalizedToolId = this._normalizeToolId(toolId);
            const tool = this._actionRegistry.get(normalizedToolId);
            return tool ? this._toToolSnapshot(tool) : null;
        }

        hasTool(toolId) {
            const normalizedToolId = this._normalizeToolId(toolId);
            return this._actionRegistry.has(normalizedToolId);
        }

        async canInvoke(params) {
            const normalized = this._normalizeInvokeParams(params);
            const tool = this._actionRegistry.get(normalized.toolId);
            if (!tool) {
                return {
                    ok: false,
                    callable: false,
                    toolId: normalized.toolId,
                    reason: 'tool_not_found',
                    code: 'TOOL_NOT_FOUND',
                    error: null,
                };
            }

            const registryResult = await this._actionRegistry.canExecute({
                actionId: normalized.toolId,
                payload: normalized.input,
                source: normalized.source,
                traceId: normalized.traceId,
                requestId: normalized.requestId,
                metadata: normalized.metadata,
            });

            return {
                ok: registryResult.ok,
                callable: registryResult.executable === true,
                toolId: normalized.toolId,
                reason: registryResult.reason ?? null,
                code: registryResult.code ?? null,
                error: registryResult.error ? cloneValue(registryResult.error) : null,
            };
        }

        async invoke(params) {
            const normalized = this._normalizeInvokeParams(params);
            const startedAt = getNow();
            const tool = this._actionRegistry.get(normalized.toolId);

            if (!tool) {
                const finishedAt = getNow();
                this._emitEvent(MCP_EVENT_NAMES.TOOL_NOT_FOUND, {
                    toolId: normalized.toolId,
                    traceId: normalized.traceId,
                    requestId: normalized.requestId,
                    source: normalized.source,
                });
                return {
                    ok: false,
                    toolId: normalized.toolId,
                    traceId: normalized.traceId,
                    requestId: normalized.requestId,
                    source: normalized.source,
                    status: INVOCATION_STATUS.NOT_FOUND,
                    reason: 'tool_not_found',
                    code: 'TOOL_NOT_FOUND',
                    output: undefined,
                    error: null,
                    startedAt,
                    finishedAt,
                    durationMs: finishedAt - startedAt,
                };
            }

            const context = this.buildInvokeContext({
                toolId: normalized.toolId,
                input: normalized.input,
                source: normalized.source,
                traceId: normalized.traceId,
                requestId: normalized.requestId,
                metadata: normalized.metadata,
                startedAt,
            });

            this._emitEvent(MCP_EVENT_NAMES.INVOKE_STARTED, {
                toolId: context.toolId,
                traceId: context.traceId,
                requestId: context.requestId,
                source: context.source,
                revision: context.revision,
                input: cloneValue(context.input),
            });

            const result = await this._actionRegistry.execute({
                actionId: normalized.toolId,
                payload: normalized.input,
                source: normalized.source,
                traceId: normalized.traceId,
                requestId: normalized.requestId,
                metadata: normalized.metadata,
            });

            if (result.status === INVOCATION_STATUS.SUCCESS) {
                this._emitEvent(MCP_EVENT_NAMES.INVOKE_SUCCEEDED, {
                    toolId: normalized.toolId,
                    traceId: result.traceId,
                    requestId: result.requestId,
                    source: result.source,
                    durationMs: result.durationMs,
                    output: cloneValue(result.result),
                });
                return {
                    ok: true,
                    toolId: normalized.toolId,
                    traceId: result.traceId,
                    requestId: result.requestId,
                    source: result.source,
                    status: INVOCATION_STATUS.SUCCESS,
                    reason: null,
                    code: null,
                    output: result.result,
                    error: null,
                    startedAt: result.startedAt,
                    finishedAt: result.finishedAt,
                    durationMs: result.durationMs,
                };
            }

            if (result.status === INVOCATION_STATUS.BLOCKED) {
                this._emitEvent(MCP_EVENT_NAMES.INVOKE_BLOCKED, {
                    toolId: normalized.toolId,
                    traceId: result.traceId,
                    requestId: result.requestId,
                    source: result.source,
                    reason: result.reason,
                    code: result.code,
                });
                return {
                    ok: false,
                    toolId: normalized.toolId,
                    traceId: result.traceId,
                    requestId: result.requestId,
                    source: result.source,
                    status: INVOCATION_STATUS.BLOCKED,
                    reason: result.reason,
                    code: result.code,
                    output: undefined,
                    error: null,
                    startedAt: result.startedAt,
                    finishedAt: result.finishedAt,
                    durationMs: result.durationMs,
                };
            }

            if (result.status === INVOCATION_STATUS.NOT_FOUND) {
                this._emitEvent(MCP_EVENT_NAMES.TOOL_NOT_FOUND, {
                    toolId: normalized.toolId,
                    traceId: result.traceId,
                    requestId: result.requestId,
                    source: result.source,
                });
                return {
                    ok: false,
                    toolId: normalized.toolId,
                    traceId: result.traceId,
                    requestId: result.requestId,
                    source: result.source,
                    status: INVOCATION_STATUS.NOT_FOUND,
                    reason: 'tool_not_found',
                    code: 'TOOL_NOT_FOUND',
                    output: undefined,
                    error: null,
                    startedAt: result.startedAt,
                    finishedAt: result.finishedAt,
                    durationMs: result.durationMs,
                };
            }

            this._emitEvent(MCP_EVENT_NAMES.INVOKE_FAILED, {
                toolId: normalized.toolId,
                traceId: result.traceId,
                requestId: result.requestId,
                source: result.source,
                code: result.code,
                reason: result.reason,
                error: cloneValue(result.error),
                durationMs: result.durationMs,
            });

            return {
                ok: false,
                toolId: normalized.toolId,
                traceId: result.traceId,
                requestId: result.requestId,
                source: result.source,
                status: INVOCATION_STATUS.FAILED,
                reason: result.reason,
                code: result.code,
                output: undefined,
                error: result.error ? cloneValue(result.error) : null,
                startedAt: result.startedAt,
                finishedAt: result.finishedAt,
                durationMs: result.durationMs,
            };
        }

        buildInvokeContext(params) {
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
                toolId: normalized.toolId,
                traceId: normalized.traceId,
                requestId: normalized.requestId,
                source: normalized.source,
                stockState,
                activeStock,
                input: cloneValue(normalized.input),
                metadata: cloneValue(normalized.metadata),
                revision,
                startedAt: normalized.startedAt ?? getNow(),
            });
        }

        createTraceId(prefix) {
            return this._createTraceId(prefix);
        }

        reset() {
            this._traceSequence = 0;
            this._emitEvent(MCP_EVENT_NAMES.RESET, {
                ok: true,
            });
            return {
                ok: true,
            };
        }

        _toToolSnapshot(tool) {
            return deepFreeze({
                id: tool.id,
                title: tool.title,
                description: tool.description,
                category: tool.category,
                keywords: cloneValue(tool.keywords || []),
                enabled: tool.enabled === true,
                visible: tool.visible === true,
                metadata: cloneValue(tool.metadata),
            });
        }

        _emitEvent(eventName, payload) {
            this._intentBus.emit(eventName, cloneValue(payload));
        }

        _normalizeListFilters(filters) {
            const safeFilters = isPlainObject(filters) ? filters : {};
            return {
                category: typeof safeFilters.category === 'string' && safeFilters.category.trim()
                    ? safeFilters.category.trim()
                    : null,
                enabledOnly: safeFilters.enabledOnly === true,
                visibleOnly: safeFilters.visibleOnly === true,
                query: typeof safeFilters.query === 'string' && safeFilters.query.trim()
                    ? safeFilters.query.trim()
                    : null,
            };
        }

        _normalizeInvokeParams(params) {
            if (!isPlainObject(params)) {
                throw createLocalMCPError('invoke params must be a plain object', 'INVALID_INVOKE_PARAMS');
            }

            return {
                toolId: this._normalizeToolId(params.toolId),
                input: params.input == null ? null : cloneValue(params.input),
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
                toolId: safeParams.toolId == null ? null : this._normalizeToolId(safeParams.toolId),
                input: safeParams.input == null ? null : cloneValue(safeParams.input),
                source: typeof safeParams.source === 'string' && safeParams.source.trim() ? safeParams.source.trim() : null,
                traceId: typeof safeParams.traceId === 'string' && safeParams.traceId.trim()
                    ? safeParams.traceId.trim()
                    : this._createTraceId(DEFAULT_TRACE_PREFIX),
                requestId: typeof safeParams.requestId === 'string' && safeParams.requestId.trim() ? safeParams.requestId.trim() : null,
                metadata: isPlainObject(safeParams.metadata) ? cloneValue(safeParams.metadata) : null,
                startedAt: Number.isFinite(Number(safeParams.startedAt)) ? Number(safeParams.startedAt) : null,
            };
        }

        _normalizeToolId(toolId) {
            const normalizedToolId = typeof toolId === 'string' ? toolId.trim() : '';
            if (!normalizedToolId) {
                throw createLocalMCPError('Tool ID is required', 'INVALID_TOOL_ID');
            }
            return normalizedToolId;
        }

        _createTraceId(prefix) {
            const safePrefix = typeof prefix === 'string' && prefix.trim() ? prefix.trim() : DEFAULT_TRACE_PREFIX;
            this._traceSequence += 1;
            return `${safePrefix}-${getNow()}-${this._traceSequence}`;
        }
    }

    const localMCPInternal = new LocalMCPImpl(global.IntentBus, global.GlobalStockStore, global.ActionRegistry);
    const localMCPPublicApi = Object.freeze({
        listTools: localMCPInternal.listTools.bind(localMCPInternal),
        getTool: localMCPInternal.getTool.bind(localMCPInternal),
        hasTool: localMCPInternal.hasTool.bind(localMCPInternal),
        canInvoke: localMCPInternal.canInvoke.bind(localMCPInternal),
        invoke: localMCPInternal.invoke.bind(localMCPInternal),
        buildInvokeContext: localMCPInternal.buildInvokeContext.bind(localMCPInternal),
        createTraceId: localMCPInternal.createTraceId.bind(localMCPInternal),
        reset: localMCPInternal.reset.bind(localMCPInternal),
    });

    global.LocalMCP = localMCPPublicApi;
})(window);
