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

    init() {
        this._initTheme();
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
        Paper.loadStatus();
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

        const hash = location.hash.slice(1);
        if (hash) this.switchTab(hash);
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
            });
        }
    },

    _initTableSorting() {
        document.querySelectorAll('table.sortable').forEach(t => Utils.initTableSort(t));
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
        if (this.currentTab === tab) return;
        this.currentTab = tab;

        document.querySelectorAll('.nav-link').forEach(l => {
            l.classList.toggle('active', l.dataset.tab === tab);
            l.setAttribute('aria-selected', l.dataset.tab === tab);
        });
        document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
        const panel = document.getElementById('tab-' + tab);
        if (panel) panel.classList.add('active');

        const titles = { overview: '总览', stock: '行情', backtest: '回测', portfolio: '持仓', risk: '风控', alpha: 'AI Alpha', paper: '模拟盘', strategy: '策略管理' };
        document.title = (titles[tab] || '总览') + ' - AI 量化交易系统';
        history.replaceState(null, '', '#' + tab);

        if (tab === 'overview') this._startMarketRefresh();
        else this._stopMarketRefresh();

        if (tab === 'risk') this._rkStartPolling && this._rkStartPolling();
        else this._rkStopPolling && this._rkStopPolling();

        // 缓存策略：首次切换必加载，后续30秒内不重复加载
        const now = Date.now();
        const cached = this._tabCache[tab];
        const stale = !cached || (now - cached > 30000);

        if (tab === 'overview') { if (stale) { this.loadOverview(); this._tabCache[tab] = now; } }
        else if (tab === 'portfolio') { if (stale) { this.loadPortfolio(); this._tabCache[tab] = now; } }
        else if (tab === 'risk') { if (stale) { this.loadRisk(); this._tabCache[tab] = now; } }
        else if (tab === 'strategy') { Strategy.load(); }
        else if (tab === 'alpha') { this.initAlpha(); }
        else if (tab === 'paper') { if (stale) { Paper.loadStatus(); this._tabCache[tab] = now; } }
        else if (tab === 'stock') { StockDetail.refresh(); }
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
            const watchlist = await this.fetchJSON('/api/watchlist').catch(() => []);
            this.watchlistCache = watchlist || [];

            const watchlistFilter = (q) => {
                if (!this.watchlistCache || this.watchlistCache.length === 0) return [];
                if (!q) return this.watchlistCache;
                return this.watchlistCache.filter(s =>
                    s.code.includes(q) || (s.name && s.name.toLowerCase().includes(q))
                );
            };

            this.btMultiSearch = new MultiSearchBox('bt-code', 'bt-code-dropdown', 'bt-codes-tags', { maxResults: 30 });
            this.btMultiSearch.setDataSource(watchlistFilter);

            const alphaSearch = new SearchBox('alpha-code', 'alpha-code-dropdown', {
                maxResults: 30,
                formatItem: (s) => `${s.code} ${s.name || ''}`,
            });
            alphaSearch.setDataSource(watchlistFilter);
            alphaSearch.onSelect((item) => {
                document.getElementById('alpha-code').value = item.code;
            });

            this.paperMultiSearch = new MultiSearchBox('pp-codes', 'pp-codes-dropdown', 'pp-codes-tags', { maxResults: 30 });
            this.paperMultiSearch.setDataSource(watchlistFilter);

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
        this.switchTab('backtest');
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
        const card = document.getElementById('broker-config-card');
        if (!card) return;
        const visible = card.style.display !== 'none';
        card.style.display = visible ? 'none' : '';
        if (!visible) this.loadBrokerConfig();
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
            const res = await fetch('/api/broker', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            this.toast('券商配置已保存', 'success');
        } catch (e) {
            this.toast('保存失败: ' + e.message, 'error');
        }
    },

    async testBrokerConn() {
        try {
            const res = await fetch('/api/broker/test', { method: 'POST' });
            const data = await res.json();
            this.toast(data.message, data.success ? 'success' : 'warning');
        } catch (e) {
            this.toast('连接测试失败: ' + e.message, 'error');
        }
    },

    /* loadRisk 已移至 risk.js */

    _startMarketRefresh() {
        PollManager.cancel('marketRefresh');
        this._refreshMarket();
        PollManager.register('marketRefresh', () => this._refreshMarket(), 10000);
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
};

document.addEventListener('DOMContentLoaded', () => App.init());
