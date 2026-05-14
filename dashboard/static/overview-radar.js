/**
 * 市场雷达模块
 * 涨跌幅/振幅/换手率/量比 TOP 10 + 板块轮动 + 热力图 + 北向资金
 */
(function () {
    'use strict';

    let _currentTab = 'gainers';

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
        if (data && data.stale) {
            return '<div class="radar-stale-hint">数据截至上一交易日</div>';
        }
        return '';
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
        container.innerHTML = '<div class="skeleton-block skeleton-pulse" style="height:200px;border-radius:8px"></div>';

        try {
            if (_currentTab === 'sectors') {
                await loadSectors(container);
            } else if (_currentTab === 'heatmap') {
                await loadHeatmap(container);
            } else if (_currentTab === 'northbound') {
                await loadNorthbound(container);
            } else if (_currentTab === 'hotspot') {
                await loadHotspot(container);
            } else if (_currentTab === 'news') {
                await loadNews(container);
            } else {
                await loadTopStocks(container);
            }
        } catch (e) {
            container.innerHTML = `<div class="text-muted text-center">加载失败: ${App.escapeHTML(e.message)}</div>`;
        }
    }

    async function loadTopStocks(container) {
        const data = await App.fetchJSON('/api/market/radar');
        if (!data.success) {
            container.innerHTML = `<div class="text-muted text-center">${App.escapeHTML(data.error || '加载失败')}</div>`;
            return;
        }

        const fieldMap = {
            gainers: { list: data.top_gainers, label: '涨幅', suffix: '%' },
            losers: { list: data.top_losers, label: '跌幅', suffix: '%' },
            amplitude: { list: data.top_amplitude, label: '振幅', suffix: '%' },
            turnover: { list: data.top_turnover, label: '换手率', suffix: '%' },
        };

        const cfg = fieldMap[_currentTab] || fieldMap.gainers;
        const items = cfg.list || [];

        container.innerHTML = _staleBanner(data) + `
            <div class="table-wrap">
                <table>
                    <thead><tr><th>排名</th><th>代码</th><th>名称</th><th>${cfg.label}</th><th>操作</th></tr></thead>
                    <tbody>${items.map((s, i) => {
                        const val = s.value != null ? s.value.toFixed(2) + cfg.suffix : '--';
                        const cls = _currentTab === 'losers' ? 'text-down' : 'text-up';
                        return `<tr>
                            <td>${i + 1}</td>
                            <td><a href="#" class="stock-link" data-code="${App.escapeHTML(s.code || '')}">${App.escapeHTML(s.code || '')}</a></td>
                            <td>${App.escapeHTML(s.name || '')}</td>
                            <td class="${cls}">${val}</td>
                            <td><button class="btn btn-sm" data-overview-radar-action="add-watchlist" data-code="${App.escapeHTML(s.code || '')}">加自选</button></td>
                        </tr>`;
                    }).join('')}</tbody>
                </table>
            </div>
        `;
    }

    async function loadSectors(container) {
        const data = await App.fetchJSON('/api/market/sectors?type=industry');
        if (!data.success) {
            container.innerHTML = `<div class="text-muted text-center">${App.escapeHTML(data.error || '加载失败')}</div>`;
            return;
        }

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

    async function loadHeatmap(container) {
        const data = await App.fetchJSON('/api/market/heatmap');
        if (!data.success) {
            container.innerHTML = `<div class="text-muted text-center">${App.escapeHTML(data.error || '加载失败')}</div>`;
            return;
        }

        const sectors = (data.sectors || []).filter(s => s.total_mv > 0);

        // 按市值排序，大块在前
        sectors.sort((a, b) => b.total_mv - a.total_mv);

        // 计算总面积和每个色块大小
        const totalMV = sectors.reduce((sum, s) => sum + s.total_mv, 0);

        container.innerHTML = _staleBanner(data) + `
            <div class="heatmap-legend">
                <span class="text-muted" style="font-size:var(--font-size-xs)">跌幅 5%</span>
                <div class="heatmap-gradient"></div>
                <span class="text-muted" style="font-size:var(--font-size-xs)">涨幅 5%</span>
            </div>
            <div id="heatmap-grid" class="heatmap-grid"></div>
        `;

        const grid = document.getElementById('heatmap-grid');
        if (!grid) return;

        // 使用 treemap 布局算法（简单版：按行排列）
        const containerWidth = grid.offsetWidth || 800;
        const rowHeight = 72;
        const gap = 2;
        let html = '';
        let currentRow = [];
        let currentRowMV = 0;
        const rowTargetMV = totalMV / Math.max(1, Math.ceil(sectors.length / 8));

        function flushRow() {
            if (currentRow.length === 0) return;
            const rowMV = currentRow.reduce((s, r) => s + r.total_mv, 0);
            let x = 0;
            for (const s of currentRow) {
                const w = Math.max(60, (s.total_mv / rowMV) * (containerWidth - gap * currentRow.length));
                const bg = _changeToColor(s.change_pct);
                const fg = _changeToTextColor(s.change_pct);
                const pctStr = (s.change_pct >= 0 ? '+' : '') + s.change_pct.toFixed(2) + '%';
                const fontSize = w > 100 ? '13px' : w > 70 ? '11px' : '9px';
                const showDetail = w > 90;
                html += `<div class="heatmap-cell" style="
                    width:${w}px;height:${rowHeight}px;background:${bg};color:${fg};
                    font-size:${fontSize};
                " title="${s.name} | 涨跌:${pctStr} | 上涨:${s.up_count} 下跌:${s.down_count} | 领涨:${s.leader || '--'}">
                    <div class="heatmap-cell-name">${App.escapeHTML(s.name)}</div>
                    <div class="heatmap-cell-pct">${pctStr}</div>
                    ${showDetail ? `<div class="heatmap-cell-detail">${s.up_count}↑${s.down_count}↓</div>` : ''}
                </div>`;
                x += w;
            }
            currentRow = [];
            currentRowMV = 0;
        }

        for (const s of sectors) {
            currentRow.push(s);
            currentRowMV += s.total_mv;
            if (currentRowMV >= rowTargetMV && currentRow.length >= 3) {
                flushRow();
            }
        }
        flushRow();

        grid.innerHTML = html;
    }

    async function loadNorthbound(container) {
        const data = await App.fetchJSON('/api/market/northbound');
        if (!data.success) {
            container.innerHTML = `<div class="text-muted text-center">${App.escapeHTML(data.error || '加载失败')}</div>`;
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

    async function loadHotspot(container) {
        const data = await App.fetchJSON('/api/market/hotspot');
        if (!data.success) {
            container.innerHTML = `<div class="text-muted text-center">${App.escapeHTML(data.error || '加载失败')}</div>`;
            return;
        }

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

    async function loadNews(container) {
        const data = await App.fetchJSON('/api/market/news');
        if (!data.success) {
            container.innerHTML = `<div class="text-muted text-center">${App.escapeHTML(data.error || '加载失败')}</div>`;
            return;
        }

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

    App.OverviewRadar = { init, loadRadar, addToWatchlist };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
