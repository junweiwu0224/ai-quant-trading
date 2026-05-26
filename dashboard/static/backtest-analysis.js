/* ── 回测模块：图表与深度分析 ── */

Object.assign(App, {
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
});