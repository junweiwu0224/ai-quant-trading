/* ── 研发页：数据中枢与决策矩阵 ── */
(function () {
    'use strict';

    const DataHub = {
        _inited: false,
        _searchBox: null,
        _selected: [],
        _items: [],

        init() {
            if (this._inited) {
                this.load();
                return;
            }
            this._inited = true;
            this._bindSearch();
            this._bindEvents();
            this._syncCodeRow();
            this.load();
        },

        _bindSearch() {
            const input = document.getElementById('datahub-code-input');
            const dropdown = document.getElementById('datahub-code-dropdown');
            if (!input || !dropdown || typeof SearchBox === 'undefined') return;

            this._searchBox = new SearchBox('datahub-code-input', 'datahub-code-dropdown', {
                maxResults: 40,
                minQueryLength: 1,
                emptyScope: 'watchlist',
                idleMessage: '自选股为空，输入代码或名称搜索全市场',
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
            this._searchBox.onSelect((item) => this._addCode(item));
        },

        _bindEvents() {
            document.getElementById('datahub-refresh-btn')?.addEventListener('click', () => this.load({ force: true }));
            document.getElementById('datahub-scope')?.addEventListener('change', () => {
                this._syncCodeRow();
                this._renderScopeNote();
                this.load({ force: true });
            });
            document.getElementById('datahub-add-code-btn')?.addEventListener('click', () => {
                const input = document.getElementById('datahub-code-input');
                const code = input?.value?.trim();
                if (code) this._addCode({ code });
            });
            document.getElementById('datahub-code-tags')?.addEventListener('click', (event) => {
                const btn = event.target.closest('[data-datahub-remove-code]');
                if (!btn) return;
                const code = btn.dataset.datahubRemoveCode;
                this._selected = this._selected.filter((item) => item.code !== code);
                this._renderTags();
                this.load({ force: true });
            });
            document.getElementById('datahub-matrix-table')?.addEventListener('click', (event) => {
                const emptyAction = event.target.closest('[data-datahub-empty-action]');
                if (emptyAction) {
                    event.preventDefault();
                    this._applyEmptyAction(emptyAction.dataset.datahubEmptyAction);
                    return;
                }
                const btn = event.target.closest('[data-datahub-action]');
                if (!btn) return;
                event.preventDefault();
                const code = btn.dataset.code;
                if (!code) return;
                const action = btn.dataset.datahubAction;
                if (action === 'stock') {
                    App.openStockDetail(code, { source: 'datahub:open-stock' });
                } else if (action === 'watchlist') {
                    App.addToWatchlist(code, { source: 'datahub:add-watchlist' });
                } else if (action === 'paper') {
                    App.openPaperBuy(code, { source: 'datahub:paper-buy' });
                } else if (action === 'valuation') {
                    this._openValuation(code);
                } else if (action === 'ask') {
                    this._askOpenClaw(code);
                }
            });
        },

        _applyEmptyAction(action) {
            const scope = document.getElementById('datahub-scope');
            if (action === 'signal') {
                if (scope) scope.value = 'signal';
                this._syncCodeRow();
                this._renderScopeNote();
                this.load({ force: true });
                return;
            }
            if (action === 'codes') {
                if (scope) scope.value = 'codes';
                this._syncCodeRow();
                this._renderScopeNote();
                requestAnimationFrame(() => document.getElementById('datahub-code-input')?.focus());
            }
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
            const scope = document.getElementById('datahub-scope');
            if (scope) scope.value = 'codes';
            const input = document.getElementById('datahub-code-input');
            if (input) input.value = '';
            this._syncCodeRow();
            this._renderScopeNote();
            this._renderTags();
            this.load({ force: true });
        },

        _syncCodeRow() {
            const scope = document.getElementById('datahub-scope')?.value || 'watchlist';
            const row = document.getElementById('datahub-code-row');
            if (row) row.classList.toggle('hidden', scope !== 'codes');
            this._renderScopeNote();
        },

        _renderTags() {
            const tags = document.getElementById('datahub-code-tags');
            if (!tags) return;
            tags.innerHTML = this._selected.map((item) => {
                const label = item.name ? `${item.code} ${item.name}` : item.code;
                return `<span class="sb-tag">${App.escapeHTML(label)}<span class="sb-tag-remove" data-datahub-remove-code="${App.escapeHTML(item.code)}">&times;</span></span>`;
            }).join('');
        },

        async load() {
            const tbody = document.querySelector('#datahub-matrix-table tbody');
            if (!tbody) return;
            const scope = this._normalizeScope(document.getElementById('datahub-scope')?.value || 'watchlist');
            const codes = this._selected.map((item) => item.code).join(',');
            const requestKey = this._matrixRequestKey(scope, codes);
            const hasPreviousItems = Array.isArray(this._items)
                && this._items.length > 0
                && this._matrixResultKey === requestKey;
            if (hasPreviousItems) {
                this._renderTransientNote('正在刷新，保留上次结果');
                this._renderTrust({
                    trust_state: 'refreshing',
                    trust_text: '正在刷新数据矩阵，当前表格保留上次结果。',
                });
            } else {
                tbody.innerHTML = '<tr><td colspan="10" class="text-muted text-center">加载中...</td></tr>';
                this._renderTrust({
                    trust_state: 'loading',
                    trust_text: '正在拉取行情、估值和 AI 信号数据。',
                });
            }

            if (scope === 'watchlist') {
                await this._refreshWatchlistCache();
                if (!this._hasWatchlistItems()) {
                    this._items = [];
                    this._matrixResultKey = requestKey;
                    this._renderEmptyWatchlist();
                    return;
                }
            }
            const requestId = this._beginMatrixRequest(scope, requestKey);
            this._renderScopeNote();

            try {
                if (scope === 'codes' && !codes) {
                    this._items = [];
                    this._matrixResultKey = requestKey;
                    this._render([], {});
                    return;
                }
                const fastQuery = this._buildMatrixQuery(scope, codes, { fast: true });
                let data;
                try {
                    data = await App.fetchJSON(`/api/datahub/decision-matrix?${fastQuery.toString()}`, { silent: true, timeout: 8000 });
                } catch (fastError) {
                    if (!this._isCurrentMatrixRequest(scope, requestId)) return;
                    if (!hasPreviousItems) {
                        tbody.innerHTML = '<tr><td colspan="10" class="text-muted text-center">快速预览超时，完整估值补载中...</td></tr>';
                    }
                    this._renderTransientNote(hasPreviousItems ? '快速预览超时，完整估值补载中；保留上次结果' : '快速预览超时，完整估值补载中');
                    try {
                        data = await this._loadFullMatrix(scope, codes, requestId);
                    } catch (fullError) {
                        data = await this._loadFallbackMatrix(scope, codes, requestId, fullError, hasPreviousItems);
                    }
                }
                if (!data || !this._isCurrentMatrixRequest(scope, requestId)) return;
                this._items = data.items || [];
                this._matrixResultKey = requestKey;
                this._render(this._items, data.summary || {});
            } catch (error) {
                this._renderLoadFailure(error, hasPreviousItems);
            }
        },

        async _loadFullMatrix(scope, codes, requestId) {
            const query = this._buildMatrixQuery(scope, codes, { fast: false });
            const data = await App.fetchJSON(`/api/datahub/decision-matrix?${query.toString()}`, { silent: true, timeout: 20000 });
            return this._isCurrentMatrixRequest(scope, requestId) ? data : null;
        },

        async _loadFallbackMatrix(scope, codes, requestId, error, hasPreviousItems = false) {
            const query = this._buildMatrixQuery(scope, codes, { fast: true, forceFallback: true });
            try {
                const data = await App.fetchJSON(`/api/datahub/decision-matrix?${query.toString()}`, { silent: true, timeout: 8000 });
                if (!this._isCurrentMatrixRequest(scope, requestId)) return null;
                const summary = data.summary || {};
                data.summary = {
                    ...summary,
                    used_fallback: true,
                    fallback_reason: summary.fallback_reason || 'client_timeout_default',
                    fallback_error: error?.message || '',
                };
                if (hasPreviousItems) {
                    this._renderLoadFailure(error, true, { attemptedFallback: true });
                    return null;
                }
                return data;
            } catch (fallbackError) {
                if (!this._isCurrentMatrixRequest(scope, requestId)) return null;
                this._renderLoadFailure(error || fallbackError, hasPreviousItems, { attemptedFallback: true });
                return null;
            }
        },

        _buildMatrixQuery(scope, codes = '', { fast = true, forceFallback = false } = {}) {
            const query = new URLSearchParams({ scope, limit: scope === 'signal' ? '50' : '30' });
            if (scope === 'codes') query.set('codes', codes);
            if (fast) {
                query.set('fast', 'true');
            } else {
                query.set('max_wait_sec', '6');
            }
            if (forceFallback) {
                query.set('force_fallback', 'true');
            }
            return query;
        },

        _beginMatrixRequest(scope, requestKey = null) {
            const requestId = (this._matrixRequestId || 0) + 1;
            this._matrixRequestId = requestId;
            this._matrixActiveScope = scope;
            this._matrixActiveKey = requestKey || this._matrixRequestKey(scope);
            return requestId;
        },

        _isCurrentMatrixRequest(scope, requestId) {
            return this._matrixActiveScope === scope && this._matrixRequestId === requestId;
        },

        _matrixRequestKey(scope, codes = '') {
            const normalized = this._normalizeScope(scope || 'watchlist');
            const normalizedCodes = normalized === 'codes'
                ? String(codes || '').split(',').map((code) => code.trim()).filter(Boolean).join(',')
                : '';
            return `${normalized}|${normalizedCodes}`;
        },

        async _refreshWatchlistCache() {
            try {
                const watchlist = await App.fetchJSON('/api/watchlist', { silent: true, timeout: 15000 });
                if (Array.isArray(watchlist)) {
                    App.watchlistCache = watchlist;
                }
            } catch {
                // Keep the last known cache; the matrix API is still authoritative.
            }
        },

        _hasWatchlistItems() {
            return Array.isArray(App.watchlistCache) && App.watchlistCache.length > 0;
        },

        _renderEmptyWatchlist() {
            const summary = {
                total: 0,
                trust_state: 'empty',
                trust_title: '等待自选',
                trust_text: '自选股为空，当前没有使用默认候选；添加自选股，或切到 AI 信号 Top / 指定股票继续研究。',
            };
            this._renderStats(summary, []);
            this._renderTrust(summary);
            const note = document.getElementById('datahub-scope-note');
            if (note) {
                note.innerHTML = [
                    '<span class="coverage-pill">自选股为空</span>',
                    '<span class="coverage-pill">没有使用默认候选</span>',
                    '<span class="coverage-pill">可切到 AI 信号 Top 或指定股票</span>',
                ].join('');
            }
            const tbody = document.querySelector('#datahub-matrix-table tbody');
            if (tbody) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="10">
                            <div class="datahub-empty-state">
                                <strong>自选股为空</strong>
                                <span>没有使用默认候选。先添加自选股，或切到 AI 信号 Top / 指定股票查看候选。</span>
                                <div class="datahub-empty-actions">
                                    <button class="btn btn-sm" data-datahub-empty-action="signal">看 AI 信号 Top</button>
                                    <button class="btn btn-sm" data-datahub-empty-action="codes">指定股票</button>
                                </div>
                            </div>
                        </td>
                    </tr>
                `;
            }
        },

        _renderTransientNote(message) {
            const note = document.getElementById('datahub-scope-note');
            if (!note) return;
            note.innerHTML = `<span class="coverage-pill">${App.escapeHTML(message)}</span>`;
        },

        _renderLoadFailure(error, hasPreviousItems = false, options = {}) {
            const tbody = document.querySelector('#datahub-matrix-table tbody');
            const note = document.getElementById('datahub-scope-note');
            const message = App.escapeHTML(error?.message || '未知错误');
            if (hasPreviousItems) {
                if (note) {
                    const state = options.attemptedFallback ? '刷新超时' : '刷新失败';
                    note.innerHTML = `<span class="coverage-pill">${state}</span><span class="coverage-pill">保留上次结果</span><span class="coverage-pill">${message}</span>`;
                }
                this._renderTrust({
                    trust_state: 'stale',
                    trust_title: options.attemptedFallback ? '刷新超时' : '刷新失败',
                    trust_text: '已保留上次数据矩阵；建议稍后刷新，或缩小范围后重试。',
                });
                return;
            }
            if (tbody) {
                tbody.innerHTML = `<tr><td colspan="10" class="text-muted text-center">加载失败：${message}</td></tr>`;
            }
            if (note) {
                note.innerHTML = `<span class="coverage-pill">加载失败</span><span class="coverage-pill">${message}</span>`;
            }
            this._renderTrust({
                trust_state: 'failed',
                trust_title: '加载失败',
                trust_text: `本次请求失败：${message}；可以重新刷新或切换范围。`,
            });
        },

        _render(items, summary) {
            this._renderStats(summary, items);
            this._renderTrust(summary);
            const trustInfo = this._trustState(summary);
            const lowTrust = this._isLowTrust(trustInfo);
            const tbody = document.querySelector('#datahub-matrix-table tbody');
            if (!tbody) return;
            if (!items.length) {
                tbody.innerHTML = '<tr><td colspan="10" class="text-muted text-center">暂无数据，请加入自选股或切到 AI 信号 Top</td></tr>';
                this._renderTrust({
                    ...summary,
                    trust_state: 'empty',
                    trust_title: '等待数据',
                    trust_text: '当前范围暂无矩阵数据；可以加入自选股、指定股票或切到 AI 信号 Top。',
                });
                return;
            }

            tbody.innerHTML = items.map((item) => {
                const score = Number(item.decision_score || 0);
                const scoreCls = score >= 78 ? 'score-hot' : score >= 62 ? 'score-warm' : score >= 45 ? 'score-neutral' : 'score-cold';
                const reasons = item.reason_tags || [];
                const risks = item.risk_tags || [];
                const riskGroups = this._riskTagGroups(risks);
                const riskCls = item.risk_level === '高' ? 'risk-high' : item.risk_level === '中' ? 'risk-mid' : 'risk-low';
                const nextActions = this._safeNextActions(item.next_actions || [], lowTrust);
                const stockMeta = this._stockMetaLine(item);
                const paperButton = lowTrust
                    ? ''
                    : `<button class="btn btn-xs" data-datahub-action="paper" data-code="${App.escapeHTML(item.code)}">模拟</button>`;
                return `<tr>
                    <td>${item.matrix_rank || '--'}</td>
                    <td>
                        <button class="link-button datahub-stock-link" data-datahub-action="stock" data-code="${App.escapeHTML(item.code)}">${App.escapeHTML(item.name || item.code)}</button>
                        ${stockMeta ? `<div class="datahub-stock-meta">${App.escapeHTML(stockMeta)}</div>` : ''}
                        <div class="datahub-evidence-tags">${reasons.slice(0, 3).map((tag) => `<span class="datahub-reason-tag">${App.escapeHTML(tag)}</span>`).join('')}</div>
                    </td>
                    <td><span class="datahub-score ${scoreCls}">${score}</span><span class="datahub-decision-label">${App.escapeHTML(item.decision_label || '--')}</span></td>
                    <td>${this._fmtPeg(item.peg_next_year)}</td>
                    <td class="${this._numClass(item.growth_next_year_pct)}">${this._fmtPct(item.growth_next_year_pct)}</td>
                    <td class="${this._numClass(item.upside_pct)}">${this._fmtPct(item.upside_pct)}</td>
                    <td>${this._fmtQlib(item)}</td>
                    <td>
                        <span class="datahub-risk-pill ${riskCls}">${App.escapeHTML(item.risk_level || '--')}</span>
                        <div>${this._renderRiskTags(riskGroups)}</div>
                    </td>
                    <td>${this._renderNextActions(nextActions)}</td>
                    <td class="datahub-actions">
                        <button class="btn btn-xs" data-datahub-action="valuation" data-code="${App.escapeHTML(item.code)}">估值</button>
                        <button class="btn btn-xs" data-datahub-action="watchlist" data-code="${App.escapeHTML(item.code)}">自选</button>
                        ${paperButton}
                        <button class="btn btn-xs" data-datahub-action="ask" data-code="${App.escapeHTML(item.code)}">问龙虾</button>
                    </td>
                </tr>`;
            }).join('');
        },

        _renderStats(summary, items) {
            const set = (id, value) => {
                const el = document.getElementById(id);
                if (el) el.textContent = value;
            };
            set('datahub-total', String(summary.total ?? items.length ?? 0));
            set('datahub-high-score', String(summary.high_score ?? 0));
            set('datahub-cheap', String(summary.peg_le_1 ?? 0));
            set('datahub-qlib-top', String(summary.signal_top_50 ?? summary.qlib_top_50 ?? 0));
            set('datahub-valuation-cov', summary.valuation_coverage_pct == null ? '--' : `${summary.valuation_coverage_pct}%`);
            const signalCoverage = summary.signal_coverage_pct ?? summary.qlib_coverage_pct;
            set('datahub-qlib-cov', signalCoverage == null ? '--' : `${signalCoverage}%`);
            set('datahub-actionable', String(summary.actionable ?? 0));
            set('datahub-high-risk', String(summary.high_risk ?? 0));
            set('datahub-pipe-quote', `${items.length || 0} 只`);
            set('datahub-pipe-valuation', summary.valuation_error ? '估值降级' : (summary.valuation_coverage_pct == null ? '--' : `${summary.valuation_coverage_pct}% 覆盖`));
            const signalAge = summary.signal_cache_age_label || summary.qlib_cache_age_label;
            const ageLabel = signalAge ? ` · ${signalAge}` : '';
            const validationLabel = this._signalQualityLabel(summary);
            set('datahub-pipe-ai', summary.signal_date ? `${summary.signal_date}${ageLabel}${validationLabel}` : '未生成');
            const shadow = summary.shadow || {};
            set('datahub-pipe-shadow', shadow.total_checks ? `${shadow.total_diffs || 0} 条差异 · ${shadow.codes_with_diffs || 0} 只股票` : '暂无差异日志');
            const sourceHealth = summary.source_health || {};
            const qualitySummary = summary.quality_summary || {};
            const activeSources = sourceHealth.total_active_sources != null ? `${sourceHealth.total_active_sources} 个在线` : '--';
            const qualityCount = qualitySummary.total != null ? `${qualitySummary.total} 条` : '--';
            const shadowCount = shadow.total_checks != null ? `${shadow.total_checks} 次` : '--';
            const latestVersion = this._latestSourceVersion(sourceHealth);
            set('datahub-source-health', activeSources);
            set('datahub-quality-summary', qualityCount);
            set('datahub-shadow-summary', shadowCount);
            set('datahub-version-summary', latestVersion);
            this._renderScopeNote(summary, items);
        },

        _signalQualityLabel(summary = {}) {
            const quality = summary.signal_quality || {};
            if (quality.label) {
                const sample = Number.isFinite(Number(quality.sample_days)) ? ` · 样本 ${Number(quality.sample_days)} 天` : '';
                const penalty = quality.penalty_applied ? ' · 已降权' : '';
                return ` · ${quality.label}${sample}${penalty}`;
            }
            const validation = summary.signal_validation || {};
            const labelMap = {
                validated_positive: '验证偏正',
                validated_neutral: '验证中性',
                validated_weak: '验证偏弱',
                unverified: '未验证',
            };
            return validation.confidence ? ` · ${labelMap[validation.confidence] || validation.confidence}` : '';
        },

        _renderScopeNote(summary = {}, items = this._items || []) {
            const note = document.getElementById('datahub-scope-note');
            if (!note) return;
            const scope = this._normalizeScope(document.getElementById('datahub-scope')?.value || 'watchlist');
            const labels = { watchlist: '自选股', signal: 'AI 信号 Top', qlib: 'AI 信号 Top', codes: '指定股票' };
            const desc = {
                watchlist: '当前账号自选，不代表全市场',
                signal: 'AI 信号候选池，未验证信号已降权',
                qlib: 'AI 信号候选池，未验证信号已降权',
                codes: '手动指定股票，逐只拉取数据',
            };
            const total = summary.total ?? items.length ?? 0;
            const watchlistCount = scope === 'watchlist' && Array.isArray(App.watchlistCache)
                ? App.watchlistCache.length
                : null;
            const valuation = summary.valuation_coverage_pct == null ? '--' : `${summary.valuation_coverage_pct}%`;
            const qlib = (summary.signal_coverage_pct ?? summary.qlib_coverage_pct) == null ? '--' : `${summary.signal_coverage_pct ?? summary.qlib_coverage_pct}%`;
            const signalQuality = summary.signal_quality || {};
            const signalBits = [`AI信号覆盖 ${qlib}`];
            if (signalQuality.label) signalBits.push(String(signalQuality.label));
            if (signalQuality.penalty_applied) signalBits.push('已降权');
            const isFallback = Boolean(summary.used_fallback);
            const fallbackLabel = this._fallbackLabel(summary.fallback_reason);
            const scopeLabel = labels[scope] || scope;
            const sampleLabel = isFallback ? `样本来源 ${fallbackLabel}` : `范围 ${scopeLabel}`;
            const scopeContext = isFallback ? `请求范围 ${scopeLabel}` : (desc[scope] || '当前筛选范围');
            const fallbackPill = isFallback
                ? `<span class="coverage-pill">${summary.fallback_reason === 'client_timeout_default' ? '刷新超时 · 默认候选降级预览' : fallbackLabel}</span>`
                : '';
            note.innerHTML = [
                fallbackPill,
                `<span class="coverage-pill">${App.escapeHTML(sampleLabel)}</span>`,
                `<span class="coverage-pill">${App.escapeHTML(scopeContext)}</span>`,
                `<span class="coverage-pill">${watchlistCount == null ? '' : `自选 ${App.escapeHTML(String(watchlistCount))} 只 · `}样本 ${App.escapeHTML(String(total))} 只</span>`,
                `<span class="coverage-pill">估值 ${App.escapeHTML(valuation)} · ${App.escapeHTML(signalBits.join(' · '))}</span>`,
            ].filter(Boolean).join('');
        },

        _trustState(summary = {}) {
            if (summary.trust_state) {
                return {
                    state: summary.trust_state,
                    title: summary.trust_title,
                    text: summary.trust_text,
                };
            }
            if (summary.used_fallback) {
                const reason = String(summary.fallback_reason || '');
                const title = reason === 'client_timeout_default' ? '降级预览' : '默认候选';
                const textByReason = {
                    client_timeout_default: '请求超时后切到默认候选降级预览，先刷新或缩小范围确认真实矩阵。',
                    watchlist_empty: '自选股为空，当前展示默认候选预览，不是自选结果；先添加自选股或切到 AI 信号 Top。',
                    signal_empty: 'AI 信号池为空，当前展示默认候选预览，不是信号筛选结果；先刷新信号或指定股票。',
                    forced_default: '当前强制使用默认候选预览，仅用于应急观察；先刷新真实矩阵再纳入研究。',
                };
                return {
                    state: 'fallback',
                    title,
                    text: textByReason[reason] || '当前来自默认候选降级预览，先刷新或缩小范围确认真实矩阵。',
                };
            }
            const signalStatus = summary.signal_status || summary.qlib_status || '';
            const signalQuality = summary.signal_quality || {};
            const valuationCoverage = Number(summary.valuation_coverage_pct);
            const sampleDays = Number(signalQuality.sample_days);
            const reviewReasons = [];
            if (!Number.isFinite(valuationCoverage) || valuationCoverage < 50) reviewReasons.push('估值覆盖不足');
            if (/未验证|unverified/i.test(String(signalQuality.label || ''))) reviewReasons.push('信号未验证');
            if (signalQuality.penalty_applied) reviewReasons.push('已降权');
            if (Number.isFinite(sampleDays) && sampleDays <= 0) reviewReasons.push('样本不足');
            if (signalStatus === 'offline' || signalStatus === 'empty') reviewReasons.push('AI信号离线');
            if (reviewReasons.length) {
                return {
                    state: 'review',
                    title: '需复核',
                    text: `矩阵已返回，但${reviewReasons.slice(0, 3).join('、')}；先补齐估值或验证信号后再纳入研究。`,
                };
            }
            const quality = signalQuality.label ? ` · ${signalQuality.label}` : '';
            return {
                state: 'real',
                title: '真实合成',
                text: `行情、估值和 AI 信号已完成合成${quality}，可进入估值或模拟盘复核。`,
            };
        },

        _renderTrust(summary = {}) {
            const panel = document.getElementById('datahub-trust');
            if (!panel) return;
            const info = this._trustState(summary);
            const state = info.state || 'loading';
            const title = info.title || {
                loading: '正在加载',
                refreshing: '正在刷新',
                empty: '等待数据',
                stale: '保留旧结果',
                failed: '加载失败',
                real: '真实合成',
                fallback: '降级预览',
                review: '需复核',
            }[state] || '状态未知';
            const text = info.text || '数据矩阵会标明真实合成、需复核或降级预览状态。';
            const trustClass = {
                real: 'trust-real',
                fallback: 'trust-fallback',
                review: 'trust-review',
                stale: 'trust-stale',
                failed: 'trust-failed',
                empty: 'trust-empty',
                refreshing: 'trust-loading',
                loading: 'trust-loading',
            }[state] || 'trust-loading';
            panel.className = `opportunity-trust-panel ${trustClass}`;
            panel.innerHTML = `
                <span class="opportunity-trust-badge">${App.escapeHTML(title)}</span>
                <span class="opportunity-trust-text">${App.escapeHTML(text)}</span>
            `;
        },

        _isLowTrust(info = {}) {
            return ['fallback', 'review', 'stale', 'failed', 'empty', 'loading', 'refreshing'].includes(info.state || '');
        },

        _safeNextActions(actions, lowTrust = false) {
            const list = Array.isArray(actions) ? actions : [];
            if (!lowTrust) return list;
            return list.filter((action) => !/模拟|交易|小仓|买入|卖出/.test(String(action || '')));
        },

        _fallbackLabel(reason) {
            const labels = {
                client_timeout_default: '默认候选',
                forced_default: '默认候选',
                watchlist_empty: '默认候选',
                signal_empty: '默认候选',
            };
            return labels[String(reason || '')] || '默认候选';
        },

        async _openValuation(code) {
            await App.switchTab('research');
            document.querySelector('.research-sub-tab[data-subtab="valuation"]')?.click();
            requestAnimationFrame(() => {
                globalThis.ResearchValuation?.addCode?.({ code });
            });
        },

        async _askOpenClaw(code) {
            const item = this._items.find((stock) => stock.code === code) || { code };
            const signalTrust = this._openClawSignalTrustLine(item);
            const riskLine = Array.isArray(item.risk_tags) && item.risk_tags.length
                ? `显式风险：${item.risk_tags.join('、')}。`
                : '显式风险：暂无明显风险。';
            const prompt = [
                `请基于数据中枢帮我分析 ${item.name || code}(${code})。`,
                `决策评分：${item.decision_score ?? '--'}，标签：${item.decision_label || '--'}。`,
                `PEG：${this._fmtNum(item.peg_next_year, 2)}，明年增速：${this._fmtPct(item.growth_next_year_pct)}，目标空间：${this._fmtPct(item.upside_pct)}。`,
                `AI信号：${item.signal_rank || item.qlib_rank ? `排名 ${item.signal_rank || item.qlib_rank}，分数 ${this._fmtNum(item.signal_score ?? item.qlib_score, 3)}，来源 ${item.signal_provider || 'local_momentum'}` : '暂无覆盖'}。`,
                signalTrust,
                riskLine,
                '请给我一个适合模拟盘的观察结论、风险点和下一步动作；仅供观察，不要给实盘下单建议。',
            ].join('\n');
            await App.switchTab('openclaw');
            await globalThis.OpenClawWorkbench?.maybeInitForTab?.('openclaw');
            await globalThis.OpenClawWorkbench?.send?.(prompt);
        },

        _openClawSignalTrustLine(item = {}) {
            const provider = this._sourceLabel(item.signal_provider || item.qlib_provider || 'local_momentum') || '未知来源';
            const rank = item.signal_rank || item.qlib_rank;
            const confidence = item.signal_confidence || item.qlib_confidence || item.signal_quality?.confidence || 'unverified';
            const label = item.signal_quality?.label || this._signalConfidenceLabel(confidence) || '未验证';
            const sampleDays = Number(item.signal_quality?.sample_days ?? item.signal_sample_days);
            const sample = Number.isFinite(sampleDays) ? `样本 ${sampleDays} 天` : '样本未知';
            const penalty = item.signal_quality?.penalty_applied || /AI未验证|AI未覆盖/.test((item.risk_tags || []).join('、'));
            const status = rank ? `AI${label}` : 'AI未覆盖';
            const action = penalty ? '已降权，仅供观察' : '按正常权重参与评分';
            return `信号可信度：${status}，${sample}，来源 ${provider}，${action}。`;
        },

        _fmtNum(value, digits = 2) {
            return this._hasNumber(value) ? Number(value).toFixed(digits) : '--';
        },

        _fmtPct(value) {
            return this._hasNumber(value) ? `${Number(value).toFixed(2)}%` : '--';
        },

        _numClass(value) {
            if (!this._hasNumber(value)) return '';
            const num = Number(value);
            return num > 0 ? 'text-up' : num < 0 ? 'text-down' : 'text-muted';
        },

        _hasNumber(value) {
            if (value === null || value === undefined || value === '' || value === '-' || value === '--') return false;
            return Number.isFinite(Number(value));
        },

        _fmtPeg(value) {
            if (!this._hasNumber(value) || Number(value) <= 0) {
                return '<span class="datahub-missing-badge">缺失</span>';
            }
            return App.escapeHTML(Number(value).toFixed(2));
        },

        _fmtQlib(item) {
            const rank = item.signal_rank || item.qlib_rank;
            if (!rank) {
                return '<span class="datahub-missing-badge">未覆盖</span>';
            }
            const score = this._fmtNum(item.signal_score ?? item.qlib_score, 3);
            const confidence = item.signal_confidence || 'unverified';
            const labels = {
                validated_positive: '验证偏正',
                validated_neutral: '验证中性',
                validated_weak: '验证偏弱',
                unverified: '未验证',
            };
            const label = labels[confidence] || '未验证';
            const diamond = confidence === 'validated_positive' ? '<span class="datahub-diamond">验证偏正</span>' : '';
            const provider = this._sourceLabel(item.signal_provider || 'local_momentum');
            return `${diamond}<span class="datahub-qlib-rank">#${App.escapeHTML(rank)} · ${App.escapeHTML(score)}</span><div class="text-muted text-xs">${App.escapeHTML(provider)} · ${App.escapeHTML(label)}</div>`;
        },

        _sourceLabel(value) {
            const key = String(value || '').trim();
            const labels = {
                local_stock_daily: '本地日线',
                local_stock_daily_coverage_pool: '本地日线',
                local_derived: '本地推导',
                local_momentum: '本地动量信号',
                astock: '研报估值',
                research_report: '研报估值',
                market_news_multi_source: '市场新闻聚合',
                eastmoney: '东方财富',
                ths: '同花顺',
                tushare: 'Tushare',
                signal_engine: 'Signal Engine',
                legacy_qlib: 'Qlib兼容',
                qlib: 'Qlib兼容',
            };
            return labels[key] || key;
        },

        _signalConfidenceLabel(value) {
            const labels = {
                validated_positive: '验证偏正',
                validated_neutral: '验证中性',
                validated_weak: '验证偏弱',
                unverified: '未验证',
            };
            const key = String(value || '').trim();
            return labels[key] || key;
        },

        _qualityStatusLabel(value) {
            const labels = {
                ok: '',
                stale: '质量 滞后',
                degraded: '质量 降级',
                unavailable: '质量 不可用',
                error: '质量 异常',
            };
            const key = String(value || '').trim();
            return labels[key] ?? (key ? `质量 ${key}` : '');
        },

        _valuationSourceLabel(item = {}) {
            const source = String(item.valuation_source || item.source || item.report_source || '').trim();
            const reportCount = Number(item.report_count);
            if (source === 'astock' || source === 'research_report') {
                return Number.isFinite(reportCount) && reportCount <= 0 ? '研报缺失' : '研报估值';
            }
            if (source === 'local_derived' || source === 'stock_daily+signal+momentum') {
                return '本地推导';
            }
            return this._sourceLabel(source);
        },

        _normalizeScope(scope) {
            return scope === 'qlib' ? 'signal' : scope;
        },

        _riskTagGroups(risks) {
            const hidden = new Set(['PEG缺失']);
            const dataGaps = new Set(['AI未覆盖', 'AI未验证', '无研报预测', '增速缺失', '目标价缺失', '行情缓存偏旧', '数据源超时']);
            return (Array.isArray(risks) ? risks : []).reduce((groups, tag) => {
                if (hidden.has(tag)) return groups;
                if (dataGaps.has(tag)) {
                    groups.dataGaps.push(tag);
                } else {
                    groups.marketRisks.push(tag);
                }
                return groups;
            }, { dataGaps: [], marketRisks: [] });
        },

        _renderRiskTags(groups = {}) {
            const marketRisks = Array.isArray(groups.marketRisks) ? groups.marketRisks.slice(0, 3) : [];
            const dataGaps = Array.isArray(groups.dataGaps) ? groups.dataGaps.slice(0, 2) : [];
            const riskHtml = marketRisks
                .map((tag) => `<span class="datahub-risk-tag">${App.escapeHTML(tag)}</span>`)
                .join('');
            const gapHtml = dataGaps
                .map((tag) => `<span class="datahub-data-gap-tag">${App.escapeHTML(tag)}</span>`)
                .join('');
            return riskHtml || gapHtml
                ? `${riskHtml}${gapHtml}`
                : '<span class="text-muted text-xs">暂无明显风险</span>';
        },

        _actionIntentClass(action) {
            const text = String(action || '');
            if (/问龙虾|研究|重点池/.test(text)) return 'action-research';
            if (/模拟|交易|小仓|买入|卖出/.test(text)) return 'action-trade';
            if (/观察|跟踪|自选|监控|等待/.test(text)) return 'action-watch';
            if (/补|核对|查|估值详情|同业估值|PEG|目标价|缺失数据/.test(text)) return 'action-data';
            if (/暂缓|保留/.test(text)) return 'action-hold';
            return 'action-watch';
        },

        _renderNextActions(actions) {
            const list = Array.isArray(actions) ? actions.slice(0, 4) : [];
            if (!list.length) return '<span class="text-muted">--</span>';
            return list.map((action) => {
                const cls = this._actionIntentClass(action);
                return `<span class="datahub-action-tag ${cls}">${App.escapeHTML(action)}</span>`;
            }).join('');
        },

        _stockMetaLine(item) {
            const code = String(item.code || '').trim();
            const industry = String(item.industry || '')
                .trim()
                .replace(/^制造业[-·\s]*/, '')
                .replace(/制造业$/, '')
                .trim();
            const quoteSource = this._sourceLabel(item.quote_source || item.price_source || item.market_source);
            const quoteDate = String(item.quote_date || item.trade_date || '').trim();
            const valuationSource = this._valuationSourceLabel(item);
            const confidence = this._signalConfidenceLabel(item.signal_confidence || item.qlib_confidence);
            const quality = this._qualityStatusLabel(item.quality_status);
            const quoteMeta = quoteSource || quoteDate
                ? `行情 ${[quoteSource, quoteDate].filter(Boolean).join(' ')}`
                : '';
            const valuationMeta = valuationSource ? `估值 ${valuationSource}` : '';
            const signalMeta = confidence ? `AI ${confidence}` : '';
            return [
                code,
                industry,
                quoteMeta,
                valuationMeta,
                signalMeta,
                quality,
            ].filter(Boolean).join(' · ');
        },

        _latestSourceVersion(sourceHealth) {
            if (!sourceHealth || !sourceHealth.sources) return '--';
            const entries = Object.entries(sourceHealth.sources);
            if (!entries.length) return '--';
            const versions = entries.flatMap(([, info]) => {
                const active = info.active_versions || [];
                const latest = info.latest_version ? [info.latest_version] : [];
                return [...latest, ...active].filter(Boolean);
            });
            return versions.length ? versions[0] : '--';
        },
    };

    globalThis.ResearchDataHub = DataHub;
})();
