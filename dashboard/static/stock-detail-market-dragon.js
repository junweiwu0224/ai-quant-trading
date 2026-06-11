/* ── 股票详情页：龙虎榜分析 ── */

if (!globalThis.StockDetail) {
    globalThis.StockDetail = {};
}

Object.assign(globalThis.StockDetail, {
    async _loadDragonTiger(code, stale) {
        try {
            const data = await App.fetchJSON(`/api/stock/dragon-tiger/${code}?days=90`);
            if (stale && stale()) return;
            if (!data) {
                this._setWorkbenchEvents?.('dragon_tiger', [], {
                    type: 'dragon_tiger',
                    title: '龙虎榜暂缺',
                    source: 'stock_dragon_tiger',
                    source_label: '龙虎榜',
                    status: 'missing',
                    missing_reason: '龙虎榜接口未返回数据',
                });
                return;
            }
            this._setDragonTigerWorkbenchEvents(data);
            this._renderDragonTiger(data);
        } catch (e) {
            console.error('加载龙虎榜分析失败:', e);
            if (stale && stale()) return;
            this._setWorkbenchEvents?.('dragon_tiger', [], {
                type: 'dragon_tiger',
                title: '龙虎榜加载失败',
                source: 'stock_dragon_tiger',
                source_label: '龙虎榜',
                status: 'missing',
                missing_reason: '龙虎榜数据加载失败',
            });
        }
    },

    _setDragonTigerWorkbenchEvents(data = {}) {
        const records = Array.isArray(data.records) ? data.records : [];
        if (!data.success || !records.length) {
            this._setWorkbenchEvents?.('dragon_tiger', [], {
                type: 'dragon_tiger',
                title: '龙虎榜暂缺',
                source: 'stock_dragon_tiger',
                source_label: '龙虎榜',
                status: 'missing',
                missing_reason: '近90日暂无龙虎榜上榜记录',
            });
            return;
        }
        this._setWorkbenchEvents?.('dragon_tiger', records.slice(0, 12).map((record) => {
            const net = Number(record.net_amount);
            const changeRate = Number(record.change_rate);
            const reasons = Array.isArray(record.reasons) ? record.reasons.filter(Boolean) : [];
            return {
                type: 'dragon_tiger',
                status: 'ready',
                title: net > 0 ? '龙虎榜净买入' : net < 0 ? '龙虎榜净卖出' : '龙虎榜上榜',
                detail: [
                    Number.isFinite(net) ? `净额 ${net >= 0 ? '+' : ''}${(net / 10000).toFixed(2)}亿` : '',
                    Number.isFinite(changeRate) ? `当日涨跌 ${changeRate >= 0 ? '+' : ''}${changeRate.toFixed(2)}%` : '',
                    reasons.join('、'),
                ].filter(Boolean).join(' · '),
                at: record.date || '',
                date_key: this._stockDataDateKey?.(record.date) || record.date || '',
                source: 'stock_dragon_tiger',
                source_label: '龙虎榜',
                direction: net > 0 ? 'increase' : net < 0 ? 'decrease' : 'flat',
                value: Number.isFinite(net) ? net : null,
                raw: record,
            };
        }), {
            type: 'dragon_tiger',
            source: 'stock_dragon_tiger',
            source_label: '龙虎榜',
        });
    },

    _renderDragonTiger(data) {
        const container = document.getElementById('sd-dragon-tiger');
        if (!container) return;

        const hint = document.getElementById('sd-dt-hint');
        if (hint && data.summary) {
            hint.textContent = `近${data.summary.period_days}日上榜${data.summary.total_listings}次`;
        }

        if (!data.success || (!data.records?.length && !data.traders?.length)) {
            container.innerHTML = '<div class="text-muted text-center" style="padding:20px">暂无龙虎榜数据</div>';
            return;
        }

        const { summary, records, traders, return_stats } = data;
        const netCls = summary.total_net_amount >= 0 ? 'text-up' : 'text-down';
        const retCls = summary.avg_return_5d >= 0 ? 'text-up' : 'text-down';
        const summaryHtml = `
            <div class="dt-summary-row">
                <div class="dt-summary-item">
                    <span class="dt-summary-label">上榜次数</span>
                    <span class="dt-summary-value">${summary.total_listings}</span>
                </div>
                <div class="dt-summary-item">
                    <span class="dt-summary-label">净买入合计</span>
                    <span class="dt-summary-value ${netCls}">${summary.total_net_amount >= 0 ? '+' : ''}${(summary.total_net_amount / 10000).toFixed(2)}亿</span>
                </div>
                <div class="dt-summary-item">
                    <span class="dt-summary-label">上榜后5日均收益</span>
                    <span class="dt-summary-value ${retCls}">${summary.avg_return_5d >= 0 ? '+' : ''}${summary.avg_return_5d}%</span>
                </div>
            </div>
        `;

        let returnsHtml = '';
        if (return_stats && return_stats.length > 0) {
            returnsHtml = `
                <h4 class="dt-section-title">上榜后收益统计</h4>
                <div class="table-wrap">
                    <table>
                        <thead><tr><th>上榜日</th><th>入场价</th><th>1日</th><th>3日</th><th>5日</th><th>10日</th></tr></thead>
                        <tbody>${return_stats.map(r => {
                            const fmt = (v) => v != null ? (v >= 0 ? `<span class="text-up">+${v}%</span>` : `<span class="text-down">${v}%</span>`) : '--';
                            return `<tr>
                                <td>${r.date}</td>
                                <td>${r.entry_price?.toFixed(2) || '--'}</td>
                                <td>${fmt(r['1d'])}</td>
                                <td>${fmt(r['3d'])}</td>
                                <td>${fmt(r['5d'])}</td>
                                <td>${fmt(r['10d'])}</td>
                            </tr>`;
                        }).join('')}</tbody>
                    </table>
                </div>
            `;
        }

        let tradersHtml = '';
        if (traders && traders.length > 0) {
            tradersHtml = `
                <h4 class="dt-section-title">活跃营业部 TOP 15</h4>
                <div class="table-wrap">
                    <table>
                        <thead><tr><th>营业部</th><th>买入</th><th>卖出</th><th>净买入</th><th>上榜</th><th>3日上涨率</th></tr></thead>
                        <tbody>${traders.map(t => {
                            const netCls = t.total_net >= 0 ? 'text-up' : 'text-down';
                            const probCls = t.avg_rise_prob >= 50 ? 'text-up' : t.avg_rise_prob > 0 ? 'text-down' : '';
                            return `<tr>
                                <td class="dt-trader-name" title="${App.escapeHTML(t.name)}">${App.escapeHTML(t.name)}</td>
                                <td>${(t.total_buy / 10000).toFixed(2)}亿</td>
                                <td>${(t.total_sell / 10000).toFixed(2)}亿</td>
                                <td class="${netCls}">${t.total_net >= 0 ? '+' : ''}${(t.total_net / 10000).toFixed(2)}亿</td>
                                <td>${t.count}次/${t.listing_days}日</td>
                                <td class="${probCls}">${t.avg_rise_prob > 0 ? t.avg_rise_prob + '%' : '--'}</td>
                            </tr>`;
                        }).join('')}</tbody>
                    </table>
                </div>
            `;
        }

        let recordsHtml = '';
        if (records && records.length > 0) {
            recordsHtml = `
                <h4 class="dt-section-title">最近上榜记录</h4>
                <div class="table-wrap">
                    <table>
                        <thead><tr><th>日期</th><th>涨跌幅</th><th>买入</th><th>卖出</th><th>净买入</th><th>上榜原因</th></tr></thead>
                        <tbody>${records.slice(0, 10).map(r => {
                            const netCls = r.net_amount >= 0 ? 'text-up' : 'text-down';
                            const chgCls = r.change_rate >= 0 ? 'text-up' : 'text-down';
                            return `<tr>
                                <td>${r.date}</td>
                                <td class="${chgCls}">${r.change_rate >= 0 ? '+' : ''}${r.change_rate.toFixed(2)}%</td>
                                <td>${(r.buy_amount / 10000).toFixed(2)}亿</td>
                                <td>${(r.sell_amount / 10000).toFixed(2)}亿</td>
                                <td class="${netCls}">${r.net_amount >= 0 ? '+' : ''}${(r.net_amount / 10000).toFixed(2)}亿</td>
                                <td>${r.reasons.map(App.escapeHTML).join('、') || '--'}</td>
                            </tr>`;
                        }).join('')}</tbody>
                    </table>
                </div>
            `;
        }

        container.innerHTML = summaryHtml + returnsHtml + tradersHtml + recordsHtml;
    },
});
