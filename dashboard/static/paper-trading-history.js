/* ── 模拟盘：交易历史 / 风控 / 状态 / 轮询 ── */

if (!globalThis.PaperTrading) {
    globalThis.PaperTrading = {};
}

Object.assign(globalThis.PaperTrading, {
    _tradeFilter: { code: '', direction: '' },
    _benchmarkCurve: [],

    _applyTradeFilter(trades) {
        const { code, direction } = this._tradeFilter;
        return trades.filter(t => {
            if (code && !t.code.includes(code)) return false;
            if (direction && t.direction !== direction) return false;
            return true;
        });
    },

    onTradeFilterChange() {
        const codeEl = document.getElementById('pt-filter-code');
        const dirEl = document.getElementById('pt-filter-direction');
        this._tradeFilter.code = codeEl ? codeEl.value.trim() : '';
        this._tradeFilter.direction = dirEl ? dirEl.value : '';
        this.renderTrades({ items: this.state.trades, page: 1, total_pages: 1 });
    },

    async loadTrades(page = 1) {
        try {
            const data = await App.fetchJSON(`/api/paper/trades-v2?page=${page}&page_size=50`);
            this.state.trades = data.data.items || [];
            this.renderTrades(data.data);
        } catch (e) {
            console.error('加载交易历史失败:', e);
        }
    },

    renderTrades(pagination) {
        const tbody = document.querySelector('#pt-trades-table tbody');
        const emptyHint = document.getElementById('pt-trades-empty');
        if (!tbody) return;

        const filtered = this._applyTradeFilter(this.state.trades);

        if (filtered.length === 0) {
            tbody.innerHTML = '<tr><td colspan="9" class="text-muted text-center">暂无交易记录</td></tr>';
            if (emptyHint) emptyHint.style.display = 'block';
            return;
        }

        if (emptyHint) emptyHint.style.display = 'none';
        tbody.innerHTML = filtered.map(trade => {
            const time = trade.created_at ? Utils.formatBeijingTime(trade.created_at) : '--';
            const dirClass = trade.direction === 'buy' ? 'text-up' : 'text-down';
            const dirText = trade.direction === 'buy' ? '买入' : '卖出';
            const profitClass = trade.profit >= 0 ? 'text-up' : 'text-down';
            const profitSign = trade.profit >= 0 ? '+' : '';
            const cost = (trade.commission || 0) + (trade.stamp_tax || 0);

            return `<tr>
                <td>${time}</td>
                <td><a href="#" class="stock-link" data-code="${App.escapeHTML(trade.code)}">${App.escapeHTML(trade.code)}</a></td>
                <td class="${dirClass}">${dirText}</td>
                <td>¥${trade.price.toFixed(2)}</td>
                <td>${trade.volume}</td>
                <td class="${profitClass}">${profitSign}¥${trade.profit.toFixed(2)}</td>
                <td>${cost > 0 ? '¥' + cost.toFixed(2) : '--'}</td>
                <td>${trade.strategy_name || '--'}</td>
                <td>${trade.signal_reason || '--'}</td>
            </tr>`;
        }).join('');

        this.renderPagination(pagination);
    },

    renderPagination(pagination) {
        const container = document.getElementById('pt-trades-pagination');
        if (!container) return;

        const { page, total_pages } = pagination;
        let html = '';
        if (total_pages > 1) {
            html += `<button class="btn btn-sm" ${page <= 1 ? 'disabled' : ''} data-paper-action="load-trades-page" data-page="${page - 1}">上一页</button>`;
            html += `<span class="mx-sm">第 ${page} / ${total_pages} 页</span>`;
            html += `<button class="btn btn-sm" ${page >= total_pages ? 'disabled' : ''} data-paper-action="load-trades-page" data-page="${page + 1}">下一页</button>`;
        }
        container.innerHTML = html;
    },

    async exportTrades(format = 'csv') {
        try {
            const data = await App.fetchJSON(`/api/paper/trades-v2/export?format=${format}`);
            if (format === 'csv') {
                const blob = new Blob([data.data.content], { type: 'text/csv;charset=utf-8;' });
                const link = document.createElement('a');
                link.href = URL.createObjectURL(blob);
                link.download = data.data.filename;
                link.click();
            } else {
                const blob = new Blob([JSON.stringify(data.data.content, null, 2)], { type: 'application/json' });
                const link = document.createElement('a');
                link.href = URL.createObjectURL(blob);
                link.download = data.data.filename;
                link.click();
            }
            App.toast('导出成功', 'success');
        } catch (e) {
            App.toast(`导出失败: ${e.message}`, 'error');
        }
    },

    async loadRiskEvents() {
        try {
            const data = await App.fetchJSON('/api/paper/risk/events');
            this.state.riskEvents = data.data || [];
            this.renderRiskEvents();
        } catch (e) {
            console.error('加载风控事件失败:', e);
        }
    },

    renderRiskEvents() {
        const tbody = document.querySelector('#pt-risk-events-table tbody');
        if (!tbody) return;

        if (this.state.riskEvents.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-muted text-center">暂无风控事件</td></tr>';
            return;
        }

        tbody.innerHTML = this.state.riskEvents.map(event => {
            const time = event.created_at ? Utils.formatBeijingTime(event.created_at) : '--';
            const typeMap = {
                'stop_loss': { text: '止损', cls: 'text-down' },
                'take_profit': { text: '止盈', cls: 'text-up' },
                'trailing_stop': { text: '移动止损', cls: 'text-down' },
                'position_limit': { text: '仓位限制', cls: 'badge-warning' },
                'drawdown_limit': { text: '回撤限制', cls: 'text-down' },
            };
            const typeInfo = typeMap[event.event_type] || { text: event.event_type, cls: '' };

            return `<tr>
                <td>${time}</td>
                <td>${App.escapeHTML(event.code || '--')}</td>
                <td><span class="${typeInfo.cls}" style="font-weight:600">${typeInfo.text}</span></td>
                <td>${event.trigger_price ? '¥' + event.trigger_price.toFixed(2) : '--'}</td>
                <td>${App.escapeHTML(event.reason)}</td>
            </tr>`;
        }).join('');
    },

    loadStatus() {
        return Promise.resolve().then(async () => {
            try {
                const data = await App.fetchJSON('/api/paper/status');
                this.state.isRunning = data.running;
                this.state.config = data.config || {};
                if (data.cash != null) this.state.config.cash = data.cash;
                if (data.equity != null) this.state.config.equity = data.equity;
                this.renderStatus();
            } catch (e) {
                console.error('加载状态失败:', e);
            }
        });
    },

    renderStatus() {
        this._hideSkeletons();
        const statusEl = document.getElementById('pt-status');
        const equityEl = document.getElementById('pt-equity');
        const posCountEl = document.getElementById('pt-pos-count');
        const tradeCountEl = document.getElementById('pt-trade-count');

        if (statusEl) {
            statusEl.textContent = this.state.isRunning ? '运行中' : '已停止';
            statusEl.className = 'stat-value ' + (this.state.isRunning ? 'text-up' : '');
        }
        if (equityEl) {
            const eq = this.state.performance.total_equity;
            equityEl.textContent = eq != null && eq !== 0 ? App.fmt(eq) : '--';
        }
        if (posCountEl) posCountEl.textContent = this.state.positions.length;
        if (tradeCountEl) tradeCountEl.textContent = this.state.performance.total_trades || 0;

        const winRateEl = document.getElementById('pt-win-rate');
        if (winRateEl) {
            const wr = this.state.performance.win_rate;
            winRateEl.textContent = wr != null ? (wr * 100).toFixed(2) + '%' : '--';
        }

        const cashEl = document.getElementById('pt-available-cash');
        if (cashEl) {
            const cash = this.state.config.cash ?? this.state.performance.cash;
            cashEl.textContent = cash != null ? App.fmt(cash) : '--';
        }
    },

    startPolling() {
        this.stopPolling();
        PollManager.register('paperStatus', () => this.loadStatus(), this.polling.status.interval);
        PollManager.register('paperPositions', () => this.loadPositions(), this.polling.positions.interval);
        PollManager.register('paperOrders', () => this.loadOrders(), this.polling.orders.interval);
        PollManager.register('paperEquity', () => this.loadEquityCurve(), this.polling.equity.interval);
    },

    stopPolling() {
        PollManager.cancel('paperStatus');
        PollManager.cancel('paperPositions');
        PollManager.cancel('paperOrders');
        PollManager.cancel('paperEquity');
    },

    refreshAll() {
        this.loadStatus();
        this.loadPositions();
        this.loadOrders();
        this.loadPerformance();
        this.loadEquityCurve();
        this.loadTrades();
        this.loadRiskEvents();
    },
});
