/* ── AI 量化交易系统 — 核心入口 ── */

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
        if (typeof App.LLM !== 'undefined') App.LLM.toggleCopilot();
    },

    // Tab别名映射 (新Tab名 → 实际面板ID)
    _panelAlias: {
        sim: 'paper',          // 模拟 复用模拟盘面板
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
        if (typeof opts === 'number') opts = { timeout: opts };
        const { timeout = 15000, silent = false, retries = 0, label = '', ...fetchOpts } = opts;

        for (let attempt = 0; attempt <= retries; attempt++) {
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), timeout);
            try {
                const res = await fetch(url, { ...fetchOpts, signal: controller.signal });
                if (!res.ok) {
                    const statusText = { 400: '请求参数错误', 401: '未授权', 403: '无权限', 404: '接口不存在', 500: '服务器内部错误', 502: '服务不可用', 503: '服务维护中' }[res.status] || `HTTP ${res.status}`;
                    throw new Error(label ? `${label}: ${statusText}` : statusText);
                }
                return await res.json();
            } catch (e) {
                clearTimeout(timer);
                const isLast = attempt === retries;
                if (e.name === 'AbortError') {
                    if (isLast && !silent) this.toast(label ? `${label}: 请求超时` : '请求超时，请检查网络', 'error');
                    if (!isLast) { await new Promise(r => setTimeout(r, 1000 * (attempt + 1))); continue; }
                    throw new Error('请求超时');
                }
                if (!navigator.onLine) {
                    if (!silent) this.toast('网络已断开，请检查连接', 'error');
                    throw new Error('网络离线');
                }
                if (isLast) {
                    if (!silent) this.toast(e.message || '请求失败', 'error');
                    throw e;
                }
                await new Promise(r => setTimeout(r, 1000 * (attempt + 1)));
            } finally {
                clearTimeout(timer);
            }
        }
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

    /** 请求通知权限（首次交互时调用） */
    _requestNotifyPermission() {
        if ('Notification' in window && Notification.permission === 'default') {
            Notification.requestPermission();
        }
    },

    /** PWA 离线状态指示条 */
    _initNetworkStatus() {
        const bar = document.getElementById('offline-bar');
        if (!bar) return;

        const update = () => {
            if (navigator.onLine) {
                bar.classList.add('hidden');
            } else {
                bar.classList.remove('hidden');
            }
        };

        window.addEventListener('online', () => {
            update();
            this.toast('网络已恢复', 'success');
        });
        window.addEventListener('offline', () => {
            update();
            this.toast('网络已断开，部分功能不可用', 'warning');
        });
        update();
    },

    /** 统一加入自选股：即时更新表格 + 延迟 enrichment 刷新 */
    async addToWatchlist(code) {
        if (!code) return false;
        try {
            const data = await this.fetchJSON('/api/watchlist', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code }), label: '加入自选股',
            });
            if (!data.success) {
                this.toast(data.error || data.message || '添加失败', 'error');
                return false;
            }
            // 即时追加到本地缓存
            const existing = (this.watchlistCache || []).find(s => s.code === code);
            if (!existing) {
                const item = {
                    code,
                    name: data.name || code,
                    industry: '', sector: '', concepts: [],
                    price: data.price || null,
                    change_pct: data.change_pct != null ? data.change_pct : null,
                };
                this.watchlistCache = [...(this.watchlistCache || []), item];
            }
            // 即时重渲染自选股表格
            Watchlist.render(this.watchlistCache);
            this._watchlistRowMap = null;
            RealtimeQuotes.subscribe([code]);
            this.toast(`${code} ${data.name || ''} 已加入自选股`, 'success');
            // 延迟刷新获取 enrichment（行业/板块/概念/实时行情）
            this._scheduleWatchlistRefresh();
            return true;
        } catch (e) {
            this.toast('加入自选股失败', 'error');
            return false;
        }
    },

    /** 批量加入自选股 */
    async addAllToWatchlist(codes) {
        if (!Array.isArray(codes) || codes.length === 0) return;
        let ok = 0, fail = 0;
        for (const code of codes) {
            const result = await this.addToWatchlist(code);
            if (result) ok++; else fail++;
        }
        if (codes.length > 1) {
            this.toast(`自选股: 成功 ${ok}，失败 ${fail}`, ok > 0 ? 'success' : 'error');
        }
    },

    _watchlistRefreshTimer: null,
    _scheduleWatchlistRefresh() {
        if (this._watchlistRefreshTimer) return;
        this._watchlistRefreshTimer = setTimeout(() => {
            this._watchlistRefreshTimer = null;
            Watchlist._refreshWatchlistTable();
        }, 3000);
    },

    init() {
        this._initTheme();
        this._initV2();
        this.bindTabs();
        this.bindBacktest();
        this.bindOptimize();
        this.bindSensitivity();
        this.bindStrategyChips();
        this.setDefaultDate();
        this.loadStockList();
        this.loadBenchmarks();
        this.initSidebar();
        this.loadOverview();
        this._startMarketRefresh();
        Paper.init();
        Watchlist.init();

        RealtimeQuotes.connect();
        RealtimeQuotes.onUpdate((data) => {
            if (data._status) return;
            this._updateWatchlistPrices(data);
        });
        StockDetail.init();

        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                PollManager.pauseAll();
            } else {
                PollManager.resumeAll();
            }
        });

        document.addEventListener('click', (e) => {
            const link = e.target.closest('.stock-link');
            if (!link) return;
            e.preventDefault();
            const code = link.dataset.code;
            if (code) {
                StockDetail.open(code);
                this.switchTab('stock');
            }
        });

        this._initTableSorting();
        this._initGlobalShortcuts();
        this._initPWA();

        const hash = location.hash.slice(1);
        if (hash) this.switchTab(hash);
    },

    _initV2() {
        // 加载情报页模块
        if (typeof Intelligence !== 'undefined') Intelligence.init();
        // 初始化 Offcanvas 抽屉
        this._initOffcanvas();
        // EventBus 联动
        this._initV2Events();
        // 预移动研发Tab内容
        this._moveResearchPanels();
        this._researchMoved = true;
        // 绑定研发子Tab切换
        this._initResearchSubTabs();
        // 初始化异常聚合条
        this._initAlertAggregator();
        // 请求通知权限
        this._requestNotifyPermission();
        // PWA 离线状态指示
        this._initNetworkStatus();
        console.log('[V2] 5+1导航模式已启用');
    },

    // ── V2: Offcanvas 行情速览抽屉 ──

    _initOffcanvas() {
        const overlay = document.getElementById('offcanvas-overlay');
        const closeBtn = document.getElementById('offcanvas-close');
        if (overlay) overlay.addEventListener('click', () => this.closeOffcanvas());
        if (closeBtn) closeBtn.addEventListener('click', () => this.closeOffcanvas());
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') this.closeOffcanvas();
        });
    },

    async openOffcanvas(code) {
        // 排他性：打开行情抽屉时关闭 Copilot
        if (typeof App.LLM !== 'undefined' && App.LLM.closeCopilot) App.LLM.closeCopilot();

        const panel = document.getElementById('stock-offcanvas');
        const overlay = document.getElementById('offcanvas-overlay');
        const body = document.getElementById('offcanvas-body');
        const title = document.getElementById('offcanvas-title');
        if (!panel || !body) return;

        panel.classList.add('active');
        if (overlay) overlay.classList.add('active');
        panel.setAttribute('aria-hidden', 'false');
        body.innerHTML = '<div class="text-center" style="padding:40px"><span class="spinner"></span> 加载中...</div>';

        try {
            const data = await this.fetchJSON(`/api/stock/detail/${code}`);
            if (!data.success) {
                body.innerHTML = `<div class="text-muted text-center">${this.escapeHTML(data.error || '加载失败')}</div>`;
                return;
            }
            const q = data.quote || {};
            const name = q.name || code;
            if (title) title.textContent = `${name} 行情速览`;

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
                    <span class="oc-quote-code">${this.escapeHTML(code)}</span>
                </div>
                <div class="oc-quote-price ${cls}">¥${q.price != null ? q.price.toFixed(2) : '--'}</div>
                <div class="oc-quote-change ${cls}">${sign}${changeAbs.toFixed(2)} (${sign}${changePct.toFixed(2)}%)</div>
                <div class="oc-metrics">
                    ${metrics.map(([l, v]) => `<div class="oc-metric"><span class="label">${l}</span><span class="value">${v}</span></div>`).join('')}
                </div>
                <div class="oc-actions">
                    <button class="btn btn-sm btn-primary" onclick="App.switchTab('stock'); StockDetail.open('${this.escapeHTML(code)}'); App.closeOffcanvas();">查看详情</button>
                    <button class="btn btn-sm" onclick="App.addToWatchlist('${this.escapeHTML(code)}')">加自选</button>
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

    // ── 异常聚合条 ──

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

        // 监听风控告警事件
        this.on('risk:alert', (data) => {
            this._aggAlerts.push({ level: data.level || 'warn', msg: data.msg || '风控告警', ts: Date.now() });
            this._aggSilenced = false;
            update();
            clearTimeout(this._aggTimer);
            this._aggTimer = setTimeout(() => { this._aggSilenced = true; update(); }, 30000);
        });

        // 监听预警触发事件
        this.on('alert:triggered', (data) => {
            this._aggAlerts.push({ level: 'warn', msg: `预警触发: ${data.code || ''}`, ts: Date.now() });
            this._aggSilenced = false;
            update();
            clearTimeout(this._aggTimer);
            this._aggTimer = setTimeout(() => { this._aggSilenced = true; update(); }, 30000);
        });

        // 手动关闭
        if (dismissBtn) {
            dismissBtn.addEventListener('click', () => {
                this._aggAlerts = [];
                this._aggSilenced = false;
                clearTimeout(this._aggTimer);
                update();
            });
        }
    },

    // ── V2: EventBus 联动 ──

    _initV2Events() {
        // 新闻→行情抽屉
        this.on('news:open-stock', ({ code }) => {
            if (code) this.openOffcanvas(code);
        });

        // 问财→选股器：切换到研发Tab并传递股票池
        this.on('iwencai:send-to-screener', ({ pool, query }) => {
            this.toast(`已推送 ${pool?.length || 0} 只股票至选股器`, 'success');
            this.switchTab('research');
            requestAnimationFrame(() => {
                document.querySelector('.research-sub-tab[data-subtab="screener"]')?.click();
                requestAnimationFrame(() => {
                    if (typeof App.Screener !== 'undefined') {
                        if (App.Screener.init && !this._tabCache['screener']) {
                            App.Screener.init();
                            this._tabCache['screener'] = Date.now();
                        }
                        if (App.Screener.renderFromPool) {
                            App.Screener.renderFromPool(pool, query);
                        }
                    }
                });
            });
        });

        // 问财/AI预测→AI分析：打开 Copilot 并发送分析请求
        this.on('iwencai:analyze', ({ query, data }) => {
            if (typeof App.LLM !== 'undefined') {
                this.toast('已发送至 AI 助手', 'info');
                App.LLM.openCopilot();
                let msg;
                if (data && data.data) {
                    msg = `请分析以下问财查询结果：\n查询：${query}\n数据：${JSON.stringify(data.data.slice(0, 5))}`;
                } else {
                    msg = query;
                }
                setTimeout(() => App.LLM.sendQuick(msg), 400);
            }
        });

        // 热点→问财（已在 intelligence.js 中处理，此处无需重复）

        // 模拟交易下单/撤单后自动刷新持仓数据
        this.on('data:portfolio-updated', ({ source } = {}) => {
            const active = this._activeTab;
            if (active === 'overview') {
                this.loadOverview();
            } else if (active === 'trade') {
                this.loadTradeTab();
            }
        });

        // 时间轴联动：情报→研发（同步日期）
        this.on('timeline:focus', ({ date }) => {
            if (!date) return;
            this.switchTab('research');
            // 延迟确保研发页已激活
            requestAnimationFrame(() => {
                ['alpha-start', 'bt-start', 'ensemble-start'].forEach(id => {
                    const el = document.getElementById(id);
                    if (el && !el.value) el.value = date;
                });
                this.toast(`已联动日期: ${date}`, 'info');
            });
        });
    },

    // ── V2: 研发Tab 子Tab初始化 ──

    _researchMoved: false,
    _researchTabsInited: false,
    _tradeTabsInited: false,

    // 研发页跨子Tab状态同步
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
                // 券商子Tab激活时加载配置
                if (subtab === 'broker' && !this._tabCache['broker']) {
                    this.loadBrokerConfig();
                    this._tabCache['broker'] = Date.now();
                }
                // 触发resize让图表重新计算
                requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
            });
        });
    },

    _initResearchSubTabs() {
        // 首次激活时移动 DOM 元素
        if (!this._researchMoved) {
            this._researchMoved = true;
            this._moveResearchPanels();
        }
        // Bug2修复: 防止重复绑定子Tab事件
        if (this._researchTabsInited) return;
        this._researchTabsInited = true;
        const tabs = document.querySelectorAll('.research-sub-tab');
        if (tabs.length) {
            tabs.forEach(tab => {
                tab.addEventListener('click', () => {
                    this._saveResearchSession();
                    tabs.forEach(t => { t.classList.remove('active'); t.setAttribute('aria-selected', 'false'); });
                    tab.classList.add('active');
                    tab.setAttribute('aria-selected', 'true');
                    document.querySelectorAll('.research-sub-panel').forEach(p => p.classList.remove('active'));
                    const panel = document.getElementById('research-panel-' + tab.dataset.subtab);
                    if (panel) panel.classList.add('active');
                    // 延迟加载子模块
                    this._onResearchSubTabActivate(tab.dataset.subtab);
                    // 应用跨子Tab共享状态（下一帧确保DOM就绪）
                    requestAnimationFrame(() => this._applyResearchSession());
                });
            });
            // 初始化默认子Tab的头部可见性
            const defaultTab = document.querySelector('.research-sub-tab.active');
            if (defaultTab) this._onResearchSubTabActivate(defaultTab.dataset.subtab);
        }
    },

    _moveResearchPanels() {
        const move = (srcId, destId) => {
            const src = document.getElementById(srcId);
            const dest = document.getElementById(destId);
            if (src && dest) {
                while (src.firstChild) dest.appendChild(src.firstChild);
            }
        };

        // 选股器和多股对比已直接放在研发页 HTML 中，无需运行时移动

        // 因子：从 alpha 移动因子研究面板
        move('alpha-panel-factor', 'research-panel-factor');

        // 模型：从 alpha 移动模型分析 + 交易信号 + 模型对比 + Walk-forward
        const modelDest = document.getElementById('research-panel-model');
        const modelSrc = document.getElementById('alpha-panel-model');
        const signalSrc = document.getElementById('alpha-panel-signal');
        const compareSrc = document.getElementById('alpha-panel-compare');
        const wfSrc = document.getElementById('alpha-panel-wf');
        if (modelDest) {
            // 股票选择器提升到研究Tab共享区域（因子/模型/挖掘都需要）
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

        // 回测：移动整个 backtest 面板内容
        const btPanel = document.getElementById('tab-backtest');
        const btDest = document.getElementById('research-panel-backtest');
        if (btPanel && btDest) {
            // 跳过 section 本身，只移动子元素
            while (btPanel.children.length > 0) {
                btDest.appendChild(btPanel.children[0]);
            }
        }

        // LLM：从 alpha 移动 AI 聊天面板到模型子Tab
        move('alpha-panel-llm', 'research-panel-model');

        // 挖掘：从 alpha 移动因子挖掘 + 组合优化
        const miningDest = document.getElementById('research-panel-mining');
        const mineSrc = document.getElementById('alpha-panel-mine');
        const portoptSrc = document.getElementById('alpha-panel-portopt');
        if (miningDest) {
            if (mineSrc) { while (mineSrc.firstChild) miningDest.appendChild(mineSrc.firstChild); }
            if (portoptSrc) { while (portoptSrc.firstChild) miningDest.appendChild(portoptSrc.firstChild); }
        }

        // 策略：移动整个 strategy 面板内容
        const stPanel = document.getElementById('tab-strategy');
        const stDest = document.getElementById('research-panel-strategy');
        if (stPanel && stDest) {
            while (stPanel.children.length > 0) {
                stDest.appendChild(stPanel.children[0]);
            }
        }

        // 风控已作为交易子Tab，无需DOM移动
    },

    _onResearchSubTabActivate(subtab) {
        // 共享头部按需显示 + 控件精准切换
        const alphaHeader = document.querySelector('#tab-research > .page-header');
        const alphaStats = document.getElementById('alpha-perf-stats');
        const modelSel = document.getElementById('alpha-model');
        const analyzeBtn = document.querySelector('button[onclick="App.loadAlpha()"]');
        const optimizeBtn = document.querySelector('button[onclick="App.optimizeAlpha()"]');
        const needsHeader = ['factor', 'model', 'mining'].includes(subtab);

        if (alphaHeader) alphaHeader.style.display = needsHeader ? '' : 'none';
        if (alphaStats) alphaStats.style.display = (subtab === 'model') ? '' : 'none';
        if (modelSel) modelSel.style.display = (subtab === 'model') ? '' : 'none';
        if (analyzeBtn) analyzeBtn.style.display = (subtab === 'model') ? '' : 'none';
        if (optimizeBtn) optimizeBtn.style.display = (subtab === 'model') ? '' : 'none';

        // 切换子Tab时重置共享选择器状态，避免缓存残留
        this._researchActiveSubtab = subtab;
        if (!needsHeader) {
            const codeInput = document.getElementById('alpha-code');
            if (codeInput) codeInput.value = '';
        }

        // 延迟初始化各子模块（首次激活时加载）
        if (subtab === 'backtest') {
            if (typeof Backtest !== 'undefined' && Backtest.load && !this._tabCache['backtest']) {
                Backtest.load();
                this._tabCache['backtest'] = Date.now();
            }
        } else if (subtab === 'factor') {
            if (typeof Factor !== 'undefined' && Factor.init && !this._tabCache['factor']) {
                Factor.init();
                this._tabCache['factor'] = Date.now();
            }
        } else if (subtab === 'strategy') {
            if (typeof Strategy !== 'undefined') Strategy.load();
        } else if (subtab === 'screener') {
            if (typeof App.Screener !== 'undefined' && App.Screener.init && !this._tabCache['screener']) {
                App.Screener.init();
                this._tabCache['screener'] = Date.now();
            }
        } else if (subtab === 'compare') {
            if (typeof App.Compare !== 'undefined' && App.Compare.init && !this._tabCache['compare']) {
                App.Compare.init();
                this._tabCache['compare'] = Date.now();
            }
        } else if (subtab === 'model') {
            if (typeof App.initAlpha === 'function' && !this._tabCache['model']) {
                App.initAlpha();
                this._tabCache['model'] = Date.now();
            }
        }
        // Bug3修复: 子面板激活后触发 resize，让图表重新计算尺寸
        requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
    },

    _initTheme() {
        const saved = localStorage.getItem('theme');
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        const theme = saved || (prefersDark ? 'dark' : 'light');
        document.documentElement.setAttribute('data-theme', theme);

        const btn = document.getElementById('theme-toggle');
        if (btn) {
            btn.addEventListener('click', () => {
                const current = document.documentElement.getAttribute('data-theme');
                const next = current === 'dark' ? 'light' : 'dark';
                document.documentElement.setAttribute('data-theme', next);
                localStorage.setItem('theme', next);
                if (typeof ChartFactory !== 'undefined') ChartFactory._colorCache = null;
            });
        }
    },

    _initPWA() {
        // Service Worker 注册
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.register('/sw.js?v=6', { scope: '/' }).then((reg) => {
                // 强制检查 SW 更新
                reg.update();
                reg.addEventListener('updatefound', () => {
                    const newWorker = reg.installing;
                    newWorker.addEventListener('statechange', () => {
                        if (newWorker.state === 'activated') {
                            location.reload();
                        }
                    });
                });
            }).catch(() => {});
        }

        // 安装提示
        window.addEventListener('beforeinstallprompt', (e) => {
            e.preventDefault();
            this._pwaInstallEvent = e;
            this._showInstallBanner();
        });
    },

    _showInstallBanner() {
        if (localStorage.getItem('pwa_install_dismissed')) return;
        const banner = document.createElement('div');
        banner.id = 'pwa-install-banner';
        banner.style.cssText = 'position:fixed;bottom:60px;left:50%;transform:translateX(-50%);z-index:9999;background:var(--bg-secondary);border:1px solid var(--border-color);border-radius:12px;padding:12px 16px;box-shadow:0 4px 16px rgba(0,0,0,0.3);display:flex;align-items:center;gap:12px;font-size:13px;max-width:90vw';
        banner.innerHTML = `
            <span>安装到桌面，获得更好体验</span>
            <button class="btn btn-sm btn-primary" id="pwa-install-btn">安装</button>
            <button class="btn btn-sm" id="pwa-dismiss-btn" style="opacity:0.6">×</button>
        `;
        document.body.appendChild(banner);
        document.getElementById('pwa-install-btn').onclick = async () => {
            if (this._pwaInstallEvent) {
                this._pwaInstallEvent.prompt();
                const result = await this._pwaInstallEvent.userChoice;
                if (result.outcome === 'accepted') this.toast('已安装到桌面', 'success');
                this._pwaInstallEvent = null;
            }
            banner.remove();
        };
        document.getElementById('pwa-dismiss-btn').onclick = () => {
            localStorage.setItem('pwa_install_dismissed', '1');
            banner.remove();
        };
    },

    _initTableSorting() {
        document.querySelectorAll('table.sortable').forEach(t => Utils.initTableSort(t));
    },

    _initGlobalShortcuts() {
        const tabs = ['overview', 'intelligence', 'research', 'trade', 'sim', 'stock'];
        document.addEventListener('keydown', (e) => {
            const tag = e.target.tagName;
            const isInput = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || e.target.isContentEditable;

            // Escape: 关闭弹窗/overlay/帮助/LLM面板
            if (e.key === 'Escape') {
                const help = document.getElementById('shortcuts-help');
                if (help && help.style.display !== 'none') { help.style.display = 'none'; e.preventDefault(); return; }
                const overlay = document.querySelector('.overlay.active, .modal.active, .drawer.open');
                if (overlay) { overlay.classList.remove('active', 'open'); e.preventDefault(); return; }
                const llmPanel = document.getElementById('llm-panel');
                if (llmPanel && llmPanel.classList.contains('open')) { llmPanel.classList.remove('open'); e.preventDefault(); return; }
            }

            // 以下快捷键在输入框中不生效
            if (isInput) return;

            // Ctrl+K / Cmd+K: 聚焦搜索框
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                const searchInput = document.getElementById('stock-detail-code') || document.querySelector('.search-input');
                if (searchInput) { searchInput.focus(); searchInput.select(); }
                return;
            }

            // /: 聚焦搜索框（无修饰键）
            if (e.key === '/') {
                e.preventDefault();
                const searchInput = document.getElementById('stock-detail-code') || document.querySelector('.search-input');
                if (searchInput) { searchInput.focus(); searchInput.select(); }
                return;
            }

            // Ctrl+1 ~ Ctrl+8: 切换 tab
            if ((e.ctrlKey || e.metaKey) && e.key >= '1' && e.key <= '8') {
                e.preventDefault();
                const idx = parseInt(e.key) - 1;
                if (idx < tabs.length) this.switchTab(tabs[idx]);
                return;
            }

            // Ctrl+0: 切换到总览
            if ((e.ctrlKey || e.metaKey) && e.key === '0') {
                e.preventDefault();
                this.switchTab('overview');
                return;
            }

            // r: 刷新当前 tab 数据
            if (e.key === 'r' && !e.ctrlKey && !e.metaKey) {
                e.preventDefault();
                const activeTab = document.querySelector('.nav-link.active')?.dataset.tab;
                if (activeTab === 'overview') this.loadOverview();
                else if (activeTab === 'paper') PaperTrading?.refresh?.();
                else if (activeTab === 'portfolio') App.Portfolio?.refresh?.();
                return;
            }

            // ?: 显示快捷键帮助
            if (e.key === '?' || (e.shiftKey && e.key === '/')) {
                e.preventDefault();
                this._toggleShortcutsHelp();
                return;
            }

            // Alt+P: Command Palette
            if (e.altKey && e.key === 'p') {
                e.preventDefault();
                this._toggleCommandPalette();
                return;
            }

            // Alt+H: 隐私模式
            if (e.altKey && e.key === 'h') {
                e.preventDefault();
                this.togglePrivacy();
                return;
            }
        });
    },

    _toggleShortcutsHelp() {
        let el = document.getElementById('shortcuts-help');
        if (!el) {
            el = document.createElement('div');
            el.id = 'shortcuts-help';
            el.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);z-index:9999;background:var(--bg-secondary);border:1px solid var(--border-color);border-radius:12px;padding:24px;box-shadow:0 8px 32px rgba(0,0,0,0.3);max-width:400px;width:90%';
            el.innerHTML = `
                <h3 style="margin:0 0 16px;font-size:16px">键盘快捷键</h3>
                <div style="display:grid;grid-template-columns:auto 1fr;gap:8px 16px;font-size:13px">
                    <kbd>/</kbd><span>聚焦搜索框</span>
                    <kbd>Ctrl+K</kbd><span>聚焦搜索框</span>
                    <kbd>Ctrl+0~8</kbd><span>切换页面</span>
                    <kbd>r</kbd><span>刷新当前页</span>
                    <kbd>Alt+P</kbd><span>命令面板</span>
                    <kbd>?</kbd><span>显示/隐藏帮助</span>
                    <kbd>Esc</kbd><span>关闭弹窗/帮助</span>
                </div>
            `;
            document.body.appendChild(el);
        } else {
            el.style.display = el.style.display === 'none' ? '' : 'none';
        }
    },

    /** Command Palette (Alt+P) */
    _toggleCommandPalette() {
        let el = document.getElementById('cmd-palette');
        if (el) {
            el.classList.toggle('hidden');
            if (!el.classList.contains('hidden')) {
                el.querySelector('input')?.focus();
            }
            return;
        }

        // 首次创建
        el = document.createElement('div');
        el.id = 'cmd-palette';
        el.className = 'cmd-palette-overlay';
        el.innerHTML = `
            <div class="cmd-palette">
                <input type="text" class="cmd-palette-input" placeholder="输入命令或搜索..." autocomplete="off" aria-label="命令面板">
                <div class="cmd-palette-list" id="cmd-palette-list"></div>
                <div class="cmd-palette-footer">
                    <span><kbd>↑↓</kbd> 导航</span>
                    <span><kbd>Enter</kbd> 执行</span>
                    <span><kbd>Esc</kbd> 关闭</span>
                </div>
            </div>
        `;
        document.body.appendChild(el);

        const input = el.querySelector('input');
        const list = document.getElementById('cmd-palette-list');

        const commands = [
            { label: '监控', desc: '切换到监控页', icon: '📊', action: () => this.switchTab('overview') },
            { label: '情报', desc: '切换到情报页', icon: '📰', action: () => this.switchTab('intelligence') },
            { label: '研发', desc: '切换到研发页', icon: '🔬', action: () => this.switchTab('research') },
            { label: '交易', desc: '切换到交易页', icon: '💹', action: () => this.switchTab('trade') },
            { label: '模拟', desc: '切换到模拟盘', icon: '🎮', action: () => this.switchTab('sim') },
            { label: '刷新', desc: '刷新当前页数据', icon: '🔄', action: () => { const t = document.querySelector('.nav-link.active')?.dataset.tab; if (t === 'overview') this.loadOverview(); } },
            { label: '搜索', desc: '聚焦搜索框', icon: '🔍', action: () => { document.getElementById('stock-detail-code')?.focus(); } },
            { label: '帮助', desc: '显示快捷键帮助', icon: '❓', action: () => this._toggleShortcutsHelp() },
            { label: '主题', desc: '切换深色/浅色主题', icon: '🎨', action: () => { const t = document.documentElement.getAttribute('data-theme'); document.documentElement.setAttribute('data-theme', t === 'dark' ? 'light' : 'dark'); } },
            { label: '隐私', desc: '切换隐私模式 (Alt+H)', icon: '🙈', action: () => this.togglePrivacy() },
            { label: '导出', desc: 'Emergency Data Dump', icon: '💾', action: () => this.dumpAll() },
        ];

        let selectedIndex = 0;

        const render = (filter = '') => {
            const f = filter.toLowerCase();
            const filtered = f ? commands.filter(c => c.label.toLowerCase().includes(f) || c.desc.toLowerCase().includes(f)) : commands;
            selectedIndex = 0;
            list.innerHTML = filtered.map((c, i) => `
                <div class="cmd-palette-item ${i === 0 ? 'active' : ''}" data-index="${i}">
                    <span class="cmd-palette-icon">${c.icon}</span>
                    <span class="cmd-palette-label">${c.label}</span>
                    <span class="cmd-palette-desc">${c.desc}</span>
                </div>
            `).join('');
            return filtered;
        };

        let filtered = render();

        input.addEventListener('input', () => { filtered = render(input.value); });

        input.addEventListener('keydown', (e) => {
            const items = list.querySelectorAll('.cmd-palette-item');
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                selectedIndex = Math.min(selectedIndex + 1, items.length - 1);
                items.forEach((it, i) => it.classList.toggle('active', i === selectedIndex));
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                selectedIndex = Math.max(selectedIndex - 1, 0);
                items.forEach((it, i) => it.classList.toggle('active', i === selectedIndex));
            } else if (e.key === 'Enter') {
                e.preventDefault();
                if (filtered[selectedIndex]) {
                    filtered[selectedIndex].action();
                    el.classList.add('hidden');
                    input.value = '';
                }
            } else if (e.key === 'Escape') {
                el.classList.add('hidden');
                input.value = '';
            }
        });

        list.addEventListener('click', (e) => {
            const item = e.target.closest('.cmd-palette-item');
            if (item) {
                const idx = parseInt(item.dataset.index);
                if (filtered[idx]) {
                    filtered[idx].action();
                    el.classList.add('hidden');
                    input.value = '';
                }
            }
        });

        // 点击遮罩关闭
        el.addEventListener('click', (e) => {
            if (e.target === el) {
                el.classList.add('hidden');
                input.value = '';
            }
        });

        el.classList.remove('hidden');
        input.focus();
    },

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
            const industryCell = row.cells?.[2];
            if (industryCell && q.industry) industryCell.textContent = q.industry;
            const sectorCell = row.cells?.[3];
            if (sectorCell && q.sector) sectorCell.textContent = q.sector;
            const conceptsCell = row.cells?.[4];
            if (conceptsCell && q.concepts) {
                let c = q.concepts;
                if (typeof c === 'string') c = c.split(',').filter(Boolean);
                if (!Array.isArray(c)) c = [];
                conceptsCell.innerHTML = c.length > 0
                    ? c.slice(0, 3).map(x => `<span class="sd-tag">${App.escapeHTML(x)}</span>`).join('')
                    + (c.length > 3 ? `<span class="text-muted" title="${App.escapeHTML(c.join('、'))}"> +${c.length - 3}</span>` : '')
                    : '--';
            }
            const priceCell = row.cells?.[5];
            if (priceCell) {
                priceCell.textContent = '¥' + q.price.toFixed(2);
                priceCell.className = q.change_pct >= 0 ? 'text-up' : 'text-down';
            }
            const changeCell = row.cells?.[6];
            if (changeCell) {
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

    initSidebar() {
        const collapsed = localStorage.getItem('sidebar-collapsed') === 'true';
        if (collapsed) {
            document.getElementById('sidebar')?.classList.add('collapsed');
            document.body.classList.add('sidebar-collapsed');
        }
    },

    toggleSidebar() {
        const sidebar = document.getElementById('sidebar');
        if (!sidebar) return;
        const collapsed = sidebar.classList.toggle('collapsed');
        document.body.classList.toggle('sidebar-collapsed', collapsed);
        localStorage.setItem('sidebar-collapsed', collapsed);
        const btn = sidebar.querySelector('.sidebar-toggle');
        if (btn) btn.setAttribute('aria-label', collapsed ? '展开导航' : '折叠导航');
    },

    bindTabs() {
        document.addEventListener('click', (e) => {
            const link = e.target.closest('.nav-link');
            if (!link) return;
            e.preventDefault();
            const tab = link.dataset.tab;
            if (tab) this.switchTab(tab);
        });

        document.addEventListener('keydown', (e) => {
            const link = e.target.closest('.nav-link');
            if (!link) return;
            const links = [...document.querySelectorAll('.nav-link')];
            const idx = links.indexOf(link);
            let next;
            if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = links[(idx + 1) % links.length];
            else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = links[(idx - 1 + links.length) % links.length];
            else if (e.key === 'Home') next = links[0];
            else if (e.key === 'End') next = links[links.length - 1];
            if (next) { e.preventDefault(); next.focus(); next.click(); }
        });
    },

    _tabCache: {},

    switchTab(tab) {
        // 旧路由重定向
        const _legacyRedirect = { backtest: 'research', alpha: 'research', portfolio: 'trade', paper: 'sim', strategy: 'research', risk: 'trade' };
        tab = _legacyRedirect[tab] || tab;

        if (this.currentTab === tab) return;
        this.currentTab = tab;

        // Tab → 面板映射（部分Tab复用旧面板）
        const panelId = this._panelAlias[tab] || tab;

        document.querySelectorAll('.nav-link').forEach(l => {
            l.classList.toggle('active', l.dataset.tab === tab);
            l.setAttribute('aria-selected', l.dataset.tab === tab);
        });
        document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
        const panel = document.getElementById('tab-' + panelId);
        if (panel) panel.classList.add('active');

        const titles = {
            overview: '监控', stock: '行情', alpha: 'AI Alpha', paper: '模拟盘', strategy: '策略管理',
            intelligence: '情报', research: '研发', trade: '交易', sim: '模拟',
        };
        document.title = (titles[tab] || '监控') + ' - AI 量化交易系统';
        history.replaceState(null, '', '#' + tab);

        if (tab === 'overview') this._startMarketRefresh();
        else {
            this._stopMarketRefresh();
            if (App._quoteStatusTimer) { clearInterval(App._quoteStatusTimer); App._quoteStatusTimer = null; }
        }

        // 风控内容在交易Tab，切换到交易时启动风控轮询
        if (tab === 'trade') {
            this._rkStartPolling && this._rkStartPolling();
        } else {
            this._rkStopPolling && this._rkStopPolling();
        }

        // 缓存策略：首次切换必加载，后续30秒内不重复加载
        const now = Date.now();
        const cached = this._tabCache[tab];
        const stale = !cached || (now - cached > 30000);

        if (tab === 'overview') { if (stale) { this.loadOverview(); this._tabCache[tab] = now; } }
        else if (tab === 'trade') {
            this._initTradeSubTabs();
            if (stale) { this.loadTradeTab(); this._tabCache[tab] = now; }
        }
        else if (tab === 'strategy') { Strategy.load(); }
        else if (tab === 'research') {
            this._initResearchSubTabs();
        }
        else if (tab === 'paper' || tab === 'sim') { if (stale) { Paper.loadStatus(); this._tabCache[tab] = now; } }
        else if (tab === 'stock') { StockDetail.refresh(); }
        else if (tab === 'intelligence') { if (typeof Intelligence !== 'undefined') Intelligence.load(); }

        // Bug3修复: 延迟触发 resize，解决 ECharts/Chart.js 在隐藏面板中宽高为0的问题
        requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
    },

    async setDefaultDate() {
        let endDate;
        try {
            const status = await this.fetchJSON('/api/system/status');
            endDate = status.db_stats?.latest_date || Utils.todayBeijing();
        } catch {
            endDate = Utils.todayBeijing();
        }

        const d = new Date(endDate);
        const startD = new Date(d);
        startD.setMonth(startD.getMonth() - 1);
        if (startD.getMonth() !== (d.getMonth() - 1 + 12) % 12) {
            startD.setDate(0);
        }
        const startDate = startD.toLocaleDateString('sv-SE', Utils._bjOpts);

        document.getElementById('bt-start').value = startDate;
        document.getElementById('bt-end').value = endDate;
        document.getElementById('alpha-start').value = startDate;
        document.getElementById('alpha-end').value = endDate;
    },

    paperMultiSearch: null,

    async loadStockList() {
        try {
            // 并行加载自选股和全市场股票
            const [watchlist, allStocks] = await Promise.all([
                this.fetchJSON('/api/watchlist').catch(() => []),
                this.fetchJSON('/api/stock/search?q=&limit=6000').catch(() => []),
            ]);
            this.watchlistCache = watchlist || [];
            this._allStocks = allStocks || [];

            // 全市场搜索数据源（本地过滤，响应快）
            const fullMarketFilter = (q) => {
                const list = this._allStocks;
                if (!list || list.length === 0) return [];
                if (!q) return list.slice(0, 50);
                const ql = q.toLowerCase();
                return list.filter(s =>
                    s.code.includes(q) || (s.name && s.name.toLowerCase().includes(ql))
                ).slice(0, 50);
            };

            this.btMultiSearch = new MultiSearchBox('bt-code', 'bt-code-dropdown', 'bt-codes-tags', { maxResults: 30 });
            this.btMultiSearch.setDataSource(fullMarketFilter);

            const alphaSearch = new SearchBox('alpha-code', 'alpha-code-dropdown', {
                maxResults: 30,
                formatItem: (s) => `${s.code} ${s.name || ''}`,
            });
            alphaSearch.setDataSource(fullMarketFilter);
            alphaSearch.onSelect((item) => {
                document.getElementById('alpha-code').value = item.code;
            });

            this.paperMultiSearch = new MultiSearchBox('pp-codes', 'pp-codes-dropdown', 'pp-codes-tags', { maxResults: 30 });
            this.paperMultiSearch.setDataSource(fullMarketFilter);

            Watchlist.setSelected(this.watchlistCache.map(s => s.code));
        } catch (e) {
            this.toast('股票列表加载失败', 'error');
        }
    },

    async loadBenchmarks() {
        try {
            const benchmarks = await this.fetchJSON('/api/backtest/benchmarks');
            const select = document.getElementById('bt-benchmark');
            if (!select || !benchmarks) return;
            benchmarks.forEach(b => {
                const opt = document.createElement('option');
                opt.value = b.code;
                opt.textContent = b.name;
                select.appendChild(opt);
            });
        } catch (e) {
            console.error('基准列表加载失败:', e);
        }
    },

    exportCSV() {
        const data = this._lastBacktestData;
        if (!data) { this.toast('请先运行回测', 'error'); return; }

        const rows = [['日期', '权益']];
        (data.equity_curve || []).forEach(p => rows.push([p.date, p.equity]));
        rows.push([]);
        rows.push(['交易明细']);
        rows.push(['日期', '代码', '方向', '价格', '数量', '入场价']);
        (data.trades || []).forEach(t => {
            rows.push([t.datetime, t.code, t.direction === 'long' ? '买入' : '卖出', t.price, t.volume, t.entry_price || '']);
        });
        rows.push([]);
        rows.push(['统计指标']);
        rows.push(['总收益率', (data.total_return * 100).toFixed(2) + '%']);
        rows.push(['年化收益', (data.annual_return * 100).toFixed(2) + '%']);
        rows.push(['最大回撤', (data.max_drawdown * 100).toFixed(2) + '%']);
        rows.push(['夏普比率', data.sharpe_ratio]);
        rows.push(['Sortino比率', data.sortino_ratio]);
        rows.push(['Calmar比率', data.calmar_ratio]);
        rows.push(['胜率', (data.win_rate * 100).toFixed(1) + '%']);
        rows.push(['盈亏比', data.profit_loss_ratio]);
        rows.push(['交易次数', data.total_trades]);

        const csv = '﻿' + rows.map(r => r.join(',')).join('\n');
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `backtest_${data.start_date}_${data.end_date}.csv`;
        a.click();
        URL.revokeObjectURL(url);
        this.toast('CSV导出成功', 'success');
    },

    async exportPDF() {
        const data = this._lastBacktestData;
        if (!data) { this.toast('请先运行回测', 'error'); return; }

        const btn = event.target;
        btn.disabled = true;
        btn.textContent = '生成中...';

        try {
            const body = {
                strategy: document.getElementById('bt-strategy').value,
                codes: this.btMultiSearch
                    ? this.btMultiSearch.getSelectedCodes()
                    : [document.getElementById('bt-code').value.trim()].filter(Boolean),
                start_date: document.getElementById('bt-start').value,
                end_date: document.getElementById('bt-end').value,
                initial_cash: parseFloat(document.getElementById('bt-cash').value) || 100000,
                commission_rate: parseFloat(document.getElementById('bt-commission').value) || 0.0003,
                stamp_tax_rate: parseFloat(document.getElementById('bt-stamp-tax').value) || 0.001,
                slippage: parseFloat(document.getElementById('bt-slippage').value) || 0.002,
                benchmark: document.getElementById('bt-benchmark').value || '',
                enable_risk: document.getElementById('bt-risk').value === 'true',
            };

            const res = await fetch('/api/backtest/report/pdf', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });

            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `backtest_report_${body.start_date}_${body.end_date}.pdf`;
            a.click();
            URL.revokeObjectURL(url);
            this.toast('PDF报告已生成', 'success');
        } catch (err) {
            this.toast('PDF生成失败: ' + err.message, 'error');
        } finally {
            btn.disabled = false;
            btn.textContent = '导出PDF报告';
        }
    },

    quickBacktest(strategyName) {
        document.getElementById('bt-strategy').value = strategyName;
        this.switchTab('research');
        requestAnimationFrame(() => {
            document.querySelector('.research-sub-tab[data-subtab="backtest"]')?.click();
        });
    },

    bindStrategyChips() {
        document.addEventListener('click', (e) => {
            const chip = e.target.closest('.chip');
            if (!chip) return;
            e.preventDefault();
            const checkbox = chip.querySelector('input[type="checkbox"]');
            if (!checkbox) return;
            checkbox.checked = !checkbox.checked;
            chip.classList.toggle('active', checkbox.checked);
            this.compareStrategies();
        });
    },

    toggleBrokerConfig() {
        // 切换到券商配置子Tab
        const brokerTab = document.querySelector('.trade-sub-tab[data-subtab="broker"]');
        if (brokerTab) brokerTab.click();
    },

    async loadBrokerConfig() {
        try {
            const config = await this.fetchJSON('/api/broker');
            document.getElementById('br-type').value = config.broker_type || 'simulated';
            document.getElementById('br-account').value = config.account_id || '';
            document.getElementById('br-addr').value = config.gateway_addr || '';
            document.getElementById('br-appid').value = config.app_id || '';
            document.getElementById('br-auth').value = config.auth_code || '';
        } catch (e) {
            this.toast('加载券商配置失败', 'error');
        }
    },

    async saveBrokerConfig() {
        const data = {
            broker_type: document.getElementById('br-type').value,
            account_id: document.getElementById('br-account').value.trim(),
            gateway_addr: document.getElementById('br-addr').value.trim(),
            app_id: document.getElementById('br-appid').value.trim(),
            auth_code: document.getElementById('br-auth').value.trim(),
        };
        try {
            await App.fetchJSON('/api/broker', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
                label: '保存券商配置',
            });
            this.toast('券商配置已保存', 'success');
        } catch (e) {
            this.toast('保存失败: ' + e.message, 'error');
        }
    },

    async testBrokerConn() {
        try {
            const data = await App.fetchJSON('/api/broker/test', { method: 'POST', label: '连接测试' });
            const extra = data.stub ? '（桩实现，需部署 Gateway）' : '';
            this.toast(`${data.message}${extra}`, data.success ? 'success' : 'warning');
        } catch (e) {
            this.toast('连接测试失败: ' + e.message, 'error');
        }
    },

    onBrokerTypeChange(type) {
        const addr = document.getElementById('br-addr');
        const account = document.getElementById('br-account');
        const hint = {
            simulated: { addr: '', account: '' },
            ctp: { addr: 'tcp://180.168.146.187:10130', account: '期货账号' },
            xtp: { addr: '交易服务器IP:端口', account: '资金账号' },
        }[type] || {};
        if (addr) addr.placeholder = hint.addr || '网关地址';
        if (account) account.placeholder = hint.account || '券商账户编号';
    },

    /** 统一加载交易Tab数据：共享API只请求一次，分发给持仓和风控模块 */
    async loadTradeTab() {
        try {
            const so = { silent: true };
            // 共享数据：snapshot + equityHistory + industry（3个API只调一次）
            const [snapshot, equityHistory, industry] = await Promise.all([
                this.fetchJSON('/api/portfolio/snapshot', so).catch(() => null),
                this.fetchJSON('/api/portfolio/equity-history', so).catch(() => []),
                this.fetchJSON('/api/portfolio/industry-distribution', so).catch(() => []),
            ]);
            const shared = { snapshot, equityHistory, industry };
            // 并行加载持仓特有数据 + 风控特有数据 + 活跃订单
            await Promise.all([
                this.loadPortfolio(shared),
                this.loadRisk(shared),
                this.loadActiveOrders(),
            ]);
        } catch (e) {
            this.toast('交易数据加载失败: ' + e.message, 'error');
        }
    },

    /* loadRisk 已移至 risk.js */

    /** 加载活跃挂单（交易页） */
    async loadActiveOrders() {
        try {
            const data = await this.fetchJSON('/api/paper/orders?status=pending&page_size=50', { silent: true });
            const orders = data?.data?.items || [];
            this._activeOrders = orders;
            this.renderActiveOrders(orders);
        } catch {
            this._activeOrders = [];
            this.renderActiveOrders([]);
        }
    },

    /** 渲染活跃订单表格 */
    renderActiveOrders(orders) {
        const tbody = document.querySelector('#active-orders-table tbody');
        const countEl = document.getElementById('active-orders-count');
        const panicBtn = document.getElementById('panic-btn');
        if (!tbody) return;

        if (countEl) countEl.textContent = orders.length;
        if (panicBtn) panicBtn.style.display = orders.length > 0 ? '' : 'none';

        if (orders.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-muted text-center">暂无挂单</td></tr>';
            return;
        }

        const typeMap = { market: '市价', limit: '限价', stop_loss: '止损', take_profit: '止盈' };
        tbody.innerHTML = orders.map(o => {
            const dirCls = o.direction === 'buy' ? 'text-up' : 'text-down';
            const dirText = o.direction === 'buy' ? '买入' : '卖出';
            return `<tr>
                <td><a href="#" class="stock-link" data-code="${this.escapeHTML(o.code)}">${this.escapeHTML(o.code)}</a></td>
                <td class="${dirCls}">${dirText}</td>
                <td>${typeMap[o.order_type] || o.order_type}</td>
                <td>${o.price ? '¥' + o.price.toFixed(2) : '市价'}</td>
                <td>${o.volume}</td>
                <td><span class="badge badge-warning">待撮合</span></td>
                <td><button class="btn btn-sm btn-danger" onclick="App.cancelActiveOrder('${o.order_id}')">撤销</button></td>
            </tr>`;
        }).join('');
    },

    /** 撤销单个活跃订单 */
    async cancelActiveOrder(orderId) {
        try {
            await this.fetchJSON(`/api/paper/orders/${orderId}`, { method: 'DELETE' });
            this.toast('订单已撤销', 'success');
            this.loadActiveOrders();
            this.emit('data:portfolio-updated', { source: 'cancel' });
        } catch (e) {
            this.toast('撤销失败: ' + e.message, 'error');
        }
    },

    /** Panic Button：一键全撤 */
    async panicCancelAll() {
        const orders = this._activeOrders || [];
        if (orders.length === 0) return;
        if (!confirm(`确定撤销全部 ${orders.length} 笔挂单？`)) return;

        const panicBtn = document.getElementById('panic-btn');
        if (panicBtn) { panicBtn.disabled = true; panicBtn.textContent = '撤销中...'; }

        try {
            const results = await Promise.allSettled(
                orders.map(o => this.fetchJSON(`/api/paper/orders/${o.order_id}`, { method: 'DELETE' }))
            );
            const succeeded = results.filter(r => r.status === 'fulfilled').length;
            const failed = results.length - succeeded;
            if (failed === 0) {
                this.toast(`已撤销全部 ${succeeded} 笔订单`, 'success');
            } else {
                this.toast(`撤销完成：成功 ${succeeded}，失败 ${failed}`, 'warning');
            }
            this.loadActiveOrders();
            this.emit('data:portfolio-updated', { source: 'panic' });
        } catch (e) {
            this.toast('批量撤销异常: ' + e.message, 'error');
        } finally {
            if (panicBtn) { panicBtn.disabled = false; panicBtn.textContent = '一键全撤'; }
        }
    },

    _startMarketRefresh() {
        PollManager.cancel('marketRefresh');
        this._refreshMarket();
        this._updateMarketStatus();
        // 交易时段 10 秒刷新，非交易时段 60 秒
        const interval = this._isMarketOpen() ? 10000 : 60000;
        PollManager.register('marketRefresh', () => {
            this._refreshMarket();
            this._updateMarketStatus();
        }, interval);
    },

    /** 判断 A 股是否在交易时段（9:15-11:30, 13:00-15:00, 周一至周五） */
    _isMarketOpen() {
        const now = new Date();
        const day = now.getDay();
        if (day === 0 || day === 6) return false;
        const hhmm = now.getHours() * 100 + now.getMinutes();
        return (hhmm >= 915 && hhmm <= 1130) || (hhmm >= 1300 && hhmm <= 1500);
    },

    /** 更新市场状态指示器 */
    _updateMarketStatus() {
        const el = document.getElementById('ov-market-status');
        if (!el) return;
        const now = new Date();
        const day = now.getDay();
        const hhmm = now.getHours() * 100 + now.getMinutes();
        let status, cls;
        if (day === 0 || day === 6) {
            status = '休市'; cls = 'closed';
        } else if (hhmm >= 915 && hhmm < 930) {
            status = '集合竞价'; cls = 'pre';
        } else if ((hhmm >= 930 && hhmm <= 1130) || (hhmm >= 1300 && hhmm <= 1500)) {
            status = '交易中'; cls = 'open';
        } else if (hhmm > 1130 && hhmm < 1300) {
            status = '午间休市'; cls = 'closed';
        } else {
            status = '已收盘'; cls = 'closed';
        }
        el.textContent = status;
        el.className = `market-status-badge ${cls}`;
    },

    _stopMarketRefresh() {
        PollManager.cancel('marketRefresh');
    },

    async _refreshMarket() {
        try {
            const [indices, hotSectors] = await Promise.all([
                this.fetchJSON('/api/stock/market/indices').catch(() => []),
                this.fetchJSON('/api/stock/market/hot-sectors').catch(() => ({ industries: [], concepts: [] })),
            ]);
            this.renderMarketIndices(indices);
            this.renderHotSectors(hotSectors);
        } catch (e) {
            console.warn('市场数据刷新失败:', e);
        }
    },

    // ── 实验快照系统 ──

    _SNAPSHOT_KEY: 'quant_snapshots',
    _SIM_SNAPSHOT_KEY: 'quant_sim_snapshots',

    /** 保存当前研发页实验状态为快照 */
    saveSnapshot(name) {
        const snapshot = {
            id: Date.now().toString(36),
            name: name || `实验 ${new Date().toLocaleString('zh-CN')}`,
            timestamp: Date.now(),
            data: {},
        };

        // 收集各子Tab的输入状态
        const fields = {
            'alpha-code': 'alpha-code', 'alpha-start': 'alpha-start', 'alpha-end': 'alpha-end',
            'bt-code': 'bt-code', 'bt-start': 'bt-start', 'bt-end': 'bt-end', 'bt-cash': 'bt-cash',
            'bt-strategy': 'bt-strategy', 'bt-benchmark': 'bt-benchmark',
            'ensemble-codes': 'ensemble-codes', 'ensemble-start': 'ensemble-start', 'ensemble-end': 'ensemble-end',
            'compare-codes-input': 'compare-codes-input',
        };
        for (const [key, id] of Object.entries(fields)) {
            const el = document.getElementById(id);
            if (el?.value) snapshot.data[key] = el.value;
        }

        // 保存到 localStorage
        const snapshots = this._loadSnapshots();
        snapshots.unshift(snapshot);
        // 最多保留 20 个
        if (snapshots.length > 20) snapshots.length = 20;
        localStorage.setItem(this._SNAPSHOT_KEY, JSON.stringify(snapshots));
        this.toast(`快照已保存: ${snapshot.name}`, 'success');
        return snapshot;
    },

    /** 加载快照到研发页 */
    loadSnapshot(id) {
        const snapshots = this._loadSnapshots();
        const snap = snapshots.find(s => s.id === id);
        if (!snap) { this.toast('快照不存在', 'error'); return; }

        for (const [key, value] of Object.entries(snap.data)) {
            const el = document.getElementById(key);
            if (el) el.value = value;
        }
        this._researchSession = { ...this._researchSession, ...snap.data };
        this.toast(`已加载快照: ${snap.name}`, 'success');
    },

    /** 导出所有快照为 JSON 文件 */
    exportSnapshots() {
        const snapshots = this._loadSnapshots();
        if (snapshots.length === 0) { this.toast('没有可导出的快照', 'info'); return; }

        const blob = new Blob([JSON.stringify(snapshots, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `quant-snapshots-${new Date().toISOString().slice(0, 10)}.json`;
        a.click();
        URL.revokeObjectURL(url);
        this.toast('快照已导出', 'success');
    },

    /** 从 JSON 文件导入快照 */
    importSnapshots(file) {
        const reader = new FileReader();
        reader.onload = () => {
            try {
                const imported = JSON.parse(reader.result);
                if (!Array.isArray(imported)) throw new Error('格式错误');
                const existing = this._loadSnapshots();
                const merged = [...imported, ...existing];
                // 去重（按 id）
                const unique = merged.filter((s, i, arr) => arr.findIndex(x => x.id === s.id) === i);
                if (unique.length > 20) unique.length = 20;
                localStorage.setItem(this._SNAPSHOT_KEY, JSON.stringify(unique));
                this.toast(`已导入 ${imported.length} 个快照`, 'success');
            } catch (e) {
                this.toast('导入失败: ' + e.message, 'error');
            }
        };
        reader.readAsText(file);
    },

    _loadSnapshots() {
        try {
            return JSON.parse(localStorage.getItem(this._SNAPSHOT_KEY) || '[]');
        } catch {
            return [];
        }
    },

    // ── 模拟盘策略对比 ──

    /** 保存当前模拟盘绩效快照 */
    saveSimSnapshot() {
        const metrics = {
            id: Date.now().toString(36),
            name: `策略 ${new Date().toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}`,
            timestamp: Date.now(),
            cumReturn: document.getElementById('pt-cumulative-return')?.textContent || '--',
            maxDD: document.getElementById('pt-max-drawdown')?.textContent || '--',
            sharpe: document.getElementById('pt-sortino-ratio')?.textContent || '--',
            winRate: document.getElementById('pt-win-rate-perf')?.textContent || '--',
        };

        const snapshots = this._loadSimSnapshots();
        snapshots.unshift(metrics);
        if (snapshots.length > 10) snapshots.length = 10;
        localStorage.setItem(this._SIM_SNAPSHOT_KEY, JSON.stringify(snapshots));
        this.renderSimCompare();
        this.toast('模拟盘快照已保存', 'success');
    },

    /** 渲染策略对比表 */
    renderSimCompare() {
        const tbody = document.querySelector('#sim-compare-table tbody');
        if (!tbody) return;
        const snapshots = this._loadSimSnapshots();
        if (snapshots.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-muted text-center">暂无对比数据，点击"保存当前快照"</td></tr>';
            return;
        }
        tbody.innerHTML = snapshots.map(s => {
            const date = new Date(s.timestamp).toLocaleDateString('zh-CN');
            return `<tr>
                <td>${this.escapeHTML(s.name)}</td>
                <td>${date}</td>
                <td>${s.cumReturn}</td>
                <td>${s.maxDD}</td>
                <td>${s.sharpe}</td>
                <td>${s.winRate}</td>
                <td><button class="btn btn-sm" onclick="App.deleteSimSnapshot('${s.id}')">删除</button></td>
            </tr>`;
        }).join('');
    },

    deleteSimSnapshot(id) {
        const snapshots = this._loadSimSnapshots().filter(s => s.id !== id);
        localStorage.setItem(this._SIM_SNAPSHOT_KEY, JSON.stringify(snapshots));
        this.renderSimCompare();
    },

    _loadSimSnapshots() {
        try {
            return JSON.parse(localStorage.getItem(this._SIM_SNAPSHOT_KEY) || '[]');
        } catch {
            return [];
        }
    },

    // ── Emergency Data Dump ──

    /** 导出所有关键数据（dump all） */
    async dumpAll() {
        this.toast('正在导出数据...', 'info');
        const so = { silent: true };
        const [snapshot, trades, watchlist, alerts, qlib, status] = await Promise.allSettled([
            this.fetchJSON('/api/portfolio/snapshot', so),
            this.fetchJSON('/api/portfolio/trades/recent?limit=100', so),
            this.fetchJSON('/api/watchlist', so),
            this.fetchJSON('/api/alerts/rules', so),
            this.fetchJSON('/api/qlib/top?top_n=50', so),
            this.fetchJSON('/api/system/status', so),
        ]);

        const dump = {
            version: '1.0',
            timestamp: new Date().toISOString(),
            portfolio: snapshot.status === 'fulfilled' ? snapshot.value : null,
            trades: trades.status === 'fulfilled' ? trades.value : null,
            watchlist: watchlist.status === 'fulfilled' ? watchlist.value : null,
            alerts: alerts.status === 'fulfilled' ? alerts.value : null,
            qlib: qlib.status === 'fulfilled' ? qlib.value : null,
            system: status.status === 'fulfilled' ? status.value : null,
            snapshots: this._loadSnapshots(),
            simSnapshots: this._loadSimSnapshots(),
            localStorage: { ...localStorage },
        };

        const blob = new Blob([JSON.stringify(dump, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `quant-dump-${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.json`;
        a.click();
        URL.revokeObjectURL(url);
        this.toast('数据导出完成', 'success');
    },

    // ── 隐私模式 ──

    _privacyMode: false,

    togglePrivacy() {
        this._privacyMode = !this._privacyMode;
        document.documentElement.classList.toggle('privacy-mode', this._privacyMode);
        this.toast(this._privacyMode ? '隐私模式已开启' : '隐私模式已关闭', 'info');
    },
};

document.addEventListener('DOMContentLoaded', () => App.init());
