/* ── 风控模块：指标卡片 + VaR 面板 ── */

Object.assign(App, {
    _rkRenderStats() {
        const s = this._rk.snapshot;
        if (!s) return;

        const risk = s.risk || s.risk_indicators || {};
        const positions = s.positions || [];
        const totalEquity = s.total_equity || 0;
        const dailyPnl = s.daily_pnl || 0;
        const dailyPnlPct = totalEquity > 0 ? (dailyPnl / totalEquity * 100) : 0;

        this._rkSetCard('rk-equity', this.fmt(totalEquity));
        this._rkSetCard('rk-daily-pnl', `${dailyPnl >= 0 ? '+' : ''}${this.fmt(dailyPnl)} (${dailyPnlPct >= 0 ? '+' : ''}${dailyPnlPct.toFixed(2)}%)`, dailyPnl >= 0 ? 'text-up' : 'text-down');
        this._rkSetCard('rk-max-dd', ((risk.max_drawdown ?? 0) * 100).toFixed(2) + '%', 'text-down');
        this._rkSetCard('rk-var95', ((risk.var_95 ?? 0) * 100).toFixed(2) + '%');
        this._rkSetCard('rk-sharpe', (risk.sharpe_ratio ?? 0).toFixed(2), (risk.sharpe_ratio ?? 0) >= 1 ? 'text-up' : (risk.sharpe_ratio ?? 0) < 0 ? 'text-down' : '');
        this._rkSetCard('rk-pos-count', positions.length);
    },

    _rkSetCard(id, value, colorClass) {
        const el = document.getElementById(id);
        if (!el) return;
        el.textContent = value;
        el.className = 'stat-value';
        if (colorClass) el.classList.add(colorClass);
    },

    _rkRenderRiskPanel() {
        const risk = this._rk.snapshot?.risk || this._rk.snapshot?.risk_indicators;
        if (!risk) return;

        const items = [
            { label: 'VaR 95%', value: ((risk.var_95 ?? 0) * 100).toFixed(2) + '%', tip: '95% 置信度下的最大可能损失' },
            { label: 'VaR 99%', value: ((risk.var_99 ?? 0) * 100).toFixed(2) + '%', tip: '99% 置信度下的最大可能损失' },
            { label: '年化波动率', value: ((risk.volatility ?? 0) * 100).toFixed(2) + '%', tip: '年化收益率标准差' },
            { label: '最大回撤', value: ((risk.max_drawdown ?? 0) * 100).toFixed(2) + '%', tip: '峰值到谷底的最大跌幅', cls: 'text-down' },
            { label: 'Sharpe', value: (risk.sharpe_ratio ?? 0).toFixed(2), tip: '超额收益 / 波动率，>1 为优', cls: (risk.sharpe_ratio ?? 0) >= 1 ? 'text-up' : '' },
            { label: 'Sortino', value: (risk.sortino_ratio ?? 0).toFixed(2), tip: '仅考虑下行风险的 Sharpe' },
            { label: 'Calmar', value: (risk.calmar_ratio ?? 0).toFixed(2), tip: '年化收益 / 最大回撤' },
            { label: 'Beta', value: (risk.beta ?? 0).toFixed(2), tip: '相对沪深300的系统性风险' },
            { label: 'Alpha', value: ((risk.alpha ?? 0) * 100).toFixed(2) + '%', tip: '相对基准的超额收益' },
            { label: '信息比率', value: (risk.information_ratio ?? 0).toFixed(2), tip: '超额收益 / 跟踪误差' },
        ];

        const panel = document.getElementById('rk-indicator-panel');
        if (!panel) return;

        panel.innerHTML = items.map(it => `
            <div class="rk-indicator-item" title="${this.escapeHTML(it.tip)}">
                <div class="rk-indicator-label">${this.escapeHTML(it.label)}</div>
                <div class="rk-indicator-value ${it.cls || ''}">${this.escapeHTML(it.value)}</div>
            </div>
        `).join('');
    },
});
