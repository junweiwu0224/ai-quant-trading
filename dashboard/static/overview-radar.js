/**
 * 市场雷达模块
 * 涨跌幅/振幅/换手率/量比 TOP 10 + 板块轮动 + 热力图 + 北向资金
 */
(function () {
    'use strict';

    let _currentTab = 'gainers';
    let _radarRequestSeq = 0;

    function createActionTraceId(prefix) {
        if (window.LocalMCP && typeof window.LocalMCP.createTraceId === 'function') {
            return window.LocalMCP.createTraceId(prefix);
        }
        const safePrefix = typeof prefix === 'string' && prefix.trim() ? prefix.trim() : 'overview-radar';
        return `${safePrefix}-${Date.now()}`;
    }

    async function init() {
        bindTabs();
        bindActions();
        _updateRadarStatus();
        loadRadar();
    }

    function _updateRadarStatus() {
        const el = document.getElementById('radar-market-status');
        if (!el) return;
        const now = new Date();
        const day = now.getDay();
        const hhmm = now.getHours() * 100 + now.getMinutes();
        let status, cls;
        if (day === 0 || day === 6) {
            status = '休市'; cls = 'closed';
        } else if (hhmm >= 915 && hhmm < 930) {
            status = '集合竞价'; cls = 'pre';
        } else if ((hhmm >= 930 && hhmm <= 1130) || (hhmm >= 1300 && hhmm <= 1500)) {
            status = '实时'; cls = 'open';
        } else if (hhmm > 1130 && hhmm < 1300) {
            status = '午间休市'; cls = 'closed';
        } else {
            status = '休市'; cls = 'closed';
        }
        el.textContent = status;
        el.className = `market-status-badge ${cls}`;
    }

    function _staleBanner(data) {
        if (data && data.local_fallback) {
            const dateText = data.latest_date ? ` · ${App.escapeHTML(data.latest_date)}` : '';
            const note = data.coverage_note || '本地缓存数据';
            return `<div class="radar-stale-hint">${App.escapeHTML(note)}${dateText}</div>`;
        }
        if (data && data.source === 'eastmoney_full_market_rank') {
            const note = data.coverage_note || '全A股延迟快照';
            const total = data.total_stocks ? ` · ${Number(data.total_stocks).toLocaleString()}只` : '';
            return `<div class="radar-stale-hint">${App.escapeHTML(note)}${total}</div>`;
        }
        if (data && data.stale) {
            return '<div class="radar-stale-hint">数据截至上一交易日</div>';
        }
        return '';
    }

    function _sourceLabel(source) {
        const value = String(source || '');
        if (value.includes('local_stock_daily')) return '本地 stock_daily';
        if (value.includes('eastmoney')) return '东方财富';
        if (value.includes('northbound')) return '北向资金源';
        return value || '--';
    }

    function _universeLabel(data) {
        const universe = String(data?.universe || '');
        if (data?.source_unavailable) return '北向资金源不可用';
        if (universe.includes('local_stock_daily')) return '本地日线覆盖池';
        if (data?.local_fallback) return '本地日线覆盖池';
        if (universe.includes('full') || data?.source === 'eastmoney_full_market_rank') return '全A延迟快照';
        if (universe.includes('northbound')) return '北向资金';
        return universe || '当前数据源';
    }

    function _formatRadarUpdate(data) {
        const raw = data?.latest_date || data?.timestamp || data?.generated_at || '';
        return raw ? String(raw).slice(0, 10) : '--';
    }

    function _updateCoverageStrip(data, fallbackMode = '') {
        const el = document.getElementById('overview-radar-coverage');
        if (!el || !data) return;
        const total = Number(data.total_stocks ?? data.total ?? data.stock_count);
        const effective = Number.isFinite(total) && total > 0 ? `${total.toLocaleString('zh-CN')}只` : '--';
        const sourceLabel = _sourceLabel(data.source);
        const note = data.source_unavailable
            ? (data.coverage_note || '当前源不可用，未返回实时数值')
            : (data.coverage_note || (data.local_fallback ? '本地缓存降级展示' : '服务端延迟快照'));
        const mode = fallbackMode || (data.source_unavailable ? '源不可用' : (data.local_fallback || data.stale ? '降级/缓存' : '在线'));
        el.innerHTML = [
            `范围 ${_universeLabel(data)}`,
            `排序 ${sourceLabel}`,
            `有效 ${effective}`,
            `更新 ${_formatRadarUpdate(data)}`,
            `状态 ${mode}`,
            note,
        ].map((text) => `<span class="coverage-pill">${App.escapeHTML(text)}</span>`).join('');
    }

    function bindTabs() {
        document.querySelectorAll('.radar-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.radar-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                _currentTab = tab.dataset.tab;
                loadRadar();
            });
        });
    }

    function bindActions() {
        document.addEventListener('click', (e) => {
            const button = e.target.closest('[data-overview-radar-action="add-watchlist"]');
            if (!button) {
                return;
            }

            e.preventDefault();
            const code = typeof button.dataset.code === 'string' ? button.dataset.code.trim() : '';
            if (code) {
                addToWatchlist(code);
            }
        });
    }

    async function loadRadar() {
        const container = document.getElementById('radar-content');
        if (!container) return;
        // Tab守卫：仅在总览/监控Tab激活时加载，防止幽灵请求
        const overviewPanel = document.getElementById('tab-overview');
        if (overviewPanel && !overviewPanel.classList.contains('active')) return;
        const request = { id: ++_radarRequestSeq, tab: _currentTab };
        container.innerHTML = '<div class="skeleton-block skeleton-pulse" style="height:200px;border-radius:8px"></div>';

        try {
            if (_currentTab === 'sectors') {
                await loadSectors(container, request);
            } else if (_currentTab === 'heatmap') {
                await loadHeatmap(container, request);
            } else if (_currentTab === 'northbound') {
                await loadNorthbound(container, request);
            } else if (_currentTab === 'hotspot') {
                await loadHotspot(container, request);
            } else if (_currentTab === 'news') {
                await loadNews(container, request);
            } else {
                await loadTopStocks(container, request);
            }
        } catch (e) {
            if (!isCurrentRadarRequest(request)) return;
            if (isSoftRadarTimeout(e)) {
                container.innerHTML = '<div class="text-muted text-center">市场雷达暂未返回，稍后刷新可重试</div>';
                return;
            }
            container.innerHTML = `<div class="text-muted text-center">加载失败: ${App.escapeHTML(e.message)}</div>`;
        }
    }

    function isSoftRadarTimeout(error) {
        const message = error?.message || String(error || '');
        return /请求超时|timeout/i.test(message);
    }

    function isCurrentRadarRequest(request) {
        return Boolean(request)
            && request.id === _radarRequestSeq
            && request.tab === _currentTab;
    }

    function fetchFastMarketJSON(url) {
        return App.fetchJSON(url, { silent: true, timeout: 30000 });
    }

    async function loadTopStocks(container, request) {
        const data = await fetchFastMarketJSON('/api/market/radar?fast=true');
        if (!isCurrentRadarRequest(request)) return;
        if (!data.success) {
            container.innerHTML = `<div class="text-muted text-center">${App.escapeHTML(data.error || '加载失败')}</div>`;
            return;
        }
        _updateCoverageStrip(data);

        const fieldMap = {
            gainers: { list: data.top_gainers, label: '涨幅', suffix: '%' },
            losers: { list: data.top_losers, label: '跌幅', suffix: '%' },
            amplitude: { list: data.top_amplitude, label: '振幅', suffix: '%' },
            turnover: {
                list: data.top_turnover,
                label: data.local_fallback ? '成交额' : '换手率',
                suffix: data.local_fallback ? '亿' : '%',
            },
        };

        const cfg = fieldMap[_currentTab] || fieldMap.gainers;
        const items = cfg.list || [];

        container.innerHTML = _staleBanner(data) + `
            <div class="table-wrap">
                <table id="overview-radar-table" data-testid="overview-radar-table">
                    <thead><tr><th>排名</th><th>代码</th><th>名称</th><th>${cfg.label}</th><th>操作</th></tr></thead>
                    <tbody>${items.map((s, i) => {
                        const val = s.value != null ? s.value.toFixed(2) + cfg.suffix : '--';
                        const cls = _currentTab === 'losers' ? 'text-down' : 'text-up';
                        return `<tr>
                            <td>${i + 1}</td>
                            <td><a href="#" class="stock-link" data-code="${App.escapeHTML(s.code || '')}" data-name="${App.escapeHTML(s.name || '')}">${App.escapeHTML(s.code || '')}</a></td>
                            <td>${App.escapeHTML(s.name || '')}</td>
                            <td class="${cls}">${val}</td>
                            <td><button class="btn btn-sm" data-overview-radar-action="add-watchlist" data-code="${App.escapeHTML(s.code || '')}">加自选</button></td>
                        </tr>`;
                    }).join('')}</tbody>
                </table>
            </div>
        `;
    }

    async function loadSectors(container, request) {
        const data = await fetchFastMarketJSON('/api/market/sectors?type=industry&fast=true');
        if (!isCurrentRadarRequest(request)) return;
        if (!data.success) {
            container.innerHTML = `<div class="text-muted text-center">${App.escapeHTML(data.error || '加载失败')}</div>`;
            return;
        }
        _updateCoverageStrip(data);

        const sectors = data.sectors || [];
        container.innerHTML = _staleBanner(data) + `
            <div class="table-wrap">
                <table>
                    <thead><tr><th>排名</th><th>板块</th><th>涨跌幅</th><th>上涨</th><th>下跌</th><th>领涨股</th></tr></thead>
                    <tbody>${sectors.slice(0, 20).map((s, i) => {
                        const cls = s.change_pct >= 0 ? 'text-up' : 'text-down';
                        return `<tr>
                            <td>${i + 1}</td>
                            <td>${App.escapeHTML(s.name || '')}</td>
                            <td class="${cls}">${s.change_pct >= 0 ? '+' : ''}${s.change_pct.toFixed(2)}%</td>
                            <td class="text-up">${s.up_count}</td>
                            <td class="text-down">${s.down_count}</td>
                            <td>${App.escapeHTML(s.leader || '--')}</td>
                        </tr>`;
                    }).join('')}</tbody>
                </table>
            </div>
        `;
    }

    // ── 板块热力图 ──

    function _changeToColor(changePct) {
        // A股惯例：红涨绿跌，按涨跌幅映射色阶
        const v = Math.max(-5, Math.min(5, changePct));
        const t = (v + 5) / 10; // 0~1
        if (changePct >= 0) {
            // 浅红→深红
            const r = Math.round(180 + 75 * t);
            const g = Math.round(80 - 40 * t);
            const b = Math.round(70 - 40 * t);
            return `rgb(${r},${g},${b})`;
        } else {
            // 浅绿→深绿
            const r = Math.round(80 - 50 * (1 - t));
            const g = Math.round(160 + 50 * (1 - t));
            const b = Math.round(90 + 30 * (1 - t));
            return `rgb(${r},${g},${b})`;
        }
    }

    function _changeToTextColor(changePct) {
        // 色块上文字：涨跌幅越大越白
        return Math.abs(changePct) > 1.5 ? '#fff' : 'var(--text-primary)';
    }

    function _heatmapWeight(sector) {
        return Math.max(
            0,
            Number(sector.total_mv) ||
            Number(sector.stock_count) ||
            ((Number(sector.up_count) || 0) + (Number(sector.down_count) || 0)) ||
            1,
        );
    }

    function _heatmapWeightMeta(sector) {
        const totalMv = Number(sector.total_mv);
        if (Number.isFinite(totalMv) && totalMv > 0) {
            return `${Math.round(totalMv).toLocaleString('zh-CN')}亿`;
        }
        const stockCount = Number(sector.stock_count);
        if (Number.isFinite(stockCount) && stockCount > 0) {
            return `${Math.round(stockCount).toLocaleString('zh-CN')}只`;
        }
        return '--';
    }

    function _heatmapWeightLabel(data, sectors) {
        if (sectors.some((s) => Number(s.total_mv) > 0)) return '市值权重';
        if (sectors.some((s) => Number(s.stock_count) > 0) || data.local_fallback) return '覆盖股数权重';
        return '数量权重';
    }

    async function loadHeatmap(container, request) {
        const data = await fetchFastMarketJSON('/api/market/heatmap?fast=true');
        if (!isCurrentRadarRequest(request)) return;
        if (!data.success) {
            container.innerHTML = `<div class="text-muted text-center">${App.escapeHTML(data.error || '加载失败')}</div>`;
            return;
        }
        _updateCoverageStrip(data);

        const sectors = (data.sectors || [])
            .map((s) => ({ ...s, _weight: _heatmapWeight(s) }))
            .filter((s) => s._weight > 0);

        // 按当前可用权重排序，大块在前
        sectors.sort((a, b) => b._weight - a._weight);

        // 计算总面积和每个色块大小
        const totalWeight = sectors.reduce((sum, s) => sum + s._weight, 0) || 1;
        const weightLabel = _heatmapWeightLabel(data, sectors);

        container.innerHTML = _staleBanner(data) + `
            <div class="radar-stale-hint">口径 ${App.escapeHTML(weightLabel)} · 展示 ${sectors.length}/${data.total || sectors.length}</div>
            <div class="heatmap-legend">
                <span class="text-muted" style="font-size:var(--font-size-xs)">跌幅 5%</span>
                <div class="heatmap-gradient"></div>
                <span class="text-muted" style="font-size:var(--font-size-xs)">涨幅 5%</span>
            </div>
            <div id="heatmap-grid" class="heatmap-grid"></div>
        `;

        const grid = document.getElementById('heatmap-grid');
        if (!grid || !isCurrentRadarRequest(request)) return;

        // 使用 treemap 布局算法（简单版：按行排列）
        const containerWidth = grid.offsetWidth || 800;
        const rowHeight = 72;
        const gap = 2;
        let html = '';
        let currentRow = [];
        let currentRowWeight = 0;
        const rowTargetWeight = totalWeight / Math.max(1, Math.ceil(sectors.length / 8));

        function flushRow() {
            if (currentRow.length === 0) return;
            const rowWeight = currentRow.reduce((s, r) => s + r._weight, 0);
            let x = 0;
            for (const s of currentRow) {
                const w = Math.max(60, (s._weight / rowWeight) * (containerWidth - gap * currentRow.length));
                const bg = _changeToColor(s.change_pct);
                const fg = _changeToTextColor(s.change_pct);
                const pctStr = (s.change_pct >= 0 ? '+' : '') + s.change_pct.toFixed(2) + '%';
                const fontSize = w > 100 ? '13px' : w > 70 ? '11px' : '9px';
                const showDetail = w > 90;
                html += `<div class="heatmap-cell" style="
                    width:${w}px;height:${rowHeight}px;background:${bg};color:${fg};
                    font-size:${fontSize};
                " title="${s.name} | 涨跌:${pctStr} | ${weightLabel}:${_heatmapWeightMeta(s)} | 上涨:${s.up_count} 下跌:${s.down_count} | 领涨:${s.leader || '--'}">
                    <div class="heatmap-cell-name">${App.escapeHTML(s.name)}</div>
                    <div class="heatmap-cell-pct">${pctStr}</div>
                    ${showDetail ? `<div class="heatmap-cell-detail">${_heatmapWeightMeta(s)} · ${s.up_count}↑${s.down_count}↓</div>` : ''}
                </div>`;
                x += w;
            }
            currentRow = [];
            currentRowWeight = 0;
        }

        for (const s of sectors) {
            currentRow.push(s);
            currentRowWeight += s._weight;
            if (currentRowWeight >= rowTargetWeight && currentRow.length >= 3) {
                flushRow();
            }
        }
        flushRow();

        grid.innerHTML = html;
    }

    async function loadNorthbound(container, request) {
        const data = await fetchFastMarketJSON('/api/market/northbound?fast=true');
        if (!isCurrentRadarRequest(request)) return;
        if (!data.success) {
            container.innerHTML = `<div class="text-muted text-center">${App.escapeHTML(data.error || '加载失败')}</div>`;
            return;
        }
        _updateCoverageStrip(data, data.source_unavailable ? '源不可用' : '');

        if (data.source_unavailable) {
            const note = data.coverage_note || '北向资金源不可用，当前无可用缓存';
            container.innerHTML = `
                <div class="radar-stale-hint">北向资金源不可用 · ${App.escapeHTML(note)}</div>
                <div class="radar-northbound">
                    <div class="radar-nb-summary">
                        <div class="radar-nb-item">
                            <span class="radar-nb-label">今日净流入</span>
                            <span class="radar-nb-value text-muted">--</span>
                        </div>
                        <div class="radar-nb-item">
                            <span class="radar-nb-label">沪股通</span>
                            <span class="radar-nb-value text-muted">--</span>
                        </div>
                        <div class="radar-nb-item">
                            <span class="radar-nb-label">深股通</span>
                            <span class="radar-nb-value text-muted">--</span>
                        </div>
                    </div>
                </div>
            `;
            return;
        }

        const net = data.today_net || 0;
        const shNet = data.today_sh_net || 0;
        const szNet = data.today_sz_net || 0;
        const cls = net >= 0 ? 'text-up' : 'text-down';

        const flow = data.flow || [];
        const recentFlow = flow.slice(-10);

        container.innerHTML = _staleBanner(data) + `
            <div class="radar-northbound">
                <div class="radar-nb-summary">
                    <div class="radar-nb-item">
                        <span class="radar-nb-label">今日净流入</span>
                        <span class="radar-nb-value ${cls}">${net >= 0 ? '+' : ''}${net.toFixed(2)} 亿</span>
                    </div>
                    <div class="radar-nb-item">
                        <span class="radar-nb-label">沪股通</span>
                        <span class="radar-nb-value ${shNet >= 0 ? 'text-up' : 'text-down'}">${shNet >= 0 ? '+' : ''}${shNet.toFixed(2)} 亿</span>
                    </div>
                    <div class="radar-nb-item">
                        <span class="radar-nb-label">深股通</span>
                        <span class="radar-nb-value ${szNet >= 0 ? 'text-up' : 'text-down'}">${szNet >= 0 ? '+' : ''}${szNet.toFixed(2)} 亿</span>
                    </div>
                </div>
                ${recentFlow.length > 0 ? `
                <div class="radar-nb-flow">
                    <span class="text-muted" style="font-size:var(--font-size-xs)">最近走势：</span>
                    ${recentFlow.map(f => {
                        const c = f.total_net >= 0 ? 'text-up' : 'text-down';
                        return `<span class="radar-nb-dot ${c}" title="${f.time} ${f.total_net}亿">${f.total_net >= 0 ? '▲' : '▼'}</span>`;
                    }).join('')}
                </div>` : ''}
            </div>
        `;
    }

    // ── 热点归因 ──

    async function loadHotspot(container, request) {
        const data = await App.fetchJSON('/api/market/hotspot');
        if (!isCurrentRadarRequest(request)) return;
        if (!data.success) {
            container.innerHTML = `<div class="text-muted text-center">${App.escapeHTML(data.error || '加载失败')}</div>`;
            return;
        }
        _updateCoverageStrip(data);

        const concepts = data.hot_concepts || [];
        const industries = data.hot_industries || [];
        const flow = data.fund_flow || [];

        container.innerHTML = _staleBanner(data) + `
            <div class="hotspot-summary">${App.escapeHTML(data.summary || '')}</div>
            <div class="hotspot-sections">
                <div class="hotspot-section">
                    <h4>热门概念 TOP 10</h4>
                    <div class="table-wrap">
                        <table>
                            <thead><tr><th>概念</th><th>涨跌幅</th><th>领涨股</th><th>上涨/下跌</th></tr></thead>
                            <tbody>${concepts.map(c => {
                                const cls = c.change_pct >= 0 ? 'text-up' : 'text-down';
                                return `<tr>
                                    <td>${App.escapeHTML(c.name || '--')}</td>
                                    <td class="${cls}">${c.change_pct >= 0 ? '+' : ''}${c.change_pct.toFixed(2)}%</td>
                                    <td>${App.escapeHTML(c.leader || '--')}</td>
                                    <td><span class="text-up">${c.up_count}</span>/<span class="text-down">${c.down_count}</span></td>
                                </tr>`;
                            }).join('')}</tbody>
                        </table>
                    </div>
                </div>
                <div class="hotspot-section">
                    <h4>资金流向 TOP 10</h4>
                    <div class="table-wrap">
                        <table>
                            <thead><tr><th>行业</th><th>涨跌幅</th><th>主力净流入(亿)</th><th>净占比</th></tr></thead>
                            <tbody>${flow.map(f => {
                                const cls = f.main_net_inflow >= 0 ? 'text-up' : 'text-down';
                                return `<tr>
                                    <td>${App.escapeHTML(f.name || '--')}</td>
                                    <td class="${f.change_pct >= 0 ? 'text-up' : 'text-down'}">${f.change_pct >= 0 ? '+' : ''}${f.change_pct.toFixed(2)}%</td>
                                    <td class="${cls}">${f.main_net_inflow >= 0 ? '+' : ''}${f.main_net_inflow.toFixed(2)}</td>
                                    <td>${f.main_net_inflow_pct.toFixed(2)}%</td>
                                </tr>`;
                            }).join('')}</tbody>
                        </table>
                    </div>
                </div>
            </div>
        `;
    }

    // ── 市场新闻 ──

    async function loadNews(container, request) {
        const data = await App.fetchJSON('/api/market/news');
        if (!isCurrentRadarRequest(request)) return;
        if (!data.success) {
            container.innerHTML = `<div class="text-muted text-center">${App.escapeHTML(data.error || '加载失败')}</div>`;
            return;
        }
        _updateCoverageStrip(data);

        const news = data.news || [];
        const sentiment = data.overall_sentiment || 0;
        const sentCls = sentiment >= 0.1 ? 'text-up' : sentiment <= -0.1 ? 'text-down' : 'text-muted';
        const sentLabel = sentiment >= 0.1 ? '偏多' : sentiment <= -0.1 ? '偏空' : '中性';

        container.innerHTML = _staleBanner(data) + `
            <div class="news-header">
                <span class="news-sentiment ${sentCls}">市场情绪：${sentLabel} (${sentiment.toFixed(2)})</span>
                <span class="text-muted" style="font-size:var(--font-size-xs)">${data.timestamp || ''}</span>
            </div>
            <div class="news-list">
                ${news.length === 0 ? '<div class="text-muted text-center">暂无新闻</div>' :
                    news.map(n => {
                        const sCls = n.sentiment > 0.2 ? 'text-up' : n.sentiment < -0.2 ? 'text-down' : 'text-muted';
                        const icon = n.sentiment > 0.2 ? '▲' : n.sentiment < -0.2 ? '▼' : '●';
                        return `<div class="news-item">
                            <span class="news-icon ${sCls}">${icon}</span>
                            <span class="news-title">${App.escapeHTML(n.title || '')}</span>
                            <span class="news-time text-muted">${App.escapeHTML(n.time || '')}</span>
                        </div>`;
                    }).join('')}
            </div>
        `;
    }

    async function addToWatchlist(code) {
        if (!code) {
            return {
                ok: false,
                status: 'failed',
                code: 'STOCK_CODE_REQUIRED',
            };
        }

        return App.addToWatchlist(code, {
            source: 'overview-radar:add-watchlist',
            traceId: createActionTraceId('overview-radar'),
        });
    }

    App.OverviewRadar = {
        init,
        loadRadar,
        addToWatchlist,
        _setCurrentTabForTest(tab) {
            _currentTab = tab;
        },
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            if (globalThis.__AUTH_GATE_REQUIRED__ === true) return;
            init();
        });
    } else {
        if (globalThis.__AUTH_GATE_REQUIRED__ !== true) init();
    }
})();
