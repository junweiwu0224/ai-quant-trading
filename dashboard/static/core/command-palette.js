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
        TASK: 'task',
    });

    const TASK_INTENT = Object.freeze({
        EMPTY: 'empty',
        STOCK_LOOKUP: 'stock_lookup',
        FUNCTION_NAV: 'function_nav',
        NATURAL_LANGUAGE_SCREENER: 'natural_language_screener',
        MARKET_TOPIC: 'market_topic',
        MARKET_QUESTION: 'market_question',
    });

    const TASK_BUCKET_META = Object.freeze({
        natural_language_screener: {
            id: 'screener',
            label: '问财选股',
            title: '用问财解析选股条件',
            description: '拆解自然语言条件，生成候选池并保留来源上下文',
        },
        market_topic: {
            id: 'sector',
            label: '板块/主题',
            title: '用问财追踪板块主题',
            description: '进入情报页查看主题、成分股、新闻和后续动作',
        },
        market_question: {
            id: 'question',
            label: '市场问句',
            title: '用问财回答市场问题',
            description: '把问句路由到情报工作台，继续收窄、解释或生成篮子',
        },
    });

    const DEFAULT_IWENCAI_CONTEXT_FIELDS = Object.freeze([
        'raw_query',
        'intent_type',
        'selected_bucket',
        'result_pool_id',
        'parsed_conditions',
    ]);
    const DEFAULT_IWENCAI_ACTIONS = Object.freeze(['open_stock', 'send_screener', 'analyze', 'create_basket', 'draft_backtest']);

    function goldenQuestion(item) {
        const route = item.route || 'iwencai';
        const bucket = item.bucket || item.primary_bucket || 'question';
        const isIwencai = route === 'iwencai';
        return Object.freeze({
            ...item,
            route,
            bucket,
            primary_bucket: item.primary_bucket || bucket,
            expected_status: item.expected_status || null,
            allowed_fallback_status: item.allowed_fallback_status || (isIwencai ? ['partial_result', 'degraded_data'] : []),
            required_actions: item.required_actions || (
                isIwencai
                    ? DEFAULT_IWENCAI_ACTIONS
                    : (route === 'stock' ? ['open_stock'] : ['execute_function'])
            ),
            required_source_context: item.required_source_context || (
                isIwencai ? DEFAULT_IWENCAI_CONTEXT_FIELDS : ['raw_query', 'intent_type', 'selected_bucket']
            ),
            required_visible_reason: item.required_visible_reason || item.query,
        });
    }

    const GLOBAL_SEARCH_GOLDEN_QUERIES = Object.freeze([
        goldenQuestion({ id: 'stock-code-600519', query: '600519', intent_type: 'stock_lookup', bucket: 'stocks', route: 'stock', required_visible_reason: '明确股票代码直达行情' }),
        goldenQuestion({ id: 'stock-name-maotai', query: '贵州茅台', intent_type: 'stock_lookup', bucket: 'stocks', route: 'stock', required_visible_reason: '明确股票名称直达行情' }),
        goldenQuestion({ id: 'stock-ambiguous-zhongxin', query: '中信', intent_type: 'stock_lookup', bucket: 'stocks', route: 'stock', expected_status: 'needs_disambiguation', required_visible_reason: '股票简称存在歧义，需要候选列表' }),
        goldenQuestion({ id: 'stock-ambiguous-pingan', query: '平安', intent_type: 'stock_lookup', bucket: 'stocks', route: 'stock', expected_status: 'needs_disambiguation', required_visible_reason: '股票简称存在歧义，需要候选列表' }),
        goldenQuestion({ id: 'function-paper', query: '打开模拟盘', intent_type: 'function_nav', bucket: 'functions', route: 'function', required_visible_reason: '功能导航直达模拟盘' }),
        goldenQuestion({ id: 'function-datahub', query: '切到数据中枢', intent_type: 'function_nav', bucket: 'functions', route: 'function', required_visible_reason: '功能导航直达数据中枢' }),
        goldenQuestion({ id: 'screener-dividend-value-volume', query: '高股息 低估值 近5日放量', intent_type: 'natural_language_screener', bucket: 'screener', route: 'iwencai', required_visible_reason: '股息率、估值、成交量条件拆解' }),
        goldenQuestion({ id: 'screener-roe-volume', query: '近5日放量且ROE大于15%', intent_type: 'natural_language_screener', bucket: 'screener', route: 'iwencai', required_visible_reason: '成交量和ROE条件拆解' }),
        goldenQuestion({ id: 'screener-inflow-turnover', query: '近3日主力净流入 换手率大于5%', intent_type: 'natural_language_screener', bucket: 'screener', route: 'iwencai', required_visible_reason: '资金流和换手率条件拆解' }),
        goldenQuestion({ id: 'screener-breakout-low-pe', query: '突破20日新高且市盈率低于20', intent_type: 'natural_language_screener', bucket: 'screener', route: 'iwencai', required_visible_reason: '趋势突破和估值条件拆解' }),
        goldenQuestion({ id: 'screener-risk-exclusion', query: '剔除ST 低负债率 高ROE', intent_type: 'natural_language_screener', bucket: 'screener', route: 'iwencai', required_visible_reason: '风险排除条件保留' }),
        goldenQuestion({ id: 'screener-smallcap-quality', query: '小市值 高毛利率 低商誉', intent_type: 'natural_language_screener', bucket: 'screener', route: 'iwencai', required_visible_reason: '市值、毛利率、商誉条件拆解' }),
        goldenQuestion({ id: 'topic-semiconductor-why', query: '半导体今天为什么上涨？', intent_type: 'market_topic', bucket: 'sector', route: 'iwencai', required_visible_reason: '主题归因和证据分桶' }),
        goldenQuestion({ id: 'topic-robot', query: '机器人概念有哪些成分股在放量', intent_type: 'market_topic', bucket: 'sector', route: 'iwencai', required_visible_reason: '主题成分股和放量条件联动' }),
        goldenQuestion({ id: 'topic-cpo-flow', query: 'CPO板块主力资金和新闻催化', intent_type: 'market_topic', bucket: 'sector', route: 'iwencai', required_visible_reason: '资金和新闻证据分桶' }),
        goldenQuestion({ id: 'topic-hk-connect', query: '沪深港通资金今天流向哪些行业', intent_type: 'market_topic', bucket: 'sector', route: 'iwencai', required_visible_reason: '跨市场资金视角' }),
        goldenQuestion({ id: 'topic-ai-compute', query: '算力板块今天谁最强', intent_type: 'market_topic', bucket: 'sector', route: 'iwencai', required_visible_reason: '板块强弱和成分股榜单' }),
        goldenQuestion({ id: 'question-risk', query: '今天市场最大的风险是什么？', intent_type: 'market_question', bucket: 'question', route: 'iwencai', required_visible_reason: '市场风险证据分桶' }),
        goldenQuestion({ id: 'question-news-impact', query: '这条新闻会影响哪些股票？', intent_type: 'market_question', bucket: 'question', route: 'iwencai', required_visible_reason: '新闻来源上下文保留' }),
        goldenQuestion({ id: 'question-basket-backtest', query: '把高股息低估值组合生成回测草案', intent_type: 'market_question', bucket: 'question', route: 'iwencai', required_visible_reason: '只生成草案，不自动执行回测', required_actions: ['create_basket', 'draft_backtest', 'analyze'] }),
        goldenQuestion({ id: 'question-market-breadth', query: '今天全市场广度为什么偏强', intent_type: 'market_question', bucket: 'question', route: 'iwencai', required_visible_reason: '市场广度指标解释' }),
        goldenQuestion({ id: 'question-no-match', query: '不存在的奇怪条件abcxyz只看火星概念', intent_type: 'market_question', bucket: 'question', route: 'iwencai', expected_status: 'no_match', allowed_fallback_status: ['needs_disambiguation'], required_actions: ['analyze'], required_visible_reason: '无匹配股票' }),
        goldenQuestion({ id: 'failure-unsupported-field', query: '只看外星营收增长且火星订单爆发', intent_type: 'natural_language_screener', bucket: 'screener', route: 'iwencai', expected_status: 'degraded_data', allowed_fallback_status: ['no_match'], required_actions: ['analyze'], required_visible_reason: '字段不支持或缺少数据源' }),
        goldenQuestion({ id: 'failure-timeout', query: '问财接口超时后保留上下文', intent_type: 'market_question', bucket: 'question', route: 'iwencai', expected_status: 'failed', allowed_fallback_status: ['degraded_data'], required_actions: ['analyze'], required_visible_reason: '请求超时后保留上下文' }),
        goldenQuestion({ id: 'failure-rate-limit', query: '问财限流时如何继续筛选', intent_type: 'market_question', bucket: 'question', route: 'iwencai', expected_status: 'degraded_data', allowed_fallback_status: ['failed'], required_actions: ['analyze'], required_visible_reason: '限流或源不可用' }),
        goldenQuestion({ id: 'failure-stale-cache', query: '缓存过期但先看历史候选池', intent_type: 'market_question', bucket: 'question', route: 'iwencai', expected_status: 'degraded_data', allowed_fallback_status: ['partial_result'], required_actions: ['open_stock', 'analyze'], required_visible_reason: '缓存过期或数据日期偏旧' }),
        goldenQuestion({ id: 'failure-degraded-hit-count', query: '字段命中数不可用时显示原因', intent_type: 'natural_language_screener', bucket: 'screener', route: 'iwencai', expected_status: 'degraded_data', allowed_fallback_status: ['partial_result'], required_actions: ['open_stock', 'analyze'], required_visible_reason: '条件命中数不可用' }),
        goldenQuestion({ id: 'partial-topic-evidence', query: '只有候选股没有新闻证据时如何处理', intent_type: 'market_question', bucket: 'question', route: 'iwencai', expected_status: 'partial_result', allowed_fallback_status: ['degraded_data'], required_visible_reason: '部分证据缺失但候选池保留' }),
        goldenQuestion({ id: 'needs-disambiguation', query: '中信今天能不能买', intent_type: 'market_question', bucket: 'question', route: 'iwencai', expected_status: 'needs_disambiguation', allowed_fallback_status: ['partial_result'], required_actions: ['open_stock', 'analyze'], required_visible_reason: '股票主体存在歧义' }),
        goldenQuestion({ id: 'requires-confirmation', query: '把这批股票全部加入自选', intent_type: 'market_question', bucket: 'question', route: 'iwencai', expected_status: 'requires_confirmation', allowed_fallback_status: [], required_actions: ['analyze'], required_visible_reason: '写入动作需要确认' }),
    ]);

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
            taskResults: [],
            resultBuckets: [],
            mergedResults: [],
            activeIntent: null,
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
            const nextTaskResults = normalized.clearQuery ? [] : this._state.taskResults;
            const nextResultBuckets = normalized.clearQuery ? [] : this._state.resultBuckets;
            const nextMergedResults = normalized.clearQuery ? [] : this._state.mergedResults;
            this._setState({
                isOpen: false,
                query: nextQuery,
                actionResults: nextActionResults,
                stockResults: nextStockResults,
                taskResults: nextTaskResults,
                resultBuckets: nextResultBuckets,
                mergedResults: nextMergedResults,
                activeIntent: normalized.clearQuery ? null : this._state.activeIntent,
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
                        taskCount: 0,
                        mergedCount: 0,
                        error: null,
                    };
                }

                const activeIntent = this._classifyGlobalSearchIntent(snapshotQuery, { actionResults, stockResults });
                const taskResults = this._buildTaskRouterResults(snapshotMode, snapshotQuery, activeIntent);
                const resultBuckets = this._buildResultBuckets(actionResults, stockResults, taskResults, activeIntent);
                const mergedResults = this._buildMergedResults(snapshotMode, actionResults, stockResults, taskResults, activeIntent);
                const selectedIndex = this._resolveSelectedIndex(mergedResults.length);

                this._setState({
                    actionResults,
                    stockResults,
                    taskResults,
                    resultBuckets,
                    mergedResults,
                    activeIntent,
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
                    taskCount: taskResults.length,
                    intentType: activeIntent?.type || null,
                    resultBuckets: cloneValue(resultBuckets),
                    mergedCount: mergedResults.length,
                });
                this._emitSelectionChanged(normalized.source, normalized.traceId);

                return {
                    ok: true,
                    requestId,
                    traceId: normalized.traceId,
                    actionCount: actionResults.length,
                    stockCount: stockResults.length,
                    taskCount: taskResults.length,
                    intentType: activeIntent?.type || null,
                    resultBuckets: cloneValue(resultBuckets),
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
                        taskCount: 0,
                        mergedCount: 0,
                        error: null,
                    };
                }

                const errorShape = getErrorShape(error, 'Failed to refresh command palette results');
                this._setState({
                    actionResults: snapshotMode === PALETTE_MODE.STOCK ? [] : this._state.actionResults,
                    stockResults: snapshotMode === PALETTE_MODE.ACTION ? [] : this._state.stockResults,
                    taskResults: [],
                    resultBuckets: [],
                    mergedResults: [],
                    activeIntent: null,
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
                    taskCount: 0,
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

        getGoldenQuestions() {
            return this._snapshotValue(GLOBAL_SEARCH_GOLDEN_QUERIES);
        }

        async classifyIntent(params) {
            const safeParams = typeof params === 'string' ? { query: params } : (isPlainObject(params) ? params : {});
            const query = typeof safeParams.query === 'string' ? safeParams.query : '';
            const mode = this._normalizeMode(safeParams.mode || PALETTE_MODE.MIXED);
            const traceId = typeof safeParams.traceId === 'string' && safeParams.traceId.trim()
                ? safeParams.traceId.trim()
                : this._createTraceId(DEFAULT_TRACE_PREFIX);
            const requestId = typeof safeParams.requestId === 'string' && safeParams.requestId.trim()
                ? safeParams.requestId.trim()
                : this._createRequestId(DEFAULT_REQUEST_PREFIX);
            const actionResults = this._buildActionResults(mode, query);
            let stockResults = [];
            try {
                stockResults = await this._loadStockResults({
                    mode,
                    query,
                    requestId,
                    source: 'command-palette:classify-intent',
                    traceId,
                });
            } catch (error) {
                stockResults = [];
            }
            return this._snapshotValue(this._classifyGlobalSearchIntent(query, { actionResults, stockResults }));
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

                if (normalized.item.kind === RESULT_KIND.TASK) {
                    const taskResult = await this._executeTaskRouterItem(normalized.item);
                    const result = {
                        ok: taskResult.ok === true,
                        kind: RESULT_KIND.TASK,
                        traceId: normalized.traceId,
                        requestId: normalized.requestId,
                        status: taskResult.ok === true ? EXECUTION_STATUS.SUCCESS : EXECUTION_STATUS.FAILED,
                        result: taskResult.ok === true ? taskResult : null,
                        error: taskResult.ok === true ? null : {
                            message: taskResult.error || 'Failed to route global search task',
                            code: taskResult.code || null,
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

        _classifyGlobalSearchIntent(query, context = {}) {
            const rawQuery = typeof query === 'string' ? query.trim() : '';
            if (!rawQuery) {
                return {
                    type: TASK_INTENT.EMPTY,
                    confidence: 0,
                    reason: '空查询',
                    query: '',
                    normalized_query: '',
                    bucket: null,
                };
            }

            const actionResults = Array.isArray(context.actionResults) ? context.actionResults : [];
            const stockResults = Array.isArray(context.stockResults) ? context.stockResults : [];
            const normalizedQuery = rawQuery.toLowerCase();
            const golden = GLOBAL_SEARCH_GOLDEN_QUERIES.find((item) => item.query === rawQuery);
            if (golden) {
                return {
                    type: golden.intent_type,
                    confidence: 0.96,
                    reason: `命中全局搜索黄金问句: ${golden.id}`,
                    query: rawQuery,
                    normalized_query: normalizedQuery,
                    bucket: golden.bucket,
                    golden_id: golden.id,
                    route: golden.route,
                    expected_status: golden.expected_status || null,
                    allowed_fallback_status: cloneValue(golden.allowed_fallback_status || []),
                    required_actions: cloneValue(golden.required_actions || []),
                    required_source_context: cloneValue(golden.required_source_context || []),
                    required_visible_reason: golden.required_visible_reason || '',
                    primary_bucket: golden.primary_bucket || golden.bucket,
                };
            }
            const hasQuestionSignal = /[?？]|为什么|怎么看|如何|分析|新闻|研报|机会|风险|原因|异动|归因|解读|影响/.test(rawQuery);
            const hasScreenerSignal = /高股息|低估值|放量|缩量|近\d+\s*日|主力|净流入|换手|量比|市盈率|市净率|分红|股息|roe|roa|pe|pb|macd|kdj|突破|新高|低位|低市盈率/i.test(rawQuery);
            const hasTopicSignal = /板块|概念|行业|主题|赛道|半导体|机器人|新能源|银行|算力|光模块|cpo|ai|低空经济|医药|军工|消费|电力|有色|汽车|券商|港股通|沪深港通/i.test(rawQuery);
            const exactCode = /^\d{6}$/.test(rawQuery);
            const exactStockMatch = stockResults.some((item) => {
                const code = typeof item.code === 'string' ? item.code.trim() : '';
                const name = typeof item.name === 'string' ? item.name.trim() : '';
                return code === rawQuery || name === rawQuery;
            });

            if ((exactCode || exactStockMatch) && !hasQuestionSignal && !hasScreenerSignal && !hasTopicSignal) {
                return {
                    type: TASK_INTENT.STOCK_LOOKUP,
                    confidence: exactCode ? 0.98 : 0.9,
                    reason: '匹配到明确股票代码或名称',
                    query: rawQuery,
                    normalized_query: normalizedQuery,
                    bucket: 'stocks',
                };
            }

            if (hasScreenerSignal) {
                return {
                    type: TASK_INTENT.NATURAL_LANGUAGE_SCREENER,
                    confidence: 0.86,
                    reason: '包含可解析的选股条件',
                    query: rawQuery,
                    normalized_query: normalizedQuery,
                    bucket: TASK_BUCKET_META.natural_language_screener.id,
                };
            }

            if (hasTopicSignal) {
                return {
                    type: TASK_INTENT.MARKET_TOPIC,
                    confidence: hasQuestionSignal ? 0.82 : 0.78,
                    reason: '包含板块、主题或跨市场线索',
                    query: rawQuery,
                    normalized_query: normalizedQuery,
                    bucket: TASK_BUCKET_META.market_topic.id,
                };
            }

            if (hasQuestionSignal) {
                return {
                    type: TASK_INTENT.MARKET_QUESTION,
                    confidence: 0.8,
                    reason: '包含市场问句或解释需求',
                    query: rawQuery,
                    normalized_query: normalizedQuery,
                    bucket: TASK_BUCKET_META.market_question.id,
                };
            }

            if (actionResults.length > 0 && stockResults.length === 0) {
                return {
                    type: TASK_INTENT.FUNCTION_NAV,
                    confidence: 0.74,
                    reason: '更像功能导航',
                    query: rawQuery,
                    normalized_query: normalizedQuery,
                    bucket: 'functions',
                };
            }

            if (stockResults.length > 0) {
                return {
                    type: TASK_INTENT.STOCK_LOOKUP,
                    confidence: 0.68,
                    reason: '更像股票检索',
                    query: rawQuery,
                    normalized_query: normalizedQuery,
                    bucket: 'stocks',
                };
            }

            return {
                type: TASK_INTENT.MARKET_QUESTION,
                confidence: 0.56,
                reason: '未命中股票或功能，作为市场问句处理',
                query: rawQuery,
                normalized_query: normalizedQuery,
                bucket: TASK_BUCKET_META.market_question.id,
            };
        }

        _buildTaskRouterResults(mode, query, intent) {
            if (mode !== PALETTE_MODE.MIXED || !intent || !intent.query) {
                return [];
            }
            if (![TASK_INTENT.NATURAL_LANGUAGE_SCREENER, TASK_INTENT.MARKET_TOPIC, TASK_INTENT.MARKET_QUESTION].includes(intent.type)) {
                return [];
            }

            const meta = TASK_BUCKET_META[intent.type] || TASK_BUCKET_META.market_question;
            const sourceContext = this._buildTaskSourceContext(intent, meta);
            return [this._snapshotValue({
                kind: RESULT_KIND.TASK,
                id: `global-search-task:${intent.type}:${this._buildTaskSlug(intent.query)}`,
                title: meta.title,
                description: meta.description,
                query: intent.query,
                intent: cloneValue(intent),
                intent_type: intent.type,
                raw_query: intent.query,
                bucket: meta.id,
                bucketLabel: meta.label,
                enabled: true,
                source_context: cloneValue(sourceContext),
                metadata: {
                    route: 'iwencai',
                    intent_type: intent.type,
                    bucket: meta.id,
                    raw_query: intent.query,
                    source_context: cloneValue(sourceContext),
                },
            })];
        }

        _buildResultBuckets(actionResults, stockResults, taskResults, activeIntent) {
            const buckets = [];
            if (stockResults.length) {
                buckets.push({
                    id: 'stocks',
                    name: '行情',
                    type: 'stock_lookup',
                    count: stockResults.length,
                    active: activeIntent?.bucket === 'stocks',
                });
            }
            if (actionResults.length) {
                buckets.push({
                    id: 'functions',
                    name: '功能',
                    type: 'function_nav',
                    count: actionResults.length,
                    active: activeIntent?.bucket === 'functions',
                });
            }
            taskResults.forEach((item) => {
                const id = item.bucket || item.source_context?.selected_bucket || 'question';
                if (buckets.some((bucket) => bucket.id === id)) {
                    return;
                }
                buckets.push({
                    id,
                    name: item.bucketLabel || item.source_context?.bucket_label || item.title || '问句',
                    type: item.intent_type || item.intent?.type || item.source_context?.intent_type || 'market_question',
                    count: 1,
                    active: true,
                });
            });
            return buckets.map((bucket) => this._snapshotValue(bucket));
        }

        _buildTaskSourceContext(intent, meta) {
            const slug = this._buildTaskSlug(intent.query);
            return {
                source: 'global_search',
                sourceLabel: '全局搜索',
                context_type: 'global_search_task',
                query: intent.query,
                raw_query: intent.query,
                intent_type: intent.type,
                intent_confidence: intent.confidence,
                selected_bucket: meta.id,
                bucket_label: meta.label,
                result_pool_id: `global-search:${slug}`,
                parsed_conditions: [],
                condition_hit_count: {},
                expected_status: intent.expected_status || null,
                allowed_fallback_status: cloneValue(intent.allowed_fallback_status || []),
                required_actions: cloneValue(intent.required_actions || []),
                required_source_context: cloneValue(intent.required_source_context || []),
                rank_reason: `全局搜索: ${intent.query}`,
            };
        }

        _buildTaskSlug(query) {
            const normalized = typeof query === 'string' ? query.trim().toLowerCase() : '';
            const safe = normalized
                .replace(/\s+/g, '-')
                .replace(/[^\w\u4e00-\u9fa5-]+/g, '')
                .slice(0, 48);
            return safe || 'query';
        }

        _buildMergedResults(mode, actionResults, stockResults, taskResults = [], activeIntent = null) {
            if (mode === PALETTE_MODE.ACTION) {
                return actionResults;
            }
            if (mode === PALETTE_MODE.STOCK) {
                return stockResults;
            }
            const taskFirst = activeIntent && [
                TASK_INTENT.NATURAL_LANGUAGE_SCREENER,
                TASK_INTENT.MARKET_TOPIC,
                TASK_INTENT.MARKET_QUESTION,
            ].includes(activeIntent.type);
            return taskFirst
                ? [...taskResults, ...stockResults, ...actionResults]
                : [...actionResults, ...stockResults, ...taskResults];
        }

        async _executeTaskRouterItem(item) {
            const query = typeof item.query === 'string' ? item.query.trim() : '';
            if (!query) {
                return {
                    ok: false,
                    error: 'Task router item requires query',
                    code: 'TASK_QUERY_EMPTY',
                };
            }

            const sourceContext = isPlainObject(item.source_context)
                ? cloneValue(item.source_context)
                : (isPlainObject(item.metadata?.source_context) ? cloneValue(item.metadata.source_context) : {});
            const selectedBucket = item.bucket || sourceContext.selected_bucket || null;
            const app = global.App || {};

            if (typeof app.ensureBundle === 'function') {
                await app.ensureBundle('intelligence');
            }
            if (typeof app.switchTab === 'function') {
                await app.switchTab('intelligence');
            }
            await this._waitForIntelligencePageLoad();
            const intelligence = await this._waitForIwencaiRunner();
            if (typeof intelligence.bindIwencai === 'function') {
                intelligence.bindIwencai();
            }

            const input = global.document && typeof global.document.getElementById === 'function'
                ? global.document.getElementById('intel-iwencai-input')
                : null;
            if (input) {
                input.value = query;
            }

            if (typeof intelligence.runIwencai !== 'function') {
                return {
                    ok: false,
                    error: 'Intelligence.runIwencai is not available',
                    code: 'IWENCAI_UNAVAILABLE',
                };
            }

            const output = await intelligence.runIwencai({
                source: 'global_search',
                query,
                raw_query: sourceContext.raw_query || query,
                intent_type: sourceContext.intent_type || item.intent?.type || item.intent_type || TASK_INTENT.MARKET_QUESTION,
                selected_bucket: selectedBucket,
                source_context: {
                    ...sourceContext,
                    query,
                    raw_query: sourceContext.raw_query || query,
                    selected_bucket: selectedBucket,
                    intent_type: sourceContext.intent_type || item.intent?.type || item.intent_type || TASK_INTENT.MARKET_QUESTION,
                },
            });

            return {
                ok: true,
                route: 'iwencai',
                query,
                selected_bucket: selectedBucket,
                source_context: {
                    ...sourceContext,
                    query,
                    raw_query: sourceContext.raw_query || query,
                    selected_bucket: selectedBucket,
                    intent_type: sourceContext.intent_type || item.intent?.type || item.intent_type || TASK_INTENT.MARKET_QUESTION,
                },
                output: output === undefined ? null : cloneValue(output),
            };
        }

        async _waitForIwencaiRunner(timeoutMs = 5000) {
            const startedAt = getNow();
            while (getNow() - startedAt <= timeoutMs) {
                const intelligence = global.Intelligence || {};
                if (typeof intelligence.runIwencai === 'function') {
                    return intelligence;
                }
                await new Promise((resolve) => {
                    if (typeof global.setTimeout === 'function') {
                        global.setTimeout(resolve, 50);
                        return;
                    }
                    resolve();
                });
            }
            return global.Intelligence || {};
        }

        async _waitForIntelligencePageLoad(timeoutMs = 5000) {
            const startedAt = getNow();
            while (getNow() - startedAt <= timeoutMs) {
                const intelligence = global.Intelligence || {};
                const loadingPromise = intelligence.state?.loadingPromise;
                if (loadingPromise && typeof loadingPromise.then === 'function') {
                    try {
                        await loadingPromise;
                    } catch (error) {
                        return;
                    }
                    return;
                }
                if (global.document?.getElementById?.('intel-iwencai-result')) {
                    return;
                }
                await new Promise((resolve) => {
                    if (typeof global.setTimeout === 'function') {
                        global.setTimeout(resolve, 50);
                        return;
                    }
                    resolve();
                });
            }
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

            if (item.kind === RESULT_KIND.TASK) {
                const query = typeof item.query === 'string' ? item.query.trim() : '';
                if (!query) {
                    throw createCommandPaletteError('Task item requires query', 'INVALID_TASK_ITEM');
                }
                const sourceContext = isPlainObject(item.source_context)
                    ? cloneValue(item.source_context)
                    : (isPlainObject(item.metadata?.source_context) ? cloneValue(item.metadata.source_context) : null);
                return {
                    kind: RESULT_KIND.TASK,
                    id: typeof item.id === 'string' && item.id.trim()
                        ? item.id.trim()
                        : `global-search-task:${this._buildTaskSlug(query)}`,
                    title: typeof item.title === 'string' && item.title.trim() ? item.title.trim() : '用问财处理这个问题',
                    description: typeof item.description === 'string' && item.description.trim() ? item.description.trim() : null,
                    query,
                    raw_query: typeof item.raw_query === 'string' && item.raw_query.trim() ? item.raw_query.trim() : query,
                    intent: isPlainObject(item.intent) ? cloneValue(item.intent) : null,
                    intent_type: typeof item.intent_type === 'string' && item.intent_type.trim()
                        ? item.intent_type.trim()
                        : (isPlainObject(item.intent) && typeof item.intent.type === 'string' ? item.intent.type : sourceContext?.intent_type || null),
                    bucket: typeof item.bucket === 'string' && item.bucket.trim() ? item.bucket.trim() : null,
                    bucketLabel: typeof item.bucketLabel === 'string' && item.bucketLabel.trim() ? item.bucketLabel.trim() : null,
                    enabled: item.enabled !== false,
                    source_context: sourceContext,
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
        getGoldenQuestions: commandPaletteInternal.getGoldenQuestions.bind(commandPaletteInternal),
        classifyIntent: commandPaletteInternal.classifyIntent.bind(commandPaletteInternal),
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
