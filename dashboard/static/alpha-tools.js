/* ── AI Alpha：因子挖掘 / 公式 / 篮子 / 优化 ── */

Object.assign(App, {
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

    initFormulaBasketPickers() {
        if (this._formulaBasketPickersBound) return;
        this._formulaBasketPickersBound = true;

        if (document.getElementById('formula-code') && document.getElementById('formula-code-dropdown') && typeof SearchBox !== 'undefined') {
            this.formulaCodeSearch = new SearchBox('formula-code', 'formula-code-dropdown', {
                maxResults: 30,
                idleMessage: '自选股为空，输入代码或名称搜索全市场',
                formatItem: (s) => `${s.code} ${s.name || ''}`,
            });
            this.formulaCodeSearch.setDataSource((q) => this.searchStockPickerCandidates(q, {
                limit: 50,
                emptyLimit: 50,
                emptyScope: 'watchlist',
                silent: true,
            }));
            this.formulaCodeSearch.onSelect((item) => {
                const input = document.getElementById('formula-code');
                if (input) input.value = item.code;
            });
        }

        if (document.getElementById('basket-code-input') && document.getElementById('basket-code-dropdown') && document.getElementById('basket-code-tags') && typeof MultiSearchBox !== 'undefined') {
            this.basketMultiSearch = new MultiSearchBox('basket-code-input', 'basket-code-dropdown', 'basket-code-tags', {
                maxResults: 40,
                idleMessage: '自选股为空，输入代码或名称搜索全市场',
                formatItem: (s) => `${s.code} ${s.name || ''}`,
            });
            this.basketMultiSearch.setDataSource((q) => this.searchStockPickerCandidates(q, {
                limit: 50,
                emptyLimit: 50,
                emptyScope: 'watchlist',
                silent: true,
            }));
            this.basketMultiSearch.onToggle = () => this._syncBasketCandidatesFromPicker();
        }
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
            this.toast('全市场公式选股中...', 'info');
            const data = await this.postJSON('/api/alpha/formula/screen', { formula, start_date: startDate, end_date: endDate });
            this.renderFormulaScreen(data);
            this.toast('全市场选股完成', 'success');
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

    _normalizeBasketCandidate(item, index = 0) {
        const code = String(item?.code || '').trim();
        if (!/^\d{6}$/.test(code)) return null;
        const probability = Number(item?.probability);
        return {
            code,
            name: String(item?.name || code).trim(),
            industry: String(item?.industry || item?.sector || '').trim(),
            probability: Number.isFinite(probability) ? probability : Math.max(0.5, 0.82 - index * 0.03),
        };
    },

    _setBasketCandidates(items, { syncPicker = true } = {}) {
        const seen = new Set();
        const candidates = (Array.isArray(items) ? items : [])
            .map((item, index) => this._normalizeBasketCandidate(item, index))
            .filter(Boolean)
            .filter((item) => {
                if (seen.has(item.code)) return false;
                seen.add(item.code);
                return true;
            });
        const textarea = document.getElementById('basket-candidates');
        if (textarea) {
            textarea.value = candidates.length ? JSON.stringify(candidates, null, 2) : '';
        }
        if (syncPicker && this.basketMultiSearch) {
            this.basketMultiSearch.setSelected(candidates);
        }
        return candidates;
    },

    _syncBasketCandidatesFromPicker() {
        const selected = this.basketMultiSearch ? this.basketMultiSearch.getSelected() : [];
        this._setBasketCandidates(selected, { syncPicker: false });
    },

    useWatchlistForBasket() {
        const watchlist = Array.isArray(this.watchlistCache) ? this.watchlistCache : [];
        if (!watchlist.length) {
            this.toast('自选股为空，请先添加自选股或搜索加入篮子', 'warning');
            return;
        }
        const candidates = this._setBasketCandidates(watchlist.slice(0, 30));
        this.toast(`已导入 ${candidates.length} 只自选股`, 'success');
    },

    clearBasketCandidates() {
        this._setBasketCandidates([]);
        this.toast('篮子候选已清空', 'success');
    },

    _parseBasketCandidates() {
        const raw = document.getElementById('basket-candidates')?.value?.trim() || '';
        if (!raw) return [];
        const parsed = JSON.parse(raw);
        return this._setBasketCandidates(Array.isArray(parsed) ? parsed : []);
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
    document.addEventListener('DOMContentLoaded', () => {
        if (globalThis.__AUTH_GATE_REQUIRED__ === true) return;
        App.initAlpha?.();
    });
} else if (globalThis.__AUTH_GATE_REQUIRED__ !== true) {
    App.initAlpha?.();
}
