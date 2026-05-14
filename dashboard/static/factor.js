/* ── 因子分析模块 ── */

const Factor = {
    _factors: [],

    async init() {
        if (this._factors.length) return;
        try {
            const data = await App.fetchJSON('/api/factor/list');
            this._factors = data.factors || [];
        } catch (e) {
            console.error('加载因子列表失败:', e);
        }
    },

    async analyze() {
        await this.init();
        const code = document.getElementById('alpha-code')?.value;
        const startDate = document.getElementById('alpha-start')?.value;
        const endDate = document.getElementById('alpha-end')?.value;

        const factorSel = document.getElementById('factor-select');
        const factorName = factorSel?.value;
        if (!code) { App.toast('请先选择股票', 'error'); return; }
        if (!factorName) { App.toast('请选择因子', 'error'); return; }

        const btn = App._getLegacyActionButton ? App._getLegacyActionButton('factor-analyze') : null;
        if (btn) { btn.disabled = true; btn.textContent = '分析中...'; }

        try {
            const result = await App.postJSON('/api/factor/analyze', {
                factor_name: factorName,
                stock_codes: [code],
                start_date: startDate || '2024-01-01',
                end_date: endDate || '2024-12-31',
                forward_period: 5,
            });

            if (!result.success) { App.toast(result.error || '分析失败', 'error'); return; }

            // 更新指标卡片
            document.getElementById('factor-avg-ic').textContent = result.avg_ic?.toFixed(4) || '--';
            document.getElementById('factor-ic-std').textContent = result.ic_std?.toFixed(4) || '--';
            document.getElementById('factor-ir').textContent = result.ir?.toFixed(4) || '--';

            // IC 序列图
            this._renderICChart(result.ic_series || []);

            // 分层收益图
            this._renderQuantileChart(result.quantile_returns || []);

            App.toast('因子分析完成', 'success');
        } catch (e) {
            App.toast('因子分析失败: ' + e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = '运行分析'; }
        }
    },

    async loadCorrelation() {
        await this.init();
        const code = document.getElementById('alpha-code')?.value;
        const startDate = document.getElementById('alpha-start')?.value;
        const endDate = document.getElementById('alpha-end')?.value;

        if (!code) { App.toast('请先选择股票', 'error'); return; }

        const btn = App._getLegacyActionButton ? App._getLegacyActionButton('factor-correlation') : null;
        if (btn) { btn.disabled = true; btn.textContent = '分析中...'; }

        try {
            // 取前6个技术因子做相关性
            const techFactors = this._factors.filter(f =>
                ['ma_5_ratio', 'ma_20_ratio', 'rsi_14', 'macd_hist', 'boll_width', 'atr_14',
                 'volatility_20', 'ret_5d', 'volume_ratio_5'].includes(f.name)
            ).map(f => f.name);

            if (techFactors.length < 2) { App.toast('可用因子不足', 'error'); return; }

            const result = await App.postJSON('/api/factor/correlation', {
                factor_names: techFactors.slice(0, 9),
                stock_codes: [code],
                start_date: startDate || '2024-01-01',
                end_date: endDate || '2024-12-31',
            });

            if (!result.success) { App.toast(result.error || '分析失败', 'error'); return; }

            this._renderCorrelation(result.factors, result.matrix);
            App.toast('因子相关性分析完成', 'success');
        } catch (e) {
            App.toast('相关性分析失败: ' + e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = '分析相关性'; }
        }
    },

    _renderICChart(icSeries) {
        const canvas = document.getElementById('factor-ic-chart');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (canvas._chart) canvas._chart.destroy();

        const labels = icSeries.map(d => d.date?.slice(5) || '');
        const values = icSeries.map(d => d.ic);
        const colors = values.map(v => v >= 0 ? 'rgba(16,185,129,0.7)' : 'rgba(239,68,68,0.7)');

        canvas._chart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: 'IC',
                    data: values,
                    backgroundColor: colors,
                    borderWidth: 0,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { label: c => `IC: ${c.parsed.y.toFixed(4)}` } },
                },
                scales: {
                    x: { ticks: { maxRotation: 45, font: { size: 10 } } },
                    y: { title: { display: true, text: 'IC' } },
                },
            },
        });
    },

    _renderQuantileChart(quantileReturns) {
        const canvas = document.getElementById('factor-quantile-bar-chart');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (canvas._chart) canvas._chart.destroy();

        const labels = ['Q1(低)', 'Q2', 'Q3', 'Q4', 'Q5(高)'];
        const colors = quantileReturns.map((v, i) => {
            const t = i / 4;
            return `rgba(${Math.round(239 - t * 100)}, ${Math.round(68 + t * 120)}, ${Math.round(68 + t * 50)}, 0.8)`;
        });

        canvas._chart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: '平均收益',
                    data: quantileReturns.map(v => (v * 100).toFixed(2)),
                    backgroundColor: colors,
                    borderWidth: 0,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { label: c => `收益: ${c.parsed.y}%` } },
                },
                scales: {
                    y: { title: { display: true, text: '收益率(%)' } },
                },
            },
        });
    },

    _renderCorrelation(factors, matrix) {
        // 表格
        const table = document.getElementById('factor-corr-matrix');
        if (table && matrix) {
            let html = '<thead><tr><th></th>';
            factors.forEach(f => { html += `<th style="font-size:11px">${f}</th>`; });
            html += '</tr></thead><tbody>';
            matrix.forEach((row, i) => {
                html += `<tr><td style="font-weight:600;font-size:11px">${factors[i]}</td>`;
                row.forEach(v => {
                    const abs = Math.abs(v);
                    const bg = abs > 0.7 ? 'rgba(239,68,68,0.3)' : abs > 0.4 ? 'rgba(245,158,11,0.2)' : 'transparent';
                    html += `<td style="text-align:center;font-size:11px;background:${bg}">${v.toFixed(2)}</td>`;
                });
                html += '</tr>';
            });
            html += '</tbody>';
            table.innerHTML = html;
        }

        // 热力图 Canvas
        const canvas = document.getElementById('factor-heatmap');
        if (!canvas || !matrix) return;
        const ctx = canvas.getContext('2d');
        const n = factors.length;
        const cellSize = Math.min(40, Math.floor(350 / n));
        canvas.width = cellSize * n + 60;
        canvas.height = cellSize * n + 60;

        ctx.clearRect(0, 0, canvas.width, canvas.height);
        const offsetX = 50, offsetY = 10;

        // 标签
        ctx.font = '10px sans-serif';
        ctx.fillStyle = '#94a3b8';
        factors.forEach((f, i) => {
            ctx.save();
            ctx.translate(offsetX + i * cellSize + cellSize / 2, offsetY - 2);
            ctx.rotate(-Math.PI / 4);
            ctx.fillText(f, 0, 0);
            ctx.restore();
            ctx.fillText(f, 2, offsetY + i * cellSize + cellSize / 2 + 3);
        });

        // 热力格
        matrix.forEach((row, i) => {
            row.forEach((v, j) => {
                const r = v > 0 ? Math.round(16 + v * 80) : 16;
                const g = v > 0 ? Math.round(185 - v * 100) : Math.round(185 + v * 100);
                const b = v < 0 ? Math.round(129 - v * 100) : 129;
                ctx.fillStyle = `rgba(${r},${g},${b},0.8)`;
                ctx.fillRect(offsetX + j * cellSize, offsetY + i * cellSize, cellSize - 1, cellSize - 1);
                ctx.fillStyle = Math.abs(v) > 0.5 ? '#fff' : '#333';
                ctx.textAlign = 'center';
                ctx.fillText(v.toFixed(2), offsetX + j * cellSize + cellSize / 2, offsetY + i * cellSize + cellSize / 2 + 3);
            });
        });
    },
};
