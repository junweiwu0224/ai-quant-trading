/* ── AI Alpha：因子评价 / SHAP / Walk-forward / 模型对比 ── */

Object.assign(App, {
    // ── 因子评价 ──

    async loadFactorEval() {
        const code = document.getElementById('alpha-code').value;
        const startDate = document.getElementById('alpha-start').value;
        const endDate = document.getElementById('alpha-end').value;
        if (!code) { this.toast('请先选择股票', 'error'); return; }

        try {
            const data = await this.postJSON('/api/alpha/factor-eval', { code, start_date: startDate, end_date: endDate, forward_period: 5 });
            this.renderFactorEval(data);
        } catch (e) {
            this.toast('因子评价失败: ' + e.message, 'error');
        }
    },

    renderFactorEval(data) {
        if (!data || data.length === 0) return;
        const c = ChartFactory.getColors();

        // 因子评价表
        const tbody = document.querySelector('#alpha-factor-eval-table tbody');
        if (tbody) {
            const esc = App.escapeHTML;
            tbody.innerHTML = data.slice(0, 30).map(f => `
                <tr>
                    <td>${esc(f.factor)}</td>
                    <td>${esc(f.ic)}</td>
                    <td class="${f.abs_ic > 0.05 ? 'text-up' : ''}">${esc(f.abs_ic)}</td>
                    <td>${esc(f.turnover)}</td>
                </tr>
            `).join('');
        }

        // 分层收益图（Top 因子）
        const topFactors = data.filter(f => f.quantile_returns && f.quantile_returns.length > 0);
        if (topFactors.length > 0) {
            const first = topFactors[0];
            const n = first.quantile_returns.length;
            ChartFactory.bar('alpha-quantile-chart', {
                labels: Array.from({ length: n }, (_, i) => `Q${i + 1}`),
                values: first.quantile_returns,
            }, 'quantile');
        }
    },

    // ── SHAP ──

    async loadShap() {
        const code = document.getElementById('alpha-code').value;
        const startDate = document.getElementById('alpha-start').value;
        const endDate = document.getElementById('alpha-end').value;
        const modelType = document.getElementById('alpha-model')?.value || 'lightgbm';
        if (!code) { this.toast('请先选择股票', 'error'); return; }

        try {
            this.toast('SHAP 分析中...', 'info');
            const data = await this.postJSON('/api/alpha/shap', { code, start_date: startDate, end_date: endDate, model_type: modelType });
            if (data.error) { this.toast('SHAP: ' + data.error, 'error'); return; }
            this.renderShap(data);
            this.toast('SHAP 分析完成', 'success');
        } catch (e) {
            this.toast('SHAP 分析失败: ' + e.message, 'error');
        }
    },

    renderShap(data) {
        if (!data) return;
        const c = ChartFactory.getColors();

        // SHAP 全局重要性（替代 feature importance）
        const imp = data.global_importance || [];
        if (imp.length > 0) {
            ChartFactory.horizontalBar('alpha-shap-chart', {
                labels: imp.slice(0, 20).map(d => d.feature),
                values: imp.slice(0, 20).map(d => d.shap_importance),
            }, 'shap');
        }

        // SHAP 依赖图（第一个因子）
        const dep = data.dependence || {};
        const depKeys = Object.keys(dep);
        if (depKeys.length > 0) {
            const feat = depKeys[0];
            const d = dep[feat];
            const scatterData = d.feature_values.map((fv, i) => ({ x: fv, y: d.shap_values[i] }));
            ChartFactory.scatter('alpha-shap-dep-chart', scatterData, feat);
        }
    },

    // ── Walk-forward ──

    async loadWalkForward() {
        const code = document.getElementById('alpha-code').value;
        const startDate = document.getElementById('alpha-start').value;
        const endDate = document.getElementById('alpha-end').value;
        const modelType = document.getElementById('alpha-model')?.value || 'lightgbm';
        if (!code) { this.toast('请先选择股票', 'error'); return; }

        try {
            this.toast('Walk-forward 验证中...', 'info');
            const data = await this.postJSON('/api/alpha/walk-forward', { code, start_date: startDate, end_date: endDate, model_type: modelType });
            this.renderWalkForward(data);
            this.toast('Walk-forward 完成', 'success');
        } catch (e) {
            this.toast('Walk-forward 失败: ' + e.message, 'error');
        }
    },

    renderWalkForward(data) {
        if (!data || !data.windows) return;
        const c = ChartFactory.getColors();
        const windows = data.windows;
        const stability = data.stability || {};

        // WF AUC 曲线
        if (windows.length > 0) {
            ChartFactory.line('alpha-wf-chart', {
                labels: windows.map(w => `W${w.window}`),
                datasets: [
                    { label: 'Train AUC', data: windows.map(w => w.train_auc), color: c.primary },
                    { label: 'Test AUC', data: windows.map(w => w.test_auc), color: c.success },
                ],
            }, 'wf', {
                plugins: { legend: { labels: { color: c.text } } },
                scales: { y: { min: 0.4, max: 1.0 } },
            });
        }

        // 稳定性指标
        const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val || '--'; };
        setVal('alpha-wf-mean', stability.mean_auc);
        setVal('alpha-wf-std', stability.std_auc);
        setVal('alpha-wf-min', stability.min_auc);
        setVal('alpha-wf-max', stability.max_auc);
        setVal('alpha-wf-windows', stability.n_windows);

        const stabEl = document.getElementById('alpha-wf-stable');
        if (stabEl) {
            stabEl.textContent = stability.is_stable ? '稳定' : '不稳定';
            stabEl.className = 'stat-value ' + (stability.is_stable ? 'text-up' : 'text-down');
        }
    },

    // ── 模型对比 ──

    async loadCompare() {
        const code = document.getElementById('alpha-code').value;
        const startDate = document.getElementById('alpha-start').value;
        const endDate = document.getElementById('alpha-end').value;
        if (!code) { this.toast('请先选择股票', 'error'); return; }

        try {
            this.toast('模型对比中...', 'info');
            const data = await this.postJSON('/api/alpha/compare', { code, start_date: startDate, end_date: endDate });
            this.renderCompare(data);
            this.toast('对比完成', 'success');
        } catch (e) {
            this.toast('模型对比失败: ' + e.message, 'error');
        }
    },

    renderCompare(data) {
        if (!data) return;
        const c = ChartFactory.getColors();

        // 对比表格
        const tbody = document.querySelector('#alpha-compare-table tbody');
        if (tbody) {
            const esc = App.escapeHTML;
            const models = ['lightgbm', 'xgboost', 'ensemble'];
            tbody.innerHTML = models.map(m => {
                const d = data[m] || {};
                return `<tr>
                    <td>${esc(m)}</td>
                    <td>${esc(d.auc) || '--'}</td>
                    <td>${esc(d.accuracy) || '--'}</td>
                    <td>${esc(d.error) || 'OK'}</td>
                </tr>`;
            }).join('');
        }

        // AUC 对比柱状图
        const models = Object.keys(data).filter(m => !data[m].error);
        if (models.length > 0) {
            ChartFactory.bar('alpha-compare-chart', {
                labels: models,
                values: models.map(m => data[m].auc),
            }, 'compare');
        }
    },

    // ── 因子相关性 ──

    async loadFactorCorrelation() {
        const code = document.getElementById('alpha-code').value;
        const startDate = document.getElementById('alpha-start').value;
        const endDate = document.getElementById('alpha-end').value;
        if (!code) { this.toast('请先选择股票', 'error'); return; }

        try {
            const data = await this.postJSON('/api/alpha/factor-correlation', { code, start_date: startDate, end_date: endDate });
            this.renderFactorCorrelation(data);
        } catch (e) {
            this.toast('因子相关性分析失败: ' + e.message, 'error');
        }
    },

    renderFactorCorrelation(data) {
        if (!data) return;

        // 高相关因子对表格
        const tbody = document.querySelector('#alpha-corr-table tbody');
        if (tbody) {
            const pairs = data.high_corr_pairs || [];
            if (pairs.length === 0) {
                tbody.innerHTML = '<tr><td colspan="3" class="text-muted">无高相关因子对 (阈值 > 0.8)</td></tr>';
            } else {
                const esc = App.escapeHTML;
                tbody.innerHTML = pairs.map(p => `
                    <tr>
                        <td>${esc(p.factor_a)}</td>
                        <td>${esc(p.factor_b)}</td>
                        <td class="${Math.abs(p.correlation) > 0.9 ? 'text-down' : ''}">${esc(p.correlation)}</td>
                    </tr>
                `).join('');
            }
        }

        // 热力图用 canvas 绘制
        this._renderHeatmap(data);
    },

    _renderHeatmap(data) {
        const canvas = document.getElementById('alpha-heatmap-canvas');
        if (!canvas || !data.factors || !data.matrix) return;

        const ctx = canvas.getContext('2d');
        const factors = data.factors;
        const matrix = data.matrix;
        const n = factors.length;
        const cellSize = Math.min(Math.floor(600 / n), 20);
        const labelWidth = 80;

        canvas.width = labelWidth + n * cellSize;
        canvas.height = labelWidth + n * cellSize;

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // 绘制热力图
        for (let i = 0; i < n; i++) {
            for (let j = 0; j < n; j++) {
                const val = matrix[i]?.[j] ?? 0;
                const absVal = Math.abs(val);
                let r, g, b;
                if (val > 0) {
                    r = 220; g = Math.round(220 - absVal * 180); b = Math.round(220 - absVal * 180);
                } else {
                    r = Math.round(220 - absVal * 180); g = Math.round(220 - absVal * 180); b = 220;
                }
                ctx.fillStyle = `rgb(${r},${g},${b})`;
                ctx.fillRect(labelWidth + j * cellSize, labelWidth + i * cellSize, cellSize - 1, cellSize - 1);
            }
        }

        // 标签
        ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--text') || '#333';
        ctx.font = '9px sans-serif';
        for (let i = 0; i < n; i++) {
            const shortName = factors[i].slice(0, 10);
            ctx.fillText(shortName, 2, labelWidth + i * cellSize + cellSize / 2 + 3);
            ctx.save();
            ctx.translate(labelWidth + i * cellSize + cellSize / 2, labelWidth - 3);
            ctx.rotate(-Math.PI / 4);
            ctx.fillText(shortName, 0, 0);
            ctx.restore();
        }
    },

    // ── 因子衰减 ──

    async loadFactorDecay() {
        const code = document.getElementById('alpha-code').value;
        const startDate = document.getElementById('alpha-start').value;
        const endDate = document.getElementById('alpha-end').value;
        if (!code) { this.toast('请先选择股票', 'error'); return; }

        try {
            const data = await this.postJSON('/api/alpha/factor-decay', { code, start_date: startDate, end_date: endDate, top_n: 8 });
            this.renderFactorDecay(data);
        } catch (e) {
            this.toast('因子衰减分析失败: ' + e.message, 'error');
        }
    },

    renderFactorDecay(data) {
        if (!data || Object.keys(data).length === 0) { ChartFactory.showEmpty('alpha-decay-chart'); return; }
        const c = ChartFactory.getColors();
        const periods = ['1d', '3d', '5d', '10d', '20d', '60d'];
        const colors = [c.primary, c.success, c.warning, c.danger, c.muted, c.tertiary, c.quaternary, c.border];

        const datasets = Object.entries(data).map(([factor, ics], i) => ({
            label: factor,
            data: periods.map(p => ics[p] || 0),
            color: colors[i % colors.length],
        }));

        ChartFactory.line('alpha-decay-chart', {
            labels: periods,
            datasets: datasets,
        }, 'decay', {
            plugins: { legend: { labels: { color: c.text } } },
            scales: { y: { title: { display: true, text: 'IC', color: c.textMuted } } },
        });
    },
});
