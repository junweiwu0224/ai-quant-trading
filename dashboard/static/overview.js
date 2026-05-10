/* ── 总览模块 ── */

Object.assign(App, {
    _overviewLoaded: false,

    async loadOverview() {
        if (this._loadingOverview) return;
        this._loadingOverview = true;
        const refreshBtn = document.querySelector('button[onclick="App.loadOverview()"]');
        if (refreshBtn) refreshBtn.disabled = true;
        const loadStartTime = Date.now();

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

            // Qlib 心跳检查（异步，不阻塞）
            this._checkQlibHealth();

            this._updateQuoteStatus();
            this._updateMarketPhase();
            if (!this._phaseTimer) {
                this._phaseTimer = setInterval(() => this._updateMarketPhase(), 60000);
            }
            if (!this._freshnessTimer) {
                this._freshnessTimer = setInterval(() => this._updateDataFreshness(), 30000);
            }
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

            // 最近交易（仅显示前5条）
            const tradesBody = document.querySelector('#ov-trades-table tbody');
            if (tradesBody && trades.length > 0) {
                tradesBody.innerHTML = trades.slice(0, 5).map(t => `
                    <tr><td>${Utils.formatBeijingTime(t.time)}</td><td><a href="#" class="stock-link" data-code="${this.escapeHTML(t.code)}">${this.escapeHTML(t.code)} ${this.escapeHTML(t.name || '')}</a></td><td class="${(t.direction === 'long' || t.direction === 'buy') ? 'text-up' : 'text-down'}">${(t.direction === 'long' || t.direction === 'buy') ? '买入' : '卖出'}</td><td>¥${this.escapeHTML(t.price)}</td><td>${this.escapeHTML(t.volume)}</td></tr>
                `).join('');
            }

            // 阶段 2：次要数据（图表 + 市场，不阻塞首屏）
            this._loadOverviewSecondary(so);

            // 数据新鲜度指示
            this._overviewDataTime = loadStartTime;
            this._updateDataFreshness();
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
        if (alwaysRed) {
            // 回撤阈值：>0.5% 暗红，否则普通红
            el.className = 'stat-value ' + (Math.abs(value) > 0.005 ? 'stat-value-critical' : 'text-up');
        } else {
            el.className = 'stat-value ' + (value >= 0 ? 'text-up' : 'text-down');
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

    /** Qlib 心跳检查 */
    async _checkQlibHealth() {
        const el = document.getElementById('ov-qlib-status');
        if (!el) return;
        try {
            const data = await this.fetchJSON('/api/qlib/health', { silent: true });
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
