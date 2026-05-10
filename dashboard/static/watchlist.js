/* ── 自选股管理（多选下拉模式） ── */

const Watchlist = {
    _multiSearch: null,
    _watchlistCodes: new Set(),
    _sortKey: null,
    _sortDir: 'desc',
    _lastData: [],
    _stockListCache: null,
    _stockListCacheTime: 0,
    _STOCK_CACHE_TTL: 5 * 60 * 1000, // 5 分钟

    init() {
        this._multiSearch = new MultiSearchBox('watchlist-input', 'watchlist-search-results', 'watchlist-tags', {
            maxResults: 200,
            formatItem: (s) => `${s.code} ${s.name || ''}`,
        });

        // 数据源：全量股票缓存 5 分钟，搜索关键词实时请求
        this._multiSearch.setDataSource(async (q) => {
            try {
                if (!q) {
                    // 无关键词：使用缓存
                    const now = Date.now();
                    if (this._stockListCache && (now - this._stockListCacheTime) < this._STOCK_CACHE_TTL) {
                        return this._stockListCache;
                    }
                    const results = await App.fetchJSON('/api/stock/search?q=&limit=6000');
                    this._stockListCache = results || [];
                    this._stockListCacheTime = now;
                    return this._stockListCache;
                }
                // 有关键词：实时搜索
                const results = await App.fetchJSON(`/api/stock/search?q=${encodeURIComponent(q)}&limit=50`);
                return results || [];
            } catch (e) {
                console.error('搜索失败:', e);
                return [];
            }
        });

        // 监听选择变化：同步到后端（300ms 防抖）
        this._multiSearch.onToggle = (item, selected) => this._debouncedToggle(item, selected);
    },

    /** 请求去重：同一股票 300ms 内不重复操作 */
    _debouncedToggle(item, selected) {
        const key = `${item.code}_${selected}`;
        if (this._pendingToggle === key) return;
        this._pendingToggle = key;
        setTimeout(() => { this._pendingToggle = null; }, 300);
        this._onToggle(item, selected);
    },

    /** 设置已选中的自选股（从后端加载后调用，需要 stockCache） */
    setSelected(codes) {
        this._watchlistCodes = new Set(codes);
        if (!this._multiSearch || !App.stockCache) return;
        const items = App.stockCache.filter(s => this._watchlistCodes.has(s.code));
        this._multiSearch.setSelected(items);
    },

    /** 直接用完整股票数据设置已选中项（不依赖 stockCache） */
    setSelectedItems(items) {
        if (!Array.isArray(items)) return;
        this._watchlistCodes = new Set(items.map(s => s.code));
        if (this._multiSearch) {
            this._multiSearch.setSelected(items);
        }
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

            // 局部更新：追加到本地数据和表格（使用 API 返回的 name/price）
            const existing = this._lastData.find(s => s.code === code);
            if (!existing) {
                const item = {
                    code,
                    name: data.name || code,
                    industry: '', sector: '', concepts: [],
                    price: data.price || null,
                    change_pct: data.change_pct != null ? data.change_pct : null,
                };
                this._lastData.push(item);
                App.watchlistCache = [...this._lastData];
            }
            const stockBody = document.querySelector('#ov-stocks-table tbody');
            const hintEl = document.getElementById('ov-stock-hint');
            this._renderRows(this._lastData, stockBody, hintEl);
            App._watchlistRowMap = null; // 重建索引，让 WebSocket 更新能命中新行

            // 更新 tags
            if (this._multiSearch) {
                const items = this._lastData.filter(s => this._watchlistCodes.has(s.code));
                this._multiSearch.setSelected(items);
            }

            App.toast(`已添加 ${code}`, 'success');

            // 延迟刷新自选股表格，等行业/板块/概念 enrichment 完成
            // 不清除已有定时器，避免快速连续添加时互相取消
            if (!this._refreshTimer) {
                this._refreshTimer = setTimeout(() => {
                    this._refreshTimer = null;
                    this._refreshWatchlistTable();
                }, 3000);
            }
        } catch (e) {
            App.toast('添加失败: ' + e.message, 'error');
        }
    },

    async _removeFromWatchlist(code) {
        try {
            const res = await fetch(`/api/watchlist/${code}`, { method: 'DELETE' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            this._watchlistCodes.delete(code);

            // 局部更新：从本地数据移除
            this._lastData = this._lastData.filter(s => s.code !== code);
            App.watchlistCache = [...this._lastData];

            // 同步清除 MultiSearchBox 内部选中状态
            if (this._multiSearch) {
                this._multiSearch._selected = this._multiSearch._selected.filter(s => s.code !== code);
                this._multiSearch._renderTags();
            }

            RealtimeQuotes.unsubscribe([code]);

            // 重新渲染表格
            const stockBody = document.querySelector('#ov-stocks-table tbody');
            const hintEl = document.getElementById('ov-stock-hint');
            this._renderRows(this._lastData, stockBody, hintEl);

            App.toast(`已移除 ${code}`, 'success');
        } catch (e) {
            App.toast('移除失败: ' + e.message, 'error');
        }
    },

    /** 仅刷新自选股表格（增删后延迟调用，获取 enrichment 数据） */
    async _refreshWatchlistTable() {
        try {
            const fresh = await App.fetchJSON('/api/watchlist', { silent: true }).catch(() => null);
            if (!Array.isArray(fresh)) return;
            this._lastData = fresh;
            App.watchlistCache = fresh;
            this._watchlistCodes = new Set(fresh.map(s => s.code));
            const stockBody = document.querySelector('#ov-stocks-table tbody');
            const hintEl = document.getElementById('ov-stock-hint');
            this._renderRows(fresh, stockBody, hintEl);
            App._watchlistRowMap = null; // 重建索引
            if (this._multiSearch) {
                this._multiSearch.setSelected(fresh);
            }
        } catch (e) {
            console.warn('自选股表格刷新失败:', e);
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
        App._watchlistRowMap = null; // 重建索引
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
