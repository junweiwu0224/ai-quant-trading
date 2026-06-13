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

        _buildIwencaiProviderEvidenceForPrompt(sourceContext) {
            const source = sourceContext && typeof sourceContext === 'object' ? sourceContext : {};
            const evidence = source.provider_evidence && typeof source.provider_evidence === 'object'
                ? source.provider_evidence
                : null;
            if (!evidence) {
                return null;
            }
            const safeText = (value, limit = 160) => {
                if (value === null || value === undefined) return '';
                return String(value)
                    .replace(/\b(cookie|token|secret|password|passwd|authorization|session|api[_-]?key|invite)\s*[:=]\s*[^,\s;]+/ig, '[redacted]')
                    .replace(/Bearer\s+[A-Za-z0-9._~+/=-]+/g, '[redacted]')
                    .slice(0, limit);
            };
            const safeNumber = (value) => {
                const num = Number(value);
                return Number.isFinite(num) ? num : 0;
            };
            const safeObjectCounts = (value, maxKeys = 12) => {
                if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
                return Object.fromEntries(Object.entries(value)
                    .slice(0, maxKeys)
                    .map(([key, count]) => [safeText(key, 80), safeNumber(count)]));
            };
            const degradation = evidence.degradation && typeof evidence.degradation === 'object'
                ? evidence.degradation
                : {};
            return {
                schema_version: safeText(evidence.schema_version, 80),
                summary_status: safeText(evidence.summary_status, 80),
                field_coverage_status: safeText(evidence.field_coverage_status, 80),
                provider: safeText(evidence.provider, 80),
                provider_status: safeText(evidence.provider_status, 80),
                data_status: safeText(evidence.data_status, 80),
                cache_status: safeText(evidence.cache_status, 80),
                candidate_count: safeNumber(evidence.candidate_count),
                reported_total: safeNumber(evidence.reported_total),
                condition_status_counts: safeObjectCounts(evidence.condition_status_counts),
                candidate_validation: safeObjectCounts(evidence.candidate_validation),
                write_actions_allowed: evidence.write_actions_allowed === true,
                enabled_write_actions: Array.isArray(evidence.enabled_write_actions)
                    ? evidence.enabled_write_actions.map((item) => safeText(item, 80)).filter(Boolean).slice(0, 8)
                    : [],
                blocked_write_actions: Array.isArray(evidence.blocked_write_actions)
                    ? evidence.blocked_write_actions.map((item) => safeText(item, 80)).filter(Boolean).slice(0, 8)
                    : [],
                degradation: {
                    type: safeText(degradation.type, 80),
                    reason: safeText(degradation.reason, 180),
                    next_action: safeText(degradation.next_action, 180),
                    cache_status: safeText(degradation.cache_status, 80),
                    retry_after_seconds: safeText(degradation.retry_after_seconds, 40),
                    response_type: safeText(degradation.response_type, 80),
                    schema_signature: safeText(degradation.schema_signature, 160),
                },
            };
        },

        _buildIwencaiProviderEvidenceForReview(sourceContext) {
            const source = sourceContext && typeof sourceContext === 'object' ? sourceContext : {};
            const evidence = source.provider_evidence && typeof source.provider_evidence === 'object'
                ? source.provider_evidence
                : null;
            if (!evidence) {
                return null;
            }
            const safeText = (value, limit = 180) => {
                if (value === null || value === undefined) return '';
                return String(value)
                    .replace(/\b(cookie|token|secret|password|passwd|authorization|session|api[_-]?key|invite)\s*[:=]\s*[^,\s;]+/ig, '[redacted]')
                    .replace(/Bearer\s+[A-Za-z0-9._~+/=-]+/g, '[redacted]')
                    .slice(0, limit);
            };
            const safeNumberOrNull = (value) => {
                const num = Number(value);
                return Number.isFinite(num) ? num : null;
            };
            const safeObjectCounts = (value, maxKeys = 12) => {
                if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
                return Object.fromEntries(Object.entries(value)
                    .slice(0, maxKeys)
                    .map(([key, count]) => [safeText(key, 80), safeNumberOrNull(count) || 0]));
            };
            const degradation = evidence.degradation && typeof evidence.degradation === 'object'
                ? evidence.degradation
                : {};
            const conditionEvidence = Array.isArray(evidence.condition_evidence)
                ? evidence.condition_evidence
                    .filter((item) => item && typeof item === 'object')
                    .slice(0, 8)
                    .map((item) => ({
                        raw_text: safeText(item.raw_text, 120),
                        field: safeText(item.field, 100),
                        hit_count: safeNumberOrNull(item.hit_count),
                        hit_count_status: safeText(item.hit_count_status || item.status, 80),
                        evidence_level: safeText(item.evidence_level, 80),
                        source_field: safeText(item.source_field, 100),
                        missing_reason: safeText(item.missing_reason, 160),
                        status: safeText(item.status, 80),
                    }))
                : [];
            return {
                schema_version: safeText(evidence.schema_version, 80),
                query: safeText(evidence.query || source.query || source.raw_query, 240),
                result_pool_id: safeText(evidence.result_pool_id || source.result_pool_id, 120),
                summary_status: safeText(evidence.summary_status, 80),
                provider: safeText(evidence.provider, 80),
                provider_status: safeText(evidence.provider_status, 80),
                data_status: safeText(evidence.data_status, 80),
                data_as_of: safeText(evidence.data_as_of, 80),
                cache_status: safeText(evidence.cache_status, 80),
                reported_total: safeNumberOrNull(evidence.reported_total) || 0,
                candidate_count: safeNumberOrNull(evidence.candidate_count) || 0,
                field_coverage_status: safeText(evidence.field_coverage_status, 80),
                condition_status_counts: safeObjectCounts(evidence.condition_status_counts),
                condition_evidence: conditionEvidence,
                candidate_validation: safeObjectCounts(evidence.candidate_validation),
                write_actions_allowed: evidence.write_actions_allowed === true,
                enabled_write_actions: Array.isArray(evidence.enabled_write_actions)
                    ? evidence.enabled_write_actions.map((item) => safeText(item, 80)).filter(Boolean).slice(0, 8)
                    : [],
                blocked_write_actions: Array.isArray(evidence.blocked_write_actions)
                    ? evidence.blocked_write_actions.map((item) => safeText(item, 80)).filter(Boolean).slice(0, 8)
                    : [],
                degradation: {
                    type: safeText(degradation.type, 80),
                    reason: safeText(degradation.reason, 180),
                    next_action: safeText(degradation.next_action, 180),
                    cache_status: safeText(degradation.cache_status, 80),
                    retry_after_seconds: safeText(degradation.retry_after_seconds, 40),
                    local_wait_seconds: safeText(degradation.local_wait_seconds, 40),
                    response_type: safeText(degradation.response_type, 80),
                    schema_signature: safeText(degradation.schema_signature, 160),
                },
            };
        },

        _buildIwencaiEvidenceReviewForPrompt(review) {
            const payload = review && typeof review === 'object' && review.result && typeof review.result === 'object'
                ? review.result
                : review;
            if (!payload || typeof payload !== 'object') {
                return null;
            }
            const safeText = (value, limit = 180) => {
                if (value === null || value === undefined) return '';
                return String(value)
                    .replace(/\b(cookie|token|secret|password|passwd|authorization|session|api[_-]?key|invite)\s*[:=]\s*[^,\s;]+/ig, '[redacted]')
                    .replace(/Bearer\s+[A-Za-z0-9._~+/=-]+/g, '[redacted]')
                    .slice(0, limit);
            };
            const safeNumber = (value) => {
                const num = Number(value);
                return Number.isFinite(num) ? num : 0;
            };
            const safeObjectCounts = (value, maxKeys = 12) => {
                if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
                return Object.fromEntries(Object.entries(value)
                    .slice(0, maxKeys)
                    .map(([key, count]) => [safeText(key, 80), safeNumber(count)]));
            };
            const evidenceStatus = payload.evidence_status && typeof payload.evidence_status === 'object'
                ? payload.evidence_status
                : {};
            const conditionValidation = payload.condition_validation && typeof payload.condition_validation === 'object'
                ? payload.condition_validation
                : {};
            const candidateValidation = payload.candidate_validation && typeof payload.candidate_validation === 'object'
                ? payload.candidate_validation
                : {};
            const degradation = payload.degradation && typeof payload.degradation === 'object'
                ? payload.degradation
                : {};
            const gate = payload.write_action_gate && typeof payload.write_action_gate === 'object'
                ? payload.write_action_gate
                : {};
            return {
                schema_version: safeText(payload.schema_version, 80),
                input_trust: safeText(payload.input_trust, 80),
                review_status: safeText(payload.review_status, 80),
                evidence_status: {
                    present: evidenceStatus.present === true,
                    schema_version: safeText(evidenceStatus.schema_version, 80),
                    summary_status: safeText(evidenceStatus.summary_status, 80),
                    provider: safeText(evidenceStatus.provider, 80),
                    provider_status: safeText(evidenceStatus.provider_status, 80),
                    data_status: safeText(evidenceStatus.data_status, 80),
                    cache_status: safeText(evidenceStatus.cache_status, 80),
                    result_pool_id: safeText(evidenceStatus.result_pool_id, 120),
                    candidate_count: safeNumber(evidenceStatus.candidate_count),
                    reported_total: safeNumber(evidenceStatus.reported_total),
                    field_coverage_status: safeText(evidenceStatus.field_coverage_status, 80),
                },
                condition_status_counts: safeObjectCounts(conditionValidation.status_counts),
                candidate_validation: safeObjectCounts(candidateValidation),
                degradation: {
                    type: safeText(degradation.type, 80),
                    reason: safeText(degradation.reason, 180),
                    next_action: safeText(degradation.next_action, 180),
                    cache_status: safeText(degradation.cache_status, 80),
                    retry_after_seconds: safeText(degradation.retry_after_seconds, 40),
                    response_type: safeText(degradation.response_type, 80),
                    schema_signature: safeText(degradation.schema_signature, 160),
                },
                write_action_gate: {
                    allowed_by_review_tool: gate.allowed_by_review_tool === true,
                    evidence_allows_write_actions: gate.evidence_allows_write_actions === true,
                    requires_separate_tool_and_confirmation: gate.requires_separate_tool_and_confirmation === true,
                    reason: safeText(gate.reason, 120),
                    enabled_write_actions: Array.isArray(gate.enabled_write_actions)
                        ? gate.enabled_write_actions.map((item) => safeText(item, 80)).filter(Boolean).slice(0, 8)
                        : [],
                    blocked_write_actions: Array.isArray(gate.blocked_write_actions)
                        ? gate.blocked_write_actions.map((item) => safeText(item, 80)).filter(Boolean).slice(0, 8)
                        : [],
                },
                recommended_safe_next_actions: Array.isArray(payload.recommended_safe_next_actions)
                    ? payload.recommended_safe_next_actions.map((item) => safeText(item, 180)).filter(Boolean).slice(0, 5)
                    : [],
            };
        },

        async _reviewIwencaiProviderEvidence(sourceContext) {
            const source = sourceContext && typeof sourceContext === 'object' ? sourceContext : {};
            const evidence = this._buildIwencaiProviderEvidenceForReview(source);
            if (!evidence || typeof this.fetchJSON !== 'function') {
                return null;
            }
            try {
                const response = await this.fetchJSON('/api/openclaw/tools/invoke', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        tool: 'quant.iwencai.evidence.review',
                        arguments: {
                            source_context: {
                                source: source.source || 'iwencai',
                                result_pool_id: source.result_pool_id || '',
                                provider_evidence: evidence,
                            },
                        },
                    }),
                    silent: true,
                    timeout: 15000,
                });
                return this._buildIwencaiEvidenceReviewForPrompt(response);
            } catch (error) {
                console.warn('[iWencai] OpenClaw evidence review failed', error);
                return null;
            }
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

            this.on('iwencai:send-to-screener', async ({ pool, query, source_context }) => {
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
                                App.Screener.renderFromPool(codes, query, source_context || null);
                            }
                        }
                    });
                });
            });

            this.on('iwencai:analyze', async ({ query, data, source_context }) => {
                await this.ensureBundle?.('llm');
                const openclawEvidenceReview = await this._reviewIwencaiProviderEvidence(source_context);
                if (typeof App.LLM !== 'undefined') {
                    this.toast('已发送至 AI 助手', 'info');
                    App.LLM.openCopilot();
                    const conditions = Array.isArray(source_context?.parsed_conditions)
                        ? source_context.parsed_conditions
                            .map((item) => item?.raw_text || item?.field)
                            .filter(Boolean)
                            .slice(0, 6)
                        : [];
                    const eventGroup = source_context?.event_group || data?.event_group || null;
                    const eventGroupContext = eventGroup && typeof eventGroup === 'object'
                        ? {
                            stock_code: eventGroup.stock_code || '',
                            stock_name: eventGroup.stock_name || '',
                            event_date: eventGroup.event_date || '',
                            event_count: eventGroup.event_count || 0,
                            raw_count: eventGroup.raw_count || eventGroup.event_count || 0,
                            event_types: Array.isArray(eventGroup.event_types) ? eventGroup.event_types.slice(0, 8) : [],
                            primary_event_id: eventGroup.primary_event_id || '',
                            event_titles: Array.isArray(eventGroup.event_titles) ? eventGroup.event_titles.slice(0, 5) : [],
                            dedupe_policy: eventGroup.dedupe_policy || '',
                            rank_reason: eventGroup.rank_reason || '',
                        }
                        : null;
                    const eventGroupDiagnosis = data?.event_group_diagnosis && typeof data.event_group_diagnosis === 'object'
                        ? {
                            summary: data.event_group_diagnosis.summary || '',
                            counter_evidence: data.event_group_diagnosis.counter_evidence || '',
                            missing_evidence: data.event_group_diagnosis.missing_evidence || '',
                            confidence: data.event_group_diagnosis.confidence || '',
                            signal_direction: data.event_group_diagnosis.signal_direction || '',
                        }
                        : null;
                    const providerEvidence = this._buildIwencaiProviderEvidenceForPrompt(source_context);
                    const contextLine = source_context && typeof source_context === 'object'
                        ? `\n来源上下文：${JSON.stringify({
                            source: source_context.source || 'iwencai',
                            result_pool_id: source_context.result_pool_id || '',
                            selected_bucket: source_context.selected_bucket || '',
                            intent_type: source_context.intent_type || '',
                            parsed_conditions: conditions,
                            condition_hit_count: source_context.condition_hit_count || {},
                            provider_evidence: providerEvidence,
                            openclaw_evidence_review: openclawEvidenceReview,
                            event_group: eventGroupContext,
                            event_group_diagnosis: eventGroupDiagnosis,
                        })}`
                        : '';
                    let msg;
                    if (data && Array.isArray(data.summaryRows) && data.summaryRows.length > 0) {
                        const rows = data.summaryRows.slice(0, 10);
                        msg = `请分析以下问财查询结果：\n查询：${query}${contextLine}\n精简数据：${JSON.stringify(rows)}`;
                    } else {
                        msg = `${query || ''}${contextLine}`;
                    }
                    setTimeout(() => App.LLM.sendQuick(msg), 400);
                }
            });

            const buildBasketCandidates = (items) => {
                const seen = new Set();
                const sanitizeRowEvidence = (evidence) => {
                    if (!evidence || typeof evidence !== 'object') return null;
                    const sourceFields = Array.isArray(evidence.source_fields) ? evidence.source_fields : [];
                    const matchedConditions = Array.isArray(evidence.matched_conditions) ? evidence.matched_conditions : [];
                    const missingConditions = Array.isArray(evidence.missing_conditions) ? evidence.missing_conditions : [];
                    return {
                        result_pool_id: String(evidence.result_pool_id || ''),
                        row_id: String(evidence.row_id || evidence.row_evidence_id || ''),
                        code: String(evidence.code || ''),
                        name: String(evidence.name || ''),
                        rank: Number.isFinite(Number(evidence.rank)) ? Number(evidence.rank) : null,
                        provider: String(evidence.provider || ''),
                        data_as_of: String(evidence.data_as_of || ''),
                        cache_status: String(evidence.cache_status || ''),
                        validation_status: String(evidence.validation_status || evidence.status || ''),
                        evidence_level: String(evidence.evidence_level || ''),
                        matched_conditions: matchedConditions.slice(0, 8),
                        missing_conditions: missingConditions.slice(0, 8),
                        source_fields: sourceFields.slice(0, 12),
                        missing_reason: String(evidence.missing_reason || ''),
                    };
                };
                return (Array.isArray(items) ? items : [])
                    .map((item, index) => {
                        const code = String(item?.code || '').trim();
                        if (!/^\d{6}$/.test(code) || seen.has(code)) return null;
                        seen.add(code);
                        const probability = Number(item?.probability ?? item?.score);
                        const candidate = {
                            code,
                            name: String(item?.name || code).trim(),
                            industry: String(item?.industry || item?.sector || '').trim(),
                        };
                        if (Number.isFinite(probability)) {
                            candidate.probability = probability;
                        } else if (Number.isFinite(Number(item?.rank_score))) {
                            candidate.rank_score = Number(item.rank_score);
                        } else {
                            candidate.rank = index + 1;
                        }
                        const rowEvidence = sanitizeRowEvidence(item?.candidate_provenance || item?.row_evidence || item?.rowEvidence?.raw || item?.source_context?.candidate_provenance);
                        if (rowEvidence) {
                            candidate.candidate_provenance = rowEvidence;
                            candidate.row_evidence_id = rowEvidence.row_id;
                            candidate.row_evidence_status = rowEvidence.validation_status;
                        }
                        return candidate;
                    })
                    .filter(Boolean)
                    .slice(0, 50);
            };

            const ensureBasketDraftBundle = async () => {
                await this.loadScript?.('/static/alpha.js?v=6');
                await this.loadScript?.('/static/alpha-tools.js?v=13');
            };

            const buildBacktestDraft = ({ query, candidates, source_context, backtest_draft }) => {
                const eventGroup = source_context?.event_group || {};
                const sourceContext = {
                    ...(source_context || {}),
                };
                if (query && !sourceContext.query && !sourceContext.raw_query) {
                    sourceContext.query = query;
                }
                const baseConditions = backtest_draft?.conditions && typeof backtest_draft.conditions === 'object'
                    ? backtest_draft.conditions
                    : {
                        hypothesis: eventGroup.stock_name || eventGroup.stock_code
                            ? `${eventGroup.stock_name || eventGroup.stock_code} 事件组需要验证`
                            : `${query || '问财候选池'} 候选池需要验证`,
                        event_date: eventGroup.event_date || '',
                        primary_event_title: eventGroup.primary_event_title || eventGroup.primary_event_id || '',
                        rank_reason: eventGroup.rank_reason || '',
                        candidate_count: candidates.length,
                        entry_rule: '待确认',
                        exit_rule: '待确认',
                        holding_periods: [1, 3, 5],
                        benchmark: '沪深300',
                    };
                return {
                    ...(backtest_draft || {}),
                    draft_type: String(backtest_draft?.draft_type || (eventGroup.stock_code ? 'event_group_backtest_draft' : 'iwencai_basket_backtest_draft')),
                    status: 'draft',
                    requires_confirmation: true,
                    execution_policy: 'manual_only',
                    execution_status: 'not_executed',
                    allowed_actions: ['view', 'edit', 'run_backtest_after_confirmation'],
                    conditions: baseConditions,
                    source_context: {
                        ...sourceContext,
                        ...(backtest_draft?.source_context || {}),
                    },
                };
            };

            const openResearchBasketDraft = async ({ query, candidates, source_context, draftMode, backtest_draft }) => {
                const normalized = buildBasketCandidates(candidates);
                const sourceLabel = source_context?.event_group ? '事件组' : '问财候选';
                if (!normalized.length) {
                    this.toast(`${sourceLabel}候选池为空，未生成篮子草案`, 'warning');
                    return;
                }
                await ensureBasketDraftBundle();
                await this.switchTab('research', { subtab: 'basket', skipBundle: true, applySession: false });
                const normalizedDraft = draftMode === 'backtest'
                    ? buildBacktestDraft({ query, candidates: normalized, source_context, backtest_draft })
                    : (backtest_draft ? buildBacktestDraft({ query, candidates: normalized, source_context, backtest_draft }) : null);
                const applyBasketDraft = () => {
                    if (typeof App.initAlpha === 'function') {
                        App.initAlpha();
                    }
                    if (typeof App._setBasketCandidates === 'function') {
                        App._setBasketCandidates(normalized);
                    }
                    const textarea = document.getElementById('basket-candidates');
                    if (textarea) {
                        textarea.dataset.sourceContext = JSON.stringify(source_context || {});
                        textarea.dataset.sourceQuery = query || '';
                        if (normalizedDraft) {
                            textarea.dataset.backtestDraft = JSON.stringify(normalizedDraft);
                        } else {
                            delete textarea.dataset.backtestDraft;
                        }
                    }
                    this._iwencaiBasketDraft = {
                        query: query || '',
                        candidates: normalized,
                        source_context: source_context || null,
                        backtest_draft: normalizedDraft,
                        draftMode: draftMode || 'basket',
                        created_at: new Date().toISOString(),
                    };
                    if (typeof App.renderBasketBacktestDraft === 'function') {
                        App.renderBasketBacktestDraft(normalizedDraft);
                    }
                    return Boolean(document.getElementById('basket-backtest-draft'));
                };
                const applied = applyBasketDraft();
                requestAnimationFrame(() => {
                    if (!applied || !document.getElementById('basket-candidates')?.dataset?.backtestDraft) {
                        applyBasketDraft();
                    }
                    const message = draftMode === 'backtest'
                        ? `已生成 ${normalized.length} 只${sourceLabel}的回测草案，请在篮子页确认参数后手动执行计划回测`
                        : `已生成 ${normalized.length} 只${sourceLabel}的篮子草案`;
                    this.toast(message, normalized.length ? 'success' : 'warning');
                });
            };

            this.on('iwencai:create-basket', async ({ query, candidates, source_context, backtest_draft }) => {
                await openResearchBasketDraft({ query, candidates, source_context, backtest_draft, draftMode: 'basket' });
            });

            this.on('iwencai:draft-backtest', async ({ query, candidates, source_context, backtest_draft }) => {
                await openResearchBasketDraft({ query, candidates, source_context, backtest_draft, draftMode: 'backtest' });
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

            await this._onResearchSubTabActivate(activeSubtab, options);
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

        async _onResearchSubTabActivate(subtab, options = {}) {
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

            const skipBundle = options.skipBundle === true;

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
                if (!skipBundle) {
                    await this.ensureBundle?.('research');
                }
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
                if (options.skipBundle !== true) {
                    await this.ensureBundle?.('research');
                    this.bindBacktest?.();
                    this.bindOptimize?.();
                    this.bindSensitivity?.();
                    this.bindStrategyChips?.();
                }
                this._initResearchSubTabs();
                const requestedSubtab = typeof options.subtab === 'string' ? options.subtab.trim() : '';
                const domActiveSubtab = document.querySelector('.research-sub-tab.active')?.dataset?.subtab || '';
                const activeResearchSubtab = requestedSubtab || this._researchActiveSubtab || domActiveSubtab || 'valuation';
                await this._activateResearchSubTab(activeResearchSubtab, {
                    skipBundle: options.skipBundle === true,
                    applySession: options.applySession,
                });
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
                window.dispatchEvent?.(new Event('aiq:intelligence-tab-active'));
            }

            requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
        },
    });
})(window);
