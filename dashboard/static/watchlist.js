/* ── 自选股管理（多选下拉模式） ── */

const Watchlist = {
    _multiSearch: null,
    _watchlistCodes: new Set(),
    _sortKey: null,
    _sortDir: 'desc',
    _lastData: [],

    init() {
        this._multiSearch = new MultiSearchBox('watchlist-input', 'watchlist-search-results', 'watchlist-tags', {
            maxResults: 50,
            formatItem: (s) => `${s.code} ${s.name || ''}`,
        });

        // 数据源：服务器端搜索
        this._multiSearch.setDataSource(async (q) => {
            if (!q) {
                // 无查询时返回自选股
                return App.watchlistCache || [];
            }
            // 服务器端搜索
            try {
                const results = await App.fetchJSON(`/api/stock/search?q=${encodeURIComponent(q)}&limit=50`);
                return results || [];
            } catch (e) {
                console.error('搜索失败:', e);
                return [];
            }
        });

        // 监听选择变化：同步到后端
        this._multiSearch.onToggle = (item, selected) => this._onToggle(item, selected);
    },

    /** 设置已选中的自选股（从后端加载后调用） */
    setSelected(codes) {
        this._watchlistCodes = new Set(codes);
        if (!this._multiSearch || !App.stockCache) return;
        const items = App.stockCache.filter(s => this._watchlistCodes.has(s.code));
        this._multiSearch.setSelected(items);
    },

    /** 单个股票切换选中状态 */
    async _onToggle(item, selected) {
        if (selected) {
            await this._addToWatchlist(item.code);
        } else {
            await this._removeFromWatchlist(item.code);
        }
    },

    async _addToWatchlist(code) {
        try {
            const res = await fetch('/api/watchlist', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
            this._watchlistCodes.add(code);
            RealtimeQuotes.subscribe([code]);
            App.toast(`已添加 ${code}`, 'success');
            // 立即刷新表格
            App.loadOverview();
            // 延迟再刷一次，等行情服务拿到行业/板块/概念数据
            clearTimeout(this._refreshTimer);
            this._refreshTimer = setTimeout(() => App.loadOverview(), 2500);
        } catch (e) {
            App.toast('添加失败: ' + e.message, 'error');
        }
    },

    async _removeFromWatchlist(code) {
        try {
            const res = await fetch(`/api/watchlist/${code}`, { method: 'DELETE' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            this._watchlistCodes.delete(code);
            RealtimeQuotes.unsubscribe([code]);
            App.toast(`已移除 ${code}`, 'success');
            App.loadOverview();
        } catch (e) {
            App.toast('移除失败: ' + e.message, 'error');
        }
    },

    render(stocks) {
        const stockBody = document.querySelector('#ov-stocks-table tbody');
        const hintEl = document.getElementById('ov-stock-hint');
        if (!stockBody) return;

        const list = Array.isArray(stocks) ? stocks : [];
        this._lastData = list;
        this._bindSortHeaders();
        this._renderRows(list, stockBody, hintEl);
    },

    _bindSortHeaders() {
        const table = document.getElementById('ov-stocks-table');
        if (!table || table._sortBound) return;
        table._sortBound = true;
        const headers = table.querySelectorAll('thead th');
        const sortMap = { 5: 'price', 6: 'change_pct' };
        Object.entries(sortMap).forEach(([idx, key]) => {
            const th = headers[idx];
            if (!th) return;
            th.style.cursor = 'pointer';
            th.style.userSelect = 'none';
            th.addEventListener('click', () => {
                if (this._sortKey === key) {
                    this._sortDir = this._sortDir === 'desc' ? 'asc' : 'desc';
                } else {
                    this._sortKey = key;
                    this._sortDir = 'desc';
                }
                this._updateSortIndicators(headers);
                const stockBody = document.querySelector('#ov-stocks-table tbody');
                const hintEl = document.getElementById('ov-stock-hint');
                this._renderRows(this._lastData, stockBody, hintEl);
            });
        });
    },

    _updateSortIndicators(headers) {
        [5, 6].forEach(idx => {
            const th = headers[idx];
            if (!th) return;
            const key = idx === 5 ? 'price' : 'change_pct';
            const base = th.textContent.replace(/ [▲▼]/g, '');
            if (this._sortKey === key) {
                th.textContent = base + (this._sortDir === 'desc' ? ' ▼' : ' ▲');
            } else {
                th.textContent = base;
            }
        });
    },

    _renderRows(list, stockBody, hintEl) {
        if (!stockBody) return;

        let sorted = [...list];
        if (this._sortKey) {
            sorted.sort((a, b) => {
                const rtA = RealtimeQuotes.getQuote(a.code);
                const rtB = RealtimeQuotes.getQuote(b.code);
                let va, vb;
                if (this._sortKey === 'price') {
                    va = rtA ? rtA.price : (a.price || a.latest_price || 0);
                    vb = rtB ? rtB.price : (b.price || b.latest_price || 0);
                } else {
                    va = rtA ? rtA.change_pct : (a.change_pct ?? 0);
                    vb = rtB ? rtB.change_pct : (b.change_pct ?? 0);
                }
                return this._sortDir === 'desc' ? vb - va : va - vb;
            });
        }

        if (sorted.length > 0) {
            if (hintEl) hintEl.textContent = `(共 ${sorted.length} 只)`;
            stockBody.innerHTML = sorted.slice(0, 20).map(s => {
                const rt = RealtimeQuotes.getQuote(s.code);
                const price = rt ? rt.price : (s.price || s.latest_price || null);
                const changePct = rt ? rt.change_pct : (s.change_pct != null ? s.change_pct : null);
                const industry = rt ? (rt.industry || '') : (s.industry || '');
                const sector = rt ? (rt.sector || '') : (s.sector || '');
                let concepts = rt ? (rt.concepts || []) : (s.concepts || []);
                if (typeof concepts === 'string') concepts = concepts.split(',').filter(Boolean);
                if (!Array.isArray(concepts)) concepts = [];
                const conceptStr = concepts.length > 0
                    ? concepts.slice(0, 3).map(c => `<span class="sd-tag">${App.escapeHTML(c)}</span>`).join('')
                    + (concepts.length > 3 ? `<span class="text-muted" title="${App.escapeHTML(concepts.join('、'))}"> +${concepts.length - 3}</span>` : '')
                    : '--';
                const priceStr = price ? '¥' + Number(price).toFixed(2) : '--';
                const changeStr = changePct != null
                    ? `<span class="change-pct">${changePct >= 0 ? '+' : ''}${changePct.toFixed(2)}%</span>`
                    : '';
                const changeClass = changePct != null ? (changePct >= 0 ? 'text-up' : 'text-down') : '';
                return `
                <tr>
                    <td>${App.escapeHTML(s.code)}</td>
                    <td><a href="#stock" class="stock-link" data-code="${App.escapeHTML(s.code)}">${App.escapeHTML(s.name) || '--'}</a></td>
                    <td>${App.escapeHTML(industry) || '--'}</td>
                    <td>${App.escapeHTML(sector) || '--'}</td>
                    <td class="concepts-cell">${conceptStr}</td>
                    <td class="${changeClass}">${priceStr}</td>
                    <td class="${changeClass}">${changeStr}</td>
                </tr>`;
            }).join('');
        } else {
            if (hintEl) hintEl.textContent = '';
            stockBody.innerHTML = '<tr><td colspan="7" class="text-muted">暂无自选股，使用上方搜索框添加</td></tr>';
        }
    },
};
