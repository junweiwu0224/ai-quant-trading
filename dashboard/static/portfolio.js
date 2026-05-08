/* ── 持仓模块：编排器 ── */

Object.assign(App, {
    _pf: {
        snapshot: null,
        positions: [],
        trades: [],
        industry: [],
        equityHistory: [],
        historyPage: 1,
        historyTotal: 0,
        historyLoaded: false,
        searchQuery: '',
        strategyFilter: '',
        sortKey: 'mv',
        sortDir: 'desc',
        equityCurveRange: '1m',
        _closingCode: null,
        _partialCode: null,
        _sltpCode: null,
    },

    _pfLoaded: false,

    async loadPortfolio() {
        const refreshBtn = document.querySelector('button[onclick="App.loadPortfolio()"]');
        if (refreshBtn) refreshBtn.disabled = true;

        if (!this._pfLoaded) {
            this._showPortfolioSkeletons();
        }

        try {
            const so = { silent: true };
            const [snapshot, trades, industry, equityHistory] = await Promise.all([
                this.fetchJSON('/api/portfolio/snapshot'),
                this.fetchJSON('/api/portfolio/trades', so).catch(() => []),
                this.fetchJSON('/api/portfolio/industry-distribution', so).catch(() => []),
                this.fetchJSON('/api/portfolio/equity-history', so).catch(() => []),
            ]);

            this._pf.snapshot = snapshot;
            this._pf.positions = snapshot.positions || [];
            this._pf.trades = trades;
            this._pf.industry = industry;
            this._pf.equityHistory = equityHistory;

            this._pfRenderAll();
            this._hidePortfolioSkeletons();
            this._pfUpdateTime();
            this._pfBindTableEvents();
        } catch (e) {
            this.toast('持仓数据加载失败', 'error');
        } finally {
            this._pfLoaded = true;
            if (refreshBtn) refreshBtn.disabled = false;
        }
    },

    _showPortfolioSkeletons() {
        document.querySelectorAll('#tab-portfolio .stat-value').forEach(el => {
            el.classList.add('skeleton-text');
        });
    },

    _hidePortfolioSkeletons() {
        document.querySelectorAll('#tab-portfolio .stat-value.skeleton-text').forEach(el => {
            el.classList.remove('skeleton-text');
        });
    },

    _pfRenderAll() {
        this._pfRenderStats();
        this._pfRenderTable();
        this._pfRenderEquityCurve();
        this._pfRenderPnlChart();
        this._pfRenderIndustryChart();
        this._pfRenderAllocationChart();
        this._pfRenderPositionTrend();
        this._pfRenderTrades();
    },

    _pfUpdateTime() {
        const el = document.getElementById('pf-last-update');
        if (el && this._pf.snapshot?.update_time) {
            const t = new Date(this._pf.snapshot.update_time);
            el.textContent = `更新于 ${Utils.formatBeijingTimeOnly(this._pf.snapshot.update_time)}`;
        }
    },
});
