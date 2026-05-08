/* ── 股票详情页（独立Tab） ── */

const StockDetail = {
    _klineChart: null,
    _klineResizeObs: null,
    _candleSeries: null,
    _volumeSeries: null,
    _maSeries: {},
    _indicatorSeries: {},
    _profitChart: null,
    _northChart: null,
    _capitalChart: null,
    _currentCode: null,
    _currentPeriod: 'daily',
    _currentIndicator: '',
    _currentKlines: null,
    _searchBox: null,

    init() {
        // 搜索框
        this._searchBox = new SearchBox('stock-detail-code', 'stock-detail-dropdown', {
            maxResults: 50,
            formatItem: (s) => `${s.code} ${s.name || ''}`,
        });
        this._searchBox.setDataSource(async (q) => {
            if (!q) {
                // 无查询时返回自选股
                return App.watchlistCache || [];
            }
            // 服务器端搜索
            try {
                const results = await App.fetchJSON(`/api/stock/search?q=${encodeURIComponent(q)}&limit=50`);
                return results || [];
            } catch (e) {
                console.error('搜索失败:', e);
                return [];
            }
        });
        this._searchBox.onSelect((item) => this.open(item.code));
        this._bindChartTabs();
        this._bindIndicatorSelector();
    },

    /** 打开某只股票的详情 */
    async open(code) {
        this._currentCode = code;
        const content = document.getElementById('sd-content');
        const placeholder = document.getElementById('sd-placeholder');
        if (content) content.style.display = 'block';
        if (placeholder) placeholder.style.display = 'none';

        // 更新搜索框显示
        if (this._searchBox) this._searchBox.setValue(code);

        // 显示全局 loading
        this._setLoading(true);

        // 每个加载独立 try/catch，一个失败不影响其他
        const loads = [
            this._loadDetail(code),
            this._loadTimeline(code),
            this._loadCapitalFlow(code),
            this._loadOrderBook(code),
            this._loadPeriodReturns(code),
            this._loadProfitTrend(code),
            this._loadShareholders(code),
            this._loadDividends(code),
            this._loadAnnouncements(code),
            this._loadIndustryComparison(code),
            this._loadNorthbound(code),
        ];
        await Promise.allSettled(loads);

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

    async _loadDetail(code) {
        try {
            const data = await App.fetchJSON(`/api/stock/detail/${code}`);
            this._renderDetailHeader(data);
            this._renderDetailStats(data);
        } catch (e) {
            console.error('加载股票详情失败:', e);
            App.toast('加载股票详情失败', 'error');
        }
    },

    _renderDetailHeader(data) {
        document.getElementById('sd-name').textContent = data.name;
        document.getElementById('sd-code').textContent = data.code;

        const priceEl = document.getElementById('sd-price');
        priceEl.textContent = '¥' + data.price.toFixed(2);
        priceEl.className = 'sd-price ' + (data.change_pct >= 0 ? 'text-up' : 'text-down');

        const changeEl = document.getElementById('sd-change');
        const sign = data.change >= 0 ? '+' : '';
        changeEl.textContent = `${sign}${data.change.toFixed(2)}  ${sign}${data.change_pct.toFixed(2)}%`;
        changeEl.className = 'sd-change ' + (data.change_pct >= 0 ? 'text-up' : 'text-down');

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
        set('sd-pe', data.pe_ratio);
        set('sd-pb', data.pb_ratio);
        set('sd-turnover', data.turnover_rate ? data.turnover_rate + '%' : '--');
        set('sd-amp', data.amplitude ? data.amplitude + '%' : '--');
        set('sd-vr', data.volume_ratio);

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
        set('sd-pe-ttm', data.pe_ttm);
        set('sd-ps', data.ps_ratio);
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
    async _loadPeriodReturns(code) {
        try {
            // 加载日K数据（足够计算60日涨幅）
            const data = await App.fetchJSON(`/api/stock/kline/${code}?period=daily&count=250`);
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
                const yearStart = new Date(new Date().getFullYear(), 0, 1);
                const ytdKline = klines.find(k => new Date(k.date) >= yearStart);
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
    async _loadProfitTrend(code) {
        try {
            const data = await App.fetchJSON(`/api/stock/profit-trend/${code}`);
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
    async _loadShareholders(code) {
        try {
            const data = await App.fetchJSON(`/api/stock/shareholders/${code}`);
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
    async _loadDividends(code) {
        try {
            const data = await App.fetchJSON(`/api/stock/dividends/${code}`);
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
    async _loadAnnouncements(code) {
        try {
            const data = await App.fetchJSON(`/api/stock/announcements/${code}`);
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
    async _loadIndustryComparison(code) {
        try {
            const data = await App.fetchJSON(`/api/stock/industry-comparison/${code}`);
            const stocks = data.stocks || [];
            const industry = data.industry || '--';

            // 更新行业名称
            const nameEl = document.getElementById('sd-industry-name');
            if (nameEl) nameEl.textContent = `行业: ${industry}`;

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
    async _loadNorthbound(code) {
        try {
            const data = await App.fetchJSON(`/api/stock/northbound/${code}`);
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

    /** 移除 LightweightCharts 内置的 TradingView logo 链接 */
    _removeTVLogo(container) {
        const remove = () => {
            const logo = container.querySelector('#tv-attr-logo');
            if (logo) logo.remove();
        };
        remove();
        setTimeout(remove, 100);
        setTimeout(remove, 500);
    },

    async _loadKline(code, period) {
        this._currentPeriod = period;
        try {
            const data = await App.fetchJSON(`/api/stock/kline/${code}?period=${period}&count=200`);
            this._renderKlineChart(data.klines);
            document.querySelectorAll('#tab-stock .sd-chart-tabs .sd-tab').forEach(t => {
                const isActive = t.dataset.period === period;
                t.classList.toggle('active', isActive);
                t.setAttribute('aria-selected', isActive);
            });
        } catch (e) {
            console.error('加载K线失败:', e);
        }
    },

    _renderKlineChart(klines) {
        const container = document.getElementById('sd-kline-chart');
        if (!container) return;

        if (this._klineChart) {
            this._klineChart.remove();
            this._klineChart = null;
        }
        // 断开旧 ResizeObserver
        if (this._klineResizeObs) {
            this._klineResizeObs.disconnect();
            this._klineResizeObs = null;
        }
        this._indicatorSeries = {};

        if (!klines || klines.length === 0) {
            container.innerHTML = '<p class="text-muted" style="text-align:center;padding:2rem">暂无K线数据</p>';
            return;
        }

        // 存储 K 线数据供指标使用
        this._currentKlines = klines;

        // 根据是否有副图指标调整高度
        const hasSubIndicator = this._currentIndicator && ['MACD', 'KDJ', 'RSI', 'WR', 'OBV'].includes(this._currentIndicator);
        const mainHeight = hasSubIndicator ? 300 : 400;

        const chart = LightweightCharts.createChart(container, {
            width: container.clientWidth,
            height: hasSubIndicator ? 420 : 400,
            layout: {
                background: { type: 'solid', color: '#1a1a2e' },
                textColor: '#e0e0e0',
            },
            grid: {
                vertLines: { color: '#2a2a3e' },
                horzLines: { color: '#2a2a3e' },
            },
            crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
            rightPriceScale: { borderColor: '#3a3a4e' },
            timeScale: { borderColor: '#3a3a4e', timeVisible: true },
            watermark: { visible: false },
        });
        this._klineChart = chart;
        this._removeTVLogo(container);

        // K 线（A股：红涨绿跌）
        const candleSeries = chart.addCandlestickSeries({
            upColor: '#ef5350',
            downColor: '#26a69a',
            borderUpColor: '#ef5350',
            borderDownColor: '#26a69a',
            wickUpColor: '#ef5350',
            wickDownColor: '#26a69a',
        });
        candleSeries.setData(klines.map(k => ({
            time: k.date,
            open: k.open,
            high: k.high,
            low: k.low,
            close: k.close,
        })));
        this._candleSeries = candleSeries;

        // 成交量（主图底部）
        const volumeSeries = chart.addHistogramSeries({
            priceFormat: { type: 'volume' },
            priceScaleId: 'volume',
        });
        chart.priceScale('volume').applyOptions({
            scaleMargins: { top: hasSubIndicator ? 0.65 : 0.8, bottom: 0 },
        });
        volumeSeries.setData(klines.map(k => ({
            time: k.date,
            value: k.volume,
            color: k.close >= k.open ? 'rgba(239,83,80,0.5)' : 'rgba(38,166,154,0.5)',
        })));
        this._volumeSeries = volumeSeries;

        // MA 均线
        this._addMA(chart, klines, 5, '#f6d365');
        this._addMA(chart, klines, 10, '#42e695');
        this._addMA(chart, klines, 20, '#bb86fc');
        this._addMA(chart, klines, 60, '#03dac6');

        // BOLL 布林带（叠加在主图上）
        if (this._currentIndicator === 'BOLL') {
            this._addBOLL(chart, klines);
        }

        // 副图指标
        if (hasSubIndicator) {
            this._addSubIndicator(chart, klines, this._currentIndicator);
        }

        chart.timeScale().fitContent();

        this._klineResizeObs = new ResizeObserver(() => {
            chart.applyOptions({ width: container.clientWidth });
        });
        this._klineResizeObs.observe(container);
    },

    _addMA(chart, klines, period, color) {
        const maData = [];
        for (let i = period - 1; i < klines.length; i++) {
            let sum = 0;
            for (let j = i - period + 1; j <= i; j++) {
                sum += klines[j].close;
            }
            maData.push({ time: klines[i].date, value: sum / period });
        }
        const series = chart.addLineSeries({
            color: color,
            lineWidth: 1,
            priceLineVisible: false,
            lastValueVisible: false,
            crosshairMarkerVisible: false,
        });
        series.setData(maData);
        this._maSeries[`ma${period}`] = series;
    },

    /** BOLL 布林带（叠加在主图上） */
    _addBOLL(chart, klines) {
        const boll = TechnicalIndicators.calculate(klines, 'BOLL');
        if (!boll) return;

        const upperSeries = chart.addLineSeries({
            color: '#ff9800',
            lineWidth: 1,
            priceLineVisible: false,
            lastValueVisible: false,
        });
        upperSeries.setData(boll.dates.map((d, i) => ({ time: d, value: boll.upper[i] })));

        const middleSeries = chart.addLineSeries({
            color: '#fff',
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            priceLineVisible: false,
            lastValueVisible: false,
        });
        middleSeries.setData(boll.dates.map((d, i) => ({ time: d, value: boll.middle[i] })));

        const lowerSeries = chart.addLineSeries({
            color: '#2196f3',
            lineWidth: 1,
            priceLineVisible: false,
            lastValueVisible: false,
        });
        lowerSeries.setData(boll.dates.map((d, i) => ({ time: d, value: boll.lower[i] })));

        this._indicatorSeries = { upper: upperSeries, middle: middleSeries, lower: lowerSeries };
    },

    /** 副图指标（MACD/KDJ/RSI/WR/OBV） */
    _addSubIndicator(chart, klines, name) {
        const indicator = TechnicalIndicators.calculate(klines, name);
        if (!indicator) return;

        const scaleId = 'indicator';
        chart.priceScale(scaleId).applyOptions({
            scaleMargins: { top: 0.7, bottom: 0 },
        });

        switch (name) {
            case 'MACD':
                this._addMACDSub(chart, indicator, scaleId);
                break;
            case 'KDJ':
                this._addKDJSub(chart, indicator, scaleId);
                break;
            case 'RSI':
                this._addRSISub(chart, indicator, scaleId);
                break;
            case 'WR':
                this._addWRSub(chart, indicator, scaleId);
                break;
            case 'OBV':
                this._addOBVSub(chart, indicator, scaleId);
                break;
        }
    },

    _addMACDSub(chart, data, scaleId) {
        // MACD 柱状图
        const macdSeries = chart.addHistogramSeries({
            priceScaleId: scaleId,
            priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
        });
        macdSeries.setData(data.dates.map((d, i) => ({
            time: d,
            value: data.macd[i],
            color: data.macd[i] >= 0 ? 'rgba(239,83,80,0.8)' : 'rgba(38,166,154,0.8)',
        })));

        // DIF 线
        const difSeries = chart.addLineSeries({
            color: '#ffd54f',
            lineWidth: 1,
            priceScaleId: scaleId,
            priceLineVisible: false,
            lastValueVisible: false,
        });
        difSeries.setData(data.dates.map((d, i) => ({ time: d, value: data.dif[i] })));

        // DEA 线
        const deaSeries = chart.addLineSeries({
            color: '#4fc3f7',
            lineWidth: 1,
            priceScaleId: scaleId,
            priceLineVisible: false,
            lastValueVisible: false,
        });
        deaSeries.setData(data.dates.map((d, i) => ({ time: d, value: data.dea[i] })));

        this._indicatorSeries = { macd: macdSeries, dif: difSeries, dea: deaSeries };
    },

    _addKDJSub(chart, data, scaleId) {
        const colors = { k: '#ffd54f', d: '#4fc3f7', j: '#ff7043' };
        const series = {};
        for (const key of ['k', 'd', 'j']) {
            const s = chart.addLineSeries({
                color: colors[key],
                lineWidth: 1,
                priceScaleId: scaleId,
                priceLineVisible: false,
                lastValueVisible: false,
            });
            s.setData(data.dates.map((d, i) => ({ time: d, value: data[key][i] })));
            series[key] = s;
        }
        this._indicatorSeries = series;
    },

    _addRSISub(chart, data, scaleId) {
        const rsiSeries = chart.addLineSeries({
            color: '#ffd54f',
            lineWidth: 1,
            priceScaleId: scaleId,
            priceLineVisible: false,
            lastValueVisible: false,
        });
        rsiSeries.setData(data.dates.map((d, i) => ({ time: d, value: data.rsi[i] })));

        // 30/70 参考线
        const ref30 = chart.addLineSeries({
            color: 'rgba(255,255,255,0.2)',
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            priceScaleId: scaleId,
            priceLineVisible: false,
            lastValueVisible: false,
        });
        ref30.setData(data.dates.map(d => ({ time: d, value: 30 })));

        const ref70 = chart.addLineSeries({
            color: 'rgba(255,255,255,0.2)',
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            priceScaleId: scaleId,
            priceLineVisible: false,
            lastValueVisible: false,
        });
        ref70.setData(data.dates.map(d => ({ time: d, value: 70 })));

        this._indicatorSeries = { rsi: rsiSeries, ref30, ref70 };
    },

    _addWRSub(chart, data, scaleId) {
        const wrSeries = chart.addLineSeries({
            color: '#ff7043',
            lineWidth: 1,
            priceScaleId: scaleId,
            priceLineVisible: false,
            lastValueVisible: false,
        });
        wrSeries.setData(data.dates.map((d, i) => ({ time: d, value: data.wr[i] })));
        this._indicatorSeries = { wr: wrSeries };
    },

    _addOBVSub(chart, data, scaleId) {
        const obvSeries = chart.addLineSeries({
            color: '#66bb6a',
            lineWidth: 1,
            priceScaleId: scaleId,
            priceFormat: { type: 'volume' },
            priceLineVisible: false,
            lastValueVisible: false,
        });
        obvSeries.setData(data.dates.map((d, i) => ({ time: d, value: data.obv[i] })));
        this._indicatorSeries = { obv: obvSeries };
    },

    /** 绑定指标选择器事件 */
    _bindIndicatorSelector() {
        const select = document.getElementById('sd-indicator-select');
        if (!select) return;
        select.addEventListener('change', () => {
            this._currentIndicator = select.value;
            if (this._currentKlines && this._currentPeriod !== 'timeline') {
                this._renderKlineChart(this._currentKlines);
            }
        });
    },

    async _loadTimeline(code) {
        try {
            const data = await App.fetchJSON(`/api/stock/timeline/${code}`);
            this._renderTimelineChart(data.trends, data.pre_close);
        } catch (e) {
            console.error('加载分时失败:', e);
        }
    },

    _renderTimelineChart(trends, preClose) {
        const container = document.getElementById('sd-kline-chart');
        if (!container) return;

        // 清除现有图表
        if (this._klineChart) {
            this._klineChart.remove();
            this._klineChart = null;
        }
        if (this._klineResizeObs) {
            this._klineResizeObs.disconnect();
            this._klineResizeObs = null;
        }

        container.innerHTML = '';

        if (!trends || trends.length === 0) {
            container.innerHTML = '<p class="text-muted" style="text-align:center;padding:2rem">非交易时段</p>';
            return;
        }

        // 使用 LightweightCharts 渲染分时图
        const chart = LightweightCharts.createChart(container, {
            width: container.clientWidth,
            height: 400,
            layout: {
                background: { type: 'solid', color: '#1a1a2e' },
                textColor: '#e0e0e0',
            },
            grid: {
                vertLines: { color: '#2a2a3e' },
                horzLines: { color: '#2a2a3e' },
            },
            crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
            rightPriceScale: { borderColor: '#3a3a4e' },
            timeScale: { borderColor: '#3a3a4e', timeVisible: true },
            watermark: { visible: false },
        });
        // 移除 TradingView logo
        this._removeTVLogo(container);

        // 转换时间格式
        const parseTime = (timeStr) => {
            const parts = timeStr.split(' ');
            if (parts.length > 1) {
                const [date, time] = parts;
                const [year, month, day] = date.split('-');
                const [hour, minute] = time.split(':');
                return new Date(year, month - 1, day, hour, minute).getTime() / 1000;
            }
            return new Date(timeStr).getTime() / 1000;
        };

        // 分时价格线
        const areaSeries = chart.addAreaSeries({
            topColor: 'rgba(79, 195, 247, 0.4)',
            bottomColor: 'rgba(79, 195, 247, 0.05)',
            lineColor: '#4fc3f7',
            lineWidth: 2,
        });

        const timelineData = trends.map(t => ({
            time: parseTime(t.time),
            value: t.close,
        }));
        areaSeries.setData(timelineData);

        // 均价线
        const avgSeries = chart.addLineSeries({
            color: '#ffd54f',
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            priceLineVisible: false,
            lastValueVisible: false,
        });

        const avgData = trends.map(t => ({
            time: parseTime(t.time),
            value: t.avg_price,
        }));
        avgSeries.setData(avgData);

        // 昨收参考线
        if (preClose) {
            const preCloseSeries = chart.addLineSeries({
                color: 'rgba(255,255,255,0.3)',
                lineWidth: 1,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                priceLineVisible: false,
                lastValueVisible: false,
            });

            const preCloseData = trends.map(t => ({
                time: parseTime(t.time),
                value: preClose,
            }));
            preCloseSeries.setData(preCloseData);
        }

        // 成交量
        const volumeSeries = chart.addHistogramSeries({
            priceFormat: { type: 'volume' },
            priceScaleId: 'volume',
        });

        chart.priceScale('volume').applyOptions({
            scaleMargins: { top: 0.8, bottom: 0 },
        });

        const volumeData = trends.map(t => ({
            time: parseTime(t.time),
            value: t.volume,
            color: t.close >= preClose ? 'rgba(239,83,80,0.5)' : 'rgba(38,166,154,0.5)',
        }));
        volumeSeries.setData(volumeData);

        chart.timeScale().fitContent();

        // 响应式
        this._klineResizeObs = new ResizeObserver(() => {
            chart.applyOptions({ width: container.clientWidth });
        });
        this._klineResizeObs.observe(container);
    },

    async _loadCapitalFlow(code) {
        try {
            const data = await App.fetchJSON(`/api/stock/capital-flow/${code}?days=20`);
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

    async _loadOrderBook(code) {
        try {
            const data = await App.fetchJSON(`/api/stock/order-book/${code}`);
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

    _bindChartTabs() {
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

            if (period === 'timeline') {
                this._loadTimeline(this._currentCode);
            } else {
                this._loadKline(this._currentCode, period);
            }
        });
    },
};
