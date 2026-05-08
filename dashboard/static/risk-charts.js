/* ── 风控模块：图表 ── */

Object.assign(App, {
    _rkRenderCharts() {
        this._rkRenderDrawdownCurve();
        this._rkRenderCapitalGauge();
        this._rkRenderIndustry();
        this._rkRenderCorrelation();
        this._rkRenderPositionPie();
    },

    _rkRenderDrawdownCurve() {
        const history = this._rk.equityHistory;
        if (!history || history.length < 2) return;

        const labels = [];
        const ddData = [];
        let peak = 0;

        for (const point of history) {
            const eq = point.equity || 0;
            if (eq > peak) peak = eq;
            const dd = peak > 0 ? (-(peak - eq) / peak * 100) : 0;
            labels.push(point.date);
            ddData.push(dd);
        }

        const c = ChartFactory.getColors();
        ChartFactory.line('rk-drawdown-chart', {
            labels,
            datasets: [
                { label: '回撤', data: ddData, borderColor: c.danger, backgroundColor: c.danger + '30', fill: true, tension: 0.3, pointRadius: 0 },
            ],
        }, 'rk-dd');
    },

    _rkRenderCapitalGauge() {
        const cap = this._rk.capital;
        if (!cap) return;

        const used = cap.market_value || 0;
        const cash = cap.cash || 0;
        const total = cap.total_equity || (used + cash);

        ChartFactory.doughnut('rk-capital-chart', {
            labels: ['持仓市值', '可用现金'],
            values: [used, cash],
        }, 'rk-cap');

        const pct = total > 0 ? (used / total * 100).toFixed(1) : '0';
        const el = document.getElementById('rk-capital-pct');
        if (el) el.textContent = pct + '%';

        this._rkSetInfo('rk-cap-total', this.fmt(total));
        this._rkSetInfo('rk-cap-used', this.fmt(used));
        this._rkSetInfo('rk-cap-cash', this.fmt(cash));
        this._rkSetInfo('rk-cap-max-single', ((cap.max_single_pct || 0) * 100).toFixed(1) + '%');
    },

    _rkRenderIndustry() {
        const data = this._rk.industry;
        if (!data || data.length === 0) return;

        const labels = data.map(d => d.industry);
        const values = data.map(d => d.value);

        ChartFactory.horizontalBar('rk-industry-chart', { labels, values }, 'rk-ind');

        const warnEl = document.getElementById('rk-industry-warn');
        if (warnEl) {
            const total = values.reduce((a, b) => a + b, 0);
            const maxPct = total > 0 ? Math.max(...values) / total : 0;
            warnEl.textContent = maxPct > 0.3 ? '行业集中度超过 30%，请注意分散风险' : '';
            warnEl.className = maxPct > 0.3 ? 'text-down mt-sm' : '';
        }
    },

    _rkRenderCorrelation() {
        const data = this._rk.correlation;
        if (!data || data.length === 0) return;

        const canvas = document.getElementById('rk-correlation-canvas');
        if (!canvas) return;

        const codes = [...new Set(data.flatMap(d => [d.code_a, d.code_b]))].sort();
        const n = codes.length;
        if (n < 2) return;

        const matrix = {};
        for (const item of data) {
            matrix[item.code_a + '|' + item.code_b] = item.correlation;
            matrix[item.code_b + '|' + item.code_a] = item.correlation;
        }
        for (const code of codes) {
            matrix[code + '|' + code] = 1;
        }

        const containerWidth = canvas.parentElement?.clientWidth || 400;
        const maxCellSize = 48;
        const minCellSize = 28;
        const padding = 52;
        const availWidth = Math.max(containerWidth - padding * 2, 200);
        const cellSize = Math.max(minCellSize, Math.min(maxCellSize, Math.floor(availWidth / n)));
        const size = n * cellSize + padding * 2;

        canvas.width = size * 2;
        canvas.height = size * 2;
        canvas.style.width = size + 'px';
        canvas.style.height = size + 'px';

        const ctx = canvas.getContext('2d');
        ctx.scale(2, 2);
        ctx.clearRect(0, 0, size, size);

        const textColor = getComputedStyle(document.documentElement).getPropertyValue('--text-tertiary').trim() || '#888';
        const primaryColor = getComputedStyle(document.documentElement).getPropertyValue('--text-primary').trim() || '#333';

        ctx.font = '11px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillStyle = textColor;

        for (let i = 0; i < n; i++) {
            ctx.fillText(codes[i].slice(-4), padding + i * cellSize + cellSize / 2, padding - 10);
            ctx.save();
            ctx.translate(padding - 10, padding + i * cellSize + cellSize / 2);
            ctx.rotate(-Math.PI / 2);
            ctx.fillText(codes[i].slice(-4), 0, 0);
            ctx.restore();
        }

        for (let i = 0; i < n; i++) {
            for (let j = 0; j < n; j++) {
                const val = matrix[codes[i] + '|' + codes[j]] || 0;
                const x = padding + j * cellSize;
                const y = padding + i * cellSize;

                const r = val >= 0 ? 198 : 16;
                const g = val >= 0 ? 87 : 185;
                const b = val >= 0 ? 70 : 129;
                const alpha = Math.abs(val) * 0.8;

                ctx.fillStyle = `rgba(${r},${g},${b},${alpha})`;
                ctx.fillRect(x, y, cellSize - 1, cellSize - 1);

                ctx.fillStyle = Math.abs(val) > 0.5 ? '#fff' : primaryColor;
                ctx.font = `${Math.max(9, cellSize * 0.25)}px sans-serif`;
                ctx.fillText(val.toFixed(2), x + cellSize / 2, y + cellSize / 2);
            }
        }

        canvas.onmousemove = e => {
            const rect = canvas.getBoundingClientRect();
            const scaleX = size / rect.width;
            const scaleY = size / rect.height;
            const mx = (e.clientX - rect.left) * scaleX;
            const my = (e.clientY - rect.top) * scaleY;
            const ci = Math.floor((mx - padding) / cellSize);
            const ri = Math.floor((my - padding) / cellSize);

            if (ri >= 0 && ri < n && ci >= 0 && ci < n) {
                const val = matrix[codes[ri] + '|' + codes[ci]] || 0;
                canvas.title = `${codes[ri]} vs ${codes[ci]}: ${val.toFixed(3)}`;
            } else {
                canvas.title = '';
            }
        };
    },

    _rkRenderPositionPie() {
        const positions = this._rk.snapshot?.positions;
        if (!positions || positions.length === 0) return;

        const cash = this._rk.snapshot?.cash || 0;
        const labels = positions.map(p => p.code);
        const values = positions.map(p => p.market_value || p.value || 0);
        labels.push('现金');
        values.push(cash);

        ChartFactory.doughnut('rk-position-chart', { labels, values }, 'rk-pos');
    },

    _rkSetInfo(id, value) {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    },
});
