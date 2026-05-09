/* ── 优化 + 敏感性分析 + 蒙特卡洛模块 ── */

Object.assign(App, {
    bindOptimize() {
        const form = document.getElementById('bt-optimize-form');
        if (!form) return;
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const codes = this.btMultiSearch
                ? this.btMultiSearch.getSelectedCodes()
                : [document.getElementById('bt-code').value.trim()].filter(Boolean);
            if (codes.length === 0) { this.toast('请先选择股票代码', 'error'); return; }

            const btn = document.getElementById('opt-run-btn');
            btn.disabled = true;
            btn.textContent = '优化中...';
            document.getElementById('opt-result').style.display = 'none';
            const progWrap = document.getElementById('opt-progress-wrap');
            if (progWrap) progWrap.style.display = '';

            const body = {
                strategy: document.getElementById('bt-strategy').value,
                codes: codes,
                start_date: document.getElementById('bt-start').value,
                end_date: document.getElementById('bt-end').value,
                initial_cash: parseFloat(document.getElementById('bt-cash').value) || 100000,
                commission_rate: parseFloat(document.getElementById('bt-commission').value) || 0.0003,
                stamp_tax_rate: parseFloat(document.getElementById('bt-stamp-tax').value) || 0.001,
                slippage: parseFloat(document.getElementById('bt-slippage').value) || 0.002,
                metric: document.getElementById('opt-metric').value,
                method: document.getElementById('opt-method').value,
                n_trials: parseInt(document.getElementById('opt-trials').value) || 50,
            };

            try {
                const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
                const ws = new WebSocket(`${proto}//${location.host}/api/optimization/ws/run`);
                const result = await new Promise((resolve, reject) => {
                    ws.onopen = () => ws.send(JSON.stringify(body));
                    ws.onmessage = (evt) => {
                        const msg = JSON.parse(evt.data);
                        if (msg.type === 'progress') {
                            const fill = document.getElementById('opt-progress-fill');
                            const text = document.getElementById('opt-progress-text');
                            if (fill) fill.style.width = (msg.progress * 100).toFixed(1) + '%';
                            if (text) text.textContent = (msg.progress * 100).toFixed(1) + '%';
                        } else if (msg.type === 'complete') {
                            resolve(msg.data);
                        } else if (msg.type === 'error') {
                            reject(new Error(msg.message));
                        }
                    };
                    ws.onerror = () => reject(new Error('连接失败'));
                    setTimeout(() => { ws.close(); reject(new Error('超时')); }, 600000);
                });
                this._showOptResult(result);
                this.toast(`优化完成，最优${result.metric_name}: ${result.best_metric}`, 'success');
            } catch (err) {
                this.toast('优化失败: ' + err.message, 'error');
            } finally {
                btn.disabled = false;
                btn.textContent = '开始优化';
                if (progWrap) progWrap.style.display = 'none';
            }
        });
    },

    _showOptResult(data) {
        document.getElementById('opt-result').style.display = '';
        const statsEl = document.getElementById('opt-best-stats');
        if (statsEl) {
            const bp = data.best_params;
            const paramStr = Object.entries(bp).map(([k, v]) => `${k}=${v}`).join(', ');
            statsEl.innerHTML = [
                `<span class="as-item"><span class="as-label">最优参数:</span><span class="as-value">${paramStr}</span></span>`,
                `<span class="as-item"><span class="as-label">${data.metric_name}:</span><span class="as-value">${data.best_metric}</span></span>`,
                `<span class="as-item"><span class="as-label">试验次数:</span><span class="as-value">${data.total_trials}</span></span>`,
                `<span class="as-item"><span class="as-label">耗时:</span><span class="as-value">${data.elapsed_seconds}s</span></span>`,
            ].join('');
        }
        const tbody = document.querySelector('#opt-results-table tbody');
        if (tbody && data.results) {
            tbody.innerHTML = data.results.slice(0, 20).map((r, i) => {
                const p = r.params || {};
                const paramStr = Object.entries(p).map(([k, v]) => `${this.escapeHTML(k)}=${typeof v === 'number' ? (Number.isInteger(v) ? v : v.toFixed(2)) : this.escapeHTML(v)}`).join(', ');
                return `<tr>
                    <td>${i + 1}</td><td>${paramStr}</td>
                    <td>${r.metric}</td><td>${(r.total_return * 100).toFixed(2)}%</td>
                    <td>${(r.max_drawdown * 100).toFixed(2)}%</td><td>${r.sharpe_ratio}</td>
                    <td>${(r.win_rate * 100).toFixed(1)}%</td><td>${r.total_trades}</td>
                </tr>`;
            }).join('');
        }
    },

    bindSensitivity() {
        const form = document.getElementById('bt-sensitivity-form');
        if (!form) return;
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const codes = this.btMultiSearch
                ? this.btMultiSearch.getSelectedCodes()
                : [document.getElementById('bt-code').value.trim()].filter(Boolean);
            if (codes.length === 0) { this.toast('请先选择股票代码', 'error'); return; }

            const btn = document.getElementById('sens-run-btn');
            btn.disabled = true;
            btn.textContent = '分析中...';
            document.getElementById('sens-result').style.display = 'none';
            const progWrap = document.getElementById('sens-progress-wrap');
            if (progWrap) progWrap.style.display = '';

            const body = {
                strategy: document.getElementById('bt-strategy').value,
                codes: codes,
                start_date: document.getElementById('bt-start').value,
                end_date: document.getElementById('bt-end').value,
                initial_cash: parseFloat(document.getElementById('bt-cash').value) || 100000,
                commission_rate: parseFloat(document.getElementById('bt-commission').value) || 0.0003,
                stamp_tax_rate: parseFloat(document.getElementById('bt-stamp-tax').value) || 0.001,
                slippage: parseFloat(document.getElementById('bt-slippage').value) || 0.002,
                metric: document.getElementById('sens-metric').value,
                param_x: document.getElementById('sens-param-x').value,
                param_y: document.getElementById('sens-param-y').value,
            };

            try {
                const data = await App.fetchJSON('/api/optimization/sensitivity', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                    label: '敏感性分析',
                });
                if (data.error) throw new Error(data.error);
                this._showSensResult(data);
                this.toast(`敏感性分析完成，最优${data.metric_name}: ${data.best_metric}`, 'success');
            } catch (err) {
                this.toast('分析失败: ' + err.message, 'error');
            } finally {
                btn.disabled = false;
                btn.textContent = '开始分析';
                if (progWrap) progWrap.style.display = 'none';
            }
        });
    },

    _showSensResult(data) {
        document.getElementById('sens-result').style.display = '';
        const statsEl = document.getElementById('sens-stats');
        if (statsEl) {
            const bp = data.best_params;
            const paramStr = Object.entries(bp).map(([k, v]) => `${k}=${v}`).join(', ');
            statsEl.innerHTML = [
                `<span class="as-item"><span class="as-label">最优参数:</span><span class="as-value">${paramStr}</span></span>`,
                `<span class="as-item"><span class="as-label">${data.metric_name}:</span><span class="as-value">${data.best_metric}</span></span>`,
                `<span class="as-item"><span class="as-label">试验次数:</span><span class="as-value">${data.total_trials}</span></span>`,
                `<span class="as-item"><span class="as-label">耗时:</span><span class="as-value">${data.elapsed_seconds}s</span></span>`,
            ].join('');
        }

        const canvas = document.getElementById('sens-chart');
        if (!canvas) return;
        if (this._sensChart) this._sensChart.destroy();

        const xs = data.x_values;
        const ys = data.y_values;
        const grid = data.grid;

        const heatData = [];
        let minVal = Infinity, maxVal = -Infinity;
        for (const cell of grid) {
            const xi = xs.indexOf(cell.x);
            const yi = ys.indexOf(cell.y);
            if (xi >= 0 && yi >= 0) {
                heatData.push({ x: xi, y: yi, v: cell.metric });
                if (cell.metric < minVal) minVal = cell.metric;
                if (cell.metric > maxVal) maxVal = cell.metric;
            }
        }

        const datasets = [{
            label: data.metric_name,
            data: heatData.map(d => ({ x: d.x, y: d.y, r: 18 })),
            backgroundColor: heatData.map(d => {
                const t = maxVal > minVal ? (d.v - minVal) / (maxVal - minVal) : 0.5;
                const r = Math.round(50 + t * 205);
                const g = Math.round(100 - t * 80);
                const b = Math.round(255 - t * 205);
                return `rgba(${r},${g},${b},0.85)`;
            }),
        }];

        this._sensChart = new Chart(canvas, {
            type: 'bubble',
            data: { datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        type: 'linear',
                        min: -0.5,
                        max: xs.length - 0.5,
                        ticks: {
                            stepSize: 1,
                            callback: (val) => xs[val] !== undefined ? xs[val] : '',
                        },
                        title: { display: true, text: data.param_x },
                    },
                    y: {
                        type: 'linear',
                        min: -0.5,
                        max: ys.length - 0.5,
                        ticks: {
                            stepSize: 1,
                            callback: (val) => ys[val] !== undefined ? ys[val] : '',
                        },
                        title: { display: true, text: data.param_y },
                    },
                },
                plugins: {
                    tooltip: {
                        callbacks: {
                            label: (ctx) => {
                                const d = heatData[ctx.dataIndex];
                                return `${data.param_x}=${xs[d.x]}, ${data.param_y}=${ys[d.y]}, ${data.metric_name}=${d.v.toFixed(4)}`;
                            },
                        },
                    },
                    legend: { display: false },
                },
            },
        });
    },

    async runMonteCarlo() {
        const data = this._lastBacktestData;
        if (!data || !data.trades || data.trades.length < 5) {
            this.toast('请先运行回测（至少5笔交易）', 'error');
            return;
        }

        const btn = document.getElementById('mc-run-btn');
        if (btn) {
            btn.disabled = true;
            btn.textContent = '模拟中...';
        }

        try {
            // 调用后端蒙特卡洛 API
            const reqBody = this._lastBacktestBody || {};
            const result = await this.fetchJSON('/api/backtest/monte-carlo', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ...reqBody,
                    simulations: 1000,
                }),
            });

            if (result.error) {
                this.toast('蒙特卡洛模拟失败: ' + result.error, 'error');
                return;
            }

            document.getElementById('mc-result').style.display = '';
            const statsEl = document.getElementById('mc-stats');
            if (statsEl) {
                const p = result.percentiles;
                statsEl.innerHTML = [
                    `<span class="as-item"><span class="as-label">模拟次数:</span><span class="as-value">${result.simulations}</span></span>`,
                    `<span class="as-item"><span class="as-label">平均收益:</span><span class="as-value">${result.mean.toFixed(2)}%</span></span>`,
                    `<span class="as-item"><span class="as-label">5%分位:</span><span class="as-value text-success">${p.p5.toFixed(2)}%</span></span>`,
                    `<span class="as-item"><span class="as-label">中位数:</span><span class="as-value">${p.p50.toFixed(2)}%</span></span>`,
                    `<span class="as-item"><span class="as-label">95%分位:</span><span class="as-value text-danger">${p.p95.toFixed(2)}%</span></span>`,
                    `<span class="as-item"><span class="as-label">破产概率(亏50%+):</span><span class="as-value">${result.ruin_prob.toFixed(1)}%</span></span>`,
                ].join('');
            }

            const hist = result.histogram;
            if (hist && hist.bins.length > 0) {
                const colors = hist.bins.map(b => parseFloat(b) >= 0 ? 'rgba(239,83,80,0.6)' : 'rgba(16,185,129,0.6)');
                ChartFactory.bar('mc-chart', { labels: hist.bins, values: hist.counts, colors }, 'monteCarlo', {
                    plugins: { legend: { display: false } },
                });
            }

            this.toast('蒙特卡洛模拟完成', 'success');
        } catch (e) {
            this.toast('蒙特卡洛模拟失败: ' + e.message, 'error');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = '运行蒙特卡洛';
            }
        }
    },
});
