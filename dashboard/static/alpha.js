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
        if (!this._alphaActionHandlersBound) {
            this._alphaActionHandlersBound = true;
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
                    'basket-use-watchlist': () => this.useWatchlistForBasket(),
                    'basket-clear-candidates': () => this.clearBasketCandidates(),
                    'basket-plan': () => this.loadBasketPlan(),
                    'basket-backtest': () => this.loadBasketBacktest(),
                    'basket-update-backtest-draft': () => this.updateBasketBacktestDraftFromEditor?.(),
                };
                actions[actionButton.dataset.alphaAction]?.();
            });
        }

        this.initFormulaBasketPickers?.();
        this.renderBasketBacktestDraft?.();
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


});

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        if (globalThis.__AUTH_GATE_REQUIRED__ === true) return;
        App.initAlpha();
    });
} else if (globalThis.__AUTH_GATE_REQUIRED__ !== true) {
    App.initAlpha();
}
