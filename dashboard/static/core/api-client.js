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

    const FIELD_LABELS = {
        username: '用户名',
        password: '密码',
        invite_code: '邀请码',
        display_name: '昵称',
        email: '邮箱',
    };

    function formatValidationMessage(item) {
        if (!item || typeof item !== 'object') {
            return '';
        }
        const loc = Array.isArray(item.loc) ? item.loc : [];
        const field = loc.length ? loc[loc.length - 1] : '';
        const label = FIELD_LABELS[field] || field || '字段';
        const type = String(item.type || '');
        const ctx = item.ctx || {};

        if (type.includes('string_too_short') && ctx.min_length) {
            return `${label}至少需要 ${ctx.min_length} 个字符`;
        }
        if (type.includes('string_too_long') && ctx.max_length) {
            return `${label}最多只能 ${ctx.max_length} 个字符`;
        }
        if (type.includes('missing')) {
            return `请填写${label}`;
        }
        return item.msg ? `${label}: ${item.msg}` : '';
    }

    function formatErrorDetail(detail, status) {
        if (!detail) {
            return '';
        }
        if (typeof detail === 'string') {
            return detail;
        }
        if (Array.isArray(detail)) {
            const messages = detail.map(formatValidationMessage).filter(Boolean);
            if (messages.length) {
                return `请求参数校验失败：${messages.join('；')}`;
            }
            return status === 422 ? '请求参数校验失败' : JSON.stringify(detail);
        }
        if (typeof detail === 'object') {
            if (typeof detail.message === 'string' && detail.message) {
                return detail.message;
            }
            if (typeof detail.error === 'string' && detail.error) {
                return detail.error;
            }
            try {
                return JSON.stringify(detail);
            } catch {
                return String(detail);
            }
        }
        return String(detail);
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
                                detail = formatErrorDetail(
                                    parsed.detail || parsed.error || parsed.message || '',
                                    res.status,
                                );
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
