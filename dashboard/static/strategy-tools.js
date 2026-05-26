/* ── 策略管理：通用确认 / 克隆 / 删除 ── */

if (!globalThis.Strategy) {
    globalThis.Strategy = {};
}

Object.assign(globalThis.Strategy, {
    _confirm(title, message) {
        return new Promise(resolve => {
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

    async clone(name) {
        try {
            const s = await App.fetchJSON(`/api/strategy/${encodeURIComponent(name)}`);
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

    async remove(name) {
        const ok = await this._confirm(`删除策略 "${name}"`, '删除后不可恢复，确定继续？');
        if (!ok) return;
        try {
            await App.fetchJSON(`/api/strategy/${encodeURIComponent(name)}`, { method: 'DELETE', label: '删除策略' });
            App.toast('策略已删除', 'success');
            this.load();
        } catch (e) {
            App.toast('删除失败: ' + e.message, 'error');
        }
    },
});
