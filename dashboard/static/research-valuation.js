/* ── 研发页：估值数据中心 ── */
(function () {
    'use strict';

    const ValuationCenter = {
        _inited: false,
        _searchBox: null,
        _selected: [],
        _items: [],
        _industryFilter: '',
        _activeStockCode: '',
        _activeStockName: '',

        init() {
            if (this._inited) {
                this._syncPublicContext();
                this.load();
                return;
            }
            this._inited = true;
            this._syncPublicContext();
            this._bindSearch();
            this._bindEvents();
            this.load();
        },

        addCode(item) {
            this._addCode(item);
        },

        getContext() {
            const activeCode = this._getActiveStockCode();
            const activeName = this._getActiveStockName(activeCode);
            return {
                type: 'research',
                currentTab: 'research',
                activeSubtab: 'valuation',
                activeStock: activeCode ? {
                    code: activeCode,
                    name: activeName || null,
                } : null,
                selection: this._selected.map((item) => ({ code: item.code, name: item.name || '' })),
                filters: {
                    scope: this._normalizeScope(document.getElementById('valuation-scope')?.value || 'watchlist'),
                    industry: this._industryFilter || '',
                },
                pageDesc: '估值数据中心：PEG、同业对比、行业热力、研报共识',
            };
        },

        _syncPublicContext() {
            if (typeof App.registerContext === 'function') {
                App.registerContext('research', () => this.getContext());
            }
            const root = document.getElementById('research-panel-valuation');
            if (root) {
                const activeCode = this._getActiveStockCode();
                const activeName = this._getActiveStockName(activeCode);
                root.dataset.activeStockCode = activeCode || '';
                root.dataset.activeStockName = activeName || '';
            }
            this._renderScopeNote();
        },

        _getActiveStockCode() {
            const root = document.getElementById('research-panel-valuation');
            const code = root?.dataset?.activeStockCode?.trim();
            if (code) return code;
            const stockStore = globalThis.GlobalStockStore?.getState?.();
            return this._activeStockCode || stockStore?.identity?.code || globalThis.App?.getLastOpenedStockCode?.() || '';
        },

        _getActiveStockName(code) {
            const root = document.getElementById('research-panel-valuation');
            const name = root?.dataset?.activeStockName?.trim();
            if (name) return name;
            if (this._activeStockName) return this._activeStockName;
            const selected = this._selected.find((item) => item.code === code);
            if (selected?.name) return selected.name;
            const stockStore = globalThis.GlobalStockStore?.getState?.();
            return stockStore?.identity?.code === code ? (stockStore?.identity?.name || '') : '';
        },

        _setActiveStockContext(code, name = '') {
            const safeCode = String(code || '').trim();
            const safeName = String(name || '').trim();
            if (!safeCode) return;
            this._activeStockCode = safeCode;
            this._activeStockName = safeName;
            const root = document.getElementById('research-panel-valuation');
            if (root) {
                root.dataset.activeStockCode = safeCode;
                root.dataset.activeStockName = safeName;
            }
            this._renderScopeNote();
            this._syncPublicContext();
        },

        _bindSearch() {
            const input = document.getElementById('valuation-code-input');
            const dropdown = document.getElementById('valuation-code-dropdown');
            if (!input || !dropdown || typeof SearchBox === 'undefined') return;

            this._searchBox = new SearchBox('valuation-code-input', 'valuation-code-dropdown', {
                maxResults: 40,
                formatItem: (s) => `${s.code} ${s.name || ''}`,
            });
            this._searchBox.setDataSource(async (q) => {
                return App.searchStockPickerCandidates(q, {
                    limit: 50,
                    emptyLimit: 50,
                    emptyScope: 'watchlist',
                    silent: true,
                });
            });
            this._searchBox.onSelect((item) => {
                this._addCode(item);
            });
        },

        _bindEvents() {
            document.getElementById('valuation-refresh-btn')?.addEventListener('click', () => this.load({ force: true }));
            document.getElementById('valuation-scope')?.addEventListener('change', () => {
                this._syncCodeRow();
                this._renderScopeNote();
                this.load({ force: true });
            });
            ['valuation-max-peg', 'valuation-min-growth', 'valuation-min-upside', 'valuation-min-reports', 'valuation-bucket-filter'].forEach((id) => {
                document.getElementById(id)?.addEventListener('change', () => this.load({ force: true }));
            });
            document.getElementById('valuation-cheap-growth-btn')?.addEventListener('click', () => {
                document.getElementById('valuation-max-peg').value = '1';
                document.getElementById('valuation-min-growth').value = '15';
                document.getElementById('valuation-min-reports').value = '1';
                this.load({ force: true });
            });
            document.getElementById('valuation-clear-filter-btn')?.addEventListener('click', () => {
                ['valuation-max-peg', 'valuation-min-growth', 'valuation-min-upside'].forEach((id) => { const el = document.getElementById(id); if (el) el.value = ''; });
                const reports = document.getElementById('valuation-min-reports');
                if (reports) reports.value = '0';
                const bucket = document.getElementById('valuation-bucket-filter');
                if (bucket) bucket.value = '';
                this._industryFilter = '';
                this.load({ force: true });
            });
            document.getElementById('valuation-add-code-btn')?.addEventListener('click', () => {
                const input = document.getElementById('valuation-code-input');
                const code = input?.value?.trim();
                if (code) this._addCode({ code });
            });
            document.getElementById('valuation-code-tags')?.addEventListener('click', (event) => {
                const btn = event.target.closest('[data-valuation-remove-code]');
                if (!btn) return;
                const code = btn.dataset.valuationRemoveCode;
                this._selected = this._selected.filter((item) => item.code !== code);
                this._renderTags();
                this.load({ force: true });
            });
            document.getElementById('valuation-table')?.addEventListener('click', (event) => {
                const action = event.target.closest('[data-valuation-action]');
                if (!action) return;
                const code = action.dataset.code;
                if (!code) return;
                const type = action.dataset.valuationAction;
                if (type === 'detail') {
                    this.loadDetail(code);
                } else if (type === 'stock') {
                    App.openStockDetail(code, { source: 'valuation-center:open-stock' });
                } else if (type === 'watchlist') {
                    App.addToWatchlist(code, { source: 'valuation-center:add-watchlist' });
                }
            });
            this._syncCodeRow();
        },

        _addCode(item) {
            const code = String(item?.code || '').trim();
            if (!/^\d{6}$/.test(code)) {
                App.toast('请输入 6 位股票代码', 'error');
                return;
            }
            if (!this._selected.some((stock) => stock.code === code)) {
                this._selected.push({ code, name: item.name || '' });
            }
            const scope = document.getElementById('valuation-scope');
            if (scope) scope.value = 'codes';
            document.getElementById('valuation-code-input').value = '';
            this._setActiveStockContext(code, item.name || '');
            this._syncCodeRow();
            this._renderTags();
            this.load({ force: true });
        },

        _syncCodeRow() {
            const scope = this._normalizeScope(document.getElementById('valuation-scope')?.value || 'watchlist');
            const row = document.getElementById('valuation-code-row');
            if (row) row.classList.toggle('hidden', scope !== 'codes');
            this._renderScopeNote();
        },

        _renderTags() {
            const tags = document.getElementById('valuation-code-tags');
            if (!tags) return;
            tags.innerHTML = this._selected.map((item) => {
                const label = item.name ? `${item.code} ${item.name}` : item.code;
                return `<span class="sb-tag">${App.escapeHTML(label)}<span class="sb-tag-remove" data-valuation-remove-code="${App.escapeHTML(item.code)}">&times;</span></span>`;
            }).join('');
        },

        async load() {
            const tbody = document.querySelector('#valuation-table tbody');
            if (!tbody) return;

            const scope = this._normalizeScope(document.getElementById('valuation-scope')?.value || 'watchlist');
            const activeCode = this._getActiveStockCode();
            const currentStock = activeCode ? this._selected.find((item) => item.code === activeCode) || { code: activeCode, name: this._getActiveStockName(activeCode) } : null;
            let selectedCodes = this._selected.map((item) => item.code);
            const query = new URLSearchParams({ scope, limit: scope === 'all' ? '50' : scope === 'signal' ? '50' : '30' });
            if (scope === 'codes') {
                const preferredCodes = activeCode && !selectedCodes.includes(activeCode)
                    ? [activeCode, ...selectedCodes]
                    : selectedCodes;
                if (!this._selected.some((item) => item.code === activeCode) && currentStock) {
                    this._selected = [currentStock, ...this._selected.filter((item) => item.code !== activeCode)];
                    selectedCodes = this._selected.map((item) => item.code);
                }
                query.set('codes', preferredCodes.filter(Boolean).join(','));
            }
            this._appendFilters(query);
            if (this._industryFilter) query.set('industry', this._industryFilter);
            this._renderScopeNote();

            try {
                if (scope === 'codes' && !query.get('codes')) {
                    this._items = [];
                    this._render([]);
                    return;
                }
                query.set('max_wait_sec', '6');
                const data = await App.fetchJSON(`/api/valuation/center?${query.toString()}`, { silent: true, timeout: 20000 });
                this._items = data.items || [];
                this._render(this._items);
                this.loadIndustries(scope, query.get('codes') || selectedCodes.join(','));
                const preferredItem = activeCode
                    ? this._items.find((item) => item.code === activeCode) || this._items[0]
                    : this._items[0];
                if (preferredItem) {
                    this._setActiveStockContext(preferredItem.code, preferredItem.name || '');
                    this.loadDetail(preferredItem.code);
                } else {
                    const detail = document.getElementById('valuation-detail');
                    const reports = document.getElementById('valuation-reports');
                    const peers = document.getElementById('valuation-peer-panel');
                    if (detail) detail.innerHTML = '<div class="text-muted text-center" style="padding:20px">暂无匹配股票</div>';
                    if (reports) reports.innerHTML = '<div class="text-muted text-center" style="padding:20px">暂无数据</div>';
                    if (peers) peers.innerHTML = '<div class="text-muted text-center" style="padding:12px">暂无同业对比</div>';
                }
            } catch (error) {
                tbody.innerHTML = `<tr><td colspan="10" class="text-muted text-center">加载失败：${App.escapeHTML(error.message || '未知错误')}</td></tr>`;
            }
        },

        _appendFilters(query) {
            const val = (id) => document.getElementById(id)?.value?.trim();
            const maxPeg = val('valuation-max-peg');
            const minGrowth = val('valuation-min-growth');
            const minUpside = val('valuation-min-upside');
            const minReports = val('valuation-min-reports');
            const bucket = val('valuation-bucket-filter');
            if (maxPeg) query.set('max_peg', maxPeg);
            if (minGrowth) query.set('min_growth', minGrowth);
            if (minUpside) query.set('min_upside', minUpside);
            if (minReports) query.set('min_reports', minReports);
            if (bucket) query.set('bucket', bucket);
        },

        _render(items) {
            const tbody = document.querySelector('#valuation-table tbody');
            if (!tbody) return;
            this._renderStats(items);
            if (!items.length) {
                tbody.innerHTML = '<tr><td colspan="10" class="text-muted text-center">暂无估值数据</td></tr>';
                return;
            }
            tbody.innerHTML = items.map((item, index) => {
                const peg = this._fmtNum(item.peg_next_year);
                const pegCls = item.peg_next_year != null && item.peg_next_year <= 1 ? 'text-up' : item.peg_next_year > 2 ? 'text-down' : '';
                const upsideCls = item.upside_pct > 0 ? 'text-up' : item.upside_pct < 0 ? 'text-down' : '';
                const sourceLine = this._sourceLine(item);
                return `<tr>
                    <td>${item.rank || index + 1}</td>
                    <td><button class="link-button valuation-stock-link" data-valuation-action="detail" data-code="${App.escapeHTML(item.code)}">${App.escapeHTML(item.name || item.code)}</button><div class="text-muted text-xs">${App.escapeHTML(item.code)}</div>${sourceLine ? `<div class="text-muted text-xs">${App.escapeHTML(sourceLine)}</div>` : ''}</td>
                    <td>${App.escapeHTML(item.industry || '--')}</td>
                    <td>${this._fmtMoney(item.price)}</td>
                    <td>${this._fmtNum(item.pe_ttm)}</td>
                    <td>${this._fmtPct(item.growth_next_year_pct)}</td>
                    <td class="${pegCls}">${peg}</td>
                    <td class="${upsideCls}">${this._fmtPct(item.upside_pct)}</td>
                    <td><span class="valuation-badge">${App.escapeHTML(item.valuation_bucket || item.consensus_label || '--')}</span></td>
                    <td class="valuation-actions">
                        <button class="btn btn-xs" data-valuation-action="stock" data-code="${App.escapeHTML(item.code)}">详情</button>
                        <button class="btn btn-xs" data-valuation-action="watchlist" data-code="${App.escapeHTML(item.code)}">自选</button>
                    </td>
                </tr>`;
            }).join('');
        },

        _renderStats(items) {
            const set = (id, text) => { const el = document.getElementById(id); if (el) el.textContent = text; };
            const pegs = items.map((item) => item.peg_next_year).filter((value) => Number.isFinite(Number(value)));
            const covered = items.filter((item) => item.report_count > 0).length;
            const cheap = pegs.filter((value) => Number(value) <= 1).length;
            const sorted = [...pegs].sort((a, b) => a - b);
            const median = sorted.length ? sorted[Math.floor(sorted.length / 2)] : null;
            set('valuation-total', String(items.length));
            set('valuation-cheap-count', String(cheap));
            set('valuation-coverage', items.length ? `${Math.round(covered / items.length * 100)}%` : '--');
            set('valuation-median-peg', median != null ? Number(median).toFixed(2) : '--');
            this._renderScopeNote(items);
        },

        _renderScopeNote(items = this._items || []) {
            const note = document.getElementById('valuation-scope-note');
            if (!note) return;
            const scope = this._normalizeScope(document.getElementById('valuation-scope')?.value || 'signal');
            const labels = { signal: 'AI信号覆盖池', qlib: 'AI信号覆盖池', watchlist: '自选股', codes: '指定股票', all: '全市场估值' };
            const desc = {
                signal: '机构预测 + AI信号覆盖池，不等同全量日线',
                qlib: '机构预测 + AI信号覆盖池，不等同全量日线',
                watchlist: '当前账号自选范围',
                codes: '手动指定股票对比',
                all: '估值服务全市场扫描，非本地日线全量',
            };
            const activeCode = this._getActiveStockCode();
            const active = activeCode ? `当前 ${activeCode}` : '未指定个股';
            note.innerHTML = [
                `<span class="coverage-pill">范围 ${App.escapeHTML(labels[scope] || scope)}</span>`,
                `<span class="coverage-pill">${App.escapeHTML(desc[scope] || '当前筛选范围')}</span>`,
                `<span class="coverage-pill">样本 ${App.escapeHTML(String(items.length || 0))} 只</span>`,
                `<span class="coverage-pill">${App.escapeHTML(active)}</span>`,
            ].join('');
        },

        async loadIndustries(scope, codes) {
            const root = document.getElementById('valuation-industry-strip');
            if (!root) return;
            root.innerHTML = '<div class="text-muted">行业热力加载中...</div>';
            const normalizedScope = this._normalizeScope(scope);
            const query = new URLSearchParams({ scope: normalizedScope, limit: normalizedScope === 'all' ? '80' : normalizedScope === 'signal' ? '80' : '50' });
            if (scope === 'codes' && codes) query.set('codes', codes);
            try {
                const data = await App.fetchJSON(`/api/valuation/industries?${query.toString()}`, { silent: true, timeout: 20000 });
                const items = (data.items || []).slice(0, 6);
                if (!items.length) {
                    root.innerHTML = '<div class="text-muted">暂无行业聚合</div>';
                    return;
                }
                root.innerHTML = items.map((item) => {
                    const peg = item.median_peg == null ? '--' : Number(item.median_peg).toFixed(2);
                    const growth = item.median_growth == null ? '--' : `${Number(item.median_growth).toFixed(1)}%`;
                    const activeCls = this._industryFilter && item.industry === this._industryFilter ? ' is-active' : '';
                    return `<button class="valuation-industry-chip${activeCls}" data-industry="${App.escapeHTML(item.industry || '')}">
                        <strong>${App.escapeHTML(item.industry || '未分类')}</strong>
                        <span>${item.count || 0}只 · PEG ${peg} · 增速 ${growth}</span>
                        <em>低估高增 ${item.cheap_growth_count || 0}</em>
                    </button>`;
                }).join('');
                root.querySelectorAll('[data-industry]').forEach((btn) => {
                    btn.addEventListener('click', () => {
                        this._industryFilter = btn.dataset.industry || '';
                        this.load({ force: true });
                    });
                });
            } catch (error) {
                root.innerHTML = '<div class="text-muted">行业热力加载失败</div>';
            }
        },

        async loadDetail(code) {
            const detail = document.getElementById('valuation-detail');
            const reports = document.getElementById('valuation-reports');
            if (detail) detail.innerHTML = '<div class="text-muted text-center" style="padding:20px">加载中...</div>';
            if (reports) reports.innerHTML = '<div class="text-muted text-center" style="padding:20px">加载中...</div>';
            try {
                const data = await App.fetchJSON(`/api/valuation/stock/${encodeURIComponent(code)}?report_limit=8`, { silent: true, timeout: 20000 });
                if (data?.data?.code) {
                    this._setActiveStockContext(data.data.code, data.data.stock_name || data.data.name || '');
                }
                this._renderDetail(data.data || {});
                this.loadPeers(code);
            } catch (error) {
                if (detail) detail.innerHTML = `<div class="text-muted text-center">加载失败：${App.escapeHTML(error.message || '')}</div>`;
            }
        },

        async loadPeers(code) {
            const root = document.getElementById('valuation-peer-panel');
            if (!root) return;
            root.innerHTML = '<div class="text-muted text-center" style="padding:12px">同业对比加载中...</div>';
            try {
                const data = await App.fetchJSON(`/api/valuation/peers/${encodeURIComponent(code)}?limit=10`, { silent: true, timeout: 20000 });
                const peers = data.peers || [];
                const summary = data.summary || {};
                if (!peers.length) {
                    root.innerHTML = '<div class="text-muted text-center" style="padding:12px">暂无同业对比</div>';
                    return;
                }
                root.innerHTML = `
                    <div class="valuation-peer-head">
                        <strong>同业位置</strong>
                        <span>排名 ${summary.target_rank || '--'} / ${summary.peer_count || peers.length} · 中位PEG ${this._fmtNum(summary.median_peg)}</span>
                    </div>
                    <div class="valuation-peer-list">
                        ${peers.slice(0, 8).map((peer) => `
                            <button class="valuation-peer-item" data-peer-code="${App.escapeHTML(peer.code || '')}">
                                <span>${App.escapeHTML(peer.name || peer.code || '--')}</span>
                                <em>PEG ${this._fmtNum(peer.peg_next_year)} · 增速 ${this._fmtPct(peer.growth_next_year_pct)}</em>
                            </button>
                        `).join('')}
                    </div>
                `;
                root.querySelectorAll('[data-peer-code]').forEach((btn) => {
                    btn.addEventListener('click', () => this.loadDetail(btn.dataset.peerCode));
                });
            } catch (error) {
                root.innerHTML = '<div class="text-muted text-center" style="padding:12px">同业对比加载失败</div>';
            }
        },

        _renderDetail(item) {
            const detail = document.getElementById('valuation-detail');
            const reports = document.getElementById('valuation-reports');
            if (detail) {
                const sourceBadges = this._renderSourceBadges(item);
                const metrics = [
                    ['现价', this._fmtMoney(item.price)],
                    ['PE(TTM)', this._fmtNum(item.pe_ttm)],
                    ['明年增速', this._fmtPct(item.growth_next_year_pct)],
                    ['PEG', this._fmtNum(item.peg_next_year)],
                    ['目标价', this._fmtMoney(item.target_price)],
                    ['空间', this._fmtPct(item.upside_pct)],
                    ['研报数', item.report_count || 0],
                    ['最新评级', item.latest_rating || '--'],
                ];
                detail.innerHTML = `
                    <div class="valuation-detail-head">
                        <div><strong>${App.escapeHTML(item.name || item.code || '--')}</strong><span class="text-muted"> ${App.escapeHTML(item.code || '')}</span></div>
                        <span class="valuation-badge">${App.escapeHTML(item.valuation_bucket || '--')}</span>
                    </div>
                    ${sourceBadges}
                    <div class="valuation-metric-grid">${metrics.map(([label, value]) => `<div class="valuation-metric"><span>${label}</span><strong>${value}</strong></div>`).join('')}</div>
                `;
            }
            if (reports) {
                const list = item.reports || [];
                if (!list.length) {
                    reports.innerHTML = '<div class="text-muted text-center" style="padding:20px">暂无研报预测</div>';
                    return;
                }
                reports.innerHTML = list.map((report) => `
                    <div class="valuation-report-item">
                        <div class="valuation-report-title">${App.escapeHTML(report.title || '--')}</div>
                        <div class="valuation-report-meta">${App.escapeHTML(report.date || '')} · ${App.escapeHTML(report.org || '--')} · ${App.escapeHTML(report.rating || '--')}</div>
                        ${report.source_note ? `<div class="text-muted text-xs">${App.escapeHTML(report.source_note)}</div>` : ''}
                        <div class="valuation-report-grid">
                            <span>本年EPS ${this._fmtNum(report.this_year_eps)}</span>
                            <span>明年EPS ${this._fmtNum(report.next_year_eps)}</span>
                            <span>本年PE ${this._fmtNum(report.this_year_pe)}</span>
                            <span>明年PE ${this._fmtNum(report.next_year_pe)}</span>
                        </div>
                    </div>
                `).join('');
            }
        },

        _normalizeScope(scope) {
            return scope === 'qlib' ? 'signal' : scope;
        },

        _fmtNum(value) {
            return Number.isFinite(Number(value)) ? Number(value).toFixed(2) : '--';
        },

        _fmtPct(value) {
            return Number.isFinite(Number(value)) ? `${Number(value).toFixed(2)}%` : '--';
        },

        _fmtMoney(value) {
            return Number.isFinite(Number(value)) ? `¥${Number(value).toFixed(2)}` : '--';
        },

        _sourceLine(item) {
            const parts = [];
            if (item.source) parts.push(item.source);
            if (item.source_version) parts.push(item.source_version);
            if (item.quality_status) parts.push(item.quality_status);
            return parts.join(' · ');
        },

        _renderSourceBadges(item) {
            const badges = [];
            const pushBadge = (label, value) => {
                if (value) badges.push(`<span class="valuation-badge">${App.escapeHTML(label)} ${App.escapeHTML(value)}</span>`);
            };
            pushBadge('来源', item.source);
            pushBadge('版本', item.source_version);
            pushBadge('质量', item.quality_status);
            pushBadge('快照', item.snapshot_at);
            pushBadge('行情', item.quote_source);
            if (!badges.length) return '';
            return `<div style="display:flex;flex-wrap:wrap;gap:6px;margin:10px 0 12px;">${badges.join('')}</div>`;
        },
    };

    globalThis.ResearchValuation = ValuationCenter;
})();
