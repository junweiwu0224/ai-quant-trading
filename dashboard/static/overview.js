/* ── 总览模块 ── */

Object.assign(App, {
    _overviewLoaded: false,

    async loadOverview() {
        if (this._loadingOverview) return;
        this._loadingOverview = true;
        const refreshBtn = document.querySelector('button[onclick="App.loadOverview()"]');
        if (refreshBtn) refreshBtn.disabled = true;

        // 首次加载显示骨架屏
        if (!this._overviewLoaded) {
            this._showOverviewSkeletons();
        }

        try {
            const so = { silent: true };

            // 阶段 1：核心数据（snapshot + watchlist + status + trades）
            const [snapshot, trades, status, watchlist] = await Promise.all([
                this.fetchJSON('/api/portfolio/snapshot', so).catch(() => ({ total_equity: 0, cash: 0, market_value: 0, positions: [] })),
                this.fetchJSON('/api/portfolio/trades/recent?limit=20', so).catch(() => []),
                this.fetchJSON('/api/system/status', so).catch(() => ({ db_stats: {}, paper_running: false, ai_model: '--' })),
                this.fetchJSON('/api/watchlist', so).catch(() => []),
            ]);

            const dbStats = status.db_stats || {};

            // 核心指标卡片
            document.getElementById('ov-equity').textContent = this.fmt(snapshot.total_equity);
            this._renderMetric('ov-daily-pnl', snapshot.daily_pnl, snapshot.daily_pnl_pct, true);
            this._renderPctMetric('ov-cum-return', snapshot.cumulative_return);
            this._renderPctMetric('ov-max-dd', snapshot.max_drawdown, true);
            document.getElementById('ov-sharpe').textContent = snapshot.sharpe_ratio?.toFixed(2) ?? '--';
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

            this._updateQuoteStatus();
            if (!this._quoteStatusTimer) {
                this._quoteStatusTimer = setInterval(() => this._updateQuoteStatus(), 1000);
            }

            // 自选股
            this.watchlistCache = watchlist || [];
            Watchlist.render(watchlist);
            Watchlist.setSelectedItems(watchlist || []);
            this._buildWatchlistIndex();

            // 持仓明细
            this._renderPositions(snapshot);

            // 最近交易
            const tradesBody = document.querySelector('#ov-trades-table tbody');
            if (tradesBody && trades.length > 0) {
                tradesBody.innerHTML = trades.map(t => `
                    <tr><td>${Utils.formatBeijingTime(t.time)}</td><td><a href="#" class="stock-link" data-code="${this.escapeHTML(t.code)}">${this.escapeHTML(t.code)} ${this.escapeHTML(t.name || '')}</a></td><td class="${(t.direction === 'long' || t.direction === 'buy') ? 'text-up' : 'text-down'}">${(t.direction === 'long' || t.direction === 'buy') ? '买入' : '卖出'}</td><td>¥${this.escapeHTML(t.price)}</td><td>${this.escapeHTML(t.volume)}</td></tr>
                `).join('');
            }

            // 阶段 2：次要数据（图表 + 市场，不阻塞首屏）
            this._loadOverviewSecondary(so);
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
        const [equityHistory, indices, hotSectors, marketStats, benchmark] = await Promise.all([
            this.fetchJSON('/api/portfolio/equity-history', so).catch(() => []),
            this.fetchJSON('/api/stock/market/indices', so).catch(() => []),
            this.fetchJSON('/api/stock/market/hot-sectors', so).catch(() => ({ industries: [], concepts: [] })),
            this.fetchJSON('/api/stock/market/stats', so).catch(() => null),
            this.fetchJSON('/api/stock/market/benchmark?count=60', so).catch(() => []),
        ]);

        this._overviewChartData = equityHistory;
        this._overviewBenchmarkData = benchmark;
        this._overviewChartMode = 'equity';

        const chartContainer = document.querySelector('#tab-overview .chart-container');
        if (chartContainer) {
            const skel = chartContainer.querySelector('.skeleton-chart');
            if (skel) skel.remove();
            const canvas = chartContainer.querySelector('canvas');
            if (canvas) canvas.style.display = '';
        }
        try { this.renderEquityChart(equityHistory); } catch (e) { console.warn('收益图表渲染失败:', e); }
        try { this.renderMarketIndices(indices); } catch (e) { console.warn('指数渲染失败:', e); }
        try { this.renderHotSectors(hotSectors); } catch (e) { console.warn('热门板块渲染失败:', e); }
        if (marketStats) this._renderMarketStats(marketStats);
    },

    _showOverviewSkeletons() {
        // 统计卡片骨架屏
        ['ov-equity', 'ov-daily-pnl', 'ov-cum-return', 'ov-max-dd', 'ov-sharpe', 'ov-position-count'].forEach(id => {
            const el = document.getElementById(id);
            if (el) { el.textContent = ''; el.classList.add('skeleton-text'); }
        });
        // 持仓表格骨架屏
        const posBody = document.querySelector('#ov-positions-table tbody');
        if (posBody) posBody.innerHTML = `<tr><td colspan="8">${Utils.skeletonRows(4, 8)}</td></tr>`;
        // 交易表格骨架屏
        const tradesBody = document.querySelector('#ov-trades-table tbody');
        if (tradesBody) tradesBody.innerHTML = `<tr><td colspan="5">${Utils.skeletonRows(3, 5)}</td></tr>`;
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
        const sign = pnl >= 0 ? '+' : '';
        const arrow = pnl >= 0 ? '↑' : '↓';
        const text = isCurrency ? `${arrow} ${sign}¥${Math.abs(pnl).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}` : `${arrow} ${sign}${(pnlPct * 100).toFixed(2)}%`;
        el.textContent = text;
        el.className = 'stat-value ' + (pnl >= 0 ? 'text-up' : 'text-down');
    },

    _renderPctMetric(id, value, alwaysRed) {
        const el = document.getElementById(id);
        if (!el) return;
        const arrow = value >= 0 ? '↑' : '↓';
        el.textContent = arrow + ' ' + (value >= 0 ? '+' : '') + (value * 100).toFixed(2) + '%';
        if (alwaysRed) el.className = 'stat-value text-up';
        else el.className = 'stat-value ' + (value >= 0 ? 'text-up' : 'text-down');
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
            <td colspan="2"><strong>合计</strong></td>
            <td>${positions.reduce((s, p) => s + p.volume, 0)}</td>
            <td></td>
            <td></td>
            <td class="${snapshot.total_pnl >= 0 ? 'text-up' : 'text-down'}"><strong>${snapshot.total_pnl >= 0 ? '+' : ''}¥${Math.abs(snapshot.total_pnl).toFixed(2)}</strong></td>
            <td class="${snapshot.total_pnl >= 0 ? 'text-up' : 'text-down'}"><strong>${snapshot.total_pnl >= 0 ? '+' : ''}${(snapshot.total_pnl_pct * 100).toFixed(2)}%</strong></td>
            <td></td>
        </tr>`;

        // 表格增强：排序+分页
        if (positions.length > 10) {
            Utils.enhanceTable('#ov-positions-table', { pageSize: 15, searchable: false });
        }
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

        // 情绪指标：上涨占比 > 60% 偏多，< 40% 偏空
        let sentimentText, sentimentCls;
        const upRatio = up / total;
        if (upRatio >= 0.6) { sentimentText = '偏多'; sentimentCls = 'text-up'; }
        else if (upRatio <= 0.4) { sentimentText = '偏空'; sentimentCls = 'text-down'; }
        else { sentimentText = '震荡'; sentimentCls = 'text-muted'; }

        const upEnd = parseFloat(upPct);
        const flatEnd = upEnd + parseFloat(flatPct);
        el.innerHTML = `
            <div class="market-stat-row">
                <span class="market-stat-label">涨跌分布</span>
                <span class="market-stat-sentiment ${sentimentCls}">${sentimentText}</span>
            </div>
            <div class="market-stat-bar-wrap">
                <div class="market-stat-bar" style="background:linear-gradient(to right,#c65746 0%,#c65746 ${upEnd}%,#a29c95 ${upEnd}%,#a29c95 ${flatEnd}%,#10b981 ${flatEnd}%,#10b981 100%)"></div>
                <div class="market-stat-bar-labels">
                    <span class="text-up">${up} (${upPct}%)</span>
                    <span class="text-muted">${flat}</span>
                    <span class="text-down">${down} (${downPct}%)</span>
                </div>
            </div>
            <div class="market-stat-extra">
                <span>涨停 <strong class="text-up">${stats.limit_up || 0}</strong></span>
                <span>跌停 <strong class="text-down">${stats.limit_down || 0}</strong></span>
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
        // 防抖：200ms 内不重复切换
        clearTimeout(this._chartSwitchTimer);
        this._chartSwitchTimer = setTimeout(() => this._doSwitchChart(mode), 150);
    },

    _doSwitchChart(mode) {
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
            const cls = idx.change_pct >= 0 ? 'text-up' : 'text-down';
            const sign = idx.change_pct >= 0 ? '+' : '';
            return `
                <div class="market-index">
                    <div class="idx-name">${this.escapeHTML(idx.name)}</div>
                    <div class="idx-price ${cls}">${idx.price.toFixed(2)}</div>
                    <div class="idx-change ${cls}">${sign}${idx.change.toFixed(2)}  ${sign}${idx.change_pct.toFixed(3)}%</div>
                </div>`;
        }).join('');
    },

    renderHotSectors(data) {
        const industriesEl = document.getElementById('ov-hot-industries');
        const conceptsEl = document.getElementById('ov-hot-concepts');

        const renderList = (el, items) => {
            if (!el || !Array.isArray(items) || items.length === 0) {
                if (el) el.innerHTML = '<div class="text-muted">暂无数据</div>';
                if (el) console.warn('热门板块渲染: 无数据', { el: el?.id, items });
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

    // _startMarketRefresh / _stopMarketRefresh / _refreshMarket
    // 已在 app.js 中通过 PollManager 统一管理，此处不再重复定义
});
