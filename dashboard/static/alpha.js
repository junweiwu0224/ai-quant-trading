/* ── AI Alpha 全功能模块 ── */

Object.assign(App, {

    // ── 工具方法 ──
    // escapeHtml 已在 app.js 中定义为 escapeHTML，此处不再重复

    async postJSON(url, body) {
        return App.fetchJSON(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
    },

    // ── 子 Tab 切换 ──
    switchAlphaTab(tabName) {
        document.querySelectorAll('#alpha-sub-tabs .alpha-sub-tab').forEach(btn => {
            const isActive = btn.dataset.tab === tabName;
            btn.classList.toggle('active', isActive);
            btn.setAttribute('aria-selected', String(isActive));
        });
        document.querySelectorAll('#alpha-sub-panels .alpha-sub-panel').forEach(panel => {
            panel.classList.toggle('hidden', panel.id !== `alpha-panel-${tabName}`);
        });
    },

    initAlpha() {
        if (this._alphaInitDone) return;
        this._alphaInitDone = true;
        // 子 Tab 事件绑定
        document.querySelectorAll('#alpha-sub-tabs .alpha-sub-tab').forEach(btn => {
            btn.addEventListener('click', () => this.switchAlphaTab(btn.dataset.tab));
        });
        document.addEventListener('click', (event) => {
            const actionButton = event.target.closest('[data-alpha-action]');
            if (!actionButton) return;
            event.preventDefault();

            const actions = {
                'load-alpha': () => this.loadAlpha(),
                'optimize-alpha': () => this.optimizeAlpha(),
                'load-shap': () => this.loadShap(),
                'load-factor-eval': () => this.loadFactorEval(),
                'load-factor-decay': () => this.loadFactorDecay(),
                'load-factor-correlation': () => this.loadFactorCorrelation(),
                'factor-analyze': () => {
                    if (typeof Factor !== 'undefined') Factor.analyze();
                },
                'factor-correlation': () => {
                    if (typeof Factor !== 'undefined') Factor.loadCorrelation();
                },
                'load-compare': () => this.loadCompare(),
                'load-walk-forward': () => this.loadWalkForward(),
                'load-mine': () => this.loadMine(),
                'portopt-optimize': () => {
                    if (typeof PortfolioOpt !== 'undefined') PortfolioOpt.optimize();
                },
                'formula-evaluate': () => this.loadFormulaEvaluate(),
                'formula-screen': () => this.loadFormulaScreen(),
                'formula-catalog': () => this.loadFormulaCatalog(),
                'basket-plan': () => this.loadBasketPlan(),
                'basket-backtest': () => this.loadBasketBacktest(),
            };
            actions[actionButton.dataset.alphaAction]?.();
        });
    },

    // ── 主分析入口 ──
    async loadAlpha(opts = {}) {
        const code = document.getElementById('alpha-code').value;
        const startDate = document.getElementById('alpha-start').value;
        const endDate = document.getElementById('alpha-end').value;
        const modelType = document.getElementById('alpha-model')?.value || 'lightgbm';
        if (!code) { this.toast('请输入股票代码', 'error'); return; }

        const btn = this._getResearchHeaderActionButton ? this._getResearchHeaderActionButton('alpha-analyze') : null;
        if (btn) { btn.disabled = true; btn.dataset.origText = btn.textContent; btn.innerHTML = '<span class="skeleton-pulse" style="display:inline-block;width:1em;height:1em;border-radius:50%;vertical-align:middle;margin-right:4px"></span>分析中...'; }

        try {
            if (!opts.silent) this.toast('正在分析，请稍候...', 'info');
            const [importance, training, predictions, signals, perf] = await Promise.all([
                this.fetchJSON(`/api/alpha/factor-importance?code=${encodeURIComponent(code)}&start_date=${encodeURIComponent(startDate)}&end_date=${encodeURIComponent(endDate)}&model_type=${encodeURIComponent(modelType)}`),
                this.fetchJSON(`/api/alpha/training-metrics?code=${encodeURIComponent(code)}&start_date=${encodeURIComponent(startDate)}&end_date=${encodeURIComponent(endDate)}&model_type=${encodeURIComponent(modelType)}`),
                this.postJSON('/api/alpha/predict', { code, start_date: startDate, end_date: endDate, threshold: 0.5, model_type: modelType, buy_threshold: 0.6, sell_threshold: 0.4 }),
                this.fetchJSON(`/api/alpha/kline-signals?code=${encodeURIComponent(code)}&start_date=${encodeURIComponent(startDate)}&end_date=${encodeURIComponent(endDate)}&model_type=${encodeURIComponent(modelType)}&buy_threshold=0.6&sell_threshold=0.4`),
                this.postJSON('/api/alpha/performance', { code, start_date: startDate, end_date: endDate, model_type: modelType }).catch(() => null),
            ]);

            this.renderFeatureImportance(importance);
            this.renderTrainingCurve(training);
            this.renderPredictVsActual(predictions);
            this.renderSignalChart(signals);
            this.renderPerformance(perf);
            if (!opts.silent) this.toast('分析完成', 'success');
        } catch (e) {
            if (!opts.silent) this.toast('AI Alpha 分析失败: ' + e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = btn.dataset.origText || '分析'; }
        }
    },

    // ── 基础图表 ──

    renderFeatureImportance(data) {
        if (!data || data.length === 0) { ChartFactory.showEmpty('alpha-feature-chart'); return; }
        ChartFactory.horizontalBar('alpha-feature-chart', {
            labels: data.map(d => d.feature),
            values: data.map(d => d.importance),
        }, 'feature');
    },

    renderTrainingCurve(data) {
        if (!data || !data.epochs || data.epochs.length === 0) { ChartFactory.showEmpty('alpha-training-chart'); return; }
        const c = ChartFactory.getColors();
        ChartFactory.line('alpha-training-chart', {
            labels: data.epochs,
            datasets: [
                { label: 'Train AUC', data: data.train_auc, yAxisID: 'y-auc' },
                { label: 'Val AUC', data: data.val_auc, color: c.success, yAxisID: 'y-auc', borderDash: [5, 3] },
                { label: 'Train Loss', data: data.train_loss, color: c.warning, yAxisID: 'y-loss' },
                { label: 'Val Loss', data: data.val_loss, color: c.danger, yAxisID: 'y-loss', borderDash: [5, 3] },
            ],
        }, 'training', {
            plugins: { legend: { labels: { color: c.text } } },
            scales: {
                'y-auc': { type: 'linear', position: 'left', title: { display: true, text: 'AUC', color: c.textMuted }, ticks: { color: c.textMuted } },
                'y-loss': { type: 'linear', position: 'right', title: { display: true, text: 'Loss', color: c.textMuted }, ticks: { color: c.textMuted }, grid: { drawOnChartArea: false } },
            },
        });
    },

    renderPredictVsActual(data) {
        if (!data || !data.predictions || data.predictions.length === 0) { ChartFactory.showEmpty('alpha-predict-chart'); return; }
        const c = ChartFactory.getColors();
        const preds = data.predictions;
        ChartFactory.line('alpha-predict-chart', {
            labels: preds.map(p => p.date),
            datasets: [
                { label: '预测概率', data: preds.map(p => p.probability) },
                { label: '阈值线', data: preds.map(() => 0.5), color: c.danger, borderDash: [5, 5], borderWidth: 1 },
            ],
        }, 'predict', {
            plugins: { legend: { labels: { color: c.text } } },
            scales: { y: { min: 0, max: 1 } },
        });
    },

    renderSignalChart(klineData) {
        const kline = klineData.kline || [];
        const signals = klineData.signals || [];
        if (kline.length === 0) { ChartFactory.showEmpty('alpha-signal-chart'); return; }

        const c = ChartFactory.getColors();
        const closeData = kline.map(k => k.close);
        const dates = kline.map(k => k.date);
        const buyDates = new Set(signals.filter(s => s.type === 'buy').map(s => s.date));
        const sellDates = new Set(signals.filter(s => s.type === 'sell').map(s => s.date));

        const buyPoints = dates.map((d, i) => buyDates.has(d) ? closeData[i] : null);
        const sellPoints = dates.map((d, i) => sellDates.has(d) ? closeData[i] : null);

        ChartFactory.line('alpha-signal-chart', {
            labels: dates,
            datasets: [
                { label: '收盘价', data: closeData, color: c.muted },
                { label: '买入信号', data: buyPoints, color: c.success, pointRadius: 8, pointStyle: 'triangle' },
                { label: '卖出信号', data: sellPoints, color: c.danger, pointRadius: 8, pointStyle: 'triangle', pointRotation: 180 },
            ],
        }, 'signal', {
            plugins: { legend: { labels: { color: c.text } } },
        });
    },

    // ── 策略绩效 ──

    renderPerformance(data) {
        if (!data || !data.metrics) return;
        const m = data.metrics;
        const s = data.summary || {};
        const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val || '--'; };

        setVal('alpha-total-return', m['总收益率']);
        setVal('alpha-annual-return', m['年化收益率']);
        setVal('alpha-max-dd', m['最大回撤']);
        setVal('alpha-sharpe', m['夏普比率']);
        setVal('alpha-sortino', m['索提诺比率']);
        setVal('alpha-calmar', m['卡尔玛比率']);
        setVal('alpha-win-rate', s.win_rate ? (s.win_rate * 100).toFixed(1) + '%' : '--');
        setVal('alpha-profit-ratio', s.profit_ratio || '--');
        setVal('alpha-buy-count', s.buy_count || '--');
        setVal('alpha-sell-count', s.sell_count || '--');
        setVal('alpha-avg-win', s.avg_win ? '¥' + s.avg_win : '--');
        setVal('alpha-avg-loss', s.avg_loss ? '¥' + s.avg_loss : '--');

        // 权益曲线图
        const eq = data.equity_curve || [];
        if (eq.length > 0) {
            const c = ChartFactory.getColors();
            ChartFactory.line('alpha-equity-chart', {
                labels: eq.map(e => e.date),
                datasets: [{ label: '权益', data: eq.map(e => e.equity) }],
            }, 'equity', {
                plugins: { legend: { labels: { color: c.text } } },
            });
        }

        // 交易记录表
        const trades = data.trades || [];
        const tbody = document.querySelector('#alpha-trades-table tbody');
        if (tbody) {
            if (trades.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" class="text-muted">暂无交易</td></tr>';
            } else {
                const esc = App.escapeHTML;
                tbody.innerHTML = trades.map(t => `
                    <tr>
                        <td>${esc(t.date)}</td>
                        <td class="${t.type === 'buy' ? 'text-up' : 'text-down'}">${t.type === 'buy' ? '买入' : '卖出'}</td>
                        <td>${esc(t.price)}</td>
                        <td>${esc(t.shares)}</td>
                        <td class="${(t.pnl || 0) > 0 ? 'text-up' : (t.pnl || 0) < 0 ? 'text-down' : ''}">${t.pnl != null ? '¥' + esc(t.pnl) : '--'}</td>
                    </tr>
                `).join('');
            }
        }
    },

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

    // ── 自动因子挖掘 ──

    async loadMine() {
        const code = document.getElementById('alpha-code').value;
        const startDate = document.getElementById('alpha-start').value;
        const endDate = document.getElementById('alpha-end').value;
        if (!code) { this.toast('请先选择股票', 'error'); return; }

        try {
            this.toast('因子挖掘中...', 'info');
            const data = await this.postJSON('/api/alpha/mine', { code, start_date: startDate, end_date: endDate, top_n: 30 });
            this.renderMine(data);
            this.toast('因子挖掘完成', 'success');
        } catch (e) {
            this.toast('因子挖掘失败: ' + e.message, 'error');
        }
    },

    renderMine(data) {
        const tbody = document.querySelector('#alpha-mine-table tbody');
        if (!tbody) return;
        if (!data || data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-muted">未发现有效因子</td></tr>';
            return;
        }
        const esc = App.escapeHTML;
        tbody.innerHTML = data.map((f, i) => `
            <tr>
                <td>${i + 1}</td>
                <td>${esc(f.name)}</td>
                <td>${esc(f.ic)}</td>
                <td>${esc(f.abs_ic)}</td>
            </tr>
        `).join('');
    },

    // ── 公式系统 ──

    async loadFormulaEvaluate() {
        const code = document.getElementById('formula-code')?.value?.trim();
        const formula = document.getElementById('formula-source')?.value?.trim();
        const startDate = document.getElementById('formula-start')?.value || '';
        const endDate = document.getElementById('formula-end')?.value || '';
        if (!code || !formula) { this.toast('请填写股票代码和公式', 'error'); return; }

        try {
            this.toast('公式执行中...', 'info');
            const data = await this.postJSON('/api/alpha/formula/evaluate', { code, formula, start_date: startDate, end_date: endDate });
            this.renderFormulaEvaluate(data);
            this.toast(data?.success ? '公式执行完成' : '公式执行失败', data?.success ? 'success' : 'error');
        } catch (e) {
            this.toast('公式执行失败: ' + e.message, 'error');
        }
    },

    async loadFormulaScreen() {
        const formula = document.getElementById('formula-source')?.value?.trim();
        const startDate = document.getElementById('formula-start')?.value || '';
        const endDate = document.getElementById('formula-end')?.value || '';
        if (!formula) { this.toast('请先填写公式', 'error'); return; }

        try {
            this.toast('公式选股中...', 'info');
            const data = await this.postJSON('/api/alpha/formula/screen', { formula, start_date: startDate, end_date: endDate });
            this.renderFormulaScreen(data);
            this.toast('公式选股完成', 'success');
        } catch (e) {
            this.toast('公式选股失败: ' + e.message, 'error');
        }
    },

    async loadFormulaCatalog() {
        try {
            const data = await this.fetchJSON('/api/alpha/formula/catalog');
            this.renderFormulaCatalog(data);
            this.toast('公式目录已加载', 'success');
        } catch (e) {
            this.toast('公式目录加载失败: ' + e.message, 'error');
        }
    },

    renderFormulaEvaluate(data) {
        const successEl = document.getElementById('formula-success');
        const latestEl = document.getElementById('formula-latest-value');
        const matchEl = document.getElementById('formula-match-count');
        const errorEl = document.getElementById('formula-error-list');
        const seriesBody = document.querySelector('#formula-series-table tbody');

        if (successEl) successEl.textContent = data?.success ? '是' : '否';
        if (latestEl) latestEl.textContent = data?.latest_value ?? '--';
        if (matchEl) matchEl.textContent = Array.isArray(data?.series) ? String(data.series.length) : '0';
        if (errorEl) errorEl.textContent = data?.error || '暂无错误';

        if (seriesBody) {
            const esc = App.escapeHTML;
            const rows = Array.isArray(data?.series) ? data.series : [];
            seriesBody.innerHTML = rows.length > 0
                ? rows.map(row => `<tr><td>${esc(row.date)}</td><td>${esc(row.value ?? row.latest_value ?? '--')}</td></tr>`).join('')
                : '<tr><td colspan="2" class="text-muted">暂无结果</td></tr>';
        }
    },

    renderFormulaScreen(data) {
        const matchEl = document.getElementById('formula-match-count');
        const errorEl = document.getElementById('formula-error-list');
        const body = document.querySelector('#formula-screen-table tbody');
        const errors = Array.isArray(data?.errors) ? data.errors : [];

        if (matchEl) matchEl.textContent = String(data?.total ?? 0);
        if (errorEl) {
            errorEl.innerHTML = errors.length > 0
                ? errors.map(item => `<div>${App.escapeHTML(item.code)}: ${App.escapeHTML(item.error)}</div>`).join('')
                : '暂无错误';
        }

        if (body) {
            const matches = Array.isArray(data?.matches) ? data.matches : [];
            const esc = App.escapeHTML;
            body.innerHTML = matches.length > 0
                ? matches.map(item => `<tr><td>${esc(item.code)}</td><td>${esc(item.name)}</td><td>${esc(item.industry)}</td><td>${esc(item.latest_value)}</td></tr>`).join('')
                : '<tr><td colspan="4" class="text-muted">无命中结果</td></tr>';
        }
    },

    renderFormulaCatalog(data) {
        const body = document.querySelector('#formula-catalog-table tbody');
        if (!body) return;
        const funcs = Array.isArray(data?.functions) ? data.functions : [];
        const esc = App.escapeHTML;
        body.innerHTML = funcs.length > 0
            ? funcs.map(item => `<tr><td>${esc(item.name)}</td><td>${esc(item.args)}</td><td>${esc(item.desc)}</td></tr>`).join('')
            : '<tr><td colspan="3" class="text-muted">暂无公式目录</td></tr>';
    },

    // ── 篮子交易 ──

    _parseBasketCandidates() {
        const raw = document.getElementById('basket-candidates')?.value?.trim() || '';
        if (!raw) return [];
        const parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? parsed : [];
    },

    async loadBasketPlan() {
        const initialCash = Number(document.getElementById('basket-cash')?.value || 0);
        const allocation = document.getElementById('basket-allocation')?.value || 'equal';
        const rebalanceDays = Number(document.getElementById('basket-rebalance')?.value || 5);
        let candidates;
        try {
            candidates = this._parseBasketCandidates();
        } catch (error) {
            this.toast('候选股票格式不正确，请输入 JSON 数组', 'error');
            return;
        }
        if (!candidates.length) { this.toast('请先填写候选股票', 'error'); return; }

        try {
            this.toast('生成篮子计划中...', 'info');
            const data = await this.postJSON('/api/alpha/basket/plan', { candidates, initial_cash: initialCash, allocation, rebalance_days: rebalanceDays });
            this.renderBasketPlan(data);
            this.toast(data?.success ? '篮子计划已生成' : '篮子计划生成失败', data?.success ? 'success' : 'error');
        } catch (e) {
            this.toast('篮子计划生成失败: ' + e.message, 'error');
        }
    },

    async loadBasketBacktest() {
        const initialCash = Number(document.getElementById('basket-cash')?.value || 0);
        const allocation = document.getElementById('basket-allocation')?.value || 'equal';
        const rebalanceDays = Number(document.getElementById('basket-rebalance')?.value || 5);
        let candidates;
        try {
            candidates = this._parseBasketCandidates();
        } catch (error) {
            this.toast('候选股票格式不正确，请输入 JSON 数组', 'error');
            return;
        }
        if (!candidates.length) { this.toast('请先填写候选股票', 'error'); return; }

        try {
            this.toast('篮子回测中...', 'info');
            const data = await this.postJSON('/api/alpha/basket/backtest', { candidates, initial_cash: initialCash, allocation, rebalance_days: rebalanceDays });
            this.renderBasketBacktest(data);
            this.toast(data?.success ? '篮子回测完成' : '篮子回测失败', data?.success ? 'success' : 'error');
        } catch (e) {
            this.toast('篮子回测失败: ' + e.message, 'error');
        }
    },

    renderBasketPlan(data) {
        const successEl = document.getElementById('basket-success');
        const targetEl = document.getElementById('basket-target-value');
        const costEl = document.getElementById('basket-estimated-cost');
        const warningEl = document.getElementById('basket-warning-list');
        const body = document.querySelector('#basket-legs-table tbody');

        if (successEl) successEl.textContent = data?.success ? '是' : '否';
        if (targetEl) targetEl.textContent = data?.total_target_value != null ? `¥${Number(data.total_target_value).toFixed(2)}` : '--';
        if (costEl) costEl.textContent = data?.total_estimated_cost != null ? `¥${Number(data.total_estimated_cost).toFixed(2)}` : '--';
        if (warningEl) {
            const warnings = Array.isArray(data?.warnings) ? data.warnings : [];
            warningEl.innerHTML = warnings.length > 0
                ? warnings.map(item => `<div>${App.escapeHTML(item)}</div>`).join('')
                : '暂无警告';
        }

        if (body) {
            const legs = Array.isArray(data?.legs) ? data.legs : [];
            const esc = App.escapeHTML;
            body.innerHTML = legs.length > 0
                ? legs.map(item => `<tr><td>${esc(item.code)}</td><td>${esc(item.name)}</td><td>${esc(item.industry)}</td><td>${esc(item.weight)}</td><td>${esc(item.price)}</td><td>${esc(item.shares)}</td><td>${esc(item.target_value)}</td></tr>`).join('')
                : '<tr><td colspan="7" class="text-muted">暂无持仓腿</td></tr>';
        }
    },

    renderBasketBacktest(data) {
        const summary = document.getElementById('basket-backtest-summary');
        if (!summary) return;
        if (!data?.success) {
            summary.textContent = data?.error || '篮子回测失败';
            return;
        }

        const metrics = data.metrics || {};
        const lines = [
            metrics['总收益率'],
            metrics['年化收益率'],
            metrics['最大回撤'],
            metrics['夏普比率'],
            metrics['胜率'],
        ].filter(Boolean);
        summary.textContent = lines.length > 0 ? lines.join(' | ') : '回测完成';
    },

    async optimizeAlpha() {
        const code = document.getElementById('alpha-code').value;
        const startDate = document.getElementById('alpha-start').value;
        const endDate = document.getElementById('alpha-end').value;
        const modelType = document.getElementById('alpha-model')?.value || 'lightgbm';
        if (!code) { this.toast('请先选择股票', 'error'); return; }

        try {
            this.toast('超参优化中（约 1-3 分钟）...', 'info');
            const data = await this.postJSON('/api/alpha/optimize', { code, start_date: startDate, end_date: endDate, model_type: modelType, n_trials: 50 });
            if (data.error) {
                this.toast('优化失败: ' + data.error, 'error');
                return;
            }

            // 显示优化结果
            const paramsStr = Object.entries(data.best_params || {})
                .map(([k, v]) => `${k}=${typeof v === 'number' ? v.toFixed(4) : v}`)
                .join(', ');
            this.toast(`优化完成！最佳参数: ${paramsStr}`, 'success');

            // 显示到面板
            const el = document.getElementById('alpha-opt-result');
            if (el) el.textContent = paramsStr || '无';

            // 重新加载分析（静默模式，避免重复 toast）
            await this.loadAlpha({ silent: true });
        } catch (e) {
            this.toast('超参优化失败: ' + e.message, 'error');
        }
    },
});

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => App.initAlpha());
} else {
    App.initAlpha();
}
