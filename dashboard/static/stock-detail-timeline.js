/* ── 股票详情页：分时 / 资金流 ── */

if (!globalThis.StockDetail) {
    globalThis.StockDetail = {};
}

Object.assign(globalThis.StockDetail, {
    async _loadTimeline(code, stale) {
        this._currentPeriod = 'timeline';
        this._syncWorkbenchChartState?.({ period: 'timeline' });
        const indicatorEl = document.querySelector('.sd-indicator-selector');
        if (indicatorEl) indicatorEl.style.display = 'none';
        const infoPanel = document.getElementById('sd-timeline-info');
        if (infoPanel) infoPanel.classList.remove('hidden');
        try {
            const data = await App.fetchJSON(`/api/stock/timeline/${code}`);
            if (!data || (stale && stale())) return;
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
                    const cur = data && (data.current || data);
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

        // Y轴固定涨跌幅刻度（左侧显示：0.00%, ±0.50%, ±1.00%, ±2.00%, ±3.00%, ±5.00%）
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
                const levels = [0, 0.5, -0.5, 1, -1, 2, -2, 3, -3, 5, -5];
                ctx.save();
                ctx.font = '10px sans-serif';
                ctx.textAlign = 'right';
                for (const pct of levels) {
                    const price = pc * (1 + pct / 100);
                    const y = yAxis.convertToPixel(price);
                    if (y < 0 || y > bounding.height) continue;
                    const pctText = (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%';
                    ctx.fillStyle = pct > 0 ? '#c65746' : pct < 0 ? '#10b981' : '#6d6760';
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
        this._multiDayOverlays = [];
        const multiBtn = document.getElementById('sd-multiday-btn');
        if (multiBtn) multiBtn.classList.remove('active');
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

        const toFiniteNumber = (value) => {
            const num = Number(value);
            return Number.isFinite(num) ? num : null;
        };

        const dateKeyFromTime = (timeStr) => (
            typeof timeStr === 'string' && timeStr.length >= 10 ? timeStr.slice(0, 10) : ''
        );

        const buildSelectedTimelineCandle = (trend, kLineData, idx) => {
            const safeIndex = Number.isInteger(idx) && idx >= 0
                ? idx
                : trends.findIndex(item => item === trend || item.time === trend?.time);
            const price = toFiniteNumber(trend?.close ?? kLineData?.close);
            const avg = toFiniteNumber(trend?.avg_price ?? kLineData?.avg_price ?? kLineData?.avg);
            const prev = toFiniteNumber(preClose);
            const change = price != null && prev != null ? price - prev : null;
            const changePct = change != null && prev ? (change / prev) * 100 : null;
            const timestamp = kLineData?.timestamp ?? (trend?.time ? parseTime(trend.time) : null);

            return {
                period: 'timeline',
                timestamp,
                time: trend?.time || kLineData?.time || '',
                dataIndex: safeIndex >= 0 ? safeIndex : null,
                date_key: dateKeyFromTime(trend?.time || kLineData?.time),
                price,
                close: price,
                avg,
                avg_price: avg,
                change,
                change_pct: changePct,
                volume: toFiniteNumber(trend?.volume ?? kLineData?.volume),
            };
        };

        const syncSelectedTimelineCandle = (trend, kLineData, idx) => {
            const selectedCandle = buildSelectedTimelineCandle(trend, kLineData, idx);
            if (selectedCandle) this._syncWorkbenchChartState?.({ selectedCandle });
        };

        // 加载分时数据
        const chartData = trends.map(t => {
            const price = toFiniteNumber(t.close);
            const prev = toFiniteNumber(preClose);
            const change = price != null && prev != null ? price - prev : null;
            return {
                timestamp: parseTime(t.time),
                time: t.time,
                date_key: dateKeyFromTime(t.time),
                open: t.close,
                high: t.close,
                low: t.close,
                close: t.close,
                price: t.close,
                avg: t.avg_price,
                avg_price: t.avg_price,
                change,
                change_pct: change != null && prev ? (change / prev) * 100 : null,
                volume: t.volume,
            };
        });
        this._currentChartData = chartData;
        chart.applyNewData(chartData);
        this._renderStockChartEventLayer?.(chartData);

        // 设置默认缩放：确保显示完整交易时段（9:30-15:00 = 242根1分钟线）
        const fullDayBars = 242;
        const dataLen = trends.length;
        if (dataLen > 0) {
            // 通过 barSpace 控制可见范围，确保始终显示完整交易时段
            const widthPx = container.clientWidth || 600;
            const barSpace = Math.max(1, Math.min(30, Math.floor(widthPx / fullDayBars)));
            chart.setBarSpace(barSpace);
        }

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
        const dataListCache = chart.getDataList();
        this._updateTimelineInfo(lastTrend, preClose, trends);
        syncSelectedTimelineCandle(lastTrend, dataListCache[dataListCache.length - 1], trends.length - 1);

        // Y轴左侧涨跌幅浮层标签（十字线跟随）
        let tlLeftEl = container.querySelector('.sd-crosshair-label-left');
        if (!tlLeftEl) {
            tlLeftEl = document.createElement('div');
            tlLeftEl.className = 'sd-crosshair-label sd-crosshair-label-left';
            container.appendChild(tlLeftEl);
        }

        chart.subscribeAction('onCrosshairChange', (crosshair) => {
            if (!crosshair || !crosshair.kLineData) {
                this._updateTimelineInfo(lastTrend, preClose, trends);
                syncSelectedTimelineCandle(lastTrend, dataListCache[dataListCache.length - 1], trends.length - 1);
                tlLeftEl.style.display = 'none';
                return;
            }
            const idx = crosshair.dataIndex;
            const t = trends[idx];
            if (t) this._updateTimelineInfo(t, preClose, trends);
            syncSelectedTimelineCandle(t, crosshair.kLineData, idx);

            // 左侧跟随十字线显示涨跌幅
            const price = crosshair.kLineData.close;
            if (preClose && preClose > 0 && price && crosshair.y != null) {
                const pct = (price - preClose) / preClose * 100;
                const color = pct > 0.01 ? '#c65746' : pct < -0.01 ? '#10b981' : '#6d6760';
                const sign = pct >= 0 ? '+' : '';
                tlLeftEl.textContent = `${sign}${pct.toFixed(2)}%`;
                tlLeftEl.style.display = 'block';
                tlLeftEl.style.color = color;
                tlLeftEl.style.borderColor = color;
                tlLeftEl.style.top = `${crosshair.y}px`;
            } else {
                tlLeftEl.style.display = 'none';
            }
        });

        // Y轴自动缩放（放大后线始终可见）
        if (typeof chart.setAutoScale === 'function') {
            chart.setAutoScale(true);
        }

        if (chart.timeScale && typeof chart.timeScale === 'function') {
            const timeScale = chart.timeScale();
            if (timeScale && typeof timeScale.fitContent === 'function') {
                timeScale.fitContent();
            }
        }

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

        // 量比 = 当前累计成交量 / 5日平均成交量
        const detail = this._detailData;
        if (vol != null && detail && detail.avg_volume_5d > 0) {
            const vr = vol / detail.avg_volume_5d;
            const vrClass = vr >= 1.5 ? 'text-up' : vr <= 0.5 ? 'text-down' : '';
            set('sd-ti-vr', vr.toFixed(2), vrClass);
        } else if (detail && detail.volume_ratio != null) {
            set('sd-ti-vr', detail.volume_ratio.toFixed(2));
        }
    },

});
