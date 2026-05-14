(function attachDegradedModeManager(global) {
    'use strict';

    if (!global.IntentBus) {
        throw new Error('DegradedModeManager requires window.IntentBus');
    }

    if (!global.ActionRegistry) {
        throw new Error('DegradedModeManager requires window.ActionRegistry');
    }

    const EVENT_NAMES = Object.freeze({
        STATE_CHANGED: 'degraded:state-changed',
        BADGE_UPDATED: 'degraded:badge-updated',
        UI_DIM: 'degraded:ui-dim',
        TOAST: 'degraded:toast',
        ACTIONS_UPDATED: 'degraded:actions-updated',
    });

    const INPUT_EVENT_NAMES = Object.freeze({
        API_FAILURE: 'system:api-failure',
        API_RECOVERED: 'system:api-recovered',
        DEGRADED_SET: 'system:degraded-set',
        DEGRADED_RECOVER: 'system:degraded-recover',
    });

    const STATE_KEYS = Object.freeze({
        NETWORK_OFFLINE: 'network-offline',
        MARKET_DATA_DOWN: 'market-data-down',
        MARKET_DATA_STALE: 'market-data-stale',
        TRADE_READONLY: 'trade-readonly',
        TRADE_API_DOWN: 'trade-api-down',
        PORTFOLIO_READONLY: 'portfolio-readonly',
        SYSTEM_DEGRADED: 'system-degraded',
    });

    const LEVEL_PRIORITY = Object.freeze({
        info: 1,
        warning: 2,
        critical: 3,
    });

    const DIM_SCOPE_PRIORITY = Object.freeze({
        global: 1,
        market: 2,
        trade: 3,
        portfolio: 4,
        panel: 5,
    });

    const UI_DIM_MODE_PRIORITY = Object.freeze({
        dim: 1,
        readonly: 2,
        blocked: 3,
    });

    const EMPTY_ARRAY = Object.freeze([]);

    const DEFAULT_OPTIONS = Object.freeze({
        failureIntentNames: [INPUT_EVENT_NAMES.API_FAILURE],
        recoveryIntentNames: [INPUT_EVENT_NAMES.API_RECOVERED],
        manualSetIntentNames: [INPUT_EVENT_NAMES.DEGRADED_SET],
        manualRecoverIntentNames: [INPUT_EVENT_NAMES.DEGRADED_RECOVER],
        actionPolicies: {
            'network-offline': {
                disable: [
                    'sim-trade:submit-order',
                    'sim-trade:cancel-order',
                    'trade:submit-order',
                    'trade:open-panel',
                    'open_paper_buy',
                ],
                readonly: ['add_to_watchlist', 'remove_from_watchlist', 'watchlist:add', 'watchlist:remove', 'portfolio:rebalance'],
            },
            'market-data-down': {
                disable: ['sim-trade:submit-order', 'trade:submit-order', 'open_paper_buy'],
                readonly: ['trade:open-panel'],
            },
            'market-data-stale': {
                readonly: ['sim-trade:submit-order', 'trade:submit-order', 'open_paper_buy'],
            },
            'trade-readonly': {
                disable: ['sim-trade:submit-order', 'sim-trade:cancel-order', 'trade:submit-order', 'open_paper_buy'],
                readonly: ['trade:open-panel', 'portfolio:rebalance'],
            },
            'trade-api-down': {
                disable: ['sim-trade:submit-order', 'sim-trade:cancel-order', 'trade:submit-order', 'trade:open-panel', 'open_paper_buy'],
                readonly: ['portfolio:rebalance'],
            },
            'portfolio-readonly': {
                readonly: ['portfolio:rebalance'],
            },
            'system-degraded': {
                disable: ['sim-trade:submit-order', 'sim-trade:cancel-order', 'trade:submit-order', 'open_paper_buy'],
                readonly: ['add_to_watchlist', 'remove_from_watchlist', 'trade:open-panel', 'watchlist:add', 'watchlist:remove', 'portfolio:rebalance'],
            },
        },
    });

    function getNow() {
        return Date.now();
    }

    function isPlainObject(value) {
        return Object.prototype.toString.call(value) === '[object Object]';
    }

    function cloneValue(value) {
        if (value === null || value === undefined) {
            return value;
        }

        if (Array.isArray(value)) {
            return value.map((item) => cloneValue(item));
        }

        if (value instanceof Date) {
            return new Date(value.getTime());
        }

        if (isPlainObject(value)) {
            return Object.fromEntries(
                Object.entries(value).map(([key, entryValue]) => [key, cloneValue(entryValue)])
            );
        }

        return value;
    }

    function deepFreeze(value) {
        if (!value || typeof value !== 'object' || Object.isFrozen(value)) {
            return value;
        }

        Object.freeze(value);
        Object.keys(value).forEach((key) => {
            deepFreeze(value[key]);
        });
        return value;
    }

    function uniqueStrings(values) {
        if (!Array.isArray(values) || values.length === 0) {
            return [];
        }

        const seen = new Set();
        const normalized = [];
        values.forEach((value) => {
            if (typeof value !== 'string') {
                return;
            }
            const nextValue = value.trim();
            if (!nextValue || seen.has(nextValue)) {
                return;
            }
            seen.add(nextValue);
            normalized.push(nextValue);
        });
        return normalized;
    }

    function normalizeEventNameList(values, fallbackValues) {
        const normalized = uniqueStrings(values);
        if (normalized.length > 0) {
            return normalized;
        }
        return uniqueStrings(fallbackValues);
    }

    function normalizeLevel(level) {
        return level === 'critical' || level === 'warning' || level === 'info' ? level : 'warning';
    }

    function normalizeDomain(domain) {
        return domain === 'network' || domain === 'market' || domain === 'trade' || domain === 'portfolio' || domain === 'system'
            ? domain
            : 'system';
    }

    function normalizeSource(source) {
        return source === 'browser' || source === 'intent' || source === 'manual' || source === 'system'
            ? source
            : 'system';
    }

    function normalizeMode(mode) {
        return typeof mode === 'string' && mode.trim() ? mode.trim() : 'dim';
    }

    function normalizeBoolean(value, fallbackValue) {
        if (typeof value === 'boolean') {
            return value;
        }
        return fallbackValue;
    }

    function sortByPriority(values, priorityMap) {
        return values.slice().sort((left, right) => {
            const leftPriority = priorityMap[left] || Number.MAX_SAFE_INTEGER;
            const rightPriority = priorityMap[right] || Number.MAX_SAFE_INTEGER;
            if (leftPriority !== rightPriority) {
                return leftPriority - rightPriority;
            }
            return String(left).localeCompare(String(right));
        });
    }

    function createInitialSnapshot() {
        return {
            network: {
                online: true,
                lastChangedAt: null,
            },
            activeStates: {},
            derived: {
                highestSeverity: null,
                isReadonlyTrade: false,
                isMarketDataUnavailable: false,
                isOffline: false,
                blockedActions: [],
                readonlyActions: [],
                badgeStates: [],
            },
            meta: {
                updatedAt: null,
                version: 0,
            },
        };
    }

    function createManagerError(message, code) {
        const error = new Error(message);
        error.name = 'DegradedModeManagerError';
        if (code) {
            error.code = code;
        }
        return error;
    }

    function normalizeStateKeyAlias(stateKey) {
        if (stateKey === 'offline') {
            return STATE_KEYS.NETWORK_OFFLINE;
        }
        return stateKey;
    }

    class DegradedModeManagerImpl {
        constructor(intentBus, stockStore, actionRegistry) {
            this._intentBus = intentBus;
            this._stockStore = stockStore || null;
            this._actionRegistry = actionRegistry;
            this._snapshot = createInitialSnapshot();
            this._initialized = false;
            this._options = null;
            this._intentUnsubscribers = [];
            this._browserListeners = [];
            this._syncingActions = false;
            this._emittingUiSignals = false;
            this._lastActionPolicy = {
                blockedActions: [],
                readonlyActions: [],
            };
            this._managedActionBaselines = {};
        }

        init(options) {
            if (this._initialized) {
                return;
            }

            this._options = this._normalizeInitOptions(options);
            this._bindBrowserListeners();
            this._bindIntentListeners();
            this._synchronizeNetworkState();
            this._initialized = true;
            this.emitUiSignals({
                includeToast: false,
                includeBadge: true,
                includeOverlay: true,
            });
        }

        dispose() {
            this._intentUnsubscribers.forEach((unsubscribe) => {
                try {
                    unsubscribe();
                } catch (error) {
                    this._reportError('dispose-intent-listener', error);
                }
            });
            this._browserListeners.forEach((entry) => {
                try {
                    global.removeEventListener(entry.eventName, entry.handler);
                } catch (error) {
                    this._reportError('dispose-browser-listener', error);
                }
            });

            this._restoreManagedActionBaselines();
            this._intentUnsubscribers = [];
            this._browserListeners = [];
            this._initialized = false;
            this._syncingActions = false;
            this._emittingUiSignals = false;
        }

        getSnapshot() {
            return this._snapshotSnapshot();
        }

        hasState(stateKey) {
            const normalizedStateKey = normalizeStateKeyAlias(this._normalizeStateKey(stateKey));
            return Object.prototype.hasOwnProperty.call(this._snapshot.activeStates, normalizedStateKey);
        }

        getState(stateKey) {
            const normalizedStateKey = normalizeStateKeyAlias(this._normalizeStateKey(stateKey));
            const stateRecord = this._snapshot.activeStates[normalizedStateKey];
            return stateRecord ? deepFreeze(cloneValue(stateRecord)) : null;
        }

        setDegradedState(stateKey, payload) {
            const normalizedStateKey = normalizeStateKeyAlias(this._normalizeStateKey(stateKey));
            const normalizedPayload = this._normalizeSetPayload(payload);
            const previousRecord = this._snapshot.activeStates[normalizedStateKey] || null;
            const nextRecord = this._buildNextStateRecord(normalizedStateKey, previousRecord, normalizedPayload);
            const nextActiveStates = {
                ...this._snapshot.activeStates,
                [normalizedStateKey]: nextRecord,
            };

            this._commitStateChange({
                nextActiveStates,
                changedStateKeys: [normalizedStateKey],
                source: normalizedPayload.source,
                shouldNotify: normalizedPayload.silent !== true,
            });

            return this.getSnapshot();
        }

        recoverState(stateKey, options) {
            const normalizedStateKey = normalizeStateKeyAlias(this._normalizeStateKey(stateKey));
            if (!this.hasState(normalizedStateKey)) {
                return this.getSnapshot();
            }

            const normalizedOptions = this._normalizeRecoverOptions(options);
            const nextActiveStates = { ...this._snapshot.activeStates };
            delete nextActiveStates[normalizedStateKey];

            this._commitStateChange({
                nextActiveStates,
                changedStateKeys: [normalizedStateKey],
                source: normalizedOptions.source,
                shouldNotify: normalizedOptions.silent !== true,
            });

            return this.getSnapshot();
        }

        recoverAll(options) {
            const normalizedOptions = this._normalizeRecoverAllOptions(options);
            const currentKeys = Object.keys(this._snapshot.activeStates);
            const exceptSet = new Set(normalizedOptions.except);
            const nextActiveStates = Object.fromEntries(
                Object.entries(this._snapshot.activeStates).filter(([stateKey]) => exceptSet.has(stateKey))
            );
            const changedStateKeys = currentKeys.filter((stateKey) => !exceptSet.has(stateKey));

            if (changedStateKeys.length === 0) {
                return this.getSnapshot();
            }

            this._commitStateChange({
                nextActiveStates,
                changedStateKeys,
                source: normalizedOptions.source,
                shouldNotify: normalizedOptions.silent !== true,
            });

            return this.getSnapshot();
        }

        syncActionAvailability() {
            if (this._syncingActions) {
                return this._snapshotActionPolicy();
            }

            this._syncingActions = true;
            try {
                const blockedActions = this._snapshot.derived.blockedActions;
                const readonlyActions = this._snapshot.derived.readonlyActions;
                const policy = {
                    blockedActions: blockedActions.slice(),
                    readonlyActions: readonlyActions.slice(),
                };
                const affectedActions = uniqueStrings(blockedActions.concat(readonlyActions, this._lastActionPolicy.blockedActions, this._lastActionPolicy.readonlyActions));
                const blockedSet = new Set(blockedActions);
                const readonlySet = new Set(readonlyActions);

                affectedActions.forEach((actionId) => {
                    if (!this._actionRegistry.has(actionId)) {
                        delete this._managedActionBaselines[actionId];
                        return;
                    }

                    const actionSnapshot = this._actionRegistry.get(actionId);
                    if (!actionSnapshot) {
                        delete this._managedActionBaselines[actionId];
                        return;
                    }

                    const shouldDisable = blockedSet.has(actionId) || readonlySet.has(actionId);
                    const hasBaseline = Object.prototype.hasOwnProperty.call(this._managedActionBaselines, actionId);
                    if (shouldDisable) {
                        if (!hasBaseline) {
                            this._managedActionBaselines = {
                                ...this._managedActionBaselines,
                                [actionId]: actionSnapshot.enabled === true,
                            };
                        }
                        this._actionRegistry.setEnabled({
                            actionId,
                            enabled: false,
                        });
                        return;
                    }

                    if (!hasBaseline) {
                        return;
                    }

                    const baselineEnabled = this._managedActionBaselines[actionId] === true;
                    this._actionRegistry.setEnabled({
                        actionId,
                        enabled: baselineEnabled,
                    });
                    const nextBaselines = { ...this._managedActionBaselines };
                    delete nextBaselines[actionId];
                    this._managedActionBaselines = nextBaselines;
                });

                this._lastActionPolicy = policy;
                return this._snapshotActionPolicy();
            } finally {
                this._syncingActions = false;
            }
        }

        emitUiSignals(options) {
            if (this._emittingUiSignals) {
                return;
            }

            const normalizedOptions = this._normalizeEmitOptions(options);
            this._emittingUiSignals = true;
            try {
                const timestamp = getNow();
                const snapshot = this.getSnapshot();
                const stateKeys = Object.keys(snapshot.activeStates);

                if (normalizedOptions.includeBadge) {
                    this._emitIntent(EVENT_NAMES.BADGE_UPDATED, {
                        badges: cloneValue(snapshot.derived.badgeStates),
                        source: 'system',
                        timestamp,
                    });
                }

                if (normalizedOptions.includeOverlay) {
                    this._buildUiDimPayloads(snapshot).forEach((payload) => {
                        this._emitIntent(EVENT_NAMES.UI_DIM, {
                            ...payload,
                            timestamp,
                        });
                    });
                }

                this._emitIntent(EVENT_NAMES.STATE_CHANGED, {
                    snapshot,
                    changedStateKeys: cloneValue(stateKeys),
                    highestSeverity: snapshot.derived.highestSeverity,
                    source: 'system',
                    timestamp,
                });

                this._emitIntent(EVENT_NAMES.ACTIONS_UPDATED, {
                    blockedActions: cloneValue(snapshot.derived.blockedActions),
                    readonlyActions: cloneValue(snapshot.derived.readonlyActions),
                    stateKeys: cloneValue(stateKeys),
                    timestamp,
                });

                if (normalizedOptions.includeToast) {
                    this._buildToastPayloads(snapshot).forEach((payload) => {
                        this._emitIntent(EVENT_NAMES.TOAST, {
                            ...payload,
                            timestamp,
                        });
                    });
                }
            } finally {
                this._emittingUiSignals = false;
            }
        }

        _normalizeInitOptions(options) {
            const safeOptions = isPlainObject(options) ? options : {};
            const actionPolicies = this._normalizeActionPolicies(safeOptions.actionPolicies || DEFAULT_OPTIONS.actionPolicies);
            return {
                intentBus: safeOptions.intentBus || this._intentBus,
                stockStore: safeOptions.stockStore || this._stockStore,
                actionRegistry: safeOptions.actionRegistry || this._actionRegistry,
                failureIntentNames: normalizeEventNameList(safeOptions.failureIntentNames, DEFAULT_OPTIONS.failureIntentNames),
                recoveryIntentNames: normalizeEventNameList(safeOptions.recoveryIntentNames, DEFAULT_OPTIONS.recoveryIntentNames),
                manualSetIntentNames: normalizeEventNameList(safeOptions.manualSetIntentNames, DEFAULT_OPTIONS.manualSetIntentNames),
                manualRecoverIntentNames: normalizeEventNameList(safeOptions.manualRecoverIntentNames, DEFAULT_OPTIONS.manualRecoverIntentNames),
                actionPolicies,
            };
        }

        _normalizeActionPolicies(policies) {
            const safePolicies = isPlainObject(policies) ? policies : {};
            return Object.fromEntries(
                Object.entries(safePolicies).map(([stateKey, policy]) => {
                    const safePolicy = isPlainObject(policy) ? policy : {};
                    return [
                        this._normalizeStateKey(stateKey),
                        {
                            disable: uniqueStrings(safePolicy.disable),
                            readonly: uniqueStrings(safePolicy.readonly),
                        },
                    ];
                })
            );
        }

        _normalizeSetPayload(payload) {
            if (!isPlainObject(payload)) {
                throw createManagerError('setDegradedState payload must be a plain object', 'INVALID_SET_PAYLOAD');
            }

            const level = normalizeLevel(payload.level);
            const domain = normalizeDomain(payload.domain);
            const source = normalizeSource(payload.source);
            const mode = normalizeMode(payload.mode);
            const reason = typeof payload.reason === 'string' && payload.reason.trim() ? payload.reason.trim() : 'system degraded';
            const affects = this._normalizeAffects(payload.affects);
            const expiresAt = payload.expiresAt == null ? null : Number(payload.expiresAt);
            const normalizedExpiresAt = Number.isFinite(expiresAt) ? expiresAt : null;

            return {
                domain,
                level,
                mode,
                reason,
                source,
                recoverable: normalizeBoolean(payload.recoverable, true),
                affects,
                expiresAt: normalizedExpiresAt,
                details: isPlainObject(payload.details) ? cloneValue(payload.details) : {},
                silent: payload.silent === true,
            };
        }

        _normalizeRecoverOptions(options) {
            const safeOptions = isPlainObject(options) ? options : {};
            return {
                source: normalizeSource(safeOptions.source),
                reason: typeof safeOptions.reason === 'string' && safeOptions.reason.trim() ? safeOptions.reason.trim() : 'state recovered',
                silent: safeOptions.silent === true,
            };
        }

        _normalizeRecoverAllOptions(options) {
            const safeOptions = isPlainObject(options) ? options : {};
            return {
                source: normalizeSource(safeOptions.source),
                reason: typeof safeOptions.reason === 'string' && safeOptions.reason.trim() ? safeOptions.reason.trim() : 'all states recovered',
                except: uniqueStrings(safeOptions.except),
                silent: safeOptions.silent === true,
            };
        }

        _normalizeEmitOptions(options) {
            const safeOptions = isPlainObject(options) ? options : {};
            return {
                includeToast: safeOptions.includeToast === true,
                includeBadge: safeOptions.includeBadge !== false,
                includeOverlay: safeOptions.includeOverlay !== false,
            };
        }

        _normalizeAffects(affects) {
            const safeAffects = isPlainObject(affects) ? affects : {};
            return {
                actions: uniqueStrings(safeAffects.actions),
                views: uniqueStrings(safeAffects.views),
                badges: uniqueStrings(safeAffects.badges),
            };
        }

        _normalizeStateKey(stateKey) {
            if (typeof stateKey !== 'string' || !stateKey.trim()) {
                throw createManagerError('stateKey must be a non-empty string', 'INVALID_STATE_KEY');
            }
            return stateKey.trim();
        }

        _buildNextStateRecord(stateKey, previousRecord, payload) {
            const now = getNow();
            const enteredAt = previousRecord ? previousRecord.enteredAt : now;
            return deepFreeze({
                key: stateKey,
                domain: payload.domain,
                level: payload.level,
                mode: payload.mode,
                reason: payload.reason,
                source: payload.source,
                recoverable: payload.recoverable,
                affects: {
                    actions: payload.affects.actions.slice(),
                    views: payload.affects.views.slice(),
                    badges: payload.affects.badges.slice(),
                },
                enteredAt,
                updatedAt: now,
                expiresAt: payload.expiresAt,
                details: cloneValue(payload.details),
            });
        }

        _commitStateChange(params) {
            const nextActiveStates = this._pruneExpiredStates(params.nextActiveStates);
            const nextSnapshot = this._buildSnapshot(nextActiveStates);
            this._snapshot = nextSnapshot;
            this.syncActionAvailability();
            if (params.shouldNotify) {
                this._emitStateTransitionSignals(params.changedStateKeys, params.source);
            }
        }

        _pruneExpiredStates(activeStates) {
            const now = getNow();
            return Object.fromEntries(
                Object.entries(activeStates).filter(([, record]) => {
                    if (!record || record.expiresAt == null) {
                        return true;
                    }
                    return Number(record.expiresAt) > now;
                })
            );
        }

        _buildSnapshot(activeStates) {
            const previousSnapshot = this._snapshot;
            const networkStateRecord = activeStates[STATE_KEYS.NETWORK_OFFLINE] || null;
            const nextNetwork = {
                online: networkStateRecord == null,
                lastChangedAt: networkStateRecord ? networkStateRecord.updatedAt : previousSnapshot.network.lastChangedAt,
            };
            const derived = this._buildDerivedState(activeStates, nextNetwork.online);
            return deepFreeze({
                network: nextNetwork,
                activeStates: cloneValue(activeStates),
                derived,
                meta: {
                    updatedAt: getNow(),
                    version: previousSnapshot.meta.version + 1,
                },
            });
        }

        _buildDerivedState(activeStates, online) {
            const stateRecords = Object.values(activeStates);
            const highestSeverity = this._getHighestSeverity(stateRecords);
            const blockedActions = this._collectPolicyActions(activeStates, 'disable');
            const readonlyActions = this._collectPolicyActions(activeStates, 'readonly');
            return deepFreeze({
                highestSeverity,
                isReadonlyTrade: this._hasAnyState(activeStates, [STATE_KEYS.TRADE_READONLY, STATE_KEYS.TRADE_API_DOWN, STATE_KEYS.NETWORK_OFFLINE]),
                isMarketDataUnavailable: this._hasAnyState(activeStates, [STATE_KEYS.MARKET_DATA_DOWN, STATE_KEYS.NETWORK_OFFLINE]),
                isOffline: online === false,
                blockedActions,
                readonlyActions,
                badgeStates: this._buildBadgeStates(activeStates),
            });
        }

        _getHighestSeverity(stateRecords) {
            if (!Array.isArray(stateRecords) || stateRecords.length === 0) {
                return null;
            }

            return stateRecords.reduce((currentLevel, record) => {
                const recordLevel = normalizeLevel(record.level);
                if (currentLevel == null) {
                    return recordLevel;
                }
                return LEVEL_PRIORITY[recordLevel] > LEVEL_PRIORITY[currentLevel] ? recordLevel : currentLevel;
            }, null);
        }

        _collectPolicyActions(activeStates, fieldName) {
            const policyActions = Object.keys(activeStates).flatMap((stateKey) => {
                const actionPolicy = this._options && this._options.actionPolicies[stateKey]
                    ? this._options.actionPolicies[stateKey][fieldName]
                    : EMPTY_ARRAY;
                const record = activeStates[stateKey];
                const inlineActions = record && record.affects && Array.isArray(record.affects.actions)
                    ? record.affects.actions
                    : EMPTY_ARRAY;
                return actionPolicy.concat(inlineActions);
            });
            return uniqueStrings(policyActions);
        }

        _buildBadgeStates(activeStates) {
            return Object.values(activeStates)
                .map((record) => this._buildBadgeState(record))
                .filter(Boolean)
                .sort((left, right) => {
                    const leftPriority = LEVEL_PRIORITY[left.tone === 'danger' ? 'critical' : left.tone === 'warning' ? 'warning' : 'info'];
                    const rightPriority = LEVEL_PRIORITY[right.tone === 'danger' ? 'critical' : right.tone === 'warning' ? 'warning' : 'info'];
                    if (leftPriority !== rightPriority) {
                        return rightPriority - leftPriority;
                    }
                    return left.id.localeCompare(right.id);
                });
        }

        _buildBadgeState(record) {
            if (!record) {
                return null;
            }

            return deepFreeze({
                id: `${record.domain}-${record.key}`,
                scope: this._mapDomainToScope(record.domain),
                tone: this._mapLevelToTone(record.level),
                label: record.reason,
                stateKey: record.key,
                visible: true,
            });
        }

        _mapLevelToTone(level) {
            if (level === 'critical') {
                return 'danger';
            }
            if (level === 'warning') {
                return 'warning';
            }
            if (level === 'info') {
                return 'info';
            }
            return 'muted';
        }

        _mapDomainToScope(domain) {
            if (domain === 'market' || domain === 'trade' || domain === 'portfolio') {
                return domain;
            }
            return 'global';
        }

        _hasAnyState(activeStates, stateKeys) {
            return stateKeys.some((stateKey) => Object.prototype.hasOwnProperty.call(activeStates, stateKey));
        }

        _bindBrowserListeners() {
            const offlineHandler = () => {
                this.setDegradedState(STATE_KEYS.NETWORK_OFFLINE, {
                    domain: 'network',
                    level: 'critical',
                    mode: 'blocked',
                    reason: '网络已断开，系统进入降级模式',
                    source: 'browser',
                    recoverable: true,
                    affects: {
                        actions: ['sim-trade:submit-order', 'sim-trade:cancel-order', 'trade:submit-order', 'trade:open-panel'],
                        views: ['global'],
                        badges: ['network-status'],
                    },
                    details: {
                        online: false,
                    },
                });
            };
            const onlineHandler = () => {
                this.recoverState(STATE_KEYS.NETWORK_OFFLINE, {
                    source: 'browser',
                    reason: '网络已恢复',
                });
            };

            global.addEventListener('offline', offlineHandler);
            global.addEventListener('online', onlineHandler);
            this._browserListeners = [
                { eventName: 'offline', handler: offlineHandler },
                { eventName: 'online', handler: onlineHandler },
            ];
        }

        _bindIntentListeners() {
            const failureHandler = (payload) => {
                this._handleApiFailureIntent(payload);
            };
            const recoveredHandler = (payload) => {
                this._handleApiRecoveredIntent(payload);
            };
            const manualSetHandler = (payload) => {
                this._handleManualSetIntent(payload);
            };
            const manualRecoverHandler = (payload) => {
                this._handleManualRecoverIntent(payload);
            };

            const unsubscribers = [];
            this._options.failureIntentNames.forEach((eventName) => {
                unsubscribers.push(this._intentBus.on(eventName, failureHandler));
            });
            this._options.recoveryIntentNames.forEach((eventName) => {
                unsubscribers.push(this._intentBus.on(eventName, recoveredHandler));
            });
            this._options.manualSetIntentNames.forEach((eventName) => {
                unsubscribers.push(this._intentBus.on(eventName, manualSetHandler));
            });
            this._options.manualRecoverIntentNames.forEach((eventName) => {
                unsubscribers.push(this._intentBus.on(eventName, manualRecoverHandler));
            });
            this._intentUnsubscribers = unsubscribers;
        }

        _synchronizeNetworkState() {
            if (typeof global.navigator !== 'object' || typeof global.navigator.onLine !== 'boolean') {
                return;
            }
            if (global.navigator.onLine === false) {
                this.setDegradedState(STATE_KEYS.NETWORK_OFFLINE, {
                    domain: 'network',
                    level: 'critical',
                    mode: 'blocked',
                    reason: '网络已断开，系统进入降级模式',
                    source: 'browser',
                    recoverable: true,
                    affects: {
                        actions: ['sim-trade:submit-order', 'sim-trade:cancel-order', 'trade:submit-order', 'trade:open-panel'],
                        views: ['global'],
                        badges: ['network-status'],
                    },
                    details: {
                        online: false,
                    },
                    silent: true,
                });
                return;
            }
            this.recoverState(STATE_KEYS.NETWORK_OFFLINE, {
                source: 'browser',
                reason: '网络已恢复',
                silent: true,
            });
        }

        _handleApiFailureIntent(payload) {
            if (!isPlainObject(payload)) {
                return;
            }
            if (this._shouldIgnorePayload(payload)) {
                return;
            }

            const domain = normalizeDomain(payload.domain);
            const stateKey = this._resolveStateKeyFromFailurePayload(payload, domain);
            this.setDegradedState(stateKey, {
                domain,
                level: normalizeLevel(payload.severity),
                mode: normalizeMode(payload.fallbackMode || 'readonly'),
                reason: typeof payload.message === 'string' && payload.message.trim()
                    ? payload.message.trim()
                    : this._buildDefaultFailureReason(stateKey, domain),
                source: 'intent',
                recoverable: true,
                affects: {
                    actions: [],
                    views: [this._mapDomainToScope(domain)],
                    badges: [stateKey],
                },
                details: {
                    service: typeof payload.service === 'string' ? payload.service : null,
                    endpoint: typeof payload.endpoint === 'string' ? payload.endpoint : null,
                    code: payload.code == null ? null : payload.code,
                    traceId: typeof payload.traceId === 'string' ? payload.traceId : null,
                    timestamp: Number.isFinite(Number(payload.timestamp)) ? Number(payload.timestamp) : getNow(),
                    meta: isPlainObject(payload.details) ? cloneValue(payload.details) : {},
                },
            });
        }

        _handleApiRecoveredIntent(payload) {
            if (!isPlainObject(payload)) {
                return;
            }
            if (this._shouldIgnorePayload(payload)) {
                return;
            }

            const domain = normalizeDomain(payload.domain);
            const stateKey = this._resolveStateKeyFromRecoveredPayload(payload, domain);
            if (stateKey) {
                this.recoverState(stateKey, {
                    source: 'intent',
                    reason: typeof payload.message === 'string' && payload.message.trim() ? payload.message.trim() : '服务已恢复',
                });
                return;
            }

            const domainStateKeys = this._getStateKeysByDomain(domain);
            if (domainStateKeys.length === 0) {
                return;
            }
            domainStateKeys.forEach((candidateStateKey) => {
                this.recoverState(candidateStateKey, {
                    source: 'intent',
                    reason: typeof payload.message === 'string' && payload.message.trim() ? payload.message.trim() : '服务已恢复',
                    silent: true,
                });
            });
            this._emitStateTransitionSignals(domainStateKeys, 'intent');
        }

        _handleManualSetIntent(payload) {
            if (!isPlainObject(payload)) {
                return;
            }
            if (this._shouldIgnorePayload(payload)) {
                return;
            }
            if (typeof payload.stateKey !== 'string' || !payload.stateKey.trim()) {
                return;
            }

            this.setDegradedState(payload.stateKey, {
                domain: payload.domain,
                level: payload.level,
                mode: payload.mode,
                reason: payload.reason,
                source: payload.source || 'intent',
                recoverable: true,
                affects: payload.affects,
                details: payload.details,
            });
        }

        _handleManualRecoverIntent(payload) {
            if (!isPlainObject(payload)) {
                return;
            }
            if (this._shouldIgnorePayload(payload)) {
                return;
            }
            if (typeof payload.stateKey !== 'string' || !payload.stateKey.trim()) {
                return;
            }

            this.recoverState(payload.stateKey, {
                source: payload.source || 'intent',
                reason: payload.reason,
            });
        }

        _shouldIgnorePayload(payload) {
            if (!isPlainObject(payload)) {
                return true;
            }
            if (payload.__fromDegradedModeManager === true) {
                return true;
            }
            const eventName = typeof payload.type === 'string' ? payload.type : null;
            if (eventName && eventName.indexOf('degraded:') === 0) {
                return true;
            }
            return false;
        }

        _resolveStateKeyFromFailurePayload(payload, domain) {
            if (typeof payload.suggestedStateKey === 'string' && payload.suggestedStateKey.trim()) {
                return payload.suggestedStateKey.trim();
            }
            if (domain === 'market') {
                return STATE_KEYS.MARKET_DATA_DOWN;
            }
            if (domain === 'trade') {
                return STATE_KEYS.TRADE_API_DOWN;
            }
            if (domain === 'portfolio') {
                return STATE_KEYS.PORTFOLIO_READONLY;
            }
            return STATE_KEYS.SYSTEM_DEGRADED;
        }

        _resolveStateKeyFromRecoveredPayload(payload, domain) {
            if (typeof payload.suggestedStateKey === 'string' && payload.suggestedStateKey.trim()) {
                return payload.suggestedStateKey.trim();
            }
            if (domain === 'market') {
                return STATE_KEYS.MARKET_DATA_DOWN;
            }
            if (domain === 'trade') {
                return STATE_KEYS.TRADE_API_DOWN;
            }
            if (domain === 'portfolio') {
                return STATE_KEYS.PORTFOLIO_READONLY;
            }
            if (domain === 'system') {
                return STATE_KEYS.SYSTEM_DEGRADED;
            }
            return null;
        }

        _getStateKeysByDomain(domain) {
            return Object.keys(this._snapshot.activeStates).filter((stateKey) => {
                const record = this._snapshot.activeStates[stateKey];
                return record && record.domain === domain;
            });
        }

        _buildDefaultFailureReason(stateKey, domain) {
            if (stateKey === STATE_KEYS.MARKET_DATA_DOWN) {
                return '行情服务不可用';
            }
            if (stateKey === STATE_KEYS.MARKET_DATA_STALE) {
                return '行情数据已过期';
            }
            if (stateKey === STATE_KEYS.TRADE_READONLY) {
                return '交易能力已降级为只读';
            }
            if (stateKey === STATE_KEYS.TRADE_API_DOWN) {
                return '交易服务不可用';
            }
            if (stateKey === STATE_KEYS.PORTFOLIO_READONLY) {
                return '持仓与账户能力已降级为只读';
            }
            if (domain === 'network') {
                return '网络异常';
            }
            return '系统已进入降级状态';
        }

        _emitStateTransitionSignals(changedStateKeys, source) {
            const normalizedChangedKeys = uniqueStrings(changedStateKeys);
            const timestamp = getNow();
            const snapshot = this.getSnapshot();

            this._emitIntent(EVENT_NAMES.STATE_CHANGED, {
                snapshot,
                changedStateKeys: cloneValue(normalizedChangedKeys),
                highestSeverity: snapshot.derived.highestSeverity,
                source: normalizeSource(source),
                timestamp,
                __fromDegradedModeManager: true,
            });

            this._emitIntent(EVENT_NAMES.BADGE_UPDATED, {
                badges: cloneValue(snapshot.derived.badgeStates),
                source: normalizeSource(source),
                timestamp,
                __fromDegradedModeManager: true,
            });

            this._buildUiDimPayloads(snapshot).forEach((payload) => {
                this._emitIntent(EVENT_NAMES.UI_DIM, {
                    ...payload,
                    timestamp,
                    __fromDegradedModeManager: true,
                });
            });

            this._emitIntent(EVENT_NAMES.ACTIONS_UPDATED, {
                blockedActions: cloneValue(snapshot.derived.blockedActions),
                readonlyActions: cloneValue(snapshot.derived.readonlyActions),
                stateKeys: cloneValue(normalizedChangedKeys),
                timestamp,
                __fromDegradedModeManager: true,
            });

            this._buildToastPayloads(snapshot, normalizedChangedKeys).forEach((payload) => {
                this._emitIntent(EVENT_NAMES.TOAST, {
                    ...payload,
                    timestamp,
                    __fromDegradedModeManager: true,
                });
            });
        }

        _buildUiDimPayloads(snapshot) {
            const grouped = this._groupStatesByScope(snapshot.activeStates);
            const scopes = sortByPriority(Object.keys(DIM_SCOPE_PRIORITY), DIM_SCOPE_PRIORITY);
            return scopes.map((scope) => {
                const scopeRecords = grouped[scope] || [];
                const level = this._getHighestSeverity(scopeRecords) || 'info';
                const mode = this._resolveDimMode(scopeRecords);
                const reason = scopeRecords.length > 0
                    ? scopeRecords.map((record) => record.reason).join('；')
                    : this._buildRecoveredReason(scope);
                return {
                    scope,
                    active: scopeRecords.length > 0,
                    reason,
                    stateKeys: scopeRecords.map((record) => record.key),
                    level,
                    mode: scopeRecords.length > 0 ? mode : 'dim',
                };
            });
        }

        _groupStatesByScope(activeStates) {
            return Object.values(activeStates).reduce((groups, record) => {
                const scope = this._mapDomainToScope(record.domain);
                const nextGroups = { ...groups };
                const currentRecords = Array.isArray(nextGroups[scope]) ? nextGroups[scope].slice() : [];
                nextGroups[scope] = currentRecords.concat(record);
                if (scope !== 'global') {
                    const globalRecords = Array.isArray(nextGroups.global) ? nextGroups.global.slice() : [];
                    nextGroups.global = globalRecords.concat(record);
                }
                return nextGroups;
            }, {});
        }

        _resolveDimMode(records) {
            if (!Array.isArray(records) || records.length === 0) {
                return 'dim';
            }
            const modes = uniqueStrings(records.map((record) => normalizeMode(record.mode)));
            const sortedModes = sortByPriority(modes, UI_DIM_MODE_PRIORITY);
            return sortedModes[sortedModes.length - 1] || 'dim';
        }

        _buildRecoveredReason(scope) {
            if (scope === 'trade') {
                return '交易能力已恢复';
            }
            if (scope === 'market') {
                return '行情能力已恢复';
            }
            if (scope === 'portfolio') {
                return '持仓与账户能力已恢复';
            }
            if (scope === 'panel') {
                return '面板能力已恢复';
            }
            return '系统已恢复正常';
        }

        _buildToastPayloads(snapshot, changedStateKeys) {
            const normalizedChangedKeys = Array.isArray(changedStateKeys) && changedStateKeys.length > 0
                ? changedStateKeys
                : Object.keys(snapshot.activeStates);
            return normalizedChangedKeys.map((stateKey) => {
                const stateRecord = snapshot.activeStates[stateKey];
                if (stateRecord) {
                    return {
                        tone: this._mapLevelToToastTone(stateRecord.level),
                        message: stateRecord.reason,
                        stateKey,
                        dedupeKey: `degraded-${stateKey}-${snapshot.meta.version}`,
                        duration: 5000,
                    };
                }
                return {
                    tone: 'info',
                    message: this._buildRecoveredToastMessage(stateKey),
                    stateKey,
                    dedupeKey: `recovered-${stateKey}-${snapshot.meta.version}`,
                    duration: 3500,
                };
            });
        }

        _buildRecoveredToastMessage(stateKey) {
            if (stateKey === STATE_KEYS.NETWORK_OFFLINE) {
                return '网络已恢复';
            }
            if (stateKey === STATE_KEYS.MARKET_DATA_DOWN || stateKey === STATE_KEYS.MARKET_DATA_STALE) {
                return '行情能力已恢复';
            }
            if (stateKey === STATE_KEYS.TRADE_READONLY || stateKey === STATE_KEYS.TRADE_API_DOWN) {
                return '交易能力已恢复';
            }
            if (stateKey === STATE_KEYS.PORTFOLIO_READONLY) {
                return '持仓与账户能力已恢复';
            }
            if (stateKey === STATE_KEYS.SYSTEM_DEGRADED) {
                return '系统已恢复正常';
            }
            return `${stateKey} 已恢复`;
        }

        _mapLevelToToastTone(level) {
            if (level === 'critical') {
                return 'danger';
            }
            if (level === 'warning') {
                return 'warning';
            }
            return 'info';
        }

        _snapshotSnapshot() {
            return deepFreeze(cloneValue(this._snapshot));
        }

        _snapshotActionPolicy() {
            return {
                blockedActions: this._lastActionPolicy.blockedActions.slice(),
                readonlyActions: this._lastActionPolicy.readonlyActions.slice(),
            };
        }

        _restoreManagedActionBaselines() {
            const managedActionIds = Object.keys(this._managedActionBaselines);
            managedActionIds.forEach((actionId) => {
                if (!this._actionRegistry.has(actionId)) {
                    return;
                }
                this._actionRegistry.setEnabled({
                    actionId,
                    enabled: this._managedActionBaselines[actionId] === true,
                });
            });
            this._managedActionBaselines = {};
            this._lastActionPolicy = {
                blockedActions: [],
                readonlyActions: [],
            };
        }

        _emitIntent(eventName, payload) {
            try {
                if (typeof this._intentBus.emit === 'function') {
                    this._intentBus.emit(eventName, payload);
                    return;
                }
                if (typeof this._intentBus.dispatchIntent === 'function') {
                    this._intentBus.dispatchIntent(eventName, payload);
                }
            } catch (error) {
                this._reportError(`emit:${eventName}`, error);
            }
        }

        _reportError(label, error) {
            if (global.console && typeof global.console.error === 'function') {
                global.console.error(`[DegradedModeManager:${label}]`, error);
            }
        }
    }

    const degradedModeManagerInternal = new DegradedModeManagerImpl(
        global.IntentBus,
        global.GlobalStockStore || null,
        global.ActionRegistry
    );

    const degradedModeManagerPublicApi = Object.freeze({
        init: degradedModeManagerInternal.init.bind(degradedModeManagerInternal),
        dispose: degradedModeManagerInternal.dispose.bind(degradedModeManagerInternal),
        getSnapshot: degradedModeManagerInternal.getSnapshot.bind(degradedModeManagerInternal),
        hasState: degradedModeManagerInternal.hasState.bind(degradedModeManagerInternal),
        getState: degradedModeManagerInternal.getState.bind(degradedModeManagerInternal),
        setDegradedState: degradedModeManagerInternal.setDegradedState.bind(degradedModeManagerInternal),
        recoverState: degradedModeManagerInternal.recoverState.bind(degradedModeManagerInternal),
        recoverAll: degradedModeManagerInternal.recoverAll.bind(degradedModeManagerInternal),
        syncActionAvailability: degradedModeManagerInternal.syncActionAvailability.bind(degradedModeManagerInternal),
        emitUiSignals: degradedModeManagerInternal.emitUiSignals.bind(degradedModeManagerInternal),
    });

    global.DegradedModeManager = degradedModeManagerPublicApi;
})(window);
