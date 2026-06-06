/**
 * 情报模块入口
 * 只保留状态、初始化、事件分发和统一加载入口。
 */
(function () {
    'use strict';

    const Intelligence = globalThis.Intelligence || (globalThis.Intelligence = {});

    Object.assign(Intelligence, {
        state: Intelligence.state || {
            loaded: false,
            contextRegistered: false,
            delegatedActionsBound: false,
            iwencaiBound: false,
            iwencaiResult: null,
            iwencaiActionState: {
                pool: [],
                watchlistCodes: [],
                query: '',
            },
        },

        init() {
            if (typeof this.bindIwencai === 'function') {
                this.bindIwencai();
            }
            if (typeof this.bindDelegatedActions === 'function') {
                this.bindDelegatedActions();
            }

            if (!this.state.contextRegistered && typeof App.registerContext === 'function') {
                App.registerContext('intelligence', () => {
                    const summary = this.state.iwencaiResult ? {
                        query: this.state.iwencaiResult.query,
                        total: this.state.iwencaiResult.data?.length || 0,
                        sample: (this.state.iwencaiResult.data || []).slice(0, 5),
                    } : null;
                    return {
                        type: 'intelligence',
                        iwencaiResult: summary,
                        currentTab: 'intelligence',
                        pageDesc: '情报页：市场情绪、新闻流、板块热力图、热点概念、问财自然语言选股、AI 信号候选池',
                    };
                });
                this.state.contextRegistered = true;
            }
        },

        bindDelegatedActions() {
            if (this.state.delegatedActionsBound) return;
            this.state.delegatedActionsBound = true;

            document.addEventListener('click', (e) => {
                const newsTag = e.target.closest('[data-intel-action="open-news-stock"]');
                if (newsTag) {
                    e.preventDefault();
                    const code = typeof newsTag.dataset.code === 'string' ? newsTag.dataset.code.trim() : '';
                    if (code && typeof App.openStockDetail === 'function') {
                        App.openStockDetail(code, { source: 'intelligence:news-tag' });
                    }
                    return;
                }

                const hotspot = e.target.closest('[data-intel-action="query-hotspot"]');
                if (hotspot) {
                    e.preventDefault();
                    const concept = typeof hotspot.dataset.concept === 'string' ? hotspot.dataset.concept.trim() : '';
                    if (concept && typeof App.emit === 'function') {
                        App.emit('hotspot:query-iwencai', { concept });
                    }
                    return;
                }

                const sendToScreenerButton = e.target.closest('[data-intel-action="iwencai-send-screener"]');
                if (sendToScreenerButton) {
                    e.preventDefault();
                    if (this.state.iwencaiActionState.pool.length > 0 && typeof App.emit === 'function') {
                        App.emit('iwencai:send-to-screener', {
                            pool: [...this.state.iwencaiActionState.pool],
                            query: this.state.iwencaiActionState.query,
                        });
                    }
                    return;
                }

                const analyzeButton = e.target.closest('[data-intel-action="iwencai-analyze"]');
                if (analyzeButton) {
                    e.preventDefault();
                    if (typeof App.emit === 'function') {
                        App.emit('iwencai:analyze', {
                            query: this.state.iwencaiActionState.query,
                            data: this.getLastResult(),
                        });
                    }
                    return;
                }

                const addWatchlistButton = e.target.closest('[data-intel-action="iwencai-add-watchlist"]');
                if (addWatchlistButton) {
                    e.preventDefault();
                    if (this.state.iwencaiActionState.watchlistCodes.length > 0 && typeof App.addAllToWatchlist === 'function') {
                        App.addAllToWatchlist([...this.state.iwencaiActionState.watchlistCodes]);
                    }
                    return;
                }

                const timelineFocusButton = e.target.closest('[data-intel-action="timeline-focus"]');
                if (timelineFocusButton) {
                    e.preventDefault();
                    const date = typeof timelineFocusButton.dataset.date === 'string' ? timelineFocusButton.dataset.date.trim() : '';
                    if (date && typeof App.emit === 'function') {
                        App.emit('timeline:focus', { date });
                    }
                    return;
                }

                const mimoButton = e.target.closest('.qlib-btn-mimo');
                if (mimoButton) {
                    e.preventDefault();
                    e.stopPropagation();
                    const { code, name, score, industry } = mimoButton.dataset;
                    const msg = `AI 信号今天给 ${name}(${code}) 打出了 ${score} 的候选分，属于 ${industry} 板块。请帮我分析：\n1. 这只票最近有没有股东减持、负面研报或重大风险？\n2. 当前技术面是否支持介入？\n3. 如果买入，建议的止损位和目标位是多少？`;
                    if (typeof App.emit === 'function') {
                        App.emit('iwencai:analyze', { query: msg, data: null });
                    }
                    return;
                }

                const qlibRow = e.target.closest('.qlib-row');
                if (qlibRow && !e.target.closest('.qlib-btn')) {
                    const code = typeof qlibRow.dataset.code === 'string' ? qlibRow.dataset.code.trim() : '';
                    if (code && typeof App.openStockDetail === 'function') {
                        App.openStockDetail(code, { source: 'intelligence:signal-row' });
                    }
                }
            });
        },

        async load() {
            const loaders = [
                this.loadSentiment,
                this.loadNews,
                this.loadHeatmap,
                this.loadHotspot,
                this.loadMLPredictions,
                this.loadSignalBar,
            ].filter((fn) => typeof fn === 'function');

            if (this.state.loaded || loaders.length === 0) return;
            if (this.state.loadingPromise) return this.state.loadingPromise;

            this.state.loadingPromise = Promise.allSettled(loaders.map((fn) => fn.call(this)))
                .then((results) => {
                    this.state.loaded = results.some((result) => result.status === 'fulfilled');
                    return results;
                })
                .finally(() => {
                    this.state.loadingPromise = null;
                });
            return this.state.loadingPromise;
        },

        getLastResult() {
            return this.state.iwencaiResult;
        },
    });

    window.Intelligence = Intelligence;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            if (globalThis.__AUTH_GATE_REQUIRED__ === true) return;
            Intelligence.init();
        });
    } else if (globalThis.__AUTH_GATE_REQUIRED__ !== true) {
        Intelligence.init();
    }
})();
