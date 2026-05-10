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
                <div class="strategy-card">
                    <h3>${App.escapeHTML(s.label || s.name)}</h3>
                    <span class="strategy-type">${App.escapeHTML(s.type || '自定义')}</span>
                    ${s.builtin ? '<span class="badge badge-info">内置</span>' : ''}
                    ${s.has_override ? '<span class="badge badge-warning">已修改</span>' : ''}
                    ${s.code ? '<span class="badge badge-success">代码</span>' : ''}
                    <p class="strategy-desc">${App.escapeHTML(s.description)}</p>
                    <div class="strategy-params">${this._formatParams(s.params || {})}</div>
                    <div class="strategy-actions">
                        <button class="btn btn-primary btn-sm" onclick="App.quickBacktest('${App.escapeHTML(s.name)}')">快速回测</button>
                        ${s.builtin
                            ? `<button class="btn btn-secondary btn-sm" onclick="Strategy.edit('${App.escapeHTML(s.name)}')">编辑参数</button>`
                            : `<button class="btn btn-secondary btn-sm" onclick="Strategy.edit('${App.escapeHTML(s.name)}')">编辑</button>
                               <button class="btn btn-sm" onclick="Strategy.editCode('${App.escapeHTML(s.name)}')">代码</button>`
                        }
                        ${s.builtin ? '' : `<button class="btn btn-danger btn-sm" onclick="Strategy.remove('${App.escapeHTML(s.name)}')">删除</button>`}
                    </div>
                </div>
            `).join('');
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

    async remove(name) {
        if (!confirm(`确定删除策略 "${name}"？`)) return;
        try {
            await App.fetchJSON(`/api/strategy/${name}`, { method: 'DELETE', label: '删除策略' });
            App.toast('策略已删除', 'success');
            this.load();
        } catch (e) {
            App.toast('删除失败: ' + e.message, 'error');
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
        event.target.value = ''; // 清空 input 允许重复选择同一文件

        try {
            const text = await file.text();
            const data = JSON.parse(text);

            // 显示导入预览
            const strategies = data.custom || (data.strategy ? [data.strategy] : []);
            const names = strategies.map(s => s.name || '未命名').join('、');
            const overwrite = confirm(
                `发现 ${strategies.length} 个策略：${names}\n\n` +
                `点击"确定"覆盖同名策略，点击"取消"跳过同名策略`
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
};
