/* ── 风控模块：编排器 ── */

Object.assign(App, {
    _rk: {
        snapshot: null,
        equityHistory: [],
        correlation: [],
        industry: [],
        capital: null,
        events: [],
        rules: null,
        systemRules: [],
        alerts: [],
        activeAlerts: [],
        _rulesLoaded: false,
    },

    _rkLoaded: false,

    async loadRisk() {
        const refreshBtn = document.querySelector('button[onclick="App.loadRisk()"]');
        if (refreshBtn) refreshBtn.disabled = true;

        if (!this._rkLoaded) {
            this._showRiskSkeletons();
        }

        try {
            const so = { silent: true };
            const [snapshot, equityHistory, correlation, industry, capital, eventsResp, rulesResp, systemRules] = await Promise.all([
                this.fetchJSON('/api/portfolio/snapshot', so).catch(() => null),
                this.fetchJSON('/api/portfolio/equity-history', so).catch(() => []),
                this.fetchJSON('/api/portfolio/correlation', so).catch(() => []),
                this.fetchJSON('/api/portfolio/industry-distribution', so).catch(() => []),
                this.fetchJSON('/api/portfolio/capital-utilization', so).catch(() => null),
                this.fetchJSON('/api/paper/risk/events?days=90', so).catch(() => ({ success: false, data: [] })),
                this.fetchJSON('/api/paper/risk/rules', so).catch(() => ({ success: false, data: {} })),
                this.fetchJSON('/api/system/risk/rules', so).catch(() => []),
            ]);

            this._rk.snapshot = snapshot;
            this._rk.equityHistory = equityHistory;
            this._rk.correlation = correlation;
            this._rk.industry = industry;
            this._rk.capital = capital;
            this._rk.events = eventsResp?.data || [];
            this._rk.rules = rulesResp?.data || {};
            this._rk.systemRules = systemRules || [];

            this._rkRenderAll();
        } catch (e) {
            this.toast('风控数据加载失败: ' + e.message, 'error');
        } finally {
            this._rkLoaded = true;
            if (refreshBtn) refreshBtn.disabled = false;
        }
    },

    _showRiskSkeletons() {
        // 统计卡片
        const statsEl = document.querySelector('#tab-risk .stats-grid');
        if (statsEl) statsEl.innerHTML = Utils.skeletonCards(6);
        // 图表区域
        document.querySelectorAll('#tab-risk .chart-container').forEach(el => {
            el.innerHTML = Utils.skeletonChart(15);
        });
        // 事件时间线
        const timeline = document.getElementById('rk-events-timeline');
        if (timeline) timeline.innerHTML = Utils.skeletonRows(4, 1);
    },

    _rkRenderAll() {
        const safe = (name, fn) => { try { fn(); } catch (e) { console.error(`[风控] ${name} 渲染失败:`, e); } };
        safe('指标卡片', () => this._rkRenderStats());
        safe('VaR面板', () => this._rkRenderRiskPanel());
        safe('图表', () => this._rkRenderCharts());
        safe('规则', () => this._rkRenderRules());
        safe('止损止盈', () => this._rkRenderPositionSltp());
        safe('事件', () => this._rkRenderEvents());
        safe('告警横幅', () => this._rkRenderAlertBanner());
    },

    _rkStartPolling() {
        PollManager.cancel('risk');
        PollManager.register('risk', () => this.loadRisk(), 30000);
        if (this._rkRequestNotificationPermission) this._rkRequestNotificationPermission();
    },

    _rkStopPolling() {
        PollManager.cancel('risk');
    },
});
