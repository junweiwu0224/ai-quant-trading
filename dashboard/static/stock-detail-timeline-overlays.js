/* ── 股票详情页：分时叠加 / 资金流 ── */

if (!globalThis.StockDetail) {
    globalThis.StockDetail = {};
}

Object.assign(globalThis.StockDetail, {
    /** 均价线 overlay（逐段 segment 连线） */
    _addTimelineAvgOverlay(chart, trends, parseTime) {
        const segs = [];
        for (let i = 1; i < trends.length; i++) {
            if (trends[i].avg_price == null || trends[i - 1].avg_price == null) continue;
            segs.push(chart.createOverlay({
                name: 'segment',
                points: [
                    { timestamp: parseTime(trends[i - 1].time), value: trends[i - 1].avg_price },
                    { timestamp: parseTime(trends[i].time), value: trends[i].avg_price },
                ],
                styles: { line: { style: 'solid', color: '#e6a817', size: 1 } },
                lock: true,
            }));
        }
        this._avgOverlays = segs;
    },

    /** 昨收参考线 overlay（水平延伸线） */
    _addPreCloseOverlay(chart, trends, parseTime, preClose) {
        chart.createOverlay({
            name: 'straightLine',
            points: [
                { timestamp: parseTime(trends[0].time), value: preClose },
                { timestamp: parseTime(trends[trends.length - 1].time), value: preClose },
            ],
            styles: { line: { style: 'dashed', color: 'rgba(128,128,128,0.5)', size: 1 } },
            lock: true,
        });
    },

    /** 切换多日分时叠加 */
    async _toggleMultiDayOverlay(btn) {
        const chart = this._klineChart;
        if (!chart) return;

        if (this._multiDayOverlays && this._multiDayOverlays.length > 0) {
            this._multiDayOverlays.forEach(id => chart.removeOverlay(id));
            this._multiDayOverlays = [];
            btn.classList.remove('active');
            return;
        }

        if (!this._currentCode) return;
        btn.classList.add('active');

        try {
            const data = await App.fetchJSON(`/api/stock/timeline-multi/${this._currentCode}?days=5`);
            if (!data || !data.days || data.days.length < 2) {
                App.toast('多日数据不足', 'warning');
                btn.classList.remove('active');
                return;
            }

            const colors = ['#4fc3f7', '#e6a817', '#ab47bc', '#66bb6a', '#ef5350'];
            const overlays = [];

            const todayIdx = data.days.length - 1;
            const todayDay = data.days[todayIdx];
            const todayBars = todayDay.bars || [];
            if (todayBars.length < 2) return;

            const todayPreClose = this._currentTimelinePreClose || todayBars[0]?.close || 1;
            const parseTime = (timeStr) => {
                const parts = timeStr.split(' ');
                if (parts.length > 1) {
                    const [date, time] = parts;
                    const [year, month, day] = date.split('-');
                    const [hour, minute] = time.split(':');
                    return new Date(year, month - 1, day, hour, minute).getTime();
                }
                return new Date(timeStr).getTime();
            };

            const firstTs = parseTime(todayBars[0].time);
            const lastTs = parseTime(todayBars[todayBars.length - 1].time);
            const tsRange = lastTs - firstTs || 1;

            for (let di = 0; di < todayIdx; di++) {
                const day = data.days[di];
                const bars = day.bars;
                if (!bars || bars.length === 0) continue;

                const preClose = data.pre_closes[day.date] || bars[0].open || 1;
                const ohlc = [bars[0].open, bars[0].high, bars[0].low, bars[0].close];
                const returns = ohlc.map(p => (p - preClose) / preClose);

                const timePoints = [0, 0.33, 0.66, 1].map(t => firstTs + t * tsRange);
                const points = timePoints.map((ts, i) => ({
                    timestamp: ts,
                    value: todayPreClose * (1 + returns[i]),
                }));

                const color = colors[di % colors.length];
                for (let i = 1; i < points.length; i++) {
                    const segId = chart.createOverlay({
                        name: 'segment',
                        points: [points[i - 1], points[i]],
                        styles: { line: { style: 'solid', color, size: 1 } },
                        lock: true,
                    });
                    overlays.push(segId);
                }
            }

            this._multiDayOverlays = overlays;
        } catch (e) {
            console.error('多日叠加加载失败:', e);
            App.toast('多日叠加加载失败', 'error');
            btn.classList.remove('active');
        }
    },

    async _loadCapitalFlow(code, stale) {
        try {
            const data = await App.fetchJSON(`/api/stock/capital-flow/${code}?days=20`);
            if (!data || stale()) return;
            this._renderCapitalChart(data.flow);
        } catch (e) {
            console.error('加载资金流向失败:', e);
        }
    },

    _renderCapitalChart(flow) {
        const canvas = document.getElementById('sd-capital-chart');
        if (!canvas) return;

        if (!flow || flow.length === 0) {
            canvas.parentElement.innerHTML = '<p class="text-muted" style="text-align:center;padding:1rem">暂无资金流向数据</p>';
            return;
        }

        const labels = flow.map(f => f.date.substring(5));
        const mainData = flow.map(f => (f.super_net + f.big_net) / 1e4);
        const superData = flow.map(f => f.super_net / 1e4);
        const getColor = (v) => v >= 0 ? 'rgba(239, 83, 80, 0.85)' : 'rgba(38, 166, 154, 0.85)';
        const getBorderColor = (v) => v >= 0 ? 'rgba(239, 83, 80, 1)' : 'rgba(38, 166, 154, 1)';

        this._capitalChart = ChartFactory.create('sd-capital-chart', {
            type: 'bar',
            data: {
                labels,
                datasets: [
                    {
                        label: '主力净流入',
                        data: mainData,
                        backgroundColor: mainData.map(getColor),
                        borderColor: mainData.map(getBorderColor),
                        borderWidth: 1,
                        borderRadius: 2,
                    },
                    {
                        label: '其中: 超大单',
                        data: superData,
                        backgroundColor: 'rgba(255, 193, 7, 0.6)',
                        borderColor: 'rgba(255, 193, 7, 0.9)',
                        borderWidth: 1,
                        borderRadius: 2,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: {
                            color: '#aaa',
                            font: { size: 11 },
                            usePointStyle: true,
                            pointStyle: 'rectRounded',
                            padding: 15,
                        },
                    },
                    tooltip: {
                        backgroundColor: 'rgba(20,20,35,0.95)',
                        titleColor: '#eee',
                        bodyColor: '#ccc',
                        borderColor: '#444',
                        borderWidth: 1,
                        padding: 10,
                        callbacks: {
                            title: (items) => items[0]?.label || '',
                            label: (context) => {
                                const label = context.dataset.label || '';
                                const value = context.parsed.y;
                                const absValue = Math.abs(value);
                                const formatted = absValue >= 10000
                                    ? (absValue / 10000).toFixed(2) + '亿'
                                    : absValue.toFixed(0) + '万';
                                const prefix = value >= 0 ? '流入 ↑' : '流出 ↓';
                                return `${label}: ${prefix} ${formatted}`;
                            },
                            afterBody: (items) => {
                                if (items.length >= 1) {
                                    const idx = items[0].dataIndex;
                                    const f = flow[idx];
                                    if (f) {
                                        const big = f.big_net / 1e4;
                                        const med = f.medium_net / 1e4;
                                        const small = f.small_net / 1e4;
                                        const absBig = Math.abs(big);
                                        const absMed = Math.abs(med);
                                        const absSmall = Math.abs(small);
                                        const fmt = (v) => v >= 10000 ? (v / 10000).toFixed(2) + '亿' : v.toFixed(0) + '万';
                                        return [
                                            '─────────',
                                            `大单: ${big >= 0 ? '+' : '-'}${fmt(absBig)}`,
                                            `中单: ${med >= 0 ? '+' : '-'}${fmt(absMed)}`,
                                            `小单: ${small >= 0 ? '+' : '-'}${fmt(absSmall)}`,
                                        ];
                                    }
                                }
                                return [];
                            },
                        },
                    },
                },
                scales: {
                    x: {
                        ticks: { color: '#888', maxTicksLimit: 10 },
                        grid: { color: 'rgba(255,255,255,0.05)' },
                    },
                    y: {
                        ticks: {
                            color: '#888',
                            callback: v => {
                                const absV = Math.abs(v);
                                return absV >= 10000
                                    ? (absV / 10000).toFixed(0) + '亿'
                                    : absV.toFixed(0) + '万';
                            },
                        },
                        grid: { color: 'rgba(255,255,255,0.05)' },
                    },
                },
            },
        }, 'sd-capital');
    },
});
