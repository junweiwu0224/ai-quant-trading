/* ── 股票详情页：研报 / AI 解读 / Alpha 信号 ── */

if (!globalThis.StockDetail) {
    globalThis.StockDetail = {};
}

Object.assign(globalThis.StockDetail, {
    async _loadReports(code, stale) {
        try {
            const data = await App.fetchJSON(`/api/llm/reports/${code}?page_size=10`);
            if (!data || stale()) return;
            this._renderReports(data);
        } catch (e) {
            console.error('加载研报失败:', e);
        }
    },

    _renderReports(data) {
        const container = document.getElementById('sd-reports');
        if (!container) return;

        const hint = document.getElementById('sd-reports-hint');
        if (hint && data.total) {
            hint.textContent = `共 ${data.total} 篇`;
        }

        if (!data.success || !data.reports?.length) {
            container.innerHTML = '<div class="text-muted text-center" style="padding:20px">暂无研报数据</div>';
            return;
        }

        const ratingMap = {
            '买入': 'text-up', '增持': 'text-up', '推荐': 'text-up',
            '中性': 'text-muted', '持有': 'text-muted',
            '减持': 'text-down', '卖出': 'text-down',
        };

        container.innerHTML = `
            <div class="table-wrap">
                <table>
                    <thead><tr><th>日期</th><th>标题</th><th>机构</th><th>评级</th><th>操作</th></tr></thead>
                    <tbody>${data.reports.map((r, i) => {
                        const ratingCls = ratingMap[r.rating] || '';
                        return `<tr>
                            <td>${r.date}</td>
                            <td class="report-title" title="${App.escapeHTML(r.title)}">${App.escapeHTML(r.title)}</td>
                            <td>${App.escapeHTML(r.org)}</td>
                            <td class="${ratingCls}">${App.escapeHTML(r.rating || '--')}</td>
                            <td><button class="btn btn-sm js-analyze-report" data-idx="${i}">AI解读</button></td>
                        </tr>`;
                    }).join('')}</tbody>
                </table>
            </div>
        `;
        container.querySelector('table').addEventListener('click', (e) => {
            const btn = e.target.closest('.js-analyze-report');
            if (!btn) return;
            const idx = parseInt(btn.dataset.idx, 10);
            const r = data.reports[idx];
            if (r) this._analyzeReport(r.title, r.summary);
        });
    },

    async _analyzeReport(title, summary) {
        if (!title) return;
        const container = document.getElementById('sd-reports');
        if (!container) return;

        const analysisDiv = document.getElementById('sd-report-analysis') || document.createElement('div');
        analysisDiv.id = 'sd-report-analysis';
        analysisDiv.className = 'report-analysis';
        analysisDiv.innerHTML = '<div class="skeleton-block skeleton-pulse" style="height:120px;border-radius:8px"></div>';
        container.appendChild(analysisDiv);

        try {
            const data = await App.fetchJSON('/api/llm/reports/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    title: title,
                    content: summary,
                    stock_code: this._currentCode || '',
                    stock_name: document.getElementById('sd-name')?.textContent || '',
                }),
                label: 'AI 解读',
            });

            if (data.success) {
                analysisDiv.innerHTML = `
                    <div class="report-analysis-header">AI 解读</div>
                    <div class="report-analysis-content">${App.escapeHTML(data.analysis).replace(/\n/g, '<br>')}</div>
                `;
            } else {
                analysisDiv.innerHTML = `<div class="text-muted">${App.escapeHTML(data.error || '解读失败')}</div>`;
            }
        } catch (e) {
            analysisDiv.innerHTML = '<div class="text-muted">AI 解读失败</div>';
        }
    },

    async _loadAlphaSignals(code, stale) {
        try {
            const end = new Date();
            const start = new Date();
            start.setMonth(start.getMonth() - 6);
            const fmt = d => d.toISOString().slice(0, 10);
            const data = await App.fetchJSON(
                `/api/alpha/kline-signals?code=${code}&start_date=${fmt(start)}&end_date=${fmt(end)}`
            );
            if (!data || stale()) return;
            this._renderAlphaSignals(data);
        } catch (e) {
            console.error('加载 Alpha 信号失败:', e);
        }
    },

    _renderAlphaSignals(data) {
        const container = document.getElementById('sd-alpha-signals');
        if (!container) return;

        const hint = document.getElementById('sd-alpha-hint');
        const signals = data.signals || [];

        if (signals.length === 0) {
            if (hint) hint.textContent = '';
            container.innerHTML = '<div class="text-muted text-center" style="padding:20px">暂无 Alpha 信号</div>';
            return;
        }

        const buyCount = signals.filter(s => s.type === 'buy').length;
        const sellCount = signals.filter(s => s.type === 'sell').length;
        const lastSignal = signals[signals.length - 1];
        if (hint) hint.textContent = `${signals.length} 个信号 (买${buyCount}/卖${sellCount})`;

        const recent = signals.slice(-20).reverse();
        container.innerHTML = `
            <div class="sd-alpha-summary">
                <span class="sd-alpha-stat">最近信号:
                    <span class="${lastSignal.type === 'buy' ? 'text-up' : 'text-down'}">
                        ${lastSignal.type === 'buy' ? '买入' : '卖出'}
                    </span>
                    ${lastSignal.date} @ ¥${lastSignal.price}
                </span>
            </div>
            <div class="table-wrap">
                <table>
                    <thead><tr><th>日期</th><th>信号</th><th>价格</th></tr></thead>
                    <tbody>${recent.map(s => {
                        const cls = s.type === 'buy' ? 'text-up' : 'text-down';
                        const label = s.type === 'buy' ? '买入' : '卖出';
                        return `<tr>
                            <td>${s.date}</td>
                            <td class="${cls}">${label}</td>
                            <td>¥${s.price}</td>
                        </tr>`;
                    }).join('')}</tbody>
                </table>
            </div>
        `;
    },
});
