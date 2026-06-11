/* ── 股票详情页：核心生命周期 ── */

if (!globalThis.StockDetail) {
    globalThis.StockDetail = {};
}

Object.assign(globalThis.StockDetail, {
    init() {
        if (this._inited) return;
        this._inited = true;
        // 搜索框 — 只搜索自选股
        this._searchBox = new SearchBox('stock-detail-code', 'stock-detail-dropdown', {
            maxResults: 200,
            formatItem: (s) => `${s.code} ${s.name || ''}`,
        });
        this._searchBox.setDataSource(async (q) => {
            const list = App.watchlistCache || [];
            if (!q) return list;
            const kw = q.toLowerCase();
            return list.filter(s =>
                (s.code && s.code.includes(kw)) ||
                (s.name && s.name.toLowerCase().includes(kw))
            );
        });
        this._searchBox.onSelect((item) => {
            if (!item || !item.code) {
                return;
            }
            void App.openStockDetail(item.code, {
                source: 'stock-detail:search-box',
            });
        });
        this._bindChartTabs();
        this._bindIndicatorSelector();
        this._bindDrawingToolbar();
        this._bindDrawingShortcuts();

        // 默认分时模式，隐藏指标选择器
        const indicatorEl = document.querySelector('.sd-indicator-selector');
        if (indicatorEl) indicatorEl.style.display = 'none';

        // 主题切换时重绘 KLineChart（canvas 不响应 CSS 变量）
        this._themeObserver = new MutationObserver(() => {
            if (!this._klineChart) return;
            if (this._currentPeriod === 'timeline' && this._currentTimelineTrends) {
                this._renderTimelineChart(this._currentTimelineTrends, this._currentTimelinePreClose);
            } else if (this._currentKlines) {
                this._renderKlineChart(this._currentKlines);
            }
        });
        this._themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    },

    /** 打开某只股票的详情 */
    async open(code, options = {}) {
        const gen = (Number.isFinite(this._openGeneration) ? this._openGeneration : 0) + 1;
        this._openGeneration = gen;
        const previousCode = this._currentCode;
        const previousSourceContext = previousCode === code && this._sourceContext && typeof this._sourceContext === 'object'
            ? this._sourceContext
            : {};
        this._currentCode = code;
        this._detailData = null;
        const safeOptions = options && typeof options === 'object' ? options : {};
        const optionStock = safeOptions.stock && typeof safeOptions.stock === 'object' ? safeOptions.stock : null;
        const optionName = typeof safeOptions.name === 'string' && safeOptions.name.trim() ? safeOptions.name.trim() : '';
        const explicitSource = typeof safeOptions.source === 'string' && safeOptions.source.trim() ? safeOptions.source.trim() : '';
        const inheritedSourceContext = (!explicitSource || explicitSource === previousSourceContext.source)
            ? previousSourceContext
            : {};
        const explicitSourceContext = safeOptions.source_context && typeof safeOptions.source_context === 'object'
            ? safeOptions.source_context
            : {};
        const source = explicitSource || inheritedSourceContext.source || 'stock-detail:open';
        const contextText = (key) => (
            typeof safeOptions[key] === 'string'
                ? safeOptions[key]
                : (explicitSourceContext[key] || inheritedSourceContext[key] || '')
        );
        const contextValue = (key, fallback = null) => (
            safeOptions[key] !== undefined
                ? safeOptions[key]
                : explicitSourceContext[key] !== undefined
                    ? explicitSourceContext[key]
                    : inheritedSourceContext[key] !== undefined
                        ? inheritedSourceContext[key]
                        : fallback
        );
        const awaitDeferredLoad = safeOptions.awaitDeferredLoad === true;
        this._workbenchEventSources = {};
        this._baseWorkbenchEvents = [];
        this._sourceContext = {
            ...explicitSourceContext,
            source,
            sourceLabel: contextText('sourceLabel'),
            context_type: contextText('context_type'),
            sector_name: contextText('sector_name'),
            rank_reason: contextText('rank_reason'),
            query: contextText('query'),
            raw_query: contextText('raw_query'),
            intent_type: contextText('intent_type'),
            selected_bucket: contextText('selected_bucket'),
            result_pool_id: contextText('result_pool_id'),
            result_total: contextValue('result_total', null),
            parsed_conditions: contextValue('parsed_conditions', []),
            condition_hit_count: contextValue('condition_hit_count', {}),
        };
        this._syncWorkbenchOpenState(code, { safeOptions, optionStock, optionName });

        if (globalThis.App && typeof globalThis.App.syncActiveStockContext === 'function') {
            const stockStoreIdentity = globalThis.GlobalStockStore?.getState?.()?.identity || {};
            const matchedStock = (App.watchlistCache || []).find((item) => item.code === code) || null;
            const contextStock = matchedStock || optionStock || (optionName ? { code, name: optionName } : null) || (
                stockStoreIdentity.code === code && stockStoreIdentity.name
                    ? { code, name: stockStoreIdentity.name }
                    : null
            );
            globalThis.App.syncActiveStockContext(code, contextStock, source, 'stock-detail');
        }
        this._renderDetailPending(code, { stock: optionStock, name: optionName });
        // 连接 L2 十档行情
        this._connectL2(code);
        const content = document.getElementById('sd-content');
        const placeholder = document.getElementById('sd-placeholder');
        if (content) content.style.display = '';
        if (placeholder) placeholder.style.display = 'none';
        this._scrollWorkbenchIntoView();

        // 更新搜索框显示：代码 + 名称
        const wl = (App.watchlistCache || []).find(s => s.code === code);
        const stockStoreIdentity = globalThis.GlobalStockStore?.getState?.()?.identity || {};
        const storeName = stockStoreIdentity.code === code ? stockStoreIdentity.name : '';
        const label = wl ? `${wl.code} ${wl.name || ''}` : (storeName ? `${code} ${storeName}` : code);
        if (this._searchBox) this._searchBox.setValue(label);

        // 显示全局 loading
        this._setLoading(true);

        // 分级加载：关键模块先加载，非关键模块延迟加载
        const stale = () => gen !== this._openGeneration;

        // 第一屏（关键）：立即加载
        const preferredPeriod = this._preferredOpenPeriod();
        const chartLoad = preferredPeriod === 'timeline' || typeof this._loadKline !== 'function'
            ? this._loadTimeline(code, stale)
            : this._loadKline(code, preferredPeriod);
        const critical = [
            this._loadDetail(code, stale),
            chartLoad,
            this._loadOrderBook(code, stale),
            this._loadPeriodReturns(code, stale),
        ];
        await Promise.allSettled(critical);

        if (stale()) return;
        this._setLoading(false);

        const newsContainer = document.getElementById('sd-news');
        if (newsContainer) {
            newsContainer.innerHTML = '<p class="text-muted">新闻加载中...</p>';
        }

        // 第二屏（非关键）：后台加载，不阻塞 loading 状态
        const deferred = [
            this._loadCapitalFlow(code, stale),
            this._loadProfitTrend(code, stale),
            this._loadShareholders(code, stale),
            this._loadDividends(code, stale),
            this._loadAnnouncements(code, stale),
            this._loadIndustryComparison(code, stale),
            this._loadNorthbound(code, stale),
            this._loadChips(code, stale),
            this._loadMultiTimeframe(code, stale),
            this._loadDragonTiger(code, stale),
            this._loadReports(code, stale),
            this._loadValuationSnapshot(code, stale),
            this._loadAlphaSignals(code, stale),
            this._loadNews(code, stale),
        ];
        const deferredPromise = Promise.allSettled(deferred);
        if (awaitDeferredLoad) {
            await deferredPromise;
        }

        if (stale()) return;
        this._setLoading(false);
    },

    _scrollWorkbenchIntoView() {
        const content = document.getElementById('sd-content');
        if (!content || typeof content.scrollIntoView !== 'function') return;
        try {
            content.scrollIntoView({ block: 'start', inline: 'nearest' });
        } catch {
            content.scrollIntoView();
        }
    },

    _defaultStockWorkbenchState() {
        return {
            selectedSymbol: { code: '', name: '', exchange: '', asset_type: 'stock', market: 'A股' },
            quoteSnapshot: {},
            sourceContext: {},
            contextList: [],
            chartState: { period: 'timeline', adjust: 'qfq', visibleRange: null, selectedCandle: null, eventFocus: null, eventOverlay: true, eventOverlayEvents: [], eventOverlayCount: 0 },
            indicatorState: { main: ['MA'], sub: ['VOL'], active: '' },
            layoutState: { leftOpen: true, rightOpen: true, bottomTab: 'events', railTab: 'profile' },
            relatedContext: { sectors: [], indices: [], peers: [] },
            eventFeed: [],
            selectedEvent: null,
            fundamentalSnapshot: {},
            dataQuality: {},
            aiContext: {},
        };
    },

    _stockWorkbenchStateStorageKey() {
        const workspaceId = globalThis.App?._accountState?.workspace?.id || 'default';
        return `stock_workbench_state:${workspaceId}`;
    },

    _readStoredStockWorkbenchState() {
        try {
            if (!globalThis.sessionStorage || typeof globalThis.sessionStorage.getItem !== 'function') return {};
            const raw = globalThis.sessionStorage.getItem(this._stockWorkbenchStateStorageKey());
            if (!raw) return {};
            const parsed = JSON.parse(raw);
            return parsed && typeof parsed === 'object' ? parsed : {};
        } catch {
            return {};
        }
    },

    _persistStockWorkbenchState(state) {
        try {
            if (!state || !globalThis.sessionStorage || typeof globalThis.sessionStorage.setItem !== 'function') return;
            const snapshot = {
                chartState: state.chartState || {},
                indicatorState: state.indicatorState || {},
                layoutState: state.layoutState || {},
            };
            globalThis.sessionStorage.setItem(this._stockWorkbenchStateStorageKey(), JSON.stringify(snapshot));
        } catch {
            // Storage is best-effort; never block stock detail rendering.
        }
    },

    _preferredOpenPeriod() {
        const state = this._ensureStockWorkbenchState();
        const period = state.chartState?.period || this._currentPeriod || 'timeline';
        const supported = new Set(['timeline', 'daily', 'weekly', 'monthly', '60m', '30m', '15m', '5m', '1m']);
        return supported.has(period) ? period : 'timeline';
    },

    _ensureStockWorkbenchState() {
        const owner = globalThis.App || this;
        if (!owner.StockWorkbenchState || typeof owner.StockWorkbenchState !== 'object') {
            owner.StockWorkbenchState = this._defaultStockWorkbenchState();
        }
        const state = owner.StockWorkbenchState;
        const defaults = this._defaultStockWorkbenchState();
        for (const [key, value] of Object.entries(defaults)) {
            if (value === null) {
                if (!(key in state)) state[key] = null;
                continue;
            }
            if (!state[key] || typeof state[key] !== 'object') {
                state[key] = Array.isArray(value) ? [...value] : { ...value };
            }
        }
        if (!state._sessionHydrated) {
            const stored = this._readStoredStockWorkbenchState();
            if (stored.chartState && typeof stored.chartState === 'object') {
                state.chartState = { ...state.chartState, ...stored.chartState };
            }
            if (stored.indicatorState && typeof stored.indicatorState === 'object') {
                state.indicatorState = { ...state.indicatorState, ...stored.indicatorState };
            }
            if (stored.layoutState && typeof stored.layoutState === 'object') {
                state.layoutState = { ...state.layoutState, ...stored.layoutState };
            }
            Object.defineProperty(state, '_sessionHydrated', {
                value: true,
                writable: true,
                configurable: true,
            });
        }
        if (
            this._sourceContext
            && typeof this._sourceContext === 'object'
            && Object.keys(this._sourceContext).length
            && (!state.sourceContext || !Object.keys(state.sourceContext).length)
        ) {
            state.sourceContext = { ...this._sourceContext };
        }
        this.StockWorkbenchState = state;
        return state;
    },

    _syncWorkbenchOpenState(code, { safeOptions = {}, optionStock = null, optionName = '' } = {}) {
        const state = this._ensureStockWorkbenchState();
        const stockStoreIdentity = globalThis.GlobalStockStore?.getState?.()?.identity || {};
        const name = optionStock?.name
            || optionName
            || (stockStoreIdentity.code === code ? stockStoreIdentity.name : '')
            || state.selectedSymbol?.name
            || '';
        state.selectedSymbol = {
            ...state.selectedSymbol,
            code,
            name,
            asset_type: 'stock',
            market: 'A股',
        };
        state.sourceContext = { ...(this._sourceContext || {}) };
        state.selectedEvent = null;
        state.chartState = {
            ...(state.chartState || {}),
            eventFocus: null,
            eventOverlayEvents: [],
            eventOverlayCount: 0,
        };
        this._renderSelectedEventMarker(null);
        state.contextList = Array.isArray(globalThis.App?._stockContextItems) && globalThis.App._stockContextItems.length
            ? globalThis.App._stockContextItems.map((item) => ({ ...item }))
            : (Array.isArray(safeOptions.contextList)
                ? safeOptions.contextList.map((item) => ({ ...item }))
                : state.contextList || []);
        const period = state.chartState?.period || this._currentPeriod || 'timeline';
        state.chartState = {
            ...state.chartState,
            period,
            adjust: state.chartState?.adjust || 'qfq',
        };
        this._currentPeriod = period;
        this._syncWorkbenchIndicatorState(this._currentIndicator || state.indicatorState?.active || '');
        this._persistStockWorkbenchState(state);
        return state;
    },

    _syncWorkbenchChartState(patch = {}) {
        const state = this._ensureStockWorkbenchState();
        state.chartState = {
            ...state.chartState,
            ...patch,
        };
        if (this._currentCode) {
            state.selectedSymbol = {
                ...state.selectedSymbol,
                code: this._currentCode,
                asset_type: 'stock',
                market: 'A股',
            };
        }
        this._persistStockWorkbenchState(state);
        return state;
    },

    _syncWorkbenchIndicatorState(active = '') {
        const indicator = typeof active === 'string' ? active : '';
        this._currentIndicator = indicator;
        const main = ['MA'];
        const sub = ['VOL'];
        if (indicator === 'BOLL') {
            main.push('BOLL');
        } else if (['MACD', 'KDJ', 'RSI', 'WR', 'OBV'].includes(indicator)) {
            sub.push(indicator);
        }
        const state = this._ensureStockWorkbenchState();
        state.indicatorState = { ...state.indicatorState, main, sub, active: indicator };
        this._persistStockWorkbenchState(state);
        return state;
    },

    _syncWorkbenchLayoutState(patch = {}) {
        const state = this._ensureStockWorkbenchState();
        state.layoutState = {
            ...state.layoutState,
            ...patch,
        };
        this._persistStockWorkbenchState(state);
        return state;
    },

    _eventTypeLabel(type = '') {
        return {
            source_context: '来源',
            quote_snapshot: '行情',
            detail_snapshot: '资料',
            news_research: '事件',
            news: '新闻',
            report: '研报',
            research_report: '研报',
            announcement: '公告',
            alpha_signal: '信号',
            dividend: '分红',
            northbound: '北向',
            capital_flow: '资金',
            dragon_tiger: '龙虎',
            chart: '图表',
        }[type] || '事件';
    },

    _chartEventTypes() {
        return new Set([
            'news',
            'report',
            'research_report',
            'announcement',
            'alpha_signal',
            'dividend',
            'northbound',
            'capital_flow',
            'dragon_tiger',
        ]);
    },

    _eventBottomTab(type = '') {
        if (type === 'news') return 'news';
        if (['report', 'research_report', 'alpha_signal'].includes(type)) return 'reports';
        if (['announcement', 'dividend'].includes(type)) return 'announcements';
        if (['northbound', 'capital_flow', 'dragon_tiger', 'quote_snapshot', 'detail_snapshot', 'source_context'].includes(type)) return 'chart';
        return 'events';
    },

    _chartEventColor(type = '') {
        return {
            news: '#4fc3f7',
            report: '#66bb6a',
            research_report: '#66bb6a',
            announcement: '#e6a817',
            dividend: '#ab47bc',
            alpha_signal: '#ef5350',
            northbound: '#00bcd4',
            capital_flow: '#ff7043',
            dragon_tiger: '#f06292',
        }[type] || '#8b8680';
    },

    _eventDateKey(event = {}, at = '') {
        const raw = event.date_key || event.dateKey || event.date || event.time || event.chartTime || event.chart_time || at || '';
        const match = String(raw || '').match(/\d{4}-\d{2}-\d{2}/);
        return match ? match[0] : '';
    },

    _eventId(event = {}, fallback = '') {
        const raw = [
            event.id,
            event.type,
            event.date_key || event.dateKey,
            event.at || event.date || event.time || event.chartTime,
            event.title,
            fallback,
        ].filter(Boolean).join(':');
        return raw
            .toLowerCase()
            .replace(/[^a-z0-9\u4e00-\u9fa5]+/g, '-')
            .replace(/^-+|-+$/g, '')
            .slice(0, 96) || `event-${Date.now()}`;
    },

    _normalizeStockEvent(event = {}, defaults = {}) {
        const safeEvent = event && typeof event === 'object' ? event : {};
        const type = safeEvent.type || defaults.type || 'news_research';
        const at = safeEvent.at || safeEvent.date || safeEvent.time || defaults.at || '';
        const dateKey = this._eventDateKey(safeEvent, at) || this._eventDateKey(defaults, at);
        const title = safeEvent.title || defaults.title || this._eventTypeLabel(type);
        const status = safeEvent.status || defaults.status || 'ready';
        const normalized = {
            id: this._eventId({ ...defaults, ...safeEvent, type, at, title, date_key: dateKey }, defaults.source_key || defaults.source || ''),
            type,
            title,
            detail: safeEvent.detail || safeEvent.summary || defaults.detail || '',
            at,
            date_key: dateKey,
            source: safeEvent.source || defaults.source || this._eventTypeLabel(type),
            source_label: safeEvent.source_label || safeEvent.sourceLabel || defaults.source_label || defaults.sourceLabel || '',
            status,
            chartTime: safeEvent.chartTime || safeEvent.chart_time || dateKey || at || '',
            related_code: safeEvent.related_code || safeEvent.code || this._currentCode || '',
            direction: safeEvent.direction || defaults.direction || '',
            value: safeEvent.value ?? defaults.value ?? null,
            link_url: safeEvent.link_url || safeEvent.url || defaults.link_url || '',
            missing_reason: safeEvent.missing_reason || defaults.missing_reason || '',
            source_key: safeEvent.source_key || defaults.source_key || '',
            raw: safeEvent.raw || safeEvent,
        };
        if (status !== 'ready' && !normalized.detail && normalized.missing_reason) {
            normalized.detail = normalized.missing_reason;
        }
        return normalized;
    },

    _mergeWorkbenchEventFeed(baseEvents = []) {
        const dynamicEvents = Object.values(this._workbenchEventSources || {}).flat();
        const chartEventTypes = this._chartEventTypes();
        const hasConcreteNews = dynamicEvents.some((event) => (
            event.status === 'ready'
            && chartEventTypes.has(event.type)
        ));
        const filteredBase = (Array.isArray(baseEvents) ? baseEvents : [])
            .filter((event) => !(hasConcreteNews && event.type === 'news_research' && event.status === 'missing'));
        const seen = new Set();
        return [...filteredBase, ...dynamicEvents]
            .filter((event) => {
                if (!event?.id || seen.has(event.id)) return false;
                seen.add(event.id);
                return true;
            })
            .sort((a, b) => {
                const aDate = a.date_key || a.chartTime || a.at || '';
                const bDate = b.date_key || b.chartTime || b.at || '';
                if (aDate && bDate && aDate !== bDate) return bDate.localeCompare(aDate);
                if (a.status !== b.status) return a.status === 'ready' ? -1 : 1;
                return 0;
            });
    },

    _setWorkbenchEvents(sourceKey, events = [], defaults = {}) {
        const key = String(sourceKey || defaults.source_key || 'events');
        const normalized = (Array.isArray(events) ? events : [])
            .map((event, index) => this._normalizeStockEvent(event, { ...defaults, source_key: key, id: `${key}-${index}` }));
        if (!normalized.length) {
            normalized.push(this._normalizeStockEvent({
                type: defaults.type || 'news_research',
                title: defaults.title || this._eventTypeLabel(defaults.type),
                status: defaults.status || 'missing',
                missing_reason: defaults.missing_reason || '事件数据暂缺',
                detail: defaults.missing_reason || '事件数据暂缺',
            }, { ...defaults, source_key: key }));
        }
        this._workbenchEventSources = {
            ...(this._workbenchEventSources || {}),
            [key]: normalized,
        };
        const state = this._ensureStockWorkbenchState();
        state.eventFeed = this._mergeWorkbenchEventFeed(this._baseWorkbenchEvents || state.eventFeed || []);
        this._syncWorkbenchEventOverlayState(state.eventFeed);
        const hasConcreteNews = state.eventFeed.some((event) => (
            event.status === 'ready'
            && this._chartEventTypes().has(event.type)
        ));
        state.dataQuality = {
            ...(state.dataQuality || {}),
            news_research: hasConcreteNews
                ? {
                    status: 'ready',
                    source: '事件聚合',
                    updated_at: normalized.find((event) => event.status === 'ready')?.at || '',
                    missing_reason: '',
                }
                : (state.dataQuality?.news_research || {}),
        };
        this._syncWorkbenchAiContextFromState();
        this._renderStockEvidenceRail(this._headerData || {}, this._buildStockIdentitySummary(this._headerData || {}));
        this._renderStockBottomPanel();
        this._renderStockChartEventLayer();
        return state.eventFeed;
    },

    _filteredWorkbenchEvents(bottomTab, events = []) {
        const list = Array.isArray(events) ? events : [];
        const typeGroups = {
            events: null,
            news: new Set(['news']),
            reports: new Set(['report', 'research_report', 'alpha_signal']),
            announcements: new Set(['announcement', 'dividend']),
            chart: new Set(['alpha_signal', 'northbound', 'capital_flow', 'dragon_tiger', 'quote_snapshot', 'detail_snapshot', 'source_context']),
        };
        const group = typeGroups[bottomTab] || null;
        return group ? list.filter((event) => group.has(event.type)) : list;
    },

    _setStockBottomTab(bottomTab = 'events') {
        this._syncWorkbenchLayoutState({ bottomTab });
        this._renderStockBottomPanel();
    },

    _syncWorkbenchSelectedEvent(event = null) {
        const state = this._ensureStockWorkbenchState();
        state.selectedEvent = event ? { ...event } : null;
        if (!event) {
            state.chartState = {
                ...state.chartState,
                eventFocus: null,
            };
        }
        if (event) {
            const eventFocus = {
                event_id: event.id,
                type: event.type,
                title: event.title,
                timestamp: event.chartTime || event.at || '',
                date_key: event.date_key || this._eventDateKey(event, event.chartTime || event.at),
                period: state.chartState?.period || this._currentPeriod || 'timeline',
            };
            state.chartState = {
                ...state.chartState,
                eventFocus,
                selectedCandle: {
                    event_id: event.id,
                    type: event.type,
                    title: event.title,
                    timestamp: event.chartTime || event.at || '',
                    period: state.chartState?.period || this._currentPeriod || 'timeline',
                },
            };
        }
        return state;
    },

    _stockEventOverlayEvents(events = [], chartData = []) {
        const chartEventTypes = this._chartEventTypes();
        const safeChartData = Array.isArray(chartData) ? chartData : [];
        const dateIndex = new Map();
        safeChartData.forEach((item, index) => {
            const key = this._eventDateKey(item, item?.date_key || item?.time || item?.timestamp || '');
            if (key && !dateIndex.has(key)) dateIndex.set(key, index);
        });
        return (Array.isArray(events) ? events : [])
            .filter((event) => (
                event
                && event.status === 'ready'
                && chartEventTypes.has(event.type)
                && (event.date_key || event.chartTime || event.at)
            ))
            .map((event) => {
                const dateKey = this._eventDateKey(event, event.chartTime || event.at);
                const dataIndex = dateKey && dateIndex.has(dateKey) ? dateIndex.get(dateKey) : null;
                const point = dataIndex !== null ? safeChartData[dataIndex] : null;
                const xPct = point && safeChartData.length
                    ? Math.max(2, Math.min(98, ((dataIndex + 0.5) / safeChartData.length) * 100))
                    : null;
                return {
                    id: event.id,
                    type: event.type,
                    title: event.title || this._eventTypeLabel(event.type),
                    detail: event.detail || event.missing_reason || '',
                    date_key: dateKey,
                    chartTime: event.chartTime || dateKey || event.at || '',
                    source_label: event.source_label || event.source || this._eventTypeLabel(event.type),
                    direction: event.direction || '',
                    value: event.value ?? null,
                    dataIndex,
                    timestamp: point?.timestamp ?? null,
                    high: point?.high ?? point?.close ?? point?.price ?? null,
                    low: point?.low ?? point?.close ?? point?.price ?? null,
                    close: point?.close ?? point?.price ?? null,
                    xPct,
                    color: this._chartEventColor(event.type),
                };
            })
            .filter((event) => event.date_key)
            .slice(0, 60);
    },

    _syncWorkbenchEventOverlayState(events = null, chartData = null) {
        const state = this._ensureStockWorkbenchState();
        const overlayEvents = this._stockEventOverlayEvents(
            events || state.eventFeed || [],
            chartData || this._currentChartData || [],
        );
        state.chartState = {
            ...state.chartState,
            eventOverlay: true,
            eventOverlayEvents: overlayEvents,
            eventOverlayCount: overlayEvents.length,
        };
        return state;
    },

    _removeNativeChartEventOverlays() {
        const chart = this._klineChart;
        const ids = Array.isArray(this._chartEventOverlayIds) ? this._chartEventOverlayIds : [];
        if (chart && typeof chart.removeOverlay === 'function') {
            ids.forEach((id) => {
                try {
                    chart.removeOverlay(id);
                } catch {
                    // Native event overlays are best-effort; DOM hit targets remain the fallback.
                }
            });
        }
        this._chartEventOverlayIds = [];
    },

    _renderNativeChartEventOverlays(overlayEvents = [], chartData = []) {
        this._removeNativeChartEventOverlays();
        const chart = this._klineChart;
        if (!chart || typeof chart.createOverlay !== 'function') return;
        const ids = [];
        overlayEvents.forEach((event) => {
            if (event.dataIndex === null || event.dataIndex === undefined) return;
            const point = chartData[event.dataIndex] || {};
            const timestamp = point.timestamp ?? event.timestamp;
            const high = Number(point.high ?? point.close ?? event.high ?? event.close);
            const low = Number(point.low ?? point.close ?? event.low ?? event.close);
            if (!timestamp || !Number.isFinite(high) || !Number.isFinite(low)) return;
            try {
                const id = chart.createOverlay({
                    name: 'straightLine',
                    points: [
                        { timestamp, value: low },
                        { timestamp, value: high },
                    ],
                    styles: { line: { style: 'dashed', color: event.color || this._chartEventColor(event.type), size: 1 } },
                    lock: true,
                    extendData: { stockEventId: event.id, stockEventType: event.type },
                    onClick: () => this._onStockChartEventClick(event.id),
                });
                if (id) ids.push(id);
            } catch {
                // Some chart builds reject unknown overlay options; keep the page interactive.
            }
        });
        this._chartEventOverlayIds = ids;
    },

    _renderStockChartEventLayer(chartData = null) {
        const container = document.getElementById('sd-kline-chart');
        if (!container) return;
        const safeChartData = Array.isArray(chartData) ? chartData : (this._currentChartData || []);
        this._currentChartData = safeChartData;
        const state = this._syncWorkbenchEventOverlayState(null, safeChartData);
        const overlayEvents = state.chartState?.eventOverlayEvents || [];
        if (typeof container.querySelector !== 'function' || typeof container.appendChild !== 'function') {
            return;
        }
        let layer = container.querySelector('.stock-chart-event-layer');
        if (!layer) {
            layer = document.createElement('div');
            layer.className = 'stock-chart-event-layer';
            if (typeof layer.setAttribute === 'function') layer.setAttribute('aria-label', 'K线事件标记');
            container.appendChild(layer);
        }
        const selectedId = state.selectedEvent?.id || '';
        layer.innerHTML = overlayEvents.map((event, index) => {
            const left = Number.isFinite(event.xPct) ? event.xPct : 50;
            const top = 30 + ((index % 4) * 24);
            const selected = event.id === selectedId;
            const label = this._eventTypeLabel(event.type).slice(0, 2);
            const title = [
                event.source_label || this._eventTypeLabel(event.type),
                event.title,
                event.date_key,
                event.detail,
            ].filter(Boolean).join(' · ');
            return `
                <button type="button"
                    class="stock-chart-event-dot${selected ? ' is-selected' : ''}"
                    data-chart-event-id="${App.escapeHTML(event.id)}"
                    data-chart-event-date="${App.escapeHTML(event.date_key)}"
                    aria-pressed="${selected ? 'true' : 'false'}"
                    aria-label="${App.escapeHTML(title)}"
                    title="${App.escapeHTML(title)}"
                    style="left:${left.toFixed(2)}%;top:${top}px;--event-color:${App.escapeHTML(event.color)}">
                    <span>${App.escapeHTML(label)}</span>
                </button>
            `;
        }).join('');
        if (layer.dataset && layer.dataset.bound !== '1' && typeof layer.addEventListener === 'function') {
            layer.dataset.bound = '1';
            layer.addEventListener('click', (event) => {
                const target = event.target.closest?.('[data-chart-event-id]');
                if (!target) return;
                event.preventDefault();
                this._onStockChartEventClick(target.dataset.chartEventId);
            });
        }
        this._renderNativeChartEventOverlays(overlayEvents, safeChartData);
    },

    _scrollSelectedStockEventIntoView(eventId) {
        const panel = document.getElementById('stock-bottom-panel');
        const items = Array.from(panel?.querySelectorAll?.('[data-stock-event-id]') || []);
        const item = items.find((candidate) => candidate.dataset?.stockEventId === eventId);
        if (item && typeof item.scrollIntoView === 'function') {
            try {
                item.scrollIntoView({ block: 'nearest', inline: 'nearest' });
            } catch {
                item.scrollIntoView();
            }
        }
    },

    _onStockChartEventClick(eventId) {
        return this._selectStockEvent(eventId, { focusChart: true, syncBottomTab: true, scrollBottom: true });
    },

    _renderSelectedEventMarker(event = null) {
        const container = document.getElementById('sd-kline-chart');
        if (!container) return;
        let marker = container.querySelector('.stock-selected-event-marker');
        if (!event) {
            if (marker) marker.remove();
            return;
        }
        if (!marker) {
            marker = document.createElement('div');
            marker.className = 'stock-selected-event-marker';
            container.appendChild(marker);
        }
        marker.textContent = `${this._eventTypeLabel(event.type)} · ${event.title || '事件'}`;
        marker.title = event.detail || event.at || '';
    },

    _selectStockEvent(eventId, { focusChart = true, syncBottomTab = false, scrollBottom = false } = {}) {
        const state = this._ensureStockWorkbenchState();
        const event = (state.eventFeed || []).find((item) => item.id === eventId) || null;
        this._syncWorkbenchSelectedEvent(event);
        if (event && syncBottomTab) {
            this._syncWorkbenchLayoutState({ bottomTab: this._eventBottomTab(event.type) });
        }
        this._syncWorkbenchAiContextFromState();
        if (focusChart) this._renderSelectedEventMarker(event);
        this._renderStockBottomPanel();
        this._renderStockChartEventLayer();
        if (event && scrollBottom) this._scrollSelectedStockEventIntoView(event.id);
        this._renderStockEvidenceRail(this._headerData || {}, this._buildStockIdentitySummary(this._headerData || {}));
        return event;
    },

    _renderStockEventList(events = []) {
        const state = this._ensureStockWorkbenchState();
        const selectedId = state.selectedEvent?.id || '';
        const safeEvents = Array.isArray(events) && events.length
            ? events
            : [{
                id: 'event-empty',
                type: 'news_research',
                title: '事件流暂缺',
                status: 'missing',
                detail: '新闻、公告、研报或信号事件尚未返回',
                at: '',
            }];
        return safeEvents.map((event) => {
            const selected = event.id === selectedId;
            return `
                <button type="button" class="stock-event-item${selected ? ' is-selected' : ''}" data-stock-event-id="${App.escapeHTML(event.id)}" aria-pressed="${selected ? 'true' : 'false'}">
                    <span class="stock-event-type" data-type="${App.escapeHTML(event.type || '')}">${App.escapeHTML(this._eventTypeLabel(event.type))}</span>
                    <span class="stock-event-main">
                        <strong>${App.escapeHTML(event.title || '事件')}</strong>
                        <em>${App.escapeHTML(event.detail || event.missing_reason || event.source_label || event.source || '暂无详情')}</em>
                    </span>
                    <span class="stock-event-time">${App.escapeHTML(event.date_key || event.at || event.chartTime || '')}</span>
                </button>
            `;
        }).join('');
    },

    _bindStockBottomPanel() {
        const panel = document.getElementById('stock-bottom-panel');
        if (!panel || panel.dataset.bound === '1') return;
        panel.dataset.bound = '1';
        panel.addEventListener('click', (event) => {
            const tab = event.target.closest('[data-stock-bottom-tab]');
            if (tab) {
                event.preventDefault();
                this._setStockBottomTab(tab.dataset.stockBottomTab || 'events');
                return;
            }
            const item = event.target.closest('[data-stock-event-id]');
            if (item) {
                event.preventDefault();
                this._selectStockEvent(item.dataset.stockEventId, { focusChart: true });
            }
        });
    },

    _renderStockBottomPanel() {
        const panel = document.getElementById('stock-bottom-panel');
        if (!panel) return;
        const state = this._ensureStockWorkbenchState();
        const tabs = [
            ['events', '事件'],
            ['news', '新闻'],
            ['reports', '研报/信号'],
            ['announcements', '公告/分红'],
            ['chart', '图表焦点'],
        ];
        const active = state.layoutState?.bottomTab || 'events';
        const filtered = this._filteredWorkbenchEvents(active, state.eventFeed || []);
        panel.innerHTML = `
            <div class="stock-bottom-tabs" role="tablist" aria-label="股票底部事件">
                ${tabs.map(([key, label]) => `<button type="button" class="stock-bottom-tab${key === active ? ' is-active' : ''}" data-stock-bottom-tab="${App.escapeHTML(key)}" role="tab" aria-selected="${key === active ? 'true' : 'false'}">${App.escapeHTML(label)}</button>`).join('')}
            </div>
            <div class="stock-bottom-summary">
                <span>事件 ${state.eventFeed?.length || 0}</span>
                ${state.selectedEvent ? `<strong>已选: ${App.escapeHTML(state.selectedEvent.title || '')}</strong>` : '<span class="text-muted">点击事件可同步图表焦点</span>'}
            </div>
            <div class="stock-event-list" id="stock-bottom-events" role="list">
                ${this._renderStockEventList(filtered)}
            </div>
        `;
        this._bindStockBottomPanel();
    },

    /** 全局 loading 状态 */
    _setLoading(on) {
        const content = document.getElementById('sd-content');
        if (!content) return;
        content.classList.toggle('sd-loading', on);
        content.setAttribute('aria-busy', on);
    },

    /** 切换到行情Tab时刷新（如果有选中股票） */
    refresh() {
        if (this._currentCode) {
            this.open(this._currentCode);
        }
    },

    async _loadDetail(code, stale) {
        try {
            const data = await App.fetchJSON(`/api/stock/detail/${code}`);
            if (!data || stale()) return;
            this._detailData = data;
            this._renderDetailHeader(data);
            this._renderDetailStats(data);
            this._setDetailStatus('');
        } catch (e) {
            if (!stale()) {
                this._renderDetailUnavailable(code, e);
            }
            console.error('加载股票详情失败:', e);
            App.toast(`${code} 基础资料缺失，已保留可用行情/研报模块`, 'warning');
        }
    },

    _fallbackStockName(code, options = {}) {
        const safeCode = String(code || '').trim();
        const safeOptions = options && typeof options === 'object' ? options : {};
        const optionStock = safeOptions.stock && typeof safeOptions.stock === 'object' ? safeOptions.stock : null;
        const optionName = typeof safeOptions.name === 'string' && safeOptions.name.trim() ? safeOptions.name.trim() : '';
        const matchedStock = (App.watchlistCache || []).find((item) => item.code === safeCode) || null;
        const stockStoreIdentity = globalThis.GlobalStockStore?.getState?.()?.identity || {};
        return (matchedStock && typeof matchedStock.name === 'string' && matchedStock.name.trim())
            || (optionStock && typeof optionStock.name === 'string' && optionStock.name.trim())
            || optionName
            || (stockStoreIdentity.code === safeCode && typeof stockStoreIdentity.name === 'string' ? stockStoreIdentity.name.trim() : '')
            || '';
    },

    _renderDetailPending(code, options = {}) {
        const safeCode = String(code || '').trim();
        const fallbackName = this._fallbackStockName(safeCode, options);
        this._renderDetailHeader({
            code: safeCode,
            name: fallbackName || safeCode,
            concepts: [],
        });
        this._renderDetailStats({});
        this._setDetailStatus('基础资料加载中，行情和研报模块会并行更新');
    },

    _renderDetailUnavailable(code, error) {
        const safeCode = String(code || '').trim();
        const fallbackName = this._fallbackStockName(safeCode);
        this._detailData = null;
        this._renderDetailHeader({
            code: safeCode,
            name: fallbackName || safeCode,
            concepts: [],
        });
        this._renderDetailStats({});
        const status = error && error.status === 404
            ? '本地基础资料暂未覆盖该股票，下面仅展示已取到的行情、研报和估值数据'
            : '基础资料加载失败，下面仅展示已取到的行情、研报和估值数据';
        this._setDetailStatus(status);
    },

    _setDetailStatus(message) {
        const header = document.querySelector('#tab-stock .stock-detail-header');
        if (!header) return;
        let el = document.getElementById('sd-detail-status');
        if (!message) {
            if (el) el.remove();
            return;
        }
        if (!el) {
            el = document.createElement('div');
            el.id = 'sd-detail-status';
            el.className = 'sd-detail-status';
            header.appendChild(el);
        }
        el.textContent = message;
    },

    _buildStockIdentitySummary(data = {}) {
        const concepts = Array.isArray(data.concepts) ? data.concepts.filter(Boolean) : [];
        const tags = [data.industry, data.sector, ...concepts]
            .filter((item, index, list) => item && list.indexOf(item) === index)
            .slice(0, 6);
        const positioning = data.positioning
            || data.main_business
            || data.business_scope
            || data.industry
            || '公司定位数据暂缺';
        const description = data.description || data.company_profile || data.profile || '';
        const peg = data.peg_next_year ?? data.peg ?? data.peg_ratio ?? null;
        const sourceContext = this._sourceContext || {};
        return {
            positioning,
            description,
            tags,
            peg,
            sourceLabel: sourceContext.sourceLabel || data.source_label || data.source || '资料源',
            sourceContext,
            generatedAt: data.generated_at || data.updated_at || data.timestamp || '',
            aiCoverage: data.ai_coverage || data.aiCoverage || null,
            signalCoverage: data.signal_coverage || data.signalCoverage || null,
        };
    },

    _coverageText(kind, coverage) {
        if (coverage && coverage.covered === true) return `${kind} 已覆盖`;
        if (coverage && coverage.covered === false) return `${kind} 未覆盖`;
        return `${kind} 未验证`;
    },

    _coverageReason(coverage, fallback) {
        return coverage?.reason || coverage?.missing_reason || fallback;
    },

    _uniqueEvidenceItems(items = []) {
        const seen = new Set();
        return (Array.isArray(items) ? items : [items])
            .map((item) => String(item || '').trim())
            .filter((item) => {
                if (!item || seen.has(item)) return false;
                seen.add(item);
                return true;
            });
    },

    _coverageStatus(coverage) {
        if (coverage && coverage.covered === true) return 'ready';
        if (coverage && coverage.covered === false) return 'missing';
        return 'unverified';
    },

    _qualityLabel(status) {
        return {
            ready: '可用',
            missing: '缺失',
            unverified: '待验证',
            degraded: '降级',
        }[status] || '待验证';
    },

    _buildWorkbenchEvidenceState(data = {}, summary = this._buildStockIdentitySummary(data)) {
        const sourceContext = summary.sourceContext || {};
        const sourceBits = [
            sourceContext.sourceLabel || data.source_label || data.source || '',
            sourceContext.context_type ? `上下文 ${sourceContext.context_type}` : '',
            sourceContext.sector_name ? `板块 ${sourceContext.sector_name}` : '',
            sourceContext.rank_reason || '',
            sourceContext.query ? `查询 ${sourceContext.query}` : '',
        ].filter(Boolean);
        const updatedAt = data.updated_at || data.timestamp || summary.generatedAt || '';
        const sectors = this._uniqueEvidenceItems([
            sourceContext.sector_name,
            data.sector,
            data.industry,
        ]);
        const concepts = this._uniqueEvidenceItems(Array.isArray(data.concepts) ? data.concepts : summary.tags);
        const indices = this._uniqueEvidenceItems(data.related_indices || data.indices || data.relatedIndexes || []);
        const peers = this._uniqueEvidenceItems(data.peers || data.peer_stocks || data.peerStocks || []);
        const hasQuote = data.price != null || data.change != null || data.change_pct != null;
        const hasDetail = Boolean(data.code || data.name || summary.description || summary.positioning || summary.tags.length);
        const hasPeg = summary.peg !== null && summary.peg !== undefined && summary.peg !== '' && Number.isFinite(Number(summary.peg));
        const aiStatus = this._coverageStatus(summary.aiCoverage);
        const signalStatus = this._coverageStatus(summary.signalCoverage);
        const aiReason = this._coverageReason(summary.aiCoverage, 'AI 覆盖状态待验证');
        const signalReason = this._coverageReason(summary.signalCoverage, 'Signal 覆盖状态待验证');

        const dataQuality = {
            quote: {
                status: hasQuote ? 'ready' : 'missing',
                source: data.quote_source || '个股详情行情',
                updated_at: updatedAt,
                missing_reason: hasQuote ? '' : '行情快照暂未返回价格、涨跌幅或更新时间',
            },
            detail: {
                status: hasDetail ? 'ready' : 'missing',
                source: data.detail_source || data.source || 'stock_detail_api',
                updated_at: updatedAt,
                missing_reason: hasDetail ? '' : '基础资料接口暂未返回公司身份信息',
            },
            valuation: {
                status: hasPeg ? 'ready' : 'missing',
                source: data.valuation_source || '估值服务',
                updated_at: data.valuation_snapshot_at || updatedAt,
                missing_reason: hasPeg ? '' : '估值或盈利增速数据暂未覆盖 PEG',
            },
            signal: {
                status: signalStatus,
                source: 'Signal Engine',
                updated_at: updatedAt,
                missing_reason: signalStatus === 'ready' ? '' : signalReason,
            },
            ai: {
                status: aiStatus,
                source: 'AI 证据层',
                updated_at: updatedAt,
                missing_reason: aiStatus === 'ready' ? '' : aiReason,
            },
            news_research: {
                status: 'missing',
                source: '新闻/研报模块',
                updated_at: '',
                missing_reason: '新闻、公告、研报事件流尚未汇入工作台状态',
            },
        };

        const eventFeed = [
            {
                type: 'source_context',
                status: sourceBits.length ? 'ready' : 'missing',
                title: '来源上下文',
                detail: sourceBits.join(' · ') || '未从市场入口、问财、Signal 或自选传入来源上下文',
                at: updatedAt,
            },
            {
                type: 'quote_snapshot',
                status: hasQuote ? 'ready' : 'missing',
                title: '行情快照',
                detail: hasQuote ? `价格 ${data.price ?? '--'} · 涨跌幅 ${data.change_pct ?? '--'}%` : dataQuality.quote.missing_reason,
                at: updatedAt,
            },
            {
                type: 'detail_snapshot',
                status: hasDetail ? 'ready' : 'missing',
                title: '基础资料',
                detail: hasDetail ? summary.positioning : dataQuality.detail.missing_reason,
                at: updatedAt,
            },
            {
                type: 'news_research',
                status: 'missing',
                title: '新闻/研报',
                detail: dataQuality.news_research.missing_reason,
                at: '',
            },
        ];

        return {
            relatedContext: {
                sectors,
                concepts,
                indices,
                peers,
                source: sourceContext,
                missing_reason: {
                    sectors: sectors.length ? '' : '行业/板块信息暂缺',
                    concepts: concepts.length ? '' : '概念标签暂缺',
                    indices: indices.length ? '' : '关联指数等待行情联动模块回填',
                    peers: peers.length ? '' : '同业/同板块标的等待估值或行业比较模块回填',
                },
            },
            eventFeed,
            dataQuality: {
                ...dataQuality,
                aiCoverage: summary.aiCoverage,
                signalCoverage: summary.signalCoverage,
                sourceLabel: summary.sourceLabel,
                generatedAt: summary.generatedAt,
            },
            aiContext: {
                aiCoverage: {
                    status: aiStatus,
                    label: this._coverageText('AI', summary.aiCoverage),
                    reason: aiReason,
                },
                signalCoverage: {
                    status: signalStatus,
                    label: this._coverageText('Signal', summary.signalCoverage),
                    reason: signalReason,
                },
                disclaimer: 'AI/Signal 仅展示证据覆盖和状态，不构成交易建议。',
                diagnosis: [],
            },
            sourceBits,
        };
    },

    _syncWorkbenchEvidenceState(data = {}, summary = this._buildStockIdentitySummary(data)) {
        const evidenceState = this._buildWorkbenchEvidenceState(data, summary);
        const state = this._ensureStockWorkbenchState();
        const baseEvents = (evidenceState.eventFeed || []).map((event, index) => (
            this._normalizeStockEvent(event, { source_key: 'base', id: `base-${index}` })
        ));
        this._baseWorkbenchEvents = baseEvents;
        state.relatedContext = evidenceState.relatedContext;
        state.eventFeed = this._mergeWorkbenchEventFeed(baseEvents);
        this._syncWorkbenchEventOverlayState(state.eventFeed);
        const chartEventTypes = this._chartEventTypes();
        const hasConcreteNews = state.eventFeed.some((event) => (
            event.status === 'ready'
            && chartEventTypes.has(event.type)
        ));
        state.dataQuality = {
            ...evidenceState.dataQuality,
            news_research: hasConcreteNews
                ? {
                    status: 'ready',
                    source: '事件聚合',
                    updated_at: state.eventFeed.find((event) => event.status === 'ready')?.at || '',
                    missing_reason: '',
                }
                : evidenceState.dataQuality.news_research,
        };
        state.aiContext = this._buildWorkbenchAiContext(evidenceState.aiContext, {
            data,
            summary,
            dataQuality: state.dataQuality,
            relatedContext: state.relatedContext,
            eventFeed: state.eventFeed,
            selectedEvent: state.selectedEvent,
            chartState: state.chartState,
        });
        state.sourceBits = evidenceState.sourceBits;
        evidenceState.eventFeed = state.eventFeed;
        evidenceState.dataQuality = state.dataQuality;
        evidenceState.aiContext = state.aiContext;
        this._renderStockChartEventLayer();
        return evidenceState;
    },

    _renderEvidenceQualityRows(dataQuality = {}) {
        const rows = [
            ['quote', '行情'],
            ['detail', '资料'],
            ['valuation', '估值'],
            ['signal', 'Signal'],
            ['ai', 'AI'],
            ['news_research', '新闻/研报'],
        ];
        return rows.map(([key, label]) => {
            const item = dataQuality[key] || { status: 'missing', missing_reason: '状态暂缺' };
            const status = item.status || 'unverified';
            const detail = item.missing_reason || item.source || item.updated_at || '状态可用';
            return `
                <div class="stock-evidence-row">
                    <span>${App.escapeHTML(label)}</span>
                    <strong data-status="${App.escapeHTML(status)}">${App.escapeHTML(this._qualityLabel(status))}</strong>
                    <em>${App.escapeHTML(detail)}</em>
                </div>
            `;
        }).join('');
    },

    _renderEvidenceChips(items = [], missingReason = '') {
        if (Array.isArray(items) && items.length) {
            return items.map((item) => `<span>${App.escapeHTML(item)}</span>`).join('');
        }
        return `<em>${App.escapeHTML(missingReason || '暂缺')}</em>`;
    },

    _renderEvidenceEvents(events = []) {
        const safeEvents = Array.isArray(events) && events.length
            ? events
            : [{ title: '事件', status: 'missing', detail: '事件流暂缺', at: '' }];
        return safeEvents.map((event) => `
            <div class="stock-evidence-row">
                <span>${App.escapeHTML(event.title || '事件')}</span>
                <strong data-status="${App.escapeHTML(event.status || 'unverified')}">${App.escapeHTML(this._qualityLabel(event.status || 'unverified'))}</strong>
                <em>${App.escapeHTML(event.detail || event.at || '暂无详情')}</em>
            </div>
        `).join('');
    },

    _latestReadyEvents(events = [], types = []) {
        const typeSet = new Set(types);
        return (Array.isArray(events) ? events : [])
            .filter((event) => (
                event
                && event.status === 'ready'
                && (!typeSet.size || typeSet.has(event.type))
            ))
            .sort((a, b) => {
                const aDate = a.date_key || a.chartTime || a.at || '';
                const bDate = b.date_key || b.chartTime || b.at || '';
                return bDate.localeCompare(aDate);
            });
    },

    _diagnosisRow({
        key,
        label,
        status = 'unverified',
        evidence = '',
        counterEvidence = '',
        missingReason = '',
        updatedAt = '',
        source = '',
        confidence = 'low',
        focus = false,
    }) {
        return {
            key,
            label,
            status,
            evidence,
            counter_evidence: counterEvidence,
            missing_reason: missingReason,
            updated_at: updatedAt,
            source,
            confidence,
            focus,
        };
    },

    _buildWorkbenchAiDiagnosis({
        data = {},
        summary = {},
        dataQuality = {},
        relatedContext = {},
        eventFeed = [],
        selectedEvent = null,
        chartState = {},
    } = {}) {
        const quoteStatus = dataQuality.quote?.status || 'missing';
        const detailStatus = dataQuality.detail?.status || 'missing';
        const valuationStatus = dataQuality.valuation?.status || 'missing';
        const signalStatus = dataQuality.signal?.status || 'missing';
        const aiStatus = dataQuality.ai?.status || 'missing';
        const newsStatus = dataQuality.news_research?.status || 'missing';
        const updatedAt = data.updated_at || data.timestamp || summary.generatedAt || dataQuality.generatedAt || '';
        const eventFocus = chartState?.eventFocus || null;
        const focusEvent = selectedEvent || (
            eventFocus?.event_id
                ? (eventFeed || []).find((event) => event.id === eventFocus.event_id)
                : null
        );
        const capitalEvents = this._latestReadyEvents(eventFeed, ['capital_flow', 'northbound', 'dragon_tiger']);
        const newsEvents = this._latestReadyEvents(eventFeed, ['news', 'report', 'research_report', 'announcement', 'dividend', 'alpha_signal']);
        const sectorBits = [
            ...(Array.isArray(relatedContext.sectors) ? relatedContext.sectors : []),
            ...(Array.isArray(relatedContext.concepts) ? relatedContext.concepts : []),
        ].filter(Boolean);
        const hasPeg = summary.peg !== null && summary.peg !== undefined && summary.peg !== '' && Number.isFinite(Number(summary.peg));
        const quoteEvidence = quoteStatus === 'ready'
            ? `当前${data.price != null ? `价 ${data.price}` : '行情可用'} · 涨跌幅 ${data.change_pct ?? '--'}%`
            : '';
        const focusEvidence = focusEvent
            ? `图表焦点 ${this._eventTypeLabel(focusEvent.type)} · ${focusEvent.title || '事件'}`
            : '';
        const qualityGaps = Object.entries(dataQuality)
            .filter(([, item]) => item && ['missing', 'degraded', 'unverified'].includes(item.status))
            .map(([key, item]) => `${key}:${item.missing_reason || item.status}`)
            .slice(0, 3);

        return [
            this._diagnosisRow({
                key: 'technical',
                label: '技术面',
                status: focusEvidence || quoteEvidence ? 'ready' : quoteStatus,
                evidence: [focusEvidence, quoteEvidence, `周期 ${chartState?.period || this._currentPeriod || 'timeline'}`].filter(Boolean).join(' · '),
                missingReason: quoteEvidence ? '' : dataQuality.quote?.missing_reason || 'K线/行情证据暂缺',
                updatedAt,
                source: 'K线/行情',
                confidence: focusEvidence ? 'medium' : 'low',
                focus: Boolean(focusEvidence),
            }),
            this._diagnosisRow({
                key: 'capital',
                label: '资金面',
                status: capitalEvents.length ? 'ready' : 'missing',
                evidence: capitalEvents.slice(0, 2).map((event) => `${event.title}: ${event.detail || event.value || event.at || ''}`).join('；'),
                missingReason: capitalEvents.length ? '' : '资金流、北向或龙虎榜事件暂缺',
                updatedAt: capitalEvents[0]?.at || updatedAt,
                source: capitalEvents[0]?.source_label || capitalEvents[0]?.source || '事件聚合',
                confidence: capitalEvents.length ? 'medium' : 'low',
                focus: Boolean(focusEvent && ['capital_flow', 'northbound', 'dragon_tiger'].includes(focusEvent.type)),
            }),
            this._diagnosisRow({
                key: 'news',
                label: '消息面',
                status: newsEvents.length ? 'ready' : newsStatus,
                evidence: newsEvents.slice(0, 2).map((event) => `${event.title}: ${event.detail || event.at || ''}`).join('；'),
                missingReason: newsEvents.length ? '' : dataQuality.news_research?.missing_reason || '新闻、公告、研报或信号事件暂缺',
                updatedAt: newsEvents[0]?.at || updatedAt,
                source: newsEvents[0]?.source_label || newsEvents[0]?.source || '事件聚合',
                confidence: newsEvents.length ? 'medium' : 'low',
                focus: Boolean(focusEvent && ['news', 'report', 'research_report', 'announcement', 'dividend', 'alpha_signal'].includes(focusEvent.type)),
            }),
            this._diagnosisRow({
                key: 'industry',
                label: '行业面',
                status: sectorBits.length ? 'ready' : 'missing',
                evidence: sectorBits.slice(0, 5).join(' · '),
                missingReason: sectorBits.length ? '' : relatedContext.missing_reason?.sectors || '行业、概念或来源板块暂缺',
                updatedAt,
                source: relatedContext.source?.sourceLabel || relatedContext.source?.source || '个股资料',
                confidence: sectorBits.length ? 'medium' : 'low',
            }),
            this._diagnosisRow({
                key: 'fundamental',
                label: '基本面',
                status: detailStatus,
                evidence: detailStatus === 'ready' ? (summary.positioning || data.main_business || data.name || '基础资料已返回') : '',
                missingReason: detailStatus === 'ready' ? '' : dataQuality.detail?.missing_reason || '基础资料暂缺',
                updatedAt,
                source: dataQuality.detail?.source || 'stock_detail_api',
                confidence: detailStatus === 'ready' ? 'medium' : 'low',
            }),
            this._diagnosisRow({
                key: 'valuation',
                label: '估值',
                status: valuationStatus,
                evidence: hasPeg ? `PEG ${Number(summary.peg).toFixed(2)}` : '',
                counterEvidence: hasPeg ? '' : dataQuality.valuation?.missing_reason || '估值数据暂缺',
                missingReason: hasPeg ? '' : dataQuality.valuation?.missing_reason || '估值数据暂缺',
                updatedAt: dataQuality.valuation?.updated_at || updatedAt,
                source: dataQuality.valuation?.source || '估值服务',
                confidence: valuationStatus === 'ready' ? 'medium' : 'low',
            }),
            this._diagnosisRow({
                key: 'signal',
                label: 'Signal',
                status: signalStatus === 'ready' || aiStatus === 'ready' ? 'ready' : signalStatus,
                evidence: signalStatus === 'ready'
                    ? (dataQuality.signalCoverage?.reason || dataQuality.signal?.source || 'Signal Engine 已覆盖')
                    : '',
                counterEvidence: signalStatus === 'ready' ? '' : dataQuality.signal?.missing_reason || dataQuality.ai?.missing_reason || '',
                missingReason: signalStatus === 'ready' ? '' : dataQuality.signal?.missing_reason || 'Signal 验证样本或覆盖暂缺',
                updatedAt: dataQuality.signal?.updated_at || updatedAt,
                source: 'Signal Engine',
                confidence: signalStatus === 'ready' ? 'medium' : 'low',
            }),
            this._diagnosisRow({
                key: 'risk',
                label: '风险',
                status: qualityGaps.length ? 'degraded' : 'unverified',
                evidence: focusEvent ? `当前聚焦事件: ${this._eventTypeLabel(focusEvent.type)} · ${focusEvent.title || ''}` : '未形成交易建议',
                counterEvidence: qualityGaps.join('；') || '仍需回测、仓位和风险约束确认',
                missingReason: qualityGaps.length ? '' : '风险只展示证据缺口，不输出买卖结论',
                updatedAt,
                source: 'AI 证据层',
                confidence: 'low',
            }),
        ];
    },

    _buildWorkbenchAiContext(baseContext = {}, payload = {}) {
        const diagnosis = this._buildWorkbenchAiDiagnosis(payload);
        return {
            ...(baseContext || {}),
            diagnosis,
            diagnosis_updated_at: payload.data?.updated_at || payload.data?.timestamp || payload.summary?.generatedAt || '',
            diagnosis_focus_event_id: payload.selectedEvent?.id || payload.chartState?.eventFocus?.event_id || '',
            disclaimer: baseContext?.disclaimer || 'AI/Signal 仅展示证据覆盖和状态，不构成交易建议。',
        };
    },

    _syncWorkbenchAiContextFromState() {
        const state = this._ensureStockWorkbenchState();
        const data = this._headerData || {};
        const summary = this._buildStockIdentitySummary(data);
        state.aiContext = this._buildWorkbenchAiContext(state.aiContext || {}, {
            data,
            summary,
            dataQuality: state.dataQuality || {},
            relatedContext: state.relatedContext || {},
            eventFeed: state.eventFeed || [],
            selectedEvent: state.selectedEvent || null,
            chartState: state.chartState || {},
        });
        return state.aiContext;
    },

    _renderAiDiagnosisRows(diagnosis = []) {
        const rows = Array.isArray(diagnosis) && diagnosis.length
            ? diagnosis
            : [this._diagnosisRow({
                key: 'empty',
                label: 'AI诊断',
                status: 'missing',
                missingReason: '证据诊断暂缺',
                source: 'AI 证据层',
            })];
        return rows.map((item) => {
            const status = item.status || 'unverified';
            const detail = item.evidence || item.counter_evidence || item.missing_reason || '等待证据';
            const meta = [
                item.source,
                item.updated_at,
                item.confidence ? `置信 ${item.confidence}` : '',
            ].filter(Boolean).join(' · ');
            return `
                <div class="stock-ai-diagnosis-row${item.focus ? ' is-focus' : ''}" data-diagnosis-key="${App.escapeHTML(item.key || '')}">
                    <span>${App.escapeHTML(item.label || '诊断')}</span>
                    <strong data-status="${App.escapeHTML(status)}">${App.escapeHTML(this._qualityLabel(status))}</strong>
                    <em>${App.escapeHTML(detail)}</em>
                    <small>${App.escapeHTML(meta)}</small>
                </div>
            `;
        }).join('');
    },

    _bindStockEvidenceRail() {
        const rail = document.getElementById('stock-evidence-rail');
        if (!rail || typeof rail.querySelectorAll !== 'function') return;
        rail.querySelectorAll('[data-stock-evidence-tab]').forEach((button) => {
            button.addEventListener('click', () => {
                const railTab = button.dataset.stockEvidenceTab || 'profile';
                this._syncWorkbenchLayoutState({ railTab });
                this._renderStockEvidenceRail(this._headerData || {}, this._buildStockIdentitySummary(this._headerData || {}));
            });
        });
    },

    _renderDetailHeader(data = {}) {
        this._headerData = { ...data };
        const summary = this._buildStockIdentitySummary(data);
        const setText = (id, value) => {
            const el = document.getElementById(id);
            if (el) el.textContent = value;
        };
        setText('sd-name', data.name || '--');
        setText('sd-code', data.code || '--');

        const priceEl = document.getElementById('sd-price');
        if (priceEl) {
            priceEl.textContent = data.price != null ? '¥' + Number(data.price).toFixed(2) : '--';
            priceEl.className = 'sd-price ' + ((data.change_pct || 0) >= 0 ? 'text-up' : 'text-down');
        }

        const changeEl = document.getElementById('sd-change');
        if (changeEl && data.change != null && data.change_pct != null) {
            const sign = data.change >= 0 ? '+' : '';
            changeEl.textContent = `${sign}${Number(data.change).toFixed(2)}  ${sign}${Number(data.change_pct).toFixed(2)}%`;
        } else if (changeEl) {
            changeEl.textContent = '--';
        }
        if (changeEl) changeEl.className = 'sd-change ' + ((data.change_pct || 0) >= 0 ? 'text-up' : 'text-down');

        setText('sd-industry', data.industry || '');
        setText('sd-sector', data.sector || '');
        setText('sd-positioning', summary.positioning);

        const conceptsEl = document.getElementById('sd-concepts');
        if (conceptsEl && summary.tags.length > 0) {
            conceptsEl.innerHTML = summary.tags.map(c =>
                `<span class="sd-tag">${App.escapeHTML(c)}</span>`
            ).join('');
        } else if (conceptsEl) {
            conceptsEl.innerHTML = '';
        }
        const hasPeg = summary.peg !== null && summary.peg !== undefined && summary.peg !== '' && Number.isFinite(Number(summary.peg));
        const pegText = hasPeg ? `PEG ${Number(summary.peg).toFixed(2)}` : 'PEG 缺失';
        const aiText = this._coverageText('AI', summary.aiCoverage);
        const signalText = this._coverageText('Signal', summary.signalCoverage);
        const strip = document.getElementById('sd-trust-strip');
        if (strip) {
            const chips = [
                { label: pegText, title: hasPeg ? '估值服务已回填 PEG' : 'PEG 缺失：估值或增速数据暂未覆盖' },
                { label: aiText, title: this._coverageReason(summary.aiCoverage, 'AI 覆盖状态待验证') },
                { label: signalText, title: this._coverageReason(summary.signalCoverage, 'Signal 覆盖状态待验证') },
                { label: summary.sourceLabel, title: summary.sourceContext.rank_reason || summary.generatedAt || '来源上下文' },
            ];
            strip.innerHTML = chips.map((chip) => (
                `<span class="sd-trust-chip" title="${App.escapeHTML(chip.title)}">${App.escapeHTML(chip.label)}</span>`
            )).join('');
        }
        const state = this._ensureStockWorkbenchState();
        state.quoteSnapshot = {
            ...state.quoteSnapshot,
            price: data.price ?? null,
            change: data.change ?? null,
            change_pct: data.change_pct ?? null,
            updated_at: data.updated_at || data.timestamp || summary.generatedAt || '',
            market_status: data.market_status || '',
        };
        state.fundamentalSnapshot = {
            ...state.fundamentalSnapshot,
            industry: data.industry || '',
            sector: data.sector || '',
            concepts: summary.tags,
            positioning: summary.positioning,
            peg: summary.peg,
        };
        const evidenceState = this._syncWorkbenchEvidenceState(data, summary);
        this._renderStockEvidenceRail(data, summary, evidenceState);
        this._renderStockBottomPanel();
    },

    _updateHeaderValuationStatus(valuation = {}) {
        if (!valuation || typeof valuation !== 'object') return;
        const next = {
            ...(this._headerData || {}),
            peg_next_year: valuation.peg_next_year ?? valuation.peg ?? valuation.peg_ratio ?? this._headerData?.peg_next_year,
            valuation_source: valuation.source,
            valuation_quality_status: valuation.quality_status,
            valuation_snapshot_at: valuation.snapshot_at,
        };
        this._renderDetailHeader(next);
    },

    _renderStockEvidenceRail(data = {}, summary = this._buildStockIdentitySummary(data), evidenceState = null) {
        const rail = document.getElementById('stock-evidence-rail');
        if (!rail) return;
        const workbenchState = this._ensureStockWorkbenchState();
        const state = evidenceState || {
            relatedContext: workbenchState.relatedContext || {},
            eventFeed: workbenchState.eventFeed || [],
            dataQuality: workbenchState.dataQuality || {},
            aiContext: workbenchState.aiContext || {},
            sourceBits: workbenchState.sourceBits || [],
        };
        const description = summary.description || '资料暂缺；等待基础资料、公告或研报补齐。';
        const hasPeg = summary.peg !== null && summary.peg !== undefined && summary.peg !== '' && Number.isFinite(Number(summary.peg));
        const aiText = this._coverageText('AI', summary.aiCoverage);
        const signalText = this._coverageText('Signal', summary.signalCoverage);
        const aiReason = this._coverageReason(summary.aiCoverage, 'AI 覆盖状态待验证');
        const signalReason = this._coverageReason(summary.signalCoverage, 'Signal 覆盖状态待验证');
        const sourceBits = state.sourceBits || [];
        const related = state.relatedContext || {};
        const missing = related.missing_reason || {};
        const aiContext = state.aiContext || {};
        const tabs = [
            ['orderbook', '盘口'],
            ['profile', '资料'],
            ['capital', '资金'],
            ['ai', 'AI'],
            ['sentiment', '舆情'],
        ];
        const activeTab = workbenchState.layoutState?.railTab || 'profile';
        rail.innerHTML = `
            <div class="stock-evidence-tabs" role="tablist" aria-label="股票证据栏">
                ${tabs.map(([key, label]) => {
                    const active = key === activeTab;
                    return `<button type="button" class="stock-evidence-tab${active ? ' is-active' : ''}" data-stock-evidence-tab="${App.escapeHTML(key)}" role="tab" aria-selected="${active ? 'true' : 'false'}">${App.escapeHTML(label)}</button>`;
                }).join('')}
            </div>
            <section class="stock-evidence-panel">
                <div class="stock-evidence-source">${sourceBits.map((bit) => `<span>${App.escapeHTML(bit)}</span>`).join('')}</div>
                <details class="stock-evidence-profile" open>
                    <summary>资料</summary>
                    <p>${App.escapeHTML(description)}</p>
                </details>
                <div class="stock-evidence-kv"><span>PEG</span><strong>${hasPeg ? Number(summary.peg).toFixed(2) : 'PEG 缺失'}</strong></div>
                <div class="stock-evidence-kv"><span>AI</span><strong>${App.escapeHTML(this._coverageText('AI', summary.aiCoverage))}</strong><em>${App.escapeHTML(aiReason)}</em></div>
                <div class="stock-evidence-kv"><span>Signal</span><strong>${App.escapeHTML(this._coverageText('Signal', summary.signalCoverage))}</strong><em>${App.escapeHTML(signalReason)}</em></div>
                <div class="stock-evidence-section">
                    <h4>数据质量</h4>
                    <div class="stock-evidence-list">${this._renderEvidenceQualityRows(state.dataQuality || {})}</div>
                </div>
                <div class="stock-evidence-section">
                    <h4>相关上下文</h4>
                    <div class="stock-evidence-chipset">
                        ${this._renderEvidenceChips(related.sectors, missing.sectors)}
                        ${this._renderEvidenceChips(related.concepts, missing.concepts)}
                    </div>
                    <div class="stock-evidence-muted">${App.escapeHTML(missing.indices || '')}</div>
                    <div class="stock-evidence-muted">${App.escapeHTML(missing.peers || '')}</div>
                </div>
                <div class="stock-evidence-section">
                    <h4>事件</h4>
                    <div class="stock-evidence-list">${this._renderEvidenceEvents(state.eventFeed || [])}</div>
                </div>
                <div class="stock-evidence-section">
                    <h4>AI/Signal</h4>
                    <div class="stock-evidence-kv"><span>AI</span><strong>${App.escapeHTML(aiContext.aiCoverage?.label || aiText)}</strong><em>${App.escapeHTML(aiContext.aiCoverage?.reason || aiReason)}</em></div>
                    <div class="stock-evidence-kv"><span>Signal</span><strong>${App.escapeHTML(aiContext.signalCoverage?.label || signalText)}</strong><em>${App.escapeHTML(aiContext.signalCoverage?.reason || signalReason)}</em></div>
                    <div class="stock-ai-diagnosis" aria-label="证据驱动AI诊断">
                        ${this._renderAiDiagnosisRows(aiContext.diagnosis || [])}
                    </div>
                    <p class="stock-evidence-muted">${App.escapeHTML(aiContext.disclaimer || 'AI/Signal 仅展示证据覆盖和状态。')}</p>
                </div>
            </section>
        `;
        this._bindStockEvidenceRail();
    },

    _renderDetailStats(data) {
        const set = (id, v) => {
            const el = document.getElementById(id);
            if (el) el.textContent = (v != null && v !== '') ? v : '--';
        };

        // 基础统计
        set('sd-mcap', data.market_cap);
        set('sd-ccap', data.circulating_cap);
        set('sd-pe', data.pe_ratio != null ? data.pe_ratio : '--');
        set('sd-pb', data.pb_ratio != null ? data.pb_ratio : '--');
        set('sd-turnover', data.turnover_rate ? data.turnover_rate + '%' : '--');
        set('sd-amp', data.amplitude ? data.amplitude + '%' : '--');
        set('sd-vr', data.volume_ratio != null ? data.volume_ratio : '--');

        // 52周高低 & 均量
        set('sd-52w-high', data.high_52w ? '¥' + data.high_52w.toFixed(2) : '--');
        set('sd-52w-low', data.low_52w ? '¥' + data.low_52w.toFixed(2) : '--');
        set('sd-avg-vol-5d', data.avg_volume_5d ? this._formatVolume(data.avg_volume_5d) : '--');
        set('sd-avg-vol-10d', data.avg_volume_10d ? this._formatVolume(data.avg_volume_10d) : '--');

        // 财务指标
        set('sd-eps', data.eps ? '¥' + data.eps.toFixed(2) : '--');
        set('sd-bps', data.bps ? '¥' + data.bps.toFixed(2) : '--');
        set('sd-revenue', data.revenue);
        set('sd-revenue-growth', data.revenue_growth ? data.revenue_growth.toFixed(2) + '%' : '--');
        set('sd-net-profit', data.net_profit);
        set('sd-net-profit-growth', data.net_profit_growth ? data.net_profit_growth.toFixed(2) + '%' : '--');
        set('sd-gross-margin', data.gross_margin ? data.gross_margin.toFixed(2) + '%' : '--');
        set('sd-net-margin', data.net_margin ? data.net_margin.toFixed(2) + '%' : '--');
        set('sd-roe', data.roe ? data.roe.toFixed(2) + '%' : '--');
        set('sd-debt-ratio', data.debt_ratio ? data.debt_ratio.toFixed(2) + '%' : '--');

        // 股本 & 估值
        set('sd-total-shares', data.total_shares);
        set('sd-circulating-shares', data.circulating_shares);
        set('sd-pe-ttm', data.pe_ttm != null ? data.pe_ttm : '--');
        set('sd-ps', data.ps_ratio != null ? data.ps_ratio : '--');
        set('sd-dividend-yield', data.dividend_yield ? data.dividend_yield.toFixed(2) + '%' : '--');

        // 涨跌停 & 内外盘
        set('sd-limit-up', data.limit_up ? '¥' + data.limit_up.toFixed(2) : '--');
        set('sd-limit-down', data.limit_down ? '¥' + data.limit_down.toFixed(2) : '--');
        set('sd-outer-vol', data.outer_volume ? this._formatVolume(data.outer_volume) + '手' : '--');
        set('sd-inner-vol', data.inner_volume ? this._formatVolume(data.inner_volume) + '手' : '--');
    },

});
