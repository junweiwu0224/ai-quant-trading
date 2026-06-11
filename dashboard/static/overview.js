/* ── 总览模块 ── */

Object.assign(App, {
    _overviewLoaded: false,
    _overviewOpportunityScope: 'signal',

    async loadOverview() {
        if (this._loadingOverview) return;
        const currentHash = typeof location?.hash === 'string' ? location.hash : '';
        if (currentHash && currentHash !== '#overview') {
            return;
        }
        this._loadingOverview = true;
        this._setTabTitle?.('overview');
        const refreshBtn = this._getLegacyActionButton ? this._getLegacyActionButton('overview-refresh') : null;
        if (refreshBtn) refreshBtn.disabled = true;
        const loadStartTime = Date.now();

        // 首次加载显示骨架屏
        if (!this._overviewLoaded) {
            this._showOverviewSkeletons();
        }

        try {
            const so = { silent: true };

            // 阶段 1：核心数据。自选股先独立返回，用于尽早启动机会池。
            const snapshotPromise = this.fetchJSON('/api/portfolio/snapshot', so).catch(() => ({ total_equity: 0, cash: 0, market_value: 0, positions: [] }));
            const tradesPromise = this.fetchJSON('/api/portfolio/trades/recent?limit=20', so).catch(() => []);
            const statusPromise = this.fetchJSON('/api/system/status', so).catch(() => ({ db_stats: {}, paper_running: false, ai_model: '--' }));
            const watchlistPromise = this.fetchJSON('/api/watchlist', so).catch(() => []);
            watchlistPromise.then((watchlist) => {
                this.watchlistCache = watchlist || [];
                Watchlist.render(watchlist);
                Watchlist.setSelectedItems(watchlist || []);
                this._buildWatchlistIndex();
                this._loadOverviewOpportunities();
            }).catch(() => {});

            const [snapshot, trades, status, watchlist] = await Promise.all([
                snapshotPromise,
                tradesPromise,
                statusPromise,
                watchlistPromise,
            ]);

            const dbStats = status.db_stats || {};

            // 核心指标卡片
            document.getElementById('ov-equity').textContent = this.fmt(snapshot.total_equity);
            this._renderMetric('ov-daily-pnl', snapshot.daily_pnl, snapshot.daily_pnl_pct, true);
            this._renderPctMetric('ov-cum-return', snapshot.cumulative_return);
            this._renderPctMetric('ov-max-dd', snapshot.max_drawdown, true);
            const sharpeEl = document.getElementById('ov-sharpe');
            const sharpeVal = snapshot.sharpe_ratio;
            sharpeEl.textContent = sharpeVal?.toFixed(2) ?? '--';
            if (sharpeVal != null) {
                sharpeEl.className = 'stat-value ' + (sharpeVal >= 1 ? 'text-up' : sharpeVal >= 0 ? 'stat-value-warn' : 'text-down');
            }
            document.getElementById('ov-position-count').textContent = snapshot.positions?.length ?? 0;

            ['ov-equity', 'ov-daily-pnl', 'ov-cum-return', 'ov-max-dd', 'ov-sharpe', 'ov-position-count'].forEach(id => {
                document.getElementById(id)?.classList.remove('skeleton-text');
            });

            // 系统状态
            document.getElementById('ov-stock-count').textContent = dbStats.stock_count || 0;
            document.getElementById('ov-latest-date').textContent = dbStats.latest_date || '无数据';
            ['ov-stock-count', 'ov-latest-date', 'ov-paper-status', 'ov-ai-status'].forEach(id => {
                document.getElementById(id)?.classList.remove('skeleton-text');
            });
            const paperEl = document.getElementById('ov-paper-status');
            if (paperEl) paperEl.textContent = status.paper_running ? '运行中' : '已停止';
            const aiEl = document.getElementById('ov-ai-status');
            if (aiEl) aiEl.textContent = status.ai_model || '--';

            // AI 信号心跳检查（异步，不阻塞）
            this._checkSignalHealth();
            this._loadDataHubHealth();

            this._updateQuoteStatus();
            this._updateMarketPhase();
            this._registerOverviewTimers();

            // 自选股兜底：如果早启动链路被环境拦截，这里仍保持渲染和机会池加载。
            if (this.watchlistCache !== watchlist) {
                this.watchlistCache = watchlist || [];
                Watchlist.render(watchlist);
                Watchlist.setSelectedItems(watchlist || []);
                this._buildWatchlistIndex();
                this._loadOverviewOpportunities();
            }

            // 持仓明细
            this._renderPositions(snapshot);

            // 最近交易（仅显示前5条）
            const tradesBody = document.querySelector('#ov-trades-table tbody');
            if (tradesBody && trades.length > 0) {
                tradesBody.innerHTML = trades.slice(0, 5).map(t => `
                    <tr><td>${Utils.formatBeijingTime(t.time)}</td><td><a href="#" class="stock-link" data-code="${this.escapeHTML(t.code)}">${this.escapeHTML(t.code)} ${this.escapeHTML(t.name || '')}</a></td><td class="${(t.direction === 'long' || t.direction === 'buy') ? 'text-up' : 'text-down'}">${(t.direction === 'long' || t.direction === 'buy') ? '买入' : '卖出'}</td><td>¥${this.escapeHTML(t.price)}</td><td>${this.escapeHTML(t.volume)}</td></tr>
                `).join('');
            } else if (tradesBody) {
                tradesBody.innerHTML = '<tr><td colspan="5" class="text-muted">暂无交易数据</td></tr>';
            }

            // 阶段 2：次要数据（图表 + 市场，不阻塞首屏）
            this._loadOverviewSecondary(so).catch((e) => {
                console.warn('总览次要数据加载失败:', e);
                this._clearOverviewSecondarySkeletons();
            });

            // 数据新鲜度指示
            this._overviewDataTime = loadStartTime;
            this._updateDataFreshness();
            this._bindOverviewOpportunityActions();
        } catch (e) {
            ['ov-equity', 'ov-daily-pnl', 'ov-cum-return', 'ov-max-dd', 'ov-sharpe', 'ov-position-count'].forEach(id => {
                const el = document.getElementById(id);
                if (el) { el.textContent = '--'; el.classList.remove('skeleton-text'); }
            });
            this.toast('总览数据加载失败: ' + e.message, 'error');
        } finally {
            this._loadingOverview = false;
            this._overviewLoaded = true;
            if (refreshBtn) refreshBtn.disabled = false;
        }
    },

    /** 阶段 2：图表 + 市场数据（异步加载，不阻塞首屏） */
    async _loadOverviewSecondary(so) {
        const [equityHistory, indices, hotSectors] = await Promise.all([
            this.fetchJSON('/api/portfolio/equity-history', so).catch(() => []),
            this.fetchJSON('/api/stock/market/indices', so).catch(() => []),
            this.fetchJSON('/api/stock/market/hot-sectors', so).catch(() => ({ industries: [], concepts: [] })),
        ]);

        this._overviewChartData = equityHistory;

        this._clearOverviewSecondarySkeletons();
        try { this.renderEquityChart(equityHistory); } catch (e) { console.warn('收益图表渲染失败:', e); }
        try { this.renderMarketIndices(indices); } catch (e) { console.warn('指数渲染失败:', e); }
        try { this.renderHotSectors(hotSectors); } catch (e) { console.warn('热门板块渲染失败:', e); }
    },

    _bindOverviewOpportunityActions() {
        const table = document.getElementById('ov-opportunity-table');
        if (table && table.dataset.bound !== '1') {
            table.dataset.bound = '1';
            table.addEventListener('click', async (event) => {
                const btn = event.target.closest('[data-ov-opportunity-action]');
                if (!btn) return;
                event.preventDefault();
                const code = btn.dataset.code;
                if (!code) return;
                const action = btn.dataset.ovOpportunityAction;
                if (action === 'stock') {
                    App.openStockDetail(code, { source: 'overview:opportunity' });
                } else if (action === 'watchlist') {
                    App.addToWatchlist(code, { source: 'overview:opportunity' });
                } else if (action === 'ask') {
                    await this._askOpportunityOpenClaw(code);
                }
            });
        }
        const trust = document.getElementById('ov-opportunity-trust');
        if (trust && trust.dataset.bound !== '1') {
            trust.dataset.bound = '1';
            trust.addEventListener('click', async (event) => {
                const refreshBtn = event.target.closest('[data-ov-opportunity-refresh]');
                if (!refreshBtn) return;
                event.preventDefault();
                refreshBtn.disabled = true;
                try {
                    await this._loadOverviewOpportunities();
                } finally {
                    refreshBtn.disabled = false;
                }
            });
        }
        const toggle = document.querySelector('.opportunity-scope-toggle');
        if (!toggle || toggle.dataset.bound === '1') return;
        toggle.dataset.bound = '1';
        toggle.addEventListener('click', (event) => {
            const btn = event.target.closest('[data-ov-opportunity-scope]');
            if (!btn) return;
            event.preventDefault();
            this._setOverviewOpportunityScope(btn.dataset.ovOpportunityScope || 'watchlist');
        });
    },

    async _loadOverviewOpportunities() {
        const tbody = document.querySelector('#ov-opportunity-table tbody');
        if (!tbody) return;
        const scope = this._resolveOverviewOpportunityScope();
        const requestKey = this._overviewOpportunityRequestKey(scope);
        const hasPreviousItems = Array.isArray(this._overviewOpportunityItems)
            && this._overviewOpportunityItems.length > 0
            && this._overviewOpportunityResultKey === requestKey;
        if (!hasPreviousItems) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-muted text-center">加载中...</td></tr>';
        }
        const hint = document.getElementById('ov-opportunity-hint');
        if (hint) hint.textContent = 'PEG、机构预测、AI 信号与风险标签合成的优先研究清单。';
        const status = document.getElementById('ov-opportunity-status');
        if (status) {
            status.innerHTML = hasPreviousItems
                ? '<span class="opportunity-status-item">正在刷新</span><span class="opportunity-status-item">保留上次结果</span>'
                : '<span class="opportunity-status-item">正在加载</span>';
        }
        this._renderOverviewOpportunityTrust({
            state: hasPreviousItems ? 'refreshing' : 'loading',
            text: hasPreviousItems ? '正在刷新机会池，当前表格保留上次结果。' : '正在拉取机会池数据。',
        });
        try {
            const requestId = this._beginOverviewOpportunityRequest(scope, requestKey);
            this._updateOverviewOpportunityScopeButtons(scope);
            if (scope === 'watchlist' && !(this.watchlistCache || []).length) {
                this._renderOverviewOpportunityEmptyWatchlist();
                return;
            }
            const fastQuery = this._buildOverviewOpportunityQuery(scope, { fast: true });
            let fastData;
            try {
                fastData = await this.fetchJSON(`/api/datahub/decision-matrix?${fastQuery.toString()}`, { silent: true, timeout: 8000 });
            } catch (fastError) {
                if (!this._isCurrentOverviewOpportunityRequest(scope, requestId)) return;
                if (status) status.innerHTML = '<span class="opportunity-status-item">快速预览超时</span><span class="opportunity-status-item">完整估值补载中</span>';
                try {
                    await this._loadOverviewOpportunitiesFull(scope, requestId);
                } catch (fullError) {
                    await this._loadOverviewOpportunitiesFallback(scope, requestId, fullError, hasPreviousItems);
                }
                return;
            }
            if (!this._isCurrentOverviewOpportunityRequest(scope, requestId)) return;
            const fastItems = (fastData.items || []).slice(0, 5);
            if (!fastItems.length) {
                tbody.innerHTML = '<tr><td colspan="7" class="text-muted text-center">暂无候选，先加入自选或生成 AI 信号缓存</td></tr>';
                this._renderOverviewOpportunityStatus(fastData.summary || {}, 0, true);
                return;
            }
            this._renderOverviewOpportunityData(fastData, true, { scope, requestId });
            this._loadOverviewOpportunitiesFull(scope, requestId).catch((fullError) => {
                this._markOverviewOpportunityFullBackfillFailure(fullError, scope, requestId);
            });
        } catch (error) {
            this._renderOverviewOpportunityLoadFailure(error, hasPreviousItems);
        }
    },

    _renderOverviewOpportunityLoadFailure(error, hasPreviousItems = false, options = {}) {
        const tbody = document.querySelector('#ov-opportunity-table tbody');
        const status = document.getElementById('ov-opportunity-status');
        const hint = document.getElementById('ov-opportunity-hint');
        const message = this.escapeHTML(error?.message || '未知错误');
        if (hasPreviousItems) {
            if (status) {
                const state = options.attemptedFallback ? '刷新超时' : '刷新失败';
                status.innerHTML = `<span class="opportunity-status-item">${state}</span><span class="opportunity-status-item">保留上次结果</span>`;
            }
            if (hint) hint.textContent = `本次刷新失败：${message}；已保留上次机会池结果。`;
            this._renderOverviewOpportunityTrust({
                state: 'stale',
                title: options.attemptedFallback ? '刷新超时' : '刷新失败',
                text: '已保留上次机会池结果；建议稍后刷新，或打开完整矩阵复核。',
            });
            return;
        }
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-muted text-center">机会池加载失败：${message}</td></tr>`;
        }
        if (status) status.innerHTML = '<span class="opportunity-status-item">加载失败</span>';
        this._renderOverviewOpportunityTrust({
            state: 'failed',
            title: '加载失败',
            text: `本次请求失败：${message}；可以重新刷新或打开完整矩阵查看数据源状态。`,
        });
    },

    async _loadOverviewOpportunitiesFull(scope, requestId) {
        const query = this._buildOverviewOpportunityQuery(scope, { fast: false });
        const data = await this.fetchJSON(`/api/datahub/decision-matrix?${query.toString()}`, { silent: true, timeout: 20000 });
        this._renderOverviewOpportunityData(data, false, { scope, requestId });
    },

    _markOverviewOpportunityFullBackfillFailure(error, scope, requestId) {
        if (!this._isCurrentOverviewOpportunityRequest(scope, requestId)) return;
        const status = document.getElementById('ov-opportunity-status');
        const hint = document.getElementById('ov-opportunity-hint');
        const message = this.escapeHTML(error?.message || '未知错误');
        if (status) {
            const current = status.innerHTML || '';
            status.innerHTML = [
                current,
                '<span class="opportunity-status-item">完整估值补载失败</span>',
                '<span class="opportunity-status-item">保留快速预览</span>',
            ].filter(Boolean).join('');
        }
        if (hint) {
            hint.textContent = `完整估值补载失败：${message}；当前保留快速预览，建议刷新或打开完整矩阵复核。`;
        }
        this._renderOverviewOpportunityTrust({
            state: 'review',
            title: '需复核',
            text: `完整估值补载失败，当前保留快速预览；错误：${message}。`,
        });
    },

    async _loadOverviewOpportunitiesFallback(scope, requestId, error, hasPreviousItems = false) {
        const query = this._buildOverviewOpportunityQuery(scope, { fast: true, forceFallback: true });
        try {
            const data = await this.fetchJSON(`/api/datahub/decision-matrix?${query.toString()}`, { silent: true, timeout: 8000 });
            if (!this._isCurrentOverviewOpportunityRequest(scope, requestId)) return;
            const summary = data.summary || {};
            data.summary = {
                ...summary,
                used_fallback: true,
                fallback_reason: summary.fallback_reason || 'client_timeout_default',
                fallback_error: error?.message || '',
            };
            if (hasPreviousItems) {
                this._renderOverviewOpportunityLoadFailure(error, true, { attemptedFallback: true });
                return;
            }
            this._renderOverviewOpportunityData(data, true, { scope, requestId });
        } catch (fallbackError) {
            if (!this._isCurrentOverviewOpportunityRequest(scope, requestId)) return;
            if (hasPreviousItems) {
                this._renderOverviewOpportunityLoadFailure(error || fallbackError, true, { attemptedFallback: true });
                return;
            }
            this._renderOverviewOpportunityLocalEmergency(error || fallbackError, { scope, requestId });
        }
    },

    _beginOverviewOpportunityRequest(scope, requestKey = null) {
        const nextId = (this._overviewOpportunityRequestId || 0) + 1;
        this._overviewOpportunityRequestId = nextId;
        this._overviewOpportunityActiveScope = scope;
        this._overviewOpportunityActiveKey = requestKey || this._overviewOpportunityRequestKey(scope);
        return nextId;
    },

    _isCurrentOverviewOpportunityRequest(scope, requestId) {
        return this._overviewOpportunityActiveScope === scope
            && this._overviewOpportunityScope === scope
            && this._overviewOpportunityRequestId === requestId;
    },

    _buildOverviewOpportunityQuery(scope = 'watchlist', { fast = true, forceFallback = false } = {}) {
        const normalizedScope = scope === 'qlib' ? 'signal' : scope;
        const requestedScope = ['watchlist', 'signal'].includes(normalizedScope) ? normalizedScope : 'signal';
        const query = new URLSearchParams();
        query.set('scope', requestedScope);
        query.set('limit', '8');
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

    _overviewOpportunityRequestKey(scope = this._resolveOverviewOpportunityScope()) {
        return ['watchlist', 'signal'].includes(scope) ? scope : 'signal';
    },

    _resolveOverviewOpportunityScope() {
        const current = this._overviewOpportunityScope || 'signal';
        if (current === 'qlib') return 'signal';
        return ['watchlist', 'signal'].includes(current) ? current : 'signal';
    },

    _setOverviewOpportunityScope(scope) {
        const normalizedScope = scope === 'qlib' ? 'signal' : scope;
        const nextScope = ['watchlist', 'signal'].includes(normalizedScope) ? normalizedScope : 'signal';
        if (nextScope === this._overviewOpportunityScope && this._overviewOpportunityItems?.length) {
            return;
        }
        this._overviewOpportunityScope = nextScope;
        this._updateOverviewOpportunityScopeButtons(nextScope);
        this._loadOverviewOpportunities();
    },

    _updateOverviewOpportunityScopeButtons(scope) {
        document.querySelectorAll('[data-ov-opportunity-scope]').forEach((btn) => {
            const active = btn.dataset.ovOpportunityScope === scope;
            btn.classList.toggle('active', active);
            btn.setAttribute?.('aria-pressed', active ? 'true' : 'false');
        });
    },

    _renderOverviewOpportunityEmptyWatchlist() {
        const tbody = document.querySelector('#ov-opportunity-table tbody');
        const hint = document.getElementById('ov-opportunity-hint');
        if (tbody) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-muted text-center">请先添加股票到自选</td></tr>';
        }
        if (hint) {
            hint.textContent = '自选为空；添加股票后这里会显示你的专属机会池。';
        }
        this._overviewOpportunityItems = [];
        this._renderOverviewOpportunityStatus({
            total: 0,
            valuation_coverage_pct: null,
            qlib_coverage_pct: null,
            qlib_status: 'online',
            fast_mode: true,
        }, 0, true);
        this._renderOverviewOpportunityTrust({
            state: 'empty',
            title: '等待自选',
            text: '自选为空；添加股票后会生成专属机会池。',
        });
    },

    _overviewOpportunityLocalEmergencyItems() {
        return [
            {
                matrix_rank: 1,
                code: '510300',
                name: '沪深300ETF',
                industry: '宽基ETF',
                decision_score: 52,
                decision_label: '本地应急',
                peg_next_year: null,
                risk_level: '中',
                reason_tags: ['本地应急', '宽基分散'],
                risk_tags: ['数据源超时'],
                next_actions: ['稍后刷新', '加入自选跟踪', '问龙虾复核'],
            },
            {
                matrix_rank: 2,
                code: '510500',
                name: '中证500ETF',
                industry: '宽基ETF',
                decision_score: 49,
                decision_label: '本地应急',
                peg_next_year: null,
                risk_level: '中',
                reason_tags: ['本地应急', '中盘覆盖'],
                risk_tags: ['数据源超时'],
                next_actions: ['稍后刷新', '观察量能'],
            },
            {
                matrix_rank: 3,
                code: '159915',
                name: '创业板ETF',
                industry: '宽基ETF',
                decision_score: 46,
                decision_label: '本地应急',
                peg_next_year: null,
                risk_level: '中',
                reason_tags: ['本地应急', '成长风格'],
                risk_tags: ['波动较高', '数据源超时'],
                next_actions: ['稍后刷新', '等待真实数据恢复'],
            },
        ];
    },

    _renderOverviewOpportunityLocalEmergency(error, requestMeta = null) {
        if (requestMeta && !this._isCurrentOverviewOpportunityRequest(requestMeta.scope, requestMeta.requestId)) {
            return;
        }
        const hint = document.getElementById('ov-opportunity-hint');
        const items = this._overviewOpportunityLocalEmergencyItems();
        this._renderOverviewOpportunityData({
            items,
            summary: {
                total: items.length,
                used_fallback: true,
                local_emergency: true,
                fallback_reason: 'local_emergency',
                fallback_error: error?.message || '',
                valuation_coverage_pct: null,
                signal_coverage_pct: null,
                signal_status: 'offline',
                signal_quality: { label: '未验证', sample_days: 0, penalty_applied: true },
                fast_mode: true,
            },
        }, true, requestMeta);
        if (hint) {
            hint.textContent = `数据源请求超时，当前展示本地应急机会池；不代表真实信号，稍后刷新会自动恢复。`;
        }
    },

    _renderOverviewOpportunityData(data, isFast, requestMeta = null) {
        if (requestMeta && !this._isCurrentOverviewOpportunityRequest(requestMeta.scope, requestMeta.requestId)) {
            return;
        }
        const tbody = document.querySelector('#ov-opportunity-table tbody');
        const hint = document.getElementById('ov-opportunity-hint');
        if (!tbody) return;
        const items = data.items || [];
        if (!items.length) return;
        this._overviewOpportunityItems = items;
        if (requestMeta) {
            this._overviewOpportunityResultKey = data.summary?.local_emergency
                ? 'local-emergency'
                : this._overviewOpportunityRequestKey(requestMeta.scope);
        }
        tbody.innerHTML = items.map((item) => this._renderOpportunityRow(item)).join('');
        this._renderOverviewOpportunityStatus(data.summary || {}, items.length, isFast);
        this._renderOverviewOpportunityTrust(this._overviewOpportunityTrustState(data.summary || {}, isFast));
        if (hint) {
            if (data.summary?.local_emergency) {
                hint.textContent = '数据源请求超时，当前展示本地应急机会池；不代表真实信号，稍后刷新会自动恢复。';
            } else if (data.summary?.used_fallback) {
                if (data.summary?.fallback_reason === 'client_timeout_default') {
                    hint.textContent = '数据源刷新超时，当前展示默认候选降级预览；稍后刷新会自动恢复真实范围。';
                    return;
                }
                hint.textContent = isFast
                    ? '当前使用默认候选快速预览；完整估值正在后台补齐。'
                    : '当前使用默认候选；加入自选股或生成 AI 信号缓存后会自动切换。';
            } else if (isFast) {
                hint.textContent = '快速预览已加载，PEG 和机构预测正在后台补齐。';
            } else {
                hint.textContent = 'PEG、机构预测、AI 信号与风险标签合成的优先研究清单。';
            }
        }
    },

    _renderOverviewOpportunityStatus(summary = {}, itemCount = 0, isFast = false) {
        const status = document.getElementById('ov-opportunity-status');
        if (!status) return;
        const qlibStatusMap = { fresh: '在线', online: '在线', stale: '过期', offline: '离线', empty: '离线' };
        const total = summary.total ?? itemCount;
        const valuation = this._fmtOverviewPct(summary.valuation_coverage_pct);
        const qlibCoverage = this._fmtOverviewPct(summary.signal_coverage_pct ?? summary.qlib_coverage_pct);
        const qlibStatus = qlibStatusMap[summary.signal_status || summary.qlib_status] || summary.signal_status || summary.qlib_status || '未知';
        const scopeLabel = summary.local_emergency ? '本地应急' : summary.used_fallback ? '默认候选' : this._overviewOpportunityScopeLabel(this._overviewOpportunityScope);
        const cacheAge = (summary.signal_cache_age_label || summary.qlib_cache_age_label) ? ` · ${this.escapeHTML(summary.signal_cache_age_label || summary.qlib_cache_age_label)}` : '';
        const signalQuality = this._formatOverviewSignalQuality(summary);
        const mode = isFast || summary.fast_mode ? '快速预览' : '完整估值';
        const syncStatus = this._formatOverviewQlibSyncStatus(summary.signal_sync_status || summary.qlib_sync_status);
        const trustItems = this._formatOverviewOpportunityStatusTrustItems(summary);
        const items = [
            `候选 ${this.escapeHTML(total)} 只`,
            `范围 ${this.escapeHTML(scopeLabel)}`,
            `估值 ${this.escapeHTML(valuation)}`,
            `AI信号 ${this.escapeHTML(qlibStatus)}${cacheAge}`,
            `信号覆盖 ${this.escapeHTML(qlibCoverage)}`,
            signalQuality,
            mode,
            ...trustItems,
        ];
        if (syncStatus) items.splice(5, 0, syncStatus);
        status.innerHTML = items.map((text) => `<span class="opportunity-status-item">${text}</span>`).join('');
    },

    _formatOverviewOpportunityStatusTrustItems(summary = {}) {
        const items = [];
        const source = summary.source || summary.provider || summary.signal_provider || summary.qlib_provider;
        if (source) {
            items.push(`来源 ${this._overviewSignalSourceLabel(source)}`);
        }
        const updatedAt = summary.generated_at || summary.timestamp || summary.updated_at || summary.finished_at;
        if (updatedAt) {
            items.push(`更新 ${updatedAt}`);
        }
        const effectiveRaw = summary.effective_count ?? summary.valid_count ?? summary.covered_count;
        const totalRaw = summary.total_count ?? summary.stock_count ?? summary.universe_count;
        const effective = Number(effectiveRaw);
        const total = Number(totalRaw);
        if (Number.isFinite(effective) && Number.isFinite(total) && total > 0) {
            items.push(`有效 ${Math.round(effective).toLocaleString('zh-CN')}/${Math.round(total).toLocaleString('zh-CN')}`);
        } else if (Number.isFinite(effective) && effective >= 0) {
            items.push(`有效 ${Math.round(effective).toLocaleString('zh-CN')}`);
        }
        const universe = String(summary.universe || '').trim();
        const coverageNote = String(summary.coverage_note || '').trim();
        if (
            summary.partial === true ||
            summary.full_market === false ||
            /非全量|not\s*full|partial/i.test(coverageNote) ||
            (universe && !/all[_-]?a|full/i.test(universe))
        ) {
            items.push('非全量');
        }
        if (summary.source_unavailable) {
            items.push('数据源异常');
        }
        if (summary.stale) {
            items.push('缓存数据');
        }
        if (summary.stale_reason) {
            items.push(`原因 ${summary.stale_reason}`);
        }
        if (coverageNote) {
            items.push(coverageNote);
        }
        return items.map((item) => this.escapeHTML(item));
    },

    _overviewOpportunityTrustState(summary = {}, isFast = false) {
        if (summary.local_emergency) {
            return {
                state: 'emergency',
                title: '本地应急',
                text: '本地应急不可作为真实信号；仅用于页面不断链，先刷新或打开完整矩阵复核。',
            };
        }
        if (summary.used_fallback) {
            return {
                state: 'fallback',
                title: summary.fallback_reason === 'client_timeout_default' ? '降级预览' : '默认候选',
                text: '当前来自默认候选降级预览，先刷新或打开完整矩阵确认真实范围。',
            };
        }
        const signalStatus = summary.signal_status || summary.qlib_status || '';
        const signalQuality = summary.signal_quality || {};
        const quality = signalQuality.label ? ` · ${signalQuality.label}` : '';
        const mode = isFast || summary.fast_mode ? '快速预览' : '完整估值';
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
                text: `${mode}已返回，但${reviewReasons.slice(0, 3).join('、')}；先打开完整矩阵确认后再纳入研究。`,
            };
        }
        return {
            state: 'real',
            title: '真实合成',
            text: `${mode}已基于估值、AI信号和风险标签合成${quality}，可进入研发复核。`,
        };
    },

    _renderOverviewOpportunityTrust(info = {}) {
        const panel = document.getElementById('ov-opportunity-trust');
        if (!panel) return;
        const state = info.state || 'loading';
        const title = info.title || {
            loading: '正在加载',
            refreshing: '正在刷新',
            empty: '等待数据',
            stale: '保留旧结果',
            failed: '加载失败',
            real: '真实合成',
            fallback: '降级预览',
            emergency: '本地应急',
        }[state] || '状态未知';
        const text = info.text || '机会池会标明真实合成、降级预览或本地应急状态。';
        const trustClass = {
            real: info.muted ? 'trust-muted' : 'trust-real',
            fallback: 'trust-fallback',
            emergency: 'trust-emergency',
            review: 'trust-review',
            stale: 'trust-stale',
            failed: 'trust-failed',
            empty: 'trust-empty',
            refreshing: 'trust-loading',
            loading: 'trust-loading',
        }[state] || 'trust-loading';
        panel.className = `opportunity-trust-panel ${trustClass}`;
        panel.innerHTML = `
            <span class="opportunity-trust-badge">${this.escapeHTML(title)}</span>
            <span class="opportunity-trust-text">${this.escapeHTML(text)}</span>
            <span class="opportunity-trust-actions">
                <button class="btn btn-xs" type="button" data-ov-opportunity-refresh>刷新</button>
                <button class="btn btn-xs" type="button" data-app-action="switch-tab" data-tab="research" data-subtab="datahub">打开完整矩阵</button>
            </span>
        `;
    },

    _formatOverviewSignalQuality(summary = {}) {
        const quality = summary.signal_quality || {};
        const validation = summary.signal_validation || {};
        const labelMap = {
            validated_positive: '验证偏正',
            validated_neutral: '验证中性',
            validated_weak: '验证偏弱',
            unverified: '未验证',
        };
        const label = quality.label || labelMap[validation.confidence] || '未验证';
        const rawSampleDays = quality.sample_days ?? validation.sample_days;
        const sampleDays = Number.isFinite(Number(rawSampleDays)) ? Number(rawSampleDays) : null;
        const penalty = quality.penalty_applied === true || (!quality.label && !String(validation.confidence || '').startsWith('validated'));
        const parts = [`信号质量 ${this.escapeHTML(label)}`];
        if (sampleDays !== null) parts.push(`样本 ${this.escapeHTML(sampleDays)} 天`);
        if (penalty) parts.push('已降权');
        return parts.join(' · ');
    },

    _formatOverviewQlibSyncStatus(syncStatus) {
        if (!syncStatus || typeof syncStatus !== 'object') return '';
        const successCount = Number(syncStatus.success_count);
        const targetCount = Number(syncStatus.target_count);
        const failCount = Number(syncStatus.fail_count || 0);
        if (!Number.isFinite(successCount) || !Number.isFinite(targetCount) || targetCount <= 0) {
            return '';
        }
        const parts = [`同步 ${successCount}/${targetCount}`];
        if (failCount > 0) {
            parts.push(`失败 ${failCount}`);
        }
        return parts.join(' · ');
    },

    _overviewOpportunityScopeLabel(scope) {
        return {
            watchlist: '自选',
            signal: 'AI信号 Top',
            qlib: 'AI信号 Top',
        }[scope] || 'AI信号 Top';
    },

    _overviewActionIntentClass(action) {
        const text = String(action || '');
        if (/问龙虾|研究|重点池/.test(text)) return 'action-research';
        if (/模拟|交易|小仓|买入|卖出/.test(text)) return 'action-trade';
        if (/观察|跟踪|自选|监控|等待/.test(text)) return 'action-watch';
        if (/补|核对|查|估值详情|同业估值|PEG|目标价|缺失数据/.test(text)) return 'action-data';
        if (/暂缓|保留/.test(text)) return 'action-hold';
        return 'action-watch';
    },

    _renderOverviewOpportunityActions(actions) {
        const list = Array.isArray(actions) ? actions.slice(0, 4) : [];
        if (!list.length) return '<span class="text-muted">--</span>';
        return list.map((action) => {
            const cls = this._overviewActionIntentClass(action);
            return `<span class="datahub-action-tag ${cls}">${this.escapeHTML(action)}</span>`;
        }).join('');
    },

    _renderOverviewOpportunityStockMeta(item) {
        const code = String(item?.code || '').trim();
        const industry = String(item?.industry || '').trim();
        const primaryIndustry = industry.split(/\s*[-｜|/]\s*/).find((part) => part.trim())?.trim() || '';
        const meta = [code, primaryIndustry].filter(Boolean).join(' · ') || '--';
        const title = industry ? ` title="${this.escapeHTML(industry)}"` : '';
        return `<div class="opportunity-stock-meta text-muted text-xs"${title}>${this.escapeHTML(meta)}</div>`;
    },

    _renderOpportunityRow(item) {
        const score = Number(item.decision_score || 0);
        const scoreCls = score >= 78 ? 'score-hot' : score >= 62 ? 'score-warm' : score >= 45 ? 'score-neutral' : 'score-cold';
        const riskCls = item.risk_level === '高' ? 'risk-high' : item.risk_level === '中' ? 'risk-mid' : 'risk-low';
        const actions = item.next_actions || [];
        const reasonTags = (item.reason_tags || []).slice(0, 3);
        const riskTags = (item.risk_tags || []).slice(0, 3);
        return `<tr>
            <td>${item.matrix_rank || '--'}</td>
            <td>
                <button class="link-button datahub-stock-link" data-ov-opportunity-action="stock" data-code="${this.escapeHTML(item.code || '')}">${this.escapeHTML(item.name || item.code || '--')}</button>
                ${this._renderOverviewOpportunityStockMeta(item)}
                <div class="opportunity-evidence-tags">${reasonTags.map((tag) => `<span class="datahub-reason-tag">${this.escapeHTML(tag)}</span>`).join('') || '<span class="text-muted text-xs">暂无评分依据</span>'}</div>
            </td>
            <td><span class="datahub-score ${scoreCls}">${score}</span><span class="datahub-decision-label">${this.escapeHTML(item.decision_label || '--')}</span></td>
            <td>${this._fmtOverviewNum(item.peg_next_year, 2)}</td>
            <td>
                <span class="datahub-risk-pill ${riskCls}">${this.escapeHTML(item.risk_level || '--')}</span>
                <div class="opportunity-risk-tags">${riskTags.map((tag) => `<span class="datahub-risk-tag">${this.escapeHTML(tag)}</span>`).join('') || '<span class="text-muted text-xs">暂无明显风险</span>'}</div>
            </td>
            <td>${this._renderOverviewOpportunityActions(actions)}</td>
            <td class="datahub-actions">
                <button class="btn btn-xs" data-ov-opportunity-action="watchlist" data-code="${this.escapeHTML(item.code || '')}">自选</button>
                <button class="btn btn-xs" data-ov-opportunity-action="ask" data-code="${this.escapeHTML(item.code || '')}">问龙虾</button>
            </td>
        </tr>`;
    },

    async _askOpportunityOpenClaw(code) {
        const item = (this._overviewOpportunityItems || []).find((stock) => stock.code === code) || { code };
        const signalTrust = this._overviewOpportunitySignalTrustLine(item);
        const riskLine = Array.isArray(item.risk_tags) && item.risk_tags.length
            ? `显式风险：${item.risk_tags.join('、')}。`
            : '显式风险：暂无明显风险。';
        const prompt = [
            `请基于首页数据机会池分析 ${item.name || code}(${code})。`,
            `决策评分：${item.decision_score ?? '--'}，标签：${item.decision_label || '--'}，风险：${item.risk_level || '--'}。`,
            `AI信号：${item.signal_rank || item.qlib_rank ? `排名 ${item.signal_rank || item.qlib_rank}，分数 ${this._fmtOverviewNum(item.signal_score ?? item.qlib_score, 3)}，来源 ${item.signal_provider || item.qlib_provider || 'local_momentum'}` : '暂无覆盖'}。`,
            signalTrust,
            riskLine,
            `下一步建议：${(item.next_actions || []).join('、') || '--'}。`,
            '请给我一个模拟盘观察计划；仅供观察，不要给实盘下单建议。',
        ].join('\n');
        await App.switchTab('openclaw');
        await globalThis.OpenClawWorkbench?.maybeInitForTab?.('openclaw');
        await globalThis.OpenClawWorkbench?.send?.(prompt);
    },

    _overviewOpportunitySignalTrustLine(item = {}) {
        const provider = this._overviewSignalSourceLabel(item.signal_provider || item.qlib_provider || 'local_momentum') || '未知来源';
        const rank = item.signal_rank || item.qlib_rank;
        const confidence = item.signal_confidence || item.qlib_confidence || item.signal_quality?.confidence || 'unverified';
        const label = item.signal_quality?.label || this._overviewSignalConfidenceLabel(confidence) || '未验证';
        const sampleDays = Number(item.signal_quality?.sample_days ?? item.signal_sample_days);
        const sample = Number.isFinite(sampleDays) ? `样本 ${sampleDays} 天` : '样本未知';
        const riskText = (item.risk_tags || []).join('、');
        const penalty = item.signal_quality?.penalty_applied || /AI未验证|AI未覆盖/.test(riskText);
        const status = rank ? `AI${label}` : 'AI未覆盖';
        const action = penalty ? '已降权，仅供观察' : '按正常权重参与评分';
        return `信号可信度：${status}，${sample}，来源 ${provider}，${action}。`;
    },

    _overviewSignalSourceLabel(value) {
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

    _overviewSignalConfidenceLabel(value) {
        const labels = {
            validated_positive: '验证偏正',
            validated_neutral: '验证中性',
            validated_weak: '验证偏弱',
            unverified: '未验证',
        };
        const key = String(value || '').trim();
        return labels[key] || key;
    },

    _fmtOverviewNum(value, digits = 2) {
        if (value === null || typeof value === 'undefined' || value === '') return '--';
        return Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : '--';
    },

    _fmtOverviewPct(value) {
        return Number.isFinite(Number(value)) ? `${Number(value).toFixed(0)}%` : '--';
    },

    _clearOverviewSecondarySkeletons() {
        const chartContainer = document.querySelector('#tab-overview .chart-container');
        if (chartContainer) {
            const skel = chartContainer.querySelector('.skeleton-chart');
            if (skel) skel.remove();
            const canvas = chartContainer.querySelector('canvas');
            if (canvas) canvas.style.display = '';
        }

        const indicesEl = document.getElementById('ov-market-indices');
        if (indicesEl?.querySelector('.skeleton-indices')) {
            indicesEl.innerHTML = '<div class="text-muted text-center">暂无指数数据</div>';
        }
        ['ov-hot-industries', 'ov-hot-concepts'].forEach((id) => {
            const el = document.getElementById(id);
            if (el?.querySelector('.skeleton-sector-rows')) {
                el.innerHTML = '<div class="text-muted">暂无数据</div>';
            }
        });
    },

    _showOverviewSkeletons() {
        // 统计卡片骨架屏
        ['ov-equity', 'ov-daily-pnl', 'ov-cum-return', 'ov-max-dd', 'ov-sharpe', 'ov-position-count'].forEach(id => {
            const el = document.getElementById(id);
            if (el) { el.textContent = ''; el.classList.add('skeleton-text'); }
        });
        // 持仓表格骨架屏
        const posBody = document.querySelector('#ov-positions-table tbody');
        if (posBody) posBody.innerHTML = `<tr><td colspan="8">${Utils.skeletonRows(5, 8)}</td></tr>`;
        // 交易表格骨架屏
        const tradesBody = document.querySelector('#ov-trades-table tbody');
        if (tradesBody) tradesBody.innerHTML = `<tr><td colspan="5">${Utils.skeletonRows(5, 5)}</td></tr>`;
        // 图表骨架屏
        const chartContainer = document.querySelector('#tab-overview .chart-container');
        if (chartContainer) {
            const canvas = chartContainer.querySelector('canvas');
            if (canvas) canvas.style.display = 'none';
            if (!chartContainer.querySelector('.skeleton-chart')) {
                const skel = document.createElement('div');
                skel.className = 'skeleton-chart';
                skel.style.position = 'absolute';
                skel.style.inset = '0';
                skel.innerHTML = Array.from({length: 20}, () => {
                    const h = 20 + Math.random() * 80;
                    return `<div class="skel-bar skeleton-pulse" style="height:${h}%"></div>`;
                }).join('');
                chartContainer.style.position = 'relative';
                chartContainer.appendChild(skel);
            }
        }
    },

    _renderMetric(id, pnl, pnlPct, isCurrency) {
        const el = document.getElementById(id);
        if (!el) return;
        const value = Number(pnl || 0);
        const pct = Number(pnlPct || 0);
        const sign = value > 0 ? '+' : value < 0 ? '-' : '';
        const arrow = value > 0 ? '↑ ' : value < 0 ? '↓ ' : '';
        const text = isCurrency
            ? `${arrow}${sign}¥${Math.abs(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`
            : `${arrow}${sign}${Math.abs(pct * 100).toFixed(2)}%`;
        el.textContent = text;
        el.className = 'stat-value ' + (value > 0 ? 'text-up' : value < 0 ? 'text-down' : 'text-muted');
    },

    _renderPctMetric(id, value, alwaysRed) {
        const el = document.getElementById(id);
        if (!el) return;
        value = Number(value || 0);
        const arrow = value > 0 ? '↑ ' : value < 0 ? '↓ ' : '';
        const sign = value > 0 ? '+' : value < 0 ? '-' : '';
        el.textContent = `${arrow}${sign}${Math.abs(value * 100).toFixed(2)}%`;
        if (alwaysRed) {
            // 回撤阈值：>0.5% 暗红，否则普通红
            el.className = 'stat-value ' + (Math.abs(value) > 0.005 ? 'stat-value-critical' : 'text-muted');
        } else {
            el.className = 'stat-value ' + (value > 0 ? 'text-up' : value < 0 ? 'text-down' : 'text-muted');
        }
    },

    _renderPositions(snapshot) {
        const tbody = document.querySelector('#ov-positions-table tbody');
        if (!tbody) return;
        const positions = snapshot.positions || [];
        if (positions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="text-muted">暂无持仓</td></tr>';
            return;
        }
        const totalEquity = snapshot.total_equity || 1;
        const top5 = positions.slice(0, 5);
        tbody.innerHTML = top5.map(p => {
            const pctClass = p.pnl >= 0 ? 'text-up' : 'text-down';
            const sign = p.pnl >= 0 ? '+' : '';
            const arrow = p.pnl >= 0 ? '↑' : '↓';
            const weight = ((p.market_value / totalEquity) * 100).toFixed(1);
            return `<tr>
                <td><a href="#" class="stock-link" data-code="${this.escapeHTML(p.code)}">${this.escapeHTML(p.code)}</a></td>
                <td>${this.escapeHTML(p.name) || '--'}</td>
                <td>${p.volume}</td>
                <td>¥${p.avg_price.toFixed(3)}</td>
                <td class="${pctClass}">¥${p.current_price.toFixed(3)}</td>
                <td class="${pctClass}">${arrow} ${sign}¥${Math.abs(p.pnl).toFixed(2)}</td>
                <td class="${pctClass}">${arrow} ${sign}${(p.pnl_pct * 100).toFixed(2)}%</td>
                <td>${weight}%</td>
            </tr>`;
        }).join('') + `<tr class="pos-summary">
            <td colspan="2"><strong>合计 (${positions.length}只)</strong></td>
            <td>${positions.reduce((s, p) => s + p.volume, 0)}</td>
            <td></td>
            <td></td>
            <td class="${snapshot.total_pnl >= 0 ? 'text-up' : 'text-down'}"><strong>${snapshot.total_pnl >= 0 ? '+' : ''}¥${Math.abs(snapshot.total_pnl).toFixed(2)}</strong></td>
            <td class="${snapshot.total_pnl >= 0 ? 'text-up' : 'text-down'}"><strong>${snapshot.total_pnl >= 0 ? '+' : ''}${(snapshot.total_pnl_pct * 100).toFixed(2)}%</strong></td>
            <td></td>
        </tr>`;
    },

    renderEquityChart(data) {
        const canvasId = 'ov-overview-chart';
        if (!data || data.length === 0) { ChartFactory.showEmpty(canvasId); return; }
        ChartFactory.line(canvasId, {
            labels: data.map(p => p.date),
            datasets: [{ data: data.map(p => p.equity), fill: true }],
        }, 'overviewChart', {
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: ctx => `资产: ¥${ctx.parsed.y.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`,
                    },
                },
            },
            scales: {
                y: {
                    ticks: {
                        callback: v => '¥' + (v / 10000).toFixed(1) + '万',
                        color: '#a29c95',
                        font: { size: 11 },
                    },
                    grid: { color: 'rgba(227,225,219,0.25)' },
                },
                x: {
                    ticks: { maxTicksLimit: 8, color: '#a29c95', font: { size: 11 } },
                    grid: { display: false },
                },
            },
        });
    },

    renderMarketIndices(indices) {
        const el = document.getElementById('ov-market-indices');
        if (!el) return;
        if (!Array.isArray(indices) || indices.length === 0) {
            el.innerHTML = '<div class="text-muted text-center">暂无指数数据</div>';
            return;
        }
        el.innerHTML = indices.map(idx => {
            const changePct = Number(idx.change_pct || 0);
            const change = Number(idx.change || 0);
            const cls = changePct > 0 ? 'text-up' : changePct < 0 ? 'text-down' : 'text-muted';
            const sign = changePct > 0 ? '+' : changePct < 0 ? '-' : '';
            return `
                <div class="market-index">
                    <div class="idx-name">${this.escapeHTML(idx.name)}</div>
                    <div class="idx-price ${cls}">${idx.price.toFixed(2)}</div>
                    <div class="idx-change ${cls}">${sign}${Math.abs(change).toFixed(2)}  ${sign}${Math.abs(changePct).toFixed(3)}%</div>
                </div>`;
        }).join('');
    },

    renderHotSectors(data) {
        const industriesEl = document.getElementById('ov-hot-industries');
        const conceptsEl = document.getElementById('ov-hot-concepts');

        const renderList = (el, items) => {
            if (!el || !Array.isArray(items) || items.length === 0) {
                if (el) el.innerHTML = '<div class="text-muted">暂无数据</div>';
                return;
            }
            const maxPct = Math.max(...items.map(s => Math.abs(s.change_pct)), 0.01);
            el.innerHTML = items.map((s, i) => {
                const cls = s.change_pct >= 0 ? 'text-up' : 'text-down';
                const sign = s.change_pct >= 0 ? '+' : '';
                const barW = Math.min(Math.abs(s.change_pct) / maxPct * 100, 100);
                const barCls = s.change_pct >= 0 ? 'sr-bar-up' : 'sr-bar-down';
                return `
                    <div class="sector-row">
                        <span class="sr-rank">${i + 1}</span>
                        <span class="sr-name">${this.escapeHTML(s.name)}</span>
                        <div class="sr-bar-wrap"><div class="${barCls}" style="width:${barW}%"></div></div>
                        <span class="sr-count">涨${s.rise_count}/跌${s.fall_count}</span>
                        <span class="sr-pct ${cls}">${sign}${s.change_pct.toFixed(2)}%</span>
                    </div>`;
            }).join('');
        };

        renderList(industriesEl, data.industries);
        renderList(conceptsEl, data.concepts);
    },

    _registerOverviewTimers() {
        if (this.currentTab !== 'overview') {
            return;
        }
        if (typeof PollManager === 'undefined' || !PollManager || typeof PollManager.register !== 'function') {
            return;
        }

        PollManager.register('overview:market-phase', () => this._updateMarketPhase(), 60000);
        PollManager.register('overview:data-freshness', () => this._updateDataFreshness(), 30000);
        PollManager.register('overview:quote-status', () => this._updateQuoteStatus(), 1000);
    },

    _unregisterOverviewTimers() {
        if (typeof PollManager === 'undefined' || !PollManager || typeof PollManager.cancel !== 'function') {
            return;
        }

        PollManager.cancel('overview:market-phase');
        PollManager.cancel('overview:data-freshness');
        PollManager.cancel('overview:quote-status');
    },

    /** AI 信号心跳检查 */
    async _checkSignalHealth() {
        const el = document.getElementById('ov-qlib-status');
        if (!el) return;
        try {
            const data = await this.fetchJSON('/api/signals/health?fast=true', { silent: true });
            if (data?.status === 'online') {
                el.textContent = '🟢 在线';
                el.className = 'stat-value text-up';
            } else if (data?.status === 'stale') {
                el.textContent = '🟡 过期';
                el.className = 'stat-value stat-value-warn';
            } else {
                el.textContent = '🔴 离线';
                el.className = 'stat-value text-down';
            }
        } catch {
            el.textContent = '🔴 离线';
            el.className = 'stat-value text-down';
        }
    },

    async _loadDataHubHealth() {
        const root = document.getElementById('ov-datahub-health');
        if (!root) return;
        try {
            const data = await this.fetchJSON('/api/datahub/health?fast=true', { silent: true, timeout: 8000 });
            const quote = data.quote || {};
            const valuation = data.valuation || {};
            const qlib = data.signal || data.qlib || {};
            const stockDaily = data.stock_daily || {};
            const fullDailySync = data.full_daily_sync || {};
            const shadow = data.shadow || {};
            const stockInfoIntegrity = data.stock_info_integrity || {};
            const stockInfoCleanup = data.stock_info_cleanup_preview || {};
            const stockInfoCleanupRows = Number(stockInfoIntegrity.duplicate_extra_row_count || 0);
            const stockInfoWrongPrefix = Number(stockInfoIntegrity.wrong_prefix_count || 0);
            const stockInfoMissingIndustry = Number(stockInfoIntegrity.merged_blank_industry_count || 0);
            const stockInfoMergeRequired = Number(stockInfoCleanup.merge_required_count || 0);
            const stockInfoReadyCleanup = Number(stockInfoCleanup.cleanup_ready_count || 0);
            const stockInfoLabel = stockInfoCleanupRows > 0
                ? `${data.stock_count ?? '--'} · 待清理${stockInfoCleanupRows}`
                : `${data.stock_count ?? '--'} · 干净`;
            const stockInfoQualityParts = [];
            if (stockInfoWrongPrefix > 0) stockInfoQualityParts.push(`错前缀${stockInfoWrongPrefix}`);
            if (stockInfoMergeRequired > 0 || stockInfoReadyCleanup > 0) {
                stockInfoQualityParts.push(`需合并${stockInfoMergeRequired}`);
                stockInfoQualityParts.push(`可直删${stockInfoReadyCleanup}`);
            }
            if (stockInfoMissingIndustry > 0) stockInfoQualityParts.push(`缺行业${stockInfoMissingIndustry}`);
            const stockInfoQualityLabel = stockInfoQualityParts.length ? stockInfoQualityParts.join(' · ') : '无底层缺口';
            const age = quote.last_update_age_sec;
            const quoteLabel = quote.running
                ? (age == null ? '运行中' : `${Math.round(age)}秒前`)
                : '未运行';
            const qlibLabel = qlib.status === 'online'
                ? `在线 · ${qlib.cache_age_label || '--'}`
                : qlib.status === 'stale'
                    ? `过期 · ${qlib.cache_age_label || '--'}`
                    : '离线';
            const shadowLabel = shadow.total_checks
                ? `${shadow.total_diffs || 0} 条差异`
                : '暂无差异日志';
            const sourceHealth = data.source_health || {};
            const qualitySummary = data.quality_summary || {};
            const sourceLabel = sourceHealth.total_active_sources != null
                ? `${sourceHealth.total_active_sources} 个在线`
                : '--';
            const qualityLabel = qualitySummary.total != null
                ? `${qualitySummary.total} 条`
                : '--';
            const dailyCoverageLabel = stockDaily.coverage_pct == null
                ? '--'
                : `${stockDaily.daily_covered ?? 0}/${stockDaily.stock_count ?? data.stock_count ?? '--'} · ${stockDaily.coverage_pct}%`;
            const latestDailyLabel = stockDaily.latest_date
                ? `${stockDaily.latest_date} · ${stockDaily.latest_date_covered ?? 0}只`
                : '无数据';
            const syncLabel = fullDailySync.status_label || '未同步';
            root.innerHTML = `
                <div class="datahub-health-item"><span>股票名录</span><strong>${this.escapeHTML(stockInfoLabel)}</strong></div>
                <div class="datahub-health-item"><span>名录质量</span><strong>${this.escapeHTML(stockInfoQualityLabel)}</strong></div>
                <div class="datahub-health-item"><span>日线覆盖</span><strong>${this.escapeHTML(dailyCoverageLabel)}</strong></div>
                <div class="datahub-health-item"><span>最新日线</span><strong>${this.escapeHTML(latestDailyLabel)}</strong></div>
                <div class="datahub-health-item"><span>全量同步</span><strong>${this.escapeHTML(syncLabel)}</strong></div>
                <div class="datahub-health-item"><span>自选覆盖</span><strong>${this.escapeHTML(data.watchlist_count ?? '--')}</strong></div>
                <div class="datahub-health-item"><span>行情缓存</span><strong>${this.escapeHTML(quote.cache_count ?? '--')} / ${this.escapeHTML(quote.subscriptions ?? '--')}</strong></div>
                <div class="datahub-health-item"><span>行情新鲜度</span><strong>${this.escapeHTML(quoteLabel)}</strong></div>
                <div class="datahub-health-item"><span>估值覆盖</span><strong>${valuation.coverage_pct == null ? '--' : `${valuation.coverage_pct}%`}</strong></div>
                <div class="datahub-health-item"><span>AI信号</span><strong>${this.escapeHTML(qlibLabel)}</strong></div>
                <div class="datahub-health-item"><span>影子对账</span><strong>${this.escapeHTML(shadowLabel)}</strong></div>
                <div class="datahub-health-item"><span>数据源在线</span><strong>${this.escapeHTML(sourceLabel)}</strong></div>
                <div class="datahub-health-item"><span>质量记录</span><strong>${this.escapeHTML(qualityLabel)}</strong></div>
                <div class="datahub-health-item"><span>估值源</span><strong>机构预测</strong></div>
            `;
        } catch (e) {
            root.innerHTML = '<div class="text-muted">数据底座状态暂不可用</div>';
        }
    },

    /** 更新数据新鲜度指示 */
    _updateDataFreshness() {
        const el = document.getElementById('ov-data-freshness');
        if (!el || !this._overviewDataTime) return;

        const age = Date.now() - this._overviewDataTime;
        const min = Math.floor(age / 60000);

        let label, cls;
        if (min < 1) {
            label = '刚刚更新'; cls = 'fresh';
        } else if (min < 5) {
            label = `${min}分钟前`; cls = 'fresh';
        } else if (min < 15) {
            label = `${min}分钟前`; cls = 'stale';
        } else {
            label = `${min}分钟前`; cls = 'old';
        }

        el.textContent = label;
        el.className = `data-freshness ${cls}`;
    },

    /** 更新市场阶段指示器 (盘前/盘中/盘后) */
    _updateMarketPhase() {
        const el = document.getElementById('ov-market-phase');
        if (!el) return;

        const now = new Date();
        const hhmm = now.getHours() * 100 + now.getMinutes();
        const day = now.getDay();
        const isWeekday = day >= 1 && day <= 5;

        let phase, label;
        if (!isWeekday) {
            phase = 'post'; label = '休市';
        } else if (hhmm < 915) {
            phase = 'pre'; label = '盘前';
        } else if (hhmm <= 1130) {
            phase = 'open'; label = '盘中（上午）';
        } else if (hhmm < 1300) {
            phase = 'pre'; label = '午间休市';
        } else if (hhmm <= 1500) {
            phase = 'open'; label = '盘中（下午）';
        } else {
            phase = 'post'; label = '盘后';
        }

        el.className = `market-phase phase-${phase}`;
        el.querySelector('.market-phase-text').textContent = label;
    },

    // _startMarketRefresh / _stopMarketRefresh / _refreshMarket
    // 已在 app.js 中通过 PollManager 统一管理，此处不再重复定义
});
