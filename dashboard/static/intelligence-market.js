/* ── 情报模块：市场数据链路 ── */
(function () {
    'use strict';

    const Intelligence = globalThis.Intelligence || (globalThis.Intelligence = {});

    Object.assign(Intelligence, {
        async loadSentiment() {
            const el = document.getElementById('intel-sentiment');
            if (!el) return;

            try {
                const data = await App.fetchJSON('/api/market/radar', { silent: true });
                if (!data.success) {
                    el.innerHTML = '<div class="text-muted text-center">加载失败</div>';
                    return;
                }

                const gainers = (data.top_gainers || []).length;
                const losers = (data.top_losers || []).length;
                const total = gainers + losers;
                const upPct = total > 0 ? ((gainers / total) * 100).toFixed(0) : '--';

                el.innerHTML = `
                    <div class="intel-sent-stat">
                        <span class="label">上涨</span>
                        <span class="value text-up">${gainers}</span>
                    </div>
                    <div class="intel-sent-stat">
                        <span class="label">下跌</span>
                        <span class="value text-down">${losers}</span>
                    </div>
                    <div class="intel-sent-stat">
                        <span class="label">涨跌比</span>
                        <span class="value">${upPct}%</span>
                    </div>
                `;
            } catch {
                el.innerHTML = '<div class="text-muted text-center">加载失败</div>';
            }
        },

        async loadNews() {
            const el = document.getElementById('intel-news-list');
            const countEl = document.getElementById('intel-news-count');
            if (!el) return;

            try {
                const data = await App.fetchJSON('/api/market/news', { silent: true });
                if (!data.success) {
                    el.innerHTML = '<div class="text-muted text-center">加载失败</div>';
                    return;
                }

                const news = data.news || [];
                if (countEl) countEl.textContent = news.length;
                const timestampEl = document.getElementById('intel-timestamp');
                if (timestampEl && data.timestamp) timestampEl.textContent = data.timestamp;

                if (news.length === 0) {
                    el.innerHTML = '<div class="text-muted text-center">暂无新闻</div>';
                    return;
                }

                el.innerHTML = news.map((n) => {
                    const sentVal = n.sentiment || 0;
                    const sentCls = sentVal > 0.2 ? 'tag-up' : sentVal < -0.2 ? 'tag-down' : '';
                    const icon = sentVal > 0.2 ? '▲' : sentVal < -0.2 ? '▼' : '●';
                    const iconCls = sentVal > 0.2 ? 'text-up' : sentVal < -0.2 ? 'text-down' : 'text-muted';
                    const tags = (n.stocks || []).slice(0, 3).map((s) => (
                        `<span class="intel-news-tag ${sentCls}" data-intel-action="open-news-stock" data-code="${App.escapeHTML(s.code || '')}">${App.escapeHTML(s.name || s.code || '')}</span>`
                    )).join('');
                    return `<div class="intel-news-item">
                        <span class="intel-news-icon ${iconCls}">${icon}</span>
                        <div class="intel-news-body">
                            <div class="intel-news-title">${App.escapeHTML(n.title || '')}</div>
                            <div class="intel-news-meta">
                                <span>${App.escapeHTML(n.time || '')}</span>
                                ${tags}
                            </div>
                        </div>
                    </div>`;
                }).join('');

                const overall = data.overall_sentiment || 0;
                const sentLabel = overall >= 0.1 ? '偏多' : overall <= -0.1 ? '偏空' : '中性';
                const sentCls = overall >= 0.1 ? 'text-up' : overall <= -0.1 ? 'text-down' : 'text-muted';
                const sentHeader = document.querySelector('.intel-sentiment-card h3');
                if (sentHeader) {
                    sentHeader.innerHTML = `市场情绪 <span class="${sentCls}" style="font-size:var(--font-size-xs);font-weight:400">${sentLabel} (${overall.toFixed(2)})</span>`;
                }
            } catch {
                el.innerHTML = '<div class="text-muted text-center">加载失败</div>';
            }
        },

        async loadHeatmap() {
            const el = document.getElementById('intel-heatmap');
            if (!el) return;

            try {
                const data = await App.fetchJSON('/api/market/heatmap', { silent: true });
                if (!data.success) {
                    el.innerHTML = '<div class="text-muted text-center">加载失败</div>';
                    return;
                }

                const sectors = (data.sectors || []).filter((s) => s.total_mv > 0);
                sectors.sort((a, b) => b.total_mv - a.total_mv);

                const totalMV = sectors.reduce((sum, s) => sum + s.total_mv, 0);
                const containerWidth = el.offsetWidth || 400;
                const rowHeight = 48;
                const gap = 2;
                let html = '';
                let currentRow = [];
                let currentRowMV = 0;
                const rowTargetMV = totalMV / Math.max(1, Math.ceil(sectors.length / 6));

                function flushRow() {
                    if (currentRow.length === 0) return;
                    const rowMV = currentRow.reduce((s, r) => s + r.total_mv, 0);
                    for (const s of currentRow) {
                        const w = Math.max(50, (s.total_mv / rowMV) * (containerWidth - gap * currentRow.length));
                        const v = Math.max(-5, Math.min(5, s.change_pct));
                        const t = (v + 5) / 10;
                        const bg = s.change_pct >= 0
                            ? `rgb(${Math.round(180 + 75 * t)},${Math.round(80 - 40 * t)},${Math.round(70 - 40 * t)})`
                            : `rgb(${Math.round(80 - 50 * (1 - t))},${Math.round(160 + 50 * (1 - t))},${Math.round(90 + 30 * (1 - t))})`;
                        const fg = Math.abs(s.change_pct) > 1.5 ? '#fff' : 'var(--text-primary)';
                        const pctStr = (s.change_pct >= 0 ? '+' : '') + s.change_pct.toFixed(2) + '%';
                        const fontSize = w > 80 ? '11px' : w > 60 ? '10px' : '8px';
                        html += `<div class="heatmap-cell" style="width:${w}px;height:${rowHeight}px;background:${bg};color:${fg};font-size:${fontSize}" title="${App.escapeHTML(s.name || '')} ${pctStr}">
                            <div class="heatmap-cell-name">${App.escapeHTML(s.name || '')}</div>
                            <div class="heatmap-cell-pct">${pctStr}</div>
                        </div>`;
                    }
                    currentRow = [];
                    currentRowMV = 0;
                }

                for (const s of sectors) {
                    currentRow.push(s);
                    currentRowMV += s.total_mv;
                    if (currentRowMV >= rowTargetMV && currentRow.length >= 3) flushRow();
                }
                flushRow();

                el.innerHTML = `<div class="heatmap-grid">${html}</div>`;
            } catch {
                el.innerHTML = '<div class="text-muted text-center">加载失败</div>';
            }
        },

        async loadHotspot() {
            const el = document.getElementById('intel-hotspot');
            if (!el) return;

            try {
                const data = await App.fetchJSON('/api/market/hotspot', { silent: true });
                if (!data.success) {
                    el.innerHTML = '<div class="text-muted text-center">加载失败</div>';
                    return;
                }

                const concepts = (data.hot_concepts || []).slice(0, 20);
                const summary = data.summary || '';
                let html = '';

                if (summary) {
                    html += `<div style="font-size:var(--font-size-xs);color:var(--text-muted);margin-bottom:8px">${App.escapeHTML(summary)}</div>`;
                }
                html += '<div style="display:flex;flex-wrap:wrap;gap:4px">';
                for (const c of concepts) {
                    const pctCls = c.change_pct >= 0 ? 'up' : 'down';
                    const pctStr = (c.change_pct >= 0 ? '+' : '') + c.change_pct.toFixed(2) + '%';
                    html += `<div class="intel-hotspot-concept" data-intel-action="query-hotspot" data-concept="${App.escapeHTML(c.name || '')}" title="领涨: ${App.escapeHTML(c.leader || '--')} | 上涨:${c.up_count} 下跌:${c.down_count}">
                        <span>${App.escapeHTML(c.name || '')}</span>
                        <span class="concept-pct ${pctCls}">${pctStr}</span>
                    </div>`;
                }
                html += '</div>';
                el.innerHTML = html;
            } catch {
                el.innerHTML = '<div class="text-muted text-center">加载失败</div>';
            }
        },
    });
})();
