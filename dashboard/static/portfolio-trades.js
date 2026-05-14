/* ── 持仓模块：交易记录 ── */

document.addEventListener('click', (e) => {
    const button = e.target.closest('[data-pf-history-page]');
    if (!button) {
        return;
    }

    const page = parseInt(button.dataset.pfHistoryPage || '', 10);
    if (!Number.isFinite(page) || page <= 0) {
        return;
    }

    e.preventDefault();
    App.pfLoadHistory(page);
});

Object.assign(App, {
    _pfRenderTrades() {
        const trades = this._pf.trades || [];
        const tradeBody = document.querySelector('#pf-trades tbody');

        if (trades.length === 0) {
            tradeBody.innerHTML = '<tr><td colspan="6" class="text-muted">今日无交易</td></tr>';
            return;
        }

        tradeBody.innerHTML = trades.map(t => {
            const isBuy = t.direction === 'long';
            const dirClass = isBuy ? 'pf-val-up' : 'pf-val-down';
            return `<tr>
                <td>${this.escapeHTML(t.time) || '--'}</td>
                <td class="pf-code">${this.escapeHTML(t.code)}</td>
                <td class="${dirClass}">${isBuy ? '买入' : '卖出'}</td>
                <td class="pf-right pf-mono">¥${parseFloat(t.price).toFixed(2)}</td>
                <td class="pf-right pf-mono">${t.volume}</td>
                <td class="pf-right pf-mono">${this.fmt(t.equity)}</td>
            </tr>`;
        }).join('');
    },

    pfSwitchTradeTab(tab) {
        const todayPanel = document.getElementById('pf-trade-today');
        const historyPanel = document.getElementById('pf-trade-history');
        const tabs = document.querySelectorAll('.pf-trade-tabs .analysis-tab');

        tabs.forEach(t => t.classList.remove('active'));

        if (tab === 'today') {
            todayPanel.style.display = '';
            todayPanel.classList.add('active');
            historyPanel.style.display = 'none';
            historyPanel.classList.remove('active');
            tabs[0].classList.add('active');
        } else {
            todayPanel.style.display = 'none';
            todayPanel.classList.remove('active');
            historyPanel.style.display = '';
            historyPanel.classList.add('active');
            tabs[1].classList.add('active');
            if (!this._pf.historyLoaded) {
                this.pfLoadHistory();
            }
        }
    },

    async pfLoadHistory(page) {
        page = page || 1;
        this._pf.historyPage = page;

        const startDate = document.getElementById('pf-hist-start')?.value || '';
        const endDate = document.getElementById('pf-hist-end')?.value || '';

        try {
            const params = new URLSearchParams({ page, page_size: 20 });
            if (startDate) params.set('start_date', startDate);
            if (endDate) params.set('end_date', endDate);

            const data = await this.fetchJSON(`/api/portfolio/trades/history?${params}`);
            this._pf.historyLoaded = true;

            const tbody = document.querySelector('#pf-trade-history-table tbody');
            if (!data.trades || data.trades.length === 0) {
                tbody.innerHTML = '<tr><td colspan="7" class="text-muted">无交易记录</td></tr>';
                document.getElementById('pf-hist-pagination').innerHTML = '';
                return;
            }

            tbody.innerHTML = data.trades.map(t => {
                const isBuy = t.direction === 'long';
                const dirClass = isBuy ? 'pf-val-up' : 'pf-val-down';
                const pnl = t.pnl || 0;
                const pnlClass = pnl > 0 ? 'pf-val-up' : pnl < 0 ? 'pf-val-down' : '';
                return `<tr>
                    <td>${this.escapeHTML(t.time) || '--'}</td>
                    <td class="pf-code">${this.escapeHTML(t.code)}</td>
                    <td class="${dirClass}">${isBuy ? '买入' : '卖出'}</td>
                    <td class="pf-right pf-mono">¥${parseFloat(t.price).toFixed(2)}</td>
                    <td class="pf-right pf-mono">${t.volume}</td>
                    <td class="pf-right pf-mono ${pnlClass}">${pnl !== 0 ? this.fmt(pnl) : '--'}</td>
                    <td>${this.escapeHTML(t.strategy_name || '--')}</td>
                </tr>`;
            }).join('');

            // 分页
            this._pfRenderPagination(data.total, data.page, data.page_size);
        } catch (e) {
            this.toast('历史记录加载失败', 'error');
        }
    },

    _pfRenderPagination(total, page, pageSize) {
        const totalPages = Math.ceil(total / pageSize);
        const container = document.getElementById('pf-hist-pagination');
        if (!container || totalPages <= 1) {
            if (container) container.innerHTML = '';
            return;
        }

        let html = '';
        html += `<button ${page <= 1 ? 'disabled' : ''} data-pf-history-page="${page - 1}">上一页</button>`;

        const start = Math.max(1, page - 2);
        const end = Math.min(totalPages, page + 2);
        for (let i = start; i <= end; i++) {
            html += `<button class="${i === page ? 'active' : ''}" data-pf-history-page="${i}">${i}</button>`;
        }

        html += `<button ${page >= totalPages ? 'disabled' : ''} data-pf-history-page="${page + 1}">下一页</button>`;
        container.innerHTML = html;
    },
});
