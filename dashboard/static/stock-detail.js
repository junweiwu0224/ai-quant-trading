/* ── 股票详情页（独立Tab） ── */

const StockDetail = {
    _klineChart: null,
    _klineResizeObs: null,
    _indicatorPaneId: null,
    _avgOverlays: null,
    _timelineIndicatorsRegistered: false,
    _profitChart: null,
    _northChart: null,
    _capitalChart: null,
    _currentCode: null,
    _currentPeriod: 'daily',
    _currentIndicator: '',
    _currentKlines: null,
    _currentTimelineTrends: null,
    _currentTimelinePreClose: null,
    _searchBox: null,
    _openGeneration: 0,

    init() {
        // 搜索框 — 只搜索自选股
        this._searchBox = new SearchBox('stock-detail-code', 'stock-detail-dropdown', {
            maxResults: 200,
            formatItem: (s) => `${s.code} ${s.name || ''}`,
        });
        this._searchBox.setDataSource(async (q) => {
            const list = App.watchlistCache || [];
            if (!q) return list;
            const kw = q.toLowerCase();
            return list.filter(s =>
                (s.code && s.code.includes(kw)) ||
                (s.name && s.name.toLowerCase().includes(kw))
            );
        });
        this._searchBox.onSelect((item) => this.open(item.code));
        this._bindChartTabs();
        this._bindIndicatorSelector();

        // 默认分时模式，隐藏指标选择器
        const indicatorEl = document.querySelector('.sd-indicator-selector');
        if (indicatorEl) indicatorEl.style.display = 'none';

        // 主题切换时重绘 KLineChart（canvas 不响应 CSS 变量）
        this._themeObserver = new MutationObserver(() => {
            if (!this._klineChart) return;
            if (this._currentPeriod === 'timeline' && this._currentTimelineTrends) {
                this._renderTimelineChart(this._currentTimelineTrends, this._currentTimelinePreClose);
            } else if (this._currentKlines) {
                this._renderKlineChart(this._currentKlines);
            }
        });
        this._themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    },

    /** 打开某只股票的详情 */
    async open(code) {
        const gen = ++this._openGeneration;
        this._currentCode = code;
        const content = document.getElementById('sd-content');
        const placeholder = document.getElementById('sd-placeholder');
        if (content) content.style.display = 'block';
        if (placeholder) placeholder.style.display = 'none';

        // 更新搜索框显示：代码 + 名称
        const wl = (App.watchlistCache || []).find(s => s.code === code);
        const label = wl ? `${wl.code} ${wl.name || ''}` : code;
        if (this._searchBox) this._searchBox.setValue(label);

        // 显示全局 loading
        this._setLoading(true);

        // 每个加载独立 try/catch，一个失败不影响其他
        const stale = () => gen !== this._openGeneration;
        const loads = [
            this._loadDetail(code, stale),
            this._loadTimeline(code, stale),
            this._loadCapitalFlow(code, stale),
            this._loadOrderBook(code, stale),
            this._loadPeriodReturns(code, stale),
            this._loadProfitTrend(code, stale),
            this._loadShareholders(code, stale),
            this._loadDividends(code, stale),
            this._loadAnnouncements(code, stale),
            this._loadIndustryComparison(code, stale),
            this._loadNorthbound(code, stale),
        ];
        await Promise.allSettled(loads);

        if (stale()) return;
        this._setLoading(false);
    },

    /** 全局 loading 状态 */
    _setLoading(on) {
        const content = document.getElementById('sd-content');
        if (!content) return;
        content.classList.toggle('sd-loading', on);
        content.setAttribute('aria-busy', on);
    },

    /** 切换到行情Tab时刷新（如果有选中股票） */
    refresh() {
        if (this._currentCode) {
            this.open(this._currentCode);
        }
    },

    async _loadDetail(code, stale) {
        try {
            const data = await App.fetchJSON(`/api/stock/detail/${code}`);
            if (!data || stale()) return;
            this._renderDetailHeader(data);
            this._renderDetailStats(data);
        } catch (e) {
            console.error('加载股票详情失败:', e);
            App.toast('加载股票详情失败', 'error');
        }
    },

    _renderDetailHeader(data) {
        document.getElementById('sd-name').textContent = data.name || '--';
        document.getElementById('sd-code').textContent = data.code || '--';

        const priceEl = document.getElementById('sd-price');
        priceEl.textContent = data.price != null ? '¥' + data.price.toFixed(2) : '--';
        priceEl.className = 'sd-price ' + ((data.change_pct || 0) >= 0 ? 'text-up' : 'text-down');

        const changeEl = document.getElementById('sd-change');
        if (data.change != null && data.change_pct != null) {
            const sign = data.change >= 0 ? '+' : '';
            changeEl.textContent = `${sign}${data.change.toFixed(2)}  ${sign}${data.change_pct.toFixed(2)}%`;
        } else {
            changeEl.textContent = '--';
        }
        changeEl.className = 'sd-change ' + ((data.change_pct || 0) >= 0 ? 'text-up' : 'text-down');

        document.getElementById('sd-industry').textContent = data.industry || '';
        document.getElementById('sd-sector').textContent = data.sector || '';

        const conceptsEl = document.getElementById('sd-concepts');
        if (data.concepts && data.concepts.length > 0) {
            conceptsEl.innerHTML = data.concepts.slice(0, 15).map(c =>
                `<span class="sd-tag">${App.escapeHTML(c)}</span>`
            ).join('');
        } else {
            conceptsEl.innerHTML = '';
        }
    },

    _renderDetailStats(data) {
        const set = (id, v) => {
            const el = document.getElementById(id);
            if (el) el.textContent = v || '--';
        };

        // 基础统计
        set('sd-mcap', data.market_cap);
        set('sd-ccap', data.circulating_cap);
        set('sd-pe', data.pe_ratio != null ? data.pe_ratio : '--');
        set('sd-pb', data.pb_ratio != null ? data.pb_ratio : '--');
        set('sd-turnover', data.turnover_rate ? data.turnover_rate + '%' : '--');
        set('sd-amp', data.amplitude ? data.amplitude + '%' : '--');
        set('sd-vr', data.volume_ratio != null ? data.volume_ratio : '--');

        // 52周高低 & 均量
        set('sd-52w-high', data.high_52w ? '¥' + data.high_52w.toFixed(2) : '--');
        set('sd-52w-low', data.low_52w ? '¥' + data.low_52w.toFixed(2) : '--');
        set('sd-avg-vol-5d', data.avg_volume_5d ? this._formatVolume(data.avg_volume_5d) : '--');
        set('sd-avg-vol-10d', data.avg_volume_10d ? this._formatVolume(data.avg_volume_10d) : '--');

        // 财务指标
        set('sd-eps', data.eps ? '¥' + data.eps.toFixed(2) : '--');
        set('sd-bps', data.bps ? '¥' + data.bps.toFixed(2) : '--');
        set('sd-revenue', data.revenue);
        set('sd-revenue-growth', data.revenue_growth ? data.revenue_growth.toFixed(2) + '%' : '--');
        set('sd-net-profit', data.net_profit);
        set('sd-net-profit-growth', data.net_profit_growth ? data.net_profit_growth.toFixed(2) + '%' : '--');
        set('sd-gross-margin', data.gross_margin ? data.gross_margin.toFixed(2) + '%' : '--');
        set('sd-net-margin', data.net_margin ? data.net_margin.toFixed(2) + '%' : '--');
        set('sd-roe', data.roe ? data.roe.toFixed(2) + '%' : '--');
        set('sd-debt-ratio', data.debt_ratio ? data.debt_ratio.toFixed(2) + '%' : '--');

        // 股本 & 估值
        set('sd-total-shares', data.total_shares);
        set('sd-circulating-shares', data.circulating_shares);
        set('sd-pe-ttm', data.pe_ttm != null ? data.pe_ttm : '--');
        set('sd-ps', data.ps_ratio != null ? data.ps_ratio : '--');
        set('sd-dividend-yield', data.dividend_yield ? data.dividend_yield.toFixed(2) + '%' : '--');

        // 涨跌停 & 内外盘
        set('sd-limit-up', data.limit_up ? '¥' + data.limit_up.toFixed(2) : '--');
        set('sd-limit-down', data.limit_down ? '¥' + data.limit_down.toFixed(2) : '--');
        set('sd-outer-vol', data.outer_volume ? this._formatVolume(data.outer_volume) + '手' : '--');
        set('sd-inner-vol', data.inner_volume ? this._formatVolume(data.inner_volume) + '手' : '--');
    },

    _formatVolume(vol) {
        if (vol >= 1e8) return (vol / 1e8).toFixed(2) + '亿';
        if (vol >= 1e4) return (vol / 1e4).toFixed(2) + '万';
        return vol.toFixed(0);
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

            // 清除现有图表
            if (this._profitChart) {
                this._profitChart.destroy();
                this._profitChart = null;
            }

            const labels = trends.map(t => t.date);
            const revenues = trends.map(t => t.revenue);
            const profits = trends.map(t => t.net_profit);

            this._profitChart = new Chart(container, {
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
            });
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
            if (!data || stale()) return;
            const dividends = data.dividends;
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
        }
    },

    /** 加载公告信息 */
    async _loadAnnouncements(code, stale) {
        try {
            const data = await App.fetchJSON(`/api/stock/announcements/${code}`);
            if (!data || stale()) return;
            const announcements = data.announcements;
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
            if (!data || stale()) return;
            const records = data.records || [];
            const latest = data.latest || {};

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

            // 销毁旧图表
            if (this._northChart) {
                this._northChart.destroy();
                this._northChart = null;
            }

            // 按日期正序（旧→新）
            const sorted = [...records].reverse();
            const labels = sorted.map(r => r.date.slice(5)); // MM-DD
            const holdData = sorted.map(r => r.hold_shares); // 已经是万股
            const changeData = sorted.map(r => r.change_shares);

            this._northChart = new Chart(canvas, {
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
            });
        } catch (e) {
            console.error('加载北向资金失败:', e);
        }
    },

    async _loadKline(code, period) {
        this._currentPeriod = period;
        try {
            const data = await App.fetchJSON(`/api/stock/kline/${code}?period=${period}&count=200`);
            if (!data || !data.klines) return;
            this._renderKlineChart(data.klines);
            document.querySelectorAll('#tab-stock .sd-chart-tabs .sd-tab').forEach(t => {
                const isActive = t.dataset.period === period;
                t.classList.toggle('active', isActive);
                t.setAttribute('aria-selected', isActive);
            });
            // 同步指标选择器状态
            const select = document.getElementById('sd-indicator-select');
            if (select) select.value = this._currentIndicator || '';
        } catch (e) {
            console.error('加载K线失败:', e);
        }
    },

    /** 读取页面 CSS 变量 */
    _cssVar(name) {
        return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    },

    /** KLineChart 动态样式（跟随页面主题） */
    _klineStyles() {
        const c = (name) => this._cssVar(name);
        const upColor = c('--up-color') || '#c65746';
        const downColor = c('--down-color') || '#10b981';
        const textPrimary = c('--text-primary') || '#2d2a26';
        const textSecondary = c('--text-secondary') || '#6d6760';
        const borderColor = c('--border-color') || '#e3e1db';
        const bgPrimary = c('--bg-primary') || '#f0eee8';
        const bgSecondary = c('--bg-secondary') || '#faf9f5';
        const gridColor = borderColor;
        return {
            grid: {
                show: true,
                horizontal: { color: gridColor },
                vertical: { color: gridColor },
            },
            candle: {
                type: 'solid',
                bar: {
                    upColor: upColor,
                    downColor: downColor,
                    upBorderColor: upColor,
                    downBorderColor: downColor,
                    upWickColor: upColor,
                    downWickColor: downColor,
                },
                priceMark: {
                    show: true,
                    high: { show: true, color: textSecondary, textSize: 10 },
                    low: { show: true, color: textSecondary, textSize: 10 },
                    last: {
                        show: true,
                        upColor: upColor,
                        downColor: downColor,
                        noChangeColor: textSecondary,
                        line: { show: true, style: 'dashed', size: 1 },
                        text: { show: true, size: 11, color: '#fff', style: 'fill', borderRadius: 2, paddingLeft: 4, paddingTop: 2, paddingRight: 4, paddingBottom: 2 },
                    },
                },
                tooltip: {
                    showRule: 'always',
                    showType: 'standard',
                    text: { size: 12, color: textPrimary, marginLeft: 8, marginTop: 6, marginRight: 8, marginBottom: 0 },
                },
                area: {
                    lineColor: '#4fc3f7',
                    lineSize: 2,
                    value: 'close',
                    backgroundColor: [
                        { offset: 0, color: 'rgba(79,195,247,0.35)' },
                        { offset: 1, color: 'rgba(79,195,247,0.03)' },
                    ],
                },
            },
            indicator: {
                ohlc: { upColor: upColor, downColor: downColor },
                bars: [
                    { upColor: upColor + '99', downColor: downColor + '99', noChangeColor: textSecondary },
                ],
                lines: [
                    { color: '#e6a817', size: 1 },
                    { color: '#2196f3', size: 1 },
                    { color: '#ff7043', size: 1 },
                    { color: '#66bb6a', size: 1 },
                    { color: '#ab47bc', size: 1 },
                    { color: '#00bcd4', size: 1 },
                ],
                tooltip: {
                    showRule: 'always',
                    showType: 'standard',
                    text: { size: 12, color: textPrimary, marginLeft: 8, marginTop: 6, marginRight: 8, marginBottom: 0 },
                },
            },
            xAxis: {
                show: true,
                size: 'auto',
                axisLine: { show: true, color: borderColor },
                tickLine: { show: true, color: borderColor },
                tickText: { show: true, color: textSecondary, size: 11 },
            },
            yAxis: {
                show: true,
                size: 'auto',
                position: 'right',
                type: 'normal',
                axisLine: { show: true, color: borderColor },
                tickLine: { show: true, color: borderColor },
                tickText: { show: true, color: textSecondary, size: 11 },
            },
            separator: { size: 1, color: borderColor, activeBackgroundColor: bgPrimary },
            crosshair: {
                show: true,
                horizontal: {
                    show: true,
                    line: { show: true, style: 'dashed', size: 1, color: textSecondary, dashedValue: [4, 3] },
                    text: {
                        show: true, style: 'fill', color: '#fff', size: 11,
                        family: 'Helvetica Neue', weight: 'normal',
                        backgroundColor: textPrimary,
                        borderStyle: 'solid', borderSize: 1, borderColor: borderColor, borderRadius: 4,
                        paddingLeft: 6, paddingRight: 6, paddingTop: 3, paddingBottom: 3,
                    },
                },
                vertical: {
                    show: true,
                    line: { show: true, style: 'dashed', size: 1, color: textSecondary, dashedValue: [4, 3] },
                    text: {
                        show: true, style: 'fill', color: '#fff', size: 11,
                        family: 'Helvetica Neue', weight: 'normal',
                        backgroundColor: textPrimary,
                        borderStyle: 'solid', borderSize: 1, borderColor: borderColor, borderRadius: 4,
                        paddingLeft: 6, paddingRight: 6, paddingTop: 3, paddingBottom: 3,
                    },
                },
            },
        };
    },

    /** 使用 KLineChart 渲染 K 线图 */
    _renderKlineChart(klines) {
        const container = document.getElementById('sd-kline-chart');
        if (!container) return;

        // 销毁旧图表
        if (this._klineChart) {
            klinecharts.dispose(this._klineChart);
            this._klineChart = null;
        }
        if (this._klineResizeObs) {
            this._klineResizeObs.disconnect();
            this._klineResizeObs = null;
        }
        this._indicatorPaneId = null;

        // 清除容器残留内容
        container.innerHTML = '';

        if (!klines || klines.length === 0) {
            container.innerHTML = '<p class="text-muted" style="text-align:center;padding:2rem">暂无K线数据</p>';
            return;
        }

        this._currentKlines = klines;

        // 初始化 KLineChart（中文 + 跟随页面主题）
        const chart = klinecharts.init(container, { locale: 'zh-CN', styles: this._klineStyles() });
        this._klineChart = chart;

        // 加载 K 线数据（timestamp 转毫秒）
        chart.applyNewData(klines.map(k => ({
            timestamp: new Date(k.date + 'T00:00:00+08:00').getTime(),
            open: k.open,
            high: k.high,
            low: k.low,
            close: k.close,
            volume: k.volume,
        })));

        // MA 均线（叠加主图）
        chart.createIndicator('MA', false, { id: 'candle_pane' });

        // 成交量（独立 pane）
        chart.createIndicator('VOL', false);

        // BOLL 布林带（叠加主图，替代 MA 显示）
        if (this._currentIndicator === 'BOLL') {
            chart.createIndicator('BOLL', false, { id: 'candle_pane' });
        }

        // 副图指标（MACD/KDJ/RSI/WR/OBV）
        const subIndicators = ['MACD', 'KDJ', 'RSI', 'WR', 'OBV'];
        if (this._currentIndicator && subIndicators.includes(this._currentIndicator)) {
            const result = chart.createIndicator(this._currentIndicator, false);
            this._indicatorPaneId = Array.isArray(result) ? result[0] : result;
        }

        // 自适应宽度
        this._klineResizeObs = new ResizeObserver(() => chart.resize());
        this._klineResizeObs.observe(container);

        // Y轴涨跌幅标签（十字线悬停时显示在Y轴位置）
        this._bindCrosshairPctLabel(chart, klines, container);
    },

    /** 绑定十字线 Y 轴涨跌幅标签 */
    _bindCrosshairPctLabel(chart, klines, container) {
        let pctEl = container.querySelector('.sd-crosshair-pct');
        if (!pctEl) {
            pctEl = document.createElement('div');
            pctEl.className = 'sd-crosshair-pct';
            container.style.position = 'relative';
            container.appendChild(pctEl);
        }

        chart.subscribeAction('onCrosshairChange', (crosshair) => {
            if (!crosshair || !crosshair.kLineData || crosshair.dataIndex == null) {
                pctEl.style.display = 'none';
                return;
            }
            const idx = crosshair.dataIndex;
            const price = crosshair.kLineData.close;
            if (!price || idx <= 0) { pctEl.style.display = 'none'; return; }

            const prevClose = klines[idx - 1]?.close;
            if (!prevClose || prevClose <= 0) { pctEl.style.display = 'none'; return; }

            const pct = (price - prevClose) / prevClose * 100;
            const sign = pct >= 0 ? '+' : '';
            pctEl.textContent = `${sign}${pct.toFixed(2)}%`;
            pctEl.style.display = 'block';
            pctEl.style.color = pct > 0.01 ? '#c65746' : pct < -0.01 ? '#10b981' : '#6d6760';

            // 用 crosshair.y 像素位置定位
            if (crosshair.y != null) {
                pctEl.style.top = `${crosshair.y}px`;
            }
        });
    },

    /** 绑定指标选择器事件（KLineChart 版） */
    _bindIndicatorSelector() {
        const select = document.getElementById('sd-indicator-select');
        if (!select) return;
        select.addEventListener('change', () => {
            const chart = this._klineChart;
            const subIndicators = ['MACD', 'KDJ', 'RSI', 'WR', 'OBV'];
            const newValue = select.value;

            // 移除旧副图指标
            if (this._indicatorPaneId && chart) {
                chart.removeIndicator(this._indicatorPaneId);
                this._indicatorPaneId = null;
            }

            this._currentIndicator = newValue;

            if (this._currentPeriod === 'timeline') {
                // 分时模式下选指标 → 自动切到日K
                if (newValue && this._currentCode) {
                    this._loadKline(this._currentCode, 'daily');
                }
            } else if (chart && this._currentKlines) {
                // BOLL 叠加主图，需要重建
                if (newValue === 'BOLL') {
                    chart.createIndicator('BOLL', false, { id: 'candle_pane' });
                } else if (subIndicators.includes(newValue)) {
                    const result = chart.createIndicator(newValue, false);
                    this._indicatorPaneId = Array.isArray(result) ? result[0] : result;
                }
            }
        });
    },

    async _loadTimeline(code, stale) {
        this._currentPeriod = 'timeline';
        try {
            const data = await App.fetchJSON(`/api/stock/timeline/${code}`);
            if (!data || stale()) return;
            this._renderTimelineChart(data.trends, data.pre_close);
        } catch (e) {
            console.error('加载分时失败:', e);
        }
    },


    /** 注册分时图专用指标（成交量涨跌着色 + 涨跌双色区域） */
    _registerTimelineIndicators() {
        if (this._timelineIndicatorsRegistered) return;
        this._timelineIndicatorsRegistered = true;

        // 分时成交量（涨跌着色基于昨收）
        klinecharts.registerIndicator({
            name: 'TIMELINE_VOL',
            shortName: '成交量',
            series: 'volume',
            shouldFormatBigNumber: true,
            precision: 0,
            minValue: 0,
            figures: [{
                key: 'vol', title: 'VOL: ', type: 'bar', baseValue: 0,
                styles: ({ data }) => {
                    const cur = data.current;
                    if (!cur) return {};
                    const pc = cur.preClose;
                    if (pc == null) return {};
                    if (cur.close > pc) return { color: '#c65746' };
                    if (cur.close < pc) return { color: '#10b981' };
                    return {};
                },
            }],
            calc: (dataList, indicator) => {
                const pc = indicator.extendData;
                return dataList.map(k => ({
                    vol: k.volume ?? 0,
                    close: k.close,
                    preClose: pc,
                }));
            },
        });

        // Y轴涨跌幅百分比标签（左侧显示）
        klinecharts.registerIndicator({
            name: 'TIMELINE_PCT',
            shortName: '涨跌幅',
            series: 'price',
            figures: [],
            calc: (dataList, indicator) => {
                const pc = indicator.extendData;
                return dataList.map(k => ({ pct: pc ? ((k.close - pc) / pc * 100) : 0 }));
            },
            draw: ({ ctx, indicator, yAxis, bounding }) => {
                const pc = indicator.extendData;
                if (!pc || pc <= 0) return false;
                const range = yAxis.getRange?.();
                if (!range) return false;
                const { displayFrom, displayTo } = range;
                const step = (displayTo - displayFrom) / 6;
                if (step === 0) return true;
                ctx.save();
                ctx.font = '10px sans-serif';
                ctx.textAlign = 'right';
                for (let v = displayFrom; v <= displayTo; v += step) {
                    const pct = ((v - pc) / pc * 100);
                    const y = yAxis.convertToPixel(v);
                    if (y < 0 || y > bounding.height) continue;
                    const pctText = (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%';
                    ctx.fillStyle = pct > 0.01 ? '#c65746' : pct < -0.01 ? '#10b981' : '#6d6760';
                    ctx.fillText(pctText, -4, y + 3);
                }
                ctx.restore();
                return true;
            },
        });

        // 分时图涨跌双色区域（自定义绘制）
        klinecharts.registerIndicator({
            name: 'TIMELINE_AREA',
            shortName: '走势',
            series: 'price',
            figures: [],
            calc: (dataList) => dataList.map(k => ({ close: k.close })),
            draw: ({ ctx, indicator, xAxis, yAxis, bounding }) => {
                const pc = indicator.extendData;
                if (pc == null) return false;
                const dataList = indicator.result;
                if (!dataList || dataList.length < 2) return false;

                const getX = (i) => xAxis.convertToPixel(i);
                const getY = (v) => yAxis.convertToPixel(v);
                const upColor = '#c65746';
                const downColor = '#10b981';
                const upBg = 'rgba(198, 87, 70, 0.18)';
                const downBg = 'rgba(16, 185, 129, 0.18)';
                const y0 = getY(pc);

                // 涨区填充（价格 >= 昨收）
                ctx.save();
                ctx.beginPath();
                let started = false;
                let lastAbove = null;
                for (let i = 0; i < dataList.length; i++) {
                    const v = dataList[i].close;
                    if (v == null) continue;
                    const above = v >= pc;
                    if (lastAbove !== null && above !== lastAbove) {
                        const prev = dataList[i - 1]?.close;
                        if (prev != null) {
                            const x0 = getX(i - 1), x1 = getX(i);
                            const ratio = (pc - prev) / (v - prev);
                            ctx.lineTo(x0 + ratio * (x1 - x0), y0);
                        }
                    }
                    if (above) {
                        ctx.lineTo(getX(i), getY(v));
                        if (!started) started = true;
                    } else if (started) {
                        ctx.lineTo(getX(i), y0);
                    }
                    lastAbove = above;
                }
                ctx.lineTo(getX(dataList.length - 1), y0);
                ctx.closePath();
                ctx.fillStyle = upBg;
                ctx.fill();
                ctx.restore();

                // 跌区填充（价格 < 昨收）
                ctx.save();
                ctx.beginPath();
                started = false;
                let lastBelow = null;
                for (let i = 0; i < dataList.length; i++) {
                    const v = dataList[i].close;
                    if (v == null) continue;
                    const below = v < pc;
                    if (lastBelow !== null && below !== lastBelow) {
                        const prev = dataList[i - 1]?.close;
                        if (prev != null) {
                            const x0 = getX(i - 1), x1 = getX(i);
                            const ratio = (pc - prev) / (v - prev);
                            ctx.lineTo(x0 + ratio * (x1 - x0), y0);
                        }
                    }
                    if (below) {
                        ctx.lineTo(getX(i), getY(v));
                        if (!started) started = true;
                    } else if (started) {
                        ctx.lineTo(getX(i), y0);
                    }
                    lastBelow = below;
                }
                ctx.lineTo(getX(dataList.length - 1), y0);
                ctx.closePath();
                ctx.fillStyle = downBg;
                ctx.fill();
                ctx.restore();

                // 价格线（两色：涨红跌绿）
                ctx.save();
                ctx.lineWidth = 2;
                ctx.lineJoin = 'round';
                for (let i = 1; i < dataList.length; i++) {
                    const v = dataList[i].close;
                    const pv = dataList[i - 1]?.close;
                    if (v == null || pv == null) continue;
                    ctx.beginPath();
                    ctx.strokeStyle = v >= pc ? upColor : downColor;
                    ctx.moveTo(getX(i - 1), getY(pv));
                    ctx.lineTo(getX(i), getY(v));
                    ctx.stroke();
                }
                ctx.restore();

                return true;
            },
        });
    },

    /** 使用 KLineChart 渲染分时图（涨跌双色区域） */
    _renderTimelineChart(trends, preClose) {
        const container = document.getElementById('sd-kline-chart');
        if (!container) return;

        // 销毁旧图表
        if (this._klineChart) {
            klinecharts.dispose(this._klineChart);
            this._klineChart = null;
        }
        if (this._klineResizeObs) {
            this._klineResizeObs.disconnect();
            this._klineResizeObs = null;
        }
        this._indicatorPaneId = null;
        container.innerHTML = '';

        if (!trends || trends.length === 0) {
            container.innerHTML = '<p class="text-muted" style="text-align:center;padding:2rem">非交易时段</p>';
            return;
        }

        // 保存数据供主题切换重绘
        this._currentTimelineTrends = trends;
        this._currentTimelinePreClose = preClose;

        // 初始化 KLineChart（默认样式）
        // 分时模式下隐藏默认蜡烛（由 TIMELINE_AREA 自定义绘制）
        const baseStyles = this._klineStyles();
        const timelineStyles = {
            ...baseStyles,
            candle: {
                ...baseStyles.candle,
                type: 'area',
                area: {
                    lineColor: 'transparent',
                    lineSize: 0,
                    value: 'close',
                    backgroundColor: [{ offset: 0, color: 'transparent' }, { offset: 1, color: 'transparent' }],
                },
                priceMark: { show: false },
                tooltip: { showRule: 'none' },
            },
        };
        const chart = klinecharts.init(container, { locale: 'zh-CN', styles: timelineStyles });
        this._klineChart = chart;

        // 解析时间字符串为毫秒时间戳
        const parseTime = (timeStr) => {
            const parts = timeStr.split(' ');
            if (parts.length > 1) {
                const [date, time] = parts;
                const [year, month, day] = date.split('-');
                const [hour, minute] = time.split(':');
                return new Date(year, month - 1, day, hour, minute).getTime();
            }
            return new Date(timeStr).getTime();
        };

        // 加载分时数据
        chart.applyNewData(trends.map(t => ({
            timestamp: parseTime(t.time),
            open: t.close,
            high: t.close,
            low: t.close,
            close: t.close,
            volume: t.volume,
        })));

        // 注册分时专用指标
        this._registerTimelineIndicators();

        // 涨跌双色区域指标（自定义绘制走势线+区域填充）
        const areaResult = chart.createIndicator('TIMELINE_AREA', false, { id: 'candle_pane' });
        const areaPaneId = Array.isArray(areaResult) ? areaResult[0] : areaResult;
        chart.overrideIndicator({
            name: 'TIMELINE_AREA',
            paneId: areaPaneId,
            extendData: preClose,
        });

        // 均价线（segment overlay 绘制逐段连线）
        this._addTimelineAvgOverlay(chart, trends, parseTime);

        // 昨收参考线
        if (preClose) {
            this._addPreCloseOverlay(chart, trends, parseTime, preClose);
        }

        // 分时成交量（涨跌着色）
        const volResult = chart.createIndicator('TIMELINE_VOL', false);
        const volPaneId = Array.isArray(volResult) ? volResult[0] : volResult;
        chart.overrideIndicator({
            name: 'TIMELINE_VOL',
            paneId: volPaneId,
            extendData: preClose,
        });

        // Y轴涨跌幅百分比标签（自定义绘制叠加在主图 Y 轴上）
        if (preClose && preClose > 0) {
            const pctResult = chart.createIndicator('TIMELINE_PCT', false, { id: 'candle_pane' });
            const pctPaneId = Array.isArray(pctResult) ? pctResult[0] : pctResult;
            chart.overrideIndicator({
                name: 'TIMELINE_PCT',
                paneId: pctPaneId,
                extendData: preClose,
            });
        }

        // 十字光标联动 — 更新数据面板
        const infoPanel = document.getElementById('sd-timeline-info');
        if (infoPanel) infoPanel.classList.remove('hidden');
        const lastTrend = trends[trends.length - 1];
        this._updateTimelineInfo(lastTrend, preClose, trends);

        // Y轴涨跌幅浮层标签
        let tlPctEl = container.querySelector('.sd-crosshair-pct');
        if (!tlPctEl) {
            tlPctEl = document.createElement('div');
            tlPctEl.className = 'sd-crosshair-pct';
            container.appendChild(tlPctEl);
        }

        chart.subscribeAction('onCrosshairChange', (crosshair) => {
            if (!crosshair || !crosshair.kLineData) {
                this._updateTimelineInfo(lastTrend, preClose, trends);
                tlPctEl.style.display = 'none';
                return;
            }
            const idx = crosshair.dataIndex;
            const t = trends[idx];
            if (t) this._updateTimelineInfo(t, preClose, trends);

            // 更新 Y 轴涨跌幅浮层
            const price = crosshair.kLineData.close;
            if (preClose && preClose > 0 && price && crosshair.y != null) {
                const pct = (price - preClose) / preClose * 100;
                const sign = pct >= 0 ? '+' : '';
                tlPctEl.textContent = `${sign}${pct.toFixed(2)}%`;
                tlPctEl.style.display = 'block';
                tlPctEl.style.color = pct > 0.01 ? '#c65746' : pct < -0.01 ? '#10b981' : '#6d6760';
                tlPctEl.style.top = `${crosshair.y}px`;
            } else {
                tlPctEl.style.display = 'none';
            }
        });

        // Y轴自动缩放（放大后线始终可见）
        chart.setAutoScale(true);

        chart.timeScale().fitContent();

        // 自适应宽度
        this._klineResizeObs = new ResizeObserver(() => chart.resize());
        this._klineResizeObs.observe(container);
    },

    /** 更新分时信息面板 */
    _updateTimelineInfo(trend, preClose, trends) {
        const set = (id, val, cls) => {
            const el = document.getElementById(id);
            if (!el) return;
            el.textContent = val;
            if (cls) el.className = cls;
        };

        // 时间
        const timeStr = trend.time ? trend.time.split(' ')[1] || trend.time : '--:--';
        set('sd-ti-time', timeStr);

        // 现价
        const price = trend.close;
        const priceClass = preClose ? (price >= preClose ? 'text-up' : 'text-down') : '';
        set('sd-ti-price', price != null ? price.toFixed(2) : '--', priceClass);

        // 均价
        const avg = trend.avg_price;
        set('sd-ti-avg', avg != null ? avg.toFixed(2) : '--');

        // 涨跌 = 现价 - 昨收
        if (preClose && price != null) {
            const change = price - preClose;
            const sign = change >= 0 ? '+' : '';
            set('sd-ti-change', sign + change.toFixed(2), change >= 0 ? 'text-up' : 'text-down');

            const pct = (change / preClose * 100);
            set('sd-ti-pct', sign + pct.toFixed(2) + '%', change >= 0 ? 'text-up' : 'text-down');
        } else {
            set('sd-ti-change', '--');
            set('sd-ti-pct', '--');
        }

        // 量
        const vol = trend.volume;
        if (vol != null) {
            const volStr = vol >= 1e8 ? (vol / 1e8).toFixed(2) + '亿'
                : vol >= 1e4 ? (vol / 1e4).toFixed(2) + '万'
                : vol.toFixed(0);
            set('sd-ti-vol', volStr + '手');
        }

        // 额（volume * price 近似）
        if (vol != null && price != null) {
            const amount = vol * price;
            const amtStr = amount >= 1e12 ? (amount / 1e12).toFixed(2) + '万亿'
                : amount >= 1e8 ? (amount / 1e8).toFixed(2) + '亿'
                : amount >= 1e4 ? (amount / 1e4).toFixed(2) + '万'
                : amount.toFixed(0);
            set('sd-ti-amount', amtStr);
        }
    },

    /** 均价线 overlay（逐段 segment 连线） */
    _addTimelineAvgOverlay(chart, trends, parseTime) {
        const segs = [];
        for (let i = 1; i < trends.length; i++) {
            if (trends[i].avg_price == null || trends[i - 1].avg_price == null) continue;
            segs.push(chart.createOverlay({
                name: 'segment',
                points: [
                    { timestamp: parseTime(trends[i - 1].time), value: trends[i - 1].avg_price },
                    { timestamp: parseTime(trends[i].time), value: trends[i].avg_price },
                ],
                styles: { line: { style: 'solid', color: '#e6a817', size: 1 } },
                lock: true,
            }));
        }
        this._avgOverlays = segs;
    },

    /** 昨收参考线 overlay（水平延伸线） */
    _addPreCloseOverlay(chart, trends, parseTime, preClose) {
        chart.createOverlay({
            name: 'straightLine',
            points: [
                { timestamp: parseTime(trends[0].time), value: preClose },
                { timestamp: parseTime(trends[trends.length - 1].time), value: preClose },
            ],
            styles: { line: { style: 'dashed', color: 'rgba(128,128,128,0.5)', size: 1 } },
            lock: true,
        });
    },

    async _loadCapitalFlow(code, stale) {
        try {
            const data = await App.fetchJSON(`/api/stock/capital-flow/${code}?days=20`);
            if (!data || stale()) return;
            this._renderCapitalChart(data.flow);
        } catch (e) {
            console.error('加载资金流向失败:', e);
        }
    },

    _renderCapitalChart(flow) {
        const canvas = document.getElementById('sd-capital-chart');
        if (!canvas) return;

        // 销毁旧图表
        if (this._capitalChart) {
            this._capitalChart.destroy();
            this._capitalChart = null;
        }

        if (!flow || flow.length === 0) {
            canvas.parentElement.innerHTML = '<p class="text-muted" style="text-align:center;padding:1rem">暂无资金流向数据</p>';
            return;
        }

        const labels = flow.map(f => f.date.substring(5));

        // 只展示主力净流入（散户永远是反数，无需重复展示）
        const mainData = flow.map(f => (f.super_net + f.big_net) / 1e4);
        // 超大单单独展示
        const superData = flow.map(f => f.super_net / 1e4);

        // A股惯例：红=流入，绿=流出
        const getColor = (v) => v >= 0 ? 'rgba(239, 83, 80, 0.85)' : 'rgba(38, 166, 154, 0.85)';
        const getBorderColor = (v) => v >= 0 ? 'rgba(239, 83, 80, 1)' : 'rgba(38, 166, 154, 1)';

        this._capitalChart = new Chart(canvas, {
            type: 'bar',
            data: {
                labels,
                datasets: [
                    {
                        label: '主力净流入',
                        data: mainData,
                        backgroundColor: mainData.map(getColor),
                        borderColor: mainData.map(getBorderColor),
                        borderWidth: 1,
                        borderRadius: 2,
                    },
                    {
                        label: '其中: 超大单',
                        data: superData,
                        backgroundColor: 'rgba(255, 193, 7, 0.6)',
                        borderColor: 'rgba(255, 193, 7, 0.9)',
                        borderWidth: 1,
                        borderRadius: 2,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: {
                            color: '#aaa',
                            font: { size: 11 },
                            usePointStyle: true,
                            pointStyle: 'rectRounded',
                            padding: 15,
                        },
                    },
                    tooltip: {
                        backgroundColor: 'rgba(20,20,35,0.95)',
                        titleColor: '#eee',
                        bodyColor: '#ccc',
                        borderColor: '#444',
                        borderWidth: 1,
                        padding: 10,
                        callbacks: {
                            title: (items) => items[0]?.label || '',
                            label: (context) => {
                                const label = context.dataset.label || '';
                                const value = context.parsed.y;
                                const absValue = Math.abs(value);
                                const formatted = absValue >= 10000
                                    ? (absValue / 10000).toFixed(2) + '亿'
                                    : absValue.toFixed(0) + '万';
                                const prefix = value >= 0 ? '流入 ↑' : '流出 ↓';
                                return `${label}: ${prefix} ${formatted}`;
                            },
                            afterBody: (items) => {
                                if (items.length >= 1) {
                                    const idx = items[0].dataIndex;
                                    const f = flow[idx];
                                    if (f) {
                                        const big = f.big_net / 1e4;
                                        const med = f.medium_net / 1e4;
                                        const small = f.small_net / 1e4;
                                        const absBig = Math.abs(big);
                                        const absMed = Math.abs(med);
                                        const absSmall = Math.abs(small);
                                        const fmt = (v) => v >= 10000 ? (v/10000).toFixed(2)+'亿' : v.toFixed(0)+'万';
                                        return [
                                            `─────────`,
                                            `大单: ${big>=0?'+':'-'}${fmt(absBig)}`,
                                            `中单: ${med>=0?'+':'-'}${fmt(absMed)}`,
                                            `小单: ${small>=0?'+':'-'}${fmt(absSmall)}`,
                                        ];
                                    }
                                }
                                return [];
                            },
                        },
                    },
                },
                scales: {
                    x: {
                        ticks: { color: '#888', maxTicksLimit: 10 },
                        grid: { color: 'rgba(255,255,255,0.05)' },
                    },
                    y: {
                        ticks: {
                            color: '#888',
                            callback: v => {
                                const absV = Math.abs(v);
                                return absV >= 10000
                                    ? (absV / 10000).toFixed(0) + '亿'
                                    : absV.toFixed(0) + '万';
                            },
                        },
                        grid: { color: 'rgba(255,255,255,0.05)' },
                    },
                },
            },
        });
    },

    async _loadOrderBook(code, stale) {
        try {
            const data = await App.fetchJSON(`/api/stock/order-book/${code}`);
            if (!data || stale()) return;
            this._renderOrderBook(data.asks, data.bids);
        } catch (e) {
            console.error('加载盘口失败:', e);
        }
    },

    _renderOrderBook(asks, bids) {
        const asksEl = document.getElementById('sd-asks');
        const bidsEl = document.getElementById('sd-bids');
        if (!asksEl || !bidsEl) return;

        // 检查是否有有效数据（非交易时段API返回全0）
        const hasData = asks.some(a => a.price > 0) || bids.some(b => b.price > 0);
        if (!hasData) {
            asksEl.innerHTML = '<div class="sd-ob-title">卖盘</div><div class="sd-ob-empty">非交易时段</div>';
            bidsEl.innerHTML = '<div class="sd-ob-title">买盘</div><div class="sd-ob-empty">非交易时段</div>';
            return;
        }

        const asksReversed = [...asks].reverse();
        asksEl.innerHTML = '<div class="sd-ob-title">卖盘</div>' +
            asksReversed.map((a, i) => {
                const level = 5 - i;
                return `<div class="sd-ob-row ask">
                    <span class="sd-ob-level">卖${level}</span>
                    <span class="sd-ob-price">${a.price ? a.price.toFixed(2) : '--'}</span>
                    <span class="sd-ob-vol">${a.volume || '--'}</span>
                </div>`;
            }).join('');

        bidsEl.innerHTML = '<div class="sd-ob-title">买盘</div>' +
            bids.map((b, i) => {
                return `<div class="sd-ob-row bid">
                    <span class="sd-ob-level">买${i + 1}</span>
                    <span class="sd-ob-price">${b.price ? b.price.toFixed(2) : '--'}</span>
                    <span class="sd-ob-vol">${b.volume || '--'}</span>
                </div>`;
            }).join('');
    },

    _chartTabsBound: false,

    _bindChartTabs() {
        if (this._chartTabsBound) return;
        this._chartTabsBound = true;
        document.addEventListener('click', (e) => {
            const tab = e.target.closest('#tab-stock .sd-chart-tabs .sd-tab');
            if (!tab || !this._currentCode) return;
            const period = tab.dataset.period;

            // 更新tab样式
            document.querySelectorAll('#tab-stock .sd-chart-tabs .sd-tab').forEach(t => {
                const isActive = t.dataset.period === period;
                t.classList.toggle('active', isActive);
                t.setAttribute('aria-selected', isActive);
            });

            // 分时模式隐藏指标选择器，K线模式显示
            const indicatorEl = document.querySelector('.sd-indicator-selector');
            if (indicatorEl) {
                indicatorEl.style.display = period === 'timeline' ? 'none' : '';
            }

            // 分时信息面板：分时模式显示，K线模式隐藏
            const infoPanel = document.getElementById('sd-timeline-info');
            if (infoPanel) {
                infoPanel.classList.toggle('hidden', period !== 'timeline');
            }

            if (period === 'timeline') {
                this._loadTimeline(this._currentCode);
            } else {
                this._loadKline(this._currentCode, period);
            }
        });
    },
};
