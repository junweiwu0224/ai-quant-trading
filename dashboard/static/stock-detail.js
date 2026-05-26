/* ── 股票详情页（独立Tab） ── */

const StockDetail = {
    _klineChart: null,
    _klineResizeObs: null,
    _indicatorPaneId: null,
    _avgOverlays: null,
    _timelineIndicatorsRegistered: false,
    _profitChart: null,
    _northChart: null,
    _capitalChart: null,
    _currentCode: null,
    _currentPeriod: 'daily',
    _currentIndicator: '',
    _currentKlines: null,
    _currentTimelineTrends: null,
    _currentTimelinePreClose: null,
    _searchBox: null,
    _openGeneration: 0,

    // L2 十档行情
    _l2Ws: null,
    _l2Levels: 5,
    _l2Data: null,
    _l2ReconnectTimer: null,

    // 主生命周期与基础详情渲染已拆分到 stock-detail-core.js

    // 基础详情加载与文本统计已拆分到 stock-detail-data.js
    // K线 / 分时 / 盘口 / L2 已拆分到 stock-detail-charts.js
    // 画线工具已拆分到 stock-detail-drawings.js

    // 筹码 / 多周期 / 龙虎榜 / 研报 / Alpha 信号已拆分到独立文件
};

globalThis.StockDetail = StockDetail;
