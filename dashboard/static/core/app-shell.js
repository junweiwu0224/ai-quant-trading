(function attachAppShell(global) {
    'use strict';

    const App = global.App;
    if (!App) {
        return;
    }

    Object.assign(App, {
        _tabCache: App._tabCache || {},

        _tabTitles: {
            overview: '监控',
            stock: '行情',
            alpha: 'AI Alpha',
            paper: '模拟盘',
            openclaw: '龙虾',
            'openclaw-settings': '龙虾设置',
            'strategy-admin': '策略管理',
            strategy: '策略管理',
            intelligence: '情报',
            research: '研发',
            trade: '交易',
        },

        _normalizeTab(tab) {
            const _legacyRedirect = { backtest: 'research', alpha: 'research', portfolio: 'trade', sim: 'paper', strategy: 'research', risk: 'trade' };
            return _legacyRedirect[tab] || tab;
        },

        _setTabTitle(tab) {
            document.title = (this._tabTitles[tab] || this._tabTitles.overview) + ' - AI 量化交易系统';
        },

        _syncTabFromHash() {
            const raw = location.hash.slice(1).trim();
            const tab = raw || 'overview';
            const normalized = this._normalizeTab(tab);
            const panelId = this._tabAlias[normalized] || normalized;
            const panel = document.getElementById(`tab-${panelId}`);
            const initialized = Boolean(this._tabCache?.[normalized]);
            if (normalized !== this.currentTab || !panel?.classList.contains('active') || !initialized) {
                void this.switchTab(tab, { replaceHash: false });
            }
        },

        _initV2() {
            this._initOffcanvas();
            this._initV2Events();
            this._moveResearchPanels();
            this._researchMoved = true;
            this._initAlertAggregator();
            this._requestNotifyPermission();
            this._initNetworkStatus();
            this._initDegradedMode();
        },

        _initOffcanvas() {
            const overlay = document.getElementById('offcanvas-overlay');
            const closeBtn = document.getElementById('offcanvas-close');
            const panel = document.getElementById('stock-offcanvas');
            const panelLifecycle = global.PanelLifecycle;

            if (panelLifecycle && typeof panelLifecycle.has === 'function' && typeof panelLifecycle.register === 'function' && !panelLifecycle.has('stock-offcanvas')) {
                panelLifecycle.register({
                    id: 'stock-offcanvas',
                    title: '行情速览',
                    keywords: ['stock', 'offcanvas', 'quote', 'detail', '行情', '速览'],
                    mount() {
                        return {};
                    },
                });
            }

            if (panel && panelLifecycle && typeof panelLifecycle.mountRoot === 'function') {
                panelLifecycle.mountRoot({ root: panel });
            }

            if (overlay) overlay.addEventListener('click', () => this.closeOffcanvas());
            if (closeBtn) closeBtn.addEventListener('click', () => this.closeOffcanvas());
            document.addEventListener('keydown', (e) => {
                if (e.key !== 'Escape') {
                    return;
                }
                const paletteRoot = document.getElementById('cmd-palette');
                const isPaletteOpen = !!paletteRoot && paletteRoot.hidden !== true && !paletteRoot.classList.contains('hidden');
                if (isPaletteOpen) {
                    return;
                }
                this.closeOffcanvas();
            });
        },

        _fmtVol(v) {
            if (v >= 1e8) return (v / 1e8).toFixed(1) + '亿手';
            if (v >= 1e4) return (v / 1e4).toFixed(1) + '万手';
            return v + '手';
        },

        _fmtAmt(v) {
            if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿';
            if (v >= 1e4) return (v / 1e4).toFixed(1) + '万';
            return v.toFixed(0);
        },

        syncActiveStockContext(code, stock, source, requestPrefix) {
            const safeCode = typeof code === 'string' ? code.trim() : '';
            if (!safeCode) {
                return false;
            }

            const safeStock = stock && typeof stock === 'object' ? stock : {};
            this._activeStockCode = safeCode;
            try {
                sessionStorage.setItem('last_stock_code', safeCode);
            } catch {
                // ignore storage failures
            }
            this._syncResearchActiveStockSignal(safeCode, safeStock);
            const stockStore = global.GlobalStockStore;
            if (stockStore && typeof stockStore.setActiveStock === 'function') {
                stockStore.setActiveStock({
                    identity: {
                        code: safeCode,
                        name: typeof safeStock.name === 'string' && safeStock.name.trim() ? safeStock.name.trim() : null,
                        market: typeof safeStock.market === 'string' && safeStock.market.trim() ? safeStock.market.trim() : null,
                        exchange: typeof safeStock.exchange === 'string' && safeStock.exchange.trim() ? safeStock.exchange.trim() : null,
                    },
                    source,
                    requestId: typeof stockStore.createRequestId === 'function'
                        ? stockStore.createRequestId(requestPrefix || source || 'stock-sync')
                        : null,
                });
            }

            const rightRail = global.RightRailController;
            if (rightRail && typeof rightRail.syncStockContext === 'function') {
                rightRail.syncStockContext({
                    source,
                });
            }

            return true;
        },

        _syncResearchActiveStockSignal(code, stock) {
            const safeCode = typeof code === 'string' ? code.trim() : '';
            if (!safeCode) {
                return;
            }

            const safeStock = stock && typeof stock === 'object' ? stock : {};
            const stockStoreIdentity = globalThis.GlobalStockStore?.getState?.()?.identity || {};
            const safeName = (typeof safeStock.name === 'string' && safeStock.name.trim())
                || (stockStoreIdentity.code === safeCode && typeof stockStoreIdentity.name === 'string' ? stockStoreIdentity.name.trim() : '')
                || '';
            const root = document.getElementById('research-panel-valuation');
            if (root) {
                root.dataset.activeStockCode = safeCode;
                root.dataset.activeStockName = safeName;
            }

            if (globalThis.ResearchValuation && typeof globalThis.ResearchValuation.getContext === 'function') {
                return;
            }

            if (typeof this.registerContext !== 'function') {
                return;
            }

            this.registerContext('research', () => {
                const panel = document.getElementById('research-panel-valuation');
                const identity = globalThis.GlobalStockStore?.getState?.()?.identity || {};
                const activeCode = panel?.dataset?.activeStockCode?.trim()
                    || this._activeStockCode
                    || identity.code
                    || '';
                const activeName = panel?.dataset?.activeStockName?.trim()
                    || (identity.code === activeCode ? identity.name : '')
                    || '';
                return {
                    type: 'research',
                    currentTab: 'research',
                    activeSubtab: this._researchActiveSubtab || 'valuation',
                    activeStock: activeCode ? {
                        code: activeCode,
                        name: activeName || null,
                    } : null,
                    selection: [],
                    filters: {
                        scope: document.getElementById('valuation-scope')?.value || 'watchlist',
                        industry: '',
                    },
                    pageDesc: '估值数据中心：PEG、同业对比、行业热力、研报共识',
                };
            });
        },

        _getResearchHeaderActionButton(role) {
            return this._getLegacyActionButton(role);
        },

        async openOffcanvas(code) {
            if (typeof App.LLM !== 'undefined' && App.LLM.closeCopilot) App.LLM.closeCopilot();

            const panel = document.getElementById('stock-offcanvas');
            const overlay = document.getElementById('offcanvas-overlay');
            const body = document.getElementById('offcanvas-body');
            const title = document.getElementById('offcanvas-title');
            if (!panel || !body) return;

            const rightRail = global.RightRailController;
            const safeCode = typeof code === 'string' ? code.trim() : '';
            if (!safeCode) return;

            panel.classList.add('active');
            if (overlay) overlay.classList.add('active');
            panel.setAttribute('aria-hidden', 'false');
            body.innerHTML = '<div class="text-center" style="padding:40px"><span class="spinner"></span> 加载中...</div>';
            this.syncActiveStockContext(safeCode, { code: safeCode }, 'app:offcanvas', 'offcanvas');
            if (rightRail && typeof rightRail.activatePanel === 'function') {
                rightRail.activatePanel({
                    panelId: 'stock-offcanvas',
                    panelParams: {
                        code: safeCode,
                        name: safeCode,
                    },
                    autoOpen: true,
                    source: 'app:offcanvas',
                });
                if (typeof rightRail.syncStockContext === 'function') {
                    rightRail.syncStockContext({ source: 'app:offcanvas:activated' });
                }
            }

            try {
                const response = await this.fetchJSON(`/api/stock/detail/${safeCode}`);
                const data = response && typeof response === 'object' && response.quote && response.success !== undefined
                    ? response.quote
                    : response;
                if (!data || typeof data !== 'object') {
                    body.innerHTML = '<div class="text-muted text-center">加载失败</div>';
                    return;
                }
                const q = data;
                const name = q.name || safeCode;
                if (title) title.textContent = `${name} 行情速览`;

                this.syncActiveStockContext(safeCode, q, 'app:offcanvas', 'offcanvas');
                if (rightRail && typeof rightRail.activatePanel === 'function') {
                    rightRail.activatePanel({
                        panelId: 'stock-offcanvas',
                        panelParams: {
                            code: safeCode,
                            name,
                        },
                        autoOpen: true,
                        source: 'app:offcanvas',
                    });
                    if (typeof rightRail.syncStockContext === 'function') {
                        rightRail.syncStockContext({ source: 'app:offcanvas:activated' });
                    }
                }

                const changePct = q.change_pct ?? 0;
                const changeAbs = q.change ?? 0;
                const cls = changePct >= 0 ? 'text-up' : 'text-down';
                const sign = changePct >= 0 ? '+' : '';

                const metrics = [
                    ['今开', q.open != null ? '¥' + q.open.toFixed(2) : '--'],
                    ['最高', q.high != null ? '¥' + q.high.toFixed(2) : '--'],
                    ['最低', q.low != null ? '¥' + q.low.toFixed(2) : '--'],
                    ['昨收', q.pre_close != null ? '¥' + q.pre_close.toFixed(2) : '--'],
                    ['成交量', q.volume != null ? this._fmtVol(q.volume) : '--'],
                    ['成交额', q.amount != null ? this._fmtAmt(q.amount) : '--'],
                    ['换手率', q.turnover_rate != null ? q.turnover_rate.toFixed(2) + '%' : '--'],
                    ['PE(TTM)', q.pe_ttm != null ? q.pe_ttm.toFixed(1) : '--'],
                    ['市值', q.market_cap != null ? q.market_cap.toFixed(1) + '亿' : '--'],
                    ['量比', q.volume_ratio != null ? q.volume_ratio.toFixed(2) : '--'],
                ];

                body.innerHTML = `
                    <div class="oc-quote-header">
                        <span class="oc-quote-name">${this.escapeHTML(name)}</span>
                        <span class="oc-quote-code">${this.escapeHTML(safeCode)}</span>
                    </div>
                    <div class="oc-quote-price ${cls}">¥${q.price != null ? q.price.toFixed(2) : '--'}</div>
                    <div class="oc-quote-change ${cls}">${sign}${changeAbs.toFixed(2)} (${sign}${changePct.toFixed(2)}%)</div>
                    <div class="oc-metrics">
                        ${metrics.map(([l, v]) => `<div class="oc-metric"><span class="label">${l}</span><span class="value">${v}</span></div>`).join('')}
                    </div>
                    <div class="oc-actions">
                        <button class="btn btn-sm btn-primary" data-stock-action="open-detail" data-code="${this.escapeHTML(safeCode)}">查看详情</button>
                        <button class="btn btn-sm" data-stock-action="add-watchlist" data-code="${this.escapeHTML(safeCode)}">加自选</button>
                    </div>
                `;
            } catch (e) {
                body.innerHTML = `<div class="text-muted text-center">加载失败: ${this.escapeHTML(e.message)}</div>`;
            }
        },

        closeOffcanvas() {
            const panel = document.getElementById('stock-offcanvas');
            const overlay = document.getElementById('offcanvas-overlay');
            if (panel) {
                panel.classList.remove('active');
                panel.setAttribute('aria-hidden', 'true');
            }
            if (overlay) overlay.classList.remove('active');

            const rightRail = global.RightRailController;
            if (rightRail && typeof rightRail.deactivatePanel === 'function') {
                rightRail.deactivatePanel({
                    closeRail: false,
                    source: 'app:offcanvas',
                });
            }
        },

        _fmtVol(v) {
            if (v >= 1e8) return (v / 1e8).toFixed(1) + '亿手';
            if (v >= 1e4) return (v / 1e4).toFixed(1) + '万手';
            return v + '手';
        },

        _fmtAmt(v) {
            if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿';
            if (v >= 1e4) return (v / 1e4).toFixed(1) + '万';
            return v.toFixed(0);
        },

        _initAlertAggregator() {
            const bar = document.getElementById('alert-agg-bar');
            const textEl = document.getElementById('alert-agg-text');
            const dismissBtn = document.getElementById('alert-agg-dismiss');
            if (!bar || !textEl) return;

            this._aggAlerts = [];
            this._aggSilenced = false;
            this._aggTimer = null;

            const update = () => {
                const alerts = this._aggAlerts;
                if (alerts.length === 0) {
                    bar.classList.add('hidden');
                    return;
                }
                bar.classList.remove('hidden');
                const danger = alerts.filter(a => a.level === 'critical').length;
                const warn = alerts.filter(a => a.level === 'warn').length;
                bar.className = 'alert-agg-bar ' + (danger > 0 ? 'level-critical' : warn > 0 ? 'level-warn' : 'level-danger');
                if (this._aggSilenced) bar.classList.add('silenced');
                const parts = [];
                if (danger > 0) parts.push(`${danger}个严重`);
                if (warn > 0) parts.push(`${warn}个警告`);
                textEl.textContent = parts.join('，') + ' — ' + alerts[alerts.length - 1].msg;
            };

            this.on('risk:alert', (data) => {
                this._aggAlerts.push({ level: data.level || 'warn', msg: data.msg || '风控告警', ts: Date.now() });
                this._aggSilenced = false;
                update();
                clearTimeout(this._aggTimer);
                this._aggTimer = setTimeout(() => { this._aggSilenced = true; update(); }, 30000);
            });

            this.on('alert:triggered', (data) => {
                this._aggAlerts.push({ level: 'warn', msg: `预警触发: ${data.code || ''}`, ts: Date.now() });
                this._aggSilenced = false;
                update();
                clearTimeout(this._aggTimer);
                this._aggTimer = setTimeout(() => { this._aggSilenced = true; update(); }, 30000);
            });

            if (dismissBtn) {
                dismissBtn.addEventListener('click', () => {
                    this._aggAlerts = [];
                    this._aggSilenced = false;
                    clearTimeout(this._aggTimer);
                    update();
                });
            }
        },

        _initV2Events() {
            const rightRail = global.RightRailController;
            const stockStore = global.GlobalStockStore;

            if (rightRail && typeof rightRail.subscribe === 'function' && stockStore && typeof stockStore.patchUI === 'function') {
                rightRail.subscribe((state) => {
                    const nextActivePanel = state && typeof state.activePanelId === 'string' ? state.activePanelId : null;
                    const nextIsOpen = state && state.isOpen === true;
                    const nextDisplayMode = state && typeof state.displayMode === 'string' ? state.displayMode : 'hidden';
                    const nextWidth = state && state.ui && Number.isFinite(Number(state.ui.width)) ? Number(state.ui.width) : null;
                    const nextPanelParams = state && state.panelParams && typeof state.panelParams === 'object'
                        ? state.panelParams
                        : null;
                    const currentStore = typeof stockStore.getState === 'function' ? stockStore.getState() : null;
                    const currentUi = currentStore && currentStore.ui ? currentStore.ui : null;
                    const currentActivePanel = currentUi && typeof currentUi.activePanel === 'string' ? currentUi.activePanel : null;
                    const currentIsOpen = currentUi && currentUi.isOpen === true;
                    const currentDisplayMode = currentUi && typeof currentUi.displayMode === 'string' ? currentUi.displayMode : 'hidden';
                    const currentWidth = currentUi && Number.isFinite(Number(currentUi.width)) ? Number(currentUi.width) : null;
                    const currentPanelParams = currentUi && currentUi.panelParams && typeof currentUi.panelParams === 'object'
                        ? currentUi.panelParams
                        : null;
                    const currentPanelParamsKey = currentPanelParams ? JSON.stringify(currentPanelParams) : '';
                    const nextPanelParamsKey = nextPanelParams ? JSON.stringify(nextPanelParams) : '';
                    const hasChanged = currentActivePanel !== nextActivePanel
                        || currentIsOpen !== nextIsOpen
                        || currentDisplayMode !== nextDisplayMode
                        || currentWidth !== nextWidth
                        || currentPanelParamsKey !== nextPanelParamsKey;

                    if (!hasChanged) {
                        return;
                    }

                    stockStore.patchUI({
                        patch: {
                            activePanel: nextActivePanel,
                            isOpen: nextIsOpen,
                            displayMode: nextDisplayMode,
                            width: nextWidth,
                            panelParams: nextPanelParams,
                        },
                        source: 'app:right-rail-sync',
                    });
                });
            }

            this.on('news:open-stock', ({ code }) => {
                if (code) {
                    this.openStockDetail(code, {
                        source: 'app:news-open-stock',
                    });
                }
            });

            this.on('iwencai:send-to-screener', async ({ pool, query }) => {
                await this.ensureBundle?.('research');
                const codes = Array.isArray(pool)
                    ? Array.from(new Set(pool.map((code) => String(code || '').trim()).filter(Boolean)))
                    : [];
                this.toast(`已推送 ${codes.length} 只股票至选股器`, 'success');
                await this.switchTab('research', { subtab: 'screener' });
                requestAnimationFrame(() => {
                    requestAnimationFrame(() => {
                        if (typeof App.Screener !== 'undefined') {
                            if (App.Screener.init && !this._tabCache['screener']) {
                                App.Screener.init();
                                this._tabCache['screener'] = Date.now();
                            }
                            if (App.Screener.renderFromPool) {
                                App.Screener.renderFromPool(codes, query);
                            }
                        }
                    });
                });
            });

            this.on('iwencai:analyze', async ({ query, data }) => {
                await this.ensureBundle?.('llm');
                if (typeof App.LLM !== 'undefined') {
                    this.toast('已发送至 AI 助手', 'info');
                    App.LLM.openCopilot();
                    let msg;
                    if (data && Array.isArray(data.summaryRows) && data.summaryRows.length > 0) {
                        const rows = data.summaryRows.slice(0, 10);
                        msg = `请分析以下问财查询结果：\n查询：${query}\n精简数据：${JSON.stringify(rows)}`;
                    } else {
                        msg = query;
                    }
                    setTimeout(() => App.LLM.sendQuick(msg), 400);
                }
            });

            this.on('data:portfolio-updated', ({ source } = {}) => {
                const active = this.currentTab;
                if (active === 'overview') {
                    this.loadOverview();
                } else if (active === 'trade') {
                    this.loadTradeTab();
                }
            });

            this.on('timeline:focus', ({ date }) => {
                if (!date) return;
                this.switchTab('research');
                requestAnimationFrame(() => {
                    ['alpha-start', 'bt-start', 'ensemble-start'].forEach(id => {
                        const el = document.getElementById(id);
                        if (el && !el.value) el.value = date;
                    });
                    this.toast(`已联动日期: ${date}`, 'info');
                });
            });
        },

        _researchMoved: false,
        _researchTabsInited: false,
        _tradeTabsInited: false,
        _researchSession: { code: '', startDate: '', endDate: '' },

        _saveResearchSession() {
            const active = this._researchActiveSubtab;
            if (!active) return;
            const fieldMap = {
                factor:    { code: 'alpha-code',      start: 'alpha-start',    end: 'alpha-end' },
                model:     { code: 'ensemble-codes',   start: 'ensemble-start', end: 'ensemble-end' },
                backtest:  { code: 'bt-code',          start: 'bt-start',       end: 'bt-end' },
                compare:   { code: 'compare-codes-input' },
            };
            const m = fieldMap[active];
            if (!m) return;
            const codeEl = document.getElementById(m.code);
            const startEl = m.start && document.getElementById(m.start);
            const endEl = m.end && document.getElementById(m.end);
            if (codeEl?.value?.trim()) this._researchSession.code = codeEl.value.trim();
            if (startEl?.value) this._researchSession.startDate = startEl.value;
            if (endEl?.value) this._researchSession.endDate = endEl.value;
        },

        _applyResearchSession() {
            const subtab = this._researchActiveSubtab;
            const s = this._researchSession;
            if (!s.code) return;
            const fieldMap = {
                factor:    { code: 'alpha-code',      start: 'alpha-start',    end: 'alpha-end' },
                model:     { code: 'ensemble-codes',   start: 'ensemble-start', end: 'ensemble-end' },
                backtest:  { code: 'bt-code',          start: 'bt-start',       end: 'bt-end' },
            };
            const m = fieldMap[subtab];
            if (!m) return;
            const codeEl = document.getElementById(m.code);
            if (codeEl && !codeEl.value) codeEl.value = s.code;
            if (m.start) {
                const startEl = document.getElementById(m.start);
                if (startEl && !startEl.value && s.startDate) startEl.value = s.startDate;
            }
            if (m.end) {
                const endEl = document.getElementById(m.end);
                if (endEl && !endEl.value && s.endDate) endEl.value = s.endDate;
            }
        },

        _initTradeSubTabs() {
            if (this._tradeTabsInited) return;
            this._tradeTabsInited = true;
            this._bindBrokerConfig();
            const tabs = document.querySelectorAll('.trade-sub-tab');
            if (!tabs.length) return;
            tabs.forEach(tab => {
                tab.addEventListener('click', () => {
                    tabs.forEach(t => { t.classList.remove('active'); t.setAttribute('aria-selected', 'false'); });
                    tab.classList.add('active');
                    tab.setAttribute('aria-selected', 'true');
                    document.querySelectorAll('.trade-sub-panel').forEach(p => p.classList.remove('active'));
                    const subtab = tab.dataset.subtab;
                    const panel = document.getElementById('trade-panel-' + subtab);
                    if (panel) panel.classList.add('active');
                    if (subtab === 'broker' && !this._tabCache['broker']) {
                        this.loadBrokerConfig();
                        this._tabCache['broker'] = Date.now();
                    }
                    requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
                });
            });
        },

        _bindBrokerConfig() {
            if (this._brokerConfigBound) return;
            this._brokerConfigBound = true;

            const brokerType = document.getElementById('br-type');
            const saveButton = document.getElementById('br-save-btn');
            const testButton = document.getElementById('br-test-btn');

            brokerType?.addEventListener('change', (event) => {
                this.onBrokerTypeChange(event.target.value);
            });
            saveButton?.addEventListener('click', (event) => {
                event.preventDefault();
                this.saveBrokerConfig();
            });
            testButton?.addEventListener('click', (event) => {
                event.preventDefault();
                this.testBrokerConn();
            });
        },

        _initResearchSubTabs() {
            if (!this._researchMoved) {
                this._researchMoved = true;
                this._moveResearchPanels();
            }
            if (this._researchTabsInited) return;
            this._researchTabsInited = true;
            const tabs = document.querySelectorAll('.research-sub-tab');
            if (tabs.length) {
                tabs.forEach(tab => {
                    tab.addEventListener('click', async (event) => {
                        event?.preventDefault?.();
                        await this._activateResearchSubTab(tab.dataset.subtab, { saveSession: true });
                    });
                });
            }
        },

        async _activateResearchSubTab(subtab, options = {}) {
            if (options.saveSession) {
                this._saveResearchSession();
            }

            const tabs = Array.from(document.querySelectorAll('.research-sub-tab'));
            const requestedSubtab = typeof subtab === 'string' && subtab.trim() ? subtab.trim() : '';
            const selectedTab = tabs.find(t => t.dataset.subtab === requestedSubtab)
                || tabs.find(t => t.dataset.subtab === 'valuation')
                || tabs[0]
                || null;
            const activeSubtab = selectedTab?.dataset?.subtab || requestedSubtab || 'valuation';

            tabs.forEach(t => {
                const isActive = t === selectedTab;
                t.classList.toggle('active', isActive);
                t.setAttribute('aria-selected', String(isActive));
            });

            document.querySelectorAll('.research-sub-panel').forEach(p => p.classList.remove('active'));
            const panel = document.getElementById('research-panel-' + activeSubtab);
            if (panel) panel.classList.add('active');

            await this._onResearchSubTabActivate(activeSubtab);
            if (options.applySession !== false) {
                requestAnimationFrame(() => this._applyResearchSession());
            }
            return activeSubtab;
        },

        _moveResearchPanels() {
            const move = (srcId, destId) => {
                const src = document.getElementById(srcId);
                const dest = document.getElementById(destId);
                if (src && dest) {
                    while (src.firstChild) dest.appendChild(src.firstChild);
                }
            };

            move('alpha-panel-factor', 'research-panel-factor');

            const modelDest = document.getElementById('research-panel-model');
            const modelSrc = document.getElementById('alpha-panel-model');
            const signalSrc = document.getElementById('alpha-panel-signal');
            const compareSrc = document.getElementById('alpha-panel-compare');
            const wfSrc = document.getElementById('alpha-panel-wf');
            if (modelDest) {
                const researchPanels = document.querySelector('#tab-research .research-sub-panels');
                const alphaHeader = document.querySelector('#tab-alpha .page-header');
                const alphaStats = document.getElementById('alpha-perf-stats');
                if (alphaHeader && researchPanels) researchPanels.parentNode.insertBefore(alphaHeader, researchPanels);
                if (alphaStats && researchPanels) researchPanels.parentNode.insertBefore(alphaStats, researchPanels);
                if (modelSrc) { while (modelSrc.firstChild) modelDest.appendChild(modelSrc.firstChild); }
                if (signalSrc) { while (signalSrc.firstChild) modelDest.appendChild(signalSrc.firstChild); }
                if (compareSrc) { while (compareSrc.firstChild) modelDest.appendChild(compareSrc.firstChild); }
                if (wfSrc) { while (wfSrc.firstChild) modelDest.appendChild(wfSrc.firstChild); }
            }

            const btPanel = document.getElementById('tab-backtest');
            const btDest = document.getElementById('research-panel-backtest');
            if (btPanel && btDest) {
                while (btPanel.children.length > 0) {
                    btDest.appendChild(btPanel.children[0]);
                }
            }

            move('alpha-panel-llm', 'research-panel-model');

            const miningDest = document.getElementById('research-panel-mining');
            const mineSrc = document.getElementById('alpha-panel-mine');
            const portoptSrc = document.getElementById('alpha-panel-portopt');
            if (miningDest) {
                if (mineSrc) { while (mineSrc.firstChild) miningDest.appendChild(mineSrc.firstChild); }
                if (portoptSrc) { while (portoptSrc.firstChild) miningDest.appendChild(portoptSrc.firstChild); }
            }
        },

        async _onResearchSubTabActivate(subtab) {
            const alphaHeader = document.querySelector('#tab-research > .page-header');
            const alphaStats = document.getElementById('alpha-perf-stats');
            const modelSel = document.getElementById('alpha-model');
            const analyzeBtn = this._getResearchHeaderActionButton('alpha-analyze');
            const optimizeBtn = this._getResearchHeaderActionButton('alpha-optimize');
            const modelGroup = modelSel?.closest('.research-param-model');
            const actionGroup = analyzeBtn?.closest('.research-param-actions');
            const needsHeader = ['factor', 'model', 'mining'].includes(subtab);

            if (alphaHeader) alphaHeader.style.display = needsHeader ? '' : 'none';
            if (alphaStats) alphaStats.style.display = (subtab === 'model') ? '' : 'none';
            if (modelSel) modelSel.style.display = (subtab === 'model') ? '' : 'none';
            if (analyzeBtn) analyzeBtn.style.display = (subtab === 'model') ? '' : 'none';
            if (optimizeBtn) optimizeBtn.style.display = (subtab === 'model') ? '' : 'none';
            if (modelGroup) modelGroup.style.display = (subtab === 'model') ? '' : 'none';
            if (actionGroup) actionGroup.style.display = (subtab === 'model') ? '' : 'none';

            this._researchActiveSubtab = subtab;
            if (!needsHeader) {
                const codeInput = document.getElementById('alpha-code');
                if (codeInput) codeInput.value = '';
            }

            if (subtab === 'backtest') {
                await this.ensureBundle?.('research');
                this.bindBacktest?.();
                this.bindOptimize?.();
                this.bindSensitivity?.();
                if (typeof Backtest !== 'undefined' && Backtest.load && !this._tabCache['backtest']) {
                    Backtest.load();
                    this._tabCache['backtest'] = Date.now();
                }
            } else if (subtab === 'datahub') {
                await this.ensureBundle?.('research');
                if (globalThis.ResearchDataHub?.init) {
                    globalThis.ResearchDataHub.init();
                }
            } else if (subtab === 'valuation') {
                await this.ensureBundle?.('research');
                if (globalThis.ResearchValuation?.init) {
                    globalThis.ResearchValuation.init();
                }
            } else if (subtab === 'factor') {
                await this.ensureBundle?.('research');
                if (typeof Factor !== 'undefined' && Factor.init && !this._tabCache['factor']) {
                    Factor.init();
                    this._tabCache['factor'] = Date.now();
                }
            } else if (subtab === 'strategy') {
                await this.ensureBundle?.('strategy');
                if (typeof Strategy !== 'undefined') Strategy.load();
            } else if (subtab === 'screener') {
                await this.ensureBundle?.('research');
                if (typeof App.Screener !== 'undefined' && App.Screener.init && !this._tabCache['screener']) {
                    App.Screener.init();
                    this._tabCache['screener'] = Date.now();
                }
            } else if (subtab === 'compare') {
                await this.ensureBundle?.('research');
                if (typeof App.Compare !== 'undefined' && App.Compare.init && !this._tabCache['compare']) {
                    App.Compare.init();
                    this._tabCache['compare'] = Date.now();
                }
            } else if (subtab === 'model' || subtab === 'formula' || subtab === 'basket') {
                await this.ensureBundle?.('research');
                if (typeof App.initAlpha === 'function') {
                    App.initAlpha();
                    this._tabCache[subtab] = Date.now();
                }
            } else if (subtab === 'agentic') {
                await this.ensureBundle?.('research');
                globalThis.AgenticSignals?.boot?.();
            }
            requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
        },

        _setTabTitle(tab) {
            document.title = (this._tabTitles[tab] || this._tabTitles.overview) + ' - AI 量化交易系统';
        },

        async switchTab(tab, options = {}) {
            const requestedTab = this._normalizeTab(typeof tab === 'string' && tab ? tab : 'overview');
            const requestedPanelId = this._tabAlias[requestedTab] || requestedTab;
            const activeTab = document.getElementById(`tab-${requestedPanelId}`) ? requestedTab : 'overview';
            const activePanelId = this._tabAlias[activeTab] || activeTab;

            this.currentTab = activeTab;

            document.querySelectorAll('.nav-link').forEach(l => {
                const isActive = l.dataset.tab === activeTab;
                l.classList.toggle('active', isActive);
                l.setAttribute('aria-selected', String(isActive));
            });
            document.querySelectorAll('.tab-panel').forEach(p => {
                const isActive = p.id === `tab-${activePanelId}`;
                p.classList.toggle('active', isActive);
                p.classList.toggle('hidden', !isActive);
                p.setAttribute('aria-hidden', isActive ? 'false' : 'true');
                if (isActive) {
                    p.removeAttribute('hidden');
                    p.removeAttribute('inert');
                } else {
                    p.setAttribute('hidden', '');
                    p.setAttribute('inert', '');
                }
            });

            this._setTabTitle(activeTab);
            if (options.replaceHash !== false && location.hash !== '#' + activeTab) {
                history.replaceState(null, '', '#' + activeTab);
            }

            if (activeTab === 'overview') {
                if (typeof this._registerOverviewTimers === 'function') {
                    this._registerOverviewTimers();
                }
                this._startMarketRefresh();
            } else {
                this._stopMarketRefresh();
                if (typeof this._unregisterOverviewTimers === 'function') {
                    this._unregisterOverviewTimers();
                }
            }

            if (activeTab === 'trade') {
                this._rkStartPolling && this._rkStartPolling();
            } else {
                this._rkStopPolling && this._rkStopPolling();
            }

            if (activeTab !== 'paper') {
                globalThis.Paper?._stopPolling?.();
            }

            const now = Date.now();
            const cached = this._tabCache[activeTab];
            const stale = !cached || (now - cached > 30000);

            if (activeTab === 'overview') {
                await this.ensureBundle?.('overview');
                if (stale) { this.loadOverview(); this._tabCache[activeTab] = now; }
            }
            else if (activeTab === 'trade') {
                await this.ensureBundle?.('trade');
                this._initTradeSubTabs();
                if (stale) { this.loadTradeTab(); this._tabCache[activeTab] = now; }
            }
            else if (activeTab === 'strategy-admin') {
                await this.ensureBundle?.('strategy');
                globalThis.Strategy?.load?.();
            }
            else if (activeTab === 'research') {
                await this.ensureBundle?.('research');
                this.bindBacktest?.();
                this.bindOptimize?.();
                this.bindSensitivity?.();
                this.bindStrategyChips?.();
                this._initResearchSubTabs();
                const requestedSubtab = typeof options.subtab === 'string' ? options.subtab.trim() : '';
                const domActiveSubtab = document.querySelector('.research-sub-tab.active')?.dataset?.subtab || '';
                const activeResearchSubtab = requestedSubtab || this._researchActiveSubtab || domActiveSubtab || 'valuation';
                await this._activateResearchSubTab(activeResearchSubtab);
            }
            else if (activeTab === 'paper') {
                await this.ensureBundle?.('paper');
                globalThis.Paper?.init?.();
                globalThis.Paper?._startPolling?.();
                if (stale) { globalThis.Paper?.loadStatus?.(); this._tabCache[activeTab] = now; }
            }
            else if (activeTab === 'openclaw') {
                await this.ensureBundle?.('openclaw');
                await globalThis.OpenClawWorkbench?.maybeInitForTab?.('openclaw');
            }
            else if (activeTab === 'openclaw-settings') {
                await this.ensureBundle?.('openclaw');
                await globalThis.OpenClawWorkbench?.maybeInitForTab?.('openclaw-settings');
            }
            else if (activeTab === 'stock') {
                await this.ensureBundle?.('stock');
                globalThis.StockDetail?.init?.();
                if (options.autoOpenStock === false) {
                    return;
                }
                const activeCode = (typeof this.getLastOpenedStockCode === 'function' && this.getLastOpenedStockCode())
                    || this._activeStockCode
                    || globalThis.StockDetail?._currentCode
                    || globalThis.GlobalStockStore?.getState?.()?.identity?.code
                    || '';
                if (activeCode) {
                    if (activeCode !== globalThis.StockDetail?._currentCode) {
                        await globalThis.StockDetail?.open?.(activeCode);
                    } else {
                        globalThis.StockDetail?.refresh?.();
                    }
                }
            }
            else if (activeTab === 'intelligence') {
                await this.ensureBundle?.('intelligence');
                globalThis.Intelligence?.init?.();
                globalThis.Intelligence?.load?.();
            }

            requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
        },
    });
})(window);
