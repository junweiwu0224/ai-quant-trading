/* ── 回测模块 ── */

Object.assign(App, {
    bindBacktest() {
        const form = document.getElementById('backtest-form');
        if (!form) return;

        // 动态加载策略列表
        this._loadStrategies();
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const codes = this.btMultiSearch
                ? this.btMultiSearch.getSelectedCodes()
                : [document.getElementById('bt-code').value.trim()].filter(Boolean);
            const startDate = document.getElementById('bt-start').value;
            const endDate = document.getElementById('bt-end').value;
            const cash = parseFloat(document.getElementById('bt-cash').value);

            if (codes.length === 0) { this.toast('请至少选择一只股票', 'error'); return; }
            if (startDate > endDate) { this.toast('开始日期不能晚于结束日期', 'error'); return; }
            if (cash <= 0) { this.toast('初始资金必须大于 0', 'error'); return; }

            const btn = document.getElementById('bt-run-btn');
            btn.disabled = true;
            btn.innerHTML = '<span class="skeleton-pulse" style="display:inline-block;width:1em;height:1em;border-radius:50%;vertical-align:middle;margin-right:4px"></span>运行中...';
            // 显示取消按钮
            let cancelBtn = document.getElementById('bt-cancel-btn');
            if (!cancelBtn) {
                cancelBtn = document.createElement('button');
                cancelBtn.id = 'bt-cancel-btn';
                cancelBtn.className = 'btn btn-sm btn-danger';
                cancelBtn.textContent = '取消回测';
                cancelBtn.style.marginLeft = '8px';
                btn.parentElement.appendChild(cancelBtn);
            }
            cancelBtn.style.display = '';
            cancelBtn.disabled = false;
            document.getElementById('bt-results').style.display = 'none';
            this._showProgress(0, '');

            const body = {
                strategy: document.getElementById('bt-strategy').value,
                codes: codes,
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
                    // 取消按钮事件
                    cancelBtn.onclick = () => {
                        try { ws.send(JSON.stringify({ type: 'cancel' })); } catch (e) { /* ignore */ }
                        cancelBtn.disabled = true;
                        cancelBtn.textContent = '取消中...';
                    };
                    ws.onmessage = (evt) => {
                        const msg = JSON.parse(evt.data);
                        if (msg.type === 'progress') {
                            this._showProgress(msg.progress, msg.current_date, msg.elapsed, msg.remaining);
                        } else if (msg.type === 'complete') {
                            resolve(msg.data);
                        } else if (msg.type === 'cancelled') {
                            reject(new Error('cancelled'));
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
                if (err.message === 'cancelled') {
                    this.toast('回测已取消', 'info');
                } else {
                    this.toast('回测失败: ' + err.message, 'error');
                }
            } finally {
                btn.disabled = false;
                btn.textContent = '运行回测';
                const cancelBtn = document.getElementById('bt-cancel-btn');
                if (cancelBtn) cancelBtn.style.display = 'none';
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

    showBacktestResults(data, reqBody) {
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

        this._lastBacktestData = data;
        this._lastBacktestBody = reqBody;

        const curve = data.equity_curve || [];
        const benchmarkCurve = data.benchmark_curve || [];
        if (curve.length > 0) {
            const datasets = [{ data: curve.map(p => p.equity), fill: true, label: '策略收益' }];
            if (benchmarkCurve.length > 0) {
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
                App.fetchJSON('/api/backtest/monthly-returns', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(reqBody), label: '月度收益', silent: true }),
                App.fetchJSON('/api/backtest/drawdown', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(reqBody), label: '回撤数据', silent: true }),
            ]);
            this.renderMonthlyHeatmap(monthly);
            this.renderDrawdown(drawdown);
        } catch (e) {
            this.toast('月度收益/回撤数据加载失败', 'error');
        }
        this._loadAnalysis(reqBody);
        this._bindAnalysisTabs();
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

    _bindAnalysisTabs() {
        document.querySelectorAll('.analysis-tab').forEach(tab => {
            tab.onclick = () => {
                document.querySelectorAll('.analysis-tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.analysis-panel').forEach(p => p.classList.remove('active'));
                tab.classList.add('active');
                const panel = document.getElementById('bt-panel-' + tab.dataset.panel);
                if (panel) panel.classList.add('active');
            };
        });
    },

    async _loadAnalysis(reqBody) {
        const post = (url) => App.fetchJSON(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(reqBody),
            silent: true,
        });

        const [returnsData, tradesData, weekdayData, turnoverData, holdingData, attributionData] = await Promise.all([
            post('/api/backtest/analysis/returns').catch(() => null),
            post('/api/backtest/analysis/trades').catch(() => null),
            post('/api/backtest/analysis/weekday').catch(() => null),
            post('/api/backtest/analysis/turnover').catch(() => null),
            post('/api/backtest/analysis/holding-period').catch(() => null),
            post('/api/backtest/analysis/attribution').catch(() => null),
        ]);

        if (returnsData && !returnsData.error) this._renderReturnDist(returnsData);
        if (tradesData && !tradesData.error) this._renderTradeAnalysis(tradesData);
        if (weekdayData && !weekdayData.error) this._renderWeekday(weekdayData);
        if (turnoverData && !turnoverData.error) this._renderTurnover(turnoverData);
        if (holdingData && !holdingData.error) this._renderHoldingPeriod(holdingData);
        if (attributionData && !attributionData.error) this._renderAttribution(attributionData);
    },

    _renderReturnDist(data) {
        const h = data.histogram;
        const s = data.stats;
        const statsEl = document.getElementById('bt-return-stats');
        if (statsEl) {
            statsEl.innerHTML = [
                `<span class="as-item"><span class="as-label">均值:</span><span class="as-value">${s.mean}%</span></span>`,
                `<span class="as-item"><span class="as-label">标准差:</span><span class="as-value">${s.std}%</span></span>`,
                `<span class="as-item"><span class="as-label">偏度:</span><span class="as-value">${s.skewness}</span></span>`,
                `<span class="as-item"><span class="as-label">峰度:</span><span class="as-value">${s.kurtosis}</span></span>`,
                `<span class="as-item"><span class="as-label">上涨天数:</span><span class="as-value text-danger">${s.positive_days}</span></span>`,
                `<span class="as-item"><span class="as-label">下跌天数:</span><span class="as-value text-success">${s.negative_days}</span></span>`,
            ].join('');
        }
        if (h && h.bins.length > 0) {
            const colors = h.bins.map(b => b >= 0 ? 'rgba(239,83,80,0.7)' : 'rgba(16,185,129,0.7)');
            ChartFactory.bar('bt-return-dist-chart', {
                labels: h.bins.map(b => b.toFixed(1) + '%'),
                values: h.counts,
                colors,
            }, 'returnDist', {
                plugins: { legend: { display: false } },
                scales: { x: { ticks: { maxTicksLimit: 10 } } },
            });
        }
    },

    _renderTradeAnalysis(data) {
        const s = data.stats;
        const statsEl = document.getElementById('bt-trade-stats');
        if (statsEl && s) {
            statsEl.innerHTML = [
                `<span class="as-item"><span class="as-label">总交易:</span><span class="as-value">${s.total_trades}</span></span>`,
                `<span class="as-item"><span class="as-label">盈利:</span><span class="as-value text-danger">${s.win_count}</span></span>`,
                `<span class="as-item"><span class="as-label">亏损:</span><span class="as-value text-success">${s.loss_count}</span></span>`,
                `<span class="as-item"><span class="as-label">平均盈利:</span><span class="as-value text-danger">+${s.avg_win}%</span></span>`,
                `<span class="as-item"><span class="as-label">平均亏损:</span><span class="as-value text-success">${s.avg_loss}%</span></span>`,
                `<span class="as-item"><span class="as-label">最大单笔盈利:</span><span class="as-value text-danger">+${s.max_win}%</span></span>`,
                `<span class="as-item"><span class="as-label">最大单笔亏损:</span><span class="as-value text-success">${s.max_loss}%</span></span>`,
                `<span class="as-item"><span class="as-label">最大连胜:</span><span class="as-value">${s.max_consecutive_wins}</span></span>`,
                `<span class="as-item"><span class="as-label">最大连亏:</span><span class="as-value">${s.max_consecutive_losses}</span></span>`,
            ].join('');
        }
        const pd = data.pnl_distribution;
        if (pd && pd.bins.length > 0) {
            const colors = pd.bins.map(b => b >= 0 ? 'rgba(239,83,80,0.7)' : 'rgba(16,185,129,0.7)');
            ChartFactory.bar('bt-trade-pnl-chart', {
                labels: pd.bins.map(b => b.toFixed(1) + '%'),
                values: pd.counts,
                colors,
            }, 'tradePnl', {
                plugins: { legend: { display: false } },
            });
        }
    },

    _renderWeekday(data) {
        if (!data || !data.labels) return;
        const colors = data.avg_returns.map(v => v >= 0 ? 'rgba(239,83,80,0.7)' : 'rgba(16,185,129,0.7)');
        ChartFactory.bar('bt-weekday-chart', {
            labels: data.labels,
            values: data.avg_returns,
            colors,
        }, 'weekday', {
            plugins: { legend: { display: false } },
            scales: { y: { ticks: { callback: v => v.toFixed(3) + '%' } } },
        });
    },

    _renderTurnover(data) {
        const s = data.summary;
        const statsEl = document.getElementById('bt-turnover-stats');
        if (statsEl && s) {
            const c = data.cost_breakdown;
            statsEl.innerHTML = [
                `<span class="as-item"><span class="as-label">日均换手率:</span><span class="as-value">${(s.avg_daily_turnover * 100).toFixed(3)}%</span></span>`,
                `<span class="as-item"><span class="as-label">总买入:</span><span class="as-value">${this._formatMoney(s.total_buy_amount)}</span></span>`,
                `<span class="as-item"><span class="as-label">总卖出:</span><span class="as-value">${this._formatMoney(s.total_sell_amount)}</span></span>`,
                `<span class="as-item"><span class="as-label">交易天数:</span><span class="as-value">${s.trading_days}</span></span>`,
                `<span class="as-item"><span class="as-label">佣金:</span><span class="as-value">${this._formatMoney(c.commission)}</span></span>`,
                `<span class="as-item"><span class="as-label">印花税:</span><span class="as-value">${this._formatMoney(c.stamp_tax)}</span></span>`,
                `<span class="as-item"><span class="as-label">滑点成本:</span><span class="as-value">${this._formatMoney(c.slippage)}</span></span>`,
                `<span class="as-item"><span class="as-label">总成本:</span><span class="as-value text-danger">${this._formatMoney(c.total)}</span></span>`,
                `<span class="as-item"><span class="as-label">成本拖累:</span><span class="as-value text-danger">${(s.cost_drag * 100).toFixed(2)}%</span></span>`,
            ].join('');
        }
        const series = data.turnover_series;
        if (series && series.length > 0) {
            ChartFactory.bar('bt-turnover-chart', {
                labels: series.map(d => d.date),
                values: series.map(d => d.turnover_rate * 100),
                colors: series.map(() => 'rgba(99,102,241,0.7)'),
            }, 'turnover', {
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { maxTicksLimit: 10 } },
                    y: { ticks: { callback: v => v.toFixed(2) + '%' } },
                },
            });
        }
    },

    _formatMoney(v) {
        if (v == null) return '--';
        if (v >= 10000) return (v / 10000).toFixed(2) + '万';
        return v.toFixed(2);
    },

    _renderHoldingPeriod(data) {
        const s = data.summary;
        const statsEl = document.getElementById('bt-holding-stats');
        if (statsEl && s) {
            statsEl.innerHTML = [
                `<span class="as-item"><span class="as-label">完整交易轮次:</span><span class="as-value">${s.total_round_trips}</span></span>`,
                `<span class="as-item"><span class="as-label">平均持仓天数:</span><span class="as-value">${s.avg_holding_days}</span></span>`,
                `<span class="as-item"><span class="as-label">中位数天数:</span><span class="as-value">${s.median_holding_days}</span></span>`,
                `<span class="as-item"><span class="as-label">最长持仓:</span><span class="as-value">${s.max_holding_days}天</span></span>`,
                `<span class="as-item"><span class="as-label">最短持仓:</span><span class="as-value">${s.min_holding_days}天</span></span>`,
                `<span class="as-item"><span class="as-label">盈利平均天数:</span><span class="as-value text-danger">${s.avg_win_days}天</span></span>`,
                `<span class="as-item"><span class="as-label">亏损平均天数:</span><span class="as-value text-success">${s.avg_loss_days}天</span></span>`,
            ].join('');
        }
        const dist = data.distribution;
        if (dist && dist.labels.length > 0) {
            ChartFactory.bar('bt-holding-dist-chart', {
                labels: dist.labels,
                values: dist.counts,
                colors: dist.counts.map(() => 'rgba(99,102,241,0.7)'),
            }, 'holdingDist', {
                plugins: { legend: { display: false } },
            });
        }
        const pnl = data.pnl_by_period;
        if (pnl && pnl.length > 0) {
            const colors = pnl.map(p => p.avg_pnl >= 0 ? 'rgba(239,83,80,0.7)' : 'rgba(16,185,129,0.7)');
            ChartFactory.bar('bt-holding-pnl-chart', {
                labels: pnl.map(p => p.period),
                values: pnl.map(p => p.avg_pnl),
                colors,
            }, 'holdingPnl', {
                plugins: { legend: { display: false } },
                scales: { y: { ticks: { callback: v => v.toFixed(1) + '%' } } },
            });
        }
    },

    _renderAttribution(data) {
        const s = data.summary;
        const statsEl = document.getElementById('bt-attribution-stats');
        if (statsEl && s) {
            const color = v => v >= 0 ? 'text-danger' : 'text-success';
            statsEl.innerHTML = [
                `<span class="as-item"><span class="as-label">配置效应:</span><span class="as-value ${color(s.total_allocation)}">${s.total_allocation > 0 ? '+' : ''}${s.total_allocation}%</span></span>`,
                `<span class="as-item"><span class="as-label">选择效应:</span><span class="as-value ${color(s.total_selection)}">${s.total_selection > 0 ? '+' : ''}${s.total_selection}%</span></span>`,
                `<span class="as-item"><span class="as-label">交互效应:</span><span class="as-value ${color(s.total_interaction)}">${s.total_interaction > 0 ? '+' : ''}${s.total_interaction}%</span></span>`,
                `<span class="as-item"><span class="as-label">超额收益:</span><span class="as-value ${color(s.total_excess_return)}">${s.total_excess_return > 0 ? '+' : ''}${s.total_excess_return}%</span></span>`,
            ].join('');
        }
        const tbody = document.querySelector('#bt-attribution-table tbody');
        if (tbody && data.sectors) {
            const fmt = v => (v > 0 ? '+' : '') + v.toFixed(2) + '%';
            tbody.innerHTML = data.sectors.map(s => `
                <tr>
                    <td>${this.escapeHTML(s.sector)}</td>
                    <td>${(s.portfolio_weight * 100).toFixed(1)}%</td>
                    <td>${(s.benchmark_weight * 100).toFixed(1)}%</td>
                    <td>${s.portfolio_return}%</td>
                    <td>${s.benchmark_return}%</td>
                    <td class="${s.allocation_effect >= 0 ? 'text-danger' : 'text-success'}">${fmt(s.allocation_effect)}</td>
                    <td class="${s.selection_effect >= 0 ? 'text-danger' : 'text-success'}">${fmt(s.selection_effect)}</td>
                    <td class="${s.interaction_effect >= 0 ? 'text-danger' : 'text-success'}">${fmt(s.interaction_effect)}</td>
                    <td class="${s.total_effect >= 0 ? 'text-danger' : 'text-success'}">${fmt(s.total_effect)}</td>
                </tr>
            `).join('');
        }
    },

    async compareStrategies() {
        const strategies = [...document.querySelectorAll('#bt-compare-section input:checked')].map(el => el.value);
        if (strategies.length === 0) return;
        const codes = this.btMultiSearch
            ? this.btMultiSearch.getSelectedCodes()
            : [document.getElementById('bt-code').value.trim()].filter(Boolean);
        if (codes.length === 0) return;

        const body = {
            strategies, codes: codes,
            start_date: document.getElementById('bt-start').value,
            end_date: document.getElementById('bt-end').value,
            initial_cash: parseFloat(document.getElementById('bt-cash').value),
        };

        try {
            const results = await App.fetchJSON('/api/backtest/compare', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
                label: '策略对比',
            });
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

    async _loadStrategies() {
        const select = document.getElementById('bt-strategy');
        if (!select) return;

        try {
            const strategies = await this.fetchJSON('/api/backtest/strategies');
            select.innerHTML = strategies.map(s =>
                `<option value="${this.escapeHTML(s.name)}">${this.escapeHTML(s.label)}</option>`
            ).join('');
        } catch (e) {
            console.error('加载策略列表失败:', e);
            select.innerHTML = '<option value="dual_ma">双均线策略</option>';
        }
    },
});
