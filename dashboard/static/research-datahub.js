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
            tbody.innerHTML = '<tr><td colspan="10" class="text-muted text-center">加载中...</td></tr>';

            const scope = this._normalizeScope(document.getElementById('datahub-scope')?.value || 'watchlist');
            if (scope === 'watchlist') {
                await this._refreshWatchlistCache();
            }
            const codes = this._selected.map((item) => item.code).join(',');
            const query = new URLSearchParams({ scope, limit: scope === 'signal' ? '50' : '30' });
            if (scope === 'codes') query.set('codes', codes);
            this._renderScopeNote();

            try {
                if (scope === 'codes' && !codes) {
                    this._items = [];
                    this._render([], {});
                    return;
                }
                const data = await App.fetchJSON(`/api/datahub/decision-matrix?${query.toString()}`, { silent: true, timeout: 60000 });
                this._items = data.items || [];
                this._render(this._items, data.summary || {});
            } catch (error) {
                tbody.innerHTML = `<tr><td colspan="10" class="text-muted text-center">加载失败：${App.escapeHTML(error.message || '未知错误')}</td></tr>`;
            }
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

        _render(items, summary) {
            this._renderStats(summary, items);
            const tbody = document.querySelector('#datahub-matrix-table tbody');
            if (!tbody) return;
            if (!items.length) {
                tbody.innerHTML = '<tr><td colspan="10" class="text-muted text-center">暂无数据，请加入自选股或切到 AI 信号 Top</td></tr>';
                return;
            }

            tbody.innerHTML = items.map((item) => {
                const score = Number(item.decision_score || 0);
                const scoreCls = score >= 78 ? 'score-hot' : score >= 62 ? 'score-warm' : score >= 45 ? 'score-neutral' : 'score-cold';
                const reasons = item.reason_tags || [];
                const risks = item.risk_tags || [];
                const displayRisks = this._displayRiskTags(risks);
                const riskCls = item.risk_level === '高' ? 'risk-high' : item.risk_level === '中' ? 'risk-mid' : 'risk-low';
                const nextActions = item.next_actions || [];
                const stockMeta = this._stockMetaLine(item);
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
                        <div>${displayRisks.slice(0, 3).map((tag) => `<span class="datahub-risk-tag">${App.escapeHTML(tag)}</span>`).join('') || '<span class="text-muted text-xs">暂无明显风险</span>'}</div>
                    </td>
                    <td>${nextActions.slice(0, 3).map((tag) => `<span class="datahub-next-tag">${App.escapeHTML(tag)}</span>`).join('') || '<span class="text-muted">--</span>'}</td>
                    <td class="datahub-actions">
                        <button class="btn btn-xs" data-datahub-action="valuation" data-code="${App.escapeHTML(item.code)}">估值</button>
                        <button class="btn btn-xs" data-datahub-action="watchlist" data-code="${App.escapeHTML(item.code)}">自选</button>
                        <button class="btn btn-xs" data-datahub-action="paper" data-code="${App.escapeHTML(item.code)}">模拟</button>
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
            note.innerHTML = [
                `<span class="coverage-pill">范围 ${App.escapeHTML(labels[scope] || scope)}</span>`,
                `<span class="coverage-pill">${App.escapeHTML(desc[scope] || '当前筛选范围')}</span>`,
                `<span class="coverage-pill">${watchlistCount == null ? '' : `自选 ${App.escapeHTML(String(watchlistCount))} 只 · `}样本 ${App.escapeHTML(String(total))} 只</span>`,
                `<span class="coverage-pill">估值 ${App.escapeHTML(valuation)} · ${App.escapeHTML(signalBits.join(' · '))}</span>`,
            ].join('');
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
            const prompt = [
                `请基于数据中枢帮我分析 ${item.name || code}(${code})。`,
                `决策评分：${item.decision_score ?? '--'}，标签：${item.decision_label || '--'}。`,
                `PEG：${this._fmtNum(item.peg_next_year, 2)}，明年增速：${this._fmtPct(item.growth_next_year_pct)}，目标空间：${this._fmtPct(item.upside_pct)}。`,
                `AI信号：${item.signal_rank || item.qlib_rank ? `排名 ${item.signal_rank || item.qlib_rank}，分数 ${this._fmtNum(item.signal_score ?? item.qlib_score, 3)}，来源 ${item.signal_provider || 'local_momentum'}` : '暂无覆盖'}。`,
                '请给我一个适合模拟盘的观察结论、风险点和下一步动作。',
            ].join('\n');
            await App.switchTab('openclaw');
            await globalThis.OpenClawWorkbench?.maybeInitForTab?.('openclaw');
            await globalThis.OpenClawWorkbench?.send?.(prompt);
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
            const label = confidence.startsWith('validated') ? '已验证' : '未验证';
            const diamond = confidence.startsWith('validated') ? '<span class="datahub-diamond">已验证</span>' : '';
            return `${diamond}<span class="datahub-qlib-rank">#${App.escapeHTML(rank)} · ${App.escapeHTML(score)}</span><div class="text-muted text-xs">${App.escapeHTML(item.signal_provider || 'local_momentum')} · ${App.escapeHTML(label)}</div>`;
        },

        _normalizeScope(scope) {
            return scope === 'qlib' ? 'signal' : scope;
        },

        _displayRiskTags(risks) {
            const technicalMissing = new Set(['PEG缺失', 'AI未覆盖']);
            return (Array.isArray(risks) ? risks : []).filter((tag) => !technicalMissing.has(tag));
        },

        _stockMetaLine(item) {
            const code = String(item.code || '').trim();
            const industry = String(item.industry || '')
                .trim()
                .replace(/^制造业[-·\s]*/, '')
                .replace(/制造业$/, '')
                .trim();
            return [code, industry].filter(Boolean).join(' · ');
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
