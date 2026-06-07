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
        const gen = ++this._openGeneration;
        this._currentCode = code;
        this._detailData = null;
        const safeOptions = options && typeof options === 'object' ? options : {};
        const optionStock = safeOptions.stock && typeof safeOptions.stock === 'object' ? safeOptions.stock : null;
        const optionName = typeof safeOptions.name === 'string' && safeOptions.name.trim() ? safeOptions.name.trim() : '';
        const source = typeof safeOptions.source === 'string' && safeOptions.source.trim() ? safeOptions.source.trim() : 'stock-detail:open';
        const awaitDeferredLoad = safeOptions.awaitDeferredLoad === true;

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
        if (content) content.style.display = 'block';
        if (placeholder) placeholder.style.display = 'none';

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
        const critical = [
            this._loadDetail(code, stale),
            this._loadTimeline(code, stale),
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

    _renderDetailHeader(data) {
        document.getElementById('sd-name').textContent = data.name || '--';
        document.getElementById('sd-code').textContent = data.code || '--';

        const priceEl = document.getElementById('sd-price');
        priceEl.textContent = data.price != null ? '¥' + data.price.toFixed(2) : '--';
        priceEl.className = 'sd-price ' + ((data.change_pct || 0) >= 0 ? 'text-up' : 'text-down');

        const changeEl = document.getElementById('sd-change');
        if (data.change != null && data.change_pct != null) {
            const sign = data.change >= 0 ? '+' : '';
            changeEl.textContent = `${sign}${data.change.toFixed(2)}  ${sign}${data.change_pct.toFixed(2)}%`;
        } else {
            changeEl.textContent = '--';
        }
        changeEl.className = 'sd-change ' + ((data.change_pct || 0) >= 0 ? 'text-up' : 'text-down');

        document.getElementById('sd-industry').textContent = data.industry || '';
        document.getElementById('sd-sector').textContent = data.sector || '';

        const conceptsEl = document.getElementById('sd-concepts');
        if (data.concepts && data.concepts.length > 0) {
            conceptsEl.innerHTML = data.concepts.slice(0, 15).map(c =>
                `<span class="sd-tag">${App.escapeHTML(c)}</span>`
            ).join('');
        } else {
            conceptsEl.innerHTML = '';
        }
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
