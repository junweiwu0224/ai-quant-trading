/* ── 持仓模块：图表渲染 ── */

Object.assign(App, {
    _pfRenderEquityCurve() {
        const history = this._pf.equityHistory || [];
        if (history.length < 2) { ChartFactory.showEmpty('pf-equity-curve'); return; }

        const range = this._pf.equityCurveRange || '1m';
        const rangeDays = { '1m': 30, '3m': 90, '6m': 180, 'all': 9999 };
        const days = rangeDays[range] || 30;
        const data = history.slice(-days);

        const c = ChartFactory.getColors();
        const labels = data.map(d => d.date || d.time || '');
        const values = data.map(d => d.equity);

        // 基准对比线
        const benchmark = this._pf.snapshot?.benchmark;
        let benchmarkData = null;
        if (benchmark && benchmark.benchmark_return !== 0 && values.length > 0) {
            const startVal = values[0];
            const bmReturn = benchmark.benchmark_return;
            const portReturn = benchmark.portfolio_return;
            const ratio = portReturn !== 0 ? bmReturn / portReturn : 0;
            benchmarkData = values.map((v, i) => {
                const progress = i / (values.length - 1);
                return startVal * (1 + bmReturn * progress);
            });
        }

        const datasets = [{
            label: '权益',
            data: values,
            borderColor: c.accent,
            backgroundColor: c.accent + '20',
            fill: true,
            tension: 0.3,
            pointRadius: 0,
            borderWidth: 2,
        }];

        if (benchmarkData) {
            datasets.push({
                label: '沪深300',
                data: benchmarkData,
                borderColor: c.danger,
                backgroundColor: 'transparent',
                fill: false,
                tension: 0.3,
                pointRadius: 0,
                borderWidth: 1.5,
                borderDash: [4, 4],
            });
        }

        const canvas = document.getElementById('pf-equity-curve');
        if (!canvas) return;

        if (canvas._chart) canvas._chart.destroy();
        canvas._chart = new Chart(canvas, {
            type: 'line',
            data: { labels, datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { intersect: false, mode: 'index' },
                plugins: {
                    legend: { display: datasets.length > 1, position: 'top' },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => `${ctx.dataset.label}: ¥${ctx.parsed.y.toLocaleString()}`,
                        },
                    },
                },
                scales: {
                    x: { display: true, ticks: { maxTicksLimit: 8 } },
                    y: {
                        display: true,
                        ticks: { callback: (v) => '¥' + (v / 1000).toFixed(0) + 'k' },
                    },
                },
            },
        });
    },

    _pfRenderPnlChart() {
        const positions = this._pf.positions;
        if (!positions || positions.length === 0) { ChartFactory.showEmpty('pf-pnl-chart'); return; }

        const c = ChartFactory.getColors();
        const colors = positions.map(p => p.pnl >= 0 ? 'rgba(16,185,129,0.7)' : 'rgba(198,87,70,0.7)');
        const borderColors = positions.map(p => p.pnl >= 0 ? c.success : c.danger);
        ChartFactory.bar('pf-pnl-chart', {
            labels: positions.map(p => p.code),
            values: positions.map(p => p.pnl),
            colors, borderColors,
        }, 'pnl');
    },

    _pfRenderIndustryChart() {
        const industry = this._pf.industry;
        if (!industry || industry.length === 0) { ChartFactory.showEmpty('pf-industry-chart'); return; }
        ChartFactory.pie('pf-industry-chart', {
            labels: industry.map(d => d.industry || '未知'),
            values: industry.map(d => d.value),
        }, 'industry');
    },

    _pfRenderAllocationChart() {
        const s = this._pf.snapshot;
        if (!s || !s.positions || s.positions.length === 0) { ChartFactory.showEmpty('pf-allocation-chart'); return; }
        const labels = s.positions.map(p => p.code);
        const values = s.positions.map(p => p.market_value);
        if (s.cash > 0) { labels.push('现金'); values.push(s.cash); }
        ChartFactory.doughnut('pf-allocation-chart', { labels, values }, 'allocation');
    },

    _pfRenderPositionTrend() {
        const history = this._pf.equityHistory || [];
        if (history.length < 2) { ChartFactory.showEmpty('pf-position-trend-chart'); return; }

        // 用权益历史中的持仓数或权益变化作为趋势
        const c = ChartFactory.getColors();
        const labels = history.map(d => d.date || '');
        const values = history.map(d => d.equity);

        const canvas = document.getElementById('pf-position-trend-chart');
        if (!canvas) return;

        if (canvas._chart) canvas._chart.destroy();
        canvas._chart = new Chart(canvas, {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    label: '权益走势',
                    data: values,
                    borderColor: c.accent,
                    backgroundColor: c.accent + '15',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0,
                    borderWidth: 2,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { maxTicksLimit: 10 } },
                    y: { ticks: { callback: (v) => '¥' + (v / 1000).toFixed(0) + 'k' } },
                },
            },
        });
    },

    pfSetRange(range) {
        this._pf.equityCurveRange = range;
        document.querySelectorAll('.pf-range-btns .chip').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.range === range);
        });
        this._pfRenderEquityCurve();
    },
});
