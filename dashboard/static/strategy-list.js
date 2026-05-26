/* ── 策略管理：列表 / 筛选 / 头部控制 ── */

if (!globalThis.Strategy) {
    globalThis.Strategy = {};
}

Object.assign(globalThis.Strategy, {
    _bindHeaderControls() {
        if (this._headerControlsBound) {
            return;
        }

        const exportBtn = document.getElementById('strategy-export-btn');
        const createBtn = document.getElementById('strategy-create-btn');
        const codeBtn = document.getElementById('strategy-code-editor-btn');
        const ensembleBtn = document.getElementById('strategy-ensemble-btn');
        const aiBtn = document.getElementById('strategy-ai-btn');
        const importInput = document.getElementById('strategy-import-input');
        const ensemble = typeof Ensemble !== 'undefined' ? Ensemble : null;

        if (!exportBtn || !importInput || !createBtn || !codeBtn || !ensembleBtn || !aiBtn) {
            return;
        }

        exportBtn.removeAttribute('onclick');
        exportBtn.addEventListener('click', (e) => {
            e.preventDefault();
            this.exportAll();
        });

        importInput.removeAttribute('onchange');
        importInput.addEventListener('change', (event) => {
            this.importFromFile(event);
        });

        createBtn.removeAttribute('onclick');
        createBtn.addEventListener('click', (e) => {
            e.preventDefault();
            this.showCreateModal();
        });

        codeBtn.removeAttribute('onclick');
        codeBtn.addEventListener('click', (e) => {
            e.preventDefault();
            this.showCodeEditor();
        });

        if (ensemble?.showEnsembleModal) {
            ensembleBtn.removeAttribute('onclick');
            ensembleBtn.addEventListener('click', (e) => {
                e.preventDefault();
                ensemble.showEnsembleModal();
            });
        }

        if (ensemble?.showAIModal) {
            aiBtn.removeAttribute('onclick');
            aiBtn.addEventListener('click', (e) => {
                e.preventDefault();
                ensemble.showAIModal();
            });
        }

        this._headerControlsBound = true;
    },

    _formatParams(params) {
        const entries = Object.entries(params || {});
        if (!entries.length) return '<span class="text-muted">无参数</span>';
        return entries.map(([k, v]) => `<code>${App.escapeHTML(k)}</code>=${App.escapeHTML(String(v))}`).join(' &nbsp;');
    },

    _renderStrategyCard(s) {
        return `
            <div class="strategy-card" data-name="${App.escapeHTML(s.name)}">
                <h3>${App.escapeHTML(s.label || s.name)}</h3>
                <span class="strategy-type">${App.escapeHTML(s.type || '自定义')}</span>
                ${s.builtin ? '<span class="badge badge-info">内置</span>' : ''}
                ${s.has_override ? '<span class="badge badge-warning">已修改</span>' : ''}
                ${s.code ? '<span class="badge badge-success">代码</span>' : ''}
                <p class="strategy-desc">${App.escapeHTML(s.description)}</p>
                <div class="strategy-params">${this._formatParams(s.params || {})}</div>
                <div class="strategy-actions">
                    <button class="btn btn-primary btn-sm" data-action="backtest">快速回测</button>
                    <button class="btn btn-sm" data-action="optimize">优化</button>
                    <button class="btn btn-sm" data-action="versions">版本</button>
                    <button class="btn btn-sm" data-action="records">记录</button>
                    ${s.builtin
                        ? `<button class="btn btn-secondary btn-sm" data-action="edit">编辑参数</button>`
                        : `<button class="btn btn-secondary btn-sm" data-action="edit">编辑</button>
                           <button class="btn btn-sm" data-action="editCode">代码</button>
                           <button class="btn btn-sm" data-action="clone">克隆</button>`
                    }
                    ${s.builtin ? '' : `<button class="btn btn-danger btn-sm" data-action="delete">删除</button>`}
                </div>
            </div>
        `;
    },

    _renderTagFilterBar(tags) {
        const filterBar = document.getElementById('st-filter');
        if (!filterBar) return;
        if (!tags.length) {
            filterBar.innerHTML = '';
            return;
        }
        filterBar.innerHTML = `<span style="font-size:13px;color:var(--text-secondary);margin-right:8px">标签:</span>` +
            [`<span class="tag-chip${!this._activeTag ? ' active' : ''}" data-tag="">全部</span>`]
                .concat(tags.map(t => `<span class="tag-chip${this._activeTag===t ? ' active' : ''}" data-tag="${App.escapeHTML(t)}">${App.escapeHTML(t)}</span>`))
                .join('');
        filterBar.onclick = (e) => {
            const chip = e.target.closest('.tag-chip');
            if (!chip) return;
            this._activeTag = chip.dataset.tag;
            this.load();
        };
    },

    async load() {
        this._bindHeaderControls();
        const grid = document.getElementById('st-list');
        if (!grid) return;
        grid.innerHTML = '<div class="skeleton-block skeleton-pulse" style="height:200px;border-radius:8px"></div>';

        try {
            const strategies = await App.fetchJSON('/api/strategy/list');

            const tagSet = new Set();
            strategies.forEach(s => (s.tags || []).forEach(t => tagSet.add(t)));
            this._allTags = [...tagSet].sort();
            this._activeTag = this._activeTag || '';

            this._renderTagFilterBar(this._allTags);

            const filtered = this._activeTag
                ? strategies.filter(s => (s.tags || []).includes(this._activeTag))
                : strategies;

            grid.innerHTML = filtered.map(s => this._renderStrategyCard(s)).join('');

            grid.onclick = (e) => {
                const btn = e.target.closest('[data-action]');
                if (!btn) return;
                const card = btn.closest('.strategy-card');
                const name = card?.dataset.name;
                if (!name) return;
                const action = btn.dataset.action;
                if (action === 'backtest') App.quickBacktest(name);
                else if (action === 'edit') this.edit(name);
                else if (action === 'editCode') this.editCode(name);
                else if (action === 'delete') this.remove(name);
                else if (action === 'versions') this.showVersions(name);
                else if (action === 'records') this.showRecords(name);
                else if (action === 'clone') this.clone(name);
                else if (action === 'optimize') this.showOptimize(name);
            };

            App._loadStrategies?.();
            if (typeof PaperTrading !== 'undefined') PaperTrading.loadStrategyList?.();
        } catch (e) {
            grid.innerHTML = '<div class="empty-state"><p>策略加载失败，请刷新重试</p></div>';
            App.toast('策略数据加载失败', 'error');
        }
    },
});

const _strategyListBoot = () => {
    const shouldBoot = location.hash === '#strategy-admin'
        || globalThis.App?.currentTab === 'strategy-admin';
    if (!shouldBoot) return;
    const grid = document.getElementById('st-list');
    if (grid && grid.querySelector('.strategy-card')) return;
    globalThis.Strategy?.load?.();
};

if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            if (globalThis.__AUTH_GATE_REQUIRED__ === true) return;
            requestAnimationFrame(_strategyListBoot);
        }, { once: true });
    } else if (globalThis.__AUTH_GATE_REQUIRED__ !== true) {
        requestAnimationFrame(_strategyListBoot);
    }
