/* ── 模拟盘完整功能 ── */

const PaperTrading = {
    // ────────────── 状态 ──────────────
    state: {
        isRunning: false,
        config: {},
        positions: [],
        orders: [],
        trades: [],
        performance: {},
        equityCurve: [],
        riskEvents: [],
    },

    // ────────────── 图表实例 ──────────────
    charts: {
        equityCurve: null,
        drawdown: null,
        monthlyHeatmap: null,
        returnDist: null,
        weekdayEffect: null,
    },

    // ────────────── 轮询管理 ──────────────
    polling: {
        status: { interval: 5000, timer: null },
        positions: { interval: 10000, timer: null },
        orders: { interval: 3000, timer: null },
        equity: { interval: 30000, timer: null },
    },

    // ────────────── 初始化 ──────────────
    _loaded: false,

    init() {
        this.bindEvents();
        if (!this._loaded) this._showSkeletons();
        this.loadStatus();
        this.loadPositions();
        this.loadOrders();
        this.loadPerformance();
        this.loadEquityCurve();
        this.startPolling();
    },

    _showSkeletons() {
        // 统计卡片
        const statsEl = document.querySelector('#tab-paper .stats-grid');
        if (statsEl) statsEl.innerHTML = Utils.skeletonCards(6);
        // 订单表格
        const orderBody = document.querySelector('#pt-orders-table tbody');
        if (orderBody) orderBody.innerHTML = `<tr><td colspan="8">${Utils.skeletonRows(3, 8)}</td></tr>`;
        // 持仓表格
        const posBody = document.querySelector('#pt-positions-table tbody');
        if (posBody) posBody.innerHTML = `<tr><td colspan="8">${Utils.skeletonRows(3, 8)}</td></tr>`;
        // 绩效卡片
        const perfEl = document.getElementById('pt-performance-stats');
        if (perfEl) perfEl.innerHTML = Utils.skeletonCards(12);
        // 图表
        document.querySelectorAll('#tab-paper .chart-container').forEach(el => {
            el.innerHTML = Utils.skeletonChart(15);
        });
    },

    bindEvents() {
        // 订单表单提交
        const orderForm = document.getElementById('pt-order-form');
        if (orderForm) {
            orderForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.createOrder();
            });
        }

        // 订单类型切换
        const orderTypeSelect = document.getElementById('pt-order-type');
        if (orderTypeSelect) {
            orderTypeSelect.addEventListener('change', () => {
                this.togglePriceInput();
            });
        }

        // 快捷数量按钮
        document.querySelectorAll('.pt-qty-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const qty = parseInt(btn.dataset.qty);
                document.getElementById('pt-volume').value = qty;
            });
        });

        // 刷新按钮
        document.getElementById('pt-refresh-btn')?.addEventListener('click', () => {
            this.refreshAll();
        });
    },

    // ────────────── 订单管理 ──────────────

    async createOrder() {
        const code = document.getElementById('pt-code').value.trim();
        const direction = document.getElementById('pt-direction').value;
        const orderType = document.getElementById('pt-order-type').value;
        const price = document.getElementById('pt-price').value;
        const volume = parseInt(document.getElementById('pt-volume').value);

        if (!code) {
            App.toast('请输入股票代码', 'error');
            return;
        }

        if (!volume || volume <= 0) {
            App.toast('请输入有效数量', 'error');
            return;
        }

        if (volume % 100 !== 0) {
            App.toast('数量必须是100的整数倍', 'error');
            return;
        }

        const body = {
            code,
            direction,
            order_type: orderType,
            volume,
        };

        if (orderType !== 'market' && price) {
            body.price = parseFloat(price);
        }

        try {
            const res = await fetch('/api/paper/orders', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });

            const data = await res.json();

            if (!res.ok) {
                throw new Error(data.detail || data.message || `HTTP ${res.status}`);
            }

            App.toast(`订单创建成功: ${data.data.order_id}`, 'success');
            this.loadOrders();
            this.loadPositions();
        } catch (e) {
            App.toast(`创建订单失败: ${e.message}`, 'error');
        }
    },

    async cancelOrder(orderId) {
        if (!confirm('确定要撤销此订单吗？')) return;

        try {
            const res = await fetch(`/api/paper/orders/${orderId}`, {
                method: 'DELETE',
            });

            const data = await res.json();

            if (!res.ok) {
                throw new Error(data.detail || data.message || `HTTP ${res.status}`);
            }

            App.toast('订单已撤销', 'success');
            this.loadOrders();
        } catch (e) {
            App.toast(`撤销订单失败: ${e.message}`, 'error');
        }
    },

    async loadOrders() {
        try {
            const data = await App.fetchJSON('/api/paper/orders?status=pending&page_size=100');
            this.state.orders = data.data.items || [];
            this.renderOrders();
        } catch (e) {
            console.error('加载订单失败:', e);
        }
    },

    renderOrders() {
        const tbody = document.querySelector('#pt-orders-table tbody');
        if (!tbody) return;

        if (this.state.orders.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-muted" style="text-align:center">暂无挂单</td></tr>';
            return;
        }

        tbody.innerHTML = this.state.orders.map(order => {
            const typeMap = {
                'market': '市价',
                'limit': '限价',
                'stop_loss': '止损',
                'take_profit': '止盈',
            };
            const dirClass = order.direction === 'buy' ? 'text-up' : 'text-down';
            const dirText = order.direction === 'buy' ? '买入' : '卖出';

            return `<tr>
                <td>${App.escapeHTML(order.code)}</td>
                <td class="${dirClass}">${dirText}</td>
                <td>${typeMap[order.order_type] || order.order_type}</td>
                <td>${order.price ? '¥' + order.price.toFixed(2) : '市价'}</td>
                <td>${order.volume}</td>
                <td><span class="badge badge-warning">待撮合</span></td>
                <td>
                    <button class="btn btn-sm btn-danger" onclick="PaperTrading.cancelOrder('${order.order_id}')">
                        撤销
                    </button>
                </td>
            </tr>`;
        }).join('');
    },

    togglePriceInput() {
        const orderType = document.getElementById('pt-order-type').value;
        const priceGroup = document.getElementById('pt-price-group');

        if (priceGroup) {
            priceGroup.style.display = orderType === 'market' ? 'none' : 'block';
        }
    },

    // ────────────── 持仓管理 ──────────────

    async loadPositions() {
        try {
            const data = await App.fetchJSON('/api/paper/positions');
            this.state.positions = data.data || [];
            this.renderPositions();
        } catch (e) {
            console.error('加载持仓失败:', e);
        }
    },

    renderPositions() {
        const tbody = document.querySelector('#pt-positions-table tbody');
        if (!tbody) return;

        if (this.state.positions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="9" class="text-muted" style="text-align:center">暂无持仓</td></tr>';
            return;
        }

        tbody.innerHTML = this.state.positions.map(pos => {
            const pnlClass = pos.unrealized_pnl >= 0 ? 'text-up' : 'text-down';
            const pnlSign = pos.unrealized_pnl >= 0 ? '+' : '';

            return `<tr>
                <td>${App.escapeHTML(pos.code)}</td>
                <td>${pos.volume}</td>
                <td>¥${pos.avg_price.toFixed(2)}</td>
                <td>¥${pos.current_price.toFixed(2)}</td>
                <td>¥${pos.market_value.toLocaleString()}</td>
                <td class="${pnlClass}">${pnlSign}¥${pos.unrealized_pnl.toFixed(2)}</td>
                <td class="${pnlClass}">${pnlSign}${pos.unrealized_pnl_pct.toFixed(2)}%</td>
                <td>
                    <input type="number" class="form-control form-control-sm"
                           value="${pos.stop_loss_price || ''}"
                           placeholder="止损价"
                           onchange="PaperTrading.updateStopLoss('${pos.code}', this.value, 'stop_loss')">
                </td>
                <td>
                    <input type="number" class="form-control form-control-sm"
                           value="${pos.take_profit_price || ''}"
                           placeholder="止盈价"
                           onchange="PaperTrading.updateStopLoss('${pos.code}', this.value, 'take_profit')">
                </td>
            </tr>`;
        }).join('');
    },

    async updateStopLoss(code, value, type) {
        const body = {};
        if (type === 'stop_loss') {
            body.stop_loss_price = value ? parseFloat(value) : null;
        } else {
            body.take_profit_price = value ? parseFloat(value) : null;
        }

        try {
            const res = await fetch(`/api/paper/positions/${code}/stop-loss`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });

            const data = await res.json();

            if (!res.ok) {
                throw new Error(data.detail || data.message || `HTTP ${res.status}`);
            }

            App.toast('止损止盈价格已更新', 'success');
        } catch (e) {
            App.toast(`更新失败: ${e.message}`, 'error');
        }
    },

    async closePosition(code, volume = null) {
        const confirmMsg = volume ? `确定要平仓 ${code} ${volume}股吗？` : `确定要全部平仓 ${code} 吗？`;
        if (!confirm(confirmMsg)) return;

        try {
            const url = volume
                ? `/api/paper/positions/${code}/close?volume=${volume}`
                : `/api/paper/positions/${code}/close`;

            const res = await fetch(url, { method: 'POST' });
            const data = await res.json();

            if (!res.ok) {
                throw new Error(data.detail || data.message || `HTTP ${res.status}`);
            }

            App.toast('平仓订单已创建', 'success');
            this.loadOrders();
            this.loadPositions();
        } catch (e) {
            App.toast(`平仓失败: ${e.message}`, 'error');
        }
    },

    // ────────────── 绩效分析 ──────────────

    async loadPerformance() {
        try {
            const data = await App.fetchJSON('/api/paper/performance');
            this.state.performance = data.data || {};
            this.renderPerformance();
        } catch (e) {
            console.error('加载绩效失败:', e);
        }
    },

    renderPerformance() {
        const perf = this.state.performance;

        // 更新绩效统计卡片
        const elements = {
            'pt-total-equity': perf.total_equity ? App.fmt(perf.total_equity) : '--',
            'pt-daily-return': perf.daily_return ? (perf.daily_return * 100).toFixed(2) + '%' : '--',
            'pt-cumulative-return': perf.cumulative_return ? (perf.cumulative_return * 100).toFixed(2) + '%' : '--',
            'pt-max-drawdown': perf.max_drawdown ? (perf.max_drawdown * 100).toFixed(2) + '%' : '--',
            'pt-sharpe-ratio': perf.sharpe_ratio ? perf.sharpe_ratio.toFixed(4) : '--',
            'pt-sortino-ratio': perf.sortino_ratio ? perf.sortino_ratio.toFixed(4) : '--',
            'pt-calmar-ratio': perf.calmar_ratio ? perf.calmar_ratio.toFixed(4) : '--',
            'pt-win-rate': perf.win_rate ? (perf.win_rate * 100).toFixed(2) + '%' : '--',
            'pt-profit-loss-ratio': perf.profit_loss_ratio ? perf.profit_loss_ratio.toFixed(4) : '--',
            'pt-total-trades': perf.total_trades || '--',
            'pt-winning-trades': perf.winning_trades || '--',
            'pt-losing-trades': perf.losing_trades || '--',
            'pt-avg-win': perf.avg_win ? '¥' + perf.avg_win.toFixed(2) : '--',
            'pt-avg-loss': perf.avg_loss ? '¥' + perf.avg_loss.toFixed(2) : '--',
            'pt-max-consecutive-wins': perf.max_consecutive_wins || '--',
            'pt-max-consecutive-losses': perf.max_consecutive_losses || '--',
        };

        Object.entries(elements).forEach(([id, value]) => {
            const el = document.getElementById(id);
            if (el) el.textContent = value;
        });
    },

    async loadMonthlyHeatmap() {
        try {
            const data = await App.fetchJSON('/api/paper/performance/monthly-heatmap');
            this.renderMonthlyHeatmap(data.data || {});
        } catch (e) {
            console.error('加载月度热力图失败:', e);
        }
    },

    renderMonthlyHeatmap(monthlyReturns) {
        const container = document.getElementById('pt-monthly-heatmap');
        if (!container) return;

        const months = Object.keys(monthlyReturns).sort();
        if (months.length === 0) {
            container.innerHTML = '<p class="text-muted">暂无数据</p>';
            return;
        }

        // 创建热力图表格
        let html = '<div class="heatmap-grid">';
        months.forEach(month => {
            const value = monthlyReturns[month];
            const color = this.getHeatmapColor(value);
            const sign = value >= 0 ? '+' : '';
            html += `
                <div class="heatmap-cell" style="background-color: ${color}">
                    <div class="heatmap-month">${month}</div>
                    <div class="heatmap-value">${sign}${(value * 100).toFixed(1)}%</div>
                </div>
            `;
        });
        html += '</div>';

        container.innerHTML = html;
    },

    getHeatmapColor(value) {
        // 根据收益值返回颜色
        if (value > 0.1) return 'rgba(34, 197, 94, 0.8)';
        if (value > 0.05) return 'rgba(34, 197, 94, 0.6)';
        if (value > 0) return 'rgba(34, 197, 94, 0.4)';
        if (value > -0.05) return 'rgba(239, 68, 68, 0.4)';
        if (value > -0.1) return 'rgba(239, 68, 68, 0.6)';
        return 'rgba(239, 68, 68, 0.8)';
    },

    // ────────────── 资金曲线 ──────────────

    async loadEquityCurve() {
        try {
            const data = await App.fetchJSON('/api/paper/equity-curve-v2');
            this.state.equityCurve = data.data || [];
            this.renderEquityCurve();
        } catch (e) {
            console.error('加载资金曲线失败:', e);
        }
    },

    renderEquityCurve() {
        const canvas = document.getElementById('pt-equity-chart');
        if (!canvas) return;

        const curve = this.state.equityCurve;
        if (curve.length < 2) return;

        const labels = curve.map((p, i) => i + 1);
        const values = curve.map(p => p.equity);

        if (this.charts.equityCurve) {
            this.charts.equityCurve.data.labels = labels;
            this.charts.equityCurve.data.datasets[0].data = values;
            this.charts.equityCurve.update('none');
            return;
        }

        this.charts.equityCurve = new Chart(canvas, {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    label: '权益',
                    data: values,
                    borderColor: '#4a90d9',
                    backgroundColor: 'rgba(74,144,217,0.1)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 0,
                    borderWidth: 2,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                scales: {
                    x: { display: false },
                    y: {
                        ticks: {
                            callback: v => '¥' + (v / 10000).toFixed(1) + '万',
                        },
                    },
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: ctx => '¥' + ctx.parsed.y.toLocaleString(),
                        },
                    },
                },
            },
        });
    },

    async loadDrawdownCurve() {
        try {
            const data = await App.fetchJSON('/api/paper/drawdown');
            this.renderDrawdownCurve(data.data || []);
        } catch (e) {
            console.error('加载回撤曲线失败:', e);
        }
    },

    renderDrawdownCurve(drawdownData) {
        const canvas = document.getElementById('pt-drawdown-chart');
        if (!canvas) return;

        if (drawdownData.length < 2) return;

        const labels = drawdownData.map((p, i) => i + 1);
        const values = drawdownData.map(p => p.drawdown * 100);

        if (this.charts.drawdown) {
            this.charts.drawdown.data.labels = labels;
            this.charts.drawdown.data.datasets[0].data = values;
            this.charts.drawdown.update('none');
            return;
        }

        this.charts.drawdown = new Chart(canvas, {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    label: '回撤',
                    data: values,
                    borderColor: '#ef4444',
                    backgroundColor: 'rgba(239,68,68,0.1)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 0,
                    borderWidth: 2,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                scales: {
                    x: { display: false },
                    y: {
                        ticks: {
                            callback: v => v.toFixed(1) + '%',
                        },
                    },
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: ctx => ctx.parsed.y.toFixed(2) + '%',
                        },
                    },
                },
            },
        });
    },

    // ────────────── 交易历史 ──────────────

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
        if (!tbody) return;

        if (this.state.trades.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="text-muted" style="text-align:center">暂无交易记录</td></tr>';
            return;
        }

        tbody.innerHTML = this.state.trades.map(trade => {
            const time = trade.created_at ? new Date(trade.created_at).toLocaleString('zh-CN') : '--';
            const dirClass = trade.direction === 'buy' ? 'text-up' : 'text-down';
            const dirText = trade.direction === 'buy' ? '买入' : '卖出';
            const profitClass = trade.profit >= 0 ? 'text-up' : 'text-down';
            const profitSign = trade.profit >= 0 ? '+' : '';

            return `<tr>
                <td>${time}</td>
                <td>${App.escapeHTML(trade.code)}</td>
                <td class="${dirClass}">${dirText}</td>
                <td>¥${trade.price.toFixed(2)}</td>
                <td>${trade.volume}</td>
                <td class="${profitClass}">${profitSign}¥${trade.profit.toFixed(2)}</td>
                <td>${trade.strategy_name || '--'}</td>
                <td>${trade.signal_reason || '--'}</td>
            </tr>`;
        }).join('');

        // 渲染分页
        this.renderPagination(pagination);
    },

    renderPagination(pagination) {
        const container = document.getElementById('pt-trades-pagination');
        if (!container) return;

        const { page, total_pages } = pagination;
        let html = '';

        if (total_pages > 1) {
            html += `<button class="btn btn-sm" ${page <= 1 ? 'disabled' : ''} onclick="PaperTrading.loadTrades(${page - 1})">上一页</button>`;
            html += `<span class="mx-sm">第 ${page} / ${total_pages} 页</span>`;
            html += `<button class="btn btn-sm" ${page >= total_pages ? 'disabled' : ''} onclick="PaperTrading.loadTrades(${page + 1})">下一页</button>`;
        }

        container.innerHTML = html;
    },

    async exportTrades(format = 'csv') {
        try {
            const data = await App.fetchJSON(`/api/paper/trades-v2/export?format=${format}`);

            if (format === 'csv') {
                // 下载CSV文件
                const blob = new Blob([data.data.content], { type: 'text/csv;charset=utf-8;' });
                const link = document.createElement('a');
                link.href = URL.createObjectURL(blob);
                link.download = data.data.filename;
                link.click();
            } else {
                // 下载JSON文件
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

    // ────────────── 风控管理 ──────────────

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
            tbody.innerHTML = '<tr><td colspan="5" class="text-muted" style="text-align:center">暂无风控事件</td></tr>';
            return;
        }

        tbody.innerHTML = this.state.riskEvents.map(event => {
            const time = event.created_at ? new Date(event.created_at).toLocaleString('zh-CN') : '--';
            const typeMap = {
                'stop_loss': '止损',
                'take_profit': '止盈',
                'trailing_stop': '移动止损',
                'position_limit': '仓位限制',
                'drawdown_limit': '回撤限制',
            };

            return `<tr>
                <td>${time}</td>
                <td>${App.escapeHTML(event.code || '--')}</td>
                <td>${typeMap[event.event_type] || event.event_type}</td>
                <td>${event.trigger_price ? '¥' + event.trigger_price.toFixed(2) : '--'}</td>
                <td>${App.escapeHTML(event.reason)}</td>
            </tr>`;
        }).join('');
    },

    // ────────────── 状态管理 ──────────────

    async loadStatus() {
        try {
            const data = await App.fetchJSON('/api/paper/status');
            this.state.isRunning = data.running;
            this.state.config = data.config || {};
            this.renderStatus();
        } catch (e) {
            console.error('加载状态失败:', e);
        }
    },

    renderStatus() {
        const statusEl = document.getElementById('pt-status');
        const equityEl = document.getElementById('pt-equity');
        const posCountEl = document.getElementById('pt-pos-count');
        const tradeCountEl = document.getElementById('pt-trade-count');

        if (statusEl) {
            statusEl.textContent = this.state.isRunning ? '运行中' : '已停止';
            statusEl.className = 'stat-value ' + (this.state.isRunning ? 'text-up' : '');
        }

        if (equityEl) equityEl.textContent = this.state.performance.total_equity
            ? App.fmt(this.state.performance.total_equity) : '--';

        if (posCountEl) posCountEl.textContent = this.state.positions.length;

        if (tradeCountEl) tradeCountEl.textContent = this.state.performance.total_trades || 0;
    },

    // ────────────── 轮询管理 ──────────────

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

    // ────────────── 工具方法 ──────────────

    formatMoney(value) {
        if (value == null) return '--';
        return '¥' + value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    },

    formatPercent(value) {
        if (value == null) return '--';
        return (value * 100).toFixed(2) + '%';
    },
};

// 页面加载时初始化
document.addEventListener('DOMContentLoaded', () => {
    PaperTrading.init();
});
