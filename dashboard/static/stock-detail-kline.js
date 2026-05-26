/* ── 股票详情页：K线与指标 ── */

if (!globalThis.StockDetail) {
    globalThis.StockDetail = {};
}

Object.assign(globalThis.StockDetail, {
    async _loadKline(code, period) {
        this._currentPeriod = period;
        try {
            const data = await App.fetchJSON(`/api/stock/kline/${code}?period=${period}&count=200`);
            if (!data || !data.klines) return;
            this._renderKlineChart(data.klines);
            this._loadDrawings();
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
                    showRule: 'none',
                    showType: 'standard',
                    text: { size: 12, color: textSecondary, marginLeft: 8, marginTop: 6, marginRight: 8, marginBottom: 0 },
                    rect: {
                        position: 'fixed',
                        paddingLeft: 10, paddingRight: 10, paddingTop: 8, paddingBottom: 8,
                        offsetLeft: 10, offsetTop: 8, offsetRight: 10, offsetBottom: 8,
                        borderRadius: 4, borderSize: 1, borderColor: borderColor,
                        color: bgSecondary,
                    },
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
                    showRule: 'none',
                    showType: 'standard',
                    showName: false, showParams: false,
                    text: { size: 12, color: textSecondary, marginLeft: 8, marginTop: 2, marginRight: 8, marginBottom: 0 },
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

    /** 使用 KLineChart 渲染 K 线图（同花顺风格） */
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
        this._avgOverlays = null;
        this._multiDayOverlays = [];

        // 清除容器残留内容
        container.innerHTML = '';

        if (!klines || klines.length === 0) {
            container.innerHTML = '<p class="text-muted" style="text-align:center;padding:2rem">暂无K线数据</p>';
            return;
        }

        this._currentKlines = klines;

        // ── 自定义 tooltip overlay（同花顺风格固定左上角） ──
        const tooltipEl = document.createElement('div');
        tooltipEl.className = 'sd-kline-tooltip';
        tooltipEl.innerHTML = [
            '<div class="kl-row"><span class="kl-date"></span></div>',
            '<div class="kl-row"><label>开</label><span class="kl-open"></span></div>',
            '<div class="kl-row"><label>高</label><span class="kl-high"></span></div>',
            '<div class="kl-row"><label>低</label><span class="kl-low"></span></div>',
            '<div class="kl-row"><label>收</label><span class="kl-close"></span></div>',
            '<div class="kl-row"><label>量</label><span class="kl-vol"></span></div>',
            '<div class="kl-row"><label>涨跌额</label><span class="kl-change"></span></div>',
            '<div class="kl-row"><label>涨跌幅</label><span class="kl-pct"></span></div>',
            '<div class="kl-ma-row"></div>',
        ].join('');
        container.appendChild(tooltipEl);

        // 缓存 tooltip span 引用
        const spans = {
            date: tooltipEl.querySelector('.kl-date'),
            open: tooltipEl.querySelector('.kl-open'),
            high: tooltipEl.querySelector('.kl-high'),
            low: tooltipEl.querySelector('.kl-low'),
            close: tooltipEl.querySelector('.kl-close'),
            vol: tooltipEl.querySelector('.kl-vol'),
            change: tooltipEl.querySelector('.kl-change'),
            pct: tooltipEl.querySelector('.kl-pct'),
            maRow: tooltipEl.querySelector('.kl-ma-row'),
        };

        // MA 颜色映射
        const maColors = ['#e6a817', '#2196f3', '#ff7043', '#66bb6a'];
        const maPeriods = [5, 10, 20, 60];

        // 格式化成交量
        const fmtVol = (v) => {
            if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿';
            if (v >= 1e4) return (v / 1e4).toFixed(0) + '万';
            return String(v);
        };

        // 格式化日期
        const fmtDate = (ts) => {
            const d = new Date(ts);
            const y = d.getFullYear();
            const m = String(d.getMonth() + 1).padStart(2, '0');
            const dd = String(d.getDate()).padStart(2, '0');
            return `${y}-${m}-${dd}`;
        };

        // 设置 span 值并带颜色
        const setSpan = (el, val, colorClass) => {
            el.textContent = val;
            el.className = el.className.replace(/\s*kl-(up|down|flat)\s*/g, '').trim() + ' ' + colorClass;
        };

        // 计算 MA 值
        const calcMA = (dataList, idx, period) => {
            if (idx < period - 1) return null;
            let sum = 0;
            for (let i = idx - period + 1; i <= idx; i++) {
                sum += dataList[i].close;
            }
            return sum / period;
        };

        // 更新 tooltip 内容
        const updateTooltip = (kLineData, dataList, idx) => {
            if (!kLineData) return;
            const k = kLineData;
            const prevClose = idx > 0 ? dataList[idx - 1].close : k.open;
            const change = k.close - prevClose;
            const pct = prevClose ? (change / prevClose) * 100 : 0;
            const colorClass = change > 0.001 ? 'kl-up' : change < -0.001 ? 'kl-down' : 'kl-flat';

            spans.date.textContent = fmtDate(k.timestamp);
            setSpan(spans.open, k.open.toFixed(2), colorClass);
            setSpan(spans.high, k.high.toFixed(2), colorClass);
            setSpan(spans.low, k.low.toFixed(2), colorClass);
            setSpan(spans.close, k.close.toFixed(2), colorClass);
            spans.vol.textContent = fmtVol(k.volume);

            const sign = change >= 0 ? '+' : '';
            setSpan(spans.change, `${sign}${change.toFixed(2)}`, colorClass);
            setSpan(spans.pct, `${sign}${pct.toFixed(2)}%`, colorClass);

            // 更新 MA 值
            let maHtml = '';
            for (let i = 0; i < maPeriods.length; i++) {
                const maVal = calcMA(dataList, idx, maPeriods[i]);
                if (maVal != null) {
                    maHtml += `<span style="color:${maColors[i]}">MA${maPeriods[i]}: ${maVal.toFixed(2)}</span> `;
                }
            }
            spans.maRow.innerHTML = maHtml;
        };

        // 初始化 KLineChart（中文 + 跟随页面主题）
        const chart = klinecharts.init(container, { locale: 'zh-CN', styles: this._klineStyles() });
        this._klineChart = chart;

        // 加载 K 线数据（timestamp 转毫秒）
        const chartData = klines.map(k => ({
            timestamp: new Date(k.date + 'T00:00:00+08:00').getTime(),
            open: k.open,
            high: k.high,
            low: k.low,
            close: k.close,
            volume: k.volume,
        }));
        chart.applyNewData(chartData);

        // 默认显示最后一根 K 线
        if (chartData.length > 0) {
            updateTooltip(chartData[chartData.length - 1], chartData, chartData.length - 1);
        }

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

        // 十字线事件 → 更新 tooltip
        const dataListCache = chart.getDataList();
        chart.subscribeAction('onCrosshairChange', (crosshair) => {
            if (!crosshair || !crosshair.kLineData) {
                // 十字线离开，显示最后一根 K 线
                if (dataListCache.length > 0) {
                    updateTooltip(dataListCache[dataListCache.length - 1], dataListCache, dataListCache.length - 1);
                }
                return;
            }
            updateTooltip(crosshair.kLineData, dataListCache, crosshair.dataIndex);
        });

        // 自适应宽度
        this._klineResizeObs = new ResizeObserver(() => chart.resize());
        this._klineResizeObs.observe(container);
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

});
