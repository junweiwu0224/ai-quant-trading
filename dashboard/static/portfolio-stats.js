/* ── 持仓模块：统计卡片 ── */

Object.assign(App, {
    _pfRenderStats() {
        const s = this._pf.snapshot;
        if (!s) return;

        const fmt = (v) => this.fmt(v);
        const fmtPct = (v) => (v * 100).toFixed(2) + '%';
        const colorClass = (v) => v > 0 ? 'pf-val-up' : v < 0 ? 'pf-val-down' : 'pf-val-flat';

        document.getElementById('pf-equity').textContent = fmt(s.total_equity);
        document.getElementById('pf-cash').textContent = fmt(s.cash);
        document.getElementById('pf-mv').textContent = fmt(s.market_value);
        document.getElementById('pf-count').textContent = s.positions.length;

        const dayPnlEl = document.getElementById('pf-day-pnl');
        dayPnlEl.textContent = (s.daily_pnl >= 0 ? '+' : '') + fmt(s.daily_pnl);
        dayPnlEl.className = 'stat-value ' + colorClass(s.daily_pnl);

        const totalRetEl = document.getElementById('pf-total-return');
        totalRetEl.textContent = fmtPct(s.cumulative_return);
        totalRetEl.className = 'stat-value ' + colorClass(s.cumulative_return);

        const maxDdEl = document.getElementById('pf-max-dd');
        maxDdEl.textContent = fmtPct(-s.max_drawdown);
        maxDdEl.className = 'stat-value pf-val-down';

        const sharpeEl = document.getElementById('pf-sharpe');
        sharpeEl.textContent = s.sharpe_ratio.toFixed(2);
        sharpeEl.className = 'stat-value ' + colorClass(s.sharpe_ratio);

        const utilEl = document.getElementById('pf-utilization');
        const utilRate = s.capital ? s.capital.utilization_rate : 0;
        utilEl.textContent = fmtPct(utilRate);
    },
});
