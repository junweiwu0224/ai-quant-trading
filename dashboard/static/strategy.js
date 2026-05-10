/* ── 策略管理（含模态框 CRUD + 结构化参数表单 + 代码编辑器） ── */

const Strategy = {
    // 内置策略参数定义 {name: [{key, label, type, min, max, step, default}]}
    PARAM_DEFS: {
        dual_ma: [
            { key: 'short_window', label: '短均线周期', type: 'int', min: 2, max: 60, default: 5 },
            { key: 'long_window', label: '长均线周期', type: 'int', min: 5, max: 250, default: 20 },
            { key: 'position_pct', label: '仓位比例', type: 'float', min: 0.01, max: 1, step: 0.05, default: 0.9 },
        ],
        bollinger: [
            { key: 'window', label: '窗口期', type: 'int', min: 5, max: 120, default: 20 },
            { key: 'num_std', label: '标准差倍数', type: 'float', min: 0.5, max: 4, step: 0.1, default: 2 },
            { key: 'position_pct', label: '仓位比例', type: 'float', min: 0.01, max: 1, step: 0.05, default: 0.9 },
        ],
        momentum: [
            { key: 'lookback', label: '回看周期', type: 'int', min: 2, max: 120, default: 20 },
            { key: 'entry_threshold', label: '入场阈值', type: 'float', min: 0.01, max: 1, step: 0.01, default: 0.1 },
        ],
    },

    async load() {
        const grid = document.getElementById('st-list');
        if (!grid) return;
        grid.innerHTML = '<div class="skeleton-block skeleton-pulse" style="height:200px;border-radius:8px"></div>';

        try {
            const strategies = await App.fetchJSON('/api/strategy/list');
            grid.innerHTML = strategies.map(s => `
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
            `).join('');
            // 事件委托（避免 XSS）
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
            };
            // 通知其他模块刷新策略列表
            App._loadStrategies?.();
            if (typeof PaperTrading !== 'undefined') PaperTrading.loadStrategyList?.();
        } catch (e) {
            grid.innerHTML = '<div class="empty-state"><p>策略加载失败，请刷新重试</p></div>';
            App.toast('策略数据加载失败', 'error');
        }
    },

    _formatParams(params) {
        const entries = Object.entries(params || {});
        if (!entries.length) return '<span class="text-muted">无参数</span>';
        return entries.map(([k, v]) => `<code>${App.escapeHTML(k)}</code>=${App.escapeHTML(String(v))}`).join(' &nbsp;');
    },

    showCreateModal() {
        this._showModal({
            title: '新增策略',
            name: '', label: '', description: '', params: {},
            isNew: true, builtinName: null,
        });
    },

    showCodeEditor() {
        this._showCodeModal({ name: '', code: '', isNew: true });
    },

    async edit(name) {
        try {
            const strategies = await App.fetchJSON('/api/strategy/list');
            const s = strategies.find(x => x.name === name);
            if (!s) { App.toast('策略不存在', 'error'); return; }
            this._showModal({
                title: s.builtin ? `编辑参数 — ${s.label || s.name}` : `编辑策略 — ${s.label || s.name}`,
                name: s.name,
                label: s.label || s.name,
                description: s.description || '',
                params: s.params || {},
                isNew: false,
                builtinName: s.builtin ? s.name : null,
            });
        } catch (e) {
            App.toast('加载策略失败', 'error');
        }
    },

    async editCode(name) {
        try {
            const strategies = await App.fetchJSON('/api/strategy/list');
            const s = strategies.find(x => x.name === name);
            if (!s) { App.toast('策略不存在', 'error'); return; }
            this._showCodeModal({
                name: s.name,
                code: s.code || '',
                isNew: false,
            });
        } catch (e) {
            App.toast('加载策略失败', 'error');
        }
    },

    _showCodeModal({ name, code, isNew }) {
        document.querySelector('.modal-overlay')?.remove();

        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';

        overlay.innerHTML = `
            <div class="modal" style="max-width:800px;width:95vw" role="dialog" aria-modal="true" aria-label="${isNew ? '新建代码策略' : '编辑策略代码'}">
                <h2>${isNew ? '新建代码策略' : '编辑策略代码 — ' + App.escapeHTML(name)}</h2>
                ${isNew ? `<div class="form-group" style="margin-bottom:12px">
                    <label>策略名称（英文标识）</label>
                    <input type="text" id="modal-code-name" value="${App.escapeHTML(name)}" placeholder="如 my_strategy" required>
                </div>` : ''}
                <div class="form-group" style="margin-bottom:12px">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
                        <label style="margin:0">策略代码 (Python)</label>
                        <div>
                            <button class="btn btn-sm" id="modal-code-template">加载模板</button>
                            <button class="btn btn-sm" id="modal-code-validate">验证代码</button>
                        </div>
                    </div>
                    <textarea id="modal-code-editor" rows="20" style="width:100%;font-family:monospace;font-size:13px;line-height:1.5;padding:12px;border:1px solid var(--border-color);border-radius:8px;background:var(--bg-secondary);resize:vertical;tab-size:4">${App.escapeHTML(code || '')}</textarea>
                    <div id="modal-code-status" style="margin-top:6px;font-size:12px;min-height:18px"></div>
                </div>
                <div style="font-size:12px;color:var(--text-tertiary);margin-bottom:12px">
                    <p>提示：策略类必须继承 <code>BaseStrategy</code>，实现 <code>on_bar(self, bar)</code> 方法。</p>
                    <p>可用：<code>self.buy(code, volume)</code>、<code>self.sell(code, volume)</code>、<code>self.portfolio</code></p>
                </div>
                <div class="modal-actions">
                    <button class="btn btn-ghost" id="modal-code-cancel">取消</button>
                    <button class="btn btn-primary" id="modal-code-save">保存</button>
                </div>
            </div>
        `;

        document.body.appendChild(overlay);

        // Focus first interactive element
        const firstInput = overlay.querySelector('input, textarea');
        if (firstInput) setTimeout(() => firstInput.focus(), 50);

        const editor = overlay.querySelector('#modal-code-editor');
        const statusEl = overlay.querySelector('#modal-code-status');

        // Tab 键支持
        editor.addEventListener('keydown', (e) => {
            if (e.key === 'Tab') {
                e.preventDefault();
                const start = editor.selectionStart;
                const end = editor.selectionEnd;
                editor.value = editor.value.substring(0, start) + '    ' + editor.value.substring(end);
                editor.selectionStart = editor.selectionEnd = start + 4;
            }
        });

        // 加载模板
        overlay.querySelector('#modal-code-template').addEventListener('click', async () => {
            try {
                const data = await App.fetchJSON('/api/strategy/template');
                editor.value = data.code || '';
                statusEl.innerHTML = '<span style="color:var(--success-color)">模板已加载</span>';
            } catch (e) {
                statusEl.innerHTML = '<span style="color:var(--error-color)">加载模板失败</span>';
            }
        });

        // 验证代码
        overlay.querySelector('#modal-code-validate').addEventListener('click', async () => {
            try {
                const data = await App.fetchJSON('/api/strategy/validate-code', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ code: editor.value }),
                    label: '代码验证',
                });
                if (data.valid) {
                    statusEl.innerHTML = '<span style="color:var(--success-color)">代码验证通过</span>';
                } else {
                    statusEl.innerHTML = `<span style="color:var(--error-color)">验证失败: ${App.escapeHTML(data.error)}</span>`;
                }
            } catch (e) {
                statusEl.innerHTML = '<span style="color:var(--error-color)">验证请求失败</span>';
            }
        });

        // 关闭
        overlay.querySelector('#modal-code-cancel').addEventListener('click', () => overlay.remove());
        overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });

        // 保存
        overlay.querySelector('#modal-code-save').addEventListener('click', async () => {
            const codeText = editor.value.trim();
            if (!codeText) { App.toast('代码不能为空', 'error'); return; }

            if (isNew) {
                const newName = overlay.querySelector('#modal-code-name')?.value.trim();
                if (!newName) { App.toast('策略名称不能为空', 'error'); return; }
                if (!/^[a-zA-Z_]\w*$/.test(newName)) { App.toast('策略名只能包含字母、数字和下划线', 'error'); return; }

                // 先验证
                try {
                    const vData = await App.fetchJSON('/api/strategy/validate-code', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ code: codeText }),
                        label: '代码验证',
                    });
                    if (!vData.valid) { App.toast('代码验证失败: ' + vData.error, 'error'); return; }
                } catch (e) { /* ignore */ }

                try {
                    await App.fetchJSON('/api/strategy', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            name: newName,
                            label: newName,
                            type: '代码策略',
                            description: '用户自定义代码策略',
                            params: {},
                            code: codeText,
                        }),
                        label: '创建策略',
                    });
                    App.toast('策略已创建', 'success');
                    overlay.remove();
                    this.load();
                } catch (e) {
                    App.toast('创建失败: ' + e.message, 'error');
                }
            } else {
                try {
                    await App.fetchJSON(`/api/strategy/${name}`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ code: codeText }),
                        label: '更新策略',
                    });
                    App.toast('策略代码已更新', 'success');
                    overlay.remove();
                    this.load();
                } catch (e) {
                    App.toast('更新失败: ' + e.message, 'error');
                }
            }
        });
    },

    _showModal({ title, name, label, description, params, isNew, builtinName }) {
        document.querySelector('.modal-overlay')?.remove();

        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';

        const paramDefs = builtinName ? this.PARAM_DEFS[builtinName] : null;
        const paramHTML = paramDefs
            ? this._buildStructuredParams(paramDefs, params)
            : `<div class="form-group" style="margin-bottom:12px">
                   <label>参数（JSON）</label>
                   <textarea id="modal-st-params" rows="4" placeholder="{}">${App.escapeHTML(JSON.stringify(params, null, 2))}</textarea>
               </div>`;

        overlay.innerHTML = `
            <div class="modal" role="dialog" aria-modal="true" aria-label="${App.escapeHTML(title)}">
                <h2>${App.escapeHTML(title)}</h2>
                ${isNew ? `<div class="form-group" style="margin-bottom:12px">
                    <label>策略名称（英文标识）</label>
                    <input type="text" id="modal-st-name" value="${App.escapeHTML(name)}" placeholder="如 my_strategy" required>
                </div>` : ''}
                ${isNew || !builtinName ? `<div class="form-group" style="margin-bottom:12px">
                    <label>显示名称</label>
                    <input type="text" id="modal-st-label" value="${App.escapeHTML(label)}" placeholder="如 我的策略" required>
                </div>` : ''}
                ${isNew || !builtinName ? `<div class="form-group" style="margin-bottom:12px">
                    <label>策略描述</label>
                    <textarea id="modal-st-desc" rows="3" placeholder="策略说明...">${App.escapeHTML(description)}</textarea>
                </div>` : ''}
                ${paramHTML}
                <div class="modal-actions">
                    <button class="btn btn-ghost" id="modal-st-cancel">取消</button>
                    <button class="btn btn-primary" id="modal-st-save">保存</button>
                </div>
            </div>
        `;

        document.body.appendChild(overlay);

        // Focus first interactive element
        const firstInput = overlay.querySelector('input, textarea, select');
        if (firstInput) setTimeout(() => firstInput.focus(), 50);

        // 关闭
        overlay.querySelector('#modal-st-cancel').addEventListener('click', () => overlay.remove());
        overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
        document.addEventListener('keydown', function esc(e) { if (e.key === 'Escape') { overlay.remove(); document.removeEventListener('keydown', esc); } });

        // 保存
        overlay.querySelector('#modal-st-save').addEventListener('click', async () => {
            const parsedParams = paramDefs
                ? this._collectStructuredParams(overlay, paramDefs)
                : this._collectJsonParams(overlay);
            if (parsedParams === null) return;

            if (isNew) {
                const newName = overlay.querySelector('#modal-st-name')?.value.trim();
                const newLabel = overlay.querySelector('#modal-st-label')?.value.trim();
                const newDesc = overlay.querySelector('#modal-st-desc')?.value.trim();
                if (!newName) { App.toast('策略名称不能为空', 'error'); return; }
                if (!/^[a-zA-Z_]\w*$/.test(newName)) { App.toast('策略名只能包含字母、数字和下划线', 'error'); return; }
                if (!newLabel) { App.toast('显示名称不能为空', 'error'); return; }
                await this._create(newName, newLabel, newDesc, parsedParams);
            } else if (builtinName) {
                await this._update(name, null, null, parsedParams);
            } else {
                const newLabel = overlay.querySelector('#modal-st-label')?.value.trim();
                const newDesc = overlay.querySelector('#modal-st-desc')?.value.trim();
                if (!newLabel) { App.toast('显示名称不能为空', 'error'); return; }
                await this._update(name, newLabel, newDesc, parsedParams);
            }
            overlay.remove();
        });
    },

    _buildStructuredParams(defs, current) {
        return `<div class="param-fields" style="margin-bottom:12px">
            <label style="font-weight:600;margin-bottom:8px;display:block">策略参数</label>
            ${defs.map(d => {
                const val = current[d.key] ?? d.default;
                const step = d.step || (d.type === 'float' ? 0.01 : 1);
                return `<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
                    <label style="min-width:100px;font-size:13px;color:var(--text-secondary)">${App.escapeHTML(d.label)}</label>
                    <input type="number" data-param="${d.key}" value="${val}"
                        min="${d.min}" max="${d.max}" step="${step}"
                        style="flex:1;padding:6px 8px;border:1px solid var(--border-color);border-radius:6px;font-size:13px">
                    <span style="font-size:11px;color:var(--text-tertiary);min-width:60px">${d.min} ~ ${d.max}</span>
                </div>`;
            }).join('')}
        </div>`;
    },

    _collectStructuredParams(overlay, defs) {
        const params = {};
        for (const d of defs) {
            const input = overlay.querySelector(`[data-param="${d.key}"]`);
            if (!input) continue;
            const raw = input.value.trim();
            if (raw === '') { App.toast(`${d.label} 不能为空`, 'error'); return null; }
            const val = d.type === 'int' ? parseInt(raw, 10) : parseFloat(raw);
            if (isNaN(val)) { App.toast(`${d.label} 必须是数字`, 'error'); return null; }
            if (val < d.min || val > d.max) { App.toast(`${d.label} 必须在 ${d.min} ~ ${d.max} 之间`, 'error'); return null; }
            params[d.key] = val;
        }
        return params;
    },

    _collectJsonParams(overlay) {
        const textarea = overlay.querySelector('#modal-st-params');
        if (!textarea) return {};
        const raw = textarea.value.trim();
        if (!raw) return {};
        try { return JSON.parse(raw); }
        catch { App.toast('参数格式不是合法 JSON', 'error'); return null; }
    },

    async _create(name, label, description, params) {
        try {
            await App.fetchJSON('/api/strategy', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, label, description, type: '自定义', params }),
                label: '创建策略',
            });
            App.toast(`策略 "${label}" 已创建`, 'success');
            this.load();
        } catch (e) {
            App.toast('创建失败: ' + e.message, 'error');
        }
    },

    async _update(name, label, description, params) {
        try {
            const body = {};
            if (label !== null) body.label = label;
            if (description !== null) body.description = description;
            if (params !== null) body.params = params;
            await App.fetchJSON(`/api/strategy/${name}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
                label: '更新策略',
            });
            App.toast('策略已更新', 'success');
            this.load();
        } catch (e) {
            App.toast('更新失败: ' + e.message, 'error');
        }
    },

    /** 导出所有策略为 JSON 文件 */
    async exportAll() {
        try {
            const data = await App.fetchJSON('/api/system/strategies/export');
            if (!data.success) {
                App.toast(data.error || '导出失败', 'error');
                return;
            }
            const json = JSON.stringify(data.data, null, 2);
            const blob = new Blob([json], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `strategies_${new Date().toISOString().slice(0, 10)}.json`;
            a.click();
            URL.revokeObjectURL(url);
            App.toast('策略已导出', 'success');
        } catch (e) {
            App.toast('导出失败: ' + e.message, 'error');
        }
    },

    /** 从文件导入策略 */
    async importFromFile(event) {
        const file = event.target.files[0];
        if (!file) return;
        event.target.value = '';

        try {
            const text = await file.text();
            const data = JSON.parse(text);

            const strategies = data.custom || (data.strategy ? [data.strategy] : []);
            const names = strategies.map(s => s.name || '未命名').join('、');
            const overwrite = await this._confirm(
                `发现 ${strategies.length} 个策略：${names}`,
                '覆盖同名策略？点击确认覆盖，取消跳过'
            );

            const result = await App.fetchJSON('/api/system/strategies/import', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ...data, overwrite }),
                label: '导入策略',
            });

            if (result.success) {
                let msg = `导入完成：${result.imported} 个成功`;
                if (result.skipped > 0) msg += `，${result.skipped} 个跳过`;
                if (result.errors?.length > 0) msg += `，${result.errors.length} 个错误`;
                App.toast(msg, result.errors?.length > 0 ? 'warning' : 'success');
                this.load();
            } else {
                App.toast(result.error || '导入失败', 'error');
            }
        } catch (e) {
            App.toast('导入失败：文件格式无效', 'error');
        }
    },

    // ── 自定义确认弹窗 (H3) ──

    _confirm(title, message) {
        return new Promise(resolve => {
            document.querySelector('.modal-overlay')?.remove();
            const overlay = document.createElement('div');
            overlay.className = 'modal-overlay';
            overlay.innerHTML = `
                <div class="modal" style="max-width:400px" role="dialog" aria-modal="true">
                    <h2>${App.escapeHTML(title)}</h2>
                    <p style="color:var(--text-secondary);margin-bottom:16px">${App.escapeHTML(message)}</p>
                    <div class="modal-actions">
                        <button class="btn btn-ghost" id="confirm-cancel">取消</button>
                        <button class="btn btn-primary" id="confirm-ok">确认</button>
                    </div>
                </div>`;
            document.body.appendChild(overlay);
            overlay.querySelector('#confirm-ok').onclick = () => { overlay.remove(); resolve(true); };
            overlay.querySelector('#confirm-cancel').onclick = () => { overlay.remove(); resolve(false); };
            overlay.onclick = (e) => { if (e.target === overlay) { overlay.remove(); resolve(false); } };
        });
    },

    // ── 克隆策略 (M2) ──

    async clone(name) {
        try {
            const strategies = await App.fetchJSON('/api/strategy/list');
            const s = strategies.find(x => x.name === name);
            if (!s) { App.toast('策略不存在', 'error'); return; }
            const newName = name + '_copy';
            await App.fetchJSON('/api/strategy', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: newName,
                    label: (s.label || s.name) + ' (副本)',
                    type: s.type || '自定义',
                    description: s.description || '',
                    params: { ...(s.params || {}) },
                    code: s.code || '',
                }),
                label: '克隆策略',
            });
            App.toast(`策略已克隆为 "${newName}"`, 'success');
            this.load();
        } catch (e) {
            App.toast('克隆失败: ' + e.message, 'error');
        }
    },

    // ── 版本管理 (C1) ──

    async showVersions(name) {
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.innerHTML = `
            <div class="modal" style="max-width:700px;width:95vw" role="dialog" aria-modal="true">
                <h2>版本管理 — ${App.escapeHTML(name)}</h2>
                <div style="display:flex;gap:8px;margin-bottom:12px">
                    <button class="btn btn-primary btn-sm" id="ver-save">保存当前版本</button>
                </div>
                <div id="ver-list"><div class="skeleton-block skeleton-pulse" style="height:100px"></div></div>
                <div id="ver-diff" style="margin-top:12px"></div>
                <div class="modal-actions"><button class="btn btn-ghost" id="ver-close">关闭</button></div>
            </div>`;
        document.body.appendChild(overlay);

        const loadVersions = async () => {
            try {
                const versions = await App.fetchJSON(`/api/strategy-version/versions/${name}`);
                const listEl = overlay.querySelector('#ver-list');
                if (!versions.length) {
                    listEl.innerHTML = '<p class="text-muted">暂无版本记录</p>';
                    return;
                }
                listEl.innerHTML = `
                    <table style="width:100%;font-size:13px;border-collapse:collapse">
                        <thead><tr style="border-bottom:1px solid var(--border-color)">
                            <th style="text-align:left;padding:6px">版本</th>
                            <th style="text-align:left;padding:6px">标签</th>
                            <th style="text-align:left;padding:6px">时间</th>
                            <th style="text-align:left;padding:6px">操作</th>
                        </tr></thead>
                        <tbody>${versions.map(v => `
                            <tr style="border-bottom:1px solid var(--border-color)">
                                <td style="padding:6px">v${v.version}${v.is_current ? ' <span class="badge badge-success">当前</span>' : ''}</td>
                                <td style="padding:6px">${App.escapeHTML(v.label || '')}</td>
                                <td style="padding:6px">${App.escapeHTML(v.created_at || '')}</td>
                                <td style="padding:6px">
                                    ${!v.is_current ? `<button class="btn btn-sm" data-ver-action="rollback" data-ver="${v.version}">回滚</button>` : ''}
                                    <button class="btn btn-sm" data-ver-action="diff" data-ver="${v.version}">对比</button>
                                </td>
                            </tr>
                        `).join('')}</tbody>
                    </table>`;

                listEl.onclick = async (e) => {
                    const btn = e.target.closest('[data-ver-action]');
                    if (!btn) return;
                    const ver = parseInt(btn.dataset.ver);
                    const action = btn.dataset.verAction;

                    if (action === 'rollback') {
                        const ok = await this._confirm(`回滚到 v${ver}`, '将创建新版本并复制该版本的参数和代码');
                        if (!ok) return;
                        try {
                            const result = await App.fetchJSON('/api/strategy-version/versions/rollback', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ strategy_name: name, version: ver }),
                            });
                            if (result.error) { App.toast(result.error, 'error'); return; }
                            App.toast(`已回滚至 v${ver}，新版本 v${result.version}`, 'success');
                            loadVersions();
                            this.load();
                        } catch (e2) { App.toast('回滚失败: ' + e2.message, 'error'); }
                    }

                    if (action === 'diff') {
                        const currentVer = versions.find(v => v.is_current)?.version;
                        if (!currentVer) return;
                        const v1 = Math.min(ver, currentVer);
                        const v2 = Math.max(ver, currentVer);
                        try {
                            const diff = await App.fetchJSON(`/api/strategy-version/versions/${name}/diff?v1=${v1}&v2=${v2}`);
                            const diffEl = overlay.querySelector('#ver-diff');
                            let html = `<h3 style="margin-bottom:8px">v${v1} vs v${v2}</h3>`;

                            // 参数差异
                            if (Object.keys(diff.param_diff || {}).length) {
                                html += '<h4>参数差异</h4><table style="width:100%;font-size:13px;border-collapse:collapse">';
                                for (const [k, vals] of Object.entries(diff.param_diff)) {
                                    html += `<tr><td style="padding:4px 8px">${App.escapeHTML(k)}</td><td style="padding:4px 8px;color:var(--error-color)">${App.escapeHTML(String(vals[`v${v1}`] ?? '-'))}</td><td style="padding:4px 8px">→</td><td style="padding:4px 8px;color:var(--success-color)">${App.escapeHTML(String(vals[`v${v2}`] ?? '-'))}</td></tr>`;
                                }
                                html += '</table>';
                            }

                            // 代码差异
                            if (diff.code_changed && diff.code_diff?.length) {
                                html += '<h4 style="margin-top:8px">代码差异</h4>';
                                html += '<pre style="font-size:12px;background:var(--bg-secondary);padding:8px;border-radius:6px;overflow-x:auto;max-height:200px">';
                                for (const line of diff.code_diff) {
                                    const color = line.startsWith('+') ? 'var(--success-color)' : line.startsWith('-') ? 'var(--error-color)' : 'var(--text-secondary)';
                                    html += `<span style="color:${color}">${App.escapeHTML(line)}</span>\n`;
                                }
                                html += '</pre>';
                            } else if (diff.code_changed) {
                                html += '<p class="text-muted">代码有变化（内容相同则不显示）</p>';
                            }

                            if (!Object.keys(diff.param_diff || {}).length && !diff.code_changed) {
                                html += '<p class="text-muted">无差异</p>';
                            }
                            diffEl.innerHTML = html;
                        } catch (e2) { App.toast('对比失败: ' + e2.message, 'error'); }
                    }
                };
            } catch (e) {
                overlay.querySelector('#ver-list').innerHTML = '<p class="text-muted">加载失败</p>';
            }
        };

        loadVersions();
        overlay.querySelector('#ver-save').onclick = async () => {
            try {
                const strategies = await App.fetchJSON('/api/strategy/list');
                const s = strategies.find(x => x.name === name);
                await App.fetchJSON('/api/strategy-version/versions/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        strategy_name: name,
                        label: `v${Date.now()}`,
                        description: '',
                        params: s?.params || {},
                        code: s?.code || '',
                    }),
                });
                App.toast('版本已保存', 'success');
                loadVersions();
            } catch (e) { App.toast('保存失败: ' + e.message, 'error'); }
        };
        overlay.querySelector('#ver-close').onclick = () => overlay.remove();
        overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };
    },

    // ── 回测记录 (C1) ──

    async showRecords(name) {
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.innerHTML = `
            <div class="modal" style="max-width:800px;width:95vw" role="dialog" aria-modal="true">
                <h2>回测记录 — ${App.escapeHTML(name)}</h2>
                <div id="rec-list"><div class="skeleton-block skeleton-pulse" style="height:100px"></div></div>
                <div id="rec-detail" style="margin-top:12px"></div>
                <div class="modal-actions"><button class="btn btn-ghost" id="rec-close">关闭</button></div>
            </div>`;
        document.body.appendChild(overlay);

        try {
            const records = await App.fetchJSON(`/api/strategy-version/records?strategy_name=${name}&limit=20`);
            const listEl = overlay.querySelector('#rec-list');
            if (!records.length) {
                listEl.innerHTML = '<p class="text-muted">暂无回测记录。运行回测后可保存结果。</p>';
            } else {
                listEl.innerHTML = `
                    <table style="width:100%;font-size:13px;border-collapse:collapse">
                        <thead><tr style="border-bottom:1px solid var(--border-color)">
                            <th style="text-align:left;padding:6px">标签</th>
                            <th style="text-align:right;padding:6px">总收益</th>
                            <th style="text-align:right;padding:6px">年化</th>
                            <th style="text-align:right;padding:6px">最大回撤</th>
                            <th style="text-align:right;padding:6px">夏普</th>
                            <th style="text-align:right;padding:6px">胜率</th>
                            <th style="text-align:left;padding:6px">时间</th>
                            <th style="text-align:left;padding:6px">操作</th>
                        </tr></thead>
                        <tbody>${records.map(r => `
                            <tr style="border-bottom:1px solid var(--border-color)" data-rec-id="${r.id}">
                                <td style="padding:6px">${App.escapeHTML(r.label || '')}</td>
                                <td style="padding:6px;text-align:right;color:${(r.total_return||0)>=0?'var(--success-color)':'var(--error-color)'}">${(r.total_return??0).toFixed(2)}%</td>
                                <td style="padding:6px;text-align:right">${(r.annual_return??0).toFixed(2)}%</td>
                                <td style="padding:6px;text-align:right;color:var(--error-color)">${(r.max_drawdown??0).toFixed(2)}%</td>
                                <td style="padding:6px;text-align:right">${(r.sharpe_ratio??0).toFixed(2)}</td>
                                <td style="padding:6px;text-align:right">${(r.win_rate??0).toFixed(1)}%</td>
                                <td style="padding:6px">${App.escapeHTML(r.created_at||'')}</td>
                                <td style="padding:6px">
                                    <button class="btn btn-sm" data-rec-action="detail" data-rec-id="${r.id}">详情</button>
                                    <button class="btn btn-sm" data-rec-action="delete" data-rec-id="${r.id}">删除</button>
                                </td>
                            </tr>
                        `).join('')}</tbody>
                    </table>`;

                listEl.onclick = async (e) => {
                    const btn = e.target.closest('[data-rec-action]');
                    if (!btn) return;
                    const recId = btn.dataset.recId;
                    const action = btn.dataset.recAction;

                    if (action === 'detail') {
                        try {
                            const d = await App.fetchJSON(`/api/strategy-version/records/${recId}`);
                            const detailEl = overlay.querySelector('#rec-detail');
                            detailEl.innerHTML = `
                                <h3>${App.escapeHTML(d.label || '')}</h3>
                                <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:8px 0">
                                    <div class="stat-card"><div class="stat-label">总收益</div><div class="stat-value">${(d.total_return??0).toFixed(2)}%</div></div>
                                    <div class="stat-card"><div class="stat-label">年化收益</div><div class="stat-value">${(d.annual_return??0).toFixed(2)}%</div></div>
                                    <div class="stat-card"><div class="stat-label">最大回撤</div><div class="stat-value">${(d.max_drawdown??0).toFixed(2)}%</div></div>
                                    <div class="stat-card"><div class="stat-label">夏普比率</div><div class="stat-value">${(d.sharpe_ratio??0).toFixed(2)}</div></div>
                                    <div class="stat-card"><div class="stat-label">胜率</div><div class="stat-value">${(d.win_rate??0).toFixed(1)}%</div></div>
                                    <div class="stat-card"><div class="stat-label">交易次数</div><div class="stat-value">${d.total_trades||0}</div></div>
                                </div>
                                <p style="font-size:12px;color:var(--text-tertiary)">股票: ${(d.codes||[]).join(', ')} | 区间: ${d.start_date||''} ~ ${d.end_date||''} | 初始资金: ${(d.initial_cash||0).toLocaleString()}</p>`;
                        } catch (e2) { App.toast('加载详情失败', 'error'); }
                    }

                    if (action === 'delete') {
                        const ok = await this._confirm('删除记录', '确定删除这条回测记录？');
                        if (!ok) return;
                        try {
                            await App.fetchJSON(`/api/strategy-version/records/${recId}`, { method: 'DELETE' });
                            App.toast('记录已删除', 'success');
                            this.showRecords(name);
                        } catch (e2) { App.toast('删除失败', 'error'); }
                    }
                };
            }
        } catch (e) {
            overlay.querySelector('#rec-list').innerHTML = '<p class="text-muted">加载失败</p>';
        }

        overlay.querySelector('#rec-close').onclick = () => overlay.remove();
        overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };
    },

    // ── 删除策略（自定义 confirm） ──

    async remove(name) {
        const ok = await this._confirm(`删除策略 "${name}"`, '删除后不可恢复，确定继续？');
        if (!ok) return;
        try {
            await App.fetchJSON(`/api/strategy/${name}`, { method: 'DELETE', label: '删除策略' });
            App.toast('策略已删除', 'success');
            this.load();
        } catch (e) {
            App.toast('删除失败: ' + e.message, 'error');
        }
    },
};
