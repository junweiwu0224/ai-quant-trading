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
            marketLoaded: false,
            contextRegistered: false,
            delegatedActionsBound: false,
            iwencaiBound: false,
            iwencaiResult: null,
            iwencaiActionState: {
                pool: [],
                watchlistCodes: [],
                query: '',
                source_context: null,
                contextList: [],
                candidates: [],
                viewModel: null,
            },
            loadedModules: {},
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

        _normalizeIwencaiActionName(action) {
            const aliases = {
                add_to_watchlist: 'add_watchlist',
                ai_analyze: 'analyze',
                ask_ai: 'ask_ai',
                create_backtest: 'draft_backtest',
                create_basket: 'create_basket',
                draft_backtest: 'draft_backtest',
                explain: 'ask_ai',
                open_stock: 'open_stock',
                send_screener: 'send_screener',
                send_to_screener: 'send_screener',
            };
            const raw = String(action || '')
                .trim()
                .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
                .replace(/[-\s:]+/g, '_')
                .toLowerCase();
            return aliases[raw] || raw;
        },

        _matchesIwencaiRequestGeneration(element = null) {
            if (!element?.dataset?.requestGeneration) return true;
            const expected = Number(element.dataset.requestGeneration);
            if (!Number.isFinite(expected) || expected <= 0) return true;
            const actionState = this.state.iwencaiActionState || {};
            const current = Number(actionState.requestGeneration || actionState.source_context?.request_generation || 0);
            return current > 0 && current === expected;
        },

        _canRunIwencaiAction(action, { requiresPool = false, element = null } = {}) {
            if (!this._matchesIwencaiRequestGeneration(element)) return false;
            const actionState = this.state.iwencaiActionState || {};
            const viewModel = actionState.viewModel || {};
            const normalized = this._normalizeIwencaiActionName(action);
            const defaultActions = ['open_stock', 'add_watchlist', 'send_screener', 'analyze', 'ask_ai', 'create_basket', 'draft_backtest'];
            const rawActions = Array.isArray(viewModel.actions) && viewModel.actions.length ? viewModel.actions : defaultActions;
            const allowed = new Set(rawActions.map((item) => this._normalizeIwencaiActionName(
                item && typeof item === 'object' ? (item.id || item.action || item.type || item.name) : item
            )));
            if (!allowed.has(normalized)) return false;
            const blockedTaskStatuses = new Set([
                'failed',
                'no_match',
                'partial_result',
                'degraded_data',
                'needs_disambiguation',
                'requires_confirmation',
            ]);
            if (blockedTaskStatuses.has(viewModel.status)) {
                return !requiresPool;
            }
            const blockedSourceStatuses = new Set([
                'failed',
                'unavailable',
                'provider_unavailable',
                'rate_limited',
                'invalid_response',
                'invalid_provider_response',
                'permission_denied',
                'request_failed',
                'partial_source_failure',
                'stale_cache',
                'offline_fallback',
            ]);
            const sourceContext = actionState.source_context || viewModel.source_context || {};
            const rawResponse = viewModel.raw_response || {};
            const sourceStatus = rawResponse.source_status && typeof rawResponse.source_status === 'object'
                ? rawResponse.source_status
                : {};
            const providerValues = [
                rawResponse.provider_status,
                rawResponse.failure_type,
                rawResponse.error_type,
                sourceStatus.status,
                sourceStatus.type,
                sourceStatus.provider_status,
                sourceStatus.cache_status,
                sourceContext.data_status,
                sourceContext.failure_type,
                sourceContext.provider_status,
                sourceContext.cache_status,
            ].map((value) => String(value || '').trim()).filter(Boolean);
            if (['add_watchlist', 'send_screener', 'create_basket', 'draft_backtest'].includes(normalized)
                && providerValues.some((value) => blockedSourceStatuses.has(value))) {
                return false;
            }
            if (requiresPool) {
                return Array.isArray(actionState.pool) && actionState.pool.length > 0;
            }
            return true;
        },

        _iwencaiCandidateByCode(code) {
            const cleanCode = String(code || '').trim();
            if (!cleanCode) return null;
            const actionState = this.state.iwencaiActionState || {};
            return (actionState.candidates || []).find((item) => item.code === cleanCode) || null;
        },

        _iwencaiRowSourceContext(candidate) {
            const actionState = this.state.iwencaiActionState || {};
            const sourceContext = actionState.source_context || {};
            const rowEvidence = candidate?.rowEvidence?.raw || candidate?.row?.candidate_provenance || candidate?.candidate_provenance || null;
            return {
                ...sourceContext,
                row_evidence: rowEvidence,
                candidate_provenance: rowEvidence,
                row_evidence_id: candidate?.rowEvidence?.row_evidence_id || rowEvidence?.row_id || '',
                row_evidence_status: candidate?.rowEvidence?.status || rowEvidence?.validation_status || 'legacy_unverified',
                rank_reason: candidate?.rank_reason || sourceContext.rank_reason || `问财条件: ${actionState.query || candidate?.code || ''}`,
            };
        },

        _canRunIwencaiRowAction(action, code, element = null, { requiresVerified = false } = {}) {
            const candidate = this._iwencaiCandidateByCode(code);
            if (!candidate) return false;
            const actionState = this.state.iwencaiActionState || {};
            const rowEvidence = candidate.rowEvidence || {};
            const rowEvidenceId = rowEvidence.row_evidence_id || candidate.row?.candidate_provenance?.row_id || '';
            const resultPoolId = rowEvidence.result_pool_id || actionState.source_context?.result_pool_id || '';
            if (element?.dataset) {
                if (!this._matchesIwencaiRequestGeneration(element)) return false;
                const elementPoolId = String(element.dataset.resultPoolId || '').trim();
                const elementEvidenceId = String(element.dataset.rowEvidenceId || '').trim();
                if (elementPoolId && resultPoolId && elementPoolId !== resultPoolId) return false;
                if (elementEvidenceId && rowEvidenceId && elementEvidenceId !== rowEvidenceId) return false;
            }
            if (!this._canRunIwencaiAction(action, { requiresPool: requiresVerified })) return false;
            if (requiresVerified && !rowEvidence.actionable) return false;
            return true;
        },

        _buildTopicSourceContext({ concept = '', query = '', source = '', pool = [], action = '' } = {}) {
            const cleanConcept = String(concept || '').trim();
            const cleanSource = String(source || '').trim() || 'intelligence:hotspot';
            const isNewsTopic = cleanSource.includes('news-topic');
            const sourceLabel = isNewsTopic ? '新闻主题' : '热点主题';
            const cleanQuery = String(query || '').trim() || (cleanConcept ? `${sourceLabel}: ${cleanConcept}` : `${sourceLabel}候选池`);
            const candidateCodes = Array.isArray(pool)
                ? [...new Set(pool.map((code) => String(code || '').trim()).filter(Boolean))].slice(0, 50)
                : [];
            const rankReason = cleanQuery === cleanConcept && cleanConcept ? `${sourceLabel}: ${cleanConcept}` : cleanQuery;
            const context = {
                source: cleanSource,
                sourceLabel,
                context_type: isNewsTopic ? 'news_topic' : 'hotspot',
                concept: cleanConcept,
                raw_query: cleanConcept || cleanQuery,
                query: cleanQuery,
                action: action || 'query_iwencai',
                result_pool_id: `${cleanSource}:${cleanConcept || 'topic'}`,
                rank_reason: rankReason,
            };
            if (candidateCodes.length > 0) {
                context.result_total = candidateCodes.length;
                context.candidate_codes = candidateCodes;
            }
            return context;
        },

        bindDelegatedActions() {
            if (this.state.delegatedActionsBound) return;
            this.state.delegatedActionsBound = true;

            document.addEventListener('click', (e) => {
                const newsTag = e.target.closest('[data-intel-action="open-news-stock"]');
                if (newsTag) {
                    e.preventDefault();
                    const code = typeof newsTag.dataset.code === 'string' ? newsTag.dataset.code.trim() : '';
                    const name = typeof newsTag.dataset.name === 'string' ? newsTag.dataset.name.trim() : '';
                    if (code && typeof App.openStockDetail === 'function') {
                        const options = { source: 'intelligence:news-tag' };
                        if (name) options.name = name;
                        App.openStockDetail(code, options);
                    }
                    return;
                }

                const hotspot = e.target.closest('[data-intel-action="query-hotspot"]');
                if (hotspot) {
                    e.preventDefault();
                    const concept = typeof hotspot.dataset.concept === 'string' ? hotspot.dataset.concept.trim() : '';
                    const source = typeof hotspot.dataset.source === 'string' && hotspot.dataset.source.trim()
                        ? hotspot.dataset.source.trim()
                        : 'intelligence:hotspot';
                    if (concept && typeof App.emit === 'function') {
                        App.emit('hotspot:query-iwencai', {
                            concept,
                            source,
                            source_context: this._buildTopicSourceContext({
                                concept,
                                query: concept,
                                source,
                                action: 'query_iwencai',
                            }),
                        });
                    }
                    return;
                }

                const topicScreenerButton = e.target.closest('[data-intel-action="send-topic-screener"]');
                if (topicScreenerButton) {
                    e.preventDefault();
                    const pool = typeof topicScreenerButton.dataset.pool === 'string'
                        ? topicScreenerButton.dataset.pool.split(',').map((code) => code.trim()).filter(Boolean)
                        : [];
                    const concept = typeof topicScreenerButton.dataset.concept === 'string' ? topicScreenerButton.dataset.concept.trim() : '';
                    const query = typeof topicScreenerButton.dataset.query === 'string' && topicScreenerButton.dataset.query.trim()
                        ? topicScreenerButton.dataset.query.trim()
                        : concept
                            ? `新闻主题: ${concept}`
                            : '新闻主题候选池';
                    if (pool.length > 0 && typeof App.emit === 'function') {
                        const source = typeof topicScreenerButton.dataset.source === 'string' && topicScreenerButton.dataset.source.trim()
                            ? topicScreenerButton.dataset.source.trim()
                            : 'intelligence:news-topic-board';
                        App.emit('iwencai:send-to-screener', {
                            pool,
                            query,
                            source_context: this._buildTopicSourceContext({
                                concept,
                                query,
                                source,
                                pool,
                                action: 'send_screener',
                            }),
                        });
                    }
                    return;
                }

                const sendToScreenerButton = e.target.closest('[data-intel-action="iwencai-send-screener"]');
                if (sendToScreenerButton) {
                    e.preventDefault();
                    if (this._canRunIwencaiAction('send_screener', { requiresPool: true, element: sendToScreenerButton }) && this.state.iwencaiActionState.pool.length > 0 && typeof App.emit === 'function') {
                        App.emit('iwencai:send-to-screener', {
                            pool: [...this.state.iwencaiActionState.pool],
                            query: this.state.iwencaiActionState.query,
                            source_context: this.state.iwencaiActionState.source_context || null,
                        });
                    }
                    return;
                }

                const bucketButton = e.target.closest('[data-intel-action="iwencai-select-bucket"]');
                if (bucketButton) {
                    e.preventDefault();
                    const bucketId = typeof bucketButton.dataset.bucketId === 'string' ? bucketButton.dataset.bucketId.trim() : '';
                    if (bucketId && typeof this.selectIwencaiBucket === 'function') {
                        this.selectIwencaiBucket(bucketId);
                    }
                    return;
                }

                const openStockButton = e.target.closest('[data-intel-action="iwencai-open-stock"]');
                if (openStockButton) {
                    e.preventDefault();
                    const code = typeof openStockButton.dataset.code === 'string' ? openStockButton.dataset.code.trim() : '';
                    if (code && this._canRunIwencaiRowAction('open_stock', code, openStockButton) && typeof App.openStockDetail === 'function') {
                        const actionState = this.state.iwencaiActionState || {};
                        const candidate = (actionState.candidates || []).find((item) => item.code === code) || { code };
                        const sourceContext = this._iwencaiRowSourceContext(candidate);
                        App.openStockDetail(code, {
                            stock: candidate,
                            name: candidate.name,
                            source: 'iwencai',
                            sourceLabel: '问财',
                            context_type: 'iwencai',
                            query: actionState.query,
                            rank_reason: sourceContext.rank_reason || `问财条件: ${actionState.query || code}`,
                            contextList: actionState.contextList || [],
                            price: candidate.price,
                            change_pct: candidate.changePct,
                            source_context: sourceContext,
                            preferDirectOpen: true,
                        });
                    }
                    return;
                }

                const analyzeButton = e.target.closest('[data-intel-action="iwencai-analyze"]');
                if (analyzeButton) {
                    e.preventDefault();
                    if (this._canRunIwencaiAction('analyze', { element: analyzeButton }) && typeof App.emit === 'function') {
                        App.emit('iwencai:analyze', {
                            query: this.state.iwencaiActionState.query,
                            data: this.getLastResult(),
                            source_context: this.state.iwencaiActionState.source_context || null,
                        });
                    }
                    return;
                }

                const askAiButton = e.target.closest('[data-intel-action="iwencai-ask-ai"]');
                if (askAiButton) {
                    e.preventDefault();
                    const code = typeof askAiButton.dataset.code === 'string' ? askAiButton.dataset.code.trim() : '';
                    const actionState = this.state.iwencaiActionState || {};
                    const candidate = (actionState.candidates || []).find((item) => item.code === code) || null;
                    if (candidate && (this._canRunIwencaiRowAction('ask_ai', code, askAiButton) || this._canRunIwencaiRowAction('analyze', code, askAiButton)) && typeof App.emit === 'function') {
                        const stockText = candidate ? `${candidate.name}(${candidate.code})` : code;
                        App.emit('iwencai:analyze', {
                            query: `请解释 ${stockText} 为什么出现在问财条件“${actionState.query || ''}”里，并列出支持证据、反证和缺失数据。`,
                            data: this.getLastResult(),
                            source_context: this._iwencaiRowSourceContext(candidate),
                        });
                    }
                    return;
                }

                const addWatchlistButton = e.target.closest('[data-intel-action="iwencai-add-watchlist"]');
                if (addWatchlistButton) {
                    e.preventDefault();
                    if (this._canRunIwencaiAction('add_watchlist', { requiresPool: true, element: addWatchlistButton }) && this.state.iwencaiActionState.watchlistCodes.length > 0 && typeof App.addAllToWatchlist === 'function') {
                        App.addAllToWatchlist([...this.state.iwencaiActionState.watchlistCodes]);
                    }
                    return;
                }

                const addOneWatchlistButton = e.target.closest('[data-intel-action="iwencai-add-one-watchlist"]');
                if (addOneWatchlistButton) {
                    e.preventDefault();
                    const code = typeof addOneWatchlistButton.dataset.code === 'string' ? addOneWatchlistButton.dataset.code.trim() : '';
                    if (code && this._canRunIwencaiRowAction('add_watchlist', code, addOneWatchlistButton, { requiresVerified: true }) && typeof App.addToWatchlist === 'function') {
                        const candidate = this._iwencaiCandidateByCode(code);
                        App.addToWatchlist(code, {
                            source: 'iwencai:add-watchlist',
                            metadata: this._iwencaiRowSourceContext(candidate),
                        });
                    }
                    return;
                }

                const basketButton = e.target.closest('[data-intel-action="iwencai-create-basket"]');
                if (basketButton) {
                    e.preventDefault();
                    const actionState = this.state.iwencaiActionState || {};
                    if (this._canRunIwencaiAction('create_basket', { requiresPool: true, element: basketButton }) && typeof App.emit === 'function') {
                        App.emit('iwencai:create-basket', {
                            query: actionState.query,
                            candidates: actionState.actionableCandidates || [],
                            source_context: actionState.source_context || null,
                        });
                    }
                    return;
                }

                const backtestDraftButton = e.target.closest('[data-intel-action="iwencai-draft-backtest"]');
                if (backtestDraftButton) {
                    e.preventDefault();
                    const actionState = this.state.iwencaiActionState || {};
                    if (this._canRunIwencaiAction('draft_backtest', { requiresPool: true, element: backtestDraftButton }) && typeof App.emit === 'function') {
                        App.emit('iwencai:draft-backtest', {
                            query: actionState.query,
                            candidates: actionState.actionableCandidates || [],
                            source_context: actionState.source_context || null,
                        });
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
                    const msg = `AI 信号今天给 ${name}(${code}) 打出了 ${score} 的候选分，属于 ${industry} 板块。请帮我做模拟盘观察计划：\n1. 先核对最近是否有股东减持、负面研报或重大风险点；\n2. 判断当前技术面和行业热度是否支持继续观察；\n3. 给出验证条件、失效条件和需要补充的数据。仅供观察，不要给实盘下单建议。`;
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
            const marketLoaderDefs = [
                ['sentiment', this.loadSentiment],
                ['news', this.loadNews],
                ['heatmap', this.loadHeatmap],
                ['hotspot', this.loadHotspot],
            ].filter(([, fn]) => typeof fn === 'function');
            const backgroundLoaderDefs = [
                ['signals', this.loadMLPredictions],
                ['signalBar', this.loadSignalBar],
            ].filter(([, fn]) => typeof fn === 'function');
            const loadedModules = this.state.loadedModules || (this.state.loadedModules = {});
            const pendingMarketLoaders = marketLoaderDefs.filter(([name]) => loadedModules[name] !== true);

            if (!this.state.backgroundLoadingPromise) {
                const pendingBackgroundLoaders = backgroundLoaderDefs.filter(([name]) => loadedModules[name] !== true);
                if (pendingBackgroundLoaders.length > 0) {
                    this.state.backgroundLoadingPromise = Promise.allSettled(pendingBackgroundLoaders.map(([, fn]) => fn.call(this)))
                        .then((results) => {
                            results.forEach((result, index) => {
                                const [name] = pendingBackgroundLoaders[index];
                                if (result.status === 'fulfilled') {
                                    loadedModules[name] = true;
                                }
                            });
                            this.state.loaded = [...marketLoaderDefs, ...backgroundLoaderDefs].every(([name]) => loadedModules[name] === true);
                            return results;
                        })
                        .finally(() => {
                            this.state.backgroundLoadingPromise = null;
                        });
                }
            }

            if (this.state.marketLoaded && pendingMarketLoaders.length === 0) {
                this.state.marketLoaded = true;
                this.state.loaded = [...marketLoaderDefs, ...backgroundLoaderDefs].every(([name]) => loadedModules[name] === true);
                return [];
            }
            if (pendingMarketLoaders.length === 0) {
                this.state.marketLoaded = true;
                this.state.loaded = [...marketLoaderDefs, ...backgroundLoaderDefs].every(([name]) => loadedModules[name] === true);
                return [];
            }
            if (this.state.loadingPromise) return this.state.loadingPromise;

            this.state.loadingPromise = Promise.allSettled(pendingMarketLoaders.map(([, fn]) => fn.call(this)))
                .then((results) => {
                    results.forEach((result, index) => {
                        const [name] = pendingMarketLoaders[index];
                        if (result.status === 'fulfilled') {
                            loadedModules[name] = true;
                        }
                    });
                    this.state.marketLoaded = marketLoaderDefs.every(([name]) => loadedModules[name] === true);
                    this.state.loaded = [...marketLoaderDefs, ...backgroundLoaderDefs].every(([name]) => loadedModules[name] === true);
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
