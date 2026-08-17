/* AI Quant Service Worker — Vue shell offline cache */

const CACHE_NAME = 'ai-quant-vue-v1';
const STATIC_ASSETS = [
    '/app/decision',
    '/static/manifest.json',
    '/static/icons/icon-192.svg',
    '/static/icons/icon-512.svg',
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

    // WebSocket 请求直接放行。
    if (url.protocol === 'ws:' || url.protocol === 'wss:') return;

    // API 请求：network-first（离线时返回缓存）
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(networkFirst(event.request));
        return;
    }

    // Small PWA assets remain available after the first successful visit.
    if (url.pathname === '/static/manifest.json' || url.pathname.startsWith('/static/icons/')) {
        event.respondWith(cacheFirst(event.request));
        return;
    }

    // Vite emits immutable, hashed assets under this path.
    if (url.pathname.startsWith('/app/assets/')) {
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
