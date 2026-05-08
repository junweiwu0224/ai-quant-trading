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
        positionPie: null,
    },

    // ────────────── 股票名称缓存 ──────────────
    _stockNameCache: {},

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
        this.initSubTabs();
        this.loadStrategyList();
        if (!this._loaded) this._showSkeletons();
        this.loadStatus();
        this.loadPositions();
        this.loadOrders();
        this.loadPerformance();
        this.loadEquityCurve();
        this.startPolling();
    },

    // ────────────── 子 Tab 切换 ──────────────
    initSubTabs() {
        document.querySelectorAll('#paper-sub-tabs .paper-sub-tab').forEach(btn => {
            btn.addEventListener('click', () => this.switchSubTab(btn.dataset.tab));
        });
    },

    switchSubTab(tabName) {
        // 更新 Tab 按钮状态
        document.querySelectorAll('#paper-sub-tabs .paper-sub-tab').forEach(btn => {
            const isActive = btn.dataset.tab === tabName;
            btn.classList.toggle('active', isActive);
            btn.setAttribute('aria-selected', String(isActive));
        });
        // 更新面板显示
        document.querySelectorAll('#paper-sub-panels .paper-sub-panel').forEach(panel => {
            panel.classList.toggle('hidden', panel.id !== `paper-panel-${tabName}`);
        });
        // 切换到绩效 Tab 时加载图表数据
        if (tabName === 'perf') {
            this.loadMonthlyHeatmap();
            this.loadReturnDistribution();
            this.loadWeekdayEffect();
            this.loadPerformanceTrend();
            this.loadTradeFrequency();
        }
    },

    // ────────────── 动态策略列表 ──────────────
    async loadStrategyList() {
        try {
            const data = await App.fetchJSON('/api/strategy/list');
            const strategies = data.data || data || [];
            const select = document.getElementById('pp-strategy');
            if (!select || !Array.isArray(strategies)) return;

            // 保留当前选中值
            const currentValue = select.value;

            // 清空并重新填充
            select.innerHTML = '';
            strategies.forEach(s => {
                const opt = document.createElement('option');
                opt.value = s.name || s.id;
                opt.textContent = s.label || s.display_name || s.name || s.id;
                select.appendChild(opt);
            });

            // 恢复选中状态
            if (currentValue && select.querySelector(`option[value="${currentValue}"]`)) {
                select.value = currentValue;
            }

            // 如果没有策略，添加默认选项
            if (strategies.length === 0) {
                select.innerHTML = `
                    <option value="dual_ma">双均线策略</option>
                    <option value="bollinger">布林带策略</option>
                    <option value="momentum">动量策略</option>
                `;
            }
        } catch (e) {
            console.warn('加载策略列表失败，使用默认策略:', e);
            // 保持默认策略列表
        }
    },

    _showSkeletons() {
        document.querySelectorAll('#tab-paper .stat-value').forEach(el => {
            el.classList.add('skeleton-text');
        });
    },

    _hideSkeletons() {
        document.querySelectorAll('#tab-paper .stat-value.skeleton-text').forEach(el => {
            el.classList.remove('skeleton-text');
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

        // 股票代码输入 - 实时行情预览
        const codeInput = document.getElementById('pt-code');
        if (codeInput) {
            let debounceTimer = null;
            codeInput.addEventListener('input', () => {
                clearTimeout(debounceTimer);
                debounceTimer = setTimeout(() => this._loadQuotePreview(codeInput.value.trim()), 300);
            });
        }
    },

    // ────────────── 实时行情预览 ──────────────
    async _loadQuotePreview(code) {
        const preview = document.getElementById('pt-quote-preview');
        if (!preview) return;

        if (!code || code.length < 6) {
            preview.classList.add('hidden');
            return;
        }

        try {
            const data = await App.fetchJSON(`/api/stock/detail/${code}`);
            if (!data || !data.data) {
                preview.classList.add('hidden');
                return;
            }

            const quote = data.data;
            const price = quote.current_price || quote.price;
            const change = quote.change_pct || 0;
            const changeClass = change >= 0 ? 'text-up' : 'text-down';
            const changeSign = change >= 0 ? '+' : '';

            document.getElementById('pt-quote-name').textContent = quote.name || '--';
            document.getElementById('pt-quote-code').textContent = code;
            document.getElementById('pt-quote-price').textContent = price ? `¥${price.toFixed(2)}` : '--';
            document.getElementById('pt-quote-price').className = change >= 0 ? 'text-up' : 'text-down';
            document.getElementById('pt-quote-change').textContent = change ? `${changeSign}${change.toFixed(2)}%` : '--';
            document.getElementById('pt-quote-change').className = changeClass;
            document.getElementById('pt-quote-high').textContent = quote.high ? `¥${quote.high.toFixed(2)}` : '--';
            document.getElementById('pt-quote-low').textContent = quote.low ? `¥${quote.low.toFixed(2)}` : '--';
            document.getElementById('pt-quote-volume').textContent = quote.volume ? this._formatVolume(quote.volume) : '--';

            preview.classList.remove('hidden');
        } catch (e) {
            preview.classList.add('hidden');
        }
    },

    _formatVolume(vol) {
        if (vol >= 100000000) return (vol / 100000000).toFixed(2) + '亿';
        if (vol >= 10000) return (vol / 10000).toFixed(2) + '万';
        return vol.toString();
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
            await this._fetchStockNames(this.state.positions.map(p => p.code));
            this.renderPositions();
            this.renderPositionPie();
        } catch (e) {
            console.error('加载持仓失败:', e);
        }
    },

    async _fetchStockNames(codes) {
        const missing = codes.filter(c => !this._stockNameCache[c]);
        if (missing.length === 0) return;
        try {
            const results = await Promise.allSettled(
                missing.map(code =>
                    App.fetchJSON(`/api/stock/detail/${code}`)
                        .then(d => ({ code, name: d.data?.name || code }))
                )
            );
            results.forEach(r => {
                if (r.status === 'fulfilled') {
                    this._stockNameCache[r.value.code] = r.value.name;
                }
            });
        } catch (e) { /* ignore */ }
    },

    _calcStopLossDistance(pos) {
        const price = pos.current_price;
        const avg = pos.avg_price;
        if (!price || !avg) return { slDist: null, tpDist: null, slPct: null, tpPct: null };

        const slDist = pos.stop_loss_price ? ((price - pos.stop_loss_price) / price * 100) : null;
        const tpDist = pos.take_profit_price ? ((pos.take_profit_price - price) / price * 100) : null;
        // 盈亏百分比（相对于成本）
        const pnlPct = (price / avg - 1) * 100;
        return { slDist, tpDist, pnlPct };
    },

    _renderStopLossBar(pos) {
        const { slDist, tpDist, pnlPct } = this._calcStopLossDistance(pos);
        if (slDist === null && tpDist === null) return '';

        // 进度条：从止损到止盈的区间，当前价在其中的位置
        const sl = pos.stop_loss_price;
        const tp = pos.take_profit_price;
        if (sl && tp && tp > sl) {
            const range = tp - sl;
            const pct = Math.max(0, Math.min(100, ((pos.current_price - sl) / range) * 100));
            const barColor = pnlPct >= 0 ? 'var(--up-color)' : 'var(--down-color)';
            return `<div class="stop-bar-wrap" title="止损 ${sl.toFixed(2)} | 止盈 ${tp.toFixed(2)}">
                <div class="stop-bar">
                    <div class="stop-bar-fill" style="width:${pct}%;background:${barColor}"></div>
                    <div class="stop-bar-marker" style="left:0" title="止损"></div>
                    <div class="stop-bar-marker" style="left:100%" title="止盈"></div>
                </div>
                <div class="stop-bar-labels">
                    <span class="text-down">${slDist !== null ? slDist.toFixed(1) + '%' : '--'}</span>
                    <span class="text-up">${tpDist !== null ? '+' + tpDist.toFixed(1) + '%' : '--'}</span>
                </div>
            </div>`;
        }

        // 只有止损或只有止盈
        let html = '<div class="stop-bar-labels">';
        if (slDist !== null) {
            const cls = slDist < 3 ? 'text-up' : slDist < 8 ? '' : 'text-down';
            html += `<span class="${cls}">距止损 ${slDist.toFixed(1)}%</span>`;
        }
        if (tpDist !== null) {
            html += `<span class="text-up">距止盈 +${tpDist.toFixed(1)}%</span>`;
        }
        html += '</div>';
        return html;
    },

    renderPositions() {
        const tbody = document.querySelector('#pt-positions-table tbody');
        const emptyHint = document.getElementById('pt-positions-empty');
        if (!tbody) return;

        if (this.state.positions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="10" class="text-muted" style="text-align:center">暂无持仓</td></tr>';
            if (emptyHint) emptyHint.style.display = 'block';
            return;
        }

        if (emptyHint) emptyHint.style.display = 'none';
        tbody.innerHTML = this.state.positions.map(pos => {
            const pnlClass = pos.unrealized_pnl >= 0 ? 'text-up' : 'text-down';
            const pnlSign = pos.unrealized_pnl >= 0 ? '+' : '';
            const name = this._stockNameCache[pos.code] || pos.code;

            return `<tr>
                <td><span class="pos-name">${App.escapeHTML(name)}</span><br><span class="text-muted" style="font-size:0.75rem">${App.escapeHTML(pos.code)}</span></td>
                <td>${pos.volume}</td>
                <td>¥${pos.avg_price.toFixed(2)}</td>
                <td>¥${pos.current_price.toFixed(2)}</td>
                <td>¥${pos.market_value.toLocaleString()}</td>
                <td class="${pnlClass}">${pnlSign}¥${pos.unrealized_pnl.toFixed(2)}</td>
                <td class="${pnlClass}">${pnlSign}${pos.unrealized_pnl_pct.toFixed(2)}%</td>
                <td>${this._renderStopLossBar(pos)}</td>
                <td>
                    <input type="number" class="form-control form-control-sm"
                           value="${pos.stop_loss_price || ''}"
                           placeholder="止损"
                           onchange="PaperTrading.updateStopLoss('${pos.code}', this.value, 'stop_loss')">
                </td>
                <td>
                    <input type="number" class="form-control form-control-sm"
                           value="${pos.take_profit_price || ''}"
                           placeholder="止盈"
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

    async closeAllPositions() {
        if (this.state.positions.length === 0) {
            App.toast('没有持仓需要平仓', 'info');
            return;
        }

        const confirmMsg = `确定要平仓所有 ${this.state.positions.length} 只持仓吗？`;
        if (!confirm(confirmMsg)) return;

        const btn = document.getElementById('pt-close-all-btn');
        if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>平仓中...'; }

        try {
            const results = await Promise.allSettled(
                this.state.positions.map(pos =>
                    fetch(`/api/paper/positions/${pos.code}/close`, { method: 'POST' })
                        .then(res => res.json())
                        .then(data => {
                            if (!data.success) throw new Error(data.detail || data.message);
                            return { code: pos.code, success: true };
                        })
                        .catch(e => ({ code: pos.code, success: false, error: e.message }))
                )
            );

            const succeeded = results.filter(r => r.status === 'fulfilled' && r.value.success).length;
            const failed = results.length - succeeded;

            if (failed === 0) {
                App.toast(`已平仓 ${succeeded} 只持仓`, 'success');
            } else {
                App.toast(`平仓完成：${succeeded} 成功，${failed} 失败`, 'warning');
            }

            this.loadOrders();
            this.loadPositions();
        } catch (e) {
            App.toast(`批量平仓失败: ${e.message}`, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = '一键清仓'; }
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
        // A股惯例：红涨绿跌
        if (value > 0.1) return 'rgba(198, 87, 70, 0.8)';   // var(--up-color)
        if (value > 0.05) return 'rgba(198, 87, 70, 0.6)';
        if (value > 0) return 'rgba(198, 87, 70, 0.4)';
        if (value > -0.05) return 'rgba(16, 185, 129, 0.4)'; // var(--down-color)
        if (value > -0.1) return 'rgba(16, 185, 129, 0.6)';
        return 'rgba(16, 185, 129, 0.8)';
    },

    // ────────────── 收益分布 ──────────────

    async loadReturnDistribution() {
        try {
            const data = await App.fetchJSON('/api/paper/performance/return-distribution');
            this.renderReturnDistribution(data.data || {});
        } catch (e) {
            console.error('加载收益分布失败:', e);
        }
    },

    renderReturnDistribution(distribution) {
        const canvas = document.getElementById('pt-return-dist-chart');
        if (!canvas) return;

        const { bins = [], counts = [] } = distribution;
        if (bins.length === 0) return;

        const labels = bins.map(b => (b * 100).toFixed(1) + '%');
        const colors = bins.map(b => b >= 0 ? 'rgba(198, 87, 70, 0.7)' : 'rgba(16, 185, 129, 0.7)');

        if (this.charts.returnDist) {
            this.charts.returnDist.data.labels = labels;
            this.charts.returnDist.data.datasets[0].data = counts;
            this.charts.returnDist.data.datasets[0].backgroundColor = colors;
            this.charts.returnDist.update('none');
            return;
        }

        this.charts.returnDist = new Chart(canvas, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: '频次',
                    data: counts,
                    backgroundColor: colors,
                    borderWidth: 0,
                    borderRadius: 4,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                scales: {
                    x: {
                        ticks: {
                            maxTicksLimit: 10,
                            font: { size: 11 },
                        },
                    },
                    y: {
                        ticks: {
                            font: { size: 11 },
                        },
                    },
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: ctx => `${ctx.parsed.y} 次`,
                        },
                    },
                },
            },
        });
    },

    // ────────────── 星期效应 ──────────────

    async loadWeekdayEffect() {
        try {
            const data = await App.fetchJSON('/api/paper/performance/weekday-effect');
            this.renderWeekdayEffect(data.data || {});
        } catch (e) {
            console.error('加载星期效应失败:', e);
        }
    },

    renderWeekdayEffect(effect) {
        const canvas = document.getElementById('pt-weekday-chart');
        if (!canvas) return;

        const weekdays = ['周一', '周二', '周三', '周四', '周五'];
        const values = weekdays.map((_, i) => effect[i + 1] || 0);
        const colors = values.map(v => v >= 0 ? 'rgba(198, 87, 70, 0.7)' : 'rgba(16, 185, 129, 0.7)');

        if (this.charts.weekdayEffect) {
            this.charts.weekdayEffect.data.datasets[0].data = values;
            this.charts.weekdayEffect.data.datasets[0].backgroundColor = colors;
            this.charts.weekdayEffect.update('none');
            return;
        }

        this.charts.weekdayEffect = new Chart(canvas, {
            type: 'bar',
            data: {
                labels: weekdays,
                datasets: [{
                    label: '平均收益率',
                    data: values,
                    backgroundColor: colors,
                    borderWidth: 0,
                    borderRadius: 4,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                scales: {
                    y: {
                        ticks: {
                            callback: v => (v * 100).toFixed(2) + '%',
                            font: { size: 11 },
                        },
                    },
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: ctx => (ctx.parsed.y * 100).toFixed(2) + '%',
                        },
                    },
                },
            },
        });
    },

    // ────────────── 资金曲线 + 基准对比 ──────────────

    _benchmarkCurve: [],

    async loadEquityCurve() {
        try {
            const [eqData, bmData] = await Promise.allSettled([
                App.fetchJSON('/api/paper/equity-curve-v2'),
                App.fetchJSON('/api/stock/market/benchmark?count=120'),
            ]);
            this.state.equityCurve = eqData.status === 'fulfilled' ? (eqData.value.data || []) : [];
            this._benchmarkCurve = bmData.status === 'fulfilled' ? (bmData.value.data || []) : [];
            this.renderEquityCurve();
        } catch (e) {
            console.error('加载资金曲线失败:', e);
        }
    },

    _normalizeBenchmark(curve, benchmark) {
        if (curve.length < 2 || benchmark.length < 2) return [];
        // 用收益率归一化：基准从 100% 开始，与权益曲线同比例
        const baseEquity = curve[0].equity;
        const baseBm = benchmark[0].close || benchmark[0].price || 1;
        return benchmark.map(bm => {
            const close = bm.close || bm.price || 0;
            return baseEquity * (close / baseBm);
        });
    },

    renderEquityCurve() {
        const canvas = document.getElementById('pt-equity-chart');
        const emptyHint = document.getElementById('pt-equity-empty');
        if (!canvas) return;

        const curve = this.state.equityCurve;
        if (curve.length < 2) {
            if (emptyHint) emptyHint.style.display = 'block';
            return;
        }

        if (emptyHint) emptyHint.style.display = 'none';
        const labels = curve.map((p, i) => i + 1);
        const values = curve.map(p => p.equity);

        const datasets = [{
            label: '策略权益',
            data: values,
            borderColor: '#4a90d9',
            backgroundColor: 'rgba(74,144,217,0.1)',
            fill: true,
            tension: 0.3,
            pointRadius: 0,
            borderWidth: 2,
        }];

        // 基准对比
        const bmValues = this._normalizeBenchmark(curve, this._benchmarkCurve);
        if (bmValues.length > 0) {
            // 对齐长度
            const aligned = [];
            for (let i = 0; i < curve.length; i++) {
                aligned.push(bmValues[i] || null);
            }
            datasets.push({
                label: '沪深300',
                data: aligned,
                borderColor: '#f59e0b',
                backgroundColor: 'transparent',
                borderDash: [4, 4],
                tension: 0.3,
                pointRadius: 0,
                borderWidth: 1.5,
            });
        }

        if (this.charts.equityCurve) {
            this.charts.equityCurve.data.labels = labels;
            this.charts.equityCurve.data.datasets = datasets;
            this.charts.equityCurve.options.plugins.legend.display = datasets.length > 1;
            this.charts.equityCurve.update('none');
            return;
        }

        this.charts.equityCurve = new Chart(canvas, {
            type: 'line',
            data: { labels, datasets },
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
                    legend: { display: datasets.length > 1, labels: { font: { size: 11 } } },
                    tooltip: {
                        callbacks: {
                            label: ctx => `${ctx.dataset.label}: ¥${ctx.parsed.y.toLocaleString()}`,
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

    _tradeFilter: { code: '', direction: '' },

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
            tbody.innerHTML = '<tr><td colspan="9" class="text-muted" style="text-align:center">暂无交易记录</td></tr>';
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
                <td>${App.escapeHTML(trade.code)}</td>
                <td class="${dirClass}">${dirText}</td>
                <td>¥${trade.price.toFixed(2)}</td>
                <td>${trade.volume}</td>
                <td class="${profitClass}">${profitSign}¥${trade.profit.toFixed(2)}</td>
                <td>${cost > 0 ? '¥' + cost.toFixed(2) : '--'}</td>
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

    // ────────────── 绩效趋势图 ──────────────

    async loadPerformanceTrend() {
        try {
            const data = await App.fetchJSON('/api/paper/performance/daily?days=60');
            this.renderPerformanceTrend(data.data || []);
        } catch (e) {
            console.error('加载绩效趋势失败:', e);
        }
    },

    renderPerformanceTrend(daily) {
        const canvas = document.getElementById('pt-perf-trend-chart');
        if (!canvas || daily.length < 2) return;

        const labels = daily.map(d => d.date);
        const sharpe = daily.map(d => d.sharpe_ratio || 0);
        const drawdown = daily.map(d => (d.max_drawdown || 0) * 100);

        if (this.charts.perfTrend) {
            this.charts.perfTrend.data.labels = labels;
            this.charts.perfTrend.data.datasets[0].data = sharpe;
            this.charts.perfTrend.data.datasets[1].data = drawdown;
            this.charts.perfTrend.update('none');
            return;
        }

        this.charts.perfTrend = new Chart(canvas, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Sharpe',
                        data: sharpe,
                        borderColor: '#4a90d9',
                        backgroundColor: 'transparent',
                        tension: 0.3,
                        pointRadius: 0,
                        borderWidth: 2,
                        yAxisID: 'y',
                    },
                    {
                        label: '最大回撤',
                        data: drawdown,
                        borderColor: '#ef4444',
                        backgroundColor: 'transparent',
                        borderDash: [4, 4],
                        tension: 0.3,
                        pointRadius: 0,
                        borderWidth: 1.5,
                        yAxisID: 'y1',
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                interaction: { mode: 'index', intersect: false },
                scales: {
                    x: { ticks: { maxTicksLimit: 8, font: { size: 10 } } },
                    y: {
                        position: 'left',
                        title: { display: true, text: 'Sharpe', font: { size: 10 } },
                        ticks: { font: { size: 10 } },
                    },
                    y1: {
                        position: 'right',
                        title: { display: true, text: '回撤 %', font: { size: 10 } },
                        ticks: { callback: v => v.toFixed(0) + '%', font: { size: 10 } },
                        grid: { drawOnChartArea: false },
                    },
                },
                plugins: {
                    legend: { labels: { font: { size: 11 } } },
                    tooltip: {
                        callbacks: {
                            label: ctx => {
                                if (ctx.datasetIndex === 1) return `回撤: ${ctx.parsed.y.toFixed(2)}%`;
                                return `Sharpe: ${ctx.parsed.y.toFixed(4)}`;
                            },
                        },
                    },
                },
            },
        });
    },

    // ────────────── 交易频率热力图 ──────────────

    async loadTradeFrequency() {
        try {
            // 从已有交易数据计算频率
            const data = await App.fetchJSON('/api/paper/trades-v2?page=1&page_size=500');
            const trades = data.data?.items || [];
            this.renderTradeFrequency(trades);
        } catch (e) {
            console.error('加载交易频率失败:', e);
        }
    },

    renderTradeFrequency(trades) {
        const canvas = document.getElementById('pt-frequency-chart');
        if (!canvas) return;

        // 按星期统计
        const weekdayNames = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
        const weekdayCounts = [0, 0, 0, 0, 0, 0, 0];
        trades.forEach(t => {
            if (t.created_at) {
                const d = new Date(t.created_at);
                weekdayCounts[d.getDay()]++;
            }
        });

        // 只显示周一到周五
        const labels = weekdayNames.slice(1, 6);
        const values = weekdayCounts.slice(1, 6);
        const maxVal = Math.max(...values, 1);
        const colors = values.map(v => {
            const intensity = 0.3 + (v / maxVal) * 0.5;
            return `rgba(74, 144, 217, ${intensity})`;
        });

        if (this.charts.frequency) {
            this.charts.frequency.data.datasets[0].data = values;
            this.charts.frequency.data.datasets[0].backgroundColor = colors;
            this.charts.frequency.update('none');
            return;
        }

        this.charts.frequency = new Chart(canvas, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: '交易次数',
                    data: values,
                    backgroundColor: colors,
                    borderWidth: 0,
                    borderRadius: 4,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                scales: {
                    y: { ticks: { stepSize: 1, font: { size: 11 } } },
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: ctx => `${ctx.parsed.y} 笔交易`,
                        },
                    },
                },
            },
        });
    },

    // ────────────── 持仓配比饼图 ──────────────

    renderPositionPie() {
        const canvas = document.getElementById('pt-position-pie');
        if (!canvas) return;

        const positions = this.state.positions;
        if (positions.length === 0) {
            if (this.charts.positionPie) { this.charts.positionPie.destroy(); this.charts.positionPie = null; }
            return;
        }

        const labels = positions.map(p => this._stockNameCache[p.code] || p.code);
        const values = positions.map(p => p.market_value);
        const total = values.reduce((a, b) => a + b, 0);
        const colors = [
            '#4a90d9', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6',
            '#1abc9c', '#e67e22', '#3498db', '#e91e63', '#00bcd4',
        ];

        if (this.charts.positionPie) {
            this.charts.positionPie.data.labels = labels;
            this.charts.positionPie.data.datasets[0].data = values;
            this.charts.positionPie.update('none');
            return;
        }

        this.charts.positionPie = new Chart(canvas, {
            type: 'doughnut',
            data: {
                labels,
                datasets: [{
                    data: values,
                    backgroundColor: colors.slice(0, positions.length),
                    borderWidth: 0,
                    hoverOffset: 6,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                cutout: '55%',
                plugins: {
                    legend: {
                        position: 'right',
                        labels: { font: { size: 11 }, padding: 8, usePointStyle: true, pointStyleWidth: 8 },
                    },
                    tooltip: {
                        callbacks: {
                            label: ctx => {
                                const pct = (ctx.parsed / total * 100).toFixed(1);
                                return `${ctx.label}: ¥${ctx.parsed.toLocaleString()} (${pct}%)`;
                            },
                        },
                    },
                },
            },
        });
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
        this._hideSkeletons();
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
};

// 页面加载时初始化
document.addEventListener('DOMContentLoaded', () => {
    PaperTrading.init();
});
