/* ── AI 量化交易系统 — 核心入口 ── */

if (typeof globalThis.ENABLE_WORKSPACE_V2 === 'undefined') {
    globalThis.ENABLE_WORKSPACE_V2 = true;
}

/* 轮询协调器：统一管理所有定时器 */
const PollManager = {
    _timers: {},

    register(name, callback, interval) {
        this.cancel(name);
        this._timers[name] = { callback, interval, timer: null, paused: false };
        this._timers[name].timer = setInterval(() => {
            if (!this._timers[name]?.paused) callback();
        }, interval);
    },

    cancel(name) {
        const t = this._timers[name];
        if (t) {
            clearInterval(t.timer);
            delete this._timers[name];
        }
    },

    pause(name) {
        if (this._timers[name]) this._timers[name].paused = true;
    },

    resume(name) {
        if (this._timers[name]) this._timers[name].paused = false;
    },

    pauseAll() {
        for (const t of Object.values(this._timers)) t.paused = true;
    },

    resumeAll() {
        for (const t of Object.values(this._timers)) t.paused = false;
    },

    destroy() {
        for (const name of Object.keys(this._timers)) this.cancel(name);
    },
};

const App = {
    stockCache: null,
    currentTab: 'overview',
    // EventBus 跨模块通信
    _eventHandlers: {},
    on(event, handler) {
        (this._eventHandlers[event] ??= []).push(handler);
    },
    off(event, handler) {
        const list = this._eventHandlers[event];
        if (list) this._eventHandlers[event] = list.filter(h => h !== handler);
    },
    emit(event, data) {
        (this._eventHandlers[event] || []).forEach(h => {
            try { h(data); } catch (e) { console.error(`EventBus [${event}]:`, e); }
        });
    },

    // V2: ContextProvider 页面上下文感知
    _contextProviders: {},
    registerContext(tab, provider) {
        this._contextProviders[tab] = provider;
    },
    getContext(tab) {
        const p = this._contextProviders[tab || this.currentTab];
        return p ? p() : null;
    },

    // V2: Copilot 快捷入口（FAB 按钮调用）
    toggleCopilot() {
        void this.ensureBundle?.('llm').then(() => {
            if (typeof App.LLM !== 'undefined') App.LLM.toggleCopilot();
        });
    },

    _scriptLoadPromises: {},
    _bundleLoadPromises: {},
    _pageBundles: {
        overview: [
            '/static/overview.js?v=7',
            '/static/overview-radar.js?v=4',
            '/static/alerts.js?v=1',
        ],
        trade: [
            '/static/portfolio-stats.js?v=1',
            '/static/portfolio-table.js?v=2',
            '/static/portfolio-charts.js?v=1',
            '/static/portfolio-trades.js?v=4',
            '/static/portfolio-actions.js?v=1',
            '/static/portfolio.js?v=3',
            '/static/risk.js?v=2',
            '/static/risk-stats.js?v=2',
            '/static/risk-charts.js?v=2',
            '/static/risk-rules.js?v=2',
            '/static/risk-positions.js?v=2',
            '/static/risk-events.js?v=2',
            '/static/risk-alerts.js?v=2',
        ],
        paper: [
            '/static/paper.js?v=8',
            '/static/paper-trading.js?v=5',
            '/static/paper-trading-trade.js?v=1',
            '/static/paper-trading-position.js?v=1',
            '/static/paper-trading-performance.js?v=1',
            '/static/paper-trading-analytics.js?v=1',
            '/static/paper-trading-history.js?v=1',
        ],
        strategy: [
            '/static/strategy.js?v=7',
            '/static/strategy-tools.js?v=2',
            '/static/strategy-list.js?v=2',
            '/static/strategy-form.js?v=1',
            '/static/strategy-code-editor.js?v=1',
            '/static/strategy-versions.js?v=1',
            '/static/strategy-records.js?v=1',
            '/static/strategy-optimizer.js?v=1',
            '/static/strategy-ensemble.js?v=1',
        ],
        openclaw: [
            '/static/openclaw-conversations.js?v=2',
            '/static/openclaw-workbench.js?v=17',
        ],
        research: [
            '/static/backtest.js?v=4',
            '/static/backtest-analysis.js?v=1',
            '/static/backtest-strategies.js?v=1',
            '/static/alpha.js?v=3',
            '/static/alpha-charts.js?v=1',
            '/static/alpha-factors.js?v=1',
            '/static/alpha-tools.js?v=1',
            '/static/llm.js?v=10',
            '/static/llm-render.js?v=1',
            '/static/llm-actions.js?v=1',
            '/static/llm-conversations.js?v=7',
            '/static/llm-copilot.js?v=1',
            '/static/compare.js?v=4',
            '/static/screener.js?v=5',
            '/static/screener-ai.js?v=1',
            '/static/optimization.js?v=2',
            '/static/factor.js?v=1',
            '/static/portfolio-opt.js?v=1',
            '/static/intelligence.js?v=2',
            '/static/intelligence-market.js?v=2',
            '/static/intelligence-iwencai.js?v=3',
            '/static/intelligence-qlib.js?v=2',
            '/static/research-datahub.js?v=3',
            '/static/research-valuation.js?v=9',
        ],
        stock: [
            '/static/stock-detail.js?v=7',
            '/static/stock-detail-core.js?v=5',
            '/static/stock-detail-drawings.js?v=1',
            '/static/stock-detail-insights.js?v=3',
            '/static/stock-detail-chips.js?v=1',
            '/static/stock-detail-market.js?v=1',
            '/static/stock-detail-market-mtf.js?v=1',
            '/static/stock-detail-market-dragon.js?v=1',
            '/static/stock-detail-research.js?v=1',
            '/static/stock-detail-valuation.js?v=11',
            '/static/stock-detail-charts.js?v=1',
            '/static/stock-detail-timeline.js?v=2',
            '/static/stock-detail-timeline-overlays.js?v=1',
            '/static/stock-detail-kline.js?v=1',
            '/static/stock-detail-book.js?v=1',
            '/static/stock-detail-data.js?v=1',
        ],
        intelligence: [
            '/static/intelligence.js?v=2',
            '/static/intelligence-market.js?v=2',
            '/static/intelligence-iwencai.js?v=3',
            '/static/intelligence-qlib.js?v=2',
        ],
        llm: [
            '/static/llm.js?v=10',
            '/static/llm-render.js?v=1',
            '/static/llm-actions.js?v=1',
            '/static/llm-conversations.js?v=7',
            '/static/llm-copilot.js?v=1',
        ],
    },

    loadScript(src) {
        if (this._scriptLoadPromises[src]) {
            return this._scriptLoadPromises[src];
        }

        this._scriptLoadPromises[src] = new Promise((resolve, reject) => {
            const existing = Array.from(document.scripts).find((script) => script.src === new URL(src, location.origin).href);
            if (existing) {
                resolve(existing);
                return;
            }

            const script = document.createElement('script');
            script.src = src;
            script.defer = true;
            script.onload = () => resolve(script);
            script.onerror = () => reject(new Error(`加载失败: ${src}`));
            document.head.appendChild(script);
        });

        return this._scriptLoadPromises[src];
    },

    async ensureBundle(name) {
        const bundle = this._pageBundles[name];
        if (!bundle || !bundle.length) {
            return;
        }

        if (!this._bundleLoadPromises[name]) {
            this._bundleLoadPromises[name] = (async () => {
                for (const src of bundle) {
                    await this.loadScript(src);
                }
            })();
        }

        return this._bundleLoadPromises[name];
    },

    // Tab别名映射 (旧Tab名 → 当前Tab名)
        _tabAlias: {
            sim: 'paper',
            'strategy-admin': 'strategy',
        },

    _uiActionPending: {},
    _degradedUiState: {
        dedupeKeys: {},
    },
    _runtimeErrorState: {
        lastSignature: '',
        lastAt: 0,
    },

    _tagLegacyActionButtons() {
        const overviewRefresh = document.querySelector('#tab-overview > .page-header .btn.btn-sm');
        if (overviewRefresh) overviewRefresh.dataset.appRole = 'overview-refresh';

        const alphaActionGroup = document.getElementById('alpha-model')?.parentElement;
        const alphaButtons = alphaActionGroup ? [...alphaActionGroup.querySelectorAll('button.btn')] : [];
        if (alphaButtons[0]) alphaButtons[0].dataset.appRole = 'alpha-analyze';
        if (alphaButtons[1]) alphaButtons[1].dataset.appRole = 'alpha-optimize';

        const factorActionGroup = document.getElementById('factor-select')?.parentElement;
        const factorButtons = factorActionGroup ? [...factorActionGroup.querySelectorAll('button.btn.btn-sm')] : [];
        if (factorButtons[0]) factorButtons[0].dataset.appRole = 'factor-analyze';
        if (factorButtons[1]) factorButtons[1].dataset.appRole = 'factor-correlation';

        const portoptPanel = document.getElementById('portopt-codes')?.closest('.card');
        const portoptButtons = portoptPanel ? [...portoptPanel.querySelectorAll('button.btn')] : [];
        const optimizeButton = portoptButtons.find(btn => btn.textContent.includes('执行优化'));
        if (optimizeButton) optimizeButton.dataset.appRole = 'portopt-optimize';
    },

    _getLegacyActionButton(role) {
        this._tagLegacyActionButtons();
        return document.querySelector(`[data-app-role="${role}"]`);
    },

    escapeHTML(str) {
        if (str == null) return '';
        return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#x27;');
    },

    safeHref(url) {
        if (!url) return '#';
        try {
            const u = new URL(url);
            if (u.protocol === 'http:' || u.protocol === 'https:') return url;
        } catch {}
        return '#';
    },

    getAPIKey() {
        return window.APIClient?.getAPIKey?.() || '';
    },

    withAPIKey(url) {
        return window.APIClient?.withAPIKey?.(url) || url;
    },

    /**
     * 统一 JSON 请求方法
     * @param {string} url - 请求地址
     * @param {object} [opts] - 选项
     * @param {number} [opts.timeout=15000] - 超时毫秒
     * @param {boolean} [opts.silent=false] - 静默模式（不显示错误Toast）
     * @param {number} [opts.retries=0] - 重试次数
     * @param {string} [opts.label] - 操作标签（用于错误消息）
     */
    async fetchJSON(url, opts = {}) {
        return window.APIClient.fetchJSON(url, {
            ...(typeof opts === 'number' ? { timeout: opts } : opts),
            onToast: (message, type) => this.toast(message, type),
        });
    },

    fmt(value) {
        if (value == null) return '--';
        if (value === 0) return '¥0';
        return '¥' + Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 });
    },

    toast(message, type = 'info') {
        let container = document.querySelector('.toast-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'toast-container';
            document.body.appendChild(container);
        }
        const el = document.createElement('div');
        el.className = `toast toast-${type}`;
        el.textContent = message;
        container.appendChild(el);
        const duration = type === 'error' ? 8000 : 3000;
        setTimeout(() => el.remove(), duration);
    },

    /** 浏览器通知 + 音频提醒 */
    notify(title, body, { sound = true, level = 'info' } = {}) {
        // 浏览器通知
        if ('Notification' in window) {
            if (Notification.permission === 'default') {
                Notification.requestPermission();
            }
            if (Notification.permission === 'granted') {
                try { new Notification(title, { body, tag: 'quant-alert' }); } catch {}
            }
        }
        // 音频提醒（Web Audio API 生成，无需外部文件）
        if (sound && this._audioEnabled !== false) {
            try {
                const ctx = new (window.AudioContext || window.webkitAudioContext)();
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.connect(gain);
                gain.connect(ctx.destination);
                const freq = level === 'critical' ? 880 : level === 'warning' ? 660 : 440;
                osc.frequency.value = freq;
                osc.type = 'sine';
                gain.gain.setValueAtTime(0.3, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.4);
                osc.start(ctx.currentTime);
                osc.stop(ctx.currentTime + 0.4);
            } catch {}
        }
    },

    // 股票动作/自选股联动已移至 app-stock-ops.js

    // App shell/navigation helpers moved to core/app-shell.js

    // UI shell helpers moved to app-ui-shell.js

    _updateQuoteStatus() {
        const quoteEl = document.getElementById('ov-quote-status');
        if (!quoteEl) return;
        const rtStatus = RealtimeQuotes.getStatus();
        if (rtStatus === 'connected') {
            const quotes = RealtimeQuotes.getAllQuotes();
            const count = Object.keys(quotes).length;
            quoteEl.innerHTML = `<span class="text-success">已连接</span> <small class="text-muted">${count}只</small>`;
            quoteEl.className = 'stat-value';
        } else if (rtStatus === 'connecting') {
            quoteEl.innerHTML = '<span class="text-muted">连接中...</span>';
            quoteEl.className = 'stat-value';
        } else {
            quoteEl.innerHTML = '<span class="text-danger">未连接</span>';
            quoteEl.className = 'stat-value';
        }
    },

    _buildWatchlistIndex() {
        this._watchlistRowMap = new Map();
        const rows = document.querySelectorAll('#ov-stocks-table tbody tr');
        rows.forEach(row => {
            const codeCell = row.cells?.[0];
            if (!codeCell) return;
            const code = codeCell.textContent.trim();
            if (code) this._watchlistRowMap.set(code, row);
        });
    },

    _updateWatchlistPrices(quotes) {
        if (!this._watchlistRowMap) this._buildWatchlistIndex();
        for (const [code, q] of Object.entries(quotes)) {
            const row = this._watchlistRowMap.get(code);
            if (!row) continue;
            const nameCell = row.cells?.[1];
            const nameLink = nameCell?.querySelector('.stock-link');
            if (nameLink && q.name && q.name !== '--') {
                nameLink.textContent = q.name;
            }
            const industryCell = row.cells?.[2];
            if (industryCell && q.industry) industryCell.textContent = q.industry;
            const sectorCell = row.cells?.[3];
            if (sectorCell && q.sector) sectorCell.textContent = q.sector;
            const conceptsCell = row.cells?.[4];
            if (conceptsCell && q.concepts) {
                conceptsCell.innerHTML = Watchlist._renderConcepts(q.concepts);
            }
            const priceCell = row.cells?.[5];
            if (priceCell && Number.isFinite(Number(q.price)) && Number(q.price) > 0) {
                priceCell.textContent = '¥' + q.price.toFixed(2);
                priceCell.className = q.change_pct >= 0 ? 'text-up' : 'text-down';
            }
            const changeCell = row.cells?.[6];
            if (changeCell && q.change_pct != null && Number.isFinite(Number(q.change_pct))) {
                const pctText = (q.change_pct >= 0 ? '+' : '') + q.change_pct.toFixed(2) + '%';
                let pctEl = changeCell.querySelector('.change-pct');
                if (!pctEl) {
                    pctEl = document.createElement('span');
                    pctEl.className = 'change-pct';
                    changeCell.textContent = '';
                    changeCell.appendChild(pctEl);
                }
                pctEl.textContent = pctText;
                changeCell.className = q.change_pct >= 0 ? 'text-up' : 'text-down';
            }
        }
    },

    // Tab cache, routing, and title state moved to core/app-shell.js

    paperMultiSearch: null,

    // 快照 / 导出 / 隐私工具已移至 app-archives.js
};

globalThis.App = App;
