/* ── 股票详情页：多周期共振分析 ── */

if (!globalThis.StockDetail) {
    globalThis.StockDetail = {};
}

Object.assign(globalThis.StockDetail, {
    async _loadMultiTimeframe(code, stale) {
        try {
            const data = await App.fetchJSON(`/api/stock/multi-timeframe/${code}`);
            if (!data || stale()) return;
            this._renderMultiTimeframe(data);
        } catch (e) {
            console.error('加载多周期分析失败:', e);
        }
    },

    _renderMultiTimeframe(data) {
        const container = document.getElementById('sd-multitimeframe');
        if (!container || !data.success) return;

        const fallbackFrame = { trend: 'neutral', strength: 0, signals: [] };
        const daily = data.daily && typeof data.daily === 'object' ? data.daily : fallbackFrame;
        const weekly = data.weekly && typeof data.weekly === 'object' ? data.weekly : fallbackFrame;
        const monthly = data.monthly && typeof data.monthly === 'object' ? data.monthly : fallbackFrame;
        const resonance = data.resonance || 'neutral';
        const resonance_label = data.resonance_label || '多周期数据暂缺';
        const strength = Number.isFinite(Number(data.strength)) ? Number(data.strength) : 0;

        function trendIcon(trend) {
            if (trend === 'bullish') return '<span class="text-up">&#9650;</span>';
            if (trend === 'bearish') return '<span class="text-down">&#9660;</span>';
            return '<span class="text-muted">&#9654;</span>';
        }

        function trendLabel(trend) {
            if (trend === 'bullish') return '<span class="text-up">看多</span>';
            if (trend === 'bearish') return '<span class="text-down">看空</span>';
            return '<span class="text-muted">中性</span>';
        }

        function strengthBar(s) {
            const color = s >= 60 ? 'var(--up-color)' : s <= 40 ? 'var(--down-color)' : 'var(--text-muted)';
            return `<div class="mtf-strength-bar"><div class="mtf-strength-fill" style="width:${s}%;background:${color}"></div></div>`;
        }

        function signalList(signals) {
            if (!signals || signals.length === 0) return '<span class="text-muted">无信号</span>';
            return signals.map(s => {
                const cls = s.direction === 'bullish' ? 'text-up' : s.direction === 'bearish' ? 'text-down' : 'text-muted';
                return `<span class="mtf-signal ${cls}">${App.escapeHTML(s.name)}</span>`;
            }).join(' ');
        }

        let resonanceClass = 'text-muted';
        if (resonance === 'strong_bullish' || resonance === 'bullish') resonanceClass = 'text-up';
        else if (resonance === 'strong_bearish' || resonance === 'bearish') resonanceClass = 'text-down';

        container.innerHTML = `
            <div class="mtf-resonance-header ${resonanceClass}">
                <div class="mtf-resonance-label">${App.escapeHTML(resonance_label)}</div>
                <div class="mtf-resonance-strength">综合强度 ${strength}/100</div>
                ${strengthBar(strength)}
            </div>
            <div class="mtf-grid">
                ${['日线', '周线', '月线'].map((label, i) => {
                    const tf = [daily, weekly, monthly][i];
                    return `<div class="mtf-card">
                        <div class="mtf-card-header">
                            <span class="mtf-card-title">${label}</span>
                            ${trendIcon(tf.trend)} ${trendLabel(tf.trend)}
                            <span class="mtf-card-score">${tf.strength}/100</span>
                        </div>
                        ${strengthBar(tf.strength)}
                        <div class="mtf-signals">${signalList(tf.signals)}</div>
                    </div>`;
                }).join('')}
            </div>
        `;
    },
});
