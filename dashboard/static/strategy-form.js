/* ── 策略管理：新增 / 编辑 / 导入导出 ── */

if (!globalThis.Strategy) {
    globalThis.Strategy = {};
}

Object.assign(globalThis.Strategy, {
    showCreateModal() {
        this._showModal({
            title: '新增策略',
            name: '', label: '', description: '', params: {},
            isNew: true, builtinName: null,
        });
    },

    async edit(name) {
        try {
            const s = await App.fetchJSON(`/api/strategy/${encodeURIComponent(name)}`);
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

    _showModal({ title, name, label, description, params, isNew, builtinName }) {
        this._removeExistingModal();

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
                    ${builtinName ? '<button class="btn btn-ghost" id="modal-st-reset" style="margin-right:auto">重置默认</button>' : ''}
                    <button class="btn btn-ghost" id="modal-st-cancel">取消</button>
                    <button class="btn btn-primary" id="modal-st-save">保存</button>
                </div>
            </div>
        `;

        document.body.appendChild(overlay);
        overlay.__strategyCleanup = () => overlay.remove();

        const firstInput = overlay.querySelector('input, textarea, select');
        if (firstInput) setTimeout(() => firstInput.focus(), 50);

        const closeOverlay = () => {
            overlay.remove();
            document.removeEventListener('keydown', onEscape);
        };
        overlay.__strategyCleanup = closeOverlay;
        const onEscape = (e) => {
            if (e.key === 'Escape') {
                closeOverlay();
            }
        };

        overlay.querySelector('#modal-st-cancel').addEventListener('click', closeOverlay);
        overlay.addEventListener('click', (e) => { if (e.target === overlay) closeOverlay(); });
        document.addEventListener('keydown', onEscape);

        if (builtinName) {
            overlay.querySelector('#modal-st-reset')?.addEventListener('click', async () => {
                try {
                    await App.fetchJSON(`/api/strategy/${encodeURIComponent(builtinName)}/reset`, { method: 'POST' });
                    App.toast('参数已重置为默认值', 'success');
                    closeOverlay();
                    this.load();
                } catch (e) { App.toast('重置失败: ' + e.message, 'error'); }
            });
        }

        const formSaveBtn = overlay.querySelector('#modal-st-save');
        const resetFormSaveButton = () => {
            formSaveBtn.disabled = false;
            formSaveBtn.textContent = '保存';
        };

        formSaveBtn.addEventListener('click', async () => {
            if (formSaveBtn.disabled) return;
            const parsedParams = paramDefs
                ? this._collectStructuredParams(overlay, paramDefs)
                : this._collectJsonParams(overlay);
            if (parsedParams === null) return;

            formSaveBtn.disabled = true;
            formSaveBtn.textContent = '保存中...';

            let saved = false;
            if (isNew) {
                const newName = overlay.querySelector('#modal-st-name')?.value.trim();
                const newLabel = overlay.querySelector('#modal-st-label')?.value.trim();
                const newDesc = overlay.querySelector('#modal-st-desc')?.value.trim();
                if (!newName) { App.toast('策略名称不能为空', 'error'); resetFormSaveButton(); return; }
                if (!/^[a-zA-Z_]\w*$/.test(newName)) { App.toast('策略名只能包含字母、数字和下划线', 'error'); resetFormSaveButton(); return; }
                if (!newLabel) { App.toast('显示名称不能为空', 'error'); resetFormSaveButton(); return; }
                saved = await this._create(newName, newLabel, newDesc, parsedParams);
            } else if (builtinName) {
                saved = await this._update(name, null, null, parsedParams);
            } else {
                const newLabel = overlay.querySelector('#modal-st-label')?.value.trim();
                const newDesc = overlay.querySelector('#modal-st-desc')?.value.trim();
                if (!newLabel) { App.toast('显示名称不能为空', 'error'); resetFormSaveButton(); return; }
                saved = await this._update(name, newLabel, newDesc, parsedParams);
            }
            if (saved) {
                closeOverlay();
                return;
            }
            resetFormSaveButton();
        });
    },

    _buildStructuredParams(defs, current) {
        return `<div class="param-fields" style="margin-bottom:12px">
            <label style="font-weight:600;margin-bottom:8px;display:block">策略参数</label>
            ${defs.map(d => {
                const rawVal = current[d.key];
                const parsedVal = d.type === 'int' ? parseInt(rawVal, 10) : parseFloat(rawVal);
                const normalizedVal = Number.isFinite(parsedVal) ? parsedVal : d.default;
                const val = App.escapeHTML(String(normalizedVal));
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
            return true;
        } catch (e) {
            App.toast('创建失败: ' + e.message, 'error');
            return false;
        }
    },

    async _update(name, label, description, params) {
        try {
            const body = {};
            if (label !== null) body.label = label;
            if (description !== null) body.description = description;
            if (params !== null) body.params = params;
            await App.fetchJSON(`/api/strategy/${encodeURIComponent(name)}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
                label: '更新策略',
            });
            App.toast('策略已更新', 'success');
            this.load();
            return true;
        } catch (e) {
            App.toast('更新失败: ' + e.message, 'error');
            return false;
        }
    },

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
});
