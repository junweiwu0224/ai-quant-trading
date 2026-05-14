(function attachBusinessAdapter(global) {
    'use strict';

    const INTENT_TYPES = Object.freeze({
        OPEN_STOCK_DETAIL: 'stock:open-detail',
        ADD_TO_WATCHLIST: 'watchlist:add-stock',
        REMOVE_FROM_WATCHLIST: 'watchlist:remove-stock',
        OPEN_PAPER_BUY: 'paper-trade:open-buy',
    });

    const PAPER_SUB_TAB_CANDIDATES = Object.freeze(['console', 'trade']);

    function isPlainObject(value) {
        return Object.prototype.toString.call(value) === '[object Object]';
    }

    function createAdapterError(message, code) {
        const error = new Error(message);
        error.name = 'BusinessAdapterError';
        if (code) {
            error.code = code;
        }
        return error;
    }

    function normalizePayload(value) {
        const safeValue = isPlainObject(value) ? value : {};
        const stock = isPlainObject(safeValue.stock) ? safeValue.stock : {};
        const payload = isPlainObject(safeValue.payload) ? safeValue.payload : {};
        const input = isPlainObject(safeValue.input) ? safeValue.input : {};
        const builtPayload = isPlainObject(safeValue.builtPayload) ? safeValue.builtPayload : {};
        const builtStock = isPlainObject(builtPayload.stock) ? builtPayload.stock : {};
        const normalizedCode = typeof safeValue.code === 'string' && safeValue.code.trim()
            ? safeValue.code.trim()
            : (typeof stock.code === 'string' && stock.code.trim()
                ? stock.code.trim()
                : (typeof payload.code === 'string' && payload.code.trim()
                    ? payload.code.trim()
                    : (typeof input.code === 'string' && input.code.trim()
                        ? input.code.trim()
                        : (typeof builtStock.code === 'string' && builtStock.code.trim() ? builtStock.code.trim() : ''))));
        const normalizedPrice = Number.isFinite(Number(safeValue.price))
            ? Number(safeValue.price)
            : (Number.isFinite(Number(stock.price))
                ? Number(stock.price)
                : (Number.isFinite(Number(payload.price))
                    ? Number(payload.price)
                    : (Number.isFinite(Number(input.price))
                        ? Number(input.price)
                        : (Number.isFinite(Number(builtStock.price)) ? Number(builtStock.price) : null))));

        return {
            code: normalizedCode,
            price: normalizedPrice,
            activeTab: typeof safeValue.activeTab === 'string' && safeValue.activeTab.trim() ? safeValue.activeTab.trim() : null,
        };
    }

    function warnUnavailable(message, detail) {
        if (global.console && typeof global.console.warn === 'function') {
            global.console.warn('[BusinessAdapter]', message, detail || null);
        }
    }

    function requireCode(payload, intentType) {
        if (!payload.code) {
            throw createAdapterError(`Intent ${intentType} requires payload.code`, 'PAYLOAD_CODE_REQUIRED');
        }
    }

    function requireApp() {
        if (!global.App) {
            warnUnavailable('window.App is not available');
            throw createAdapterError('window.App is not available', 'APP_UNAVAILABLE');
        }

        return global.App;
    }

    function requireWatchlistCommit(methodName) {
        const app = requireApp();
        if (typeof app[methodName] !== 'function') {
            warnUnavailable(`window.App.${methodName} is not available`);
            throw createAdapterError(`window.App.${methodName} is not available`, 'APP_WATCHLIST_COMMIT_UNAVAILABLE');
        }

        return app[methodName].bind(app);
    }

    function requireStockDetail() {
        if (!global.StockDetail || typeof global.StockDetail.open !== 'function') {
            warnUnavailable('window.StockDetail.open is not available');
            throw createAdapterError('window.StockDetail.open is not available', 'STOCK_DETAIL_UNAVAILABLE');
        }

        return global.StockDetail;
    }

    function dispatchInputEvent(element) {
        element.dispatchEvent(new Event('input', { bubbles: true }));
        element.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function clickElement(element) {
        if (!element) {
            return false;
        }

        element.click();
        return true;
    }

    function switchMainTab(tabName) {
        const app = requireApp();
        if (typeof app.switchTab !== 'function') {
            warnUnavailable('window.App.switchTab is not available');
            throw createAdapterError('window.App.switchTab is not available', 'APP_SWITCH_TAB_UNAVAILABLE');
        }

        app.switchTab(tabName);
    }

    function activateStockSubTab(activeTab) {
        if (!activeTab) {
            return false;
        }

        const targetButton = document.querySelector(`#tab-stock .sd-chart-tabs .sd-tab[data-period="${activeTab}"]`);
        return clickElement(targetButton);
    }

    function activatePaperSubTab(activeTab) {
        if (!activeTab) {
            return false;
        }

        const targetButton = document.querySelector(`#paper-sub-tabs .paper-sub-tab[data-tab="${activeTab}"]`);
        return clickElement(targetButton);
    }

    async function waitForElement(selector, attempts) {
        for (let index = 0; index < attempts; index += 1) {
            const element = document.querySelector(selector);
            if (element) {
                return element;
            }

            await new Promise((resolve) => {
                global.requestAnimationFrame(resolve);
            });
        }

        return null;
    }

    function ensurePaperTradingAvailable() {
        if (!global.PaperTrading) {
            warnUnavailable('window.PaperTrading is not available');
            throw createAdapterError('window.PaperTrading is not available', 'PAPER_TRADING_UNAVAILABLE');
        }

        return global.PaperTrading;
    }

    async function prefillPaperTradeForm(payload) {
        ensurePaperTradingAvailable();

        const codeInput = await waitForElement('#pt-code', 4);
        if (!codeInput) {
            warnUnavailable('paper trade code input #pt-code is not available');
            throw createAdapterError('paper trade code input is not available', 'PAPER_TRADE_CODE_INPUT_UNAVAILABLE');
        }

        codeInput.value = payload.code;
        dispatchInputEvent(codeInput);

        if (global.PaperTrading && typeof global.PaperTrading._loadQuotePreview === 'function') {
            global.PaperTrading._loadQuotePreview(payload.code);
        }

        const directionSelect = document.getElementById('pt-direction');
        if (directionSelect) {
            directionSelect.value = 'buy';
            dispatchInputEvent(directionSelect);
        }

        if (payload.price !== null) {
            const orderTypeSelect = document.getElementById('pt-order-type');
            if (orderTypeSelect && orderTypeSelect.value === 'market') {
                orderTypeSelect.value = 'limit';
                dispatchInputEvent(orderTypeSelect);
            }

            const priceInput = document.getElementById('pt-price');
            if (priceInput) {
                priceInput.value = String(payload.price);
                dispatchInputEvent(priceInput);
            }
        }
    }

    async function openStockDetail(contextOrPayload) {
        const payload = normalizePayload(contextOrPayload);
        requireCode(payload, INTENT_TYPES.OPEN_STOCK_DETAIL);

        const stockDetail = requireStockDetail();
        switchMainTab('stock');
        await stockDetail.open(payload.code);
        activateStockSubTab(payload.activeTab);

        return {
            ok: true,
            code: payload.code,
        };
    }

    async function addToWatchlist(contextOrPayload) {
        const payload = normalizePayload(contextOrPayload);
        requireCode(payload, INTENT_TYPES.ADD_TO_WATCHLIST);

        const commitWatchlistAdd = requireWatchlistCommit('_commitWatchlistAdd');
        return commitWatchlistAdd(payload.code);
    }

    async function removeFromWatchlist(contextOrPayload) {
        const payload = normalizePayload(contextOrPayload);
        requireCode(payload, INTENT_TYPES.REMOVE_FROM_WATCHLIST);

        const commitWatchlistRemove = requireWatchlistCommit('_commitWatchlistRemove');
        return commitWatchlistRemove(payload.code);
    }

    async function openPaperBuy(contextOrPayload) {
        const payload = normalizePayload(contextOrPayload);
        requireCode(payload, INTENT_TYPES.OPEN_PAPER_BUY);

        switchMainTab('sim');
        const activated = activatePaperSubTab(payload.activeTab) || activateDefaultPaperSubTab();
        await prefillPaperTradeForm(payload);

        if (!activated) {
            warnUnavailable('paper trading sub tab button was not found');
        }

        return {
            ok: true,
            code: payload.code,
        };
    }

    function activateDefaultPaperSubTab() {
        return PAPER_SUB_TAB_CANDIDATES.some((tabName) => activatePaperSubTab(tabName));
    }

    global.BusinessAdapter = Object.freeze({
        intentTypes: Object.freeze({ ...INTENT_TYPES }),
        openStockDetail,
        addToWatchlist,
        removeFromWatchlist,
        openPaperBuy,
    });
})(window);
