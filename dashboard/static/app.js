/* ── AI 量化交易系统 — 前端逻辑 ── */

const App = {
    charts: {},
    stockCache: null,

    init() {
        this.bindTabs();
        this.bindBacktest();
        this.setDefaultDate();
        this.handleHashRoute();
        this.loadStockList();
        window.addEventListener('hashchange', () => this.handleHashRoute());
    },

    /* ── Toast 通知 ── */
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

    /* ── URL Hash 路由 ── */
    handleHashRoute() {
        const hash = location.hash.replace('#', '') || 'overview';
        const validTabs = ['overview', 'backtest', 'portfolio', 'risk', 'strategy'];
        const tab = validTabs.includes(hash) ? hash : 'overview';
        this.switchTab(tab, false);
    },

    /* ── Tab 路由 ── */
    bindTabs() {
        document.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                this.switchTab(link.dataset.tab, true);
            });
        });
    },

    switchTab(tab, updateHash = true) {
        document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
        document.querySelectorAll(`.nav-link[data-tab="${tab}"]`).forEach(l => l.classList.add('active'));
        document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
        document.getElementById(`tab-${tab}`).classList.add('active');

        if (updateHash) history.replaceState(null, '', `#${tab}`);

        // 更新标题
        const titles = { overview: '总览', backtest: '回测', portfolio: '持仓', risk: '风控', strategy: '策略管理' };
        document.title = `${titles[tab] || '总览'} - AI 量化交易系统`;

        // 懒加载
        const loaders = {
            overview: () => this.loadOverview(),
            portfolio: () => this.loadPortfolio(),
            risk: () => this.loadRisk(),
            strategy: () => this.loadStrategies(),
        };
        if (loaders[tab]) loaders[tab]();
    },

    setDefaultDate() {
        const today = new Date().toISOString().split('T')[0];
        document.getElementById('bt-end').value = today;
    },

    /* ── 股票列表（缓存） ── */
    async loadStockList() {
        try {
            const res = await fetch('/api/backtest/stocks');
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            this.stockCache = data;
            const list = document.getElementById('stock-list');
            list.innerHTML = data.map(s =>
                `<option value="${s.code}">${s.code} ${s.name}</option>`
            ).join('');
        } catch (e) {
            this.toast('股票列表加载失败', 'error');
        }
    },

    /* ── 安全获取数据 ── */
    async fetchJSON(url) {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`${url} 返回 ${res.status}`);
        return res.json();
    },

    /* ── Tab 1: 总览 ── */
    async loadOverview() {
        const stockCountEl = document.getElementById('ov-stock-count');
        stockCountEl.innerHTML = '<span class="spinner"></span>';

        try {
            const [snapshot, trades, status] = await Promise.all([
                this.fetchJSON('/api/portfolio/snapshot'),
                this.fetchJSON('/api/portfolio/trades'),
                this.fetchJSON('/api/system/status'),
            ]);

            // 使用缓存的股票列表，避免重复请求
            const stocks = this.stockCache || [];

            const dbStats = status.db_stats || {};
            document.getElementById('ov-stock-count').textContent = dbStats.stock_count || 0;
            document.getElementById('ov-latest-date').textContent = dbStats.latest_date || '无数据';
            document.getElementById('ov-equity').textContent = this.fmt(snapshot.total_equity);
            document.getElementById('ov-trade-count').textContent = trades.length;

            // 模块网格
            const modulesHtml = status.modules.map(m => `
                <div class="module-item">
                    <h3>${m.name}</h3>
                    <p>${m.desc}</p>
                    <span class="badge badge-${m.status === 'current' ? 'info' : 'success'}">${m.status === 'current' ? '当前' : '已完成'}</span>
                </div>
            `).join('');
            document.getElementById('ov-modules').innerHTML = modulesHtml;

            // 股票列表
            const stockBody = document.querySelector('#ov-stocks-table tbody');
            if (stocks.length > 0) {
                document.getElementById('ov-stock-hint').textContent = `(共 ${stocks.length} 只)`;
                stockBody.innerHTML = stocks.slice(0, 30).map(s => `
                    <tr>
                        <td>${s.code}</td>
                        <td>${s.name || '--'}</td>
                        <td>${s.industry || '--'}</td>
                    </tr>
                `).join('');
            } else {
                stockBody.innerHTML = '<tr><td colspan="3" class="text-muted">数据库中暂无股票数据，请先运行数据采集</td></tr>';
            }

            // 最近交易
            const tradesBody = document.querySelector('#ov-trades-table tbody');
            if (trades.length > 0) {
                tradesBody.innerHTML = trades.slice(-10).reverse().map(t => `
                    <tr>
                        <td>${t.time || '--'}</td>
                        <td>${t.code}</td>
                        <td class="${t.direction === 'long' ? 'text-success' : 'text-danger'}">${t.direction === 'long' ? '买入' : '卖出'}</td>
                        <td>¥${t.price}</td>
                        <td>${t.volume}</td>
                        <td>${this.fmt(t.equity)}</td>
                    </tr>
                `).join('');
            }
        } catch (e) {
            stockCountEl.textContent = '--';
            this.toast('总览数据加载失败: ' + e.message, 'error');
        }
    },

    /* ── Tab 2: 回测 ── */
    bindBacktest() {
        document.getElementById('backtest-form').addEventListener('submit', async (e) => {
            e.preventDefault();

            // 表单验证
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

            // 清除旧结果
            document.getElementById('bt-results').style.display = 'none';

            const body = {
                strategy: document.getElementById('bt-strategy').value,
                codes: [code],
                start_date: startDate,
                end_date: endDate,
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
                this.showBacktestResults(data);
                this.toast('回测完成', 'success');
            } catch (err) {
                this.toast('回测失败: ' + err.message, 'error');
            } finally {
                btn.disabled = false;
                btn.textContent = '运行回测';
            }
        });
    },

    showBacktestResults(data) {
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
        if (this.charts.equity) this.charts.equity.destroy();
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
                        fill: true,
                        pointRadius: 0,
                        borderWidth: 1.5,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { display: true, ticks: { maxTicksLimit: 10, color: '#71717a' } },
                        y: { display: true, ticks: { color: '#71717a' } },
                    }
                }
            });
        }

        // 交易明细
        const trades = data.trades || [];
        const tbody = document.querySelector('#bt-trades-table tbody');
        if (trades.length > 0) {
            tbody.innerHTML = trades.map(t => `
                <tr>
                    <td>${t.datetime || '--'}</td>
                    <td>${t.code}</td>
                    <td class="${t.direction === 'long' ? 'text-success' : 'text-danger'}">${t.direction === 'long' ? '买入' : '卖出'}</td>
                    <td>${t.price}</td>
                    <td>${t.volume}</td>
                    <td>${t.entry_price || '--'}</td>
                </tr>
            `).join('');
        } else {
            tbody.innerHTML = '<tr><td colspan="6" class="text-muted">无交易记录</td></tr>';
        }

        // 风控告警
        const alerts = data.risk_alerts || [];
        if (alerts.length > 0) {
            document.getElementById('bt-alerts-card').style.display = '';
            document.querySelector('#bt-alerts-table tbody').innerHTML = alerts.map(a => `
                <tr>
                    <td>${a.date}</td>
                    <td><span class="badge badge-${a.level === 'critical' ? 'danger' : 'warning'}">${a.level}</span></td>
                    <td>${a.category}</td>
                    <td>${a.message}</td>
                </tr>
            `).join('');
        } else {
            document.getElementById('bt-alerts-card').style.display = 'none';
        }
    },

    /* ── Tab 3: 持仓 ── */
    async loadPortfolio() {
        try {
            const [snapshot, trades] = await Promise.all([
                this.fetchJSON('/api/portfolio/snapshot'),
                this.fetchJSON('/api/portfolio/trades'),
            ]);

            document.getElementById('pf-equity').textContent = this.fmt(snapshot.total_equity);
            document.getElementById('pf-cash').textContent = this.fmt(snapshot.cash);
            document.getElementById('pf-mv').textContent = this.fmt(snapshot.market_value);
            document.getElementById('pf-count').textContent = snapshot.positions.length;

            // 持仓明细
            const posBody = document.querySelector('#pf-positions tbody');
            if (snapshot.positions.length > 0) {
                posBody.innerHTML = snapshot.positions.map(p => `
                    <tr>
                        <td>${p.code}</td>
                        <td>${p.volume}</td>
                        <td>¥${p.avg_price}</td>
                        <td>${this.fmt(p.market_value)}</td>
                        <td>${snapshot.total_equity > 0 ? (p.market_value / snapshot.total_equity * 100).toFixed(1) : 0}%</td>
                    </tr>
                `).join('');
            } else {
                posBody.innerHTML = '<tr><td colspan="5" class="text-muted">暂无持仓数据</td></tr>';
            }

            // 今日交易
            const tradeBody = document.querySelector('#pf-trades tbody');
            if (trades.length > 0) {
                tradeBody.innerHTML = trades.map(t => `
                    <tr>
                        <td>${t.time || '--'}</td>
                        <td>${t.code}</td>
                        <td class="${t.direction === 'long' ? 'text-success' : 'text-danger'}">${t.direction === 'long' ? '买入' : '卖出'}</td>
                        <td>¥${t.price}</td>
                        <td>${t.volume}</td>
                        <td>${this.fmt(t.equity)}</td>
                    </tr>
                `).join('');
            } else {
                tradeBody.innerHTML = '<tr><td colspan="6" class="text-muted">今日无交易</td></tr>';
            }
        } catch (e) {
            this.toast('持仓数据加载失败', 'error');
        }
    },

    /* ── Tab 4: 风控 ── */
    async loadRisk() {
        try {
            const risk = await this.fetchJSON('/api/portfolio/risk');

            document.getElementById('rk-equity').textContent = this.fmt(risk.total_equity);
            document.getElementById('rk-cash-pct').textContent = (risk.cash_pct * 100).toFixed(1) + '%';
            document.getElementById('rk-pos-count').textContent = risk.position_count;

            // 仓位分布饼图
            if (risk.positions && risk.positions.length > 0) {
                const labels = risk.positions.map(p => p.code);
                const values = risk.positions.map(p => p.value);
                labels.push('现金');
                values.push(risk.cash);

                if (this.charts.pos) this.charts.pos.destroy();
                const ctx = document.getElementById('rk-position-chart').getContext('2d');
                this.charts.pos = new Chart(ctx, {
                    type: 'doughnut',
                    data: {
                        labels: labels,
                        datasets: [{
                            data: values,
                            backgroundColor: ['#4f8cff', '#34d399', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#6b7280'],
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { position: 'right', labels: { color: '#e4e4e7' } } }
                    }
                });
            }
        } catch (e) {
            this.toast('风控数据加载失败', 'error');
        }

        // 风控规则（独立请求，失败不影响其他）
        try {
            const rules = await this.fetchJSON('/api/system/risk/rules');
            const rulesBody = document.querySelector('#rk-rules tbody');
            rulesBody.innerHTML = rules.map(r => `
                <tr>
                    <td>${r.name}</td>
                    <td>${r.threshold}</td>
                    <td>${r.current}</td>
                    <td><span class="badge badge-${r.status === 'ok' ? 'success' : 'danger'}">${r.status === 'ok' ? '正常' : '告警'}</span></td>
                </tr>
            `).join('');
        } catch (e) {
            // 风控规则加载失败静默处理
        }
    },

    /* ── Tab 5: 策略管理 ── */
    async loadStrategies() {
        const grid = document.getElementById('st-list');
        grid.innerHTML = '<div class="loading"><span class="spinner"></span>加载中...</div>';

        try {
            const strategies = await this.fetchJSON('/api/system/strategies');
            grid.innerHTML = strategies.map(s => `
                <div class="strategy-card">
                    <h3>${s.label}</h3>
                    <span class="strategy-type">${s.type}</span>
                    <p class="strategy-desc">${s.description}</p>
                    <div class="strategy-params">参数: ${JSON.stringify(s.params)}</div>
                    <div class="strategy-actions">
                        <button class="btn btn-primary btn-sm" onclick="App.quickBacktest('${s.name}')">快速回测</button>
                    </div>
                </div>
            `).join('');
        } catch (e) {
            grid.innerHTML = '<div class="empty-state"><p>策略加载失败，请刷新重试</p></div>';
            this.toast('策略数据加载失败', 'error');
        }
    },

    quickBacktest(strategyName) {
        document.getElementById('bt-strategy').value = strategyName;
        this.switchTab('backtest', true);
    },

    /* ── 工具函数 ── */
    fmt(value) {
        if (value == null) return '--';
        if (value === 0) return '¥0';
        return '¥' + Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 });
    },
};

// 启动
document.addEventListener('DOMContentLoaded', () => App.init());
