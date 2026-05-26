(function attachMarketRefresh(global) {
    'use strict';

    const App = global.App;
    if (!App) {
        return;
    }

    Object.assign(App, {
        _startMarketRefresh() {
            PollManager.cancel('marketRefresh');
            this._refreshMarket();
            this._updateMarketStatus();
            const interval = this._isMarketOpen() ? 10000 : 60000;
            PollManager.register('marketRefresh', () => {
                this._refreshMarket();
                this._updateMarketStatus();
            }, interval);
        },

        _isMarketOpen() {
            const now = new Date();
            const day = now.getDay();
            if (day === 0 || day === 6) return false;
            const hhmm = now.getHours() * 100 + now.getMinutes();
            return (hhmm >= 915 && hhmm <= 1130) || (hhmm >= 1300 && hhmm <= 1500);
        },

        _updateMarketStatus() {
            const el = document.getElementById('ov-market-status');
            if (!el) return;
            const now = new Date();
            const day = now.getDay();
            const hhmm = now.getHours() * 100 + now.getMinutes();
            let status, cls;
            if (day === 0 || day === 6) {
                status = '休市'; cls = 'closed';
            } else if (hhmm >= 915 && hhmm < 930) {
                status = '集合竞价'; cls = 'pre';
            } else if ((hhmm >= 930 && hhmm <= 1130) || (hhmm >= 1300 && hhmm <= 1500)) {
                status = '交易中'; cls = 'open';
            } else if (hhmm > 1130 && hhmm < 1300) {
                status = '午间休市'; cls = 'closed';
            } else {
                status = '已收盘'; cls = 'closed';
            }
            el.textContent = status;
            el.className = `market-status-badge ${cls}`;
        },

        _stopMarketRefresh() {
            PollManager.cancel('marketRefresh');
        },

        async _refreshMarket() {
            try {
                const [indices, hotSectors] = await Promise.all([
                    this.fetchJSON('/api/stock/market/indices').catch(() => []),
                    this.fetchJSON('/api/stock/market/hot-sectors').catch(() => ({ industries: [], concepts: [] })),
                ]);
                this.renderMarketIndices(indices);
                this.renderHotSectors(hotSectors);
            } catch (e) {
                console.warn('市场数据刷新失败:', e);
            }
        },
    });
})(window);
