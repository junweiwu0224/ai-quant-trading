/* ── 情报模块：市场数据链路 ── */
(function () {
    'use strict';

    const Intelligence = globalThis.Intelligence || (globalThis.Intelligence = {});

    const clampNumber = (value, min, max) => Math.max(min, Math.min(max, Number(value) || 0));
    const formatPct = (value, digits = 2) => {
        const num = Number(value);
        if (!Number.isFinite(num)) return '--';
        return `${num >= 0 ? '+' : ''}${num.toFixed(digits)}%`;
    };
    const formatSigned = (value, digits = 2, suffix = '') => {
        const num = Number(value);
        if (!Number.isFinite(num)) return '--';
        return `${num >= 0 ? '+' : ''}${num.toFixed(digits)}${suffix}`;
    };
    const formatCount = (value) => {
        const num = Number(value);
        return Number.isFinite(num) ? Math.round(num).toLocaleString('zh-CN') : '--';
    };
    const safeHTML = (value) => App.escapeHTML(value ?? '');
    const fetchOnce = (key, url, opts = {}) => {
        const state = Intelligence.state || (Intelligence.state = {});
        const requests = state.marketRequests || (state.marketRequests = {});
        if (!requests[key]) {
            requests[key] = App.fetchJSON(url, { silent: true, ...opts }).finally(() => {
                delete requests[key];
            });
        }
        return requests[key];
    };
    const scoreFromBreadth = (data) => {
        const up = Number(data?.up_count) || 0;
        const down = Number(data?.down_count) || 0;
        const flat = Number(data?.flat_count) || 0;
        const total = up + down + flat;
        if (total <= 0) return null;
        return ((up - down) / total) * 100;
    };
    const heatColor = (value) => {
        const v = clampNumber(value, -5, 5);
        const strength = Math.min(1, Math.abs(v) / 5);
        if (v >= 0) {
            const r = Math.round(176 + 60 * strength);
            const g = Math.round(82 - 34 * strength);
            const b = Math.round(72 - 28 * strength);
            return `rgb(${r},${g},${b})`;
        }
        const r = Math.round(58 - 22 * strength);
        const g = Math.round(150 + 42 * strength);
        const b = Math.round(96 + 22 * strength);
        return `rgb(${r},${g},${b})`;
    };
    const heatTextColor = (value) => Math.abs(Number(value) || 0) >= 1.6 ? '#fff' : 'var(--text-primary)';
    const sourceLabel = (value) => ({
        eastmoney_sector_board: '东方财富行业板块',
        eastmoney_full_market_rank: '东方财富全A',
        local_stock_daily: '本地日线覆盖池',
        eastmoney_news: '东方财富快讯',
    }[String(value || '').trim()] || String(value || '--'));
    const sourceName = (key) => ({
        concept: '概念',
        industry: '行业',
        fund_flow: '资金流',
    }[key] || key);
    const renderStatusPill = (data) => {
        const parts = [];
        parts.push(`<span class="intel-hotspot-pill ${data.stale ? 'warn' : 'ok'}">${data.stale ? '缓存数据' : '实时数据'}</span>`);
        if (data.timestamp) {
            parts.push(`<span class="intel-hotspot-pill">更新 ${safeHTML(data.timestamp)}</span>`);
        }
        const errors = Array.isArray(data.partial_errors) ? data.partial_errors : [];
        if (errors.length > 0) {
            parts.push(`<span class="intel-hotspot-pill warn">数据源异常 ${safeHTML(errors.map(sourceName).join('、'))}</span>`);
        }
        return `<div class="intel-hotspot-status">${parts.join('')}</div>`;
    };
    const buildTreemapTiles = (sectors) => {
        const ranked = sectors
            .map((sector) => ({
                ...sector,
                weight: Math.max(0, Number(sector.total_mv) || 0),
                change: Number(sector.change_pct) || 0,
            }))
            .filter((sector) => sector.weight > 0)
            .sort((a, b) => b.weight - a.weight)
            .slice(0, 32);
        const totalWeight = ranked.reduce((sum, sector) => sum + sector.weight, 0) || 1;
        let consumed = 0;
        return ranked.map((sector, index) => {
            let share = sector.weight / totalWeight;
            let span = Math.round(share * 36);
            if (index === 0 && span < 8) span = 8;
            span = clampNumber(span, 3, 18);
            consumed += span;
            const rowSpan = span >= 16 ? 2 : 1;
            return { sector, span, rowSpan, share, consumed };
        });
    };
    const renderEvidenceList = (title, items, type) => {
        const rows = (items || []).slice(0, 4);
        if (rows.length === 0) {
            return `<div class="intel-hotspot-evidence">
                <div class="intel-hotspot-evidence-title">${title}</div>
                <div class="intel-hotspot-empty">暂无数据</div>
            </div>`;
        }
        return `<div class="intel-hotspot-evidence">
            <div class="intel-hotspot-evidence-title">${title}</div>
            ${rows.map((item) => {
                const pct = type === 'flow'
                    ? formatSigned(item.main_net_inflow, 2, '亿')
                    : formatPct(item.change_pct);
                const aux = type === 'flow'
                    ? `占比 ${formatPct(item.main_net_inflow_pct)}`
                    : `领涨 ${safeHTML(item.leader || '--')} · 上涨${Number(item.up_count) || 0} 下跌${Number(item.down_count) || 0}`;
                const cls = (Number(type === 'flow' ? item.main_net_inflow : item.change_pct) || 0) >= 0 ? 'up' : 'down';
                return `<div class="intel-hotspot-evidence-row">
                    <span class="evidence-name">${safeHTML(item.name || '--')}</span>
                    <span class="evidence-value ${cls}">${pct}</span>
                    <span class="evidence-aux">${aux}</span>
                </div>`;
            }).join('')}
        </div>`;
    };

    Object.assign(Intelligence, {
        fetchMarketJSON: fetchOnce,
        scoreFromBreadth,

        async loadSentiment() {
            const el = document.getElementById('intel-sentiment');
            if (!el) return;

            try {
                const data = await fetchOnce('breadth', '/api/market/breadth');
                if (!data.success) {
                    el.innerHTML = '<div class="text-muted text-center">加载失败</div>';
                    return;
                }

                const gainers = Number(data.up_count) || 0;
                const losers = Number(data.down_count) || 0;
                const flat = Number(data.flat_count) || 0;
                const total = gainers + losers + flat;
                const upPct = total > 0 ? ((gainers / total) * 100).toFixed(0) : '--';
                const effective = Number(data.effective_count) || Number(data.latest_date_covered) || total;
                const staleCount = Math.max(0, (Number(data.stock_count) || Number(data.total_stocks) || effective) - effective);
                const breadthScore = scoreFromBreadth(data);
                const displayBreadthScore = breadthScore == null ? null : Math.round(breadthScore);
                const sentimentLabel = displayBreadthScore == null ? '中性' : displayBreadthScore >= 10 ? '偏多' : displayBreadthScore <= -10 ? '偏空' : '中性';
                const sentimentCls = displayBreadthScore == null ? 'text-muted' : displayBreadthScore >= 10 ? 'text-up' : displayBreadthScore <= -10 ? 'text-down' : 'text-muted';
                const coverage = data.stock_count
                    ? `${formatCount(effective)}/${formatCount(data.stock_count)}`
                    : formatCount(effective);
                const stale = data.stale ? ' · 缓存' : '';
                const sentHeader = document.querySelector('.intel-sentiment-card h3');
                if (sentHeader) {
                    const scoreText = displayBreadthScore == null ? '--' : formatSigned(displayBreadthScore, 0);
                    sentHeader.innerHTML = `市场情绪 <span class="${sentimentCls}" style="font-size:var(--font-size-xs);font-weight:400">${sentimentLabel} (${scoreText})</span>`;
                }

                el.innerHTML = `
                    <div class="intel-sent-stat">
                        <span class="label">上涨</span>
                        <span class="value text-up">${formatCount(gainers)}</span>
                    </div>
                    <div class="intel-sent-stat">
                        <span class="label">下跌</span>
                        <span class="value text-down">${formatCount(losers)}</span>
                    </div>
                    <div class="intel-sent-stat">
                        <span class="label">上涨占比</span>
                        <span class="value">${upPct}%</span>
                    </div>
                    <div class="intel-sent-meta">
                        <span>有效/全量 ${safeHTML(coverage)}</span>
                        <span>平盘 ${formatCount(flat)}</span>
                        ${staleCount ? `<span>未更新 ${formatCount(staleCount)}</span>` : ''}
                        <span>涨停 ${formatCount(data.limit_up)}</span>
                        <span>跌停 ${formatCount(data.limit_down)}</span>
                        ${data.latest_date ? `<span>${safeHTML(data.latest_date)}${stale}</span>` : ''}
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
                const data = await fetchOnce('news', '/api/market/news');
                if (!data.success) {
                    el.innerHTML = '<div class="text-muted text-center">加载失败</div>';
                    return;
                }

                const news = data.news || [];
                if (countEl) countEl.textContent = news.length;
                const timestampEl = document.getElementById('intel-timestamp');
                if (timestampEl && data.timestamp) timestampEl.textContent = data.timestamp;

                if (news.length === 0) {
                    const source = data.source || '市场新闻';
                    const timestamp = data.timestamp || '暂无更新时间';
                    el.innerHTML = `<div class="text-muted text-center intel-news-empty">
                        <div>暂无市场新闻</div>
                        <div class="intel-news-meta">
                            <span>${safeHTML(source)}</span>
                            <span>${safeHTML(timestamp)}</span>
                        </div>
                    </div>`;
                    return;
                }

                const newsSource = data.source || news[0]?.source || '市场新闻';
                const newsTime = data.generated_at || data.timestamp || news[0]?.time || '暂无更新时间';
                const coverageNote = data.coverage_note || data.note || '滚动新闻快讯，按时间倒序展示';
                const newsMeta = `<div class="intel-news-source-strip">
                    <span>新闻源 ${safeHTML(sourceLabel(newsSource))}</span>
                    <span>更新 ${safeHTML(newsTime)}</span>
                    <span>展示 ${formatCount(news.length)} 条</span>
                    <span>${safeHTML(coverageNote)}</span>
                </div>`;

                el.innerHTML = newsMeta + news.map((n) => {
                    const sentVal = n.sentiment || 0;
                    const sentCls = sentVal > 0.2 ? 'tag-up' : sentVal < -0.2 ? 'tag-down' : '';
                    const icon = sentVal > 0.2 ? '▲' : sentVal < -0.2 ? '▼' : '●';
                    const iconCls = sentVal > 0.2 ? 'text-up' : sentVal < -0.2 ? 'text-down' : 'text-muted';
                    const tags = (n.stocks || []).slice(0, 3).map((s) => (
                        `<span class="intel-news-tag ${sentCls}" data-intel-action="open-news-stock" data-code="${App.escapeHTML(s.code || '')}">${App.escapeHTML(s.name || s.code || '')}</span>`
                    )).join('');
                    const source = n.source ? `<span>${App.escapeHTML(n.source)}</span>` : '';
                    return `<div class="intel-news-item">
                        <span class="intel-news-icon ${iconCls}">${icon}</span>
                        <div class="intel-news-body">
                            <div class="intel-news-title">${App.escapeHTML(n.title || '')}</div>
                            <div class="intel-news-meta">
                                ${source}
                                <span>${App.escapeHTML(n.time || '')}</span>
                                ${tags}
                            </div>
                        </div>
                    </div>`;
                }).join('');
            } catch {
                el.innerHTML = '<div class="text-muted text-center">加载失败</div>';
            }
        },

        async loadHeatmap() {
            const el = document.getElementById('intel-heatmap');
            if (!el) return;

            try {
                const data = await fetchOnce('heatmap', '/api/market/heatmap');
                if (!data.success) {
                    el.innerHTML = '<div class="text-muted text-center">加载失败</div>';
                    return;
                }

                const sectors = (data.sectors || []).filter((s) => Number(s.total_mv) > 0);
                const tiles = buildTreemapTiles(sectors);
                if (tiles.length === 0) {
                    el.innerHTML = '<div class="text-muted text-center">暂无热力数据</div>';
                    return;
                }

                const upCount = Number.isFinite(Number(data.up_count))
                    ? Number(data.up_count)
                    : sectors.filter((s) => Number(s.change_pct) > 0).length;
                const downCount = Number.isFinite(Number(data.down_count))
                    ? Number(data.down_count)
                    : sectors.filter((s) => Number(s.change_pct) < 0).length;
                const flatCount = Number.isFinite(Number(data.flat_count))
                    ? Number(data.flat_count)
                    : sectors.filter((s) => Number(s.change_pct) === 0).length;
                const avgChange = Number.isFinite(Number(data.avg_change_pct))
                    ? Number(data.avg_change_pct)
                    : sectors.reduce((sum, s) => sum + (Number(s.change_pct) || 0), 0) / sectors.length;
                const strongest = [...sectors].sort((a, b) => Math.abs(Number(b.change_pct) || 0) - Math.abs(Number(a.change_pct) || 0))[0];
                const totalCount = Number(data.total) || sectors.length;
                const displayCount = tiles.length;
                const heatmapSource = data.source || (data.local_fallback ? 'local_stock_daily' : '');
                const heatmapTime = data.generated_at || data.timestamp || '';
                const coverageNote = data.coverage_note || (data.local_fallback ? '本地覆盖池降级热力' : '板块热力快照');

                const tileHtml = tiles.map(({ sector, span, rowSpan, share }) => {
                    const change = Number(sector.change_pct) || 0;
                    const pctStr = formatPct(change);
                    const mvStr = Number.isFinite(Number(sector.total_mv)) ? `${Math.round(Number(sector.total_mv)).toLocaleString('zh-CN')}亿` : '--';
                    const cls = change >= 0 ? 'up' : 'down';
                    return `<button class="intel-treemap-tile ${cls}" data-intel-action="query-hotspot" data-concept="${safeHTML(sector.name || '')}" style="grid-column: span ${span};grid-row: span ${rowSpan};background:${heatColor(change)};color:${heatTextColor(change)}" title="${safeHTML(sector.name || '')} ${pctStr} · 市值权重 ${(share * 100).toFixed(1)}% · 领涨 ${safeHTML(sector.leader || '--')}">
                        <span class="treemap-name">${safeHTML(sector.name || '')}</span>
                        <span class="treemap-pct">${pctStr}</span>
                        <span class="treemap-meta">${mvStr} · ${Number(sector.up_count) || 0}↑ ${Number(sector.down_count) || 0}↓</span>
                    </button>`;
                }).join('');

                el.innerHTML = `
                    <div class="intel-heatmap-head">
                        <div class="intel-heatmap-stats">
                            <span>上涨 ${upCount}</span>
                            <span>下跌 ${downCount}</span>
                            <span>平盘 ${flatCount}</span>
                            <span>均值 ${formatPct(avgChange)}</span>
                            <span>全量 ${formatCount(totalCount)} · 展示 ${formatCount(displayCount)}</span>
                            ${heatmapSource ? `<span>来源 ${safeHTML(sourceLabel(heatmapSource))}</span>` : ''}
                            ${heatmapTime ? `<span>更新 ${safeHTML(heatmapTime)}</span>` : ''}
                            ${data.stale ? '<span>缓存/降级</span>' : ''}
                            ${coverageNote ? `<span>${safeHTML(coverageNote)}</span>` : ''}
                            ${strongest ? `<span>最活跃 ${safeHTML(strongest.name)} ${formatPct(strongest.change_pct)}</span>` : ''}
                        </div>
                        <div class="intel-heatmap-legend">
                            <span>跌</span><i></i><span>涨</span>
                        </div>
                    </div>
                    <div class="intel-treemap">${tileHtml}</div>`;
            } catch {
                el.innerHTML = '<div class="text-muted text-center">加载失败</div>';
            }
        },

        async loadHotspot() {
            const el = document.getElementById('intel-hotspot');
            if (!el) return;

            try {
                const data = await fetchOnce('hotspot', '/api/market/hotspot');
                if (!data.success) {
                    el.innerHTML = '<div class="text-muted text-center">加载失败</div>';
                    return;
                }

                const concepts = (data.hot_concepts || []).slice(0, 12);
                const summary = data.summary || '';
                let html = '';

                html += renderStatusPill(data);
                if (summary) {
                    html += `<div class="intel-hotspot-summary">${safeHTML(summary)}</div>`;
                }
                html += '<div class="intel-hotspot-chipset">';
                for (const c of concepts) {
                    const pctCls = c.change_pct >= 0 ? 'up' : 'down';
                    const pctStr = formatPct(c.change_pct);
                    html += `<div class="intel-hotspot-concept" data-intel-action="query-hotspot" data-concept="${safeHTML(c.name || '')}" title="领涨: ${safeHTML(c.leader || '--')} | 上涨:${Number(c.up_count) || 0} 下跌:${Number(c.down_count) || 0}">
                        <span>${safeHTML(c.name || '')}</span>
                        <span class="concept-pct ${pctCls}">${pctStr}</span>
                        <span class="concept-leader">${safeHTML(c.leader || '--')}</span>
                    </div>`;
                }
                html += '</div>';
                html += '<div class="intel-hotspot-evidence-grid">';
                html += renderEvidenceList('热点概念', data.hot_concepts || [], 'concept');
                html += renderEvidenceList('行业共振', data.hot_industries || [], 'industry');
                html += renderEvidenceList('主力净流入', data.fund_flow || [], 'flow');
                html += '</div>';
                el.innerHTML = html;
            } catch {
                el.innerHTML = '<div class="text-muted text-center">加载失败</div>';
            }
        },
    });
})();
