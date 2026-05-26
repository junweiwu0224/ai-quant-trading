/* ── 股票详情页：筹码分布 ── */

if (!globalThis.StockDetail) {
    globalThis.StockDetail = {};
}

Object.assign(globalThis.StockDetail, {
    _chipsChart: null,

    async _loadChips(code, stale) {
        try {
            const data = await App.fetchJSON(`/api/stock/chips/${code}?days=120`);
            if (!data || stale()) return;
            this._renderChips(data);
        } catch (e) {
            console.error('加载筹码分布失败:', e);
        }
    },

    _renderChips(data) {
        const profitEl = document.getElementById('sd-chips-profit');
        const avgCostEl = document.getElementById('sd-chips-avg-cost');
        const concEl = document.getElementById('sd-chips-concentration');
        const hintEl = document.getElementById('sd-chips-hint');

        if (profitEl) profitEl.textContent = data.profit_ratio != null ? data.profit_ratio + '%' : '--';
        if (avgCostEl) avgCostEl.textContent = data.avg_cost != null ? data.avg_cost.toFixed(2) : '--';
        if (concEl && data.concentration_90) {
            concEl.textContent = data.concentration_90[0] + ' ~ ' + data.concentration_90[1];
        }
        if (hintEl) hintEl.textContent = data.current_price ? `当前 ${data.current_price}` : '';

        const canvas = document.getElementById('sd-chips-chart');
        if (!canvas || !data.chips || data.chips.length === 0) return;

        const chips = data.chips;
        const labels = chips.map(c => c.price.toFixed(2));
        const values = chips.map(c => c.pct);
        const currentPrice = data.current_price || 0;
        const colors = chips.map(c =>
            c.price <= currentPrice ? 'rgba(102, 187, 106, 0.7)' : 'rgba(239, 83, 80, 0.7)'
        );

        this._chipsChart = ChartFactory.create('sd-chips-chart', {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    data: values,
                    backgroundColor: colors,
                    borderWidth: 0,
                    barPercentage: 1.0,
                    categoryPercentage: 1.0,
                }],
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: ctx => `筹码: ${ctx.raw.toFixed(2)}%`,
                        },
                    },
                },
                scales: {
                    x: {
                        display: true,
                        grid: { display: false },
                        ticks: { display: false },
                        title: { display: false },
                    },
                    y: {
                        display: true,
                        grid: { display: false },
                        ticks: {
                            maxTicksLimit: 10,
                            font: { size: 10 },
                        },
                    },
                },
            },
        }, 'sd-chips');
    },
});
