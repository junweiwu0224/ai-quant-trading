/* ── 模拟盘：绩效分析与图表 ── */

if (!globalThis.PaperTrading) {
    globalThis.PaperTrading = {};
}

Object.assign(globalThis.PaperTrading, {
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
        const isFiniteNumber = (v) => typeof v === 'number' && Number.isFinite(v);
        const fmt = (v, decimals = 2, limit = 1000) => (
            isFiniteNumber(v) && v !== 0 && Math.abs(v) <= limit ? v.toFixed(decimals) : '--'
        );
        const fmtPct = (v) => (
            isFiniteNumber(v) && v !== 0 && Math.abs(v) <= 100 ? (v * 100).toFixed(2) + '%' : '--'
        );
        const fmtYen = (v) => isFiniteNumber(v) && v !== 0 ? '¥' + v.toFixed(2) : '--';

        const elements = {
            'pt-total-equity': perf.total_equity ? App.fmt(perf.total_equity) : '--',
            'pt-daily-return': fmtPct(perf.daily_return),
            'pt-cumulative-return': fmtPct(perf.cumulative_return),
            'pt-max-drawdown': fmtPct(perf.max_drawdown),
            'pt-sharpe-ratio': fmt(perf.sharpe_ratio, 4),
            'pt-sortino-ratio': fmt(perf.sortino_ratio, 4),
            'pt-calmar-ratio': fmt(perf.calmar_ratio, 4),
            'pt-win-rate': fmtPct(perf.win_rate),
            'pt-win-rate-perf': fmtPct(perf.win_rate),
            'pt-profit-loss-ratio': fmt(perf.profit_loss_ratio, 4),
            'pt-total-trades': perf.total_trades ?? '--',
            'pt-winning-trades': perf.winning_trades ?? '--',
            'pt-losing-trades': perf.losing_trades ?? '--',
            'pt-avg-win': fmtYen(perf.avg_win),
            'pt-avg-loss': fmtYen(perf.avg_loss),
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
        const cs = getComputedStyle(document.documentElement);
        const upRgb = this._hexToRgb(cs.getPropertyValue('--up-color').trim() || '#c65746');
        const downRgb = this._hexToRgb(cs.getPropertyValue('--down-color').trim() || '#10b981');
        if (value > 0.1) return `rgba(${upRgb}, 0.8)`;
        if (value > 0.05) return `rgba(${upRgb}, 0.6)`;
        if (value > 0) return `rgba(${upRgb}, 0.4)`;
        if (value > -0.05) return `rgba(${downRgb}, 0.4)`;
        if (value > -0.1) return `rgba(${downRgb}, 0.6)`;
        return `rgba(${downRgb}, 0.8)`;
    },

    _hexToRgb(hex) {
        hex = hex.replace('#', '');
        if (hex.length === 3) hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2];
        const r = parseInt(hex.substring(0, 2), 16);
        const g = parseInt(hex.substring(2, 4), 16);
        const b = parseInt(hex.substring(4, 6), 16);
        return `${r}, ${g}, ${b}`;
    },

    async loadDailyReturns() {
        try {
            const data = await App.fetchJSON('/api/paper/equity-curve-v2');
            this.renderDailyReturns(data.data || []);
        } catch (e) {
            console.error('加载每日收益失败:', e);
        }
    },

    renderDailyReturns(points) {
        const canvas = document.getElementById('pt-daily-returns-chart');
        if (!canvas) return;

        const dayMap = {};
        points.forEach(p => {
            const day = (p.timestamp || '').slice(0, 10);
            if (day) dayMap[day] = p.equity;
        });
        const days = Object.keys(dayMap).sort();
        if (days.length < 2) {
            this._showChartEmpty(canvas, '至少需要2天数据');
            return;
        }
        this._hideChartEmpty(canvas);

        const returns = [];
        const labels = [];
        for (let i = 1; i < days.length; i++) {
            const prev = dayMap[days[i - 1]];
            const curr = dayMap[days[i]];
            if (prev > 0) {
                returns.push(((curr - prev) / prev * 100));
                labels.push(days[i].slice(5));
            }
        }

        const cs = getComputedStyle(document.documentElement);
        const upColor = cs.getPropertyValue('--up-color').trim() || '#c65746';
        const downColor = cs.getPropertyValue('--down-color').trim() || '#10b981';
        const colors = returns.map(r => r >= 0 ? upColor : downColor);

        if (this.charts.dailyReturns) {
            this.charts.dailyReturns.data.labels = labels;
            this.charts.dailyReturns.data.datasets[0].data = returns;
            this.charts.dailyReturns.data.datasets[0].backgroundColor = colors;
            this.charts.dailyReturns.update('none');
            return;
        }

        this.charts.dailyReturns = ChartFactory.create('pt-daily-returns-chart', {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    data: returns,
                    backgroundColor: colors,
                    borderRadius: 3,
                    borderSkipped: false,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => `${ctx.parsed.y >= 0 ? '+' : ''}${ctx.parsed.y.toFixed(2)}%`,
                        },
                    },
                },
                scales: {
                    x: { grid: { display: false } },
                    y: {
                        ticks: { callback: v => v.toFixed(1) + '%' },
                        grid: { color: 'rgba(128,128,128,0.1)' },
                    },
                },
            },
        }, 'pt-daily-returns');
    },

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

        const { edges = [], bins: binsRaw = [], counts = [] } = distribution;
        const binEdges = edges.length > 0 ? edges : binsRaw;
        if (binEdges.length === 0 || counts.length === 0) {
            this._showChartEmpty(canvas, '暂无收益分布数据');
            return;
        }
        this._hideChartEmpty(canvas);

        const labels = binEdges.map(b => (b * 100).toFixed(1) + '%');
        const colors = binEdges.map(b => b >= 0 ? 'rgba(198, 87, 70, 0.7)' : 'rgba(16, 185, 129, 0.7)');

        if (this.charts.returnDist) {
            this.charts.returnDist.data.labels = labels;
            this.charts.returnDist.data.datasets[0].data = counts;
            this.charts.returnDist.data.datasets[0].backgroundColor = colors;
            this.charts.returnDist.update('none');
            return;
        }

        this.charts.returnDist = ChartFactory.create('pt-return-dist-chart', {
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
        }, 'pt-return-dist');
    },

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

        if (!effect || Object.keys(effect).length === 0) {
            this._showChartEmpty(canvas, '暂无星期效应数据');
            return;
        }
        this._hideChartEmpty(canvas);
        const colors = values.map(v => v >= 0 ? 'rgba(198, 87, 70, 0.7)' : 'rgba(16, 185, 129, 0.7)');

        if (this.charts.weekdayEffect) {
            this.charts.weekdayEffect.data.datasets[0].data = values;
            this.charts.weekdayEffect.data.datasets[0].backgroundColor = colors;
            this.charts.weekdayEffect.update('none');
            return;
        }

        this.charts.weekdayEffect = ChartFactory.create('pt-weekday-chart', {
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
        }, 'pt-weekday');
    },

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

        const bmValues = this._normalizeBenchmark(curve, this._benchmarkCurve);
        if (bmValues.length > 0) {
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

        this.charts.equityCurve = ChartFactory.create('pt-equity-chart', {
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
        }, 'pt-equity');
    },

});
