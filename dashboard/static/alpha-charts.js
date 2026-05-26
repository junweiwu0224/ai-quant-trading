/* ── AI Alpha：基础图表与绩效渲染 ── */

Object.assign(App, {
    // ── 基础图表 ──

    renderFeatureImportance(data) {
        if (!data || data.length === 0) { ChartFactory.showEmpty('alpha-feature-chart'); return; }
        ChartFactory.horizontalBar('alpha-feature-chart', {
            labels: data.map(d => d.feature),
            values: data.map(d => d.importance),
        }, 'feature');
    },

    renderTrainingCurve(data) {
        if (!data || !data.epochs || data.epochs.length === 0) { ChartFactory.showEmpty('alpha-training-chart'); return; }
        const c = ChartFactory.getColors();
        ChartFactory.line('alpha-training-chart', {
            labels: data.epochs,
            datasets: [
                { label: 'Train AUC', data: data.train_auc, yAxisID: 'y-auc' },
                { label: 'Val AUC', data: data.val_auc, color: c.success, yAxisID: 'y-auc', borderDash: [5, 3] },
                { label: 'Train Loss', data: data.train_loss, color: c.warning, yAxisID: 'y-loss' },
                { label: 'Val Loss', data: data.val_loss, color: c.danger, yAxisID: 'y-loss', borderDash: [5, 3] },
            ],
        }, 'training', {
            plugins: { legend: { labels: { color: c.text } } },
            scales: {
                'y-auc': { type: 'linear', position: 'left', title: { display: true, text: 'AUC', color: c.textMuted }, ticks: { color: c.textMuted } },
                'y-loss': { type: 'linear', position: 'right', title: { display: true, text: 'Loss', color: c.textMuted }, ticks: { color: c.textMuted }, grid: { drawOnChartArea: false } },
            },
        });
    },

    renderPredictVsActual(data) {
        if (!data || !data.predictions || data.predictions.length === 0) { ChartFactory.showEmpty('alpha-predict-chart'); return; }
        const c = ChartFactory.getColors();
        const preds = data.predictions;
        ChartFactory.line('alpha-predict-chart', {
            labels: preds.map(p => p.date),
            datasets: [
                { label: '预测概率', data: preds.map(p => p.probability) },
                { label: '阈值线', data: preds.map(() => 0.5), color: c.danger, borderDash: [5, 5], borderWidth: 1 },
            ],
        }, 'predict', {
            plugins: { legend: { labels: { color: c.text } } },
            scales: { y: { min: 0, max: 1 } },
        });
    },

    renderSignalChart(klineData) {
        const kline = klineData.kline || [];
        const signals = klineData.signals || [];
        if (kline.length === 0) { ChartFactory.showEmpty('alpha-signal-chart'); return; }

        const c = ChartFactory.getColors();
        const closeData = kline.map(k => k.close);
        const dates = kline.map(k => k.date);
        const buyDates = new Set(signals.filter(s => s.type === 'buy').map(s => s.date));
        const sellDates = new Set(signals.filter(s => s.type === 'sell').map(s => s.date));

        const buyPoints = dates.map((d, i) => buyDates.has(d) ? closeData[i] : null);
        const sellPoints = dates.map((d, i) => sellDates.has(d) ? closeData[i] : null);

        ChartFactory.line('alpha-signal-chart', {
            labels: dates,
            datasets: [
                { label: '收盘价', data: closeData, color: c.muted },
                { label: '买入信号', data: buyPoints, color: c.success, pointRadius: 8, pointStyle: 'triangle' },
                { label: '卖出信号', data: sellPoints, color: c.danger, pointRadius: 8, pointStyle: 'triangle', pointRotation: 180 },
            ],
        }, 'signal', {
            plugins: { legend: { labels: { color: c.text } } },
        });
    },

    // ── 策略绩效 ──

    renderPerformance(data) {
        if (!data || !data.metrics) return;
        const m = data.metrics;
        const s = data.summary || {};
        const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val || '--'; };

        setVal('alpha-total-return', m['总收益率']);
        setVal('alpha-annual-return', m['年化收益率']);
        setVal('alpha-max-dd', m['最大回撤']);
        setVal('alpha-sharpe', m['夏普比率']);
        setVal('alpha-sortino', m['索提诺比率']);
        setVal('alpha-calmar', m['卡尔玛比率']);
        setVal('alpha-win-rate', s.win_rate ? (s.win_rate * 100).toFixed(1) + '%' : '--');
        setVal('alpha-profit-ratio', s.profit_ratio || '--');
        setVal('alpha-buy-count', s.buy_count || '--');
        setVal('alpha-sell-count', s.sell_count || '--');
        setVal('alpha-avg-win', s.avg_win ? '¥' + s.avg_win : '--');
        setVal('alpha-avg-loss', s.avg_loss ? '¥' + s.avg_loss : '--');

        // 权益曲线图
        const eq = data.equity_curve || [];
        if (eq.length > 0) {
            const c = ChartFactory.getColors();
            ChartFactory.line('alpha-equity-chart', {
                labels: eq.map(e => e.date),
                datasets: [{ label: '权益', data: eq.map(e => e.equity) }],
            }, 'equity', {
                plugins: { legend: { labels: { color: c.text } } },
            });
        }

        // 交易记录表
        const trades = data.trades || [];
        const tbody = document.querySelector('#alpha-trades-table tbody');
        if (tbody) {
            if (trades.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" class="text-muted">暂无交易</td></tr>';
            } else {
                const esc = App.escapeHTML;
                tbody.innerHTML = trades.map(t => `
                    <tr>
                        <td>${esc(t.date)}</td>
                        <td class="${t.type === 'buy' ? 'text-up' : 'text-down'}">${t.type === 'buy' ? '买入' : '卖出'}</td>
                        <td>${esc(t.price)}</td>
                        <td>${esc(t.shares)}</td>
                        <td class="${(t.pnl || 0) > 0 ? 'text-up' : (t.pnl || 0) < 0 ? 'text-down' : ''}">${t.pnl != null ? '¥' + esc(t.pnl) : '--'}</td>
                    </tr>
                `).join('');
            }
        }
    },
});
