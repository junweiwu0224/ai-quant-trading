/**
 * 情报模块 (Intelligence)
 * 黄金分割布局：左35%新闻流 + 右65%热点/热力图/问财工作台
 * 跨组件联动：热点→问财、新闻→行情详情Offcanvas
 */
(function () {
    'use strict';

    let _loaded = false;
    let _iwencaiResult = null;

    // ── 初始化 ──

    function init() {
        bindIwencai();
        App.registerContext('intelligence', () => {
            // 截断大型数据，防止 LLM prompt 膨胀
            const summary = _iwencaiResult ? {
                query: _iwencaiResult.query,
                total: _iwencaiResult.data?.length || 0,
                sample: (_iwencaiResult.data || []).slice(0, 5),
            } : null;
            return {
                type: 'intelligence',
                iwencaiResult: summary,
                currentTab: 'intelligence',
                pageDesc: '情报页：市场情绪、新闻流、板块热力图、热点概念、问财自然语言选股、Qlib AI T+1预测池',
            };
        });
    }

    // ── 加载全部数据 ──

    async function load() {
        if (!_loaded) {
            _loaded = true;
            // allSettled 确保单个数据源失败不影响其他模块
            await Promise.allSettled([
                loadSentiment(),
                loadNews(),
                loadHeatmap(),
                loadHotspot(),
                loadMLPredictions(),
                loadSignalBar(),
            ]);
        }
    }

    // ── 市场情绪 ──

    async function loadSentiment() {
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
        } catch (e) {
            el.innerHTML = '<div class="text-muted text-center">加载失败</div>';
        }
    }

    // ── 新闻流 ──

    async function loadNews() {
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

            el.innerHTML = news.map(n => {
                const sentVal = n.sentiment || 0;
                const sentCls = sentVal > 0.2 ? 'tag-up' : sentVal < -0.2 ? 'tag-down' : '';
                const icon = sentVal > 0.2 ? '▲' : sentVal < -0.2 ? '▼' : '●';
                const iconCls = sentVal > 0.2 ? 'text-up' : sentVal < -0.2 ? 'text-down' : 'text-muted';
                // 提取股票标签
                const tags = (n.stocks || []).slice(0, 3).map(s =>
                    `<span class="intel-news-tag ${sentCls}" data-code="${App.escapeHTML(s.code || '')}" onclick="App.emit('news:open-stock', {code:'${App.escapeHTML(s.code || '')}'})">${App.escapeHTML(s.name || s.code || '')}</span>`
                ).join('');
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

            // 更新总体情绪
            const overall = data.overall_sentiment || 0;
            const sentLabel = overall >= 0.1 ? '偏多' : overall <= -0.1 ? '偏空' : '中性';
            const sentCls = overall >= 0.1 ? 'text-up' : overall <= -0.1 ? 'text-down' : 'text-muted';
            const sentHeader = document.querySelector('.intel-sentiment-card h3');
            if (sentHeader) sentHeader.innerHTML = `市场情绪 <span class="${sentCls}" style="font-size:var(--font-size-xs);font-weight:400">${sentLabel} (${overall.toFixed(2)})</span>`;

        } catch (e) {
            el.innerHTML = '<div class="text-muted text-center">加载失败</div>';
        }
    }

    // ── 板块热力图 (复用 overview-radar 的逻辑) ──

    async function loadHeatmap() {
        const el = document.getElementById('intel-heatmap');
        if (!el) return;
        try {
            const data = await App.fetchJSON('/api/market/heatmap', { silent: true });
            if (!data.success) {
                el.innerHTML = '<div class="text-muted text-center">加载失败</div>';
                return;
            }
            const sectors = (data.sectors || []).filter(s => s.total_mv > 0);
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
                    html += `<div class="heatmap-cell" style="width:${w}px;height:${rowHeight}px;background:${bg};color:${fg};font-size:${fontSize}" title="${s.name} ${pctStr}">
                        <div class="heatmap-cell-name">${App.escapeHTML(s.name)}</div>
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
        } catch (e) {
            el.innerHTML = '<div class="text-muted text-center">加载失败</div>';
        }
    }

    // ── 热点归因 ──

    async function loadHotspot() {
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
            if (summary) html += `<div style="font-size:var(--font-size-xs);color:var(--text-muted);margin-bottom:8px">${App.escapeHTML(summary)}</div>`;
            html += '<div style="display:flex;flex-wrap:wrap;gap:4px">';
            for (const c of concepts) {
                const pctCls = c.change_pct >= 0 ? 'up' : 'down';
                const pctStr = (c.change_pct >= 0 ? '+' : '') + c.change_pct.toFixed(2) + '%';
                html += `<div class="intel-hotspot-concept" data-concept="${App.escapeHTML(c.name)}" title="领涨: ${App.escapeHTML(c.leader || '--')} | 上涨:${c.up_count} 下跌:${c.down_count}" onclick="App.emit('hotspot:query-iwencai', {concept:'${App.escapeHTML(c.name)}'})">
                    <span>${App.escapeHTML(c.name)}</span>
                    <span class="concept-pct ${pctCls}">${pctStr}</span>
                </div>`;
            }
            html += '</div>';
            el.innerHTML = html;
        } catch (e) {
            el.innerHTML = '<div class="text-muted text-center">加载失败</div>';
        }
    }

    // ── 问财检索 ──

    function bindIwencai() {
        const input = document.getElementById('intel-iwencai-input');
        const btn = document.getElementById('intel-iwencai-btn');
        if (!input || !btn) return;

        btn.addEventListener('click', () => runIwencai());
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); runIwencai(); }
        });

        // 监听热点→问财联动
        App.on('hotspot:query-iwencai', ({ concept }) => {
            if (input) input.value = concept;
            runIwencai();
        });
    }

    async function runIwencai() {
        const input = document.getElementById('intel-iwencai-input');
        const el = document.getElementById('intel-iwencai-result');
        if (!input || !el) return;
        const query = input.value.trim();
        if (!query) return;

        el.innerHTML = '<div class="text-center" style="padding:16px"><span class="spinner"></span> 正在查询问财...</div>';

        try {
            const resp = await App.fetchJSON('/api/llm/iwencai', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query }),
                label: '问财查询',
                timeout: 30000,
            });

            if (!resp.success) {
                el.innerHTML = `<div class="text-muted text-center">${App.escapeHTML(resp.error || '查询失败')}</div>`;
                return;
            }

            const data = resp.data || [];
            _iwencaiResult = { query, data };

            if (data.length === 0) {
                el.innerHTML = '<div class="text-muted text-center">未找到匹配结果</div>';
                return;
            }

            const cols = Object.keys(data[0]);
            const displayRows = data.slice(0, 30);
            let tableHtml = `<div class="table-wrap"><table>
                <thead><tr>${cols.map(c => `<th>${App.escapeHTML(c)}</th>`).join('')}</tr></thead>
                <tbody>${displayRows.map(row => `<tr>${cols.map(c => {
                    const v = row[c];
                    const display = v === null || v === undefined ? '' : String(v).substring(0, 25);
                    // 如果是代码列，添加点击跳转
                    if ((c === '代码' || c === 'code' || c === '股票代码') && v) {
                        return `<td><a href="#" class="stock-link" data-code="${App.escapeHTML(String(v))}">${App.escapeHTML(display)}</a></td>`;
                    }
                    return `<td>${App.escapeHTML(display)}</td>`;
                }).join('')}</tr>`).join('')}</tbody>
            </table></div>`;

            // 操作栏：发送至选股器 / 交给MiMo分析 / 加入自选
            const codes = data.map(r => r['代码'] || r['code'] || r['股票代码']).filter(Boolean);
            const actionsHtml = `<div class="iwencai-actions">
                <span class="text-muted text-xs">共 ${resp.total || data.length} 条，显示前 ${displayRows.length} 条</span>
                <button class="btn btn-sm" onclick="App.emit('iwencai:send-to-screener', {pool:${JSON.stringify(codes.slice(0, 50))}, query:'${App.escapeHTML(query)}'})">发送至选股器</button>
                <button class="btn btn-sm" onclick="App.emit('iwencai:analyze', {query:'${App.escapeHTML(query)}', data: window.Intelligence?.getLastResult?.()})">交给 MiMo 分析</button>
                <button class="btn btn-sm" onclick="App.addAllToWatchlist(${JSON.stringify(codes.slice(0, 20))})">加入自选</button>
            </div>`;

            el.innerHTML = tableHtml + actionsHtml;
        } catch (e) {
            el.innerHTML = `<div class="text-muted text-center">查询失败: ${App.escapeHTML(e.message)}</div>`;
        }
    }

    function getLastResult() {
        return _iwencaiResult;
    }

    // ── AI 预测池 (v2: 热度可视化 + Pipeline + MiMo) ──

    async function loadMLPredictions() {
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

            // 合并一致性数据
            const consistMap = {};
            if (consistData?.success && consistData.items) {
                for (const item of consistData.items) {
                    consistMap[item.code] = item;
                }
            }

            const preds = data.predictions;
            const total = preds.length;

            // 热度等级: 前5% = 🔥强动能, 前15% = 🟠中动能, 前30% = 🟡弱动能, 其余 = 冷
            function heatLevel(rank) {
                const pct = rank / total;
                if (pct <= 0.05) return { icon: '🔥', label: '强动能', cls: 'qlib-heat-hot' };
                if (pct <= 0.15) return { icon: '🟠', label: '中动能', cls: 'qlib-heat-warm' };
                if (pct <= 0.30) return { icon: '🟡', label: '弱动能', cls: 'qlib-heat-mild' };
                return { icon: '⚪', label: '', cls: 'qlib-heat-cool' };
            }

            // 分数归一化
            const scores = preds.map(p => p.score);
            const minScore = Math.min(...scores);
            const maxScore = Math.max(...scores);
            const scoreRange = maxScore - minScore || 1;

            const rows = preds.map((p, i) => {
                const heat = heatLevel(i);
                const barPct = Math.round(((p.score - minScore) / scoreRange) * 100);
                const hue = Math.round(220 - (barPct / 100) * 220);
                const barBg = `hsl(${hue}, 70%, 50%)`;
                const industry = (p.industry || '--').split('-')[0].substring(0, 8);
                const priceStr = p.price ? p.price.toFixed(2) : '--';
                // 成交额格式化
                const amtStr = p.amount ? (p.amount >= 1e8 ? (p.amount / 1e8).toFixed(1) + '亿' : (p.amount / 1e4).toFixed(0) + '万') : '--';
                const code = App.escapeHTML(p.code);
                const name = App.escapeHTML(p.name || p.code);
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
                        <button class="qlib-btn qlib-btn-mimo" data-code="${code}" data-name="${name}" data-score="${p.score.toFixed(3)}" data-industry="${App.escapeHTML(p.industry || '--')}" title="问 MiMo">🤖</button>
                    </td>
                </tr>`;
            }).join('');

            const dateStr = data.date || '--';
            el.innerHTML = `
                <div class="qlib-header">
                    <div class="qlib-header-left">
                        <span class="qlib-date" style="cursor:pointer;text-decoration:underline dotted" title="点击联动到研发页" onclick="App.emit('timeline:focus',{date:'${dateStr}'})">预测日期: ${App.escapeHTML(dateStr)}</span>
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

            // 绑定: 推送至选股器
            document.getElementById('qlib-push-screener')?.addEventListener('click', () => {
                const codes = preds.map(p => p.code);
                App.emit('iwencai:send-to-screener', {
                    pool: codes,
                    query: `Qlib Top ${total} 预测金股池 (${dateStr})`,
                });
                App.toast(`已推送 ${codes.length} 只股票至选股器`, 'success');
            });

            // 绑定: 整行点击跳转行情详情
            el.querySelectorAll('.qlib-row').forEach(row => {
                row.addEventListener('click', e => {
                    if (e.target.closest('.qlib-btn')) return; // 按钮点击不跳转
                    const code = row.dataset.code;
                    if (window.StockDetail?.show) window.StockDetail.show(code);
                });
            });

            // 绑定: 问 MiMo 按钮
            el.querySelectorAll('.qlib-btn-mimo').forEach(btn => {
                btn.addEventListener('click', e => {
                    e.stopPropagation();
                    const { code, name, score, industry } = btn.dataset;
                    const msg = `Qlib 模型今天给 ${name}(${code}) 打出了 ${score} 的高分，属于 ${industry} 板块。请帮我分析：\n1. 这只票最近有没有股东减持、负面研报或重大风险？\n2. 当前技术面是否支持介入？\n3. 如果买入，建议的止损位和目标位是多少？`;
                    App.emit('iwencai:analyze', { query: msg, data: null });
                });
            });

        } catch (e) {
            el.innerHTML = '<div class="text-muted text-center" style="padding:16px">预测加载失败</div>';
        }
    }

    // ── 信号强度聚合条 ──

    async function loadSignalBar() {
        const bar = document.getElementById('signal-bar');
        if (!bar) return;

        const sources = [];
        let compositeScore = 0;
        let validSources = 0;

        // 并行获取数据
        const [radarRes, heatmapRes, qlibRes, newsRes, hotspotRes] = await Promise.allSettled([
            App.fetchJSON('/api/market/radar', { silent: true }),
            App.fetchJSON('/api/market/heatmap', { silent: true }),
            App.fetchJSON('/api/qlib/top?top_n=50', { silent: true }),
            App.fetchJSON('/api/market/news', { silent: true }),
            App.fetchJSON('/api/market/hotspot', { silent: true }),
        ]);

        // 1. 市场情绪 (涨跌比)
        if (radarRes.status === 'fulfilled' && radarRes.value?.success) {
            const r = radarRes.value;
            const g = (r.top_gainers || []).length;
            const l = (r.top_losers || []).length;
            const total = g + l;
            if (total > 0) {
                const ratio = (g / total - 0.5) * 200; // -100 to +100
                compositeScore += ratio;
                validSources++;
                sources.push({ name: '情绪', score: ratio, color: ratio >= 0 ? '#22c55e' : '#dc2626' });
            }
        }

        // 2. 板块动能 (平均涨跌幅)
        if (heatmapRes.status === 'fulfilled' && heatmapRes.value?.success) {
            const sectors = heatmapRes.value.sectors || [];
            if (sectors.length > 0) {
                const avg = sectors.reduce((s, sec) => s + (sec.change_pct || 0), 0) / sectors.length;
                const score = Math.max(-100, Math.min(100, avg * 20)); // 放大到 -100~+100
                compositeScore += score;
                validSources++;
                sources.push({ name: '板块', score, color: score >= 0 ? '#22c55e' : '#dc2626' });
            }
        }

        // 3. AI预测 (Top50平均分)
        if (qlibRes.status === 'fulfilled' && qlibRes.value?.predictions?.length) {
            const preds = qlibRes.value.predictions;
            const scores = preds.map(p => p.score);
            const avgScore = scores.reduce((a, b) => a + b, 0) / scores.length;
            // 归一化: 假设分数范围 0~1, 映射到 -100~+100
            const normalized = (avgScore - 0.5) * 200;
            const score = Math.max(-100, Math.min(100, normalized));
            compositeScore += score;
            validSources++;
            sources.push({ name: 'AI预测', score, color: score >= 0 ? '#22c55e' : '#dc2626' });
        }

        // 4. 新闻活跃度 (数量 → 0~100)
        if (newsRes.status === 'fulfilled' && newsRes.value?.success) {
            const count = (newsRes.value.news || []).length;
            const score = Math.min(100, count * 5); // 20条 = 满分
            compositeScore += score - 50; // 中心化到 -50~+50
            validSources++;
            sources.push({ name: '新闻', score: score - 50, color: score > 50 ? '#f59e0b' : '#94a3b8' });
        }

        // 5. 热点活跃度 (数量 → 0~100)
        if (hotspotRes.status === 'fulfilled' && hotspotRes.value?.success) {
            const topics = (hotspotRes.value.hotspots || hotspotRes.value.topics || []).length;
            const score = Math.min(100, topics * 10);
            compositeScore += score - 50;
            validSources++;
            sources.push({ name: '热点', score: score - 50, color: score > 50 ? '#f59e0b' : '#94a3b8' });
        }

        // 计算综合得分
        const avgScore = validSources > 0 ? compositeScore / validSources : 0;
        const displayScore = Math.round(avgScore);

        // 更新UI
        const marker = document.getElementById('signal-bar-marker');
        const scoreEl = document.getElementById('signal-bar-score');
        const sourcesEl = document.getElementById('signal-bar-sources');

        if (marker) {
            // -100 → left:0%, +100 → left:100%
            const pct = Math.max(0, Math.min(100, (avgScore + 100) / 2));
            marker.style.left = pct + '%';
        }

        if (scoreEl) {
            scoreEl.textContent = displayScore > 0 ? '+' + displayScore : String(displayScore);
            scoreEl.style.color = displayScore >= 10 ? '#22c55e' : displayScore <= -10 ? '#dc2626' : '#f59e0b';
        }

        if (sourcesEl) {
            sourcesEl.innerHTML = sources.map(s => {
                const dotColor = s.score >= 10 ? '#22c55e' : s.score <= -10 ? '#dc2626' : '#f59e0b';
                return `<span class="signal-src"><span class="signal-src-dot" style="background:${dotColor}"></span>${s.name}</span>`;
            }).join('');
        }
    }

    // ── 公开接口 ──

    window.Intelligence = { init, load, getLastResult };

})();
