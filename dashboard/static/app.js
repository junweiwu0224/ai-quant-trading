/* ── AI 量化交易系统 — 主入口 ── */

const App = {
    stockCache: null,
    currentTab: 'overview',

    escapeHTML(str) {
        if (str == null) return '';
        return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    },

    async fetchJSON(url) {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`${url} 返回 ${res.status}`);
        return res.json();
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
        setTimeout(() => el.remove(), 3000);
    },

    init() {
        this.bindTabs();
        this.bindBacktest();
        this.bindStrategyChips();
        this.setDefaultDate();
        this.loadStockList();
        this.loadBenchmarks();
        this.initSidebar();
        this.loadOverview();
        this._startMarketRefresh();
        Paper.loadStatus();
        Watchlist.init();

        // 连接实时行情 WebSocket
        RealtimeQuotes.connect();
        RealtimeQuotes.onUpdate((data) => {
            if (data._status) return;
            this._updateWatchlistPrices(data);
        });
        StockDetail.init();

        // 股票名称点击跳转详情Tab
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

        const hash = location.hash.slice(1);
        if (hash) this.switchTab(hash);
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

    _updateWatchlistPrices(quotes) {
        const rows = document.querySelectorAll('#ov-stocks-table tbody tr');
        rows.forEach(row => {
            const codeCell = row.cells?.[0];
            if (!codeCell) return;
            const code = codeCell.textContent.trim();
            const q = quotes[code];
            if (!q) return;
            // 列: 代码(0) 名称(1) 行业(2) 板块(3) 概念(4) 最新价(5) 涨跌幅(6)
            const industryCell = row.cells?.[2];
            if (industryCell && q.industry) {
                industryCell.textContent = q.industry;
            }
            const sectorCell = row.cells?.[3];
            if (sectorCell && q.sector) {
                sectorCell.textContent = q.sector;
            }
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
                priceCell.className = q.change_pct >= 0 ? 'text-danger' : 'text-success';
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
                changeCell.className = q.change_pct >= 0 ? 'text-danger' : 'text-success';
            }
        });
    },

    /* 侧边栏折叠 */
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

    /* Tab 路由 */
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

        // 市场大盘自动刷新
        if (tab === 'overview') this._startMarketRefresh();
        else this._stopMarketRefresh();

        if (tab === 'overview') this.loadOverview();
        else if (tab === 'portfolio') this.loadPortfolio();
        else if (tab === 'risk') this.loadRisk();
        else if (tab === 'strategy') Strategy.load();
        else if (tab === 'alpha') this.initAlpha();
        else if (tab === 'paper') Paper.loadStatus();
        else if (tab === 'stock') StockDetail.refresh();
    },

    async setDefaultDate() {
        // 结束日期 = 数据库最后一个收盘日
        let endDate;
        try {
            const status = await this.fetchJSON('/api/system/status');
            endDate = status.db_stats?.latest_date || new Date().toISOString().split('T')[0];
        } catch {
            endDate = new Date().toISOString().split('T')[0];
        }

        // 开始日期 = 结束日期的上个月同日
        const d = new Date(endDate);
        const startD = new Date(d);
        startD.setMonth(startD.getMonth() - 1);
        // 处理上月无该日的情况（如 3月31日 → 2月28日）
        if (startD.getMonth() !== (d.getMonth() - 1 + 12) % 12) {
            startD.setDate(0);
        }
        const startDate = startD.toISOString().split('T')[0];

        document.getElementById('bt-start').value = startDate;
        document.getElementById('bt-end').value = endDate;
        document.getElementById('alpha-start').value = startDate;
        document.getElementById('alpha-end').value = endDate;
    },

    paperMultiSearch: null, // 模拟盘多选搜索框实例

    async loadStockList() {
        try {
            // 获取自选股列表
            const watchlist = await this.fetchJSON('/api/watchlist').catch(() => []);
            this.watchlistCache = watchlist || [];

            // 全量搜索数据源（服务器端搜索）
            const stockFilter = async (q) => {
                if (!q) {
                    // 无查询时返回热门股票（自选股 + 前50只）
                    const source = this.watchlistCache || [];
                    return source.slice(0, 50);
                }
                // 服务器端搜索
                try {
                    const results = await this.fetchJSON(`/api/stock/search?q=${encodeURIComponent(q)}&limit=50`);
                    return results || [];
                } catch (e) {
                    console.error('搜索失败:', e);
                    return [];
                }
            };

            // 仅自选股过滤器（用于回测/AI Alpha/模拟盘）
            const watchlistFilter = (q) => {
                if (!this.watchlistCache || this.watchlistCache.length === 0) return [];
                if (!q) return this.watchlistCache;
                return this.watchlistCache.filter(s =>
                    s.code.includes(q) || (s.name && s.name.toLowerCase().includes(q))
                );
            };

            // 回测搜索框（单选）
            const btSearch = new SearchBox('bt-code', 'bt-code-dropdown', {
                maxResults: 30,
                formatItem: (s) => `${s.code} ${s.name || ''}`,
            });
            btSearch.setDataSource(watchlistFilter);
            btSearch.onSelect((item) => {
                document.getElementById('bt-code').value = item.code;
            });

            // AI Alpha 搜索框（单选）
            const alphaSearch = new SearchBox('alpha-code', 'alpha-code-dropdown', {
                maxResults: 30,
                formatItem: (s) => `${s.code} ${s.name || ''}`,
            });
            alphaSearch.setDataSource(watchlistFilter);
            alphaSearch.onSelect((item) => {
                document.getElementById('alpha-code').value = item.code;
            });

            // 模拟盘搜索框（多选）
            this.paperMultiSearch = new MultiSearchBox('pp-codes', 'pp-codes-dropdown', 'pp-codes-tags', {
                maxResults: 30,
            });
            this.paperMultiSearch.setDataSource(watchlistFilter);

            // 预选自选股到多选下拉
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
        (data.equity_curve || []).forEach(p => {
            rows.push([p.date, p.equity]);
        });

        // 添加交易明细
        rows.push([]);
        rows.push(['交易明细']);
        rows.push(['日期', '代码', '方向', '价格', '数量', '入场价']);
        (data.trades || []).forEach(t => {
            rows.push([t.datetime, t.code, t.direction === 'long' ? '买入' : '卖出', t.price, t.volume, t.entry_price || '']);
        });

        // 添加统计指标
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

    quickBacktest(strategyName) {
        document.getElementById('bt-strategy').value = strategyName;
        this.switchTab('backtest');
    },

    /* ── 总览 ── */
    async loadOverview() {
        const stockCountEl = document.getElementById('ov-stock-count');
        if (stockCountEl) stockCountEl.innerHTML = '<span class="spinner"></span>';
        const refreshBtn = document.querySelector('button[onclick="App.loadOverview()"]');
        if (refreshBtn) refreshBtn.disabled = true;

        try {
            const [snapshot, trades, status, equityHistory, watchlist, indices, hotSectors, marketStats, benchmark] = await Promise.all([
                this.fetchJSON('/api/portfolio/snapshot').catch(() => ({ total_equity: 0, cash: 0, market_value: 0, positions: [] })),
                this.fetchJSON('/api/portfolio/trades/recent?limit=20').catch(() => []),
                this.fetchJSON('/api/system/status').catch(() => ({ db_stats: {}, paper_running: false, ai_model: '--' })),
                this.fetchJSON('/api/portfolio/equity-history').catch(() => []),
                this.fetchJSON('/api/watchlist').catch(() => []),
                this.fetchJSON('/api/stock/market/indices').catch(() => []),
                this.fetchJSON('/api/stock/market/hot-sectors').catch(() => ({ industries: [], concepts: [] })),
                this.fetchJSON('/api/stock/market/stats').catch(() => null),
                this.fetchJSON('/api/stock/market/benchmark?count=60').catch(() => []),
            ]);

            const dbStats = status.db_stats || {};

            // Row 1: 核心指标卡片
            document.getElementById('ov-equity').textContent = this.fmt(snapshot.total_equity);
            this._renderMetric('ov-daily-pnl', snapshot.daily_pnl, snapshot.daily_pnl_pct, true);
            this._renderPctMetric('ov-cum-return', snapshot.cumulative_return);
            this._renderPctMetric('ov-max-dd', snapshot.max_drawdown, true);
            document.getElementById('ov-sharpe').textContent = snapshot.sharpe_ratio?.toFixed(2) ?? '--';
            document.getElementById('ov-position-count').textContent = snapshot.positions?.length ?? 0;

            // 系统状态
            document.getElementById('ov-stock-count').textContent = dbStats.stock_count || 0;
            document.getElementById('ov-latest-date').textContent = dbStats.latest_date || '无数据';

            const syncEl = document.getElementById('ov-sync-status');
            if (syncEl) {
                if (dbStats.latest_date) {
                    const now = new Date();
                    const time = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}:${String(now.getSeconds()).padStart(2,'0')}`;
                    syncEl.innerHTML = `${dbStats.latest_date} <small class="text-muted">${time}</small>`;
                } else {
                    syncEl.textContent = '无数据';
                }
            }
            const paperEl = document.getElementById('ov-paper-status');
            if (paperEl) paperEl.textContent = status.paper_running ? '运行中' : '已停止';
            const aiEl = document.getElementById('ov-ai-status');
            if (aiEl) aiEl.textContent = status.ai_model || '--';

            this._updateQuoteStatus();
            if (!this._quoteStatusTimer) {
                this._quoteStatusTimer = setInterval(() => this._updateQuoteStatus(), 1000);
            }

            Watchlist.render(watchlist);

            // 持仓明细
            this._renderPositions(snapshot);

            // 最近交易
            const tradesBody = document.querySelector('#ov-trades-table tbody');
            if (tradesBody && trades.length > 0) {
                tradesBody.innerHTML = trades.map(t => `
                    <tr><td>${this.escapeHTML(t.time) || '--'}</td><td><a href="#" class="stock-link" data-code="${this.escapeHTML(t.code)}">${this.escapeHTML(t.code)}</a></td><td class="${t.direction === 'long' ? 'text-success' : 'text-danger'}">${t.direction === 'long' ? '买入' : '卖出'}</td><td>¥${this.escapeHTML(t.price)}</td><td>${this.escapeHTML(t.volume)}</td></tr>
                `).join('');
            }

            // 图表
            this._overviewChartData = equityHistory;
            this._overviewBenchmarkData = benchmark;
            this._overviewChartMode = 'equity';
            try { this.renderEquityChart(equityHistory); } catch (e) { console.warn('收益图表渲染失败:', e); }
            try { this.renderMarketIndices(indices); } catch (e) { console.warn('指数渲染失败:', e); }
            try { this.renderHotSectors(hotSectors); } catch (e) { console.warn('热门板块渲染失败:', e); }

            // 市场情绪
            if (marketStats) this._renderMarketStats(marketStats);
        } catch (e) {
            if (stockCountEl) stockCountEl.textContent = '--';
            this.toast('总览数据加载失败: ' + e.message, 'error');
        } finally {
            if (refreshBtn) refreshBtn.disabled = false;
        }
    },

    _renderMetric(id, pnl, pnlPct, isCurrency) {
        const el = document.getElementById(id);
        if (!el) return;
        const sign = pnl >= 0 ? '+' : '';
        const text = isCurrency ? `${sign}¥${Math.abs(pnl).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}` : `${sign}${(pnlPct * 100).toFixed(2)}%`;
        el.textContent = text;
        el.className = 'stat-value ' + (pnl >= 0 ? 'text-danger' : 'text-success');
    },

    _renderPctMetric(id, value, alwaysRed) {
        const el = document.getElementById(id);
        if (!el) return;
        el.textContent = (value >= 0 ? '+' : '') + (value * 100).toFixed(2) + '%';
        if (alwaysRed) el.className = 'stat-value text-danger';
        else el.className = 'stat-value ' + (value >= 0 ? 'text-danger' : 'text-success');
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
        tbody.innerHTML = positions.map(p => {
            const pctClass = p.pnl >= 0 ? 'text-danger' : 'text-success';
            const sign = p.pnl >= 0 ? '+' : '';
            const weight = ((p.market_value / totalEquity) * 100).toFixed(1);
            return `<tr>
                <td><a href="#" class="stock-link" data-code="${this.escapeHTML(p.code)}">${this.escapeHTML(p.code)}</a></td>
                <td>${this.escapeHTML(p.code)}</td>
                <td>${p.volume}</td>
                <td>¥${p.avg_price.toFixed(3)}</td>
                <td class="${pctClass}">¥${p.current_price.toFixed(3)}</td>
                <td class="${pctClass}">${sign}¥${Math.abs(p.pnl).toFixed(2)}</td>
                <td class="${pctClass}">${sign}${(p.pnl_pct * 100).toFixed(2)}%</td>
                <td>${weight}%</td>
            </tr>`;
        }).join('') + `<tr class="pos-summary">
            <td colspan="2"><strong>合计</strong></td>
            <td>${positions.reduce((s, p) => s + p.volume, 0)}</td>
            <td></td>
            <td></td>
            <td class="${snapshot.total_pnl >= 0 ? 'text-danger' : 'text-success'}"><strong>${snapshot.total_pnl >= 0 ? '+' : ''}¥${Math.abs(snapshot.total_pnl).toFixed(2)}</strong></td>
            <td class="${snapshot.total_pnl >= 0 ? 'text-danger' : 'text-success'}"><strong>${snapshot.total_pnl >= 0 ? '+' : ''}${(snapshot.total_pnl_pct * 100).toFixed(2)}%</strong></td>
            <td></td>
        </tr>`;
    },

    _renderMarketStats(stats) {
        const el = document.getElementById('ov-market-stats');
        if (!el || !stats) return;
        const up = stats.up_count || 0;
        const flat = stats.flat_count || 0;
        const down = stats.down_count || 0;
        const total = up + flat + down || 1;
        const upPct = (up / total * 100).toFixed(0);
        const flatPct = (flat / total * 100).toFixed(0);
        const downPct = (down / total * 100).toFixed(0);

        el.innerHTML = `
            <div class="market-stat-row">
                <span class="market-stat-label">涨跌分布</span>
                <div class="market-stat-bar">
                    <div class="bar-up" style="width:${upPct}%">${up}</div>
                    <div class="bar-flat" style="width:${flatPct}%">${flat}</div>
                    <div class="bar-down" style="width:${downPct}%">${down}</div>
                </div>
            </div>
            <div class="market-stat-extra">
                <span>涨停 <strong class="text-danger">${stats.limit_up || 0}</strong></span>
                <span>跌停 <strong class="text-success">${stats.limit_down || 0}</strong></span>
            </div>`;
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

    renderReturnDistribution(data) {
        const canvasId = 'ov-overview-chart';
        if (!data || data.length < 2) { ChartFactory.showEmpty(canvasId); return; }

        const labels = [];
        const dailyReturns = [];
        for (let i = 1; i < data.length; i++) {
            const prev = data[i - 1].equity;
            if (prev > 0) {
                labels.push(data[i].date ? data[i].date.substring(5) : '');
                dailyReturns.push((data[i].equity - prev) / prev * 100);
            }
        }
        if (dailyReturns.length === 0) { ChartFactory.showEmpty(canvasId); return; }

        const colors = dailyReturns.map(v => v >= 0 ? 'rgba(239,83,80,0.7)' : 'rgba(16,185,129,0.7)');
        const borderColors = dailyReturns.map(v => v >= 0 ? '#ef5350' : '#10b981');

        ChartFactory.bar(canvasId, { labels, values: dailyReturns, colors, borderColors }, 'overviewChart', {
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: ctx => `日收益: ${ctx.parsed.y >= 0 ? '+' : ''}${ctx.parsed.y.toFixed(2)}%`,
                    },
                },
            },
            scales: {
                y: {
                    ticks: {
                        callback: v => v.toFixed(1) + '%',
                        color: '#a29c95',
                        font: { size: 11 },
                    },
                    grid: { color: 'rgba(227,225,219,0.25)' },
                },
                x: {
                    ticks: { maxTicksLimit: 10, color: '#a29c95', font: { size: 11 } },
                    grid: { display: false },
                },
            },
        });
    },

    renderBenchmarkChart(equityData, benchmarkData) {
        const canvasId = 'ov-overview-chart';
        if (!equityData || equityData.length < 2) { ChartFactory.showEmpty(canvasId); return; }

        const baseEquity = equityData[0].equity;
        const portfolioReturns = equityData.map(d => ((d.equity - baseEquity) / baseEquity * 100));
        const labels = equityData.map(d => d.date ? d.date.substring(5) : '');

        const datasets = [{
            label: '模拟盘',
            data: portfolioReturns,
            color: '#ef5350',
            borderWidth: 2,
            pointRadius: 0,
        }];

        if (benchmarkData && benchmarkData.length > 0) {
            const benchMap = {};
            benchmarkData.forEach(b => { benchMap[b.date] = b.return_pct; });
            const benchReturns = equityData.map(d => benchMap[d.date] ?? null);
            datasets.push({
                label: '沪深300',
                data: benchReturns,
                color: '#4fc3f7',
                borderWidth: 1.5,
                pointRadius: 0,
                borderDash: [4, 4],
            });
        }

        ChartFactory.line(canvasId, { labels, datasets }, 'overviewChart', {
            plugins: {
                legend: { display: true, position: 'top', labels: { color: '#a29c95', font: { size: 11 }, boxWidth: 12, padding: 16 } },
                tooltip: {
                    callbacks: {
                        label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y >= 0 ? '+' : ''}${ctx.parsed.y.toFixed(2)}%`,
                    },
                },
            },
            scales: {
                y: {
                    ticks: { callback: v => v.toFixed(1) + '%', color: '#a29c95', font: { size: 11 } },
                    grid: { color: 'rgba(227,225,219,0.25)' },
                },
                x: {
                    ticks: { maxTicksLimit: 8, color: '#a29c95', font: { size: 11 } },
                    grid: { display: false },
                },
            },
        });
    },

    _switchOverviewChart(mode) {
        if (this._overviewChartMode === mode) return;
        this._overviewChartMode = mode;
        document.querySelectorAll('.chart-toggle-btn').forEach(b =>
            b.classList.toggle('active', b.dataset.mode === mode));
        const titles = { equity: '资产走势', daily: '每日收益', benchmark: '收益对比' };
        document.getElementById('ov-chart-title').textContent = titles[mode] || '资产走势';
        if (mode === 'equity') this.renderEquityChart(this._overviewChartData);
        else if (mode === 'daily') this.renderReturnDistribution(this._overviewChartData);
        else if (mode === 'benchmark') this.renderBenchmarkChart(this._overviewChartData, this._overviewBenchmarkData);
    },

    renderMarketIndices(indices) {
        const el = document.getElementById('ov-market-indices');
        if (!el || !Array.isArray(indices) || indices.length === 0) return;
        el.innerHTML = indices.map(idx => {
            const cls = idx.change_pct >= 0 ? 'text-danger' : 'text-success';
            const sign = idx.change_pct >= 0 ? '+' : '';
            return `
                <div class="market-index">
                    <div class="idx-name">${this.escapeHTML(idx.name)}</div>
                    <div class="idx-price ${cls}">${idx.price.toFixed(2)}</div>
                    <div class="idx-change ${cls}">${sign}${idx.change.toFixed(2)}  ${sign}${idx.change_pct.toFixed(2)}%</div>
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
            el.innerHTML = items.map((s, i) => {
                const cls = s.change_pct >= 0 ? 'text-danger' : 'text-success';
                const sign = s.change_pct >= 0 ? '+' : '';
                return `
                    <div class="sector-row">
                        <span class="sr-rank">${i + 1}</span>
                        <span class="sr-name">${this.escapeHTML(s.name)}</span>
                        <span class="sr-count">涨${s.rise_count}/跌${s.fall_count}</span>
                        <span class="sr-pct ${cls}">${sign}${s.change_pct.toFixed(2)}%</span>
                    </div>`;
            }).join('');
        };

        renderList(industriesEl, data.industries);
        renderList(conceptsEl, data.concepts);
    },

    _startMarketRefresh() {
        this._stopMarketRefresh();
        this._refreshMarket();
        this._marketTimer = setInterval(() => this._refreshMarket(), 10000);
    },

    _stopMarketRefresh() {
        if (this._marketTimer) {
            clearInterval(this._marketTimer);
            this._marketTimer = null;
        }
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

    /* ── 回测 ── */
    bindBacktest() {
        const form = document.getElementById('backtest-form');
        if (!form) return;
        form.addEventListener('submit', async (e) => {
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
            this._showProgress(0, '');

            const body = {
                strategy: document.getElementById('bt-strategy').value,
                codes: [code],
                start_date: startDate, end_date: endDate,
                initial_cash: cash,
                commission_rate: parseFloat(document.getElementById('bt-commission').value) || 0.0003,
                stamp_tax_rate: parseFloat(document.getElementById('bt-stamp-tax').value) || 0.001,
                slippage: parseFloat(document.getElementById('bt-slippage').value) || 0.002,
                benchmark: document.getElementById('bt-benchmark').value || '',
                enable_risk: document.getElementById('bt-risk').value === 'true',
            };

            try {
                const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
                const ws = new WebSocket(`${proto}//${location.host}/api/backtest/ws/run`);
                this._btWs = ws;

                const result = await new Promise((resolve, reject) => {
                    ws.onopen = () => ws.send(JSON.stringify(body));
                    ws.onmessage = (evt) => {
                        const msg = JSON.parse(evt.data);
                        if (msg.type === 'progress') {
                            this._showProgress(msg.progress, msg.current_date, msg.elapsed, msg.remaining);
                        } else if (msg.type === 'complete') {
                            resolve(msg.data);
                        } else if (msg.type === 'error') {
                            reject(new Error(msg.message));
                        }
                    };
                    ws.onerror = () => reject(new Error('WebSocket连接失败'));
                    ws.onclose = (evt) => {
                        if (!evt.wasClean) reject(new Error('连接中断'));
                    };
                    setTimeout(() => {
                        if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
                            ws.close();
                            reject(new Error('回测超时'));
                        }
                    }, 300000);
                });

                this.showBacktestResults(result, body);
                this.toast('回测完成', 'success');
                this.compareStrategies();
            } catch (err) {
                this.toast('回测失败: ' + err.message, 'error');
            } finally {
                btn.disabled = false;
                btn.textContent = '运行回测';
                this._hideProgress();
                if (this._btWs) {
                    try { this._btWs.close(); } catch (e) { /* ignore */ }
                    this._btWs = null;
                }
            }
        });
    },

    _showProgress(progress, currentDate, elapsed, remaining) {
        let bar = document.getElementById('bt-progress-wrap');
        if (!bar) {
            bar = document.createElement('div');
            bar.id = 'bt-progress-wrap';
            bar.className = 'bt-progress';
            bar.innerHTML = '<div class="bt-progress-bar"><div class="bt-progress-fill" id="bt-progress-fill"></div></div><div class="bt-progress-text" id="bt-progress-text"></div>';
            const form = document.getElementById('backtest-form');
            if (form) form.parentNode.insertBefore(bar, form.nextSibling);
        }
        bar.style.display = '';
        const fill = document.getElementById('bt-progress-fill');
        const text = document.getElementById('bt-progress-text');
        if (fill) fill.style.width = (progress * 100).toFixed(1) + '%';
        if (text) {
            let info = (progress * 100).toFixed(1) + '%';
            if (currentDate) info += ' · ' + currentDate;
            if (elapsed != null) info += ' · 已用' + elapsed + 's';
            if (remaining != null && remaining > 0) info += ' · 剩余约' + remaining + 's';
            text.textContent = info;
        }
    },

    _hideProgress() {
        const bar = document.getElementById('bt-progress-wrap');
        if (bar) bar.style.display = 'none';
    },

    bindStrategyChips() {
        // 绑定策略选择器的点击事件
        document.addEventListener('click', (e) => {
            const chip = e.target.closest('.chip');
            if (!chip) return;
            e.preventDefault();
            const checkbox = chip.querySelector('input[type="checkbox"]');
            if (!checkbox) return;
            checkbox.checked = !checkbox.checked;
            chip.classList.toggle('active', checkbox.checked);
            // 策略选择变化时自动触发对比
            this.compareStrategies();
        });
    },

    showBacktestResults(data, reqBody) {
        // 检查是否有错误
        if (data.error) {
            this.toast(data.error, 'error');
            document.getElementById('bt-results').style.display = 'none';
            return;
        }

        const safe = (v, d = 0) => v != null ? v : d;
        document.getElementById('bt-results').style.display = '';

        // 显示预热期信息
        const warmupDays = data.warmup_days || 0;
        const warmupInfo = document.getElementById('bt-warmup-info');
        if (warmupInfo) {
            if (warmupDays > 0) {
                warmupInfo.textContent = `预热期: ${warmupDays} 个交易日`;
                warmupInfo.style.display = '';
            } else {
                warmupInfo.style.display = 'none';
            }
        }

        document.getElementById('bt-return').textContent = (safe(data.total_return) * 100).toFixed(2) + '%';
        document.getElementById('bt-annual').textContent = (safe(data.annual_return) * 100).toFixed(2) + '%';
        document.getElementById('bt-dd').textContent = (safe(data.max_drawdown) * 100).toFixed(2) + '%';
        document.getElementById('bt-sharpe').textContent = safe(data.sharpe_ratio);
        document.getElementById('bt-sortino').textContent = safe(data.sortino_ratio);
        document.getElementById('bt-calmar').textContent = safe(data.calmar_ratio);
        document.getElementById('bt-info-ratio').textContent = safe(data.information_ratio);
        document.getElementById('bt-alpha').textContent = safe(data.alpha);
        document.getElementById('bt-beta').textContent = safe(data.beta);
        document.getElementById('bt-winrate').textContent = (safe(data.win_rate) * 100).toFixed(1) + '%';
        document.getElementById('bt-pl-ratio').textContent = safe(data.profit_loss_ratio);
        document.getElementById('bt-max-win-streak').textContent = safe(data.max_consecutive_wins);
        document.getElementById('bt-max-loss-streak').textContent = safe(data.max_consecutive_losses);
        document.getElementById('bt-trades').textContent = safe(data.total_trades);

        // 保存数据供导出使用
        this._lastBacktestData = data;
        this._lastBacktestBody = reqBody;

        const curve = data.equity_curve || [];
        const benchmarkCurve = data.benchmark_curve || [];
        if (curve.length > 0) {
            const datasets = [{ data: curve.map(p => p.equity), fill: true, label: '策略收益' }];
            if (benchmarkCurve.length > 0) {
                // 对齐基准数据到策略日期
                const bmMap = {};
                benchmarkCurve.forEach(p => { bmMap[p.date] = p.equity; });
                const bmData = curve.map(p => bmMap[p.date] != null ? bmMap[p.date] * (curve[0]?.equity || 1) : null);
                datasets.push({
                    data: bmData,
                    fill: false,
                    label: '基准',
                    borderDash: [5, 5],
                    borderColor: 'rgba(255,152,0,0.8)',
                    backgroundColor: 'transparent',
                    pointRadius: 0,
                });
            }
            ChartFactory.line('bt-equity-chart', {
                labels: curve.map(p => p.date),
                datasets,
            }, 'equity');
        }

        const trades = data.trades || [];
        const tbody = document.querySelector('#bt-trades-table tbody');
        if (trades.length > 0) {
            tbody.innerHTML = trades.map(t => `
                <tr><td>${this.escapeHTML(t.datetime) || '--'}</td><td>${this.escapeHTML(t.code)}</td><td class="${t.direction === 'long' ? 'text-success' : 'text-danger'}">${t.direction === 'long' ? '买入' : '卖出'}</td><td>${this.escapeHTML(t.price)}</td><td>${this.escapeHTML(t.volume)}</td><td>${this.escapeHTML(t.entry_price) || '--'}</td></tr>
            `).join('');
        } else {
            tbody.innerHTML = '<tr><td colspan="6" class="text-muted">无交易记录</td></tr>';
        }

        const alerts = data.risk_alerts || [];
        if (alerts.length > 0) {
            document.getElementById('bt-alerts-card').style.display = '';
            document.querySelector('#bt-alerts-table tbody').innerHTML = alerts.map(a => `
                <tr><td>${this.escapeHTML(a.date)}</td><td><span class="badge badge-${a.level === 'critical' ? 'danger' : 'warning'}">${this.escapeHTML(a.level)}</span></td><td>${this.escapeHTML(a.category)}</td><td>${this.escapeHTML(a.message)}</td></tr>
            `).join('');
        } else {
            document.getElementById('bt-alerts-card').style.display = 'none';
        }

        if (reqBody) this.loadBacktestCharts(reqBody);
    },

    async loadBacktestCharts(reqBody) {
        try {
            const [monthly, drawdown] = await Promise.all([
                fetch('/api/backtest/monthly-returns', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(reqBody) }).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }),
                fetch('/api/backtest/drawdown', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(reqBody) }).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }),
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
                const bg = val == null ? 'var(--bg-primary)' :
                    val > 0 ? `rgba(16,185,129,${Math.min(Math.abs(val) * 5, 1).toFixed(2)})` :
                    `rgba(198,87,70,${Math.min(Math.abs(val) * 5, 1).toFixed(2)})`;
                const text = val != null ? (val * 100).toFixed(1) + '%' : '--';
                html += `<td style="background:${bg}">${text}</td>`;
            }
            html += '</tr>';
        }
        html += '</tbody></table>';
        container.innerHTML = html;
    },

    renderDrawdown(data) {
        if (!data || data.length === 0) { ChartFactory.showEmpty('bt-drawdown-chart'); return; }
        ChartFactory.line('bt-drawdown-chart', {
            labels: data.map(d => d.date),
            datasets: [{ data: data.map(d => d.drawdown_pct * 100), color: '#c65746', fill: true }],
        }, 'drawdown', {
            scales: {
                y: { ticks: { color: ChartFactory.getColors().textMuted, callback: v => v + '%' } },
            },
        });
    },

    async compareStrategies() {
        const strategies = [...document.querySelectorAll('#bt-compare-section input:checked')].map(el => el.value);
        if (strategies.length === 0) return;
        const code = document.getElementById('bt-code').value.trim();
        if (!code) return;

        const body = {
            strategies, codes: [code],
            start_date: document.getElementById('bt-start').value,
            end_date: document.getElementById('bt-end').value,
            initial_cash: parseFloat(document.getElementById('bt-cash').value),
        };

        try {
            const res = await fetch('/api/backtest/compare', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const results = await res.json();
            if (!results || results.length === 0) return;

            const labelMap = { dual_ma: '双均线', bollinger: '布林带', momentum: '动量' };
            const palette = ChartFactory.palette();
            ChartFactory.line('bt-compare-chart', {
                labels: results[0].equity_curve.map(p => p.date),
                datasets: results.map((r, i) => ({
                    label: labelMap[r.strategy] || r.strategy,
                    data: r.equity_curve.map(p => p.equity),
                    color: palette[i % palette.length],
                })),
            }, 'compare', {
                plugins: { legend: { labels: { color: ChartFactory.getColors().text } } },
            });
        } catch (e) {
            console.error('策略对比失败:', e);
        }
    },

    /* ── 持仓 ── */
    async loadPortfolio() {
        const refreshBtn = document.querySelector('button[onclick="App.loadPortfolio()"]');
        if (refreshBtn) refreshBtn.disabled = true;

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

            const posBody = document.querySelector('#pf-positions tbody');
            if (snapshot.positions.length > 0) {
                posBody.innerHTML = snapshot.positions.map(p => {
                    const pnlClass = p.pnl >= 0 ? 'text-success' : 'text-danger';
                    return `<tr><td>${this.escapeHTML(p.code)}</td><td>${p.volume}</td><td>¥${p.avg_price}</td><td>¥${p.current_price}</td><td>${this.fmt(p.market_value)}</td><td class="${pnlClass}">${p.pnl >= 0 ? '+' : ''}${this.fmt(p.pnl)}</td></tr>`;
                }).join('');
            } else {
                posBody.innerHTML = '<tr><td colspan="6" class="text-muted">暂无持仓数据</td></tr>';
            }

            const tradeBody = document.querySelector('#pf-trades tbody');
            if (trades.length > 0) {
                tradeBody.innerHTML = trades.map(t => `
                    <tr><td>${this.escapeHTML(t.time) || '--'}</td><td>${this.escapeHTML(t.code)}</td><td class="${t.direction === 'long' ? 'text-success' : 'text-danger'}">${t.direction === 'long' ? '买入' : '卖出'}</td><td>¥${this.escapeHTML(t.price)}</td><td>${this.escapeHTML(t.volume)}</td><td>${this.fmt(t.equity)}</td></tr>
                `).join('');
            } else {
                tradeBody.innerHTML = '<tr><td colspan="6" class="text-muted">今日无交易</td></tr>';
            }

            this.renderPnlChart(snapshot.positions);
            this.renderIndustryChart(industry);
            this.renderAllocationChart(snapshot);
        } catch (e) {
            this.toast('持仓数据加载失败', 'error');
        } finally {
            if (refreshBtn) refreshBtn.disabled = false;
        }
    },

    renderPnlChart(positions) {
        if (!positions || positions.length === 0) { ChartFactory.showEmpty('pf-pnl-chart'); return; }
        const c = ChartFactory.getColors();
        const colors = positions.map(p => p.pnl >= 0 ? 'rgba(16,185,129,0.7)' : 'rgba(198,87,70,0.7)');
        const borderColors = positions.map(p => p.pnl >= 0 ? c.success : c.danger);
        ChartFactory.bar('pf-pnl-chart', {
            labels: positions.map(p => p.code),
            values: positions.map(p => p.pnl),
            colors, borderColors,
        }, 'pnl');
    },

    renderIndustryChart(data) {
        if (!data || data.length === 0) { ChartFactory.showEmpty('pf-industry-chart'); return; }
        ChartFactory.pie('pf-industry-chart', {
            labels: data.map(d => d.industry || '未知'),
            values: data.map(d => d.value),
        }, 'industry');
    },

    renderAllocationChart(snapshot) {
        if (!snapshot || !snapshot.positions || snapshot.positions.length === 0) { ChartFactory.showEmpty('pf-allocation-chart'); return; }
        const labels = snapshot.positions.map(p => p.code);
        const values = snapshot.positions.map(p => p.market_value);
        if (snapshot.cash > 0) { labels.push('现金'); values.push(snapshot.cash); }
        ChartFactory.doughnut('pf-allocation-chart', { labels, values }, 'allocation');
    },

    /* ── 券商账户配置 ── */
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

    /* ── 风控 ── */
    async loadRisk() {
        const refreshBtn = document.querySelector('button[onclick="App.loadRisk()"]');
        if (refreshBtn) refreshBtn.disabled = true;

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
                ChartFactory.doughnut('rk-position-chart', { labels, values }, 'pos');
            }
        } catch (e) {
            this.toast('风控数据加载失败', 'error');
        } finally {
            if (refreshBtn) refreshBtn.disabled = false;
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

    /* ── AI Alpha ── */
    initAlpha() {
        // SearchBox 已在 loadStockList 中初始化，无需额外操作
    },

    async loadAlpha() {
        const code = document.getElementById('alpha-code').value;
        const startDate = document.getElementById('alpha-start').value;
        const endDate = document.getElementById('alpha-end').value;
        if (!code) { this.toast('请输入股票代码', 'error'); return; }

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
        if (!data || data.length === 0) { ChartFactory.showEmpty('alpha-feature-chart'); return; }
        ChartFactory.horizontalBar('alpha-feature-chart', {
            labels: data.map(d => d.feature),
            values: data.map(d => d.importance),
        }, 'feature');
    },

    renderTrainingCurve(data) {
        if (!data || !data.epochs || data.epochs.length === 0) { ChartFactory.showEmpty('alpha-training-chart'); return; }
        const c = ChartFactory.getColors();
        ChartFactory.line('alpha-training-chart', {
            labels: data.epochs,
            datasets: [
                { label: 'Train AUC', data: data.train_auc, yAxisID: 'y-auc' },
                { label: 'Val AUC', data: data.val_auc, color: c.success, yAxisID: 'y-auc', borderDash: [5, 3] },
                { label: 'Train Loss', data: data.train_loss, color: c.warning, yAxisID: 'y-loss' },
                { label: 'Val Loss', data: data.val_loss, color: c.danger, yAxisID: 'y-loss', borderDash: [5, 3] },
            ],
        }, 'training', {
            plugins: { legend: { labels: { color: c.text } } },
            scales: {
                'y-auc': { type: 'linear', position: 'left', title: { display: true, text: 'AUC', color: c.textMuted }, ticks: { color: c.textMuted } },
                'y-loss': { type: 'linear', position: 'right', title: { display: true, text: 'Loss', color: c.textMuted }, ticks: { color: c.textMuted }, grid: { drawOnChartArea: false } },
            },
        });
    },

    renderPredictVsActual(data) {
        if (!data || !data.predictions || data.predictions.length === 0) { ChartFactory.showEmpty('alpha-predict-chart'); return; }
        const c = ChartFactory.getColors();
        const preds = data.predictions;
        ChartFactory.line('alpha-predict-chart', {
            labels: preds.map(p => p.date),
            datasets: [
                { label: '预测概率', data: preds.map(p => p.probability) },
                { label: '阈值线', data: preds.map(() => 0.5), color: c.danger, borderDash: [5, 5], borderWidth: 1 },
            ],
        }, 'predict', {
            plugins: { legend: { labels: { color: c.text } } },
            scales: { y: { min: 0, max: 1 } },
        });
    },

    renderSignalChart(klineData) {
        const kline = klineData.kline || [];
        const signals = klineData.signals || [];
        if (kline.length === 0) { ChartFactory.showEmpty('alpha-signal-chart'); return; }

        const c = ChartFactory.getColors();
        const closeData = kline.map(k => k.close);
        const dates = kline.map(k => k.date);
        const buyDates = new Set(signals.filter(s => s.type === 'buy').map(s => s.date));
        const sellDates = new Set(signals.filter(s => s.type === 'sell').map(s => s.date));

        const buyPoints = dates.map((d, i) => buyDates.has(d) ? closeData[i] : null);
        const sellPoints = dates.map((d, i) => sellDates.has(d) ? closeData[i] : null);

        ChartFactory.line('alpha-signal-chart', {
            labels: dates,
            datasets: [
                { label: '收盘价', data: closeData, color: c.muted },
                { label: '买入信号', data: buyPoints, color: c.success, pointRadius: 8, pointStyle: 'triangle' },
                { label: '卖出信号', data: sellPoints, color: c.danger, pointRadius: 8, pointStyle: 'triangle', pointRotation: 180 },
            ],
        }, 'signal', {
            plugins: { legend: { labels: { color: c.text } } },
        });
    },
};

document.addEventListener('DOMContentLoaded', () => App.init());
