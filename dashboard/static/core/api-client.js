(function attachAPIClient(global) {
    'use strict';

    function getAPIKey() {
        return '';
    }

    function withAPIKey(url) {
        return url;
    }

    function toast(message, type, notify) {
        if (typeof notify === 'function') {
            notify(message, type);
            return;
        }
        global.App?.toast?.(message, type);
    }

    /**
     * Unified JSON request method shared by page modules.
     * Keeps auth, retry, timeout, and user-facing errors in one place.
     */
    async function fetchJSON(url, opts = {}) {
        if (typeof opts === 'number') opts = { timeout: opts };
        const {
            timeout = 15000,
            silent = false,
            retries = 0,
            label = '',
            onToast,
            signal,
            ...fetchOpts
        } = opts;

        for (let attempt = 0; attempt <= retries; attempt++) {
            const controller = new AbortController();
            let externalAbort = null;
            if (signal) {
                externalAbort = () => controller.abort();
                if (signal.aborted) {
                    controller.abort();
                } else {
                    signal.addEventListener('abort', externalAbort, { once: true });
                }
            }
            const timer = setTimeout(() => controller.abort(), timeout);
            try {
                const headers = new Headers(fetchOpts.headers || {});
                const res = await fetch(url, { ...fetchOpts, headers, signal: controller.signal });
                if (!res.ok) {
                    let detail = '';
                    try {
                        const text = await res.text();
                        if (text) {
                            try {
                                const parsed = JSON.parse(text);
                                detail = parsed.detail || parsed.error || parsed.message || '';
                            } catch {
                                detail = text;
                            }
                        }
                    } catch {}
                    const statusText = {
                        400: '请求参数错误',
                        401: '未授权',
                        403: '无权限',
                        404: '接口不存在',
                        500: '服务器内部错误',
                        502: '服务不可用',
                        503: '服务维护中',
                    }[res.status] || `HTTP ${res.status}`;
                    const message = detail ? `${statusText}：${detail}` : statusText;
                    if (res.status === 401 && global.App && typeof global.App._handleUnauthorized === 'function' && global.App._authFlowActive !== true) {
                        global.App._handleUnauthorized(detail || '请先登录');
                    }
                    throw new Error(label ? `${label}: ${message}` : message);
                }
                return await res.json();
            } catch (e) {
                clearTimeout(timer);
                const isLast = attempt === retries;
                if (e.name === 'AbortError') {
                    if (signal?.aborted) {
                        throw e;
                    }
                    if (isLast && !silent) toast(label ? `${label}: 请求超时` : '请求超时，请检查网络', 'error', onToast);
                    if (!isLast) {
                        await new Promise(r => setTimeout(r, 1000 * (attempt + 1)));
                        continue;
                    }
                    throw new Error('请求超时');
                }
                if (!navigator.onLine) {
                    if (!silent) toast('网络已断开，请检查连接', 'error', onToast);
                    throw new Error('网络离线');
                }
                if (isLast) {
                    if (!silent) toast(e.message || '请求失败', 'error', onToast);
                    throw e;
                }
                await new Promise(r => setTimeout(r, 1000 * (attempt + 1)));
            } finally {
                clearTimeout(timer);
                if (signal && externalAbort) {
                    signal.removeEventListener('abort', externalAbort);
                }
            }
        }
    }

    global.APIClient = {
        getAPIKey,
        withAPIKey,
        fetchJSON,
    };
})(window);
