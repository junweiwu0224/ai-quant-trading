/* AI 量化交易系统 - 前端逻辑 */

const App = {
    charts: {},
    stockCache: null,
    currentTab: 'overview',

    /* XSS 防护 */
    escapeHTML(str) {
        if (str == null) return '';
        return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    },

    init() {
        this.bindTabs();
        this.bindBacktest();
        this.setDefaultDate();
        this.loadStockList();
        this.initSearchBox();
        this.initWatchlistSearch();
        this.loadOverview();
        this.loadPaperStatus();

        const hash = location.hash.slice(1);
        if (hash) this.switchTab(hash);
    },

    /* Toast */
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
        setTimeout(() => el.remove(), 3000);
    },

    /* Tab 路由 */
    bindTabs() {
        document.addEventListener('click', (e) => {
            const link = e.target.closest('.nav-link');
            if (!link) return;
            e.preventDefault();
            const tab = link.dataset.tab;
            if (tab) this.switchTab(tab);
        });

        // Tab 键盘导航
        document.addEventListener('keydown', (e) => {
            const link = e.target.closest('.nav-link');
            if (!link) return;
            const links = [...document.querySelectorAll('.nav-link')];
            const idx = links.indexOf(link);
            let next;
            if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
                next = links[(idx + 1) % links.length];
            } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
                next = links[(idx - 1 + links.length) % links.length];
            } else if (e.key === 'Home') {
                next = links[0];
            } else if (e.key === 'End') {
                next = links[links.length - 1];
            }
            if (next) {
                e.preventDefault();
                next.focus();
                next.click();
            }
        });
    },

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

        const titles = { overview: '总览', backtest: '回测', portfolio: '持仓', risk: '风控', alpha: 'AI Alpha', paper: '模拟盘', strategy: '策略管理' };
        document.title = (titles[tab] || '总览') + ' - AI 量化交易系统';

        // 更新 URL hash
        history.replaceState(null, '', '#' + tab);

        if (tab === 'overview') this.loadOverview();
        else if (tab === 'portfolio') this.loadPortfolio();
        else if (tab === 'risk') this.loadRisk();
        else if (tab === 'strategy') this.loadStrategies();
        else if (tab === 'alpha') this.initAlpha();
        else if (tab === 'paper') this.loadPaperStatus();
    },

    setDefaultDate() {
        const today = new Date().toISOString().split('T')[0];
        document.getElementById('bt-end').value = today;
        document.getElementById('alpha-end').value = today;
    },

    /* 股票搜索下拉框 */
    initSearchBox() {
        const input = document.getElementById('bt-code');
        if (!input) return;

        // 创建自定义下拉容器
        let dropdown = input.parentElement.querySelector('.search-dropdown');
        if (!dropdown) {
            dropdown = document.createElement('div');
            dropdown.className = 'search-dropdown';
            dropdown.style.display = 'none';
            input.parentElement.appendChild(dropdown);
        }

        let activeIdx = -1;
        let results = [];
        let debounceTimer = null;

        const showResults = (items) => {
            results = items;
            activeIdx = -1;
            if (items.length === 0) {
                dropdown.style.display = 'none';
                return;
            }
            dropdown.innerHTML = items.map((s, i) =>
                `<div class="search-item" data-idx="${i}">${this.escapeHTML(s.code)} ${this.escapeHTML(s.name)}</div>`
            ).join('');
            dropdown.style.display = 'block';
        };

        const selectItem = (item) => {
            input.value = item.code;
            dropdown.style.display = 'none';
        };

        input.addEventListener('input', () => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                const q = input.value.trim().toLowerCase();
                if (!q || !this.stockCache) { showResults([]); return; }
                const filtered = this.stockCache.filter(s =>
                    s.code.includes(q) || (s.name && s.name.toLowerCase().includes(q))
                ).slice(0, 10);
                showResults(filtered);
            }, 300);
        });

        input.addEventListener('keydown', (e) => {
            if (dropdown.style.display === 'none') return;
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                activeIdx = Math.min(activeIdx + 1, results.length - 1);
                dropdown.querySelectorAll('.search-item').forEach((el, i) => el.classList.toggle('active', i === activeIdx));
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                activeIdx = Math.max(activeIdx - 1, 0);
                dropdown.querySelectorAll('.search-item').forEach((el, i) => el.classList.toggle('active', i === activeIdx));
            } else if (e.key === 'Enter') {
                if (activeIdx >= 0 && results[activeIdx]) {
                    e.preventDefault();
                    selectItem(results[activeIdx]);
                }
            } else if (e.key === 'Escape') {
                dropdown.style.display = 'none';
            }
        });

        input.addEventListener('blur', () => {
            setTimeout(() => { dropdown.style.display = 'none'; }, 200);
            // 验证 6 位代码格式
            const val = input.value.trim();
            if (val && !/^\d{6}$/.test(val)) {
                this.toast('请输入 6 位股票代码', 'error');
            }
        });

        dropdown.addEventListener('mousedown', (e) => {
            const item = e.target.closest('.search-item');
            if (!item) return;
            const idx = parseInt(item.dataset.idx, 10);
            if (results[idx]) selectItem(results[idx]);
        });
    },

    /* 股票列表 */
    async loadStockList() {
        try {
            const res = await fetch('/api/backtest/stocks');
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            this.stockCache = data;
            // 填充 AI Alpha 下拉
            const alphaSelect = document.getElementById('alpha-code');
            if (alphaSelect) {
                alphaSelect.innerHTML = data.map(s =>
                    `<option value="${this.escapeHTML(s.code)}">${this.escapeHTML(s.code)} ${this.escapeHTML(s.name)}</option>`
                ).join('');
            }
        } catch (e) {
            this.toast('股票列表加载失败', 'error');
        }
    },

    async fetchJSON(url) {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`${url} 返回 ${res.status}`);
        return res.json();
    },

    destroyChart(key) {
        if (this.charts[key]) {
            this.charts[key].destroy();
            this.charts[key] = null;
        }
    },

    /* 空图表占位提示 */
    showChartEmpty(canvasId) {
        const el = document.getElementById(canvasId);
        if (!el) return;
        const parent = el.parentElement;
        if (parent && !parent.querySelector('.chart-empty')) {
            const msg = document.createElement('div');
            msg.className = 'chart-empty';
            msg.textContent = '暂无数据';
            parent.style.position = 'relative';
            parent.appendChild(msg);
        }
    },

    /* 按钮 loading 状态辅助 */
    setBtnLoading(btnSelector, loading) {
        const btn = document.querySelector(btnSelector);
        if (!btn) return;
        if (loading) {
            btn.disabled = true;
            btn.dataset.origText = btn.textContent;
            btn.innerHTML = '<span class="spinner"></span>加载中...';
        } else {
            btn.disabled = false;
            btn.textContent = btn.dataset.origText || btn.textContent;
        }
    },

    /* Tab 1: 总览 */
    async loadOverview() {
        const stockCountEl = document.getElementById('ov-stock-count');
        stockCountEl.innerHTML = '<span class="spinner"></span>';

        const refreshBtn = document.querySelector('button[onclick="App.loadOverview()"]');
        if (refreshBtn) { refreshBtn.disabled = true; }

        try {
            const [snapshot, trades, status, equityHistory, watchlist] = await Promise.all([
                this.fetchJSON('/api/portfolio/snapshot'),
                this.fetchJSON('/api/portfolio/trades'),
                this.fetchJSON('/api/system/status'),
                this.fetchJSON('/api/portfolio/equity-history').catch(() => []),
                this.fetchJSON('/api/watchlist').catch(() => []),
            ]);

            const dbStats = status.db_stats || {};
            document.getElementById('ov-stock-count').textContent = dbStats.stock_count || 0;
            document.getElementById('ov-latest-date').textContent = dbStats.latest_date || '无数据';
            document.getElementById('ov-equity').textContent = this.fmt(snapshot.total_equity);
            document.getElementById('ov-trade-count').textContent = trades.length;

            // 系统状态卡片
            const syncEl = document.getElementById('ov-sync-status');
            if (syncEl) syncEl.textContent = dbStats.latest_date ? `已同步 (${dbStats.latest_date})` : '未同步';
            const paperEl = document.getElementById('ov-paper-status');
            if (paperEl) paperEl.textContent = status.paper_running ? '运行中' : '已停止';
            const aiEl = document.getElementById('ov-ai-status');
            if (aiEl) aiEl.textContent = status.ai_model || '--';

            // 自选股列表
            this.renderOverviewWatchlist(watchlist);

            // 最近交易
            const tradesBody = document.querySelector('#ov-trades-table tbody');
            if (trades.length > 0) {
                tradesBody.innerHTML = trades.slice(-10).reverse().map(t => `
                    <tr><td>${this.escapeHTML(t.time) || '--'}</td><td>${this.escapeHTML(t.code)}</td><td class="${t.direction === 'long' ? 'text-success' : 'text-danger'}">${t.direction === 'long' ? '买入' : '卖出'}</td><td>¥${this.escapeHTML(t.price)}</td><td>${this.escapeHTML(t.volume)}</td><td>${this.fmt(t.equity)}</td></tr>
                `).join('');
            }

            // 图表
            this.renderEquityChart(equityHistory);
            this.renderReturnDistribution(equityHistory);
        } catch (e) {
            stockCountEl.textContent = '--';
            this.toast('总览数据加载失败: ' + e.message, 'error');
        } finally {
            if (refreshBtn) { refreshBtn.disabled = false; }
        }
    },

    renderEquityChart(data) {
        this.destroyChart('equity_ov');
        if (!data || data.length === 0) {
            this.showChartEmpty('ov-equity-chart');
            return;
        }
        const ctx = document.getElementById('ov-equity-chart');
        if (!ctx) return;
        this.charts.equity_ov = new Chart(ctx.getContext('2d'), {
            type: 'line',
            data: {
                labels: data.map(p => p.date),
                datasets: [{
                    label: '权益',
                    data: data.map(p => p.equity),
                    borderColor: '#4f8cff',
                    backgroundColor: 'rgba(79,140,255,0.1)',
                    fill: true, pointRadius: 0, borderWidth: 1.5,
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { maxTicksLimit: 10, color: '#71717a' } },
                    y: { ticks: { color: '#71717a' } },
                }
            }
        });
    },

    renderReturnDistribution(data) {
        this.destroyChart('returnDist');
        if (!data || data.length < 2) {
            this.showChartEmpty('ov-return-dist');
            return;
        }
        const ctx = document.getElementById('ov-return-dist');
        if (!ctx) return;

        const returns = [];
        for (let i = 1; i < data.length; i++) {
            const prev = data[i - 1].equity;
            if (prev > 0) returns.push((data[i].equity - prev) / prev);
        }
        if (returns.length === 0) {
            this.showChartEmpty('ov-return-dist');
            return;
        }

        const bins = 20;
        const min = Math.min(...returns);
        const max = Math.max(...returns);
        const step = (max - min) / bins || 0.001;
        const counts = new Array(bins).fill(0);
        const labels = [];
        for (let i = 0; i < bins; i++) {
            const lo = min + i * step;
            labels.push((lo * 100).toFixed(1) + '%');
            returns.forEach(r => {
                if (r >= lo && r < lo + step) counts[i]++;
            });
        }

        this.charts.returnDist = new Chart(ctx.getContext('2d'), {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    data: counts,
                    backgroundColor: counts.map((_, i) => (min + i * step) >= 0 ? 'rgba(52,211,153,0.6)' : 'rgba(239,68,68,0.6)'),
                    borderWidth: 0,
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { maxTicksLimit: 8, color: '#71717a', font: { size: 10 } } },
                    y: { ticks: { color: '#71717a' } },
                }
            }
        });
    },

    renderOverviewWatchlist(stocks) {
        const stockBody = document.querySelector('#ov-stocks-table tbody');
        const hintEl = document.getElementById('ov-stock-hint');
        if (!stockBody) return;

        if (stocks && stocks.length > 0) {
            if (hintEl) hintEl.textContent = `(共 ${stocks.length} 只)`;
            stockBody.innerHTML = stocks.slice(0, 20).map(s => `
                <tr>
                    <td>${this.escapeHTML(s.code)}</td>
                    <td>${this.escapeHTML(s.name) || '--'}</td>
                    <td>${this.escapeHTML(s.industry) || '--'}</td>
                    <td>${s.latest_price ? '¥' + s.latest_price : '--'}</td>
                    <td><button class="btn btn-danger btn-sm" onclick="App.removeFromWatchlist('${this.escapeHTML(s.code)}')">删除</button></td>
                </tr>
            `).join('');
        } else {
            if (hintEl) hintEl.textContent = '';
            stockBody.innerHTML = '<tr><td colspan="5" class="text-muted">暂无自选股，使用上方搜索框添加</td></tr>';
        }
    },

    /* Tab 2: 回测 */
    bindBacktest() {
        document.getElementById('backtest-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const code = document.getElementById('bt-code').value.trim();
            const startDate = document.getElementById('bt-start').value;
            const endDate = document.getElementById('bt-end').value;
            const cash = parseFloat(document.getElementById('bt-cash').value);

            if (!code) { this.toast('请输入股票代码', 'error'); return; }
            if (startDate > endDate) { this.toast('开始日期不能晚于结束日期', 'error'); return; }
            if (cash <= 0) { this.toast('初始资金必须大于 0', 'error'); return; }

            const btn = document.getElementById('bt-run-btn');
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner"></span>运行中...';
            document.getElementById('bt-results').style.display = 'none';

            const body = {
                strategy: document.getElementById('bt-strategy').value,
                codes: [code],
                start_date: startDate, end_date: endDate,
                initial_cash: cash,
                enable_risk: document.getElementById('bt-risk').value === 'true',
            };

            try {
                const res = await fetch('/api/backtest/run', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                this.showBacktestResults(data, body);
                this.toast('回测完成', 'success');
            } catch (err) {
                this.toast('回测失败: ' + err.message, 'error');
            } finally {
                btn.disabled = false;
                btn.textContent = '运行回测';
            }
        });
    },

    showBacktestResults(data, reqBody) {
        const safe = (v, d = 0) => v != null ? v : d;

        document.getElementById('bt-results').style.display = '';
        document.getElementById('bt-return').textContent = (safe(data.total_return) * 100).toFixed(2) + '%';
        document.getElementById('bt-annual').textContent = (safe(data.annual_return) * 100).toFixed(2) + '%';
        document.getElementById('bt-dd').textContent = (safe(data.max_drawdown) * 100).toFixed(2) + '%';
        document.getElementById('bt-sharpe').textContent = safe(data.sharpe_ratio);
        document.getElementById('bt-winrate').textContent = (safe(data.win_rate) * 100).toFixed(1) + '%';
        document.getElementById('bt-trades').textContent = safe(data.total_trades);

        // 收益曲线
        const curve = data.equity_curve || [];
        this.destroyChart('equity');
        if (curve.length > 0) {
            const ctx = document.getElementById('bt-equity-chart').getContext('2d');
            this.charts.equity = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: curve.map(p => p.date),
                    datasets: [{
                        label: '权益',
                        data: curve.map(p => p.equity),
                        borderColor: '#4f8cff',
                        backgroundColor: 'rgba(79,140,255,0.1)',
                        fill: true, pointRadius: 0, borderWidth: 1.5,
                    }]
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { ticks: { maxTicksLimit: 10, color: '#71717a' } },
                        y: { ticks: { color: '#71717a' } },
                    }
                }
            });
        }

        // 交易明细
        const trades = data.trades || [];
        const tbody = document.querySelector('#bt-trades-table tbody');
        if (trades.length > 0) {
            tbody.innerHTML = trades.map(t => `
                <tr><td>${this.escapeHTML(t.datetime) || '--'}</td><td>${this.escapeHTML(t.code)}</td><td class="${t.direction === 'long' ? 'text-success' : 'text-danger'}">${t.direction === 'long' ? '买入' : '卖出'}</td><td>${this.escapeHTML(t.price)}</td><td>${this.escapeHTML(t.volume)}</td><td>${this.escapeHTML(t.entry_price) || '--'}</td></tr>
            `).join('');
        } else {
            tbody.innerHTML = '<tr><td colspan="6" class="text-muted">无交易记录</td></tr>';
        }

        // 风控告警
        const alerts = data.risk_alerts || [];
        if (alerts.length > 0) {
            document.getElementById('bt-alerts-card').style.display = '';
            document.querySelector('#bt-alerts-table tbody').innerHTML = alerts.map(a => `
                <tr><td>${this.escapeHTML(a.date)}</td><td><span class="badge badge-${a.level === 'critical' ? 'danger' : 'warning'}">${this.escapeHTML(a.level)}</span></td><td>${this.escapeHTML(a.category)}</td><td>${this.escapeHTML(a.message)}</td></tr>
            `).join('');
        } else {
            document.getElementById('bt-alerts-card').style.display = 'none';
        }

        // 月度收益和回撤
        if (reqBody) {
            this.loadBacktestCharts(reqBody);
        }
    },

    async loadBacktestCharts(reqBody) {
        try {
            const [monthly, drawdown] = await Promise.all([
                fetch('/api/backtest/monthly-returns', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(reqBody) }).then(r => r.json()),
                fetch('/api/backtest/drawdown', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(reqBody) }).then(r => r.json()),
            ]);
            this.renderMonthlyHeatmap(monthly);
            this.renderDrawdown(drawdown);
        } catch (e) {
            this.toast('月度收益/回撤数据加载失败', 'error');
        }
    },

    renderMonthlyHeatmap(data) {
        const container = document.getElementById('bt-heatmap-container');
        if (!container || !data || data.length === 0) {
            if (container) container.innerHTML = '<p class="text-muted">暂无数据</p>';
            return;
        }

        const years = [...new Set(data.map(d => d.year))].sort();
        let html = '<table class="heatmap-table"><thead><tr><th></th>';
        for (let m = 1; m <= 12; m++) html += `<th>${m}月</th>`;
        html += '</tr></thead><tbody>';

        for (const year of years) {
            html += `<tr><td>${year}</td>`;
            for (let m = 1; m <= 12; m++) {
                const item = data.find(d => d.year === year && d.month === m);
                const val = item ? item.return_pct : null;
                const bg = val == null ? 'var(--surface)' :
                    val > 0 ? `rgba(52,211,153,${Math.min(Math.abs(val) * 5, 1).toFixed(2)})` :
                    `rgba(239,68,68,${Math.min(Math.abs(val) * 5, 1).toFixed(2)})`;
                const text = val != null ? (val * 100).toFixed(1) + '%' : '--';
                html += `<td style="background:${bg}">${text}</td>`;
            }
            html += '</tr>';
        }
        html += '</tbody></table>';
        container.innerHTML = html;
    },

    renderDrawdown(data) {
        this.destroyChart('drawdown');
        if (!data || data.length === 0) {
            this.showChartEmpty('bt-drawdown-chart');
            return;
        }
        const ctx = document.getElementById('bt-drawdown-chart');
        if (!ctx) return;

        this.charts.drawdown = new Chart(ctx.getContext('2d'), {
            type: 'line',
            data: {
                labels: data.map(d => d.date),
                datasets: [{
                    label: '回撤',
                    data: data.map(d => d.drawdown_pct * 100),
                    borderColor: '#ef4444',
                    backgroundColor: 'rgba(239,68,68,0.15)',
                    fill: true, pointRadius: 0, borderWidth: 1.5,
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { maxTicksLimit: 10, color: '#71717a' } },
                    y: { ticks: { color: '#71717a', callback: v => v + '%' } },
                }
            }
        });
    },

    async compareStrategies() {
        const strategies = [...document.querySelectorAll('#bt-compare-section input:checked')].map(el => el.value);
        if (strategies.length === 0) { this.toast('请选择至少一个策略', 'error'); return; }

        const code = document.getElementById('bt-code').value.trim();
        if (!code) { this.toast('请输入股票代码', 'error'); return; }

        const body = {
            strategies,
            codes: [code],
            start_date: document.getElementById('bt-start').value,
            end_date: document.getElementById('bt-end').value,
            initial_cash: parseFloat(document.getElementById('bt-cash').value),
        };

        // 按钮 loading 状态
        const btn = document.querySelector('button[onclick="App.compareStrategies()"]');
        if (btn) { btn.disabled = true; btn.dataset.origText = btn.textContent; btn.innerHTML = '<span class="spinner"></span>对比中...'; }

        try {
            const res = await fetch('/api/backtest/compare', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const results = await res.json();

            if (!results || results.length === 0) { this.toast('无对比数据', 'info'); return; }

            this.destroyChart('compare');
            const ctx = document.getElementById('bt-compare-chart').getContext('2d');
            const colors = ['#4f8cff', '#34d399', '#f59e0b', '#ef4444', '#8b5cf6'];
            const labelMap = { dual_ma: '双均线', bollinger: '布林带', momentum: '动量' };

            this.charts.compare = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: results[0].equity_curve.map(p => p.date),
                    datasets: results.map((r, i) => ({
                        label: labelMap[r.strategy] || r.strategy,
                        data: r.equity_curve.map(p => p.equity),
                        borderColor: colors[i % colors.length],
                        pointRadius: 0, borderWidth: 1.5, fill: false,
                    }))
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { labels: { color: '#e4e4e7' } } },
                    scales: {
                        x: { ticks: { maxTicksLimit: 10, color: '#71717a' } },
                        y: { ticks: { color: '#71717a' } },
                    }
                }
            });
        } catch (e) {
            this.toast('策略对比失败: ' + e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = btn.dataset.origText || '对比'; }
        }
    },

    /* Tab 3: 持仓 */
    async loadPortfolio() {
        // 按钮 loading 状态
        const refreshBtn = document.querySelector('button[onclick="App.loadPortfolio()"]');
        if (refreshBtn) { refreshBtn.disabled = true; }

        try {
            const [snapshot, trades, industry] = await Promise.all([
                this.fetchJSON('/api/portfolio/snapshot'),
                this.fetchJSON('/api/portfolio/trades'),
                this.fetchJSON('/api/portfolio/industry-distribution').catch(() => []),
            ]);

            document.getElementById('pf-equity').textContent = this.fmt(snapshot.total_equity);
            document.getElementById('pf-cash').textContent = this.fmt(snapshot.cash);
            document.getElementById('pf-mv').textContent = this.fmt(snapshot.market_value);
            document.getElementById('pf-count').textContent = snapshot.positions.length;

            // 持仓明细
            const posBody = document.querySelector('#pf-positions tbody');
            if (snapshot.positions.length > 0) {
                posBody.innerHTML = snapshot.positions.map(p => {
                    const pnlClass = p.pnl >= 0 ? 'text-success' : 'text-danger';
                    return `<tr><td>${this.escapeHTML(p.code)}</td><td>${p.volume}</td><td>¥${p.avg_price}</td><td>¥${p.current_price}</td><td>${this.fmt(p.market_value)}</td><td class="${pnlClass}">${p.pnl >= 0 ? '+' : ''}${this.fmt(p.pnl)}</td></tr>`;
                }).join('');
            } else {
                posBody.innerHTML = '<tr><td colspan="6" class="text-muted">暂无持仓数据</td></tr>';
            }

            // 今日交易
            const tradeBody = document.querySelector('#pf-trades tbody');
            if (trades.length > 0) {
                tradeBody.innerHTML = trades.map(t => `
                    <tr><td>${this.escapeHTML(t.time) || '--'}</td><td>${this.escapeHTML(t.code)}</td><td class="${t.direction === 'long' ? 'text-success' : 'text-danger'}">${t.direction === 'long' ? '买入' : '卖出'}</td><td>¥${this.escapeHTML(t.price)}</td><td>${this.escapeHTML(t.volume)}</td><td>${this.fmt(t.equity)}</td></tr>
                `).join('');
            } else {
                tradeBody.innerHTML = '<tr><td colspan="6" class="text-muted">今日无交易</td></tr>';
            }

            // 新增图表
            this.renderPnlChart(snapshot.positions);
            this.renderIndustryChart(industry);
            this.renderAllocationChart(snapshot);
        } catch (e) {
            this.toast('持仓数据加载失败', 'error');
        } finally {
            if (refreshBtn) { refreshBtn.disabled = false; }
        }
    },

    renderPnlChart(positions) {
        this.destroyChart('pnl');
        if (!positions || positions.length === 0) {
            this.showChartEmpty('pf-pnl-chart');
            return;
        }
        const ctx = document.getElementById('pf-pnl-chart');
        if (!ctx) return;

        this.charts.pnl = new Chart(ctx.getContext('2d'), {
            type: 'bar',
            data: {
                labels: positions.map(p => p.code),
                datasets: [{
                    data: positions.map(p => p.pnl),
                    backgroundColor: positions.map(p => p.pnl >= 0 ? 'rgba(52,211,153,0.7)' : 'rgba(239,68,68,0.7)'),
                    borderColor: positions.map(p => p.pnl >= 0 ? '#34d399' : '#ef4444'),
                    borderWidth: 1,
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { color: '#71717a' } },
                    y: { ticks: { color: '#71717a' } },
                }
            }
        });
    },

    renderIndustryChart(data) {
        this.destroyChart('industry');
        if (!data || data.length === 0) {
            this.showChartEmpty('pf-industry-chart');
            return;
        }
        const ctx = document.getElementById('pf-industry-chart');
        if (!ctx) return;

        const colors = ['#4f8cff', '#34d399', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#6b7280', '#14b8a6', '#f97316', '#a855f7'];
        this.charts.industry = new Chart(ctx.getContext('2d'), {
            type: 'pie',
            data: {
                labels: data.map(d => d.industry || '未知'),
                datasets: [{ data: data.map(d => d.value), backgroundColor: colors }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { position: 'right', labels: { color: '#e4e4e7', font: { size: 11 } } } }
            }
        });
    },

    renderAllocationChart(snapshot) {
        this.destroyChart('allocation');
        if (!snapshot || !snapshot.positions || snapshot.positions.length === 0) {
            this.showChartEmpty('pf-allocation-chart');
            return;
        }
        const ctx = document.getElementById('pf-allocation-chart');
        if (!ctx) return;

        const labels = snapshot.positions.map(p => p.code);
        const values = snapshot.positions.map(p => p.market_value);
        if (snapshot.cash > 0) {
            labels.push('现金');
            values.push(snapshot.cash);
        }

        const colors = ['#4f8cff', '#34d399', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#6b7280', '#14b8a6'];
        this.charts.allocation = new Chart(ctx.getContext('2d'), {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{ data: values, backgroundColor: colors }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { position: 'right', labels: { color: '#e4e4e7', font: { size: 11 } } } }
            }
        });
    },

    /* Tab 4: 风控 */
    async loadRisk() {
        // 按钮 loading 状态
        const refreshBtn = document.querySelector('button[onclick="App.loadRisk()"]');
        if (refreshBtn) { refreshBtn.disabled = true; }

        try {
            const risk = await this.fetchJSON('/api/portfolio/risk');
            document.getElementById('rk-equity').textContent = this.fmt(risk.total_equity);
            document.getElementById('rk-cash-pct').textContent = (risk.cash_pct * 100).toFixed(1) + '%';
            document.getElementById('rk-pos-count').textContent = risk.position_count;

            if (risk.positions && risk.positions.length > 0) {
                const labels = risk.positions.map(p => p.code);
                const values = risk.positions.map(p => p.value);
                labels.push('现金');
                values.push(risk.cash);

                this.destroyChart('pos');
                const ctx = document.getElementById('rk-position-chart').getContext('2d');
                this.charts.pos = new Chart(ctx, {
                    type: 'doughnut',
                    data: {
                        labels: labels,
                        datasets: [{ data: values, backgroundColor: ['#4f8cff', '#34d399', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#6b7280'] }]
                    },
                    options: {
                        responsive: true, maintainAspectRatio: false,
                        plugins: { legend: { position: 'right', labels: { color: '#e4e4e7' } } }
                    }
                });
            }
        } catch (e) {
            this.toast('风控数据加载失败', 'error');
        } finally {
            if (refreshBtn) { refreshBtn.disabled = false; }
        }

        try {
            const rules = await this.fetchJSON('/api/system/risk/rules');
            document.querySelector('#rk-rules tbody').innerHTML = rules.map(r => `
                <tr><td>${this.escapeHTML(r.name)}</td><td>${this.escapeHTML(r.threshold)}</td><td>${this.escapeHTML(r.current)}</td><td><span class="badge badge-${r.status === 'ok' ? 'success' : 'danger'}">${r.status === 'ok' ? '正常' : '告警'}</span></td></tr>
            `).join('');
        } catch (e) {
            document.querySelector('#rk-rules tbody').innerHTML = '<tr><td colspan="4" class="text-muted">风控规则加载失败</td></tr>';
        }
    },

    /* Tab 5: AI Alpha */
    initAlpha() {
        if (this.stockCache && this.stockCache.length > 0) {
            const sel = document.getElementById('alpha-code');
            if (sel && sel.options.length === 0) {
                sel.innerHTML = this.stockCache.map(s =>
                    `<option value="${this.escapeHTML(s.code)}">${this.escapeHTML(s.code)} ${this.escapeHTML(s.name)}</option>`
                ).join('');
            }
        }
    },

    async loadAlpha() {
        const code = document.getElementById('alpha-code').value;
        const startDate = document.getElementById('alpha-start').value;
        const endDate = document.getElementById('alpha-end').value;

        if (!code) { this.toast('请选择股票', 'error'); return; }

        // 按钮 loading 状态
        const btn = document.querySelector('button[onclick="App.loadAlpha()"]');
        if (btn) { btn.disabled = true; btn.dataset.origText = btn.textContent; btn.innerHTML = '<span class="spinner"></span>分析中...'; }

        try {
            this.toast('正在分析，请稍候...', 'info');
            const [importance, training, predictionsResp, signals] = await Promise.all([
                this.fetchJSON(`/api/alpha/factor-importance?code=${code}&start_date=${startDate}&end_date=${endDate}`),
                this.fetchJSON(`/api/alpha/training-metrics?code=${code}&start_date=${startDate}&end_date=${endDate}`),
                fetch('/api/alpha/predict', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code, start_date: startDate, end_date: endDate, threshold: 0.5 }) }),
                this.fetchJSON(`/api/alpha/kline-signals?code=${code}&start_date=${startDate}&end_date=${endDate}`),
            ]);

            if (!predictionsResp.ok) throw new Error(`predict 返回 ${predictionsResp.status}`);
            const predictions = await predictionsResp.json();

            this.renderFeatureImportance(importance);
            this.renderTrainingCurve(training);
            this.renderPredictVsActual(predictions);
            this.renderSignalChart(signals, predictions);
            this.toast('分析完成', 'success');
        } catch (e) {
            this.toast('AI Alpha 分析失败: ' + e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = btn.dataset.origText || '分析'; }
        }
    },

    renderFeatureImportance(data) {
        this.destroyChart('feature');
        if (!data || data.length === 0) {
            this.showChartEmpty('alpha-feature-chart');
            return;
        }
        const ctx = document.getElementById('alpha-feature-chart');
        if (!ctx) return;

        this.charts.feature = new Chart(ctx.getContext('2d'), {
            type: 'bar',
            data: {
                labels: data.map(d => d.feature),
                datasets: [{
                    data: data.map(d => d.importance),
                    backgroundColor: 'rgba(79,140,255,0.7)',
                    borderColor: '#4f8cff',
                    borderWidth: 1,
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { color: '#71717a' }, grid: { color: 'rgba(255,255,255,0.05)' } },
                    y: { ticks: { color: '#e4e4e7', font: { size: 11 } } },
                }
            }
        });
    },

    renderTrainingCurve(data) {
        this.destroyChart('training');
        if (!data || !data.epochs || data.epochs.length === 0) {
            this.showChartEmpty('alpha-training-chart');
            return;
        }
        const ctx = document.getElementById('alpha-training-chart');
        if (!ctx) return;

        this.charts.training = new Chart(ctx.getContext('2d'), {
            type: 'line',
            data: {
                labels: data.epochs,
                datasets: [
                    { label: 'Train AUC', data: data.train_auc, borderColor: '#4f8cff', yAxisID: 'y-auc', pointRadius: 0, borderWidth: 1.5 },
                    { label: 'Val AUC', data: data.val_auc, borderColor: '#34d399', yAxisID: 'y-auc', pointRadius: 0, borderWidth: 1.5, borderDash: [5, 3] },
                    { label: 'Train Loss', data: data.train_loss, borderColor: '#f59e0b', yAxisID: 'y-loss', pointRadius: 0, borderWidth: 1.5 },
                    { label: 'Val Loss', data: data.val_loss, borderColor: '#ef4444', yAxisID: 'y-loss', pointRadius: 0, borderWidth: 1.5, borderDash: [5, 3] },
                ]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { labels: { color: '#e4e4e7' } } },
                scales: {
                    x: { ticks: { color: '#71717a', maxTicksLimit: 10 } },
                    'y-auc': { type: 'linear', position: 'left', title: { display: true, text: 'AUC', color: '#71717a' }, ticks: { color: '#71717a' } },
                    'y-loss': { type: 'linear', position: 'right', title: { display: true, text: 'Loss', color: '#71717a' }, ticks: { color: '#71717a' }, grid: { drawOnChartArea: false } },
                }
            }
        });
    },

    renderPredictVsActual(data) {
        this.destroyChart('predict');
        if (!data || !data.predictions || data.predictions.length === 0) {
            this.showChartEmpty('alpha-predict-chart');
            return;
        }
        const ctx = document.getElementById('alpha-predict-chart');
        if (!ctx) return;

        const preds = data.predictions;
        this.charts.predict = new Chart(ctx.getContext('2d'), {
            type: 'line',
            data: {
                labels: preds.map(p => p.date),
                datasets: [
                    { label: '预测概率', data: preds.map(p => p.probability), borderColor: '#4f8cff', pointRadius: 0, borderWidth: 1.5, fill: false },
                    { label: '阈值线', data: preds.map(() => 0.5), borderColor: '#ef4444', borderDash: [5, 5], pointRadius: 0, borderWidth: 1 },
                ]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { labels: { color: '#e4e4e7' } } },
                scales: {
                    x: { ticks: { color: '#71717a', maxTicksLimit: 10 } },
                    y: { min: 0, max: 1, ticks: { color: '#71717a' } },
                }
            }
        });
    },

    renderSignalChart(klineData, predictData) {
        this.destroyChart('signal');
        const ctx = document.getElementById('alpha-signal-chart');
        if (!ctx) return;

        const kline = klineData.kline || [];
        const signals = klineData.signals || [];
        if (kline.length === 0) {
            this.showChartEmpty('alpha-signal-chart');
            return;
        }

        const closeData = kline.map(k => k.close);
        const dates = kline.map(k => k.date);
        const buyDates = new Set(signals.filter(s => s.type === 'buy').map(s => s.date));
        const sellDates = new Set(signals.filter(s => s.type === 'sell').map(s => s.date));

        const buyPoints = dates.map((d, i) => buyDates.has(d) ? closeData[i] : null);
        const sellPoints = dates.map((d, i) => sellDates.has(d) ? closeData[i] : null);

        this.charts.signal = new Chart(ctx.getContext('2d'), {
            type: 'line',
            data: {
                labels: dates,
                datasets: [
                    { label: '收盘价', data: closeData, borderColor: '#71717a', pointRadius: 0, borderWidth: 1.5, fill: false },
                    { label: '买入信号', data: buyPoints, borderColor: '#34d399', pointRadius: 8, pointStyle: 'triangle', showLine: false, pointBackgroundColor: '#34d399' },
                    { label: '卖出信号', data: sellPoints, borderColor: '#ef4444', pointRadius: 8, pointStyle: 'triangle', pointRotation: 180, showLine: false, pointBackgroundColor: '#ef4444' },
                ]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { labels: { color: '#e4e4e7' } } },
                scales: {
                    x: { ticks: { maxTicksLimit: 10, color: '#71717a' } },
                    y: { ticks: { color: '#71717a' } },
                }
            }
        });
    },

    quickBacktest(strategyName) {
        document.getElementById('bt-strategy').value = strategyName;
        this.switchTab('backtest');
    },

    /* ── 自选股管理 ── */
    async addToWatchlist() {
        const input = document.getElementById('watchlist-input');
        if (!input) return;
        const code = input.value.trim();
        if (!code) { this.toast('请输入股票代码', 'error'); return; }
        if (!/^\d{6}$/.test(code)) { this.toast('请输入 6 位股票代码', 'error'); return; }

        try {
            const res = await fetch('/api/watchlist', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
            this.toast(`已添加 ${code}`, 'success');
            input.value = '';
            this.loadOverview();
        } catch (e) {
            this.toast('添加失败: ' + e.message, 'error');
        }
    },

    async removeFromWatchlist(code) {
        if (!confirm(`确定删除 ${code}？`)) return;
        try {
            const res = await fetch(`/api/watchlist/${code}`, { method: 'DELETE' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            this.toast(`已删除 ${code}`, 'success');
            this.loadOverview();
        } catch (e) {
            this.toast('删除失败: ' + e.message, 'error');
        }
    },

    async syncWatchlist() {
        const btn = document.querySelector('button[onclick="App.syncWatchlist()"]');
        if (btn) { btn.disabled = true; btn.dataset.origText = btn.textContent; btn.innerHTML = '<span class="spinner"></span>同步中...'; }
        try {
            const res = await fetch('/api/watchlist/sync', { method: 'POST' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            this.toast(`同步完成: ${data.synced || 0} 只`, 'success');
            this.loadOverview();
        } catch (e) {
            this.toast('同步失败: ' + e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = btn.dataset.origText || '同步数据'; }
        }
    },

    initWatchlistSearch() {
        const input = document.getElementById('watchlist-input');
        if (!input) return;
        const resultsEl = document.getElementById('watchlist-search-results');
        if (!resultsEl) return;

        let debounceTimer = null;
        const hide = () => { resultsEl.style.display = 'none'; resultsEl.innerHTML = ''; };

        input.addEventListener('input', () => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                const q = input.value.trim().toLowerCase();
                if (!q || !this.stockCache) { hide(); return; }
                const filtered = this.stockCache.filter(s =>
                    s.code.includes(q) || (s.name && s.name.toLowerCase().includes(q))
                ).slice(0, 8);
                if (filtered.length === 0) { hide(); return; }
                resultsEl.innerHTML = filtered.map(s =>
                    `<div class="search-item" data-code="${this.escapeHTML(s.code)}">${this.escapeHTML(s.code)} ${this.escapeHTML(s.name)}</div>`
                ).join('');
                resultsEl.style.display = 'block';
            }, 300);
        });

        resultsEl.addEventListener('mousedown', (e) => {
            const item = e.target.closest('.search-item');
            if (!item) return;
            input.value = item.dataset.code;
            hide();
        });

        input.addEventListener('blur', () => setTimeout(hide, 200));
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); this.addToWatchlist(); }
            if (e.key === 'Escape') hide();
        });
    },

    /* ── 模拟盘控制 ── */
    _paperPollInterval: null,

    async startPaper() {
        const codesRaw = document.getElementById('pp-codes').value.trim();
        if (!codesRaw) { this.toast('请输入股票代码', 'error'); return; }
        const codes = codesRaw.split(/[,，\s]+/).filter(Boolean);
        if (codes.length === 0) { this.toast('请输入至少一个股票代码', 'error'); return; }

        const body = {
            strategy: document.getElementById('pp-strategy').value,
            codes,
            interval: parseInt(document.getElementById('pp-interval').value, 10) || 30,
            cash: parseFloat(document.getElementById('pp-cash').value) || 1000000,
            enable_risk: document.getElementById('pp-risk').value === 'true',
        };

        const btn = document.getElementById('pp-start-btn');
        if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>启动中...'; }

        try {
            const res = await fetch('/api/paper/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || data.message || `HTTP ${res.status}`);
            this.toast('模拟盘已启动', 'success');
            this._startPaperPolling();
            this.loadPaperStatus();
        } catch (e) {
            this.toast('启动失败: ' + e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = '启动'; }
        }
    },

    async stopPaper() {
        try {
            const res = await fetch('/api/paper/stop', { method: 'POST' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            this.toast('模拟盘已停止', 'success');
            this._stopPaperPolling();
            this.loadPaperStatus();
        } catch (e) {
            this.toast('停止失败: ' + e.message, 'error');
        }
    },

    async resetPaper() {
        if (!confirm('确定重置模拟盘？将清空所有持仓和交易记录。')) return;
        try {
            const res = await fetch('/api/paper/reset', { method: 'POST' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            this.toast('模拟盘已重置', 'success');
            this._stopPaperPolling();
            this.loadPaperStatus();
        } catch (e) {
            this.toast('重置失败: ' + e.message, 'error');
        }
    },

    async loadPaperStatus() {
        try {
            const data = await this.fetchJSON('/api/paper/status');
            const statusEl = document.getElementById('pp-status');
            const equityEl = document.getElementById('pp-equity');
            const posCountEl = document.getElementById('pp-pos-count');
            const tradeCountEl = document.getElementById('pp-trade-count');
            const startBtn = document.getElementById('pp-start-btn');
            const stopBtn = document.getElementById('pp-stop-btn');

            if (statusEl) {
                statusEl.textContent = data.running ? '运行中' : '已停止';
                statusEl.className = 'stat-value ' + (data.running ? 'text-success' : '');
            }
            if (equityEl) equityEl.textContent = data.equity != null ? this.fmt(data.equity) : '--';
            if (posCountEl) posCountEl.textContent = Object.keys(data.positions || {}).length;
            if (tradeCountEl) tradeCountEl.textContent = data.trade_count || 0;

            if (startBtn) startBtn.disabled = data.running;
            if (stopBtn) stopBtn.disabled = !data.running;

            if (data.running && !this._paperPollInterval) {
                this._startPaperPolling();
            } else if (!data.running && this._paperPollInterval) {
                this._stopPaperPolling();
            }
        } catch (e) {
            // silent
        }
    },

    _startPaperPolling() {
        this._stopPaperPolling();
        this._paperPollInterval = setInterval(() => this.loadPaperStatus(), 5000);
    },

    _stopPaperPolling() {
        if (this._paperPollInterval) {
            clearInterval(this._paperPollInterval);
            this._paperPollInterval = null;
        }
    },

    /* ── 策略管理 ── */
    async loadStrategies() {
        const grid = document.getElementById('st-list');
        grid.innerHTML = '<div class="loading"><span class="spinner"></span>加载中...</div>';

        try {
            const strategies = await this.fetchJSON('/api/strategy/list');
            grid.innerHTML = strategies.map(s => `
                <div class="strategy-card">
                    <h3>${this.escapeHTML(s.label || s.name)}</h3>
                    <span class="strategy-type">${this.escapeHTML(s.type || '自定义')}</span>
                    ${s.builtin ? '<span class="badge badge-info">内置</span>' : ''}
                    <p class="strategy-desc">${this.escapeHTML(s.description)}</p>
                    <div class="strategy-params">参数: ${this.escapeHTML(JSON.stringify(s.params || {}))}</div>
                    <div class="strategy-actions">
                        <button class="btn btn-primary btn-sm" onclick="App.quickBacktest('${this.escapeHTML(s.name)}')">快速回测</button>
                        ${s.builtin ? '' : `
                            <button class="btn btn-sm" onclick="App.editStrategy('${this.escapeHTML(s.name)}')">编辑</button>
                            <button class="btn btn-danger btn-sm" onclick="App.deleteStrategy('${this.escapeHTML(s.name)}')">删除</button>
                        `}
                    </div>
                </div>
            `).join('');
        } catch (e) {
            grid.innerHTML = '<div class="empty-state"><p>策略加载失败，请刷新重试</p></div>';
            this.toast('策略数据加载失败', 'error');
        }
    },

    async createStrategy() {
        const name = prompt('策略名称 (英文, 如 my_strategy):');
        if (!name) return;
        if (!/^[a-zA-Z_]\w*$/.test(name)) { this.toast('策略名只能包含字母、数字和下划线', 'error'); return; }

        const label = prompt('显示名称:');
        if (!label) return;
        const description = prompt('策略描述:') || '';

        try {
            const res = await fetch('/api/strategy', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, label, description, type: '自定义', params: {} }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
            this.toast(`策略 "${label}" 已创建`, 'success');
            this.loadStrategies();
        } catch (e) {
            this.toast('创建失败: ' + e.message, 'error');
        }
    },

    async editStrategy(name) {
        const description = prompt('新描述:');
        if (description === null) return;
        const label = prompt('新显示名称 (留空不变):');

        const body = {};
        if (description) body.description = description;
        if (label) body.label = label;

        try {
            const res = await fetch(`/api/strategy/${name}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
            this.toast('策略已更新', 'success');
            this.loadStrategies();
        } catch (e) {
            this.toast('更新失败: ' + e.message, 'error');
        }
    },

    async deleteStrategy(name) {
        if (!confirm(`确定删除策略 "${name}"？`)) return;
        try {
            const res = await fetch(`/api/strategy/${name}`, { method: 'DELETE' });
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.detail || `HTTP ${res.status}`);
            }
            this.toast('策略已删除', 'success');
            this.loadStrategies();
        } catch (e) {
            this.toast('删除失败: ' + e.message, 'error');
        }
    },

    /* 工具 */
    fmt(value) {
        if (value == null) return '--';
        if (value === 0) return '¥0';
        return '¥' + Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 });
    },
};

document.addEventListener('DOMContentLoaded', () => App.init());
