/* ── 策略管理：参数优化 ── */

if (!globalThis.Strategy) {
    globalThis.Strategy = {};
}

Object.assign(globalThis.Strategy, {
    async showOptimize(name) {
        const s = await App.fetchJSON(`/api/strategy/${encodeURIComponent(name)}`).catch(() => null);
        if (!s) { App.toast('策略不存在', 'error'); return; }
        const params = s.params || {};
        const paramKeys = Object.keys(params);

        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.innerHTML = `
            <div class="modal" style="max-width:600px;width:95vw" role="dialog" aria-modal="true">
                <h2>参数优化 — ${App.escapeHTML(s.label || name)}</h2>
                <p style="font-size:13px;color:var(--text-secondary);margin-bottom:12px">设置每个参数的搜索范围（逗号分隔），系统将遍历所有组合找到最优解。</p>
                <div id="opt-ranges">
                    ${paramKeys.map(k => `<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
                        <label style="min-width:100px;font-size:13px">${App.escapeHTML(k)}</label>
                        <input type="text" data-opt-key="${App.escapeHTML(k)}" value="${App.escapeHTML(String(params[k] ?? ''))}" placeholder="如: 3,5,10,15"
                            style="flex:1;padding:6px 8px;border:1px solid var(--border-color);border-radius:6px;font-size:13px">
                    </div>`).join('')}
                </div>
                <div style="display:flex;gap:8px;margin-top:12px">
                    <div style="flex:1">
                        <label style="font-size:13px">优化目标</label>
                        <select id="opt-metric" style="width:100%;padding:6px;border:1px solid var(--border-color);border-radius:6px">
                            <option value="sharpe_ratio">夏普比率</option>
                            <option value="total_return">总收益</option>
                            <option value="annual_return">年化收益</option>
                            <option value="win_rate">胜率</option>
                            <option value="max_drawdown">最大回撤（越小越好）</option>
                        </select>
                    </div>
                    <div style="flex:1">
                        <label style="font-size:13px">股票代码</label>
                        <input type="text" id="opt-codes" value="000001" placeholder="000001,000002"
                            style="width:100%;padding:6px;border:1px solid var(--border-color);border-radius:6px;font-size:13px">
                    </div>
                </div>
                <div id="opt-result" style="margin-top:16px"></div>
                <div class="modal-actions">
                    <button class="btn btn-ghost" id="opt-close">关闭</button>
                    <button class="btn btn-primary" id="opt-run">开始优化</button>
                </div>
            </div>`;
        document.body.appendChild(overlay);

        overlay.querySelector('#opt-close').onclick = () => overlay.remove();
        overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };

        overlay.querySelector('#opt-run').onclick = async () => {
            const runBtn = overlay.querySelector('#opt-run');
            runBtn.disabled = true;
            runBtn.textContent = '优化中...';

            const paramRanges = {};
            for (const k of paramKeys) {
                const input = [...overlay.querySelectorAll('[data-opt-key]')]
                    .find((el) => el.dataset.optKey === k);
                const vals = input.value.split(',').map(v => parseFloat(v.trim())).filter(v => !isNaN(v));
                if (vals.length) paramRanges[k] = vals;
            }

            const codes = overlay.querySelector('#opt-codes').value.split(',').map(c => c.trim()).filter(Boolean);
            const metric = overlay.querySelector('#opt-metric').value;

            try {
                const data = await App.fetchJSON('/api/strategy/optimize', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        strategy: name,
                        codes: codes.length ? codes : ['000001'],
                        param_ranges: paramRanges,
                        metric,
                        top_n: 5,
                    }),
                });

                const resultEl = overlay.querySelector('#opt-result');
                if (!data.best?.length) {
                    resultEl.innerHTML = '<p class="text-muted">无有效结果</p>';
                } else {
                    const metricLabels = { sharpe_ratio: '夏普', total_return: '总收益', annual_return: '年化', win_rate: '胜率', max_drawdown: '最大回撤' };
                    const safeMetricLabel = App.escapeHTML(metricLabels[metric] || metric);
                    const safeBestCount = Number.isFinite(Number(data.best.length)) ? data.best.length : 0;
                    const safeTotalCombos = Number.isFinite(Number(data.total_combos)) ? data.total_combos : 0;
                    let html = `<h3>最优 Top ${safeBestCount}（共 ${safeTotalCombos} 种组合）</h3>`;
                    html += '<table style="width:100%;font-size:13px;border-collapse:collapse;margin-top:8px">';
                    html += '<thead><tr style="border-bottom:1px solid var(--border-color)"><th style="text-align:left;padding:6px">排名</th>';
                    for (const k of paramKeys) html += `<th style="text-align:right;padding:6px">${App.escapeHTML(k)}</th>`;
                    html += `<th style="text-align:right;padding:6px">${safeMetricLabel}</th>`;
                    html += '<th style="text-align:right;padding:6px">总收益</th><th style="text-align:right;padding:6px">夏普</th>';
                    html += '</tr></thead><tbody>';
                    data.best.forEach((r, i) => {
                        html += `<tr style="border-bottom:1px solid var(--border-color)">
                            <td style="padding:6px">#${i+1}</td>`;
                        for (const k of paramKeys) html += `<td style="padding:6px;text-align:right">${App.escapeHTML(String(r.params[k] ?? '--'))}</td>`;
                        html += `<td style="padding:6px;text-align:right;font-weight:700;color:var(--success-color)">${(r[metric]??0).toFixed(2)}${metric.includes('return')||metric==='win_rate'?'%':''}</td>`;
                        html += `<td style="padding:6px;text-align:right">${(r.total_return??0).toFixed(2)}%</td>`;
                        html += `<td style="padding:6px;text-align:right">${(r.sharpe_ratio??0).toFixed(2)}</td>`;
                        html += '</tr>';
                    });
                    html += '</tbody></table>';
                    resultEl.innerHTML = html;
                }
            } catch (e) {
                overlay.querySelector('#opt-result').innerHTML = `<p style="color:var(--error-color)">优化失败: ${App.escapeHTML(e.message)}</p>`;
            }
            runBtn.disabled = false;
            runBtn.textContent = '开始优化';
        };
    },
});
