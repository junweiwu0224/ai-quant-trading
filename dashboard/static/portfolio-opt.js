/* ── 组合优化模块 ── */

const PortfolioOpt = {
    _methods: [],

    async init() {
        if (this._methods.length) return;
        try {
            const data = await App.fetchJSON('/api/portfolio-opt/methods');
            this._methods = data.methods || [];
        } catch (e) {
            console.error('加载优化方法失败:', e);
        }
    },

    async optimize() {
        await this.init();
        const codesStr = document.getElementById('portopt-codes')?.value || '';
        const codes = codesStr.split(/[,，\s]+/).filter(Boolean);
        const method = document.getElementById('portopt-method')?.value || 'max_sharpe';
        const startDate = document.getElementById('portopt-start')?.value || '2024-01-01';
        const endDate = document.getElementById('portopt-end')?.value || '2024-12-31';

        if (codes.length < 2) { App.toast('至少需要2只股票', 'error'); return; }

        const btn = App._getLegacyActionButton ? App._getLegacyActionButton('portopt-optimize') : null;
        if (btn) { btn.disabled = true; btn.textContent = '优化中...'; }

        try {
            const result = await App.postJSON('/api/portfolio-opt/optimize', {
                codes,
                method,
                start_date: startDate,
                end_date: endDate,
            });

            if (!result.success) { App.toast(result.error || '优化失败', 'error'); return; }

            // 更新指标
            document.getElementById('portopt-return').textContent = (result.expected_return * 100).toFixed(2) + '%';
            document.getElementById('portopt-vol').textContent = (result.expected_volatility * 100).toFixed(2) + '%';
            document.getElementById('portopt-sharpe').textContent = result.sharpe_ratio?.toFixed(4) || '--';

            // 权重饼图
            this._renderPie(result.weights || {});

            // 权重表格
            this._renderWeightTable(result.weights || {});

            App.toast('组合优化完成', 'success');
        } catch (e) {
            App.toast('组合优化失败: ' + e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = '执行优化'; }
        }
    },

    _renderPie(weights) {
        const canvas = document.getElementById('portopt-pie-chart');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (canvas._chart) canvas._chart.destroy();

        const entries = Object.entries(weights).filter(([, v]) => v > 0.001);
        const labels = entries.map(([k]) => k);
        const values = entries.map(([, v]) => (v * 100).toFixed(1));
        const palette = [
            'rgba(99,102,241,0.8)', 'rgba(16,185,129,0.8)', 'rgba(245,158,11,0.8)',
            'rgba(239,68,68,0.8)', 'rgba(139,92,246,0.8)', 'rgba(6,182,212,0.8)',
            'rgba(236,72,153,0.8)', 'rgba(132,204,22,0.8)', 'rgba(251,146,60,0.8)',
            'rgba(168,85,247,0.8)', 'rgba(20,184,166,0.8)', 'rgba(244,63,94,0.8)',
        ];

        canvas._chart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels,
                datasets: [{
                    data: values,
                    backgroundColor: palette.slice(0, labels.length),
                    borderWidth: 2,
                    borderColor: 'rgba(15,23,42,0.8)',
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'right', labels: { color: '#94a3b8', font: { size: 12 } } },
                    tooltip: { callbacks: { label: c => `${c.label}: ${c.parsed}%` } },
                },
            },
        });
    },

    _renderWeightTable(weights) {
        const table = document.getElementById('portopt-weight-table');
        if (!table) return;
        const entries = Object.entries(weights).filter(([, v]) => v > 0.001).sort((a, b) => b[1] - a[1]);
        let html = '<thead><tr><th>股票</th><th>权重</th></tr></thead><tbody>';
        entries.forEach(([code, w]) => {
            html += `<tr><td>${App.escapeHTML(code)}</td><td style="text-align:right">${(w * 100).toFixed(2)}%</td></tr>`;
        });
        html += '</tbody>';
        table.innerHTML = html;
    },
};
