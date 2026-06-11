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
            this._pushStockContextItem(normalizedCode, {
                stock: contextStock,
                source,
                sourceLabel: options.sourceLabel,
                contextList: options.contextList,
                sector_name: options.sector_name,
                context_type: options.context_type,
                rank_reason: options.rank_reason,
                query: options.query,
                price: options.price,
                change_pct: options.change_pct,
                updated_at: options.updated_at || options.generated_at || options.timestamp,
                source_context: options.source_context,
            });
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
                        sourceLabel: options.sourceLabel,
                        context_type: options.context_type,
                        sector_name: options.sector_name,
                        rank_reason: options.rank_reason,
                        query: options.query,
                        contextList: options.contextList,
                        source_context: options.source_context,
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

        _pushStockContextItem(code, options = {}) {
            const normalizedCode = typeof code === 'string' ? code.trim() : '';
            if (!normalizedCode) return;
            const normalizeCode = (value) => {
                const raw = String(value || '').trim();
                const match = raw.match(/^(?:sh|sz|bj)?(\d{6})(?:\.(?:SH|SZ|BJ))?$/i) || raw.match(/\b(\d{6})\b/);
                return match ? match[1] : raw;
            };
            const stock = options.stock && typeof options.stock === 'object' ? options.stock : {};
            const source = typeof options.source === 'string' && options.source.trim()
                ? options.source.trim()
                : 'app:open-stock-detail';
            const current = Array.isArray(this._stockContextItems) ? this._stockContextItems : [];
            const pool = Array.isArray(options.contextList) ? options.contextList : [];
            const sourceLabel = typeof options.sourceLabel === 'string' && options.sourceLabel.trim()
                ? options.sourceLabel.trim()
                : this._stockContextSourceLabel(source);
                const buildItem = (candidate, fallback = {}) => {
                    const candidateStock = candidate && typeof candidate === 'object' ? candidate : {};
                    const itemCode = normalizeCode(candidateStock.code || fallback.code || normalizedCode);
                    const existing = current.find((item) => item.code === itemCode) || {};
                    const itemSource = candidateStock.source || fallback.source || existing.source || source;
                    const itemSourceLabel = candidateStock.sourceLabel
                        || fallback.sourceLabel
                        || existing.sourceLabel
                        || (itemSource === source ? sourceLabel : this._stockContextSourceLabel(itemSource));
                    const sectorName = candidateStock.sector_name || fallback.sector_name || existing.sector_name || options.sector_name || '';
                    const sourceContext = candidateStock.source_context
                        || fallback.source_context
                        || existing.source_context
                        || options.source_context
                        || null;
                    return {
                        ...existing,
                        code: itemCode,
                        name: candidateStock.name || fallback.name || existing.name || itemCode,
                        source: itemSource,
                    sourceLabel: itemSourceLabel,
                    sector_name: sectorName,
                    context_type: candidateStock.context_type || fallback.context_type || existing.context_type || options.context_type || '',
                    rank_reason: candidateStock.rank_reason || fallback.rank_reason || existing.rank_reason || options.rank_reason || '',
                        query: candidateStock.query || fallback.query || existing.query || options.query || '',
                        price: candidateStock.price ?? fallback.price ?? existing.price ?? null,
                        change_pct: candidateStock.change_pct ?? fallback.change_pct ?? existing.change_pct ?? null,
                        updated_at: candidateStock.updated_at || candidateStock.generated_at || candidateStock.timestamp || options.updated_at || existing.updated_at || '',
                        source_context: sourceContext,
                    };
                };
            const selectedItem = buildItem(stock, {
                code: normalizedCode,
                name: stock.name,
                source,
                sourceLabel,
                context_type: options.context_type,
                sector_name: options.sector_name,
                rank_reason: options.rank_reason,
                query: options.query,
                price: options.price ?? stock.price,
                change_pct: options.change_pct ?? stock.change_pct,
                source_context: options.source_context,
            });
            const nextItems = [selectedItem];
            const seen = new Set([selectedItem.code]);
            for (const candidate of pool) {
                const candidateCode = normalizeCode(candidate?.code);
                if (!candidateCode || seen.has(candidateCode)) continue;
                nextItems.push(buildItem(candidate, { code: candidateCode }));
                seen.add(candidateCode);
            }
            for (const item of current) {
                if (!item?.code || seen.has(item.code)) continue;
                nextItems.push(item);
                seen.add(item.code);
            }
            this._stockContextItems = nextItems.slice(0, 50);
            this._activeStockContextCode = normalizedCode;
            if (this.StockWorkbenchState && typeof this.StockWorkbenchState === 'object') {
                this.StockWorkbenchState.contextList = this._stockContextItems.map((item) => ({ ...item }));
                this.StockWorkbenchState.selectedSymbol = {
                    ...(this.StockWorkbenchState.selectedSymbol || {}),
                    code: selectedItem.code,
                    name: selectedItem.name,
                    asset_type: 'stock',
                    market: 'A股',
                };
            }
            this._renderStockContextList();
        },

        _stockContextSourceLabel(source) {
            const value = String(source || '').trim();
            const normalized = value.toLowerCase();
            if (/iwencai|问财/i.test(value)) return '问财';
            if (/sector|heatmap|板块|local_stock_daily/i.test(value)) return '板块';
            if (/(^|[:_\-\s])(signal|ai|qlib)([:_\-\s]|$)|信号/i.test(normalized)) return 'AI信号';
            if (/opportunity|matrix|datahub/i.test(value)) return '机会池';
            if (/watchlist|自选/i.test(value)) return '自选';
            if (/news|hotspot|topic/i.test(value)) return '情报';
            if (/search/i.test(value)) return '搜索';
            if (/stock-context-list/i.test(value)) return '上下文';
            return value || '来源';
        },

        _bindStockContextList() {
            if (typeof document === 'undefined') return;
            const list = document.getElementById('stock-context-list');
            if (!list || list.dataset.bound === '1') return;
            list.dataset.bound = '1';
            list.addEventListener('click', (event) => {
                const button = event.target.closest('[data-stock-context-code]');
                if (!button) return;
                event.preventDefault();
                const code = button.dataset.stockContextCode;
                if (!code) return;
                const item = (this._stockContextItems || []).find((entry) => entry.code === code) || { code };
                const contextList = Array.isArray(this._stockContextItems)
                    ? this._stockContextItems
                    : [];
                void this.openStockDetail(code, {
                    stock: item,
                    source: item.source || 'stock-context-list',
                    sourceLabel: item.sourceLabel,
                    contextList,
                    context_type: item.context_type,
                    sector_name: item.sector_name,
                    rank_reason: item.rank_reason,
                    query: item.query,
                    price: item.price,
                    change_pct: item.change_pct,
                    updated_at: item.updated_at,
                    source_context: item.source_context,
                    preferDirectOpen: true,
                });
            });
        },

        _renderStockContextList() {
            if (typeof document === 'undefined') return;
            const list = document.getElementById('stock-context-list');
            if (!list) return;
            this._bindStockContextList();
            const items = Array.isArray(this._stockContextItems) ? this._stockContextItems.slice(0, 50) : [];
            if (!items.length) {
                list.innerHTML = '<div class="stock-context-empty">暂无上下文股票；从自选、机会池、热点或问财打开股票后会出现在这里</div>';
                return;
            }
            const escape = typeof this.escapeHTML === 'function'
                ? (value) => this.escapeHTML(value)
                : (value) => String(value ?? '');
            list.innerHTML = `
                <div class="stock-context-title">上下文股票</div>
                <div class="stock-context-items">
                    ${items.map((item) => {
                        const active = item.code === this._activeStockContextCode ? ' is-active' : '';
                        const ariaCurrent = item.code === this._activeStockContextCode ? ' aria-current="true"' : '';
                        const price = item.price != null ? `<span class="stock-context-price">${escape(item.price)}</span>` : '';
                        const reason = [item.rank_reason, item.query, item.sector_name].filter(Boolean).join(' · ');
                        return `<button type="button" class="stock-context-item${active}"${ariaCurrent} data-stock-context-code="${escape(item.code)}" data-code="${escape(item.code)}" title="${escape(reason || item.sourceLabel || '')}">
                            <span class="stock-context-main">
                                <strong>${escape(item.name || item.code)}</strong>
                                <span>${escape(item.code)}${reason ? ` · ${escape(reason)}` : ''}</span>
                            </span>
                            <span class="stock-context-side">
                                <span class="stock-context-source">${escape(item.sourceLabel || this._stockContextSourceLabel(item.source))}</span>
                                ${price}
                            </span>
                        </button>`;
                    }).join('')}
                </div>
            `;
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
