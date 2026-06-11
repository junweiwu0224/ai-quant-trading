/* ── 股票详情页：基础详情 / 文本统计 ── */

if (!globalThis.StockDetail) {
    globalThis.StockDetail = {};
}

Object.assign(globalThis.StockDetail, {
    _formatVolume(vol) {
        if (vol >= 1e8) return (vol / 1e8).toFixed(2) + '亿';
        if (vol >= 1e4) return (vol / 1e4).toFixed(2) + '万';
        return vol.toFixed(0);
    },

    _stockDataDateKey(value) {
        const match = String(value || '').match(/\d{4}-\d{2}-\d{2}/);
        return match ? match[0] : '';
    },

    _stockDataSentimentDirection(score) {
        const value = Number(score);
        if (!Number.isFinite(value)) return '';
        if (value > 0.2) return 'positive';
        if (value < -0.2) return 'negative';
        return 'neutral';
    },

    /** 计算阶段涨幅 */
    async _loadPeriodReturns(code, stale) {
        try {
            // 加载日K数据（足够计算60日涨幅）
            const data = await App.fetchJSON(`/api/stock/kline/${code}?period=daily&count=250`);
            if (!data || stale()) return;
            const klines = data.klines;
            if (!klines || klines.length < 2) return;

            const latest = klines[klines.length - 1].close;
            const setReturn = (id, days) => {
                const el = document.getElementById(id);
                if (!el) return;
                const idx = klines.length - 1 - days;
                if (idx < 0) {
                    el.textContent = '--';
                    return;
                }
                const base = klines[idx].close;
                const pct = ((latest / base - 1) * 100).toFixed(2);
                el.textContent = (pct >= 0 ? '+' : '') + pct + '%';
                el.className = pct >= 0 ? 'text-up' : 'text-down';
            };

            setReturn('sd-ret-5d', 5);
            setReturn('sd-ret-20d', 20);
            setReturn('sd-ret-60d', 60);

            // 年初至今
            const elYtd = document.getElementById('sd-ret-ytd');
            if (elYtd) {
                const yearStartStr = new Date().getFullYear() + '-01-01';
                const ytdKline = klines.find(k => k.date >= yearStartStr);
                if (ytdKline) {
                    const pct = ((latest / ytdKline.close - 1) * 100).toFixed(2);
                    elYtd.textContent = (pct >= 0 ? '+' : '') + pct + '%';
                    elYtd.className = pct >= 0 ? 'text-up' : 'text-down';
                } else {
                    elYtd.textContent = '--';
                }
            }
        } catch (e) {
            console.error('计算阶段涨幅失败:', e);
        }
    },

    /** 加载利润趋势图 */
    async _loadProfitTrend(code, stale) {
        try {
            const data = await App.fetchJSON(`/api/stock/profit-trend/${code}`);
            if (!data || stale()) return;
            const trends = data.trends;
            if (!trends || trends.length === 0) return;

            const container = document.getElementById('sd-profit-chart');
            if (!container) return;

            const labels = trends.map(t => t.date);
            const revenues = trends.map(t => t.revenue);
            const profits = trends.map(t => t.net_profit);

            this._profitChart = ChartFactory.create('sd-profit-chart', {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: '营收(亿)',
                            data: revenues,
                            backgroundColor: 'rgba(79, 195, 247, 0.6)',
                            borderColor: '#4fc3f7',
                            borderWidth: 1,
                            yAxisID: 'y',
                            order: 2,
                        },
                        {
                            label: '净利润(亿)',
                            data: profits,
                            type: 'line',
                            borderColor: '#ffd54f',
                            backgroundColor: 'rgba(255, 213, 79, 0.1)',
                            borderWidth: 2,
                            fill: true,
                            tension: 0.3,
                            yAxisID: 'y1',
                            order: 1,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {
                        mode: 'index',
                        intersect: false,
                    },
                    plugins: {
                        legend: {
                            labels: { color: '#e0e0e0' },
                        },
                        tooltip: {
                            backgroundColor: '#2a2a3e',
                            titleColor: '#e0e0e0',
                            bodyColor: '#e0e0e0',
                        },
                    },
                    scales: {
                        x: {
                            ticks: { color: '#a0a0a0' },
                            grid: { color: '#2a2a3e' },
                        },
                        y: {
                            position: 'left',
                            title: {
                                display: true,
                                text: '营收(亿)',
                                color: '#4fc3f7',
                            },
                            ticks: { color: '#4fc3f7' },
                            grid: { color: '#2a2a3e' },
                        },
                        y1: {
                            position: 'right',
                            title: {
                                display: true,
                                text: '净利润(亿)',
                                color: '#ffd54f',
                            },
                            ticks: { color: '#ffd54f' },
                            grid: { drawOnChartArea: false },
                        },
                    },
                },
            }, 'sd-profit');
        } catch (e) {
            console.error('加载利润趋势失败:', e);
        }
    },

    /** 加载十大流通股东 */
    async _loadShareholders(code, stale) {
        try {
            const data = await App.fetchJSON(`/api/stock/shareholders/${code}`);
            if (!data || stale()) return;
            const shareholders = data.shareholders;
            const tbody = document.getElementById('sd-shareholders-body');
            if (!tbody) return;

            if (!shareholders || shareholders.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" class="text-muted">暂无数据</td></tr>';
                return;
            }

            tbody.innerHTML = shareholders.map(s => {
                const changeClass = s.change > 0 ? 'text-up' : s.change < 0 ? 'text-down' : '';
                const changeSign = s.change > 0 ? '+' : '';
                return `
                    <tr>
                        <td>${App.escapeHTML(s.name)}</td>
                        <td>${s.shares.toLocaleString()}</td>
                        <td>${s.ratio}%</td>
                        <td class="${changeClass}">${changeSign}${s.change.toLocaleString()}</td>
                        <td class="${changeClass}">${changeSign}${s.change_pct}%</td>
                        <td>${s.date}</td>
                    </tr>
                `;
            }).join('');
        } catch (e) {
            console.error('加载股东数据失败:', e);
        }
    },

    /** 加载分红历史 */
    async _loadDividends(code, stale) {
        try {
            const data = await App.fetchJSON(`/api/stock/dividends/${code}`);
            if (stale()) return;
            if (!data) {
                this._setWorkbenchEvents('dividend', [], {
                    type: 'dividend',
                    title: '分红数据暂缺',
                    source: 'stock_dividends',
                    source_label: '分红',
                    status: 'missing',
                    missing_reason: '分红接口未返回数据',
                });
                return;
            }
            const dividends = data.dividends;
            if (!dividends || dividends.length === 0) {
                this._setWorkbenchEvents('dividend', [], {
                    type: 'dividend',
                    title: '分红记录暂缺',
                    source: 'stock_dividends',
                    source_label: '分红',
                    status: 'missing',
                    missing_reason: '暂无分红记录',
                });
            } else {
                this._setWorkbenchEvents('dividend', dividends.map((d) => {
                    const at = d.notice_date || d.report_date || d.ex_date || d.record_date || '';
                    return {
                        type: 'dividend',
                        status: 'ready',
                        title: d.bonus ? `分红方案：${d.bonus}` : '分红方案',
                        detail: [
                            d.progress ? `进度：${d.progress}` : '',
                            d.report_date ? `报告期：${d.report_date}` : '',
                            d.notice_date ? `公告日：${d.notice_date}` : '',
                        ].filter(Boolean).join(' · '),
                        at,
                        date_key: this._stockDataDateKey(at),
                        source: 'stock_dividends',
                        source_label: '分红',
                        direction: d.progress || '',
                        value: d.bonus || null,
                        link_url: d.url || d.link_url || '',
                        raw: d,
                    };
                }), {
                    type: 'dividend',
                    source: 'stock_dividends',
                    source_label: '分红',
                });
            }
            const tbody = document.getElementById('sd-dividends-body');
            if (!tbody) return;

            if (!dividends || dividends.length === 0) {
                tbody.innerHTML = '<tr><td colspan="4" class="text-muted">暂无分红记录</td></tr>';
                return;
            }

            tbody.innerHTML = dividends.map(d => `
                <tr>
                    <td>${d.report_date}</td>
                    <td>${App.escapeHTML(d.bonus)}</td>
                    <td>${App.escapeHTML(d.progress)}</td>
                    <td>${d.notice_date}</td>
                </tr>
            `).join('');
        } catch (e) {
            console.error('加载分红数据失败:', e);
            if (stale()) return;
            this._setWorkbenchEvents('dividend', [], {
                type: 'dividend',
                title: '分红加载失败',
                source: 'stock_dividends',
                source_label: '分红',
                status: 'missing',
                missing_reason: '分红数据加载失败',
            });
        }
    },

    /** 加载公告信息 */
    async _loadAnnouncements(code, stale) {
        try {
            const data = await App.fetchJSON(`/api/stock/announcements/${code}`);
            if (stale()) return;
            if (!data) {
                this._setWorkbenchEvents('announcement', [], {
                    type: 'announcement',
                    title: '公告数据暂缺',
                    source: 'stock_announcements',
                    source_label: '公告',
                    status: 'missing',
                    missing_reason: '公告接口未返回数据',
                });
                return;
            }
            const announcements = data.announcements;
            if (!announcements || announcements.length === 0) {
                this._setWorkbenchEvents('announcement', [], {
                    type: 'announcement',
                    title: '公告暂缺',
                    source: 'stock_announcements',
                    source_label: '公告',
                    status: 'missing',
                    missing_reason: '暂无公告',
                });
            } else {
                this._setWorkbenchEvents('announcement', announcements.map((a) => ({
                    type: 'announcement',
                    status: 'ready',
                    title: a.title || '公告',
                    detail: [a.type, a.date].filter(Boolean).join(' · '),
                    at: a.date || a.time || '',
                    date_key: this._stockDataDateKey(a.date || a.time),
                    source: 'stock_announcements',
                    source_label: a.type || '公告',
                    direction: a.type || '',
                    value: a.type || null,
                    link_url: a.url || a.link_url || '',
                    raw: a,
                })), {
                    type: 'announcement',
                    source: 'stock_announcements',
                    source_label: '公告',
                });
            }
            const container = document.getElementById('sd-announcements');
            if (!container) return;

            if (!announcements || announcements.length === 0) {
                container.innerHTML = '<p class="text-muted">暂无公告</p>';
                return;
            }

            container.innerHTML = announcements.map(a => `
                <div class="sd-ann-item">
                    <span class="sd-ann-date">${App.escapeHTML(a.date)}</span>
                    <span class="sd-ann-type">${App.escapeHTML(a.type)}</span>
                    <a href="${App.safeHref(a.url)}" target="_blank" rel="noopener" class="sd-ann-title">${App.escapeHTML(a.title)}</a>
                </div>
            `).join('');
        } catch (e) {
            console.error('加载公告失败:', e);
            if (stale()) return;
            this._setWorkbenchEvents('announcement', [], {
                type: 'announcement',
                title: '公告加载失败',
                source: 'stock_announcements',
                source_label: '公告',
                status: 'missing',
                missing_reason: '公告数据加载失败',
            });
        }
    },

    /** 加载个股新闻 */
    async _loadNews(code, stale) {
        try {
            const data = await App.fetchJSON(`/api/stock/news/${code}?limit=15`);
            if (stale()) return;
            if (!data) {
                this._setWorkbenchEvents('news', [], {
                    type: 'news',
                    title: '新闻数据暂缺',
                    source: 'stock_news',
                    source_label: '新闻',
                    status: 'missing',
                    missing_reason: '新闻接口未返回数据',
                });
                return;
            }
            const news = data.news || [];
            const sentiment = data.sentiment || {};
            if (!news.length) {
                this._setWorkbenchEvents('news', [], {
                    type: 'news',
                    title: '新闻暂缺',
                    source: 'stock_news',
                    source_label: '新闻',
                    status: 'missing',
                    missing_reason: '暂无新闻',
                });
            } else {
                this._setWorkbenchEvents('news', news.map((n) => {
                    const at = n.time || n.date || n.publish_time || n.datetime || '';
                    const score = Number(n.sentiment);
                    const scoreText = Number.isFinite(score) ? `情绪 ${score.toFixed(2)}` : '';
                    return {
                        type: 'news',
                        status: 'ready',
                        title: n.title || '个股新闻',
                        detail: [n.summary || n.digest || '', scoreText].filter(Boolean).join(' · '),
                        at,
                        date_key: this._stockDataDateKey(at),
                        source: 'stock_news',
                        source_label: n.source || '新闻',
                        direction: this._stockDataSentimentDirection(score),
                        value: Number.isFinite(score) ? score : null,
                        link_url: n.url || n.link_url || n.link || '',
                        raw: n,
                    };
                }), {
                    type: 'news',
                    source: 'stock_news',
                    source_label: '新闻',
                });
            }
            const container = document.getElementById('sd-news');
            if (!container) return;

            if (!news.length) {
                container.innerHTML = '<p class="text-muted">暂无新闻</p>';
                return;
            }

            // 情绪摘要
            const score = sentiment.sentiment_score || 0;
            const sentCls = score >= 0.1 ? 'text-up' : score <= -0.1 ? 'text-down' : 'text-muted';
            const sentLabel = score >= 0.1 ? '偏多' : score <= -0.1 ? '偏空' : '中性';
            const kw = (sentiment.hot_keywords || []).slice(0, 5);

            container.innerHTML = `
                <div class="sd-news-summary">
                    <span class="sd-news-sentiment ${sentCls}">情绪：${sentLabel} (${score.toFixed(2)})</span>
                    ${kw.length ? `<span class="sd-news-keywords">关键词：${kw.map(k => App.escapeHTML(k)).join('、')}</span>` : ''}
                </div>
                ${news.map(n => {
                    const sCls = n.sentiment > 0.2 ? 'text-up' : n.sentiment < -0.2 ? 'text-down' : 'text-muted';
                    const icon = n.sentiment > 0.2 ? '▲' : n.sentiment < -0.2 ? '▼' : '●';
                    return `<div class="sd-news-item">
                        <span class="sd-news-icon ${sCls}">${icon}</span>
                        <span class="sd-news-title">${App.escapeHTML(n.title || '')}</span>
                        <span class="sd-news-source text-muted">${App.escapeHTML(n.source || '')} ${App.escapeHTML(n.time || '')}</span>
                    </div>`;
                }).join('')}
            `;
        } catch (e) {
            console.error('加载新闻失败:', e);
            if (stale()) return;
            this._setWorkbenchEvents('news', [], {
                type: 'news',
                title: '新闻加载失败',
                source: 'stock_news',
                source_label: '新闻',
                status: 'missing',
                missing_reason: '新闻数据加载失败',
            });
            const container = document.getElementById('sd-news');
            if (container) {
                container.innerHTML = '<p class="text-muted">新闻加载失败</p>';
            }
        }
    },

    /** 加载行业对比（估值对比） */
    async _loadIndustryComparison(code, stale) {
        try {
            const data = await App.fetchJSON(`/api/stock/industry-comparison/${code}`);
            if (!data || stale()) return;
            const stocks = data.stocks || [];
            const industry = data.industry || '--';

            // 更新行业名称
            const nameEl = document.getElementById('sd-industry-name');
            if (nameEl) nameEl.textContent = `行业: ${industry}${stocks.length <= 1 ? '（未找到同行业对比数据）' : ''}`;

            const tbody = document.getElementById('sd-industry-body');
            if (!tbody) return;

            if (stocks.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" class="text-muted">暂无数据</td></tr>';
                return;
            }

            tbody.innerHTML = stocks.map(s => {
                const isCurrent = s.code === code;
                const rowClass = isCurrent ? ' class="sd-industry-current"' : '';
                const pctClass = s.change_pct >= 0 ? 'text-up' : 'text-down';
                const pctSign = s.change_pct >= 0 ? '+' : '';
                const mcapStr = s.market_cap >= 1e12
                    ? (s.market_cap / 1e12).toFixed(2) + '万亿'
                    : s.market_cap >= 1e8
                        ? (s.market_cap / 1e8).toFixed(2) + '亿'
                        : '--';
                return `<tr${rowClass}>
                    <td><strong>${App.escapeHTML(s.name)}</strong><br><small class="text-muted">${s.code}</small></td>
                    <td>¥${s.price.toFixed(2)}</td>
                    <td class="${pctClass}">${pctSign}${s.change_pct.toFixed(2)}%</td>
                    <td>${s.pe_ratio > 0 ? s.pe_ratio.toFixed(2) : '--'}</td>
                    <td>${s.pb_ratio > 0 ? s.pb_ratio.toFixed(2) : '--'}</td>
                    <td>${s.roe > 0 ? s.roe.toFixed(2) + '%' : '--'}</td>
                </tr>`;
            }).join('');
        } catch (e) {
            console.error('加载行业对比失败:', e);
            const tbody = document.getElementById('sd-industry-body');
            if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="text-muted">加载失败</td></tr>';
        }
    },

    /** 加载北向资金持仓数据 */
    async _loadNorthbound(code, stale) {
        try {
            const data = await App.fetchJSON(`/api/stock/northbound/${code}`);
            if (stale()) return;
            if (!data) {
                this._setWorkbenchEvents('northbound', [], {
                    type: 'northbound',
                    title: '北向资金暂缺',
                    source: 'northbound',
                    source_label: '北向资金',
                    status: 'missing',
                    missing_reason: '北向资金接口未返回数据',
                });
                return;
            }
            const records = data.records || [];
            const latest = data.latest || {};
            if (!records.length) {
                this._setWorkbenchEvents('northbound', [], {
                    type: 'northbound',
                    title: '北向持仓记录暂缺',
                    source: 'northbound',
                    source_label: '北向资金',
                    status: 'missing',
                    missing_reason: '暂无北向资金持仓记录',
                });
            } else {
                this._setWorkbenchEvents('northbound', records.slice(0, 20).map((r) => {
                    const changeShares = Number(r.change_shares);
                    const holdShares = Number(r.hold_shares);
                    const direction = Number.isFinite(changeShares)
                        ? (changeShares > 0 ? 'increase' : changeShares < 0 ? 'decrease' : 'flat')
                        : '';
                    const title = direction === 'increase'
                        ? '北向增持'
                        : direction === 'decrease'
                            ? '北向减持'
                            : '北向持仓更新';
                    const changeText = Number.isFinite(changeShares)
                        ? `变动 ${changeShares > 0 ? '+' : ''}${changeShares.toFixed(2)}万股`
                        : '';
                    const holdText = Number.isFinite(holdShares)
                        ? `持股 ${holdShares.toFixed(2)}万股`
                        : '';
                    return {
                        type: 'northbound',
                        status: 'ready',
                        title,
                        detail: [
                            changeText,
                            holdText,
                            r.hold_ratio != null ? `持股占比 ${Number(r.hold_ratio).toFixed(2)}%` : '',
                        ].filter(Boolean).join(' · '),
                        at: r.date || '',
                        date_key: this._stockDataDateKey(r.date),
                        source: 'northbound',
                        source_label: '北向资金',
                        direction,
                        value: Number.isFinite(changeShares) ? changeShares : null,
                        link_url: r.url || r.link_url || '',
                        raw: r,
                    };
                }), {
                    type: 'northbound',
                    source: 'northbound',
                    source_label: '北向资金',
                });
            }

            // 更新统计数据
            const setVal = (id, val) => {
                const el = document.getElementById(id);
                if (el) el.textContent = val;
            };

            if (latest.hold_shares) {
                // hold_shares 单位是万股
                const shares = latest.hold_shares;
                const sharesStr = shares >= 1e4
                    ? (shares / 1e4).toFixed(2) + '亿股'
                    : shares.toFixed(2) + '万股';
                setVal('sd-north-shares', sharesStr);
            }
            if (latest.hold_ratio != null) {
                setVal('sd-north-ratio', latest.hold_ratio.toFixed(2) + '%');
            }
            if (latest.a_ratio != null) {
                setVal('sd-north-a-ratio', latest.a_ratio.toFixed(2) + '%');
            }

            // 绘制持仓变动趋势图
            const canvas = document.getElementById('sd-north-chart');
            if (!canvas || records.length === 0) return;

            // 按日期正序（旧→新）
            const sorted = [...records].reverse();
            const labels = sorted.map(r => r.date.slice(5)); // MM-DD
            const holdData = sorted.map(r => r.hold_shares); // 已经是万股
            const changeData = sorted.map(r => r.change_shares);

            this._northChart = ChartFactory.create('sd-north-chart', {
                type: 'bar',
                data: {
                    labels,
                    datasets: [
                        {
                            label: '持股数(万股)',
                            data: holdData,
                            backgroundColor: 'rgba(139, 134, 128, 0.3)',
                            borderColor: 'rgba(139, 134, 128, 0.8)',
                            borderWidth: 1,
                            yAxisID: 'y',
                            order: 2,
                        },
                        {
                            label: '增减(万股)',
                            data: changeData,
                            type: 'line',
                            borderColor: '#ef5350',
                            backgroundColor: 'rgba(239, 83, 80, 0.1)',
                            borderWidth: 2,
                            pointRadius: 2,
                            fill: false,
                            yAxisID: 'y1',
                            order: 1,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    plugins: {
                        legend: { display: true, labels: { color: '#a29c95', font: { size: 11 } } },
                    },
                    scales: {
                        x: { ticks: { color: '#a29c95', font: { size: 10 }, maxRotation: 45 }, grid: { display: false } },
                        y: {
                            position: 'left',
                            ticks: { color: '#a29c95', font: { size: 10 } },
                            grid: { color: 'rgba(255,255,255,0.05)' },
                            title: { display: true, text: '持股(万股)', color: '#a29c95' },
                        },
                        y1: {
                            position: 'right',
                            ticks: { color: '#ef5350', font: { size: 10 } },
                            grid: { drawOnChartArea: false },
                            title: { display: true, text: '增减(万股)', color: '#ef5350' },
                        },
                    },
                },
            }, 'sd-north');
        } catch (e) {
            console.error('加载北向资金失败:', e);
            if (stale()) return;
            this._setWorkbenchEvents('northbound', [], {
                type: 'northbound',
                title: '北向资金加载失败',
                source: 'northbound',
                source_label: '北向资金',
                status: 'missing',
                missing_reason: '北向资金数据加载失败',
            });
        }
    },

});
