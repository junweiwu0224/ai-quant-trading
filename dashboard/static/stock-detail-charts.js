/* ── 股票详情页：K线 / 分时 / 盘口 ── */

if (!globalThis.StockDetail) {
    globalThis.StockDetail = {};
}

Object.assign(globalThis.StockDetail, {
    // K线与指标选择器已拆分到 stock-detail-kline.js

    // 分时 / 资金流已拆分到 stock-detail-timeline.js

    // 盘口 / L2 已拆分到 stock-detail-book.js

    _bindChartTabs() {
        if (this._chartTabsBound) return;
        this._chartTabsBound = true;
        document.addEventListener('click', (e) => {
            const orderBookButton = e.target.closest('#tab-stock .sd-ob-btn[data-levels]');
            if (orderBookButton) {
                const levels = Number(orderBookButton.dataset.levels);
                if (Number.isFinite(levels)) {
                    this.setOrderBookLevels(levels);
                }
                return;
            }

            const tab = e.target.closest('#tab-stock .sd-chart-tabs .sd-tab');
            if (!tab || !this._currentCode) return;
            const period = tab.dataset.period;

            // 更新tab样式
            document.querySelectorAll('#tab-stock .sd-chart-tabs .sd-tab').forEach(t => {
                const isActive = t.dataset.period === period;
                t.classList.toggle('active', isActive);
                t.setAttribute('aria-selected', isActive);
            });

            // 分时模式隐藏指标选择器，K线模式显示
            const indicatorEl = document.querySelector('.sd-indicator-selector');
            if (indicatorEl) {
                indicatorEl.style.display = period === 'timeline' ? 'none' : '';
            }

            // 分时信息面板：分时模式显示，K线模式隐藏
            const infoPanel = document.getElementById('sd-timeline-info');
            if (infoPanel) {
                infoPanel.classList.toggle('hidden', period !== 'timeline');
            }

            if (period === 'timeline') {
                this._loadTimeline(this._currentCode);
            } else {
                this._loadKline(this._currentCode, period);
            }
        });
    },

});
