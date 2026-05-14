(function attachPanelLifecycle(global) {
    'use strict';

    if (!global.IntentBus) {
        throw new Error('PanelLifecycle requires window.IntentBus');
    }

    if (!global.RightRailController) {
        throw new Error('PanelLifecycle requires window.RightRailController');
    }

    if (!global.GlobalStockStore) {
        throw new Error('PanelLifecycle requires window.GlobalStockStore');
    }

    const LIFECYCLE_EVENT_NAMES = Object.freeze({
        REGISTERED: 'panel-lifecycle:registered',
        UNREGISTERED: 'panel-lifecycle:unregistered',
        CHANGED: 'panel-lifecycle:changed',
        ROOT_MOUNTED: 'panel-lifecycle:root-mounted',
        ROOT_UNMOUNTED: 'panel-lifecycle:root-unmounted',
        PANEL_MOUNT_STARTED: 'panel-lifecycle:panel-mount-started',
        PANEL_MOUNTED: 'panel-lifecycle:panel-mounted',
        PANEL_ACTIVATED: 'panel-lifecycle:panel-activated',
        PANEL_UPDATED: 'panel-lifecycle:panel-updated',
        PANEL_DEACTIVATED: 'panel-lifecycle:panel-deactivated',
        PANEL_UNMOUNTED: 'panel-lifecycle:panel-unmounted',
        PANEL_DESTROYED: 'panel-lifecycle:panel-destroyed',
        PANEL_ERROR: 'panel-lifecycle:panel-error',
        SYNCED: 'panel-lifecycle:synced',
        RESET: 'panel-lifecycle:reset',
    });

    const CHANGE_REASONS = Object.freeze({
        REGISTER: 'register',
        REPLACE: 'replace',
        UNREGISTER: 'unregister',
        ROOT_MOUNT: 'root_mount',
        ROOT_UNMOUNT: 'root_unmount',
        SYNC: 'sync',
        RESET: 'reset',
    });

    const DEFAULT_TRACE_PREFIX = 'panel-lifecycle';

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
            const entries = Object.entries(value).map(([key, entryValue]) => [key, cloneValue(entryValue)]);
            return Object.fromEntries(entries);
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

    function createPanelLifecycleError(message, code) {
        const error = new Error(message);
        error.name = 'PanelLifecycleError';
        if (code) {
            error.code = code;
        }
        return error;
    }

    function getErrorShape(error, fallbackMessage) {
        if (error instanceof Error) {
            return {
                message: error.message || fallbackMessage,
                code: typeof error.code === 'string' ? error.code : null,
            };
        }

        if (typeof error === 'string' && error.trim()) {
            return {
                message: error,
                code: null,
            };
        }

        if (error && typeof error === 'object') {
            return {
                message: typeof error.message === 'string' && error.message ? error.message : fallbackMessage,
                code: typeof error.code === 'string' ? error.code : null,
            };
        }

        return {
            message: fallbackMessage,
            code: null,
        };
    }

    function createInitialState() {
        return {
            registeredPanels: {},
            activePanelId: null,
            mountedPanelId: null,
            mountedAt: null,
            rootMounted: false,
            lastError: null,
            meta: {
                lastUpdatedAt: null,
            },
        };
    }

    class PanelLifecycleImpl {
        constructor(intentBus, rightRailController, globalStockStore) {
            this._intentBus = intentBus;
            this._rightRailController = rightRailController;
            this._globalStockStore = globalStockStore;
            this._listeners = [];
            this._state = createInitialState();
            this._traceSequence = 0;
            this._root = null;
            this._panelDefinitions = new Map();
            this._currentInstance = null;
            this._currentInstancePanelId = null;
            this._currentInstanceActive = false;
            this._queuedRailSync = null;
            this._railSyncTimer = null;
            this._rightRailUnsubscribe = this._rightRailController.subscribe((state) => {
                this._queueRailSync({
                    source: 'right-rail-controller',
                    traceId: this._createTraceId(DEFAULT_TRACE_PREFIX),
                    state,
                });
            });
        }

        register(panelDefinition) {
            const normalized = this._normalizePanelDefinition(panelDefinition);
            if (this._panelDefinitions.has(normalized.id)) {
                throw createPanelLifecycleError(`Panel already registered: ${normalized.id}`, 'PANEL_ALREADY_REGISTERED');
            }

            this._panelDefinitions = new Map(this._panelDefinitions).set(normalized.id, normalized);
            this._setState({
                registeredPanels: this._buildRegisteredPanelsSnapshot(),
                meta: {
                    ...this._state.meta,
                    lastUpdatedAt: getNow(),
                },
            });
            this._emitEvent(LIFECYCLE_EVENT_NAMES.REGISTERED, {
                panelId: normalized.id,
                title: normalized.title,
            });
            this._emitEvent(LIFECYCLE_EVENT_NAMES.CHANGED, {
                reason: CHANGE_REASONS.REGISTER,
                panelId: normalized.id,
            });

            return {
                ok: true,
                panelId: normalized.id,
            };
        }

        registerMany(panelDefinitions) {
            if (!Array.isArray(panelDefinitions)) {
                throw createPanelLifecycleError('registerMany expects an array', 'INVALID_REGISTER_MANY_INPUT');
            }

            const normalizedDefinitions = panelDefinitions.map((panelDefinition) => {
                return this._normalizePanelDefinition(panelDefinition);
            });
            const nextDefinitions = new Map(this._panelDefinitions);
            const duplicateIds = [];

            normalizedDefinitions.forEach((panelDefinition) => {
                if (nextDefinitions.has(panelDefinition.id)) {
                    duplicateIds.push(panelDefinition.id);
                    return;
                }
                nextDefinitions.set(panelDefinition.id, panelDefinition);
            });

            if (duplicateIds.length > 0) {
                throw createPanelLifecycleError(
                    `Panel already registered: ${duplicateIds.join(', ')}`,
                    'PANEL_ALREADY_REGISTERED'
                );
            }

            this._panelDefinitions = nextDefinitions;
            this._setState({
                registeredPanels: this._buildRegisteredPanelsSnapshot(),
                meta: {
                    ...this._state.meta,
                    lastUpdatedAt: getNow(),
                },
            });

            const registered = normalizedDefinitions.map((panelDefinition) => panelDefinition.id);
            registered.forEach((panelId) => {
                const panel = this._panelDefinitions.get(panelId);
                this._emitEvent(LIFECYCLE_EVENT_NAMES.REGISTERED, {
                    panelId,
                    title: panel.title,
                });
            });
            this._emitEvent(LIFECYCLE_EVENT_NAMES.CHANGED, {
                reason: CHANGE_REASONS.REGISTER,
                panelIds: cloneValue(registered),
            });

            if (registered.includes(this._state.activePanelId)) {
                void this.syncWithRail({
                    source: 'panel-lifecycle:register-many',
                    traceId: this._createTraceId(DEFAULT_TRACE_PREFIX),
                });
            }

            return {
                ok: true,
                registered,
                rejected: [],
            };
        }

        replace(panelDefinition) {
            const normalized = this._normalizePanelDefinition(panelDefinition);
            this._panelDefinitions = new Map(this._panelDefinitions).set(normalized.id, normalized);
            this._setState({
                registeredPanels: this._buildRegisteredPanelsSnapshot(),
                meta: {
                    ...this._state.meta,
                    lastUpdatedAt: getNow(),
                },
            });
            this._emitEvent(LIFECYCLE_EVENT_NAMES.CHANGED, {
                reason: CHANGE_REASONS.REPLACE,
                panelId: normalized.id,
            });

            if (this._state.activePanelId === normalized.id || this._currentInstancePanelId === normalized.id) {
                void this.syncWithRail({
                    source: 'panel-lifecycle:replace',
                    traceId: this._createTraceId(DEFAULT_TRACE_PREFIX),
                });
            }

            return {
                ok: true,
                panelId: normalized.id,
            };
        }

        unregister(panelId) {
            const normalizedPanelId = this._normalizePanelId(panelId);
            if (!this._panelDefinitions.has(normalizedPanelId)) {
                return {
                    ok: false,
                    panelId: normalizedPanelId,
                    reason: 'panel_not_found',
                    code: 'PANEL_NOT_FOUND',
                };
            }

            if (this._currentInstancePanelId === normalizedPanelId) {
                void this.unmountCurrent({
                    destroy: true,
                    source: 'panel-lifecycle:unregister',
                    traceId: this._createTraceId(DEFAULT_TRACE_PREFIX),
                });
            }

            const nextDefinitions = new Map(this._panelDefinitions);
            nextDefinitions.delete(normalizedPanelId);
            this._panelDefinitions = nextDefinitions;
            this._setState({
                registeredPanels: this._buildRegisteredPanelsSnapshot(),
                meta: {
                    ...this._state.meta,
                    lastUpdatedAt: getNow(),
                },
            });
            this._emitEvent(LIFECYCLE_EVENT_NAMES.UNREGISTERED, {
                panelId: normalizedPanelId,
            });
            this._emitEvent(LIFECYCLE_EVENT_NAMES.CHANGED, {
                reason: CHANGE_REASONS.UNREGISTER,
                panelId: normalizedPanelId,
            });

            return {
                ok: true,
                panelId: normalizedPanelId,
                reason: null,
                code: null,
            };
        }

        get(panelId) {
            const normalizedPanelId = this._normalizePanelId(panelId);
            const definition = this._panelDefinitions.get(normalizedPanelId);
            return definition ? this._snapshotPanelSummary(definition) : null;
        }

        list(filters) {
            const normalizedFilters = this._normalizeListFilters(filters);
            return Array.from(this._panelDefinitions.values())
                .filter((definition) => this._matchesFilters(definition, normalizedFilters))
                .map((definition) => this._snapshotPanelSummary(definition));
        }

        has(panelId) {
            const normalizedPanelId = this._normalizePanelId(panelId);
            return this._panelDefinitions.has(normalizedPanelId);
        }

        getState() {
            return this._snapshotState();
        }

        subscribe(listener) {
            if (typeof listener !== 'function') {
                throw createPanelLifecycleError('Listener must be a function', 'INVALID_LISTENER');
            }

            this._listeners = [...this._listeners, listener];
            return () => {
                this._listeners = this._listeners.filter((item) => item !== listener);
            };
        }

        mountRoot(params) {
            const normalized = this._normalizeMountRootParams(params);
            this._root = normalized.root;
            this._setState({
                rootMounted: true,
                meta: {
                    ...this._state.meta,
                    lastUpdatedAt: getNow(),
                },
            });
            this._publishStoreSnapshot();
            this._emitEvent(LIFECYCLE_EVENT_NAMES.ROOT_MOUNTED, {
                rootMounted: true,
            });
            this._emitEvent(LIFECYCLE_EVENT_NAMES.CHANGED, {
                reason: CHANGE_REASONS.ROOT_MOUNT,
            });
            return {
                ok: true,
            };
        }

        async unmountRoot() {
            await this.unmountCurrent({
                destroy: true,
                source: 'panel-lifecycle:root-unmount',
                traceId: this._createTraceId(DEFAULT_TRACE_PREFIX),
            });
            this._root = null;
            this._setState({
                rootMounted: false,
                meta: {
                    ...this._state.meta,
                    lastUpdatedAt: getNow(),
                },
            });
            this._publishStoreSnapshot();
            this._emitEvent(LIFECYCLE_EVENT_NAMES.ROOT_UNMOUNTED, {
                rootMounted: false,
            });
            this._emitEvent(LIFECYCLE_EVENT_NAMES.CHANGED, {
                reason: CHANGE_REASONS.ROOT_UNMOUNT,
            });
            return {
                ok: true,
            };
        }

        buildPanelContext(params) {
            const normalized = this._normalizeBuildPanelContextParams(params);
            const railState = this._rightRailController.getState();
            const stockState = this._globalStockStore.getState();
            const activeStock = {
                code: stockState.identity.code,
                name: stockState.identity.name,
                market: stockState.identity.market,
                exchange: stockState.identity.exchange,
            };

            return this._snapshotValue({
                panelId: normalized.panelId,
                traceId: normalized.traceId,
                source: normalized.source,
                railState,
                stockState,
                activeStock,
                panelParams: cloneValue(railState.panelParams),
                root: this._root,
                mountedAt: this._state.mountedAt,
                updatedAt: getNow(),
            });
        }

        async syncWithRail(params) {
            const normalized = this._normalizeSimpleParams(params);
            const railState = this._rightRailController.getState();
            const activePanelId = railState.activePanelId;

            this._setState({
                activePanelId,
                meta: {
                    ...this._state.meta,
                    lastUpdatedAt: getNow(),
                },
            });

            if (!railState.isOpen) {
                if (this._currentInstanceActive) {
                    await this.deactivateCurrent({
                        source: normalized.source,
                        traceId: normalized.traceId,
                    });
                }
                if (!activePanelId && this._currentInstancePanelId) {
                    await this.unmountCurrent({
                        destroy: false,
                        source: normalized.source,
                        traceId: normalized.traceId,
                    });
                }
                this._emitEvent(LIFECYCLE_EVENT_NAMES.SYNCED, {
                    activePanelId: this._state.activePanelId,
                    mountedPanelId: this._state.mountedPanelId,
                    source: normalized.source,
                    traceId: normalized.traceId,
                });
                return {
                    ok: true,
                    activePanelId: this._state.activePanelId,
                    mountedPanelId: this._state.mountedPanelId,
                    traceId: normalized.traceId,
                };
            }

            if (!activePanelId) {
                if (this._currentInstanceActive) {
                    await this.deactivateCurrent({
                        source: normalized.source,
                        traceId: normalized.traceId,
                    });
                }
                if (this._currentInstancePanelId) {
                    await this.unmountCurrent({
                        destroy: false,
                        source: normalized.source,
                        traceId: normalized.traceId,
                    });
                }
                this._emitEvent(LIFECYCLE_EVENT_NAMES.SYNCED, {
                    activePanelId: null,
                    mountedPanelId: this._state.mountedPanelId,
                    source: normalized.source,
                    traceId: normalized.traceId,
                });
                return {
                    ok: true,
                    activePanelId: this._state.activePanelId,
                    mountedPanelId: this._state.mountedPanelId,
                    traceId: normalized.traceId,
                };
            }

            if (!this._root) {
                this._emitEvent(LIFECYCLE_EVENT_NAMES.SYNCED, {
                    activePanelId: this._state.activePanelId,
                    mountedPanelId: this._state.mountedPanelId,
                    source: normalized.source,
                    traceId: normalized.traceId,
                });
                return {
                    ok: true,
                    activePanelId: this._state.activePanelId,
                    mountedPanelId: this._state.mountedPanelId,
                    traceId: normalized.traceId,
                };
            }

            const definition = this._panelDefinitions.get(activePanelId);
            if (!definition) {
                const error = {
                    message: `Panel not registered: ${activePanelId}`,
                    code: 'PANEL_NOT_REGISTERED',
                };
                this._setState({
                    lastError: error,
                    meta: {
                        ...this._state.meta,
                        lastUpdatedAt: getNow(),
                    },
                });
                this._emitEvent(LIFECYCLE_EVENT_NAMES.PANEL_ERROR, {
                    panelId: activePanelId,
                    phase: 'sync',
                    error: cloneValue(error),
                    source: normalized.source,
                    traceId: normalized.traceId,
                });
                return {
                    ok: true,
                    activePanelId: this._state.activePanelId,
                    mountedPanelId: this._state.mountedPanelId,
                    traceId: normalized.traceId,
                };
            }

            if (this._currentInstancePanelId && this._currentInstancePanelId !== activePanelId) {
                await this.deactivateCurrent({
                    source: normalized.source,
                    traceId: normalized.traceId,
                });
                await this.unmountCurrent({
                    destroy: false,
                    source: normalized.source,
                    traceId: normalized.traceId,
                });
            }

            if (this._currentInstancePanelId !== activePanelId) {
                await this._mountPanel(definition, normalized.source, normalized.traceId);
            }

            await this.activateCurrent({
                source: normalized.source,
                traceId: normalized.traceId,
            });
            await this.updateCurrent({
                source: normalized.source,
                traceId: normalized.traceId,
            });

            this._emitEvent(LIFECYCLE_EVENT_NAMES.SYNCED, {
                activePanelId: this._state.activePanelId,
                mountedPanelId: this._state.mountedPanelId,
                source: normalized.source,
                traceId: normalized.traceId,
            });

            return {
                ok: true,
                activePanelId: this._state.activePanelId,
                mountedPanelId: this._state.mountedPanelId,
                traceId: normalized.traceId,
            };
        }

        async activateCurrent(params) {
            const normalized = this._normalizeSimpleParams(params);
            if (!this._currentInstancePanelId || !this._panelDefinitions.has(this._currentInstancePanelId)) {
                return {
                    ok: false,
                    activePanelId: this._state.activePanelId,
                    mountedPanelId: this._state.mountedPanelId,
                    traceId: normalized.traceId,
                    reason: 'panel_not_mounted',
                    code: 'PANEL_NOT_MOUNTED',
                };
            }

            if (this._currentInstanceActive) {
                return {
                    ok: true,
                    activePanelId: this._state.activePanelId,
                    mountedPanelId: this._state.mountedPanelId,
                    traceId: normalized.traceId,
                    reason: null,
                    code: null,
                };
            }

            const context = this.buildPanelContext({
                panelId: this._currentInstancePanelId,
                source: normalized.source,
                traceId: normalized.traceId,
            });

            const result = await this._invokeLifecycleMethod('activate', this._currentInstance, context, normalized.source, normalized.traceId);
            if (!result.ok) {
                return {
                    ok: false,
                    activePanelId: this._state.activePanelId,
                    mountedPanelId: this._state.mountedPanelId,
                    traceId: normalized.traceId,
                    reason: 'panel_activate_failed',
                    code: result.error.code,
                };
            }

            this._currentInstanceActive = true;
            this._emitEvent(LIFECYCLE_EVENT_NAMES.PANEL_ACTIVATED, {
                panelId: this._currentInstancePanelId,
                source: normalized.source,
                traceId: normalized.traceId,
            });
            return {
                ok: true,
                activePanelId: this._state.activePanelId,
                mountedPanelId: this._state.mountedPanelId,
                traceId: normalized.traceId,
                reason: null,
                code: null,
            };
        }

        async updateCurrent(params) {
            const normalized = this._normalizeSimpleParams(params);
            if (!this._currentInstancePanelId) {
                return {
                    ok: false,
                    mountedPanelId: null,
                    traceId: normalized.traceId,
                };
            }

            const context = this.buildPanelContext({
                panelId: this._currentInstancePanelId,
                source: normalized.source,
                traceId: normalized.traceId,
            });
            const result = await this._invokeLifecycleMethod('update', this._currentInstance, context, normalized.source, normalized.traceId);
            if (!result.ok) {
                return {
                    ok: false,
                    mountedPanelId: this._state.mountedPanelId,
                    traceId: normalized.traceId,
                };
            }

            this._emitEvent(LIFECYCLE_EVENT_NAMES.PANEL_UPDATED, {
                panelId: this._currentInstancePanelId,
                source: normalized.source,
                traceId: normalized.traceId,
            });
            return {
                ok: true,
                mountedPanelId: this._state.mountedPanelId,
                traceId: normalized.traceId,
            };
        }

        async deactivateCurrent(params) {
            const normalized = this._normalizeSimpleParams(params);
            if (!this._currentInstancePanelId || !this._currentInstanceActive) {
                return {
                    ok: true,
                    mountedPanelId: this._state.mountedPanelId,
                    traceId: normalized.traceId,
                };
            }

            const context = this.buildPanelContext({
                panelId: this._currentInstancePanelId,
                source: normalized.source,
                traceId: normalized.traceId,
            });
            await this._invokeLifecycleMethod('deactivate', this._currentInstance, context, normalized.source, normalized.traceId);
            this._currentInstanceActive = false;
            this._emitEvent(LIFECYCLE_EVENT_NAMES.PANEL_DEACTIVATED, {
                panelId: this._currentInstancePanelId,
                source: normalized.source,
                traceId: normalized.traceId,
            });
            return {
                ok: true,
                mountedPanelId: this._state.mountedPanelId,
                traceId: normalized.traceId,
            };
        }

        async unmountCurrent(params) {
            const normalized = this._normalizeUnmountCurrentParams(params);
            if (!this._currentInstancePanelId) {
                return {
                    ok: true,
                    mountedPanelId: null,
                    traceId: normalized.traceId,
                };
            }

            const panelId = this._currentInstancePanelId;
            const context = this.buildPanelContext({
                panelId,
                source: normalized.source,
                traceId: normalized.traceId,
            });

            if (this._currentInstanceActive) {
                await this._invokeLifecycleMethod('deactivate', this._currentInstance, context, normalized.source, normalized.traceId);
                this._currentInstanceActive = false;
                this._emitEvent(LIFECYCLE_EVENT_NAMES.PANEL_DEACTIVATED, {
                    panelId,
                    source: normalized.source,
                    traceId: normalized.traceId,
                });
            }

            await this._invokeLifecycleMethod('unmount', this._currentInstance, context, normalized.source, normalized.traceId);
            this._emitEvent(LIFECYCLE_EVENT_NAMES.PANEL_UNMOUNTED, {
                panelId,
                source: normalized.source,
                traceId: normalized.traceId,
            });

            if (normalized.destroy === true) {
                await this._invokeLifecycleMethod('destroy', this._currentInstance, context, normalized.source, normalized.traceId);
                this._emitEvent(LIFECYCLE_EVENT_NAMES.PANEL_DESTROYED, {
                    panelId,
                    source: normalized.source,
                    traceId: normalized.traceId,
                });
            }

            this._currentInstance = null;
            this._currentInstancePanelId = null;
            this._setState({
                mountedPanelId: null,
                mountedAt: null,
                meta: {
                    ...this._state.meta,
                    lastUpdatedAt: getNow(),
                },
            });
            this._publishStoreSnapshot();

            return {
                ok: true,
                mountedPanelId: null,
                traceId: normalized.traceId,
            };
        }

        createTraceId(prefix) {
            return this._createTraceId(prefix);
        }

        async reset() {
            await this.unmountCurrent({
                destroy: true,
                source: 'panel-lifecycle:reset',
                traceId: this._createTraceId(DEFAULT_TRACE_PREFIX),
            });
            const nextState = createInitialState();
            nextState.rootMounted = this._root != null;
            nextState.registeredPanels = this._buildRegisteredPanelsSnapshot();
            nextState.meta.lastUpdatedAt = getNow();
            this._setWholeState(nextState);
            this._emitEvent(LIFECYCLE_EVENT_NAMES.RESET, {
                ok: true,
            });
            this._emitEvent(LIFECYCLE_EVENT_NAMES.CHANGED, {
                reason: CHANGE_REASONS.RESET,
            });
            return {
                ok: true,
            };
        }

        async _mountPanel(definition, source, traceId) {
            if (!definition) {
                return;
            }

            const visibilityContext = this.buildPanelContext({
                panelId: definition.id,
                source,
                traceId,
            });
            if (typeof definition.visible === 'function') {
                const visibleResult = await this._callDefinitionVisible(definition, visibilityContext, source, traceId);
                if (visibleResult.ok !== true || visibleResult.visible !== true) {
                    return;
                }
            }

            const context = this.buildPanelContext({
                panelId: definition.id,
                source,
                traceId,
            });
            this._emitEvent(LIFECYCLE_EVENT_NAMES.PANEL_MOUNT_STARTED, {
                panelId: definition.id,
                source,
                traceId,
            });

            try {
                const maybeInstance = await definition.mount(context);
                const instance = isPlainObject(maybeInstance) ? maybeInstance : {};
                this._currentInstance = instance;
                this._currentInstancePanelId = definition.id;
                this._currentInstanceActive = false;
                this._setState({
                    mountedPanelId: definition.id,
                    mountedAt: getNow(),
                    lastError: null,
                    meta: {
                        ...this._state.meta,
                        lastUpdatedAt: getNow(),
                    },
                });
                this._publishStoreSnapshot();
                this._emitEvent(LIFECYCLE_EVENT_NAMES.PANEL_MOUNTED, {
                    panelId: definition.id,
                    source,
                    traceId,
                });
            } catch (error) {
                const errorShape = getErrorShape(error, 'Panel mount failed');
                this._setState({
                    lastError: errorShape,
                    meta: {
                        ...this._state.meta,
                        lastUpdatedAt: getNow(),
                    },
                });
                this._emitEvent(LIFECYCLE_EVENT_NAMES.PANEL_ERROR, {
                    panelId: definition.id,
                    phase: 'mount',
                    error: cloneValue(errorShape),
                    source,
                    traceId,
                });
            }
        }

        async _invokeLifecycleMethod(methodName, instance, context, source, traceId) {
            if (!instance || typeof instance[methodName] !== 'function') {
                return { ok: true, error: null };
            }

            try {
                await instance[methodName](context);
                return { ok: true, error: null };
            } catch (error) {
                const errorShape = getErrorShape(error, `Panel ${methodName} failed`);
                this._setState({
                    lastError: errorShape,
                    meta: {
                        ...this._state.meta,
                        lastUpdatedAt: getNow(),
                    },
                });
                this._emitEvent(LIFECYCLE_EVENT_NAMES.PANEL_ERROR, {
                    panelId: context.panelId,
                    phase: methodName,
                    error: cloneValue(errorShape),
                    source,
                    traceId,
                });
                return { ok: false, error: errorShape };
            }
        }

        async _callDefinitionVisible(definition, context, source, traceId) {
            try {
                return {
                    ok: true,
                    visible: definition.visible(context) === true,
                };
            } catch (error) {
                const errorShape = getErrorShape(error, 'Panel visibility evaluation failed');
                this._setState({
                    lastError: errorShape,
                    meta: {
                        ...this._state.meta,
                        lastUpdatedAt: getNow(),
                    },
                });
                this._emitEvent(LIFECYCLE_EVENT_NAMES.PANEL_ERROR, {
                    panelId: definition.id,
                    phase: 'visible',
                    error: cloneValue(errorShape),
                    source,
                    traceId,
                });
                return {
                    ok: false,
                    visible: false,
                };
            }
        }

        _buildRegisteredPanelsSnapshot() {
            const entries = Array.from(this._panelDefinitions.values()).map((definition) => {
                return [definition.id, this._snapshotPanelSummary(definition)];
            });
            return Object.fromEntries(entries);
        }

        _snapshotPanelSummary(definition) {
            return this._snapshotValue({
                id: definition.id,
                title: definition.title,
                order: definition.order,
                metadata: cloneValue(definition.metadata),
            });
        }

        _snapshotState() {
            return this._snapshotValue(this._state);
        }

        _snapshotValue(value) {
            return deepFreeze(cloneValue(value));
        }

        _setWholeState(nextState) {
            this._state = nextState;
            this._notifyListeners();
        }

        _setState(partialState) {
            const nextState = {
                ...this._state,
                ...partialState,
                meta: partialState.meta ? {
                    ...this._state.meta,
                    ...partialState.meta,
                } : this._state.meta,
            };
            this._state = nextState;
            this._notifyListeners();
        }

        _notifyListeners() {
            const snapshot = this._snapshotState();
            this._listeners.forEach((listener) => {
                listener(snapshot);
            });
        }

        _emitEvent(eventName, payload) {
            this._intentBus.emit(eventName, cloneValue(payload));
        }

        _matchesFilters(definition, filters) {
            if (filters.query) {
                const haystack = [
                    definition.id,
                    definition.title,
                    ...(Array.isArray(definition.keywords) ? definition.keywords : []),
                ].join(' ').toLowerCase();
                if (!haystack.includes(filters.query)) {
                    return false;
                }
            }

            if (!filters.visibleOnly) {
                return true;
            }

            const railState = this._rightRailController.getState();
            const stockState = this._globalStockStore.getState();
            const activeStock = {
                code: stockState.identity.code,
                name: stockState.identity.name,
                market: stockState.identity.market,
                exchange: stockState.identity.exchange,
            };
            const visibilityContext = this._snapshotValue({
                panelId: definition.id,
                traceId: this._createTraceId(DEFAULT_TRACE_PREFIX),
                source: 'panel-lifecycle:list',
                railState,
                stockState,
                activeStock,
                panelParams: cloneValue(railState.panelParams),
                root: this._root,
                mountedAt: this._state.mountedAt,
                updatedAt: getNow(),
            });

            if (typeof definition.visible !== 'function') {
                return true;
            }

            try {
                return definition.visible(visibilityContext) === true;
            } catch (error) {
                return false;
            }
        }

        _createTraceId(prefix) {
            const safePrefix = typeof prefix === 'string' && prefix.trim() ? prefix.trim() : DEFAULT_TRACE_PREFIX;
            if (typeof this._intentBus.createTraceId === 'function') {
                return this._intentBus.createTraceId(safePrefix);
            }
            this._traceSequence += 1;
            return `${safePrefix}-${getNow()}-${this._traceSequence}`;
        }

        _normalizePanelDefinition(panelDefinition) {
            if (!isPlainObject(panelDefinition)) {
                throw createPanelLifecycleError('Panel definition must be a plain object', 'INVALID_PANEL_DEFINITION');
            }

            const id = this._normalizePanelId(panelDefinition.id);
            const title = typeof panelDefinition.title === 'string' ? panelDefinition.title.trim() : '';
            if (!title) {
                throw createPanelLifecycleError('Panel title is required', 'INVALID_PANEL_TITLE');
            }

            if (typeof panelDefinition.mount !== 'function') {
                throw createPanelLifecycleError('Panel mount function is required', 'INVALID_PANEL_MOUNT');
            }

            if (panelDefinition.visible != null && typeof panelDefinition.visible !== 'function') {
                throw createPanelLifecycleError('Panel visible must be a function', 'INVALID_PANEL_VISIBLE');
            }

            return {
                id,
                title,
                mount: panelDefinition.mount,
                visible: panelDefinition.visible || null,
                order: Number.isFinite(Number(panelDefinition.order)) ? Number(panelDefinition.order) : 0,
                metadata: isPlainObject(panelDefinition.metadata) ? cloneValue(panelDefinition.metadata) : null,
                keywords: Array.isArray(panelDefinition.keywords)
                    ? panelDefinition.keywords.map((item) => String(item)).filter((item) => item.trim() !== '')
                    : [],
            };
        }

        _normalizePanelId(panelId) {
            const normalizedPanelId = typeof panelId === 'string' ? panelId.trim() : '';
            if (!normalizedPanelId) {
                throw createPanelLifecycleError('Panel ID is required', 'INVALID_PANEL_ID');
            }
            return normalizedPanelId;
        }

        _normalizeListFilters(filters) {
            const safeFilters = isPlainObject(filters) ? filters : {};
            return {
                visibleOnly: safeFilters.visibleOnly === true,
                query: typeof safeFilters.query === 'string' && safeFilters.query.trim()
                    ? safeFilters.query.trim().toLowerCase()
                    : null,
            };
        }

        _normalizeMountRootParams(params) {
            if (!isPlainObject(params) || !params.root || typeof params.root.setAttribute !== 'function') {
                throw createPanelLifecycleError('mountRoot requires a valid root element', 'INVALID_MOUNT_ROOT_PARAMS');
            }
            return {
                root: params.root,
            };
        }

        _normalizeBuildPanelContextParams(params) {
            if (!isPlainObject(params)) {
                throw createPanelLifecycleError('buildPanelContext params must be a plain object', 'INVALID_BUILD_PANEL_CONTEXT_PARAMS');
            }
            return {
                panelId: this._normalizePanelId(params.panelId),
                source: typeof params.source === 'string' && params.source.trim() ? params.source.trim() : null,
                traceId: typeof params.traceId === 'string' && params.traceId.trim()
                    ? params.traceId.trim()
                    : this._createTraceId(DEFAULT_TRACE_PREFIX),
            };
        }

        _normalizeSimpleParams(params) {
            const safeParams = isPlainObject(params) ? params : {};
            return {
                source: typeof safeParams.source === 'string' && safeParams.source.trim() ? safeParams.source.trim() : null,
                traceId: typeof safeParams.traceId === 'string' && safeParams.traceId.trim()
                    ? safeParams.traceId.trim()
                    : this._createTraceId(DEFAULT_TRACE_PREFIX),
            };
        }

        _normalizeUnmountCurrentParams(params) {
            const safeParams = isPlainObject(params) ? params : {};
            return {
                destroy: safeParams.destroy === true,
                source: typeof safeParams.source === 'string' && safeParams.source.trim() ? safeParams.source.trim() : null,
                traceId: typeof safeParams.traceId === 'string' && safeParams.traceId.trim()
                    ? safeParams.traceId.trim()
                    : this._createTraceId(DEFAULT_TRACE_PREFIX),
            };
        }

        _queueRailSync(params) {
            const safeParams = isPlainObject(params) ? params : {};
            this._queuedRailSync = {
                source: typeof safeParams.source === 'string' && safeParams.source.trim() ? safeParams.source.trim() : null,
                traceId: typeof safeParams.traceId === 'string' && safeParams.traceId.trim()
                    ? safeParams.traceId.trim()
                    : this._createTraceId(DEFAULT_TRACE_PREFIX),
            };

            if (this._railSyncTimer != null) {
                return;
            }

            this._railSyncTimer = global.setTimeout(() => {
                this._railSyncTimer = null;
                const queued = this._queuedRailSync;
                this._queuedRailSync = null;
                if (!queued) {
                    return;
                }
                void this.syncWithRail(queued);
            }, 0);
        }

        _publishStoreSnapshot() {
            if (!this._globalStockStore || typeof this._globalStockStore.patchUI !== 'function' || typeof this._globalStockStore.getState !== 'function') {
                return;
            }

            const currentStore = this._globalStockStore.getState();
            const currentUi = currentStore && currentStore.ui ? currentStore.ui : null;
            const nextMountedPanelId = this._state.mountedPanelId;
            const nextRootMounted = this._state.rootMounted === true;
            const currentMountedPanelId = currentUi && typeof currentUi.mountedPanelId === 'string' ? currentUi.mountedPanelId : null;
            const currentRootMounted = currentUi && currentUi.rootMounted === true;

            if (currentMountedPanelId === nextMountedPanelId && currentRootMounted === nextRootMounted) {
                return;
            }

            this._globalStockStore.patchUI({
                patch: {
                    mountedPanelId: nextMountedPanelId,
                    rootMounted: nextRootMounted,
                },
                source: 'panel-lifecycle:store-sync',
            });
        }
    }

    const panelLifecycleInternal = new PanelLifecycleImpl(
        global.IntentBus,
        global.RightRailController,
        global.GlobalStockStore
    );

    const panelLifecyclePublicApi = Object.freeze({
        register: panelLifecycleInternal.register.bind(panelLifecycleInternal),
        registerMany: panelLifecycleInternal.registerMany.bind(panelLifecycleInternal),
        replace: panelLifecycleInternal.replace.bind(panelLifecycleInternal),
        unregister: panelLifecycleInternal.unregister.bind(panelLifecycleInternal),
        get: panelLifecycleInternal.get.bind(panelLifecycleInternal),
        list: panelLifecycleInternal.list.bind(panelLifecycleInternal),
        has: panelLifecycleInternal.has.bind(panelLifecycleInternal),
        getState: panelLifecycleInternal.getState.bind(panelLifecycleInternal),
        subscribe: panelLifecycleInternal.subscribe.bind(panelLifecycleInternal),
        mountRoot: panelLifecycleInternal.mountRoot.bind(panelLifecycleInternal),
        unmountRoot: panelLifecycleInternal.unmountRoot.bind(panelLifecycleInternal),
        buildPanelContext: panelLifecycleInternal.buildPanelContext.bind(panelLifecycleInternal),
        syncWithRail: panelLifecycleInternal.syncWithRail.bind(panelLifecycleInternal),
        activateCurrent: panelLifecycleInternal.activateCurrent.bind(panelLifecycleInternal),
        updateCurrent: panelLifecycleInternal.updateCurrent.bind(panelLifecycleInternal),
        deactivateCurrent: panelLifecycleInternal.deactivateCurrent.bind(panelLifecycleInternal),
        unmountCurrent: panelLifecycleInternal.unmountCurrent.bind(panelLifecycleInternal),
        createTraceId: panelLifecycleInternal.createTraceId.bind(panelLifecycleInternal),
        reset: panelLifecycleInternal.reset.bind(panelLifecycleInternal),
    });

    global.PanelLifecycle = panelLifecyclePublicApi;
})(window);
