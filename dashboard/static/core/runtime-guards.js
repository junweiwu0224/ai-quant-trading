(function attachRuntimeGuards(global) {
    'use strict';

    const App = global.App;
    if (!App) {
        return;
    }

    Object.assign(App, {
        _requestNotifyPermission() {
            if ('Notification' in window && Notification.permission === 'default') {
                Notification.requestPermission();
            }
        },

        _initNetworkStatus() {
            const bar = document.getElementById('offline-bar');
            if (!bar) return;

            const update = () => {
                if (navigator.onLine) {
                    bar.classList.add('hidden');
                } else {
                    bar.classList.remove('hidden');
                }
            };

            window.addEventListener('online', () => {
                update();
            });
            window.addEventListener('offline', () => {
                update();
            });
            update();
        },

        _initDegradedMode() {
            const manager = globalThis.DegradedModeManager;
            const intentBus = globalThis.IntentBus;
            if (!manager || typeof manager.init !== 'function' || !intentBus || typeof intentBus.on !== 'function') {
                return;
            }

            manager.init();

            intentBus.on('degraded:toast', (payload) => {
                this._handleDegradedToast(payload);
            });
            intentBus.on('degraded:ui-dim', (payload) => {
                this._applyDegradedUiState(payload);
            });
            intentBus.on('degraded:state-changed', (payload) => {
                this._syncDegradedOfflineBar(payload);
                this._syncDegradedStatusBar(payload);
            });
            intentBus.on('degraded:actions-updated', () => {
                this._refreshCommandPaletteForDegradedState();
            });

            if (typeof manager.emitUiSignals === 'function') {
                manager.emitUiSignals({
                    includeToast: false,
                    includeBadge: true,
                    includeOverlay: true,
                });
            }
        },

        _handleDegradedToast(payload) {
            if (!payload || typeof payload !== 'object') {
                return;
            }

            const dedupeKey = typeof payload.dedupeKey === 'string' ? payload.dedupeKey.trim() : '';
            if (dedupeKey) {
                if (this._degradedUiState.dedupeKeys[dedupeKey] === true) {
                    return;
                }
                this._degradedUiState = {
                    ...this._degradedUiState,
                    dedupeKeys: {
                        ...this._degradedUiState.dedupeKeys,
                        [dedupeKey]: true,
                    },
                };
            }

            const message = typeof payload.message === 'string' && payload.message.trim()
                ? payload.message.trim()
                : '系统状态已变更';
            const tone = payload.tone === 'danger'
                ? 'error'
                : (payload.tone === 'warning' ? 'warning' : 'info');
            this.toast(message, tone);
        },

        _syncDegradedOfflineBar(payload) {
            const bar = document.getElementById('offline-bar');
            if (!bar || !payload || typeof payload !== 'object' || !payload.snapshot) {
                return;
            }

            const snapshot = payload.snapshot;
            const activeStates = snapshot.activeStates && typeof snapshot.activeStates === 'object'
                ? snapshot.activeStates
                : {};
            const offlineState = activeStates['network-offline'];
            if (offlineState && typeof offlineState.reason === 'string' && offlineState.reason.trim()) {
                bar.innerHTML = `<span>${this.escapeHTML(offlineState.reason.trim())}</span>`;
                bar.classList.remove('hidden');
                return;
            }

            bar.innerHTML = '<span>📡 网络已断开，部分功能可能不可用</span>';
            if (snapshot.network && snapshot.network.online === true) {
                bar.classList.add('hidden');
            }
        },

        _syncDegradedStatusBar(payload) {
            const bar = document.getElementById('degraded-status-bar');
            const text = document.getElementById('degraded-status-text');
            if (!bar || !text || !payload || typeof payload !== 'object' || !payload.snapshot) {
                return;
            }

            const snapshot = payload.snapshot;
            const highestSeverity = typeof payload.highestSeverity === 'string' && payload.highestSeverity.trim()
                ? payload.highestSeverity.trim()
                : null;
            const changedKeys = Array.isArray(payload.changedStateKeys) ? payload.changedStateKeys : [];
            const activeStates = snapshot.activeStates && typeof snapshot.activeStates === 'object'
                ? snapshot.activeStates
                : {};
            const activeRecords = Object.values(activeStates).filter((record) => record && typeof record.reason === 'string' && record.reason.trim());

            if (activeRecords.length === 0) {
                bar.classList.add('hidden');
                bar.dataset.severity = 'info';
                text.textContent = '系统已恢复正常';
                return;
            }

            const changedReasons = changedKeys
                .map((stateKey) => activeStates[stateKey])
                .filter((record) => record && typeof record.reason === 'string' && record.reason.trim())
                .map((record) => record.reason.trim());
            const message = changedReasons.length > 0
                ? changedReasons.join('；')
                : activeRecords.map((record) => record.reason.trim()).join('；');

            text.textContent = message;
            bar.dataset.severity = highestSeverity || 'warning';
            bar.classList.remove('hidden');
        },

        _applyDegradedUiState(payload) {
            if (!payload || typeof payload !== 'object') {
                return;
            }

            const scope = typeof payload.scope === 'string' ? payload.scope.trim() : '';
            const target = this._resolveDegradedScopeTarget(scope);
            if (!target) {
                return;
            }

            const isActive = payload.active === true;
            target.dataset.degradedScope = scope || 'global';
            target.dataset.degradedActive = isActive ? 'true' : 'false';
            target.dataset.degradedMode = isActive && typeof payload.mode === 'string' && payload.mode.trim()
                ? payload.mode.trim()
                : 'dim';
            target.dataset.degradedLevel = isActive && typeof payload.level === 'string' && payload.level.trim()
                ? payload.level.trim()
                : 'info';
            target.dataset.degradedReason = isActive && typeof payload.reason === 'string' && payload.reason.trim()
                ? payload.reason.trim()
                : '';
            if (!isActive) {
                delete target.dataset.degradedReason;
            }
        },

        _resolveDegradedScopeTarget(scope) {
            if (scope === 'global') {
                return document.querySelector('main.content');
            }
            if (scope === 'market') {
                return document.getElementById('tab-overview') || document.getElementById('tab-stock');
            }
            if (scope === 'trade') {
                return document.getElementById('tab-trade') || document.getElementById('trade-panel-portfolio') || document.getElementById('tab-paper');
            }
            if (scope === 'portfolio') {
                return document.getElementById('trade-panel-portfolio') || document.getElementById('tab-trade');
            }
            if (scope === 'panel') {
                return document.getElementById('stock-offcanvas');
            }
            return null;
        },

        _refreshCommandPaletteForDegradedState() {
            const palette = globalThis.CommandPalette;
            if (!palette || typeof palette.getState !== 'function' || typeof palette.refreshResults !== 'function') {
                return;
            }

            const state = palette.getState();
            if (!state || state.isOpen !== true) {
                return;
            }

            void palette.refreshResults({
                source: 'app:degraded-actions-updated',
            });
        },

        _installGlobalRuntimeErrorHandlers() {
            if (this._runtimeErrorHandlersInstalled === true) {
                return;
            }
            this._runtimeErrorHandlersInstalled = true;

            window.addEventListener('error', (event) => {
                if (!(event instanceof ErrorEvent)) {
                    return;
                }
                if (!event.error && !(typeof event.message === 'string' && event.message.trim())) {
                    return;
                }

                this._reportRuntimeError('error', {
                    message: event?.message,
                    source: event?.filename,
                    line: event?.lineno,
                    column: event?.colno,
                    error: event?.error,
                });
            });

            window.addEventListener('unhandledrejection', (event) => {
                this._reportRuntimeError('unhandledrejection', {
                    reason: event?.reason,
                });
            });
        },

        _reportRuntimeError(type, detail = {}) {
            const normalized = this._normalizeRuntimeErrorDetail(type, detail);
            const signature = `${normalized.type}|${normalized.message}|${normalized.source}|${normalized.line}|${normalized.column}`;
            const now = Date.now();
            if (
                this._runtimeErrorState.lastSignature === signature
                && now - this._runtimeErrorState.lastAt < 5000
            ) {
                return;
            }

            this._runtimeErrorState = {
                lastSignature: signature,
                lastAt: now,
            };

            if (globalThis.console && typeof globalThis.console.error === 'function') {
                globalThis.console.error('[RuntimeError]', normalized);
            }

            const isInitPhase = document.readyState !== 'complete';
            const message = isInitPhase
                ? '页面初始化异常，请刷新后重试'
                : '页面运行异常，请稍后重试';
            this.toast(message, 'error');
        },

        _normalizeRuntimeErrorDetail(type, detail = {}) {
            const sourceError = detail.error ?? detail.reason;
            const source = typeof detail.source === 'string' && detail.source.trim()
                ? detail.source.trim()
                : '';
            const line = Number.isFinite(Number(detail.line)) ? Number(detail.line) : null;
            const column = Number.isFinite(Number(detail.column)) ? Number(detail.column) : null;

            let message = '';
            if (typeof detail.message === 'string' && detail.message.trim()) {
                message = detail.message.trim();
            } else if (sourceError instanceof Error && typeof sourceError.message === 'string' && sourceError.message.trim()) {
                message = sourceError.message.trim();
            } else if (typeof sourceError === 'string' && sourceError.trim()) {
                message = sourceError.trim();
            } else {
                message = 'Unknown runtime error';
            }

            return {
                type,
                message,
                source,
                line,
                column,
                stack: sourceError instanceof Error && typeof sourceError.stack === 'string'
                    ? sourceError.stack
                    : '',
            };
        },
    });
})(window);
