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
    const normalizeStockCode = (value) => String(value || '')
        .trim()
        .replace(/\.(SH|SZ|BJ)$/i, '')
        .replace(/^(SH|SZ|BJ)/i, '');
    const signalColor = (score) => (score >= 10 ? '#22c55e' : score <= -10 ? '#dc2626' : '#f59e0b');
    const signalRawSourceName = (value) => ({
        legacy_qlib: '历史兼容信号缓存',
        qlib: '历史兼容信号缓存',
        local_momentum: '本地动量信号',
    }[String(value || '').trim()] || String(value || '未知来源'));
    const signalProviderName = (value) => ({
        local_momentum: '本地动量信号',
        signal_engine: 'Signal Engine',
        legacy_qlib: '历史兼容信号',
        qlib: '历史兼容信号',
    }[String(value || '').trim()] || String(value || '未知来源'));
    const signalModelName = (value) => ({
        local_momentum_v1: '基线动量模型',
    }[String(value || '').trim()] || String(value || '--'));
    const compactIndustryLabel = (value) => {
        const raw = String(value || '').trim();
        if (!raw) return '';
        const compact = raw
            .replace(/和其他.*$/, '')
            .replace(/及其他.*$/, '')
            .replace(/生产和供应业/g, '生产供应')
            .replace(/制造业$/, '')
            .replace(/服务业$/, '')
            .replace(/批发业$/, '')
            .replace(/零售业$/, '')
            .trim();
        return compact || raw;
    };
    const displayIndustry = (industryValue, sectorValue = '') => {
        const rawIndustry = String(industryValue || '').trim();
        const rawSector = String(sectorValue || '').trim();
        const industryParts = rawIndustry.split('-').map((part) => part.trim()).filter(Boolean);
        const labelSource = compactIndustryLabel(rawSector || industryParts[industryParts.length - 1] || rawIndustry);
        const label = labelSource ? labelSource.substring(0, 10) : '';
        return {
            label: label || '行业未标注',
            missing: !label,
            title: rawIndustry && rawIndustry !== label ? rawIndustry : '',
        };
    };
    const breadthSourceName = (value) => ({
        local_stock_daily: '本地日线覆盖池',
        eastmoney_full_market_rank: '东方财富全A',
    }[String(value || '').trim()] || String(value || '本地日线覆盖池'));
    const confidenceText = (confidence) => ({
        validated_positive: '验证偏正',
        validated_neutral: '验证中性',
        validated_weak: '验证偏弱',
        unverified: '未验证',
    }[confidence] || '未验证');
    const MIN_VALIDATION_SAMPLE_DAYS = 20;
    const validationQuality = (validation) => {
        const confidence = String(validation?.confidence || 'unverified');
        const sampleDays = Number(validation?.sample_days) || 0;
        const validated = validation?.success && confidence.startsWith('validated');
        const sampleEnough = sampleDays >= MIN_VALIDATION_SAMPLE_DAYS;
        return {
            confidence,
            sampleDays,
            validated,
            sampleEnough,
            tradable: validated && sampleEnough,
            label: validated && !sampleEnough ? '样本不足' : confidenceText(confidence),
        };
    };
    const defaultSignalQuality = () => ({
        confidence: 'unverified',
        sampleDays: 0,
        validated: false,
        sampleEnough: false,
        tradable: false,
        label: '待验证',
    });
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
    const updateSignalTopIndex = (signals, quality = null) => {
        const state = Intelligence.state || (Intelligence.state = {});
        const index = new Map();
        const signalQuality = quality || state.signalValidationQuality || defaultSignalQuality();
        for (const [idx, signal] of (Array.isArray(signals) ? signals : []).entries()) {
            const code = normalizeStockCode(signal?.code);
            const name = String(signal?.name || signal?.code || '').trim();
            if (!code && !name) continue;
            const entry = {
                code,
                name,
                score: Number(signal?.score),
                rank: idx + 1,
                confidence: signal?.signal_confidence || 'unverified',
                quality: signalQuality,
            };
            if (code) index.set(code, entry);
            if (name) index.set(`name:${name}`, entry);
        }
        state.signalTopIndex = index;
        state.signalValidationQuality = signalQuality;
        if (typeof Intelligence.refreshNewsTopicBoardWithSignals === 'function') {
            Intelligence.refreshNewsTopicBoardWithSignals();
        }
        return index;
    };
    const renderValidationSummary = (validation, { pending = false } = {}) => {
        if (validation?.success) {
            const metric1d = validation.metrics?.['1d'] || {};
            const quality = validationQuality(validation);
            if (!quality.sampleEnough) {
                return `
                    <div class="qlib-validation-summary warn" data-signal-validation-summary>
                        <span class="qlib-validation-title">Top 50 历史回测摘要</span>
                        <span>池级验证样本不足</span>
                        <span>池级状态 ${App.escapeHTML(confidenceText(validation.confidence))}</span>
                        <span>样本 ${App.escapeHTML(String(quality.sampleDays))}/${MIN_VALIDATION_SAMPLE_DAYS} 天</span>
                        <span>仅供观察，不适合作为交易依据</span>
                        <span>Top超额 ${App.escapeHTML(fmtPct(metric1d.top_excess_return_pct, 2))}</span>
                        <span>胜率 ${App.escapeHTML(fmtPlainPct(metric1d.hit_rate_pct, 1))}</span>
                        <span>Rank IC ${App.escapeHTML(fmtNum(metric1d.rank_ic, 3))}</span>
                    </div>`;
            }
            return `
                <div class="qlib-validation-summary" data-signal-validation-summary>
                    <span class="qlib-validation-title">Top 50 历史回测摘要</span>
                    <span>池级状态 ${App.escapeHTML(confidenceText(validation.confidence))}</span>
                    <span>样本 ${App.escapeHTML(String(validation.sample_days ?? 0))} 天</span>
                    <span>Top超额 ${App.escapeHTML(fmtPct(metric1d.top_excess_return_pct, 2))}</span>
                    <span>胜率 ${App.escapeHTML(fmtPlainPct(metric1d.hit_rate_pct, 1))}</span>
                    <span>Rank IC ${App.escapeHTML(fmtNum(metric1d.rank_ic, 3))}</span>
                </div>`;
        }
        return `
            <div class="qlib-validation-summary" data-signal-validation-summary>
                <span class="qlib-validation-title">Top 50 历史回测摘要</span>
                <span>状态 未验证</span>
                <span>${pending ? '历史验证后台更新中，不阻塞候选池首屏' : '历史样本不足，信号已在机会池降权'}</span>
            </div>`;
    };

    Object.assign(Intelligence, {
        heatLevel(rank, total) {
            const pct = total > 0 ? rank / total : 1;
            if (pct <= 0.05) return { icon: '🔥', label: '信号排名前5%', cls: 'qlib-heat-hot' };
            if (pct <= 0.15) return { icon: '🟠', label: '信号排名前15%', cls: 'qlib-heat-warm' };
            if (pct <= 0.30) return { icon: '🟡', label: '信号排名前30%', cls: 'qlib-heat-mild' };
            return { icon: '⚪', label: '', cls: 'qlib-heat-cool' };
        },

        renderSignalPool(data, validation = null, { pendingValidation = false } = {}) {
            const el = document.getElementById('intel-ml-pred');
            if (!el) return;

            const preds = Array.isArray(data.signals) ? data.signals : (data.predictions || []);
            if (preds.length === 0) {
                el.innerHTML = '<div class="text-muted text-center" style="padding:16px">暂无信号数据</div>';
                return;
            }

            const quality = validation?.success ? validationQuality(validation) : defaultSignalQuality();
            const confidenceLabel = validation?.success ? quality.label : '未验证';
            const total = preds.length;
            const totalUniverse = Number(data.total) || total;
            const signalProvider = data.provider || 'local_momentum';
            const modelVersion = data.model_version || '--';
            const providerLabel = signalProviderName(signalProvider);
            const modelLabel = signalModelName(modelVersion);
            const rawSourceKey = String(data.raw_source || data.source || '').trim();
            const rawSource = rawSourceKey ? signalRawSourceName(rawSourceKey) : '';
            const legacySourceNote = rawSourceKey ? `兼容缓存 ${rawSource}` : 'Signal Engine';
            const generatedAt = data.generated_at || data.updated_at || '--';
            const validationDays = validation?.success ? String(quality.sampleDays) : '0';
            const industryCoverage = preds.reduce((count, item) => {
                const industry = displayIndustry(item.industry, item.sector);
                return count + (industry.missing ? 0 : 1);
            }, 0);
            const industryMissing = Math.max(0, total - industryCoverage);
            const trustSummary = `
                <div class="qlib-trust-summary">
                    <span class="qlib-trust-title">可信口径</span>
                    <span>来源 ${App.escapeHTML(providerLabel)}</span>
                    <span>模型 ${App.escapeHTML(modelLabel)}</span>
                    <span>${App.escapeHTML(legacySourceNote)}</span>
                    <span>覆盖 ${App.escapeHTML(formatCount(totalUniverse))} 只</span>
                    <span>展示 Top ${App.escapeHTML(formatCount(total))}</span>
                    <span>生成 ${App.escapeHTML(generatedAt)}</span>
                    <span>验证样本 ${App.escapeHTML(validationDays)} 天</span>
                    <span>行业标注 ${App.escapeHTML(formatCount(industryCoverage))}/${App.escapeHTML(formatCount(total))}</span>
                    ${industryMissing ? `<span>行业缺失 ${App.escapeHTML(formatCount(industryMissing))} 只</span>` : ''}
                </div>`;
            const scores = preds.map((p) => Number(p.score) || 0);
            const minScore = Math.min(...scores);
            const maxScore = Math.max(...scores);
            const scoreRange = maxScore - minScore || 1;

            const rows = preds.map((p, i) => {
                const heat = this.heatLevel(i, total);
                const score = Number(p.score) || 0;
                const barPct = Math.round(((score - minScore) / scoreRange) * 100);
                const hue = Math.round(220 - (barPct / 100) * 220);
                const barBg = `hsl(${hue}, 70%, 50%)`;
                const industry = displayIndustry(p.industry, p.sector);
                const price = Number(p.price);
                const amount = Number(p.amount);
                const priceStr = Number.isFinite(price) && price > 0 ? price.toFixed(2) : '--';
                const amtStr = Number.isFinite(amount) && amount > 0 ? (amount >= 1e8 ? (amount / 1e8).toFixed(1) + '亿' : (amount / 1e4).toFixed(0) + '万') : '--';
                const code = App.escapeHTML(p.code || '');
                const name = App.escapeHTML(p.name || p.code || '');
                const rowConfidence = String(p.signal_confidence || 'unverified');
                const validationTitle = quality.tradable
                    ? '仅代表 Top 50 信号池历史验证，不代表单股验证'
                    : '单条信号尚未通过独立历史验证';
                const icAdjStr = quality.tradable ? '池级非单股' : confidenceText(rowConfidence);

                return `<tr class="qlib-row ${heat.cls}" data-code="${code}">
                    <td class="qlib-td qlib-td-rank">${i + 1}</td>
                    <td class="qlib-td">
                        <div class="qlib-stock-name">${name}</div>
                        <div class="qlib-stock-code">${code}</div>
                    </td>
                    <td class="qlib-td">
                        <span class="qlib-heat-icon">${heat.icon}</span>
                    </td>
                    <td class="qlib-td qlib-td-industry">
                        <span class="qlib-industry-tag${industry.missing ? ' muted' : ''}"${industry.title ? ` title="${App.escapeHTML(industry.title)}"` : ''}>${App.escapeHTML(industry.label)}</span>
                    </td>
                    <td class="qlib-td qlib-td-price">${priceStr}</td>
                    <td class="qlib-td qlib-td-vol">${amtStr}</td>
                    <td class="qlib-td qlib-td-bar">
                        <div class="qlib-bar-wrap">
                            <div class="qlib-bar-fill" style="width:${barPct}%;background:${barBg}"></div>
                        </div>
                        <span class="qlib-score" style="color:${barBg}">${score.toFixed(3)}</span>
                    </td>
                    <td class="qlib-td qlib-td-ic" title="${App.escapeHTML(validationTitle)}">${icAdjStr}</td>
                    <td class="qlib-td qlib-td-actions">
                        <button class="qlib-btn qlib-btn-mimo" data-code="${code}" data-name="${name}" data-score="${score.toFixed(3)}" data-industry="${App.escapeHTML(industry.label)}" title="问 AI">🤖</button>
                    </td>
                </tr>`;
            }).join('');

            const dateStr = data.date || '--';
            el.innerHTML = `
                <div class="qlib-header">
                    <div class="qlib-header-left">
                            <span class="qlib-trust-title">AI 信号池</span>
                            <span class="qlib-date" data-intel-action="timeline-focus" data-date="${App.escapeHTML(dateStr)}" style="cursor:pointer;text-decoration:underline dotted" title="点击联动到研发页">信号日期: ${App.escapeHTML(dateStr)}</span>
                            <span class="qlib-total">${App.escapeHTML(providerLabel)} · ${App.escapeHTML(modelLabel)} · 全市场 ${formatCount(totalUniverse)} 只 · Top ${formatCount(total)} · ${App.escapeHTML(confidenceLabel)}</span>
                    </div>
                    <button class="qlib-btn qlib-btn-push" id="qlib-push-screener">
                            📤 推送 Top 50 至选股器
                    </button>
                </div>
                ${trustSummary}
                ${renderValidationSummary(validation, { pending: pendingValidation })}
                <div class="qlib-legend">
                    <span class="qlib-legend-item"><span class="qlib-heat-icon">🔥</span> 信号排名前5%</span>
                    <span class="qlib-legend-item"><span class="qlib-heat-icon">🟠</span> 信号排名前15%</span>
                    <span class="qlib-legend-item"><span class="qlib-heat-icon">🟡</span> 信号排名前30%</span>
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
                            <th class="qlib-th qlib-td-bar" title="候选排序分，不代表上涨概率">候选分</th>
                            <th class="qlib-th qlib-td-ic" title="池级历史回测状态，不代表单股上涨概率">验证</th>
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
        },

        async loadMLPredictions() {
            const el = document.getElementById('intel-ml-pred');
            if (!el) return;

            try {
                const data = await fetchShared('signalTop50', '/api/signals/top?limit=50');

                const signals = Array.isArray(data?.signals) ? data.signals : (data?.predictions || []);
                if (!data || signals.length === 0) {
                updateSignalTopIndex([], defaultSignalQuality());
                el.innerHTML = '<div class="text-muted text-center" style="padding:16px">暂无信号数据</div>';
                return;
            }

                updateSignalTopIndex(signals, defaultSignalQuality());
                this.renderSignalPool(data, null, { pendingValidation: true });
                const state = Intelligence.state || (Intelligence.state = {});
                const requestId = (state.signalValidationRequestId || 0) + 1;
                state.signalValidationRequestId = requestId;
                state.signalValidationLoadingPromise = new Promise((resolve) => {
                    setTimeout(() => {
                        resolve((async () => {
                            const validation = await withTimeout(
                                fetchShared('signalValidation50', '/api/signals/validation?top_n=50').catch(() => null),
                                3500,
                            );
                            if (validation?.success && state.signalValidationRequestId === requestId) {
                                const quality = validationQuality(validation);
                                updateSignalTopIndex(signals, quality);
                                this.renderSignalPool(data, validation);
                            }
                            return validation;
                        })());
                    }, 0);
                }).finally(() => {
                    if (state.signalValidationRequestId === requestId) {
                        state.signalValidationLoadingPromise = null;
                    }
                });
            } catch {
                el.innerHTML = '<div class="text-muted text-center" style="padding:16px">信号加载失败</div>';
                throw new Error('signal_pool_load_failed');
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

            const renderPending = () => {
                if (!isCurrent()) return;
                if (marker) marker.style.left = '50%';
                if (scoreEl) {
                    scoreEl.textContent = '计算中';
                    scoreEl.style.color = '#f59e0b';
                }
                if (sourcesEl) {
                    sourcesEl.innerHTML = '<span class="signal-src"><span class="signal-src-dot" style="background:#f59e0b"></span>全市场广度计算中</span>';
                }
            };
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
                const coverageInfo = typeof Intelligence.breadthCoverage === 'function'
                    ? Intelligence.breadthCoverage({ ...breadth, effective_count: effective, stock_count: stockCount })
                    : { reliable: true, effective, stockCount };
                const upRatio = classifiedTotal > 0 ? ((up / classifiedTotal) * 100).toFixed(0) : '--';
                const advanceDecline = down > 0 ? (up / down).toFixed(2) : '--';
                const displayScore = Math.round(score);
                const color = signalColor(displayScore);
                const source = breadth.source || (breadth.local_fallback ? 'local_stock_daily' : 'local_stock_daily');
                const ignoredLatestDate = breadth.ignored_latest_date;
                const ignoredLatestCovered = Number(breadth.ignored_latest_date_covered) || 0;

                if (marker) {
                    const pct = coverageInfo.reliable ? Math.max(0, Math.min(100, (score + 100) / 2)) : 50;
                    marker.style.left = pct + '%';
                }

                if (scoreEl) {
                    scoreEl.textContent = coverageInfo.reliable ? `广度分 ${formatSigned(displayScore)}` : '样本不足';
                    scoreEl.title = coverageInfo.reliable
                        ? `全市场广度分 = (上涨 ${formatCount(up)} - 下跌 ${formatCount(down)}) / 分类样本 ${formatCount(classifiedTotal)}；覆盖样本 ${formatCount(effective)}/${formatCount(stockCount)}`
                        : `覆盖不足：样本 ${formatCount(effective)}/${formatCount(stockCount)}；原始广度分 ${formatSigned(displayScore)}`;
                    scoreEl.style.color = coverageInfo.reliable ? color : '#f59e0b';
                }

                if (sourcesEl) {
                    const sources = [
                        { text: `来源 ${breadthSourceName(source)}`, color: '#94a3b8' },
                        { text: coverageInfo.reliable ? '口径 全市场广度' : '覆盖不足，方向仅供参考', color: coverageInfo.reliable ? color : '#f59e0b' },
                        { text: '公式 (上涨-下跌)/(上涨+下跌+平盘)', color },
                        { text: `含义 涨跌广度净占比 ${formatSigned(displayScore)}%`, color },
                        { text: `上涨占比 ${upRatio}%`, color },
                        { text: `涨跌比 ${advanceDecline}`, color },
                        { text: `涨停/跌停 ${formatCount(breadth.limit_up)}/${formatCount(breadth.limit_down)}`, color: '#f59e0b' },
                        { text: `样本 ${formatCount(effective)}/${formatCount(stockCount)}`, color: '#94a3b8' },
                        ...(breadth.latest_date ? [{ text: `交易日 ${breadth.latest_date}`, color: '#94a3b8' }] : []),
                        ...(ignoredLatestDate ? [{ text: `忽略 ${ignoredLatestDate} 零散样本 ${formatCount(ignoredLatestCovered)} 只`, color: '#f59e0b' }] : []),
                        ...(!coverageInfo.reliable ? [{ text: `原始广度分 ${formatSigned(displayScore)}`, color: '#94a3b8' }] : []),
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

            renderPending();
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
