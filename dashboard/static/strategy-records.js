/* ── 策略管理：回测记录 ── */

if (!globalThis.Strategy) {
    globalThis.Strategy = {};
}

Object.assign(globalThis.Strategy, {
    async showRecords(name) {
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.innerHTML = `
            <div class="modal" style="max-width:800px;width:95vw" role="dialog" aria-modal="true">
                <h2>回测记录 — ${App.escapeHTML(name)}</h2>
                <div id="rec-list"><div class="skeleton-block skeleton-pulse" style="height:100px"></div></div>
                <div id="rec-compare" style="margin-top:12px"></div>
                <div id="rec-detail" style="margin-top:12px"></div>
                <div class="modal-actions"><button class="btn btn-ghost" id="rec-close">关闭</button></div>
            </div>`;
        document.body.appendChild(overlay);

        try {
            const records = await App.fetchJSON(`/api/strategy-version/records?strategy_name=${encodeURIComponent(name)}&limit=20`);
            const listEl = overlay.querySelector('#rec-list');
            if (!records.length) {
                listEl.innerHTML = '<p class="text-muted">暂无回测记录。运行回测后可保存结果。</p>';
            } else {
                listEl.innerHTML = `
                    <div style="margin-bottom:8px"><button class="btn btn-sm" id="rec-compare-btn" disabled>对比选中 (0)</button></div>
                    <table style="width:100%;font-size:13px;border-collapse:collapse">
                        <thead><tr style="border-bottom:1px solid var(--border-color)">
                            <th style="padding:6px;width:30px"><input type="checkbox" id="rec-select-all"></th>
                            <th style="text-align:left;padding:6px">标签</th>
                            <th style="text-align:right;padding:6px">总收益</th>
                            <th style="text-align:right;padding:6px">年化</th>
                            <th style="text-align:right;padding:6px">最大回撤</th>
                            <th style="text-align:right;padding:6px">夏普</th>
                            <th style="text-align:right;padding:6px">胜率</th>
                            <th style="text-align:left;padding:6px">时间</th>
                            <th style="text-align:left;padding:6px">操作</th>
                        </tr></thead>
                        <tbody>${records.map(r => {
                            const recordId = Number.parseInt(r.id, 10);
                            if (!Number.isFinite(recordId)) {
                                return '';
                            }
                            return `
                            <tr style="border-bottom:1px solid var(--border-color)">
                                <td style="padding:6px"><input type="checkbox" class="rec-cb" data-rec-id="${recordId}"></td>
                                <td style="padding:6px">${App.escapeHTML(r.label || '')}</td>
                                <td style="padding:6px;text-align:right;color:${(r.total_return||0)>=0?'var(--success-color)':'var(--error-color)'}">${(r.total_return??0).toFixed(2)}%</td>
                                <td style="padding:6px;text-align:right">${(r.annual_return??0).toFixed(2)}%</td>
                                <td style="padding:6px;text-align:right;color:var(--error-color)">${(r.max_drawdown??0).toFixed(2)}%</td>
                                <td style="padding:6px;text-align:right">${(r.sharpe_ratio??0).toFixed(2)}</td>
                                <td style="padding:6px;text-align:right">${(r.win_rate??0).toFixed(1)}%</td>
                                <td style="padding:6px">${App.escapeHTML(r.created_at||'')}</td>
                                <td style="padding:6px">
                                    <button class="btn btn-sm" data-rec-action="detail" data-rec-id="${recordId}">详情</button>
                                    <button class="btn btn-sm" data-rec-action="delete" data-rec-id="${recordId}">删除</button>
                                </td>
                            </tr>`;
                        }).join('')}</tbody>
                    </table>`;

                const compareBtn = overlay.querySelector('#rec-compare-btn');
                const selectAll = overlay.querySelector('#rec-select-all');
                const getSelected = () => [...overlay.querySelectorAll('.rec-cb:checked')]
                    .map(cb => Number.parseInt(cb.dataset.recId, 10))
                    .filter(Number.isFinite);

                selectAll.onchange = () => {
                    overlay.querySelectorAll('.rec-cb').forEach(cb => cb.checked = selectAll.checked);
                    compareBtn.disabled = getSelected().length < 2;
                    compareBtn.textContent = `对比选中 (${getSelected().length})`;
                };
                listEl.addEventListener('change', (e) => {
                    if (e.target.classList.contains('rec-cb')) {
                        compareBtn.disabled = getSelected().length < 2;
                        compareBtn.textContent = `对比选中 (${getSelected().length})`;
                    }
                });
                compareBtn.onclick = async () => {
                    const ids = getSelected();
                    if (ids.length < 2) return;
                    try {
                        const data = await App.fetchJSON('/api/strategy-version/records/compare', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(ids),
                        });
                        const cmpEl = overlay.querySelector('#rec-compare');
                        const metrics = ['total_return', 'annual_return', 'max_drawdown', 'sharpe_ratio', 'win_rate', 'total_trades'];
                        const labels = { total_return: '总收益', annual_return: '年化', max_drawdown: '最大回撤', sharpe_ratio: '夏普', win_rate: '胜率', total_trades: '交易次数' };
                        let html = '<h3>记录对比</h3><table style="width:100%;font-size:13px;border-collapse:collapse"><thead><tr style="border-bottom:1px solid var(--border-color)"><th style="text-align:left;padding:6px">指标</th>';
                        for (const r of data) html += `<th style="text-align:right;padding:6px">${App.escapeHTML(r.label || 'R'+r.id)}</th>`;
                        html += '</tr></thead><tbody>';
                        for (const m of metrics) {
                            const vals = data.map(r => r[m] ?? 0);
                            const best = m === 'max_drawdown' ? Math.min(...vals) : Math.max(...vals);
                            html += `<tr style="border-bottom:1px solid var(--border-color)"><td style="padding:6px">${labels[m]}</td>`;
                            for (const r of data) {
                                const v = r[m] ?? 0;
                                const isBest = v === best;
                                const fmt = m === 'total_trades' ? v.toFixed(0) : v.toFixed(2) + (m !== 'sharpe_ratio' ? '%' : '');
                                html += `<td style="padding:6px;text-align:right;${isBest ? 'font-weight:700;color:var(--success-color)' : ''}">${fmt}</td>`;
                            }
                            html += '</tr>';
                        }
                        html += '</tbody></table>';
                        cmpEl.innerHTML = html;
                    } catch (e2) { App.toast('对比失败', 'error'); }
                };

                listEl.onclick = async (e) => {
                    const btn = e.target.closest('[data-rec-action]');
                    if (!btn) return;
                    const recId = Number.parseInt(btn.dataset.recId, 10);
                    const action = btn.dataset.recAction;
                    if (!Number.isFinite(recId)) return;

                    if (action === 'detail') {
                        try {
                            const d = await App.fetchJSON(`/api/strategy-version/records/${encodeURIComponent(String(recId))}`);
                            const detailEl = overlay.querySelector('#rec-detail');
                            const totalTrades = Number(d.total_trades);
                            const safeTotalTrades = Number.isFinite(totalTrades) ? totalTrades : 0;
                            const safeCodes = App.escapeHTML((d.codes || []).join(', '));
                            const safeStartDate = App.escapeHTML(d.start_date || '');
                            const safeEndDate = App.escapeHTML(d.end_date || '');
                            const initialCash = Number(d.initial_cash);
                            const safeInitialCash = Number.isFinite(initialCash) ? initialCash.toLocaleString() : '--';
                            detailEl.innerHTML = `
                                <h3>${App.escapeHTML(d.label || '')}</h3>
                                <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:8px 0">
                                    <div class="stat-card"><div class="stat-label">总收益</div><div class="stat-value">${(d.total_return??0).toFixed(2)}%</div></div>
                                    <div class="stat-card"><div class="stat-label">年化收益</div><div class="stat-value">${(d.annual_return??0).toFixed(2)}%</div></div>
                                    <div class="stat-card"><div class="stat-label">最大回撤</div><div class="stat-value">${(d.max_drawdown??0).toFixed(2)}%</div></div>
                                    <div class="stat-card"><div class="stat-label">夏普比率</div><div class="stat-value">${(d.sharpe_ratio??0).toFixed(2)}</div></div>
                                    <div class="stat-card"><div class="stat-label">胜率</div><div class="stat-value">${(d.win_rate??0).toFixed(1)}%</div></div>
                                    <div class="stat-card"><div class="stat-label">交易次数</div><div class="stat-value">${safeTotalTrades}</div></div>
                                </div>
                                <p style="font-size:12px;color:var(--text-tertiary)">股票: ${safeCodes} | 区间: ${safeStartDate} ~ ${safeEndDate} | 初始资金: ${safeInitialCash}</p>`;
                        } catch (e2) { App.toast('加载详情失败', 'error'); }
                    }

                    if (action === 'delete') {
                        const ok = await this._confirm('删除记录', '确定删除这条回测记录？');
                        if (!ok) return;
                        try {
                            await App.fetchJSON(`/api/strategy-version/records/${encodeURIComponent(String(recId))}`, { method: 'DELETE' });
                            App.toast('记录已删除', 'success');
                            if (overlay.isConnected) {
                                overlay.remove();
                                this.showRecords(name);
                            }
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
});
