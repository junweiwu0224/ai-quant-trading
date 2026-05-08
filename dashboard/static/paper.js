/* ── 模拟盘控制 ── */

const Paper = {
    _pollInterval: null,
    _equityChart: null,

    async start() {
        // 优先从多选搜索框获取，兼容旧的文本输入
        let codes = [];
        if (App.paperMultiSearch) {
            codes = App.paperMultiSearch.getSelectedCodes();
        }
        if (codes.length === 0) {
            const codesRaw = document.getElementById('pp-codes').value.trim();
            if (codesRaw) codes = codesRaw.split(/[,，\s]+/).filter(Boolean);
        }
        if (codes.length === 0) { App.toast('请选择至少一只股票', 'error'); return; }

        // 收集策略参数
        const params = {};
        document.querySelectorAll('.pp-param-input').forEach(el => {
            const name = el.dataset.param;
            const val = parseFloat(el.value);
            if (name && !isNaN(val)) params[name] = val;
        });

        const body = {
            strategy: document.getElementById('pp-strategy').value,
            codes,
            interval: parseInt(document.getElementById('pp-interval').value, 10) || 30,
            cash: parseFloat(document.getElementById('pp-cash').value) || 1000000,
            enable_risk: document.getElementById('pp-risk').value === 'true',
            params: Object.keys(params).length > 0 ? params : null,
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
            App.toast('模拟盘已启动', 'success');
            this._startPolling();
            this.loadStatus();
        } catch (e) {
            App.toast('启动失败: ' + e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = '启动'; }
        }
    },

    async stop() {
        try {
            const res = await fetch('/api/paper/stop', { method: 'POST' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            App.toast('模拟盘已停止', 'success');
            this._stopPolling();
            this.loadStatus();
        } catch (e) {
            App.toast('停止失败: ' + e.message, 'error');
        }
    },

    async reset() {
        if (!confirm('确定重置模拟盘？将清空所有持仓和交易记录。')) return;
        try {
            const res = await fetch('/api/paper/reset', { method: 'POST' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            App.toast('模拟盘已重置', 'success');
            this._stopPolling();
            this.loadStatus();
            this._clearTrades();
            this._clearEquityChart();
        } catch (e) {
            App.toast('重置失败: ' + e.message, 'error');
        }
    },

    async loadStatus() {
        try {
            const data = await App.fetchJSON('/api/paper/status');
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
            if (equityEl) equityEl.textContent = data.equity != null ? App.fmt(data.equity) : '--';
            if (posCountEl) posCountEl.textContent = Object.keys(data.positions || {}).length;
            if (tradeCountEl) tradeCountEl.textContent = data.trade_count || 0;

            if (startBtn) startBtn.disabled = data.running;
            if (stopBtn) stopBtn.disabled = !data.running;

            if (data.running && !this._pollInterval) {
                this._startPolling();
            } else if (!data.running && this._pollInterval) {
                this._stopPolling();
            }

            // 运行中时刷新交易历史和权益曲线
            if (data.running) {
                this.loadTrades();
                this.loadEquityCurve();
            }
        } catch (e) {
            // silent
        }
    },

    async loadTrades() {
        try {
            const data = await App.fetchJSON('/api/paper/trades');
            const tbody = document.querySelector('#pp-trades-table tbody');
            if (!tbody) return;

            if (!data.trades || data.trades.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" class="text-muted" style="text-align:center">暂无交易记录</td></tr>';
                return;
            }

            tbody.innerHTML = data.trades.slice(-50).reverse().map(t => {
                const time = t.time ? new Date(t.time).toLocaleTimeString('zh-CN') : '--';
                const dir = t.direction === 'long' ? '买入' : '卖出';
                const dirClass = t.direction === 'long' ? 'text-up' : 'text-down';
                return `<tr>
                    <td>${time}</td>
                    <td>${App.escapeHTML(t.code)}</td>
                    <td class="${dirClass}">${dir}</td>
                    <td>¥${(t.price || 0).toFixed(2)}</td>
                    <td>${t.volume || 0}</td>
                    <td>${t.equity != null ? App.fmt(t.equity) : '--'}</td>
                </tr>`;
            }).join('');
        } catch (e) {
            // silent
        }
    },

    async loadEquityCurve() {
        try {
            const data = await App.fetchJSON('/api/paper/equity-curve');
            if (!data.curve || data.curve.length < 2) return;

            const canvas = document.getElementById('pp-equity-chart');
            if (!canvas) return;

            const labels = data.curve.map((p, i) => i + 1);
            const values = data.curve.map(p => p.equity);

            if (this._equityChart) {
                this._equityChart.data.labels = labels;
                this._equityChart.data.datasets[0].data = values;
                this._equityChart.update('none');
                return;
            }

            this._equityChart = new Chart(canvas, {
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
        } catch (e) {
            // silent
        }
    },

    _clearTrades() {
        const tbody = document.querySelector('#pp-trades-table tbody');
        if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="text-muted" style="text-align:center">暂无交易记录</td></tr>';
    },

    _clearEquityChart() {
        if (this._equityChart) {
            this._equityChart.destroy();
            this._equityChart = null;
        }
    },

    _startPolling() {
        this._stopPolling();
        PollManager.register('paperStatus', () => this.loadStatus(), 5000);
    },

    _stopPolling() {
        PollManager.cancel('paperStatus');
    },
};
