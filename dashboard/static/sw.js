/* AI Quant Service Worker — 离线缓存 + 资源预缓存 */

const CACHE_NAME = 'ai-quant-v99';
const STATIC_ASSETS = [
    '/static/style.css',
    '/static/paper-trading.css',
    '/static/manifest.json',
    '/static/icons/icon-192.svg',
    '/static/icons/icon-512.svg',
    '/static/charts.js',
    '/static/utils.js',
    '/static/search.js',
    '/static/watchlist.js',
    '/static/paper.js',
    '/static/paper-trading.js',
    '/static/paper-trading-trade.js',
    '/static/paper-trading-position.js',
    '/static/paper-trading-performance.js',
    '/static/paper-trading-analytics.js',
    '/static/paper-trading-history.js',
    '/static/strategy.js',
    '/static/strategy-list.js',
    '/static/strategy-form.js',
    '/static/strategy-code-editor.js',
    '/static/strategy-tools.js',
    '/static/strategy-versions.js',
    '/static/strategy-records.js',
    '/static/strategy-optimizer.js',
    '/static/realtime.js',
    '/static/stock-detail.js',
    '/static/stock-detail-core.js',
    '/static/stock-detail-valuation.js',
    '/static/stock-detail-drawings.js',
    '/static/stock-detail-insights.js',
    '/static/stock-detail-chips.js',
    '/static/stock-detail-market.js',
    '/static/stock-detail-market-mtf.js',
    '/static/stock-detail-market-dragon.js',
    '/static/stock-detail-research.js',
    '/static/stock-detail-charts.js',
    '/static/stock-detail-timeline.js',
    '/static/stock-detail-timeline-overlays.js',
    '/static/stock-detail-kline.js',
    '/static/stock-detail-book.js',
    '/static/stock-detail-data.js',
    '/static/app.js',
    '/static/app-stock-ops.js',
    '/static/app-ui-shell.js',
    '/static/app-workbench.js',
    '/static/app-archives.js',
    '/static/openclaw-conversations.js',
    '/static/openclaw-workbench.js',
    '/static/research-valuation.js',
    '/static/research-datahub.js',
    '/static/app-bootstrap.js',
    '/static/overview.js',
    '/static/backtest.js',
    '/static/backtest-analysis.js',
    '/static/backtest-strategies.js',
    '/static/portfolio.js',
    '/static/risk.js',
    '/static/alpha.js',
    '/static/alpha-charts.js',
    '/static/alpha-factors.js',
    '/static/alpha-tools.js',
    '/static/llm.js',
    '/static/llm-render.js',
    '/static/llm-actions.js',
    '/static/llm-conversations.js',
    '/static/llm-copilot.js',
    '/static/compare.js',
    '/static/screener.js',
    '/static/screener-ai.js',
    '/static/alerts.js',
    '/static/overview-radar.js',
    '/static/optimization.js',
    '/static/intelligence.js',
    '/static/intelligence-market.js',
    '/static/intelligence-iwencai.js',
    '/static/intelligence-signals.js',
    '/static/factor.js',
    '/static/portfolio-opt.js',
    '/static/strategy-ensemble.js',
];

const CDN_ASSETS = [
    'https://cdn.jsdelivr.net/npm/chart.js@4',
    'https://cdn.jsdelivr.net/npm/klinecharts@9/dist/klinecharts.min.js',
];

// ── Install: 预缓存静态资源 ──

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            // 本地资源优先，CDN资源尽力缓存
            return cache.addAll(STATIC_ASSETS).catch(() => {
                console.warn('[SW] 部分本地资源缓存失败，继续安装');
            });
        })
    );
    self.skipWaiting();
});

// ── Activate: 清理旧缓存 ──

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((names) => {
            return Promise.all(
                names.filter((n) => n !== CACHE_NAME).map((n) => caches.delete(n))
            );
        })
    );
    self.clients.claim();
});

// ── Fetch: 分层缓存策略 ──

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // WebSocket 请求直接放行
    if (url.protocol === 'ws:' || url.protocol === 'wss:') return;

    // API 请求：network-first（离线时返回缓存）
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(networkFirst(event.request));
        return;
    }

    // 版本化静态资源：network-first，避免开发/升级后继续吃旧缓存
    if (url.pathname.startsWith('/static/') && url.search) {
        event.respondWith(networkFirst(event.request));
        return;
    }

    // 静态资源：cache-first
    if (url.pathname.startsWith('/static/')) {
        event.respondWith(cacheFirst(event.request));
        return;
    }

    // CDN 资源：stale-while-revalidate
    if (url.hostname !== location.hostname) {
        event.respondWith(staleWhileRevalidate(event.request));
        return;
    }

    // HTML 页面：network-first
    if (event.request.mode === 'navigate') {
        event.respondWith(networkFirst(event.request));
        return;
    }

    // 其他：network-first
    event.respondWith(networkFirst(event.request));
});

// ── 缓存策略实现 ──

async function cacheFirst(request) {
    const cached = await caches.match(request);
    if (cached) return cached;
    try {
        const response = await fetch(request);
        if (response.ok) {
            const cache = await caches.open(CACHE_NAME);
            cache.put(request, response.clone());
        }
        return response;
    } catch {
        return new Response('离线', { status: 503, statusText: 'Offline' });
    }
}

async function networkFirst(request) {
    try {
        const response = await fetch(request);
        if (response.ok && request.method === 'GET') {
            const cache = await caches.open(CACHE_NAME);
            cache.put(request, response.clone());
        }
        return response;
    } catch {
        const cached = await caches.match(request);
        if (cached) return cached;
        // 离线且无缓存：页面导航返回轻量提示，不复用过期 HTML 壳子
        if (request.mode === 'navigate') {
            return new Response('离线，无法加载最新页面', {
                status: 503,
                statusText: 'Offline',
                headers: { 'Content-Type': 'text/plain; charset=utf-8' },
            });
        }
        return new Response('离线', { status: 503, statusText: 'Offline' });
    }
}

async function staleWhileRevalidate(request) {
    const cache = await caches.open(CACHE_NAME);
    const cached = await cache.match(request);
    const fetchPromise = fetch(request).then((response) => {
        if (response.ok) cache.put(request, response.clone());
        return response;
    }).catch(() => cached);
    return cached || fetchPromise;
}
