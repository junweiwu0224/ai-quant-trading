/* ── AI 量化交易系统 — 前端逻辑 ── */

const App = {
    charts: {},

    init() {
        this.bindTabs();
        this.bindBacktest();
        this.setDefaultDate();
        this.loadOverview();
        this.loadStockList();
    },

    /* ── Tab 路由 ── */
    bindTabs() {
        document.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const tab = link.dataset.tab;
                this.switchTab(tab);
            });
        });
    },

    switchTab(tab) {
        document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
        document.querySelectorAll(`.nav-link[data-tab="${tab}"]`).forEach(l => l.classList.add('active'));
        document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
        document.getElementById(`tab-${tab}`).classList.add('active');

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

    /* ── 股票搜索自动补全 ── */
    async loadStockList() {
        try {
            const res = await fetch('/api/backtest/stocks');
            const data = await res.json();
            const list = document.getElementById('stock-list');
            list.innerHTML = data.map(s =>
                `<option value="${s.code}">${s.code} ${s.name}</option>`
            ).join('');
        } catch (e) {
            // 静默失败
        }
    },

    /* ── Tab 1: 总览 ── */
    async loadOverview() {
        try {
            const [snapshot, trades, status, stocks] = await Promise.all([
                fetch('/api/portfolio/snapshot').then(r => r.json()),
                fetch('/api/portfolio/trades').then(r => r.json()),
                fetch('/api/system/status').then(r => r.json()),
                fetch('/api/backtest/stocks').then(r => r.json()),
            ]);

            // 统计卡片
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
            if (trades.length > 0) {
                const tbody = document.querySelector('#ov-trades-table tbody');
                tbody.innerHTML = trades.slice(-10).reverse().map(t => `
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
            console.log('总览数据加载失败:', e);
        }
    },

    /* ── Tab 2: 回测 ── */
    bindBacktest() {
        document.getElementById('backtest-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const btn = document.getElementById('bt-run-btn');
            btn.disabled = true;
            btn.textContent = '运行中...';

            const body = {
                strategy: document.getElementById('bt-strategy').value,
                codes: [document.getElementById('bt-code').value],
                start_date: document.getElementById('bt-start').value,
                end_date: document.getElementById('bt-end').value,
                initial_cash: parseFloat(document.getElementById('bt-cash').value),
                enable_risk: document.getElementById('bt-risk').value === 'true',
            };

            try {
                const res = await fetch('/api/backtest/run', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                const data = await res.json();
                this.showBacktestResults(data);
            } catch (err) {
                alert('回测失败: ' + err.message);
            } finally {
                btn.disabled = false;
                btn.textContent = '运行回测';
            }
        });
    },

    showBacktestResults(data) {
        document.getElementById('bt-results').style.display = '';
        document.getElementById('bt-return').textContent = (data.total_return * 100).toFixed(2) + '%';
        document.getElementById('bt-annual').textContent = (data.annual_return * 100).toFixed(2) + '%';
        document.getElementById('bt-dd').textContent = (data.max_drawdown * 100).toFixed(2) + '%';
        document.getElementById('bt-sharpe').textContent = data.sharpe_ratio;
        document.getElementById('bt-winrate').textContent = (data.win_rate * 100).toFixed(1) + '%';
        document.getElementById('bt-trades').textContent = data.total_trades;

        // 收益曲线
        if (this.charts.equity) this.charts.equity.destroy();
        const ctx = document.getElementById('bt-equity-chart').getContext('2d');
        this.charts.equity = new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.equity_curve.map(p => p.date),
                datasets: [{
                    label: '权益',
                    data: data.equity_curve.map(p => p.equity),
                    borderColor: '#4f8cff',
                    backgroundColor: 'rgba(79,140,255,0.1)',
                    fill: true,
                    pointRadius: 0,
                    borderWidth: 1.5,
                }]
            },
            options: {
                responsive: true,
                plugins: { legend: { display: false } },
                scales: {
                    x: { display: true, ticks: { maxTicksLimit: 10 } },
                    y: { display: true },
                }
            }
        });

        // 交易明细
        const tbody = document.querySelector('#bt-trades-table tbody');
        tbody.innerHTML = data.trades.map(t => `
            <tr>
                <td>${t.datetime || '--'}</td>
                <td>${t.code}</td>
                <td class="${t.direction === 'long' ? 'text-success' : 'text-danger'}">${t.direction === 'long' ? '买入' : '卖出'}</td>
                <td>${t.price}</td>
                <td>${t.volume}</td>
                <td>${t.entry_price || '--'}</td>
            </tr>
        `).join('');

        // 风控告警
        if (data.risk_alerts && data.risk_alerts.length > 0) {
            document.getElementById('bt-alerts-card').style.display = '';
            const alertBody = document.querySelector('#bt-alerts-table tbody');
            alertBody.innerHTML = data.risk_alerts.map(a => `
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
                fetch('/api/portfolio/snapshot').then(r => r.json()),
                fetch('/api/portfolio/trades').then(r => r.json()),
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
            console.log('持仓数据加载失败:', e);
        }
    },

    /* ── Tab 4: 风控 ── */
    async loadRisk() {
        try {
            const [risk, rules] = await Promise.all([
                fetch('/api/portfolio/risk').then(r => r.json()),
                fetch('/api/system/risk/rules').then(r => r.json()),
            ]);

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
                        plugins: { legend: { position: 'right' } }
                    }
                });
            }

            // 风控规则
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
            console.log('风控数据加载失败:', e);
        }
    },

    /* ── Tab 5: 策略管理 ── */
    async loadStrategies() {
        try {
            const strategies = await fetch('/api/system/strategies').then(r => r.json());
            const grid = document.getElementById('st-list');
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
            console.log('策略数据加载失败:', e);
        }
    },

    quickBacktest(strategyName) {
        document.getElementById('bt-strategy').value = strategyName;
        this.switchTab('backtest');
    },

    /* ── 工具函数 ── */
    fmt(value) {
        if (value == null || value === 0) return '¥0';
        return '¥' + Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 });
    },
};

// 启动
document.addEventListener('DOMContentLoaded', () => App.init());
