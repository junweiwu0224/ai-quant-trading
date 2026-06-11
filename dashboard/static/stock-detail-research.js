/* ── 股票详情页：研报 / AI 解读 / Alpha 信号 ── */

if (!globalThis.StockDetail) {
    globalThis.StockDetail = {};
}

Object.assign(globalThis.StockDetail, {
    _stockResearchDateKey(value) {
        const match = String(value || '').match(/\d{4}-\d{2}-\d{2}/);
        return match ? match[0] : '';
    },

    async _loadReports(code, stale) {
        try {
            const data = await App.fetchJSON(`/api/llm/reports/${code}?page_size=10`);
            if (stale()) return;
            if (!data) {
                this._setWorkbenchEvents('research_report', [], {
                    type: 'research_report',
                    title: '研报数据暂缺',
                    source: 'llm_reports',
                    source_label: '研报',
                    status: 'missing',
                    missing_reason: '研报接口未返回数据',
                });
                return;
            }
            this._renderReports(data);
        } catch (e) {
            console.error('加载研报失败:', e);
            if (stale()) return;
            this._setWorkbenchEvents('research_report', [], {
                type: 'research_report',
                title: '研报加载失败',
                source: 'llm_reports',
                source_label: '研报',
                status: 'missing',
                missing_reason: '研报数据加载失败',
            });
        }
    },

    _renderReports(data) {
        const reports = Array.isArray(data?.reports) ? data.reports : [];
        if (!data?.success || !reports.length) {
            this._setWorkbenchEvents('research_report', [], {
                type: 'research_report',
                title: '研报暂缺',
                source: 'llm_reports',
                source_label: '研报',
                status: 'missing',
                missing_reason: data?.error || data?.message || '暂无研报数据',
            });
        } else {
            this._setWorkbenchEvents('research_report', reports.map((r) => ({
                type: 'research_report',
                status: 'ready',
                title: r.title || '研究报告',
                detail: [
                    r.org ? `机构：${r.org}` : '',
                    r.rating ? `评级：${r.rating}` : '',
                    r.summary || '',
                ].filter(Boolean).join(' · '),
                at: r.date || r.publish_date || '',
                date_key: this._stockResearchDateKey(r.date || r.publish_date),
                source: 'llm_reports',
                source_label: r.org || '研报',
                direction: r.rating || '',
                value: r.rating || null,
                link_url: r.url || r.link_url || '',
                raw: r,
            })), {
                type: 'research_report',
                source: 'llm_reports',
                source_label: '研报',
            });
        }

        const container = document.getElementById('sd-reports');
        if (!container) return;

        const hint = document.getElementById('sd-reports-hint');
        if (hint && data?.total) {
            hint.textContent = `共 ${data.total} 篇`;
        }

        if (!data?.success || !reports.length) {
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
                    <tbody>${reports.map((r, i) => {
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
            const r = reports[idx];
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
            if (stale()) return;
            if (!data) {
                this._setWorkbenchEvents('alpha_signal', [], {
                    type: 'alpha_signal',
                    title: 'Alpha 信号暂缺',
                    source: 'alpha_signal',
                    source_label: 'Alpha 信号',
                    status: 'missing',
                    missing_reason: 'Alpha 信号接口未返回数据',
                });
                return;
            }
            this._renderAlphaSignals(data);
        } catch (e) {
            console.error('加载 Alpha 信号失败:', e);
            if (stale()) return;
            this._setWorkbenchEvents('alpha_signal', [], {
                type: 'alpha_signal',
                title: 'Alpha 信号加载失败',
                source: 'alpha_signal',
                source_label: 'Alpha 信号',
                status: 'missing',
                missing_reason: 'Alpha 信号数据加载失败',
            });
        }
    },

    _renderAlphaSignals(data) {
        const signals = Array.isArray(data?.signals) ? data.signals : [];
        const recent = signals.slice(-20).reverse();
        if (signals.length === 0) {
            this._setWorkbenchEvents('alpha_signal', [], {
                type: 'alpha_signal',
                title: 'Alpha 信号暂缺',
                source: 'alpha_signal',
                source_label: 'Alpha 信号',
                status: 'missing',
                missing_reason: data?.error || data?.message || '暂无 Alpha 信号',
            });
        } else {
            this._setWorkbenchEvents('alpha_signal', recent.map((s) => {
                const price = Number(s.price);
                const label = s.type === 'buy' ? '买入' : s.type === 'sell' ? '卖出' : (s.type || '信号');
                return {
                    type: 'alpha_signal',
                    status: 'ready',
                    title: `Alpha ${label}`,
                    detail: [
                        Number.isFinite(price) ? `${label} @ ¥${price}` : label,
                        s.factor || s.strategy || '',
                    ].filter(Boolean).join(' · '),
                    at: s.date || s.time || '',
                    date_key: this._stockResearchDateKey(s.date || s.time),
                    source: 'alpha_signal',
                    source_label: s.factor || s.strategy || 'Alpha 信号',
                    direction: s.type || '',
                    value: Number.isFinite(price) ? price : null,
                    link_url: s.url || s.link_url || '',
                    raw: s,
                };
            }), {
                type: 'alpha_signal',
                source: 'alpha_signal',
                source_label: 'Alpha 信号',
            });
        }

        const container = document.getElementById('sd-alpha-signals');
        if (!container) return;

        const hint = document.getElementById('sd-alpha-hint');

        if (signals.length === 0) {
            if (hint) hint.textContent = '';
            container.innerHTML = '<div class="text-muted text-center" style="padding:20px">暂无 Alpha 信号</div>';
            return;
        }

        const buyCount = signals.filter(s => s.type === 'buy').length;
        const sellCount = signals.filter(s => s.type === 'sell').length;
        const lastSignal = signals[signals.length - 1];
        if (hint) hint.textContent = `${signals.length} 个信号 (买${buyCount}/卖${sellCount})`;

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
