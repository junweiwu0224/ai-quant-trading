(function attachAppStockOps(global) {
    'use strict';

    const App = global.App;
    if (!App) {
        return;
    }

    Object.assign(App, {
        async openStockDetail(code, options = {}) {
            await this.ensureBundle?.('stock');
            const rawCode = typeof code === 'string' ? code.trim() : '';
            const codeMatch = rawCode.match(/^(?:sh|sz|bj)?(\d{6})(?:\.(?:SH|SZ|BJ))?$/i) || rawCode.match(/\b(\d{6})\b/);
            const normalizedCode = codeMatch ? codeMatch[1] : rawCode;
            if (!normalizedCode) {
                return { ok: false, status: 'invalid', code: 'STOCK_CODE_REQUIRED' };
            }

            const source = typeof options.source === 'string' && options.source.trim()
                ? options.source.trim()
                : 'app:open-stock-detail';
            const optionStock = options.stock && typeof options.stock === 'object' ? options.stock : null;
            const optionName = typeof options.name === 'string' && options.name.trim() ? options.name.trim() : '';
            const currentIdentity = globalThis.GlobalStockStore?.getState?.()?.identity || {};
            const contextStock = optionStock
                || (optionName ? { code: normalizedCode, name: optionName } : null)
                || (currentIdentity.code === normalizedCode && currentIdentity.name ? { code: normalizedCode, name: currentIdentity.name } : null);
            const preferDirectOpen = options && typeof options === 'object' && options.preferDirectOpen === true;
            try {
                sessionStorage.setItem('last_stock_code', normalizedCode);
            } catch {
                // ignore storage failures
            }

            const waitForDeferredLoad = options.awaitDeferredLoad === true;
            const waitForDetailLoad = options.awaitDetailLoad === true || waitForDeferredLoad;
            const openDirectly = async (status) => {
                this._activeStockCode = normalizedCode;
                this.syncActiveStockContext?.(normalizedCode, contextStock, source, 'open-stock-detail');
                await this.switchTab?.('stock', { autoOpenStock: false });
                if (globalThis.StockDetail && typeof globalThis.StockDetail.open === 'function') {
                    globalThis.StockDetail.init?.();
                    const detailPromise = globalThis.StockDetail.open(normalizedCode, {
                        stock: contextStock,
                        source,
                        awaitDeferredLoad: waitForDeferredLoad,
                    });
                    if (waitForDetailLoad) {
                        await detailPromise;
                    } else {
                        void Promise.resolve(detailPromise).catch((error) => {
                            console.warn('后台加载股票详情失败:', error);
                        });
                    }
                    return { ok: true, status, code: normalizedCode, source };
                }
                return { ok: false, status: 'unavailable', code: 'STOCK_DETAIL_UNAVAILABLE', source };
            };

            if (globalThis.ENABLE_WORKSPACE_V2 === false) {
                return openDirectly('legacy');
            }

            if (preferDirectOpen) {
                return openDirectly('direct');
            }

            const result = await this._invokeStockActionWithFallback({
                toolId: 'open_stock_detail',
                input: { code: normalizedCode },
                source,
                actionKey: `open_stock_detail:${normalizedCode}`,
            });
            if (result && result.ok) {
                return result;
            }
            return openDirectly('fallback');
        },

        getLastOpenedStockCode() {
            if (typeof this._activeStockCode === 'string' && this._activeStockCode.trim()) {
                return this._activeStockCode.trim();
            }
            try {
                const saved = sessionStorage.getItem('last_stock_code') || '';
                return saved.trim();
            } catch {
                return '';
            }
        },

        /** 统一加入自选股：对外入口统一走 LocalMCP */
        async addToWatchlist(code, options = {}) {
            const normalizedCode = typeof code === 'string' ? code.trim() : '';
            if (!normalizedCode) {
                return { ok: false, status: 'invalid', code: 'STOCK_CODE_REQUIRED' };
            }

            const safeOptions = options && typeof options === 'object' ? options : {};
            const source = typeof safeOptions.source === 'string' && safeOptions.source.trim()
                ? safeOptions.source.trim()
                : 'app:add-watchlist';

            return this.invokeStockAction({
                toolId: 'add_to_watchlist',
                input: { code: normalizedCode },
                source,
                traceId: typeof safeOptions.traceId === 'string' && safeOptions.traceId.trim() ? safeOptions.traceId.trim() : null,
                requestId: typeof safeOptions.requestId === 'string' && safeOptions.requestId.trim() ? safeOptions.requestId.trim() : null,
                metadata: safeOptions.metadata && typeof safeOptions.metadata === 'object' ? { ...safeOptions.metadata } : null,
                actionKey: `add_to_watchlist:${normalizedCode}`,
                suppressFailureToast: safeOptions.suppressFailureToast === true,
            });
        },

        async removeFromWatchlist(code, options = {}) {
            const normalizedCode = typeof code === 'string' ? code.trim() : '';
            if (!normalizedCode) {
                return { ok: false, status: 'invalid', code: 'STOCK_CODE_REQUIRED' };
            }

            const safeOptions = options && typeof options === 'object' ? options : {};
            const source = typeof safeOptions.source === 'string' && safeOptions.source.trim()
                ? safeOptions.source.trim()
                : 'app:remove-watchlist';

            return this.invokeStockAction({
                toolId: 'remove_from_watchlist',
                input: { code: normalizedCode },
                source,
                traceId: typeof safeOptions.traceId === 'string' && safeOptions.traceId.trim() ? safeOptions.traceId.trim() : null,
                requestId: typeof safeOptions.requestId === 'string' && safeOptions.requestId.trim() ? safeOptions.requestId.trim() : null,
                metadata: safeOptions.metadata && typeof safeOptions.metadata === 'object' ? { ...safeOptions.metadata } : null,
                actionKey: `remove_from_watchlist:${normalizedCode}`,
                suppressFailureToast: safeOptions.suppressFailureToast === true,
            });
        },

        async openPaperBuy(code, options = {}) {
            const normalizedCode = typeof code === 'string' ? code.trim() : '';
            if (!normalizedCode) {
                return { ok: false, status: 'invalid', code: 'STOCK_CODE_REQUIRED' };
            }

            const safeOptions = options && typeof options === 'object' ? options : {};
            const source = typeof safeOptions.source === 'string' && safeOptions.source.trim()
                ? safeOptions.source.trim()
                : 'app:open-paper-buy';
            const input = safeOptions.input && typeof safeOptions.input === 'object'
                ? { ...safeOptions.input, code: normalizedCode }
                : { code: normalizedCode };

            return this.invokeStockAction({
                toolId: 'open_paper_buy',
                input,
                source,
                traceId: typeof safeOptions.traceId === 'string' && safeOptions.traceId.trim() ? safeOptions.traceId.trim() : null,
                requestId: typeof safeOptions.requestId === 'string' && safeOptions.requestId.trim() ? safeOptions.requestId.trim() : null,
                metadata: safeOptions.metadata && typeof safeOptions.metadata === 'object' ? { ...safeOptions.metadata } : null,
                actionKey: `open_paper_buy:${normalizedCode}`,
                suppressFailureToast: safeOptions.suppressFailureToast === true,
            });
        },

        async _commitWatchlistAdd(code) {
            const normalizedCode = typeof code === 'string' ? code.trim() : '';
            if (!normalizedCode) {
                throw new Error('STOCK_CODE_REQUIRED');
            }

            const data = await this.fetchJSON('/api/watchlist', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code: normalizedCode }), label: '加入自选股',
            });
            if (!data.success) {
                throw new Error(data.error || data.message || '添加失败');
            }

            const existing = (this.watchlistCache || []).find((stock) => stock.code === normalizedCode);
            if (!existing) {
                const item = {
                    code: normalizedCode,
                    name: data.name || normalizedCode,
                    industry: data.industry || '',
                    sector: data.sector || '',
                    concepts: Array.isArray(data.concepts) ? data.concepts : [],
                    price: data.price || null,
                    change_pct: data.change_pct != null ? data.change_pct : null,
                };
                this.watchlistCache = [...(this.watchlistCache || []), item];
            }

            Watchlist.render(this.watchlistCache || []);
            this._watchlistRowMap = null;
            RealtimeQuotes.subscribe([normalizedCode]);
            this.toast(`${normalizedCode} ${data.name || ''} 已加入自选股`, 'success');
            this._scheduleWatchlistRefresh();

            return {
                ok: true,
                code: normalizedCode,
                data,
            };
        },

        async _commitWatchlistRemove(code) {
            const normalizedCode = typeof code === 'string' ? code.trim() : '';
            if (!normalizedCode) {
                throw new Error('STOCK_CODE_REQUIRED');
            }

            await this.fetchJSON(`/api/watchlist/${encodeURIComponent(normalizedCode)}`, {
                method: 'DELETE',
                label: '移除自选股',
            });

            this.watchlistCache = (this.watchlistCache || []).filter((stock) => stock.code !== normalizedCode);
            Watchlist.render(this.watchlistCache || []);
            this._watchlistRowMap = null;
            RealtimeQuotes.unsubscribe([normalizedCode]);
            this.toast(`已移除 ${normalizedCode}`, 'success');

            return {
                ok: true,
                code: normalizedCode,
            };
        },

        _createActionTraceId(prefix) {
            if (globalThis.LocalMCP && typeof globalThis.LocalMCP.createTraceId === 'function') {
                return globalThis.LocalMCP.createTraceId(prefix);
            }
            const safePrefix = typeof prefix === 'string' && prefix.trim() ? prefix.trim() : 'app-action';
            return `${safePrefix}-${Date.now()}`;
        },

        _setActionPending(actionKey, isPending) {
            if (!actionKey) {
                return false;
            }

            if (isPending) {
                if (this._uiActionPending[actionKey] === true) {
                    return false;
                }
                this._uiActionPending = {
                    ...this._uiActionPending,
                    [actionKey]: true,
                };
                return true;
            }

            if (this._uiActionPending[actionKey] !== true) {
                return true;
            }

            const nextPending = {
                ...this._uiActionPending,
            };
            delete nextPending[actionKey];
            this._uiActionPending = nextPending;
            return true;
        },

        async invokeStockAction(params) {
            const safeParams = params && typeof params === 'object' ? params : {};
            const shouldToastFailure = safeParams.suppressFailureToast !== true;
            const localMCP = globalThis.LocalMCP;
            if (!localMCP || typeof localMCP.invoke !== 'function') {
                if (shouldToastFailure) {
                    this.toast('统一动作入口不可用', 'error');
                }
                return {
                    ok: false,
                    status: 'failed',
                    code: 'LOCAL_MCP_UNAVAILABLE',
                };
            }

            const toolId = typeof safeParams.toolId === 'string' ? safeParams.toolId.trim() : '';
            const input = safeParams.input && typeof safeParams.input === 'object' ? { ...safeParams.input } : null;
            const source = typeof safeParams.source === 'string' && safeParams.source.trim() ? safeParams.source.trim() : 'app';
            const traceId = typeof safeParams.traceId === 'string' && safeParams.traceId.trim()
                ? safeParams.traceId.trim()
                : this._createActionTraceId(source);
            const actionKey = typeof safeParams.actionKey === 'string' && safeParams.actionKey.trim() ? safeParams.actionKey.trim() : null;

            if (!toolId) {
                if (shouldToastFailure) {
                    this.toast('动作标识缺失', 'error');
                }
                return {
                    ok: false,
                    status: 'failed',
                    code: 'ACTION_ID_REQUIRED',
                };
            }

            if (actionKey && this._setActionPending(actionKey, true) !== true) {
                return {
                    ok: false,
                    status: 'blocked',
                    code: 'ACTION_ALREADY_PENDING',
                };
            }

            try {
                const result = await localMCP.invoke({
                    toolId,
                    input,
                    source,
                    traceId,
                    requestId: typeof safeParams.requestId === 'string' && safeParams.requestId.trim() ? safeParams.requestId.trim() : null,
                    metadata: safeParams.metadata && typeof safeParams.metadata === 'object' ? { ...safeParams.metadata } : null,
                });

                if (!result.ok && shouldToastFailure) {
                    this.toast(this._resolveActionFailureMessage(result), 'error');
                }

                return result;
            } catch (error) {
                if (shouldToastFailure) {
                    this.toast(this._resolveActionFailureMessage({ error }), 'error');
                }
                return {
                    ok: false,
                    status: 'failed',
                    code: error && typeof error.code === 'string' ? error.code : 'LOCAL_MCP_INVOKE_FAILED',
                    error,
                };
            } finally {
                if (actionKey) {
                    this._setActionPending(actionKey, false);
                }
            }
        },

        _resolveActionFailureMessage(result) {
            const errorMessage = result && result.error && typeof result.error.message === 'string' && result.error.message.trim()
                ? result.error.message.trim()
                : '';

            if (errorMessage) {
                return errorMessage;
            }

            if (result && result.code === 'ACTION_ID_REQUIRED') {
                return '动作标识缺失';
            }

            if (result && result.code === 'ACTION_ALREADY_PENDING') {
                return '操作进行中，请稍候';
            }

            if (result && result.status === 'blocked') {
                return '当前操作暂不可执行';
            }

            if (result && result.status === 'not_found') {
                return '未找到可执行动作';
            }

            return '操作执行失败';
        },

        async _invokeStockActionWithFallback(params) {
            const safeParams = params && typeof params === 'object' ? params : {};
            const result = await this.invokeStockAction(safeParams);
            if (result && result.ok) {
                return result;
            }

            const code = typeof safeParams.input?.code === 'string' ? safeParams.input.code.trim() : '';
            if (safeParams.toolId === 'open_stock_detail' && code && globalThis.StockDetail && typeof globalThis.StockDetail.open === 'function') {
                await this.ensureBundle?.('stock');
                this._activeStockCode = code;
                await this.switchTab?.('stock');
                globalThis.StockDetail.init?.();
                const waitForFallbackDeferredLoad = safeParams.awaitDeferredLoad === true;
                const detailPromise = globalThis.StockDetail.open(code, {
                    awaitDeferredLoad: waitForFallbackDeferredLoad,
                });
                if (safeParams.awaitDetailLoad === true || waitForFallbackDeferredLoad) {
                    await detailPromise;
                } else {
                    void Promise.resolve(detailPromise).catch((error) => {
                        console.warn('后台加载股票详情失败:', error);
                    });
                }
                return {
                    ok: true,
                    status: 'fallback',
                    code,
                    source: safeParams.source || 'app:open-stock-detail:fallback',
                    previous: result,
                };
            }

            return result;
        },

        /** 批量加入自选股 */
        async addAllToWatchlist(codes) {
            if (!Array.isArray(codes) || codes.length === 0) return;
            let ok = 0, fail = 0;
            for (const code of codes) {
                const result = await this.addToWatchlist(code);
                if (result && result.ok) ok++; else fail++;
            }
            if (codes.length > 1) {
                this.toast(`自选股: 成功 ${ok}，失败 ${fail}`, ok > 0 ? 'success' : 'error');
            }
        },

        _watchlistRefreshTimer: null,
        _scheduleWatchlistRefresh() {
            if (this._watchlistRefreshTimer) return;
            this._watchlistRefreshTimer = setTimeout(() => {
                this._watchlistRefreshTimer = null;
                Watchlist._refreshWatchlistTable();
            }, 3000);
        },
    });
})(window);
