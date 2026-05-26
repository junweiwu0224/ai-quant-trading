(function attachAppBootstrap(global) {
    'use strict';

    const App = global.App;
    if (!App) {
        return;
    }

    Object.assign(App, {
        init() {
            this._installGlobalRuntimeErrorHandlers();
            this._initTheme();
            document.body.classList.add('auth-required');
            void this._bootstrapAuthAndApp();
        },

        async _bootstrapAuthAndApp() {
            const account = await this._loadAccountState?.();
            if (!account) {
                this._setAuthGate(true, { required: true });
                return;
            }
            this._setAuthGate(false);
            this._startAuthenticatedApp();
        },

        _startAuthenticatedApp() {
            if (!this._appShellBound) {
                this._appShellBound = true;

                if (globalThis.ENABLE_WORKSPACE_V2 !== false) {
                    this._initV2();
                }

                this.bindTabs();
                this.bindStaticActions();
                this._initTableSorting();
                this._initCommandPalette();
                this._initGlobalShortcuts();
                this._initPWA();

                document.addEventListener('visibilitychange', () => {
                    if (document.hidden) {
                        PollManager.pauseAll();
                    } else {
                        PollManager.resumeAll();
                    }
                });

                document.addEventListener('click', (e) => {
                    const detailActionButton = e.target.closest('[data-stock-action]');
                    if (detailActionButton) {
                        const actionType = detailActionButton.dataset.stockAction;
                        const code = typeof detailActionButton.dataset.code === 'string' ? detailActionButton.dataset.code.trim() : '';
                        if (!code) {
                            return;
                        }

                        e.preventDefault();

                        if (actionType === 'open-detail') {
                            this.openStockDetail(code, {
                                source: 'app:offcanvas:open-detail',
                            }).then((result) => {
                                if (result && result.ok) {
                                    this.closeOffcanvas();
                                }
                            });
                            return;
                        }

                        if (actionType === 'add-watchlist') {
                            this.addToWatchlist(code, {
                                source: 'app:offcanvas:add-watchlist',
                            });
                            return;
                        }
                    }

                    const activeOrderButton = e.target.closest('[data-app-action="cancel-active-order"]');
                    if (activeOrderButton) {
                        const orderId = typeof activeOrderButton.dataset.orderId === 'string' ? activeOrderButton.dataset.orderId.trim() : '';
                        if (!orderId) {
                            return;
                        }

                        e.preventDefault();
                        this.cancelActiveOrder(orderId);
                        return;
                    }

                    const deleteSimSnapshotButton = e.target.closest('[data-app-action="delete-sim-snapshot"]');
                    if (deleteSimSnapshotButton) {
                        const snapshotId = typeof deleteSimSnapshotButton.dataset.snapshotId === 'string' ? deleteSimSnapshotButton.dataset.snapshotId.trim() : '';
                        if (!snapshotId) {
                            return;
                        }

                        e.preventDefault();
                        this.deleteSimSnapshot(snapshotId);
                        return;
                    }

                    const tabActionLink = e.target.closest('[data-app-action="switch-tab"]');
                    if (tabActionLink) {
                        const tab = typeof tabActionLink.dataset.tab === 'string' ? tabActionLink.dataset.tab.trim() : '';
                        if (!tab) {
                            return;
                        }

                        e.preventDefault();
                        this.switchTab(tab);
                        return;
                    }

                    const link = e.target.closest('.stock-link');
                    if (!link) return;
                    e.preventDefault();
                    const code = link.dataset.code;
                    if (code) {
                        this.syncActiveStockContext(code, null, 'app:stock-link', 'stock-link');
                        this.openStockDetail(code, {
                            source: 'app:stock-link',
                        });
                    }
                });

                window.addEventListener('hashchange', () => this._syncTabFromHash());
                this._syncTabFromHash();
            }

            void this._activateAuthenticatedSession();
        },

        async _activateAuthenticatedSession() {
            this._sessionActive = true;

            if (typeof this.setDefaultDate === 'function') {
                void this.setDefaultDate();
            }
            if (typeof this.loadStockList === 'function') {
                void this.loadStockList();
            }
            if (typeof this.loadBenchmarks === 'function') {
                void this.loadBenchmarks();
            }
            if (typeof this.initSidebar === 'function') {
                this.initSidebar();
            }
            if (typeof this._startMarketRefresh === 'function') {
                this._startMarketRefresh();
            }
            if (!this._watchlistBound) {
                this._watchlistBound = true;
                Watchlist.init();
            }

            if (!this._realtimeUpdateBound) {
                this._realtimeUpdateBound = true;
                RealtimeQuotes.onUpdate((data) => {
                    if (data._status) return;
                    this._updateWatchlistPrices(data);
                });
            }
            RealtimeQuotes.connect();

            if (typeof this.loadOverview === 'function') {
                await this.loadOverview();
            }
            const currentHash = location.hash || '';
            if (currentHash === '#stock') {
                const restoredCode = await this._resolveStockRouteInitialCode();
                if (restoredCode) {
                    this._rememberStockRouteCode(restoredCode);
                    await this.switchTab('stock', { replaceHash: false });
                    return;
                }
            }
            this._syncTabFromHash();
        },

        async _resolveStockRouteInitialCode() {
            const lastCode = typeof this.getLastOpenedStockCode === 'function' ? this.getLastOpenedStockCode() : '';
            if (lastCode) {
                return lastCode;
            }

            const firstCachedCode = (this.watchlistCache || [])[0]?.code || '';
            if (firstCachedCode) {
                return firstCachedCode;
            }

            const watchlist = await this.fetchJSON('/api/watchlist', { silent: true }).catch(() => []);
            if (!Array.isArray(watchlist) || watchlist.length === 0) {
                return '';
            }

            this.watchlistCache = watchlist;
            if (globalThis.Watchlist && typeof Watchlist.render === 'function') {
                Watchlist.render(watchlist);
            }
            if (globalThis.Watchlist && typeof Watchlist.setSelectedItems === 'function') {
                Watchlist.setSelectedItems(watchlist);
            }
            if (typeof this._buildWatchlistIndex === 'function') {
                this._buildWatchlistIndex();
            }

            return watchlist[0]?.code || '';
        },

        _rememberStockRouteCode(code) {
            const normalizedCode = typeof code === 'string' ? code.trim() : '';
            if (!normalizedCode) {
                return;
            }

            this._activeStockCode = normalizedCode;
            try {
                sessionStorage.setItem('last_stock_code', normalizedCode);
            } catch {
                // ignore storage failures
            }
        },

        _pauseAuthenticatedSession() {
            this._sessionActive = false;
            if (typeof this._stopMarketRefresh === 'function') {
                this._stopMarketRefresh();
            }
            if (globalThis.RealtimeQuotes && typeof RealtimeQuotes.disconnect === 'function') {
                RealtimeQuotes.disconnect({ suppressReconnect: true });
            }
            if (typeof PollManager !== 'undefined' && PollManager && typeof PollManager.destroy === 'function') {
                PollManager.destroy();
            }
            this._overviewLoaded = false;
            this._loadingOverview = false;
            this._tabCache = {};
            this.watchlistCache = [];
            this.stockCache = null;
            this.paperMultiSearch = null;
            this._watchlistRowMap = null;
            this._researchSession = { code: '', startDate: '', endDate: '' };
            this._appStarted = false;
            this._appShellBound = false;
            this._watchlistBound = false;
            this._realtimeUpdateBound = false;
            this._staticActionsBound = false;
            this._tabsBound = false;
        },

        initSidebar() {
            const collapsed = localStorage.getItem('sidebar-collapsed') === 'true';
            if (collapsed) {
                document.getElementById('sidebar')?.classList.add('collapsed');
                document.body.classList.add('sidebar-collapsed');
            }
        },

        toggleSidebar() {
            const sidebar = document.getElementById('sidebar');
            if (!sidebar) return;
            const collapsed = sidebar.classList.toggle('collapsed');
            document.body.classList.toggle('sidebar-collapsed', collapsed);
            localStorage.setItem('sidebar-collapsed', collapsed);
            const btn = sidebar.querySelector('.sidebar-toggle');
            if (btn) btn.setAttribute('aria-label', collapsed ? '展开导航' : '折叠导航');
        },

        bindStaticActions() {
            if (this._staticActionsBound) return;
            this._staticActionsBound = true;

            const copilotFab = document.getElementById('copilot-fab');
            if (copilotFab && copilotFab.dataset.bound !== 'true') {
                copilotFab.dataset.bound = 'true';
                copilotFab.addEventListener('click', (e) => {
                    e.preventDefault();
                    this.toggleCopilot();
                });
            }

            document.addEventListener('click', (e) => {
                const button = e.target.closest('[data-app-action]');
                if (!button) return;

                const actions = {
                    'toggle-sidebar': () => this.toggleSidebar(),
                    'refresh-overview': () => this.loadOverview(),
                    'save-sim-snapshot': () => this.saveSimSnapshot(),
                    'delete-sim-snapshot': () => {
                        const snapshotId = typeof button.dataset.snapshotId === 'string' ? button.dataset.snapshotId.trim() : '';
                        if (snapshotId) this.deleteSimSnapshot(snapshotId);
                    },
                };
                const action = actions[button.dataset.appAction];
                if (!action) return;

                e.preventDefault();
                action();
            });
        },

        bindTabs() {
            if (this._tabsBound) return;
            this._tabsBound = true;
            document.addEventListener('click', (e) => {
                const link = e.target.closest('.nav-link');
                if (!link) return;
                e.preventDefault();
                const tab = link.dataset.tab;
                if (tab) this.switchTab(tab);
            });

            document.addEventListener('keydown', (e) => {
                const link = e.target.closest('.nav-link');
                if (!link) return;
                const links = [...document.querySelectorAll('.nav-link')];
                const idx = links.indexOf(link);
                let next;
                if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = links[(idx + 1) % links.length];
                else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = links[(idx - 1 + links.length) % links.length];
                else if (e.key === 'Home') next = links[0];
                else if (e.key === 'End') next = links[links.length - 1];
                if (next) { e.preventDefault(); next.focus(); next.click(); }
            });
        },

        async setDefaultDate() {
            let endDate;
            try {
                const status = await this.fetchJSON('/api/system/status');
                endDate = status.db_stats?.latest_date || Utils.todayBeijing();
            } catch {
                endDate = Utils.todayBeijing();
            }

            const d = new Date(endDate);
            const startD = new Date(d);
            startD.setMonth(startD.getMonth() - 1);
            if (startD.getMonth() !== (d.getMonth() - 1 + 12) % 12) {
                startD.setDate(0);
            }
            const startDate = startD.toLocaleDateString('sv-SE', Utils._bjOpts);

            document.getElementById('bt-start').value = startDate;
            document.getElementById('bt-end').value = endDate;
            document.getElementById('alpha-start').value = startDate;
            document.getElementById('alpha-end').value = endDate;
        },
    });
})(window);

document.addEventListener('DOMContentLoaded', () => App.init());
