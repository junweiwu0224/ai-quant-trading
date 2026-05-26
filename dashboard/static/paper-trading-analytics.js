/* ── 模拟盘：趋势 / 频率 / 持仓图表 ── */

if (!globalThis.PaperTrading) {
    globalThis.PaperTrading = {};
}

Object.assign(globalThis.PaperTrading, {
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
        if (!canvas) return;
        if (daily.length < 2) {
            this._showChartEmpty(canvas, '运行模拟盘后生成绩效趋势');
            return;
        }
        this._hideChartEmpty(canvas);

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

        this.charts.perfTrend = ChartFactory.create('pt-perf-trend-chart', {
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
        }, 'pt-perf-trend');
    },

    async loadTradeFrequency() {
        try {
            let trades = this.state.trades;
            if (!trades || trades.length === 0) {
                const data = await App.fetchJSON('/api/paper/trades-v2?page=1&page_size=500');
                trades = data.data?.items || [];
            }
            this.renderTradeFrequency(trades);
        } catch (e) {
            console.error('加载交易频率失败:', e);
        }
    },

    renderTradeFrequency(trades) {
        const canvas = document.getElementById('pt-frequency-chart');
        if (!canvas) return;

        if (!trades || trades.length === 0) {
            this._showChartEmpty(canvas, '暂无交易记录');
            return;
        }
        this._hideChartEmpty(canvas);

        const weekdayNames = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
        const weekdayCounts = [0, 0, 0, 0, 0, 0, 0];
        trades.forEach(t => {
            if (t.created_at) {
                const d = new Date(t.created_at);
                weekdayCounts[d.getDay()]++;
            }
        });

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

        this.charts.frequency = ChartFactory.create('pt-frequency-chart', {
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
        }, 'pt-frequency');
    },

    renderPositionPie() {
        const canvas = document.getElementById('pt-position-pie');
        if (!canvas) return;

        const positions = this.state.positions;
        if (positions.length === 0) {
            if (this.charts.positionPie) { this.charts.positionPie.destroy(); this.charts.positionPie = null; }
            this._showChartEmpty(canvas, '暂无持仓');
            return;
        }
        this._hideChartEmpty(canvas);

        const labels = positions.map(p => {
            const name = this._stockNameCache[p.code];
            return name ? `${p.code} ${name}` : p.code;
        });
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

        this.charts.positionPie = ChartFactory.create('pt-position-pie', {
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
        }, 'pt-position');
    },
});
