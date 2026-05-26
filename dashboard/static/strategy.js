/* ── 策略管理核心 ── */

const Strategy = {
    // 内置策略参数定义 {name: [{key, label, type, min, max, step, default}]}
    PARAM_DEFS: {
        dual_ma: [
            { key: 'short_window', label: '短均线周期', type: 'int', min: 2, max: 60, default: 5 },
            { key: 'long_window', label: '长均线周期', type: 'int', min: 5, max: 250, default: 20 },
            { key: 'position_pct', label: '仓位比例', type: 'float', min: 0.01, max: 1, step: 0.05, default: 0.9 },
        ],
        bollinger: [
            { key: 'window', label: '窗口期', type: 'int', min: 5, max: 120, default: 20 },
            { key: 'num_std', label: '标准差倍数', type: 'float', min: 0.5, max: 4, step: 0.1, default: 2 },
            { key: 'position_pct', label: '仓位比例', type: 'float', min: 0.01, max: 1, step: 0.05, default: 0.9 },
        ],
        momentum: [
            { key: 'lookback', label: '回看周期', type: 'int', min: 2, max: 120, default: 20 },
            { key: 'entry_threshold', label: '入场阈值', type: 'float', min: 0.01, max: 1, step: 0.01, default: 0.1 },
        ],
        rsi: [
            { key: 'period', label: 'RSI周期', type: 'int', min: 2, max: 50, default: 14 },
            { key: 'oversold', label: '超卖线', type: 'float', min: 10, max: 40, step: 1, default: 30 },
            { key: 'overbought', label: '超买线', type: 'float', min: 60, max: 90, step: 1, default: 70 },
        ],
        macd: [
            { key: 'fast', label: '快线周期', type: 'int', min: 2, max: 30, default: 12 },
            { key: 'slow', label: '慢线周期', type: 'int', min: 10, max: 60, default: 26 },
            { key: 'signal', label: '信号线', type: 'int', min: 2, max: 20, default: 9 },
        ],
        kdj: [
            { key: 'period', label: 'KDJ周期', type: 'int', min: 2, max: 30, default: 9 },
            { key: 'k_period', label: 'K平滑', type: 'int', min: 1, max: 10, default: 3 },
            { key: 'd_period', label: 'D平滑', type: 'int', min: 1, max: 10, default: 3 },
            { key: 'oversold', label: '超卖线', type: 'float', min: 0, max: 30, step: 1, default: 20 },
            { key: 'overbought', label: '超买线', type: 'float', min: 70, max: 100, step: 1, default: 80 },
        ],
    },

    // 所有标签（从策略列表动态收集）
    _allTags: [],
    _headerControlsBound: false,

    _removeExistingModal() {
        const existingOverlay = document.querySelector('.modal-overlay');
        if (!existingOverlay) {
            return;
        }
        if (typeof existingOverlay.__strategyCleanup === 'function') {
            existingOverlay.__strategyCleanup();
            return;
        }
        existingOverlay.remove();
    },
};

globalThis.Strategy = Strategy;
