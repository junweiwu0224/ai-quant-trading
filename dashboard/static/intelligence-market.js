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
    const normalizeStockCode = (value) => String(value || '')
        .trim()
        .replace(/\.(SH|SZ|BJ)$/i, '')
        .replace(/^(SH|SZ|BJ)/i, '');
    const MIN_BREADTH_COVERAGE_RATIO = 0.8;
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
    const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    const fetchWithSoftRetry = async (key, url, opts = {}) => {
        const { retries = 1, retryDelay = 1500, ...fetchOpts } = opts;
        let lastError = null;
        for (let attempt = 0; attempt <= retries; attempt += 1) {
            try {
                return await fetchOnce(`${key}:${attempt}`, url, fetchOpts);
            } catch (error) {
                lastError = error;
                if (attempt < retries) {
                    await delay(retryDelay);
                }
            }
        }
        throw lastError;
    };
    const softTimeout = (promise, timeoutMs) => new Promise((resolve) => {
        let settled = false;
        const finish = (value) => {
            if (settled) return;
            settled = true;
            clearTimeout(timer);
            resolve(value);
        };
        const timer = setTimeout(() => finish(null), timeoutMs);
        promise.then(
            (value) => finish(value),
            (error) => finish({ __error: error }),
        );
    });
    const scoreFromBreadth = (data) => {
        const up = Number(data?.up_count) || 0;
        const down = Number(data?.down_count) || 0;
        const flat = Number(data?.flat_count) || 0;
        const total = up + down + flat;
        if (total <= 0) return null;
        return ((up - down) / total) * 100;
    };
    const breadthCoverage = (data) => {
        const effective = Number(data?.effective_count) || Number(data?.latest_date_covered) || 0;
        const stockCount = Number(data?.stock_count) || Number(data?.total_stocks) || effective;
        const ratio = stockCount > 0 ? effective / stockCount : 1;
        return {
            effective,
            stockCount,
            ratio,
            reliable: ratio >= MIN_BREADTH_COVERAGE_RATIO,
        };
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
        market_news_multi_source: '市场新闻聚合',
    }[String(value || '').trim()] || String(value || '--'));
    const sourceName = (key) => ({
        concept: '概念',
        industry: '行业',
        fund_flow: '资金流',
    }[key] || key);
    const renderStatusPill = (data) => {
        const parts = [];
        parts.push(`<span class="intel-hotspot-pill">来源 ${safeHTML(sourceLabel(data.source || data.provider || '热点归因'))}</span>`);
        parts.push(`<span class="intel-hotspot-pill ${data.stale ? 'warn' : 'ok'}">${data.stale ? '缓存数据' : '实时数据'}</span>`);
        if (data.timestamp) {
            parts.push(`<span class="intel-hotspot-pill">更新 ${safeHTML(data.timestamp)}</span>`);
        }
        const errors = Array.isArray(data.partial_errors) ? data.partial_errors : [];
        if (errors.length > 0) {
            parts.push(`<span class="intel-hotspot-pill warn">数据源异常 ${safeHTML(errors.map(sourceName).join('、'))}</span>`);
        }
        if (data.coverage_note) {
            parts.push(`<span class="intel-hotspot-pill">${safeHTML(data.coverage_note)}</span>`);
        }
        return `<div class="intel-hotspot-status">${parts.join('')}</div>`;
    };
    const buildTreemapTiles = (sectors) => {
        const withWeights = sectors.map((sector) => ({
            ...sector,
            hasMarketValueWeight: Number(sector.total_mv) > 0,
            hasStockCountWeight: Number(sector.stock_count) > 0,
            weight: Math.max(
                0,
                Number(sector.total_mv) ||
                Number(sector.stock_count) ||
                ((Number(sector.up_count) || 0) + (Number(sector.down_count) || 0)) ||
                1,
            ),
            change: Number(sector.change_pct) || 0,
        }));
        const ranked = withWeights
            .map((sector) => ({
                ...sector,
                weight: Math.max(0, Number(sector.weight) || 0),
                change: Number(sector.change) || 0,
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
    const heatmapWeightLabel = (tiles, data) => {
        if (tiles.some(({ sector }) => Number(sector.total_mv) > 0)) {
            return '按板块总市值权重';
        }
        if (tiles.some(({ sector }) => Number(sector.stock_count) > 0) || data?.local_fallback) {
            return '本地覆盖股数权重';
        }
        return '板块数量权重';
    };
    const heatmapWeightMeta = (sector) => {
        const marketValue = Number(sector.total_mv);
        if (Number.isFinite(marketValue) && marketValue > 0) {
            return `${Math.round(marketValue).toLocaleString('zh-CN')}亿`;
        }
        const stockCount = Number(sector.stock_count);
        if (Number.isFinite(stockCount) && stockCount > 0) {
            return `${Math.round(stockCount).toLocaleString('zh-CN')}只`;
        }
        return '--';
    };
    const marketEntryStatusLabel = (status) => ({
        ready: '可用',
        degraded: '降级',
        deferred: '待接入',
    }[String(status || '').trim()] || '待接入');
    const renderMarketEntryMap = (data = {}) => {
        const source = data.source || (data.local_fallback ? 'local_stock_daily' : 'eastmoney_sector_board');
        const updatedAt = data.generated_at || data.timestamp || '';
        const coverageNote = data.coverage_note || (data.local_fallback ? '本地覆盖池降级热力' : '板块热力快照');
        const sectorStatus = data.success ? (data.stale || data.local_fallback ? 'degraded' : 'ready') : 'degraded';
        const entries = [
            {
                id: 'local-coverage',
                label: '本地覆盖池',
                universe: data.universe || (data.local_fallback ? 'local_stock_daily_coverage_pool' : 'all_a'),
                explanation: '全市场覆盖、广度、涨跌家数和本地缓存健康度',
                source: sourceLabel(source),
                updatedAt,
                status: data.local_fallback ? 'degraded' : 'ready',
                note: coverageNote,
            },
            {
                id: 'index',
                label: '指数',
                universe: 'index_watchlist',
                explanation: '宽基表现、市场广度和风险温度',
                source: '指数行情源',
                updatedAt,
                status: 'deferred',
                note: '指数入口将在 P1 后续切片接入，不伪装成股票表',
            },
            {
                id: 'sector-theme',
                label: '板块/主题',
                universe: data.universe || 'local_stock_daily_coverage_pool',
                explanation: '扩散和成分股、领涨/领跌、量能和后续动作',
                source: sourceLabel(source),
                updatedAt,
                status: sectorStatus,
                note: coverageNote,
                active: true,
            },
            {
                id: 'capital-flow',
                label: '资金流',
                universe: 'cross_asset_flow',
                explanation: '流入流出、成交榜和资金方向确认',
                source: '资金流源',
                updatedAt,
                status: 'deferred',
                note: '资金流入口待接入，当前不渲染为股票表',
            },
        ];
        return `<div class="intel-market-entry-map" role="list" aria-label="市场入口地图">
            ${entries.map((entry) => `<button type="button" class="intel-market-entry${entry.active ? ' is-active' : ''}" role="listitem" data-market-entry="${safeHTML(entry.id)}" data-status="${safeHTML(entry.status)}">
                <span class="entry-title">${safeHTML(entry.label)}</span>
                <span class="entry-meta">universe ${safeHTML(entry.universe)}</span>
                <span class="entry-meta">解释变量 ${safeHTML(entry.explanation)}</span>
                <span class="entry-meta">来源 ${safeHTML(entry.source)}</span>
                ${entry.updatedAt ? `<span class="entry-meta">更新 ${safeHTML(entry.updatedAt)}</span>` : ''}
                <span class="entry-status">状态 ${safeHTML(marketEntryStatusLabel(entry.status))}</span>
                ${entry.note ? `<span class="entry-note">${safeHTML(entry.note)}</span>` : ''}
            </button>`).join('')}
        </div>`;
    };
    const formatAmount = (value) => {
        const num = Number(value);
        if (!Number.isFinite(num) || num <= 0) return '--';
        if (num >= 1e8) return `${(num / 1e8).toFixed(1)}亿`;
        if (num >= 1e4) return `${(num / 1e4).toFixed(0)}万`;
        return `${Math.round(num)}`;
    };
    const normalizeSectorMembers = (data = {}) => {
        const members = Array.isArray(data.members) ? data.members : [];
        return members.map((item) => ({
            code: normalizeStockCode(item.code),
            name: item.name || item.code || '',
            sector_name: item.sector_name || data.sector_name || '',
            industry: item.industry || item.sector_name || data.sector_name || '',
            price: item.price ?? null,
            change_pct: item.change_pct ?? null,
            amount: item.amount ?? null,
            updated_at: item.updated_at || item.generated_at || item.timestamp || data.generated_at || data.timestamp || '',
            source: item.source || data.source || 'local_stock_daily',
            rank_reason: item.rank_reason || `${data.sector_name || '板块'}成分股`,
        })).filter((item) => item.code);
    };
    const compactText = (...items) => items
        .map((item) => String(item ?? '').trim())
        .filter(Boolean);
    const signalConfidenceLabel = (value) => ({
        validated_positive: '验证偏正',
        positive: '验证偏正',
        validated_negative: '验证偏弱',
        negative: '验证偏弱',
        sample_insufficient: '样本不足',
        insufficient: '样本不足',
        unverified: '待验证',
    }[String(value || '').trim()] || String(value || '').trim() || '待验证');
    const sectorFallbackSummary = (data, members) => {
        const changes = members.map((item) => Number(item.change_pct)).filter(Number.isFinite);
        const upCount = members.filter((item) => Number(item.change_pct) > 0).length;
        const downCount = members.filter((item) => Number(item.change_pct) < 0).length;
        const flatCount = Math.max(members.length - upCount - downCount, 0);
        const avgChange = changes.length ? changes.reduce((sum, value) => sum + value, 0) / changes.length : null;
        const leader = members[0] || null;
        return {
            member_count: Number(data.total_count ?? members.length) || members.length,
            display_count: Number(data.display_count ?? members.length) || members.length,
            avg_change_pct: avgChange,
            up_count: upCount,
            down_count: downCount,
            flat_count: flatCount,
            leader,
            direction: upCount > downCount ? '扩散偏强' : (downCount > upCount ? '扩散偏弱' : '多空均衡'),
        };
    };
    const sectorFallbackLiquidity = (members) => {
        const withAmount = members
            .map((item) => ({ ...item, amount: Number(item.amount) }))
            .filter((item) => Number.isFinite(item.amount) && item.amount > 0);
        const totalAmount = withAmount.reduce((sum, item) => sum + item.amount, 0);
        const topAmountMember = withAmount.sort((a, b) => b.amount - a.amount)[0] || null;
        return {
            total_amount: totalAmount || null,
            top_amount_member: topAmountMember,
            coverage_note: totalAmount ? '以前端成分股 amount 汇总作为量能代理' : '',
            missing_reason: totalAmount ? '' : '当前成分股缺少成交额字段',
        };
    };
    const sectorFallbackSignalOverlap = (members) => {
        const signalIndex = (Intelligence.state || {}).signalTopIndex || null;
        const matched = members
            .map((stock) => ({ stock, signal: signalEntryForStock(stock, signalIndex) }))
            .filter((item) => item.signal);
        return {
            count: matched.length,
            items: matched.slice(0, 6).map(({ stock, signal }) => ({
                code: stock.code,
                name: stock.name || stock.code,
                signal_score: signal?.score,
                signal_confidence: signalQualityLabel(signal),
            })),
            missing_reason: matched.length ? '' : 'Signal 覆盖池暂无本板块成分股',
        };
    };
    const renderSectorEvidenceTags = (items) => {
        const tags = compactText(...items);
        if (!tags.length) return '';
        return `<div class="intel-sector-evidence-tags">${tags.map((item) => `<span>${safeHTML(item)}</span>`).join('')}</div>`;
    };
    const renderSectorEvidenceSection = (title, body, tags = [], extra = '') => `<div class="intel-sector-evidence-section">
        <div class="intel-sector-evidence-title">${safeHTML(title)}</div>
        <div class="intel-sector-evidence-body">${safeHTML(body || '--')}</div>
        ${renderSectorEvidenceTags(tags)}
        ${extra}
    </div>`;
    const renderSectorEvidenceActions = (actions, sectorName) => {
        const items = Array.isArray(actions) ? actions : [];
        if (!items.length) return '';
        return `<div class="intel-sector-evidence-action-row">
            ${items.map((action) => {
                const id = String(action?.id || '').trim();
                const label = action?.label || id || '后续动作';
                const disabled = action?.status === 'deferred' || action?.enabled === false;
                if (id === 'send_screener' || id === 'send-sector-screener') {
                    return `<button type="button" data-intel-action="send-sector-screener" data-sector-name="${safeHTML(sectorName)}">${safeHTML(label)}</button>`;
                }
                return `<span class="${disabled ? 'is-disabled' : ''}">${safeHTML(label)}${disabled ? ' · 待接入' : ''}</span>`;
            }).join('')}
        </div>`;
    };
    const renderSectorEvidenceContext = (data = {}, members = []) => {
        const evidence = data.evidence_context || {};
        const summary = evidence.summary || sectorFallbackSummary(data, members);
        const liquidity = evidence.liquidity || sectorFallbackLiquidity(members);
        const signalOverlap = evidence.signal_overlap || sectorFallbackSignalOverlap(members);
        const newsResearch = evidence.news_research || {};
        const relatedIndex = evidence.related_index || {};
        const sectorName = data.sector_name || evidence.sector_name || '板块';
        const leader = summary.leader || null;
        const topAmountMember = liquidity.top_amount_member || null;
        const totalAmount = Number(liquidity.total_amount);
        const totalAmountYi = Number(liquidity.total_amount_yi);
        const liquidityLabel = Number.isFinite(totalAmount) && totalAmount > 0
            ? `成交额代理 ${formatAmount(totalAmount)}`
            : (Number.isFinite(totalAmountYi) && totalAmountYi > 0 ? `成交额代理 ${totalAmountYi.toFixed(1)}亿` : (liquidity.missing_reason || '暂无量能代理'));
        const signalCount = Number(signalOverlap.count ?? signalOverlap.covered_count ?? 0) || 0;
        const signalItems = Array.isArray(signalOverlap.items) ? signalOverlap.items : [];
        const leadSignal = signalItems[0] || null;
        const signalBody = signalCount > 0
            ? `信号重叠 ${formatCount(signalCount)}只${leadSignal ? ` · ${signalConfidenceLabel(leadSignal.signal_confidence)}` : ''}`
            : (signalOverlap.missing_reason || 'Signal 覆盖池暂无本板块成分股');
        const newsItems = Array.isArray(newsResearch.items) ? newsResearch.items : [];
        const indexItems = Array.isArray(relatedIndex.items) ? relatedIndex.items : [];
        const actionHtml = renderSectorEvidenceActions(evidence.next_actions || [
            { id: 'send_screener', label: '发送到选股器' },
            { id: 'open_stock', label: '打开成分股工作台' },
        ], sectorName);
        return `<div class="intel-sector-evidence" aria-label="${safeHTML(`${sectorName}板块证据上下文`)}">
            <div class="intel-sector-evidence-grid">
                ${renderSectorEvidenceSection('板块摘要',
                    `${summary.direction || '多空均衡'} · 上涨 ${formatCount(summary.up_count)} 下跌 ${formatCount(summary.down_count)} 平盘 ${formatCount(summary.flat_count)}`,
                    [
                        `全量 ${formatCount(summary.member_count)}只`,
                        `展示 ${formatCount(summary.display_count)}只`,
                        Number.isFinite(Number(summary.avg_change_pct)) ? `均值 ${formatPct(summary.avg_change_pct)}` : '',
                        leader ? `领涨 ${leader.name || leader.code || '--'} ${formatPct(leader.change_pct)}` : '',
                    ])}
                ${renderSectorEvidenceSection('量能代理',
                    liquidityLabel,
                    [
                        liquidity.coverage_note || '',
                        topAmountMember ? `最大成交 ${topAmountMember.name || topAmountMember.code || '--'} ${formatAmount(topAmountMember.amount)}` : '',
                    ])}
                ${renderSectorEvidenceSection('Signal 重叠',
                    signalBody,
                    [
                        signalOverlap.provider ? `来源 ${signalOverlap.provider}` : '',
                        signalOverlap.model_version ? `模型 ${signalOverlap.model_version}` : '',
                        signalOverlap.latest_date ? `更新 ${signalOverlap.latest_date}` : '',
                        leadSignal ? `样本 ${leadSignal.name || leadSignal.code || '--'}` : '',
                    ])}
                ${renderSectorEvidenceSection('新闻/研报',
                    newsItems.length ? `已关联 ${formatCount(newsItems.length)} 条` : (newsResearch.missing_reason || '板块级新闻/研报证据尚未接入'),
                    newsItems.slice(0, 2).map((item) => item.title || item.source || '新闻证据'))}
                ${renderSectorEvidenceSection('关联指数',
                    indexItems.length ? `已关联 ${formatCount(indexItems.length)} 个指数` : (relatedIndex.missing_reason || '本地暂未维护关联指数映射'),
                    indexItems.slice(0, 2).map((item) => compactText(item.name, item.code).join(' ')))}
                ${renderSectorEvidenceSection('后续动作',
                    '保留板块上下文继续研究',
                    compactText('打开成分股', '生成篮子'),
                    actionHtml)}
            </div>
        </div>`;
    };
    const renderSectorMembersPanel = (data = {}) => {
        const members = normalizeSectorMembers(data);
        const sectorName = data.sector_name || '板块';
        const effective = Number(data.effective_count ?? data.total_count ?? members.length) || 0;
        const total = Number(data.total_count ?? effective) || 0;
        const display = Number(data.display_count ?? members.length) || members.length;
        const trustParts = [
            `来源 ${sourceLabel(data.source || data.provider || 'local_stock_daily')}`,
            data.generated_at || data.timestamp ? `更新 ${data.generated_at || data.timestamp}` : '',
            `有效 ${formatCount(effective)}/${formatCount(total)}`,
            `展示 ${formatCount(display)}`,
            data.coverage_note || '',
        ].filter(Boolean);
        if (!members.length) {
            return `<div class="intel-sector-members" data-sector-name="${safeHTML(sectorName)}">
                <div class="intel-sector-members-head">
                    <div>
                        <strong>${safeHTML(sectorName)} 板块成分</strong>
                        <span>${trustParts.map(safeHTML).join(' · ')}</span>
                    </div>
                </div>
                ${renderSectorEvidenceContext(data, members)}
                <div class="intel-sector-members-empty">${safeHTML(data.missing_reason || '暂无成分股数据')}</div>
            </div>`;
        }
        return `<div class="intel-sector-members" data-sector-name="${safeHTML(sectorName)}">
            <div class="intel-sector-members-head">
                <div>
                    <strong>${safeHTML(sectorName)} 板块成分</strong>
                    <span>${trustParts.map(safeHTML).join(' · ')}</span>
                </div>
                <button type="button" class="intel-sector-members-action" data-intel-action="send-sector-screener" data-sector-name="${safeHTML(sectorName)}">发送到选股器</button>
            </div>
            ${renderSectorEvidenceContext(data, members)}
            <div class="intel-sector-member-table" role="table" aria-label="${safeHTML(sectorName)}板块成分股">
                <div class="intel-sector-member-row is-head" role="row">
                    <span>股票</span><span>涨跌幅</span><span>价格</span><span>成交额</span><span>操作</span>
                </div>
                ${members.map((item) => {
                    const cls = (Number(item.change_pct) || 0) >= 0 ? 'up' : 'down';
                    return `<button type="button" class="intel-sector-member-row" role="row" data-intel-action="open-sector-stock" data-code="${safeHTML(item.code)}">
                        <span><strong>${safeHTML(item.name || item.code)}</strong><em>${safeHTML(item.code)}</em></span>
                        <span class="${cls}">${formatPct(item.change_pct)}</span>
                        <span>${item.price != null ? safeHTML(Number(item.price).toFixed(2)) : '--'}</span>
                        <span>${safeHTML(formatAmount(item.amount))}</span>
                        <span>打开</span>
                    </button>`;
                }).join('')}
            </div>
        </div>`;
    };
    const bindHeatmapDrilldown = (el) => {
        if (!el) return;
        const dataset = el.dataset || (el.__aiqDataset || (el.__aiqDataset = {}));
        if (dataset.sectorDrilldownBound === '1') return;
        dataset.sectorDrilldownBound = '1';
        el.addEventListener('click', (event) => {
            const sectorButton = event.target.closest('[data-intel-action="select-sector"]');
            if (sectorButton) {
                event.preventDefault();
                const sectorName = String(sectorButton.dataset.sectorName || sectorButton.dataset.concept || '').trim();
                const grouping = String(sectorButton.dataset.grouping || 'industry').trim() || 'industry';
                if (!sectorName) return;
                const state = Intelligence.state || (Intelligence.state = {});
                state.latestSectorMembersPromise = Intelligence.loadSectorMembers?.(sectorName, { grouping }) || null;
                return;
            }
            const stockButton = event.target.closest('[data-intel-action="open-sector-stock"]');
            if (stockButton) {
                event.preventDefault();
                const code = normalizeStockCode(stockButton.dataset.code);
                const state = Intelligence.state || {};
                const sectorData = state.latestSectorMembers || {};
                const members = normalizeSectorMembers(sectorData);
                const stock = members.find((item) => item.code === code) || { code };
                if (code && typeof App.openStockDetail === 'function') {
                    App.openStockDetail(code, {
                        stock,
                        source: 'market:sector-heatmap',
                        sector_name: sectorData.sector_name || stock.sector_name || '',
                        context_type: 'sector',
                        contextList: members,
                        source_context: sectorData.source_context || {
                            source: 'market:sector-heatmap',
                            sourceLabel: '板块',
                            context_type: 'sector',
                            sector_name: sectorData.sector_name || stock.sector_name || '',
                        },
                        price: stock.price,
                        change_pct: stock.change_pct,
                        updated_at: stock.updated_at || sectorData.generated_at || sectorData.timestamp,
                        rank_reason: stock.rank_reason,
                        preferDirectOpen: true,
                    });
                }
                return;
            }
            const sendButton = event.target.closest('[data-intel-action="send-sector-screener"]');
            if (sendButton) {
                event.preventDefault();
                const sectorName = String(sendButton.dataset.sectorName || '').trim();
                const sectorData = (Intelligence.state || {}).latestSectorMembers || {};
                const members = normalizeSectorMembers(sectorData);
                const pool = members.map((item) => item.code).filter(Boolean);
                if (pool.length > 0 && typeof App.emit === 'function') {
                    App.emit('iwencai:send-to-screener', {
                        pool,
                        query: sectorName ? `板块成分: ${sectorName}` : '板块成分候选池',
                        source_context: sectorData.source_context || {
                            source: 'market:sector-heatmap',
                            sourceLabel: '板块',
                            context_type: 'sector',
                            sector_name: sectorName,
                        },
                    });
                }
            }
        });
    };
    const isIntelligenceTabActive = () => {
        if (globalThis.App?.currentTab === 'intelligence') return true;
        const activeNav = document.querySelector?.('.nav-link.active')?.dataset?.tab || '';
        if (activeNav === 'intelligence') return true;
        const panel = document.getElementById?.('tab-intelligence');
        return panel?.classList?.contains?.('active') === true;
    };
    const wakeActiveIntelligencePage = () => {
        const state = Intelligence.state || (Intelligence.state = {});
        if (globalThis.__AUTH_GATE_REQUIRED__ === true) return null;
        if (state.loadedModules?.heatmap === true) return null;
        if (state.marketBundleWakePromise) return state.marketBundleWakePromise;
        if (!document.getElementById?.('intel-heatmap') || !isIntelligenceTabActive()) return null;

        state.marketBundleWakePromise = Promise.resolve(state.loadingPromise)
            .catch(() => null)
            .then(() => {
                if (globalThis.__AUTH_GATE_REQUIRED__ === true) return null;
                if (state.loadedModules?.heatmap === true) return null;
                if (!document.getElementById?.('intel-heatmap') || !isIntelligenceTabActive()) return null;
                if (typeof Intelligence.loadHeatmap !== 'function') return null;
                return Intelligence.loadHeatmap.call(Intelligence).then(() => {
                    const loadedModules = state.loadedModules || (state.loadedModules = {});
                    loadedModules.heatmap = true;
                    state.marketLoaded = ['sentiment', 'news', 'heatmap', 'hotspot'].every((name) => loadedModules[name] === true);
                    state.loaded = ['sentiment', 'news', 'heatmap', 'hotspot', 'signals', 'signalBar']
                        .every((name) => loadedModules[name] === true);
                    return null;
                });
            })
            .finally(() => {
                state.marketBundleWakePromise = null;
            });
        return state.marketBundleWakePromise;
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
    const renderNewsSourceStrip = (data, count) => {
        const source = data.source || '市场新闻';
        const timestamp = data.timestamp || '暂无更新时间';
        const generatedAt = data.generated_at || '';
        const coverageNote = data.coverage_note || data.note || '滚动新闻快讯，按时间倒序展示';
        const errors = Array.isArray(data.partial_errors)
            ? data.partial_errors
            : (Array.isArray(data.errors) ? data.errors : []);
        const parts = [
            `新闻源 ${sourceLabel(source)}`,
            `更新 ${timestamp}`,
        ];
        if (generatedAt && generatedAt !== timestamp) {
            parts.push(`生成 ${generatedAt}`);
        }
        parts.push(`展示 ${formatCount(count)} 条`);
        if (data.source_unavailable) {
            parts.push('数据源异常');
        }
        if (data.stale) {
            parts.push('缓存数据');
        }
        if (data.stale_reason) {
            parts.push(`原因 ${data.stale_reason}`);
        }
        if (errors.length > 0) {
            const errorPreview = errors.slice(0, 2).map((item) => String(item || '').trim()).filter(Boolean).join('；');
            parts.push(`部分新闻源异常 ${formatCount(errors.length)} 个${errorPreview ? `：${errorPreview}` : ''}`);
        }
        if (coverageNote) {
            parts.push(coverageNote);
        }
        return `<div class="intel-news-source-strip">${parts.map((part) => `<span>${safeHTML(part)}</span>`).join('')}</div>`;
    };
    const renderNewsValueSummary = (news, data = {}) => {
        const items = Array.isArray(news) ? news : [];
        const stockKeys = new Set();
        const topicNames = new Set();
        let linkedNews = 0;
        let positive = 0;
        let neutral = 0;
        let negative = 0;
        for (const item of items) {
            const stocks = Array.isArray(item?.stocks) ? item.stocks : [];
            if (stocks.length > 0) {
                linkedNews += 1;
                for (const stock of stocks) {
                    const key = String(stock?.code || stock?.name || '').trim();
                    if (key) stockKeys.add(key);
                }
            }
            for (const topic of (Array.isArray(item?.topics) ? item.topics : [])) {
                const name = String(topic?.name || '').trim();
                if (name) topicNames.add(name);
            }
            const sentiment = Number(item?.sentiment) || 0;
            if (sentiment > 0.2) positive += 1;
            else if (sentiment < -0.2) negative += 1;
            else neutral += 1;
        }
        const linkedNewsCount = Number.isFinite(Number(data.linked_news_count)) ? Number(data.linked_news_count) : linkedNews;
        const linkedStockCount = Number.isFinite(Number(data.linked_stock_count)) ? Number(data.linked_stock_count) : stockKeys.size;
        const topicCount = Number.isFinite(Number(data.topic_count)) ? Number(data.topic_count) : topicNames.size;
        const ranking = data.ranking || {};
        const rankingLabel = ranking.method === 'actionable_value'
            ? '排序 价值优先'
            : (ranking.method ? `排序 ${ranking.method}` : '');
        const rankingDescription = ranking.description || '';
        const qualityNote = items.length === 0
            ? '当前新闻源无可用记录'
            : linkedNewsCount > 0
                ? '优先关注已映射个股的新闻'
                : '仅快讯流，暂未映射到个股';
        return `<div class="intel-news-value-summary">
            <span class="intel-news-value-title">价值摘要</span>
            <span>关联新闻 ${formatCount(linkedNewsCount)}/${formatCount(items.length)} 条</span>
            <span>关联股票 ${formatCount(linkedStockCount)} 只</span>
            <span>主题 ${formatCount(topicCount)} 个</span>
            <span>情绪 正${formatCount(positive)} 中${formatCount(neutral)} 负${formatCount(negative)}</span>
            ${rankingLabel ? `<span>${safeHTML(rankingLabel)}</span>` : ''}
            ${rankingDescription ? `<span>${safeHTML(rankingDescription)}</span>` : ''}
            <span>${safeHTML(qualityNote)}</span>
        </div>`;
    };
    const signalEntryForStock = (stock, signalIndex) => {
        if (!signalIndex || typeof signalIndex.get !== 'function') return null;
        const codeKey = normalizeStockCode(stock?.code);
        if (codeKey && signalIndex.get(codeKey)) return signalIndex.get(codeKey);
        const labelKey = String(stock?.label || stock?.name || '').trim();
        if (labelKey && signalIndex.get(`name:${labelKey}`)) return signalIndex.get(`name:${labelKey}`);
        return null;
    };
    const signalQualityLabel = (signal) => {
        const quality = signal?.quality || {};
        if (quality.tradable && quality.confidence === 'validated_positive') return '验证偏正';
        if (quality.validated && !quality.sampleEnough) return '样本不足';
        if (quality.validated) return quality.label || '已验证';
        return '待验证';
    };
    const signalQualityTitleLabel = (signal) => {
        const label = signalQualityLabel(signal);
        return label === '待验证' ? '待历史验证' : label;
    };
    const signalOverlapLabel = (count, signal) => `信号重叠 ${formatCount(count)}只 · ${signalQualityLabel(signal)}`;
    const topicScreenerPool = (topic) => {
        const seen = new Set();
        const pushCode = (stock, pool) => {
            const code = normalizeStockCode(stock?.code);
            if (!code || seen.has(code)) return;
            seen.add(code);
            pool.push(code);
        };
        const pool = [];
        for (const stock of (Array.isArray(topic?.aiMatches) ? topic.aiMatches : [])) {
            pushCode(stock, pool);
        }
        for (const stock of (Array.isArray(topic?.stocks) ? topic.stocks : [])) {
            pushCode(stock, pool);
        }
        return pool;
    };
    const renderActionableTopicBoard = (news, signalIndex = null) => {
        const items = Array.isArray(news) ? news : [];
        const topicMap = new Map();
        for (const item of items) {
            const topics = Array.isArray(item?.topics) ? item.topics : [];
            const stocks = Array.isArray(item?.stocks) ? item.stocks : [];
            for (const topic of topics) {
                const name = String(topic?.name || '').trim();
                if (!name) continue;
                if (!topicMap.has(name)) {
                    topicMap.set(name, {
                        name,
                        newsCount: 0,
                        sentimentSum: 0,
                        titles: [],
                        stocks: new Map(),
                    });
                }
                const bucket = topicMap.get(name);
                bucket.newsCount += 1;
                bucket.sentimentSum += Number(item?.sentiment) || 0;
                const title = String(item?.title || '').trim();
                if (title && bucket.titles.length < 2) bucket.titles.push(title);
                for (const stock of stocks) {
                    const code = String(stock?.code || '').trim();
                    const label = String(stock?.name || stock?.code || '').trim();
                    const key = code || label;
                    if (key && !bucket.stocks.has(key)) {
                        bucket.stocks.set(key, { code, label });
                    }
                }
            }
        }
        const topics = [...topicMap.values()]
            .map((topic) => ({
                ...topic,
                avgSentiment: topic.newsCount > 0 ? topic.sentimentSum / topic.newsCount : 0,
                stocks: [...topic.stocks.values()].map((stock) => ({
                    ...stock,
                    signal: signalEntryForStock(stock, signalIndex),
                })),
            }))
            .map((topic) => ({
                ...topic,
                aiMatches: topic.stocks.filter((stock) => stock.signal),
            }))
            .sort((a, b) => {
                if (b.newsCount !== a.newsCount) return b.newsCount - a.newsCount;
                return Math.abs(b.avgSentiment) - Math.abs(a.avgSentiment);
            })
            .slice(0, 4);
        if (topics.length === 0) return '';

        return `<div class="intel-news-topic-board">
            <div class="intel-news-topic-board-head">
                <span>可行动主题</span>
                <span>按新闻频次和情绪强度排序</span>
            </div>
            <div class="intel-news-topic-grid">
                ${topics.map((topic) => {
                    const sentimentCls = topic.avgSentiment > 0.2 ? 'up' : topic.avgSentiment < -0.2 ? 'down' : 'neutral';
                    const title = topic.titles[0] || '关联新闻';
                    const screenerPool = topicScreenerPool(topic);
                    const leadSignal = topic.aiMatches[0]?.signal || null;
                    const overlapLabel = topic.aiMatches.length > 0 ? signalOverlapLabel(topic.aiMatches.length, leadSignal) : '';
                    const queryLabel = topic.aiMatches.length > 0
                        ? `新闻主题: ${topic.name} · ${overlapLabel}`
                        : `新闻主题: ${topic.name} · 关联 ${formatCount(screenerPool.length)}只`;
                    const screenerAction = screenerPool.length > 0
                        ? `<button type="button" class="intel-topic-send-btn" data-intel-action="send-topic-screener" data-concept="${safeHTML(topic.name)}" data-pool="${safeHTML(screenerPool.join(','))}" data-query="${safeHTML(queryLabel)}" aria-label="${safeHTML(`把${topic.name}关联股票送入选股器`)}" title="${safeHTML(`把${topic.name}关联股票送入选股器`)}">入选股器</button>`
                        : '';
                    const stocks = topic.stocks.slice(0, 3).map((stock) => {
                        const label = stock.label || stock.code || '';
                        const signalScore = Number(stock.signal?.score);
                        const signalScoreText = Number.isFinite(signalScore) ? signalScore.toFixed(3) : '';
                        const signalBadge = signalScoreText ? `<span class="intel-topic-stock-ai">信号 ${safeHTML(signalScoreText)}</span>` : '';
                        const signalAttr = signalScoreText ? ` data-ai-score="${safeHTML(signalScoreText)}"` : '';
                        const actionLabel = signalScoreText
                            ? `打开${label}详情，AI候选信号分${signalScoreText}，${signalQualityTitleLabel(stock.signal)}`
                            : `打开${label}详情`;
                        return `<button type="button" class="intel-topic-stock${signalScoreText ? ' has-ai-overlap' : ''}" data-intel-action="open-news-stock" data-code="${safeHTML(stock.code)}" data-name="${safeHTML(label)}"${signalAttr} aria-label="${safeHTML(actionLabel)}" title="${safeHTML(actionLabel)}">${safeHTML(label)}${signalBadge}</button>`;
                    }).join('');
                    const aiBadge = topic.aiMatches.length > 0 ? `<span class="intel-topic-ai-badge">${safeHTML(overlapLabel)}</span>` : '';
                    return `<div class="intel-topic-card${topic.aiMatches.length > 0 ? ' has-ai-overlap' : ''}">
                        <button type="button" class="intel-topic-card-title" data-intel-action="query-hotspot" data-concept="${safeHTML(topic.name)}" data-source="intelligence:news-topic-board" aria-label="${safeHTML(`用问财检索${topic.name}`)}" title="${safeHTML(`用问财检索${topic.name}`)}">${safeHTML(topic.name)}</button>
                        <div class="intel-topic-card-meta">
                            <span>${formatCount(topic.newsCount)}条新闻</span>
                            <span>${formatCount(topic.stocks.length)}只股票</span>
                            ${aiBadge}
                            <span class="${sentimentCls}">情绪 ${formatSigned(topic.avgSentiment, 2)}</span>
                        </div>
                        <div class="intel-topic-card-titleline">${safeHTML(title)}</div>
                        ${stocks ? `<div class="intel-topic-stock-row">${stocks}</div>` : ''}
                        ${screenerAction ? `<div class="intel-topic-action-row">${screenerAction}</div>` : ''}
                    </div>`;
                }).join('')}
            </div>
        </div>`;
    };
    const renderNewsItems = (news) => news.map((n) => {
        const sentVal = n.sentiment || 0;
        const sentCls = sentVal > 0.2 ? 'tag-up' : sentVal < -0.2 ? 'tag-down' : '';
        const icon = sentVal > 0.2 ? '▲' : sentVal < -0.2 ? '▼' : '●';
        const iconCls = sentVal > 0.2 ? 'text-up' : sentVal < -0.2 ? 'text-down' : 'text-muted';
        const tags = (n.stocks || []).slice(0, 3).map((s) => {
            const code = s.code || '';
            const label = s.name || s.code || '';
            const actionLabel = `打开${label}详情`;
            return `<button type="button" class="intel-news-tag ${sentCls}" data-intel-action="open-news-stock" data-code="${safeHTML(code)}" data-name="${safeHTML(label)}" aria-label="${safeHTML(actionLabel)}" title="${safeHTML(actionLabel)}">${safeHTML(label)}</button>`;
        }).join('');
        const topicTags = (n.topics || []).slice(0, 3).map((topic) => {
            const name = topic.name || '';
            const actionLabel = `用问财检索${name}`;
            return `<button type="button" class="intel-news-tag intel-news-topic" data-intel-action="query-hotspot" data-concept="${safeHTML(name)}" data-source="intelligence:news-topic" aria-label="${safeHTML(actionLabel)}" title="${safeHTML(actionLabel)}">${safeHTML(name)}</button>`;
        }).join('');
        const valueScore = Number(n.value_score);
        const valueScoreTag = Number.isFinite(valueScore)
            ? `<span class="intel-news-tag intel-news-value">价值 ${safeHTML(valueScore.toFixed(1))}</span>`
            : '';
        const valueReasonTags = (Array.isArray(n.value_reasons) ? n.value_reasons : []).slice(0, 3)
            .map((reason) => `<span class="intel-news-tag intel-news-value-reason">${safeHTML(reason)}</span>`)
            .join('');
        const source = n.source ? `<span>${App.escapeHTML(n.source)}</span>` : '';
        return `<div class="intel-news-item">
                        <span class="intel-news-icon ${iconCls}">${icon}</span>
                        <div class="intel-news-body">
                            <div class="intel-news-title">${App.escapeHTML(n.title || '')}</div>
                            <div class="intel-news-meta">
                                ${source}
                                <span>${App.escapeHTML(n.time || '')}</span>
                                ${valueScoreTag}
                                ${valueReasonTags}
                                ${tags}
                                ${topicTags}
                            </div>
                        </div>
                    </div>`;
    }).join('');
    const renderNewsContent = (data, news) => {
        const signalIndex = (Intelligence.state || {}).signalTopIndex || null;
        const newsMeta = renderNewsSourceStrip({ ...data, source: data.source || news[0]?.source || '市场新闻' }, news.length);
        const newsValueSummary = renderNewsValueSummary(news, data);
        const topicBoard = renderActionableTopicBoard(news, signalIndex);
        return newsMeta + newsValueSummary + topicBoard + renderNewsItems(news);
    };
    const refreshNewsTopicBoardWithSignals = () => {
        const state = Intelligence.state || {};
        const latest = state.latestNewsPayload;
        const el = document.getElementById('intel-news-list');
        if (!latest || !el || !Array.isArray(latest.news) || latest.news.length === 0) return;

        const signalIndex = state.signalTopIndex || null;
        const topicBoard = renderActionableTopicBoard(latest.news, signalIndex);
        if (topicBoard && typeof el.querySelector === 'function' && typeof document.createElement === 'function') {
            const currentBoard = el.querySelector('.intel-news-topic-board');
            if (currentBoard && typeof currentBoard.replaceWith === 'function') {
                const wrapper = document.createElement('div');
                wrapper.innerHTML = topicBoard;
                if (wrapper.firstElementChild) {
                    currentBoard.replaceWith(wrapper.firstElementChild);
                    return;
                }
            }
        }
        el.innerHTML = renderNewsContent(latest.data, latest.news);
    };

    Object.assign(Intelligence, {
        fetchMarketJSON: fetchOnce,
        scoreFromBreadth,
        breadthCoverage,
        refreshNewsTopicBoardWithSignals,

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
                const coverageInfo = breadthCoverage({ ...data, effective_count: Number(data.effective_count) || Number(data.latest_date_covered) || total });
                const effective = coverageInfo.effective || total;
                const stockCount = coverageInfo.stockCount || effective;
                const staleCount = Math.max(0, stockCount - effective);
                const breadthScore = scoreFromBreadth(data);
                const displayBreadthScore = breadthScore == null ? null : Math.round(breadthScore);
                const isReliable = coverageInfo.reliable;
                const sentimentLabel = !isReliable || displayBreadthScore == null ? '覆盖不足' : displayBreadthScore >= 10 ? '偏多' : displayBreadthScore <= -10 ? '偏空' : '中性';
                const sentimentCls = !isReliable || displayBreadthScore == null ? 'text-muted' : displayBreadthScore >= 10 ? 'text-up' : displayBreadthScore <= -10 ? 'text-down' : 'text-muted';
                const coverage = stockCount
                    ? `${formatCount(effective)}/${formatCount(stockCount)}`
                    : formatCount(effective);
                const stale = data.stale ? ' · 缓存' : '';
                const source = data.source || (data.local_fallback ? 'local_stock_daily' : 'local_stock_daily');
                const ignoredLatestDate = data.ignored_latest_date;
                const ignoredLatestCovered = Number(data.ignored_latest_date_covered) || 0;
                const minCoverage = Number(data.min_selected_date_coverage_pct);
                const minCoverageText = Number.isFinite(minCoverage) && minCoverage > 0
                    ? formatCount(minCoverage)
                    : '80';
                const ignoredLatestNote = ignoredLatestDate
                    ? `已忽略 ${safeHTML(ignoredLatestDate)} 零散样本 ${formatCount(ignoredLatestCovered)} 只，低于 ${safeHTML(minCoverageText)}% 覆盖阈值`
                    : '';
                const sentHeader = document.querySelector('.intel-sentiment-card h3');
                if (sentHeader) {
                    const scoreText = !isReliable
                        ? `样本 ${coverage}`
                        : (displayBreadthScore == null ? '--' : formatSigned(displayBreadthScore, 0));
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
                        <span>来源 ${safeHTML(sourceLabel(source))}</span>
                        <span>口径 全市场上涨下跌广度</span>
                        <span>公式 (上涨-下跌)/(上涨+下跌+平盘)</span>
                        ${ignoredLatestNote ? `<span>${ignoredLatestNote}</span>` : ''}
                        ${!isReliable ? '<span>覆盖不足，方向仅供参考</span>' : ''}
                    </div>
                `;
            } catch (error) {
                el.innerHTML = '<div class="text-muted text-center">加载失败</div>';
                throw error;
            }
        },

        async loadNews() {
            const el = document.getElementById('intel-news-list');
            const countEl = document.getElementById('intel-news-count');
            if (!el) return;

            try {
                const data = await fetchWithSoftRetry('news', '/api/market/news');
                if (!data.success) {
                    el.innerHTML = '<div class="text-muted text-center">加载失败</div>';
                    return;
                }

                const news = data.news || [];
                if (countEl) countEl.textContent = news.length;
                const timestampEl = document.getElementById('intel-timestamp');
                if (timestampEl && data.timestamp) timestampEl.textContent = data.timestamp;

                if (news.length === 0) {
                    const state = Intelligence.state || (Intelligence.state = {});
                    state.latestNewsPayload = { data, news };
                    el.innerHTML = `<div class="text-muted text-center intel-news-empty">
                        <div>暂无市场新闻</div>
                        ${renderNewsSourceStrip(data, 0)}
                        ${renderNewsValueSummary(news, data)}
                    </div>`;
                    return;
                }

                const state = Intelligence.state || (Intelligence.state = {});
                state.latestNewsPayload = { data, news };
                el.innerHTML = renderNewsContent(data, news);
            } catch (error) {
                console.warn('情报新闻加载失败', error);
                el.innerHTML = '<div class="text-muted text-center">加载失败</div>';
            }
        },

        async loadHeatmap() {
            const el = document.getElementById('intel-heatmap');
            if (!el) return;
            bindHeatmapDrilldown(el);

            const renderHeatmap = (data) => {
                if (!data.success) {
                    el.innerHTML = '<div class="text-muted text-center">加载失败</div>';
                    return false;
                }

                const sectors = data.sectors || [];
                const tiles = buildTreemapTiles(sectors);
                if (tiles.length === 0) {
                    el.innerHTML = '<div class="text-muted text-center">暂无热力数据</div>';
                    return false;
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
                const weightLabel = heatmapWeightLabel(tiles, data);
                const state = Intelligence.state || (Intelligence.state = {});
                state.latestHeatmapPayload = data;

                const tileHtml = tiles.map(({ sector, span, rowSpan, share }) => {
                    const change = Number(sector.change_pct) || 0;
                    const pctStr = formatPct(change);
                    const weightMeta = heatmapWeightMeta(sector);
                    const cls = change >= 0 ? 'up' : 'down';
                    return `<button class="intel-treemap-tile ${cls}" data-intel-action="select-sector" data-sector-name="${safeHTML(sector.name || '')}" data-grouping="${safeHTML(sector.grouping || data.grouping || 'industry')}" data-concept="${safeHTML(sector.name || '')}" style="grid-column: span ${span};grid-row: span ${rowSpan};background:${heatColor(change)};color:${heatTextColor(change)}" title="${safeHTML(sector.name || '')} ${pctStr} · ${safeHTML(weightLabel)} ${(share * 100).toFixed(1)}% · 领涨 ${safeHTML(sector.leader || '--')}">
                        <span class="treemap-name">${safeHTML(sector.name || '')}</span>
                        <span class="treemap-pct">${pctStr}</span>
                        <span class="treemap-meta">${weightMeta} · ${Number(sector.up_count) || 0}↑ ${Number(sector.down_count) || 0}↓</span>
                    </button>`;
                }).join('');

                el.innerHTML = `
                    ${renderMarketEntryMap(data)}
                    <div class="intel-heatmap-head">
                        <div class="intel-heatmap-stats">
                            <span>上涨 ${upCount}</span>
                            <span>下跌 ${downCount}</span>
                            <span>平盘 ${flatCount}</span>
                            <span>均值 ${formatPct(avgChange)}</span>
                            <span>全量板块 ${formatCount(totalCount)} · 当前展示 ${formatCount(displayCount)}</span>
                            <span>口径 ${safeHTML(weightLabel)}展示 Top 32</span>
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
                return true;
            };

            try {
                const configuredTimeout = Number(Intelligence.state?.heatmapSoftTimeoutMs);
                const heatmapSoftTimeoutMs = Number.isFinite(configuredTimeout) && configuredTimeout > 0
                    ? configuredTimeout
                    : 2500;
                const configuredFallbackDelay = Number(Intelligence.state?.heatmapFallbackDelayMs);
                const heatmapFallbackDelayMs = Number.isFinite(configuredFallbackDelay) && configuredFallbackDelay > 0
                    ? configuredFallbackDelay
                    : 3500;
                const heatmapPromise = fetchWithSoftRetry('heatmap', '/api/market/heatmap?fast=true');
                const quickData = await softTimeout(heatmapPromise, heatmapSoftTimeoutMs);
                if (quickData && quickData.__error) {
                    throw quickData.__error;
                }
                if (quickData) {
                    renderHeatmap(quickData);
                    return;
                }
                const loadToken = `${Date.now()}:${Math.random()}`;
                el.dataset.heatmapLoadingToken = loadToken;
                el.innerHTML = `<div class="text-muted text-center intel-heatmap-loading" style="padding:24px">
                    热力图后台更新中<br><small>使用本地全市场覆盖池生成，完成后自动刷新</small>
                </div>`;
                heatmapPromise
                    .then((data) => {
                        if (el.dataset.heatmapLoadingToken === loadToken) {
                            renderHeatmap(data);
                        }
                    })
                    .catch((error) => {
                        console.warn('情报热力图后台加载失败', error);
                        el.innerHTML = '<div class="text-muted text-center">加载失败</div>';
                    });
                setTimeout(() => {
                    if (el.dataset.heatmapLoadingToken !== loadToken || !el.querySelector?.('.intel-heatmap-loading')) {
                        return;
                    }
                    fetchWithSoftRetry(`heatmap:fallback:${loadToken}`, '/api/market/heatmap?fast=true', { retries: 0 })
                        .then((data) => {
                            if (el.dataset.heatmapLoadingToken === loadToken) {
                                renderHeatmap(data);
                            }
                        })
                        .catch((error) => {
                            console.warn('情报热力图兜底加载失败', error);
                            if (el.dataset.heatmapLoadingToken === loadToken) {
                                el.innerHTML = '<div class="text-muted text-center">加载失败</div>';
                            }
                        });
                }, heatmapFallbackDelayMs);
            } catch (error) {
                console.warn('情报热力图加载失败', error);
                el.innerHTML = '<div class="text-muted text-center">加载失败</div>';
            }
        },

        async loadSectorMembers(sectorName, options = {}) {
            const el = document.getElementById('intel-heatmap');
            if (!el) return;
            const name = String(sectorName || '').trim();
            if (!name) return;
            const grouping = String(options.grouping || 'industry').trim() || 'industry';
            const url = `/api/market/sector-members?name=${encodeURIComponent(name)}&grouping=${encodeURIComponent(grouping)}&limit=30`;
            const state = Intelligence.state || (Intelligence.state = {});
            try {
                const data = await fetchWithSoftRetry(`sector-members:${grouping}:${name}`, url, { retries: 0 });
                state.latestSectorMembers = data;
                const existing = el.innerHTML.replace(/<div class="intel-sector-members"[\s\S]*$/m, '');
                el.innerHTML = `${existing}${renderSectorMembersPanel(data)}`;
                return data;
            } catch (error) {
                console.warn('板块成分加载失败', error);
                const existing = el.innerHTML.replace(/<div class="intel-sector-members"[\s\S]*$/m, '');
                el.innerHTML = `${existing}<div class="intel-sector-members"><div class="intel-sector-members-empty">板块成分加载失败</div></div>`;
                throw error;
            }
        },

        async loadHotspot() {
            const el = document.getElementById('intel-hotspot');
            if (!el) return;

            try {
                const data = await fetchWithSoftRetry('hotspot', '/api/market/hotspot');
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
            } catch (error) {
                console.warn('情报热点归因加载失败', error);
                el.innerHTML = '<div class="text-muted text-center">加载失败</div>';
            }
        },
    });

    window.addEventListener?.('aiq:intelligence-tab-active', () => {
        wakeActiveIntelligencePage();
    });
    wakeActiveIntelligencePage();
})();
