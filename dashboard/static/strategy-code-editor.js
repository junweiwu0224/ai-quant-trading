/* ── 策略管理：代码编辑器 ── */

if (!globalThis.Strategy) {
    globalThis.Strategy = {};
}

Object.assign(globalThis.Strategy, {
    showCodeEditor() {
        this._showCodeModal({ name: '', code: '', isNew: true });
    },

    async editCode(name) {
        try {
            const s = await App.fetchJSON(`/api/strategy/${encodeURIComponent(name)}`);
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
        this._removeExistingModal();

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
                    <div style="position:relative;display:flex;border:1px solid var(--border-color);border-radius:8px;background:var(--bg-secondary);overflow:hidden">
                        <div id="modal-code-lines" style="padding:12px 8px;background:var(--bg-tertiary,rgba(0,0,0,0.05));font-family:monospace;font-size:13px;line-height:1.5;text-align:right;color:var(--text-tertiary);user-select:none;min-width:36px;white-space:pre"></div>
                        <textarea id="modal-code-editor" rows="20" style="flex:1;font-family:monospace;font-size:13px;line-height:1.5;padding:12px;border:none;background:transparent;resize:vertical;tab-size:4;outline:none">${App.escapeHTML(code || '')}</textarea>
                    </div>
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
        overlay.__strategyCleanup = () => overlay.remove();

        // Focus first interactive element
        const firstInput = overlay.querySelector('input, textarea');
        if (firstInput) setTimeout(() => firstInput.focus(), 50);

        const editor = overlay.querySelector('#modal-code-editor');
        const statusEl = overlay.querySelector('#modal-code-status');
        const linesEl = overlay.querySelector('#modal-code-lines');

        // 行号更新
        const updateLines = () => {
            const count = editor.value.split('\n').length;
            linesEl.textContent = Array.from({length: count}, (_, i) => i + 1).join('\n');
        };
        updateLines();
        editor.addEventListener('input', updateLines);
        editor.addEventListener('scroll', () => { linesEl.scrollTop = editor.scrollTop; });

        // Tab 键支持
        editor.addEventListener('keydown', (e) => {
            if (e.key === 'Tab') {
                e.preventDefault();
                const start = editor.selectionStart;
                const end = editor.selectionEnd;
                editor.value = editor.value.substring(0, start) + '    ' + editor.value.substring(end);
                editor.selectionStart = editor.selectionEnd = start + 4;
                updateLines();
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

        // 保存（防重复提交）
        const saveBtn = overlay.querySelector('#modal-code-save');
        const resetSaveButton = () => {
            saveBtn.disabled = false;
            saveBtn.textContent = '保存';
        };
        saveBtn.addEventListener('click', async () => {
            if (saveBtn.disabled) return;
            const codeText = editor.value.trim();
            if (!codeText) { App.toast('代码不能为空', 'error'); return; }

            if (isNew) {
                const newName = overlay.querySelector('#modal-code-name')?.value.trim();
                if (!newName) { App.toast('策略名称不能为空', 'error'); return; }
                if (!/^[a-zA-Z_]\w*$/.test(newName)) { App.toast('策略名只能包含字母、数字和下划线', 'error'); return; }

                saveBtn.disabled = true;
                saveBtn.textContent = '保存中...';

                try {
                    const vData = await App.fetchJSON('/api/strategy/validate-code', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ code: codeText }),
                        label: '代码验证',
                    });
                    if (!vData.valid) {
                        App.toast('代码验证失败: ' + vData.error, 'error');
                        resetSaveButton();
                        return;
                    }
                } catch (e) {
                    App.toast('代码验证请求失败: ' + e.message, 'error');
                    resetSaveButton();
                    return;
                }

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
                    resetSaveButton();
                }
            } else {
                saveBtn.disabled = true;
                saveBtn.textContent = '保存中...';

                try {
                    await App.fetchJSON(`/api/strategy/${encodeURIComponent(name)}`, {
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
                    resetSaveButton();
                }
            }
        });
    },
});