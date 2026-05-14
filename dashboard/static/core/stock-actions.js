(function attachStockActions(global) {
    'use strict';

    if (!global.ActionRegistry) {
        throw new Error('StockActions requires window.ActionRegistry');
    }

    if (!global.IntentBus) {
        throw new Error('StockActions requires window.IntentBus');
    }

    const ACTION_CATEGORY = 'stock';
    const ACTION_IDS = Object.freeze({
        OPEN_STOCK_DETAIL: 'open_stock_detail',
        ADD_TO_WATCHLIST: 'add_to_watchlist',
        REMOVE_FROM_WATCHLIST: 'remove_from_watchlist',
        OPEN_PAPER_BUY: 'open_paper_buy',
    });

    const ACTION_RISK_LEVEL = Object.freeze({
        LOW: 'low',
        MEDIUM: 'medium',
    });

    const STOCK_INPUT_SCHEMA = Object.freeze({
        required: ['code'],
        code: 'string',
    });

    const INTENT_TYPES = Object.freeze({
        OPEN_STOCK_DETAIL: 'stock:open-detail',
        ADD_TO_WATCHLIST: 'watchlist:add-stock',
        REMOVE_FROM_WATCHLIST: 'watchlist:remove-stock',
        OPEN_PAPER_BUY: 'paper-trade:open-buy',
    });

    const DEFAULT_INTENT_TIMEOUT_MS = 8000;

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
            return Object.fromEntries(
                Object.entries(value).map(([key, item]) => [key, cloneValue(item)])
            );
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

    function createStockActionsError(message, code) {
        const error = new Error(message);
        error.name = 'StockActionsError';
        if (code) {
            error.code = code;
        }
        return error;
    }

    function resolveRegisterMany(actionRegistry) {
        if (typeof actionRegistry.registerMany === 'function') {
            return actionRegistry.registerMany.bind(actionRegistry);
        }

        if (typeof actionRegistry.registerActionMany === 'function') {
            return actionRegistry.registerActionMany.bind(actionRegistry);
        }

        return null;
    }

    function resolveRegister(actionRegistry) {
        if (typeof actionRegistry.register === 'function') {
            return actionRegistry.register.bind(actionRegistry);
        }

        if (typeof actionRegistry.registerAction === 'function') {
            return actionRegistry.registerAction.bind(actionRegistry);
        }

        throw createStockActionsError(
            'ActionRegistry must expose register() or registerAction()',
            'ACTION_REGISTRY_REGISTER_UNAVAILABLE'
        );
    }

    function resolveHas(actionRegistry) {
        if (typeof actionRegistry.has === 'function') {
            return actionRegistry.has.bind(actionRegistry);
        }

        if (typeof actionRegistry.hasAction === 'function') {
            return actionRegistry.hasAction.bind(actionRegistry);
        }

        return null;
    }

    function resolveBusinessAdapter() {
        if (!global.BusinessAdapter || typeof global.BusinessAdapter !== 'object') {
            return null;
        }

        return global.BusinessAdapter;
    }

    function invokeBusinessAdapterMethod(methodName, context) {
        const businessAdapter = resolveBusinessAdapter();
        if (!businessAdapter || typeof businessAdapter[methodName] !== 'function') {
            throw createStockActionsError(
                `BusinessAdapter must expose ${methodName}()`,
                'BUSINESS_ADAPTER_METHOD_UNAVAILABLE'
            );
        }

        return businessAdapter[methodName](context);
    }

    function resolveDispatch(intentBus) {
        if (typeof intentBus.dispatchIntent === 'function') {
            return intentBus.dispatchIntent.bind(intentBus);
        }

        if (typeof intentBus.dispatch === 'function') {
            return intentBus.dispatch.bind(intentBus);
        }

        throw createStockActionsError(
            'IntentBus must expose dispatch() or dispatchIntent()',
            'INTENT_BUS_DISPATCH_UNAVAILABLE'
        );
    }

    function resolveCreateTraceId(intentBus) {
        if (typeof intentBus.createTraceId === 'function') {
            return intentBus.createTraceId.bind(intentBus);
        }

        return function createFallbackTraceId(prefix) {
            const safePrefix = typeof prefix === 'string' && prefix.trim() ? prefix.trim() : 'stock-action';
            return safePrefix + '-' + Date.now();
        };
    }

    function normalizeStockIdentity(value) {
        const safeValue = isPlainObject(value) ? value : {};
        const code = typeof safeValue.code === 'string' ? safeValue.code.trim() : '';

        return {
            code,
            name: typeof safeValue.name === 'string' && safeValue.name.trim() ? safeValue.name.trim() : null,
            market: typeof safeValue.market === 'string' && safeValue.market.trim() ? safeValue.market.trim() : null,
            exchange: typeof safeValue.exchange === 'string' && safeValue.exchange.trim() ? safeValue.exchange.trim() : null,
        };
    }

    function resolveStockFromContext(context) {
        const candidates = [
            context && context.payload,
            context && context.builtPayload && context.builtPayload.stock,
            context && context.activeStock,
            context && context.stockState && context.stockState.identity,
        ];

        for (const candidate of candidates) {
            const normalized = normalizeStockIdentity(candidate);
            if (normalized.code) {
                return normalized;
            }
        }

        return normalizeStockIdentity(null);
    }

    function ensureStockCode(context) {
        const stock = resolveStockFromContext(context);
        if (!stock.code) {
            throw createStockActionsError('Stock code is required', 'STOCK_CODE_REQUIRED');
        }
        return stock;
    }

    function createPreconditionGuard(preconditions) {
        return function guard(context) {
            const stock = resolveStockFromContext(context);
            const failedRule = preconditions.find((rule) => {
                if (rule.type === 'stock_code_required') {
                    return !stock.code;
                }

                return false;
            });

            if (!failedRule) {
                return { ok: true, reason: null, code: null };
            }

            return {
                ok: false,
                reason: failedRule.reason,
                code: failedRule.code,
            };
        };
    }

    function createNoopRollback() {
        return function rollback() {
            return {
                ok: true,
            };
        };
    }

    function createIntentPayload(context, contractDefinition) {
        const stock = ensureStockCode(context);

        return {
            type: contractDefinition.intentType,
            payload: {
                stock: cloneValue(stock),
                actionId: contractDefinition.actionId,
                requestId: context.requestId,
                revision: context.revision,
                riskLevel: contractDefinition.riskLevel,
                preconditions: cloneValue(contractDefinition.preconditions),
                metadata: cloneValue(context.metadata),
                source: context.source,
            },
            source: context.source || 'stock-actions',
            target: ACTION_CATEGORY,
            traceId: context.traceId || createTraceId('stock-action'),
            timeoutMs: DEFAULT_INTENT_TIMEOUT_MS,
            onFail: {
                rollback: createNoopRollback(),
                label: contractDefinition.actionId,
            },
            meta: {
                actionId: contractDefinition.actionId,
                requestId: context.requestId,
                revision: context.revision,
                riskLevel: contractDefinition.riskLevel,
            },
        };
    }

    function createContractDefinition(params) {
        return deepFreeze({
            actionId: params.actionId,
            title: params.title,
            description: params.description,
            category: ACTION_CATEGORY,
            keywords: cloneValue(params.keywords || []),
            riskLevel: params.riskLevel,
            preconditions: cloneValue(params.preconditions || []),
            intentType: params.intentType,
            executor: params.executor,
        });
    }

    function toRegistryDefinition(contractDefinition) {
        return {
            id: contractDefinition.actionId,
            title: contractDefinition.title,
            description: contractDefinition.description,
            category: contractDefinition.category,
            keywords: cloneValue(contractDefinition.keywords),
            enabled: true,
            visible: true,
            metadata: {
                actionId: contractDefinition.actionId,
                riskLevel: contractDefinition.riskLevel,
                preconditions: cloneValue(contractDefinition.preconditions),
                input: cloneValue(STOCK_INPUT_SCHEMA),
                intentType: contractDefinition.intentType,
            },
            guard: createPreconditionGuard(contractDefinition.preconditions),
            buildPayload: function buildPayload(context) {
                return {
                    stock: ensureStockCode(context),
                    riskLevel: contractDefinition.riskLevel,
                    preconditions: cloneValue(contractDefinition.preconditions),
                };
            },
            handler: async function handler(context) {
                return contractDefinition.executor(context);
            },
        };
    }

    const dispatchIntent = resolveDispatch(global.IntentBus);
    const createTraceId = resolveCreateTraceId(global.IntentBus);
    const register = resolveRegister(global.ActionRegistry);
    const registerMany = resolveRegisterMany(global.ActionRegistry);
    const hasAction = resolveHas(global.ActionRegistry);

    const STOCK_ACTION_CONTRACTS = [
        createContractDefinition({
            actionId: ACTION_IDS.OPEN_STOCK_DETAIL,
            title: '打开股票详情',
            description: '切换到行情详情视图并打开当前股票。',
            keywords: ['stock', 'detail', 'open', '行情', '详情'],
            riskLevel: ACTION_RISK_LEVEL.LOW,
            preconditions: [
                {
                    type: 'stock_code_required',
                    reason: 'stock_code_required',
                    code: 'STOCK_CODE_REQUIRED',
                },
            ],
            intentType: INTENT_TYPES.OPEN_STOCK_DETAIL,
            executor: async function executor(context) {
                return invokeBusinessAdapterMethod('openStockDetail', context);
            },
        }),
        createContractDefinition({
            actionId: ACTION_IDS.ADD_TO_WATCHLIST,
            title: '加入自选股',
            description: '将当前股票加入自选股列表。',
            keywords: ['watchlist', 'favorites', '自选', '关注'],
            riskLevel: ACTION_RISK_LEVEL.MEDIUM,
            preconditions: [
                {
                    type: 'stock_code_required',
                    reason: 'stock_code_required',
                    code: 'STOCK_CODE_REQUIRED',
                },
            ],
            intentType: INTENT_TYPES.ADD_TO_WATCHLIST,
            executor: async function executor(context) {
                return invokeBusinessAdapterMethod('addToWatchlist', context);
            },
        }),
        createContractDefinition({
            actionId: ACTION_IDS.REMOVE_FROM_WATCHLIST,
            title: '移除自选股',
            description: '将当前股票从自选股列表移除。',
            keywords: ['watchlist', 'favorites', '自选', '移除'],
            riskLevel: ACTION_RISK_LEVEL.MEDIUM,
            preconditions: [
                {
                    type: 'stock_code_required',
                    reason: 'stock_code_required',
                    code: 'STOCK_CODE_REQUIRED',
                },
            ],
            intentType: INTENT_TYPES.REMOVE_FROM_WATCHLIST,
            executor: async function executor(context) {
                return invokeBusinessAdapterMethod('removeFromWatchlist', context);
            },
        }),
        createContractDefinition({
            actionId: ACTION_IDS.OPEN_PAPER_BUY,
            title: '打开模拟买入',
            description: '切换到模拟交易并打开当前股票的买入流程。',
            keywords: ['paper', 'buy', 'sim', '模拟', '买入', '交易'],
            riskLevel: ACTION_RISK_LEVEL.MEDIUM,
            preconditions: [
                {
                    type: 'stock_code_required',
                    reason: 'stock_code_required',
                    code: 'STOCK_CODE_REQUIRED',
                },
            ],
            intentType: INTENT_TYPES.OPEN_PAPER_BUY,
            executor: async function executor(context) {
                return invokeBusinessAdapterMethod('openPaperBuy', context);
            },
        }),
    ];

    const STOCK_ACTION_DEFINITIONS = STOCK_ACTION_CONTRACTS.map((contractDefinition) => {
        return toRegistryDefinition(contractDefinition);
    });

    function getDefinitionsToRegister() {
        if (typeof hasAction !== 'function') {
            return STOCK_ACTION_DEFINITIONS.map((definition) => cloneValue(definition));
        }

        return STOCK_ACTION_DEFINITIONS
            .filter((definition) => hasAction(definition.id) !== true)
            .map((definition) => cloneValue(definition));
    }

    function registerDefinitions() {
        const definitionsToRegister = getDefinitionsToRegister();
        if (definitionsToRegister.length === 0) {
            return {
                ok: true,
                registered: [],
                skipped: STOCK_ACTION_DEFINITIONS.map((definition) => definition.id),
            };
        }

        if (registerMany) {
            return registerMany(definitionsToRegister);
        }

        return definitionsToRegister.reduce((result, definition) => {
            const item = register(cloneValue(definition));
            return {
                ok: result.ok && item.ok === true,
                registered: [...result.registered, definition.id],
                skipped: cloneValue(result.skipped),
            };
        }, {
            ok: true,
            registered: [],
            skipped: STOCK_ACTION_DEFINITIONS
                .filter((definition) => hasAction && hasAction(definition.id) === true)
                .map((definition) => definition.id),
        });
    }

    const registrationResult = registerDefinitions();

    global.StockActions = Object.freeze({
        actionIds: deepFreeze(cloneValue(ACTION_IDS)),
        contracts: deepFreeze(cloneValue(STOCK_ACTION_CONTRACTS.map((definition) => ({
            actionId: definition.actionId,
            title: definition.title,
            description: definition.description,
            category: definition.category,
            keywords: cloneValue(definition.keywords),
            riskLevel: definition.riskLevel,
            preconditions: cloneValue(definition.preconditions),
            intentType: definition.intentType,
        })))),
        registrationResult: deepFreeze(cloneValue(registrationResult)),
    });
})(window);
