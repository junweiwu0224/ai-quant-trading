/* ── 情报模块：Qlib 预测池与信号聚合 ── */
(function () {
    'use strict';

    const Intelligence = globalThis.Intelligence || (globalThis.Intelligence = {});

    Object.assign(Intelligence, {
        heatLevel(rank, total) {
            const pct = total > 0 ? rank / total : 1;
            if (pct <= 0.05) return { icon: '🔥', label: '强动能', cls: 'qlib-heat-hot' };
            if (pct <= 0.15) return { icon: '🟠', label: '中动能', cls: 'qlib-heat-warm' };
            if (pct <= 0.30) return { icon: '🟡', label: '弱动能', cls: 'qlib-heat-mild' };
            return { icon: '⚪', label: '', cls: 'qlib-heat-cool' };
        },

        async loadMLPredictions() {
            const el = document.getElementById('intel-ml-pred');
            if (!el) return;

            try {
                const [data, consistData] = await Promise.all([
                    App.fetchJSON('/api/qlib/top?top_n=50', { silent: true }),
                    App.fetchJSON('/api/qlib/consistency?top_n=50', { silent: true }).catch(() => null),
                ]);

                if (!data || !data.predictions || data.predictions.length === 0) {
                    el.innerHTML = '<div class="text-muted text-center" style="padding:16px">暂无预测数据</div>';
                    return;
                }

                const consistMap = {};
                if (consistData?.success && consistData.items) {
                    for (const item of consistData.items) {
                        consistMap[item.code] = item;
                    }
                }

                const preds = data.predictions;
                const total = preds.length;
                const scores = preds.map((p) => p.score);
                const minScore = Math.min(...scores);
                const maxScore = Math.max(...scores);
                const scoreRange = maxScore - minScore || 1;

                const rows = preds.map((p, i) => {
                    const heat = this.heatLevel(i, total);
                    const barPct = Math.round(((p.score - minScore) / scoreRange) * 100);
                    const hue = Math.round(220 - (barPct / 100) * 220);
                    const barBg = `hsl(${hue}, 70%, 50%)`;
                    const industry = (p.industry || '--').split('-')[0].substring(0, 8);
                    const priceStr = p.price ? p.price.toFixed(2) : '--';
                    const amtStr = p.amount ? (p.amount >= 1e8 ? (p.amount / 1e8).toFixed(1) + '亿' : (p.amount / 1e4).toFixed(0) + '万') : '--';
                    const code = App.escapeHTML(p.code || '');
                    const name = App.escapeHTML(p.name || p.code || '');
                    const consist = consistMap[p.code];
                    const diamond = consist?.diamond ? '<span class="qlib-diamond" title="高一致性 IC_adj=' + (consist.ic_adj?.toFixed(2) || '--') + '">💎</span>' : '';
                    const icAdjStr = consist?.ic_adj != null ? consist.ic_adj.toFixed(2) : '--';

                    return `<tr class="qlib-row ${heat.cls}" data-code="${code}">
                        <td class="qlib-td qlib-td-rank">${i + 1}</td>
                        <td class="qlib-td">
                            <div class="qlib-stock-name">${name}${diamond}</div>
                            <div class="qlib-stock-code">${code}</div>
                        </td>
                        <td class="qlib-td">
                            <span class="qlib-heat-icon">${heat.icon}</span>
                        </td>
                        <td class="qlib-td qlib-td-industry">
                            <span class="qlib-industry-tag">${App.escapeHTML(industry)}</span>
                        </td>
                        <td class="qlib-td qlib-td-price">${priceStr}</td>
                        <td class="qlib-td qlib-td-vol">${amtStr}</td>
                        <td class="qlib-td qlib-td-bar">
                            <div class="qlib-bar-wrap">
                                <div class="qlib-bar-fill" style="width:${barPct}%;background:${barBg}"></div>
                            </div>
                            <span class="qlib-score" style="color:${barBg}">${p.score.toFixed(3)}</span>
                        </td>
                        <td class="qlib-td qlib-td-ic">${icAdjStr}</td>
                        <td class="qlib-td qlib-td-actions">
                            <button class="qlib-btn qlib-btn-mimo" data-code="${code}" data-name="${name}" data-score="${p.score.toFixed(3)}" data-industry="${App.escapeHTML(p.industry || '--')}" title="问 AI">🤖</button>
                        </td>
                    </tr>`;
                }).join('');

                const dateStr = data.date || '--';
                el.innerHTML = `
                    <div class="qlib-header">
                        <div class="qlib-header-left">
                            <span class="qlib-date" data-intel-action="timeline-focus" data-date="${App.escapeHTML(dateStr)}" style="cursor:pointer;text-decoration:underline dotted" title="点击联动到研发页">预测日期: ${App.escapeHTML(dateStr)}</span>
                            <span class="qlib-total">全市场 ${data.total} 只 · Top ${total}</span>
                        </div>
                        <button class="qlib-btn qlib-btn-push" id="qlib-push-screener">
                            📤 推送 Top 50 至选股器
                        </button>
                    </div>
                    <div class="qlib-legend">
                        <span class="qlib-legend-item"><span class="qlib-heat-icon">🔥</span> 强动能(前5%)</span>
                        <span class="qlib-legend-item"><span class="qlib-heat-icon">🟠</span> 中动能(前15%)</span>
                        <span class="qlib-legend-item"><span class="qlib-heat-icon">🟡</span> 弱动能(前30%)</span>
                        <span class="qlib-legend-item"><span class="qlib-heat-icon">⚪</span> 观望</span>
                    </div>
                    <div class="qlib-table-wrap">
                        <table class="qlib-table">
                            <thead><tr>
                                <th class="qlib-th qlib-td-rank">#</th>
                                <th class="qlib-th">股票</th>
                                <th class="qlib-th">热度</th>
                                <th class="qlib-th">行业</th>
                                <th class="qlib-th qlib-td-price">价格</th>
                                <th class="qlib-th qlib-td-vol">成交额</th>
                                <th class="qlib-th qlib-td-bar">预测力</th>
                                <th class="qlib-th qlib-td-ic" title="一致性 IC_adj = Score/σ(Hist)">一致性</th>
                                <th class="qlib-th qlib-td-actions">操作</th>
                            </tr></thead>
                            <tbody>${rows}</tbody>
                        </table>
                    </div>`;

                document.getElementById('qlib-push-screener')?.addEventListener('click', () => {
                    const codes = preds.map((p) => p.code);
                    if (typeof App.emit === 'function') {
                        App.emit('iwencai:send-to-screener', {
                            pool: codes,
                            query: `Qlib Top ${total} 预测金股池 (${dateStr})`,
                        });
                    }
                    App.toast(`已推送 ${codes.length} 只股票至选股器`, 'success');
                });
            } catch {
                el.innerHTML = '<div class="text-muted text-center" style="padding:16px">预测加载失败</div>';
            }
        },

        async loadSignalBar() {
            const bar = document.getElementById('signal-bar');
            if (!bar) return;

            const sources = [];
            let compositeScore = 0;
            let validSources = 0;

            const [radarRes, heatmapRes, qlibRes, newsRes, hotspotRes] = await Promise.allSettled([
                App.fetchJSON('/api/market/radar', { silent: true }),
                App.fetchJSON('/api/market/heatmap', { silent: true }),
                App.fetchJSON('/api/qlib/top?top_n=50', { silent: true }),
                App.fetchJSON('/api/market/news', { silent: true }),
                App.fetchJSON('/api/market/hotspot', { silent: true }),
            ]);

            if (radarRes.status === 'fulfilled' && radarRes.value?.success) {
                const r = radarRes.value;
                const g = (r.top_gainers || []).length;
                const l = (r.top_losers || []).length;
                const total = g + l;
                if (total > 0) {
                    const ratio = (g / total - 0.5) * 200;
                    compositeScore += ratio;
                    validSources++;
                    sources.push({ name: '情绪', score: ratio, color: ratio >= 0 ? '#22c55e' : '#dc2626' });
                }
            }

            if (heatmapRes.status === 'fulfilled' && heatmapRes.value?.success) {
                const sectors = heatmapRes.value.sectors || [];
                if (sectors.length > 0) {
                    const avg = sectors.reduce((s, sec) => s + (sec.change_pct || 0), 0) / sectors.length;
                    const score = Math.max(-100, Math.min(100, avg * 20));
                    compositeScore += score;
                    validSources++;
                    sources.push({ name: '板块', score, color: score >= 0 ? '#22c55e' : '#dc2626' });
                }
            }

            if (qlibRes.status === 'fulfilled' && qlibRes.value?.predictions?.length) {
                const preds = qlibRes.value.predictions;
                const scores = preds.map((p) => p.score);
                const avgScore = scores.reduce((a, b) => a + b, 0) / scores.length;
                const normalized = (avgScore - 0.5) * 200;
                const score = Math.max(-100, Math.min(100, normalized));
                compositeScore += score;
                validSources++;
                sources.push({ name: 'AI预测', score, color: score >= 0 ? '#22c55e' : '#dc2626' });
            }

            if (newsRes.status === 'fulfilled' && newsRes.value?.success) {
                const count = (newsRes.value.news || []).length;
                const score = Math.min(100, count * 5);
                compositeScore += score - 50;
                validSources++;
                sources.push({ name: '新闻', score: score - 50, color: score > 50 ? '#f59e0b' : '#94a3b8' });
            }

            if (hotspotRes.status === 'fulfilled' && hotspotRes.value?.success) {
                const topics = (hotspotRes.value.hotspots || hotspotRes.value.topics || []).length;
                const score = Math.min(100, topics * 10);
                compositeScore += score - 50;
                validSources++;
                sources.push({ name: '热点', score: score - 50, color: score > 50 ? '#f59e0b' : '#94a3b8' });
            }

            const avgScore = validSources > 0 ? compositeScore / validSources : 0;
            const displayScore = Math.round(avgScore);

            const marker = document.getElementById('signal-bar-marker');
            const scoreEl = document.getElementById('signal-bar-score');
            const sourcesEl = document.getElementById('signal-bar-sources');

            if (marker) {
                const pct = Math.max(0, Math.min(100, (avgScore + 100) / 2));
                marker.style.left = pct + '%';
            }

            if (scoreEl) {
                scoreEl.textContent = displayScore > 0 ? '+' + displayScore : String(displayScore);
                scoreEl.style.color = displayScore >= 10 ? '#22c55e' : displayScore <= -10 ? '#dc2626' : '#f59e0b';
            }

            if (sourcesEl) {
                sourcesEl.innerHTML = sources.map((s) => {
                    const dotColor = s.score >= 10 ? '#22c55e' : s.score <= -10 ? '#dc2626' : '#f59e0b';
                    return `<span class="signal-src"><span class="signal-src-dot" style="background:${dotColor}"></span>${s.name}</span>`;
                }).join('');
            }
        },

        async loadDataHubDigest() {
            const el = document.getElementById('intel-ml-pred');
            if (!el) return;
            try {
                const data = await App.fetchJSON('/api/datahub/health', { silent: true, timeout: 12000 });
                const sourceHealth = data.source_health || {};
                const qualitySummary = data.quality_summary || {};
                const shadow = data.shadow || {};
                el.dataset.datahubDigest = JSON.stringify({
                    sources: sourceHealth.total_active_sources || 0,
                    quality: qualitySummary.total || 0,
                    shadow: shadow.total_checks || 0,
                });
            } catch {
                // keep existing prediction UI intact
            }
        },
    });
})();
