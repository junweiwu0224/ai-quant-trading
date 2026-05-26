/* ── 情报模块：问财工作台 ── */
(function () {
    'use strict';

    const Intelligence = globalThis.Intelligence || (globalThis.Intelligence = {});
    const state = Intelligence.state || (Intelligence.state = {});

    Object.assign(Intelligence, {
        bindIwencai() {
            if (state.iwencaiBound) return;

            const input = document.getElementById('intel-iwencai-input');
            const btn = document.getElementById('intel-iwencai-btn');
            if (!input || !btn) return;

            state.iwencaiBound = true;

            btn.addEventListener('click', () => this.runIwencai());
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    this.runIwencai();
                }
            });

            if (typeof App.on === 'function') {
                App.on('hotspot:query-iwencai', ({ concept }) => {
                    if (input) input.value = concept;
                    this.runIwencai();
                });
            }
        },

        async runIwencai() {
            const input = document.getElementById('intel-iwencai-input');
            const el = document.getElementById('intel-iwencai-result');
            if (!input || !el) return;

            const query = input.value.trim();
            if (!query) return;

            el.innerHTML = '<div class="text-center" style="padding:16px"><span class="spinner"></span> 正在查询问财...</div>';

            try {
                const resp = await App.fetchJSON('/api/llm/iwencai', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query }),
                    label: '问财查询',
                    timeout: 30000,
                });

                if (!resp.success) {
                    el.innerHTML = `<div class="text-muted text-center">${App.escapeHTML(resp.error || '查询失败')}</div>`;
                    return;
                }

                const data = Array.isArray(resp.data) ? resp.data : [];
                state.iwencaiResult = { query, data };

                if (data.length === 0) {
                    el.innerHTML = '<div class="text-muted text-center">未找到匹配结果</div>';
                    return;
                }

                const cols = Object.keys(data[0]);
                const displayRows = data.slice(0, 30);
                const tableHtml = `<div class="table-wrap"><table>
                    <thead><tr>${cols.map((c) => `<th>${App.escapeHTML(c)}</th>`).join('')}</tr></thead>
                    <tbody>${displayRows.map((row) => `<tr>${cols.map((c) => {
                        const v = row[c];
                        const display = v === null || v === undefined ? '' : String(v).substring(0, 25);
                        if ((c === '代码' || c === 'code' || c === '股票代码') && v) {
                            return `<td><a href="#" class="stock-link" data-code="${App.escapeHTML(String(v))}">${App.escapeHTML(display)}</a></td>`;
                        }
                        return `<td>${App.escapeHTML(display)}</td>`;
                    }).join('')}</tr>`).join('')}</tbody>
                </table></div>`;

                const codes = data.map((r) => r['代码'] || r['code'] || r['股票代码']).filter(Boolean);
                state.iwencaiActionState = {
                    pool: codes.slice(0, 50),
                    watchlistCodes: codes.slice(0, 20),
                    query,
                };

                const actionsHtml = `<div class="iwencai-actions">
                    <span class="text-muted text-xs">共 ${resp.total || data.length} 条，显示前 ${displayRows.length} 条</span>
                    <button class="btn btn-sm" data-intel-action="iwencai-send-screener">发送至选股器</button>
                    <button class="btn btn-sm" data-intel-action="iwencai-analyze">交给 AI 分析</button>
                    <button class="btn btn-sm" data-intel-action="iwencai-add-watchlist">加入自选</button>
                </div>`;

                el.innerHTML = tableHtml + actionsHtml;
            } catch (e) {
                el.innerHTML = `<div class="text-muted text-center">查询失败: ${App.escapeHTML(e.message)}</div>`;
            }
        },

        getLastResult() {
            return state.iwencaiResult;
        },
    });

    if (typeof Intelligence.init === 'function') {
        Intelligence.init();
    }
})();
