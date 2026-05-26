/* ── 策略管理：版本管理 ── */

if (!globalThis.Strategy) {
    globalThis.Strategy = {};
}

Object.assign(globalThis.Strategy, {
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
                const versions = await App.fetchJSON(`/api/strategy-version/versions/${encodeURIComponent(name)}`);
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
                        <tbody>${versions.map(v => {
                            const versionNumber = Number.parseInt(v.version, 10);
                            if (!Number.isFinite(versionNumber)) {
                                return '';
                            }
                            return `
                            <tr style="border-bottom:1px solid var(--border-color)">
                                <td style="padding:6px">v${versionNumber}${v.is_current ? ' <span class="badge badge-success">当前</span>' : ''}</td>
                                <td style="padding:6px">${App.escapeHTML(v.label || '')}</td>
                                <td style="padding:6px">${App.escapeHTML(v.created_at || '')}</td>
                                <td style="padding:6px">
                                    ${!v.is_current ? `<button class="btn btn-sm" data-ver-action="rollback" data-ver="${versionNumber}">回滚</button>` : ''}
                                    <button class="btn btn-sm" data-ver-action="diff" data-ver="${versionNumber}">对比</button>
                                </td>
                            </tr>`;
                        }).join('')}</tbody>
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
                            const diff = await App.fetchJSON(`/api/strategy-version/versions/${encodeURIComponent(name)}/diff?v1=${encodeURIComponent(String(v1))}&v2=${encodeURIComponent(String(v2))}`);
                            const diffEl = overlay.querySelector('#ver-diff');
                            let html = `<h3 style="margin-bottom:8px">v${v1} vs v${v2}</h3>`;

                            if (Object.keys(diff.param_diff || {}).length) {
                                html += '<h4>参数差异</h4><table style="width:100%;font-size:13px;border-collapse:collapse">';
                                for (const [k, vals] of Object.entries(diff.param_diff)) {
                                    html += `<tr><td style="padding:4px 8px">${App.escapeHTML(k)}</td><td style="padding:4px 8px;color:var(--error-color)">${App.escapeHTML(String(vals[`v${v1}`] ?? '-'))}</td><td style="padding:4px 8px">→</td><td style="padding:4px 8px;color:var(--success-color)">${App.escapeHTML(String(vals[`v${v2}`] ?? '-'))}</td></tr>`;
                                }
                                html += '</table>';
                            }

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
                const s = await App.fetchJSON(`/api/strategy/${encodeURIComponent(name)}`);
                const result = await App.fetchJSON('/api/strategy-version/versions/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        strategy_name: name,
                        label: '',
                        description: '',
                        params: s?.params || {},
                        code: s?.code || '',
                    }),
                });
                App.toast(`版本 v${result.version} 已保存`, 'success');
                loadVersions();
            } catch (e) { App.toast('保存失败: ' + e.message, 'error'); }
        };
        overlay.querySelector('#ver-close').onclick = () => overlay.remove();
        overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };
    },
});
