/* ── 情报模块：AI 信号池与信号聚合 ── */
(function () {
    'use strict';

    const Intelligence = globalThis.Intelligence || (globalThis.Intelligence = {});
    const fetchShared = (key, url, opts = {}) => {
        if (typeof Intelligence.fetchMarketJSON === 'function') {
            return Intelligence.fetchMarketJSON(key, url, opts);
        }
        return App.fetchJSON(url, { silent: true, ...opts });
    };
    const withTimeout = (promise, timeoutMs = 2500) => new Promise((resolve) => {
        let settled = false;
        const finish = (value) => {
            if (settled) return;
            settled = true;
            clearTimeout(timer);
            resolve(value);
        };
        const timer = setTimeout(() => finish(null), timeoutMs);
        Promise.resolve(promise).then(finish).catch(() => finish(null));
    });
    const scoreFromBreadth = (data) => {
        if (typeof Intelligence.scoreFromBreadth === 'function') {
            return Intelligence.scoreFromBreadth(data);
        }
        const up = Number(data?.up_count) || 0;
        const down = Number(data?.down_count) || 0;
        const flat = Number(data?.flat_count) || 0;
        const total = up + down + flat;
        return total > 0 ? ((up - down) / total) * 100 : null;
    };
    const formatCount = (value) => {
        const num = Number(value);
        return Number.isFinite(num) ? Math.round(num).toLocaleString('zh-CN') : '--';
    };
    const formatSigned = (value) => {
        const num = Number(value);
        if (!Number.isFinite(num)) return '--';
        return `${num >= 0 ? '+' : ''}${Math.round(num)}`;
    };
    const signalColor = (score) => (score >= 10 ? '#22c55e' : score <= -10 ? '#dc2626' : '#f59e0b');
    const signalRawSourceName = (value) => ({
        legacy_qlib: '历史预测缓存',
        qlib: '历史预测缓存',
        local_momentum: '本地动量信号',
    }[String(value || '').trim()] || String(value || '未知来源'));
    const breadthSourceName = (value) => ({
        local_stock_daily: '本地日线覆盖池',
        eastmoney_full_market_rank: '东方财富全A',
    }[String(value || '').trim()] || String(value || '本地日线覆盖池'));

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
                    fetchShared('signalTop50', '/api/signals/top?limit=50'),
                    fetchShared('signalValidation50', '/api/signals/validation?top_n=50').catch(() => null),
                ]);

                if (!data || !data.predictions || data.predictions.length === 0) {
                    el.innerHTML = '<div class="text-muted text-center" style="padding:16px">暂无预测数据</div>';
                    return;
                }

                const validation = consistData?.success ? consistData : null;
                const confidenceLabel = {
                    validated_positive: '验证偏正',
                    validated_neutral: '验证中性',
                    validated_weak: '验证偏弱',
                    unverified: '未验证',
                }[validation?.confidence] || '未验证';
                const confidenceText = (confidence) => ({
                    validated_positive: '验证偏正',
                    validated_neutral: '验证中性',
                    validated_weak: '验证偏弱',
                    unverified: '未验证',
                }[confidence] || '未验证');
                const metric1d = validation?.metrics?.['1d'] || {};
                const fmtPct = (value, digits = 2) => {
                    const num = Number(value);
                    if (!Number.isFinite(num)) return '--';
                    return `${num >= 0 ? '+' : ''}${num.toFixed(digits)}%`;
                };
                const fmtPlainPct = (value, digits = 1) => {
                    const num = Number(value);
                    return Number.isFinite(num) ? `${num.toFixed(digits)}%` : '--';
                };
                const fmtNum = (value, digits = 3) => {
                    const num = Number(value);
                    return Number.isFinite(num) ? num.toFixed(digits) : '--';
                };
                const validationSummary = validation ? `
                    <div class="qlib-validation-summary">
                        <span class="qlib-validation-title">验证摘要</span>
                        <span>状态 ${App.escapeHTML(confidenceText(validation.confidence))}</span>
                        <span>样本 ${App.escapeHTML(String(validation.sample_days ?? 0))} 天</span>
                        <span>Top超额 ${App.escapeHTML(fmtPct(metric1d.top_excess_return_pct, 2))}</span>
                        <span>胜率 ${App.escapeHTML(fmtPlainPct(metric1d.hit_rate_pct, 1))}</span>
                        <span>Rank IC ${App.escapeHTML(fmtNum(metric1d.rank_ic, 3))}</span>
                    </div>` : `
                    <div class="qlib-validation-summary">
                        <span class="qlib-validation-title">验证摘要</span>
                        <span>状态 未验证</span>
                        <span>历史样本不足，信号已在机会池降权</span>
                    </div>`;

                const preds = data.predictions;
                const total = preds.length;
                const totalUniverse = Number(data.total) || total;
                const rawSource = signalRawSourceName(data.raw_source || data.source || data.provider);
                const rawSourceKey = String(data.raw_source || data.source || '').trim();
                const legacySourceNote = rawSourceKey ? `兼容 ${rawSourceKey}` : 'Signal Engine';
                const generatedAt = data.generated_at || data.updated_at || '--';
                const validationDays = validation ? String(validation.sample_days ?? 0) : '0';
                const trustSummary = `
                    <div class="qlib-trust-summary">
                        <span class="qlib-trust-title">可信口径</span>
                        <span>来源 ${App.escapeHTML(rawSource)}</span>
                        <span>${App.escapeHTML(legacySourceNote)}</span>
                        <span>覆盖 ${App.escapeHTML(formatCount(totalUniverse))} 只</span>
                        <span>展示 Top ${App.escapeHTML(formatCount(total))}</span>
                        <span>生成 ${App.escapeHTML(generatedAt)}</span>
                        <span>验证样本 ${App.escapeHTML(validationDays)} 天</span>
                    </div>`;
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
                    const rowConfidence = validation?.confidence && validation.confidence !== 'unverified'
                        ? validation.confidence
                        : p.signal_confidence;
                    const diamond = rowConfidence?.startsWith?.('validated') ? '<span class="qlib-diamond" title="信号池已通过历史验证">✓</span>' : '';
                    const icAdjStr = confidenceText(rowConfidence);

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
                                <span class="qlib-trust-title">AI 信号池</span>
	                            <span class="qlib-date" data-intel-action="timeline-focus" data-date="${App.escapeHTML(dateStr)}" style="cursor:pointer;text-decoration:underline dotted" title="点击联动到研发页">信号日期: ${App.escapeHTML(dateStr)}</span>
	                            <span class="qlib-total">${App.escapeHTML(data.provider || 'local_momentum')} · ${App.escapeHTML(data.model_version || '--')} · 全市场 ${formatCount(totalUniverse)} 只 · Top ${formatCount(total)} · ${App.escapeHTML(confidenceLabel)}</span>
                        </div>
                        <button class="qlib-btn qlib-btn-push" id="qlib-push-screener">
	                            📤 推送 Top 50 至选股器
                        </button>
                    </div>
                    ${trustSummary}
                    ${validationSummary}
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
                                <th class="qlib-th qlib-td-bar">信号分</th>
                                <th class="qlib-th qlib-td-ic" title="历史验证状态，不代表上涨概率">验证</th>
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
                            query: `AI 信号 Top ${total} 候选池 (${dateStr})`,
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

            const state = Intelligence.state || (Intelligence.state = {});
            const requestId = (state.signalBarRequestId || 0) + 1;
            state.signalBarRequestId = requestId;
            const isCurrent = () => state.signalBarRequestId === requestId;
            const breadthPromise = fetchShared('breadth', '/api/market/breadth');
            const marker = document.getElementById('signal-bar-marker');
            const scoreEl = document.getElementById('signal-bar-score');
            const sourcesEl = document.getElementById('signal-bar-sources');

            const renderUnavailable = () => {
                if (!isCurrent()) return;
                if (marker) marker.style.left = '50%';
                if (scoreEl) {
                    scoreEl.textContent = '--';
                    scoreEl.style.color = '#f59e0b';
                }
                if (sourcesEl) {
                    sourcesEl.innerHTML = '<span class="signal-src"><span class="signal-src-dot" style="background:#f59e0b"></span>广度不可用</span>';
                }
            };
            const renderBreadth = (breadth) => {
                if (!isCurrent()) return;
                const score = scoreFromBreadth(breadth);
                if (score === null) {
                    if (marker) marker.style.left = '50%';
                    if (scoreEl) scoreEl.textContent = '--';
                    if (sourcesEl) sourcesEl.textContent = '';
                    return;
                }

                const up = Number(breadth.up_count) || 0;
                const down = Number(breadth.down_count) || 0;
                const flat = Number(breadth.flat_count) || 0;
                const classifiedTotal = up + down + flat;
                const effective = Number(breadth.effective_count) || Number(breadth.latest_date_covered) || up + down + flat;
                const stockCount = Number(breadth.stock_count) || Number(breadth.total_stocks) || effective;
                const upRatio = classifiedTotal > 0 ? ((up / classifiedTotal) * 100).toFixed(0) : '--';
                const advanceDecline = down > 0 ? (up / down).toFixed(2) : '--';
                const displayScore = Math.round(score);
                const color = signalColor(displayScore);
                const source = breadth.source || (breadth.local_fallback ? 'local_stock_daily' : 'local_stock_daily');

                if (marker) {
                    const pct = Math.max(0, Math.min(100, (score + 100) / 2));
                    marker.style.left = pct + '%';
                }

                if (scoreEl) {
                    scoreEl.textContent = `广度分 ${formatSigned(displayScore)}`;
                    scoreEl.title = `全市场广度分 = (上涨 ${formatCount(up)} - 下跌 ${formatCount(down)}) / 分类样本 ${formatCount(classifiedTotal)}；覆盖样本 ${formatCount(effective)}/${formatCount(stockCount)}`;
                    scoreEl.style.color = color;
                }

                if (sourcesEl) {
                    const sources = [
                        { text: `来源 ${breadthSourceName(source)}`, color: '#94a3b8' },
                        { text: '口径 全市场广度', color },
                        { text: '公式 (上涨-下跌)/(上涨+下跌+平盘)', color },
                        { text: `上涨占比 ${upRatio}%`, color },
                        { text: `涨跌比 ${advanceDecline}`, color },
                        { text: `涨停/跌停 ${formatCount(breadth.limit_up)}/${formatCount(breadth.limit_down)}`, color: '#f59e0b' },
                        { text: `样本 ${formatCount(effective)}/${formatCount(stockCount)}`, color: '#94a3b8' },
                    ];
                    sourcesEl.innerHTML = sources.map((s) => {
                        return `<span class="signal-src"><span class="signal-src-dot" style="background:${s.color}"></span>${App.escapeHTML(s.text)}</span>`;
                    }).join('');
                }
            };

            const quickBreadth = await withTimeout(breadthPromise, 1500);
            if (quickBreadth?.success) {
                renderBreadth(quickBreadth);
                return;
            }

            renderUnavailable();
            const finalBreadth = await withTimeout(breadthPromise, 10000);
            if (finalBreadth?.success) {
                renderBreadth(finalBreadth);
            } else {
                renderUnavailable();
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
