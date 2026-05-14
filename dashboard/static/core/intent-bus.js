(function attachIntentBus(global) {
    'use strict';

    const EVENT_NAMES = Object.freeze({
        DISPATCH: 'intent:dispatch',
        START: 'intent:start',
        SUCCESS: 'intent:success',
        FAIL: 'intent:fail',
        TIMEOUT: 'intent:timeout',
        ROLLBACK_START: 'intent:rollback:start',
        ROLLBACK_SUCCESS: 'intent:rollback:success',
        ROLLBACK_FAIL: 'intent:rollback:fail',
        SETTLED: 'intent:settled',
    });

    const FAILURE_REASONS = Object.freeze({
        TIMEOUT: 'timeout',
        HANDLER_ERROR: 'handler_error',
        CANCELLED: 'cancelled',
        UNKNOWN: 'unknown',
    });

    const RESULT_STATUS = Object.freeze({
        SUCCESS: 'success',
        FAILED: 'failed',
        TIMEOUT: 'timeout',
        ROLLBACK_FAILED: 'rollback_failed',
    });

    const DEFAULT_TRACE_PREFIX = 'intent';

    function getNow() {
        return Date.now();
    }

    function isPlainObject(value) {
        return Object.prototype.toString.call(value) === '[object Object]';
    }

    function getErrorShape(error, fallbackMessage) {
        if (error instanceof Error) {
            return {
                name: error.name || 'Error',
                message: error.message || fallbackMessage,
                code: typeof error.code === 'string' ? error.code : undefined,
            };
        }

        if (typeof error === 'string' && error.trim()) {
            return {
                name: 'Error',
                message: error,
                code: undefined,
            };
        }

        if (error && typeof error === 'object') {
            return {
                name: typeof error.name === 'string' && error.name ? error.name : 'Error',
                message: typeof error.message === 'string' && error.message ? error.message : fallbackMessage,
                code: typeof error.code === 'string' ? error.code : undefined,
            };
        }

        return {
            name: 'Error',
            message: fallbackMessage,
            code: undefined,
        };
    }

    function createIntentError(message, code, name) {
        const error = new Error(message);
        error.name = name || 'IntentBusError';
        if (code) {
            error.code = code;
        }
        return error;
    }

    function clonePayload(value) {
        if (value === undefined) {
            return undefined;
        }

        if (Array.isArray(value)) {
            return value.slice();
        }

        if (isPlainObject(value)) {
            return { ...value };
        }

        return value;
    }

    class IntentBusImpl {
        constructor() {
            this._eventHandlers = new Map();
            this._pendingIntents = new Map();
            this._sequence = 0;
        }

        on(eventName, handler) {
            this._assertEventName(eventName);
            this._assertHandler(handler);

            const currentHandlers = this._eventHandlers.get(eventName) || [];
            const nextHandlers = [...currentHandlers, handler];
            this._eventHandlers.set(eventName, nextHandlers);

            return () => {
                this.off(eventName, handler);
            };
        }

        off(eventName, handler) {
            this._assertEventName(eventName);
            this._assertHandler(handler);

            const currentHandlers = this._eventHandlers.get(eventName);
            if (!currentHandlers || currentHandlers.length === 0) {
                return;
            }

            const nextHandlers = currentHandlers.filter((item) => item !== handler);
            if (nextHandlers.length === 0) {
                this._eventHandlers.delete(eventName);
                return;
            }

            this._eventHandlers.set(eventName, nextHandlers);
        }

        once(eventName, handler) {
            this._assertEventName(eventName);
            this._assertHandler(handler);

            const wrappedHandler = (payload) => {
                this.off(eventName, wrappedHandler);
                handler(payload);
            };

            return this.on(eventName, wrappedHandler);
        }

        emit(eventName, payload) {
            this._assertEventName(eventName);

            const handlers = this._eventHandlers.get(eventName);
            if (!handlers || handlers.length === 0) {
                return;
            }

            const snapshot = handlers.slice();
            snapshot.forEach((handler) => {
                try {
                    handler(payload);
                } catch (error) {
                    this._reportHandlerError(eventName, error);
                }
            });
        }

        async _runIntentHandlers(eventName, payload) {
            this._assertEventName(eventName);

            const handlers = this._eventHandlers.get(eventName);
            if (!handlers || handlers.length === 0) {
                return;
            }

            const snapshot = handlers.slice();
            for (const handler of snapshot) {
                await handler(payload);
            }
        }

        async dispatch(intentDescriptor) {
            const descriptor = this._normalizeIntentDescriptor(intentDescriptor);
            const startedAt = getNow();
            const pendingRecord = {
                traceId: descriptor.traceId,
                type: descriptor.type,
                source: descriptor.source,
                target: descriptor.target,
                timeoutMs: descriptor.timeoutMs,
                startedAt,
                status: 'pending',
            };

            const executionState = {
                descriptor,
                startedAt,
                finishedAt: null,
                timeoutId: null,
                isSettled: false,
                timeoutTriggered: false,
                handlerFinished: false,
            };

            this._pendingIntents = new Map(this._pendingIntents).set(descriptor.traceId, pendingRecord);

            this.emit(EVENT_NAMES.DISPATCH, {
                traceId: descriptor.traceId,
                type: descriptor.type,
                payload: descriptor.payload,
                source: descriptor.source,
                target: descriptor.target,
                timeoutMs: descriptor.timeoutMs,
                meta: descriptor.meta,
                dispatchedAt: startedAt,
            });

            this.emit(EVENT_NAMES.START, {
                traceId: descriptor.traceId,
                type: descriptor.type,
                payload: descriptor.payload,
                source: descriptor.source,
                target: descriptor.target,
                timeoutMs: descriptor.timeoutMs,
                startedAt,
            });

            const timeoutPromise = new Promise((_, reject) => {
                executionState.timeoutId = setTimeout(() => {
                    executionState.timeoutTriggered = true;
                    const error = createIntentError(
                        `Intent timed out after ${descriptor.timeoutMs}ms`,
                        'INTENT_TIMEOUT',
                        'IntentTimeoutError'
                    );
                    reject(error);
                }, descriptor.timeoutMs);
            });

            const handlerPromise = this._runIntentHandlers(
                descriptor.type,
                this._buildIntentEventPayload(descriptor, startedAt)
            ).then(() => {
                executionState.handlerFinished = true;
                return undefined;
            });

            try {
                await Promise.race([handlerPromise, timeoutPromise]);

                const successResult = this._finalizeSuccess(executionState);
                return successResult;
            } catch (error) {
                const failureReason = executionState.timeoutTriggered
                    ? FAILURE_REASONS.TIMEOUT
                    : FAILURE_REASONS.HANDLER_ERROR;
                const failureResult = await this._finalizeFailure(executionState, error, failureReason);
                return failureResult;
            } finally {
                this._clearTimeout(executionState);
                void handlerPromise.catch(() => undefined);
            }
        }

        getPending(traceId) {
            if (traceId === undefined) {
                return Array.from(this._pendingIntents.values()).map((item) => ({ ...item }));
            }

            if (typeof traceId !== 'string' || traceId.trim() === '') {
                return null;
            }

            const record = this._pendingIntents.get(traceId);
            return record ? { ...record } : null;
        }

        hasPending(traceId) {
            if (typeof traceId !== 'string' || traceId.trim() === '') {
                return false;
            }

            return this._pendingIntents.has(traceId);
        }

        createTraceId(prefix) {
            const safePrefix = typeof prefix === 'string' && prefix.trim() ? prefix.trim() : DEFAULT_TRACE_PREFIX;
            this._sequence += 1;
            return `${safePrefix}-${getNow()}-${this._sequence}`;
        }

        _normalizeIntentDescriptor(intentDescriptor) {
            if (!isPlainObject(intentDescriptor)) {
                throw createIntentError('Intent descriptor must be a plain object', 'INVALID_INTENT_DESCRIPTOR');
            }

            const type = typeof intentDescriptor.type === 'string' ? intentDescriptor.type.trim() : '';
            if (!type) {
                throw createIntentError('Intent type is required', 'INVALID_INTENT_TYPE');
            }

            const traceId = typeof intentDescriptor.traceId === 'string' ? intentDescriptor.traceId.trim() : '';
            if (!traceId) {
                throw createIntentError('Intent traceId is required', 'INVALID_TRACE_ID');
            }

            if (this.hasPending(traceId)) {
                throw createIntentError(`Intent traceId already pending: ${traceId}`, 'DUPLICATE_TRACE_ID');
            }

            const timeoutMs = Number(intentDescriptor.timeoutMs);
            if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
                throw createIntentError('Intent timeoutMs must be a positive number', 'INVALID_TIMEOUT');
            }

            const onFail = isPlainObject(intentDescriptor.onFail) ? { ...intentDescriptor.onFail } : null;
            if (!onFail || typeof onFail.rollback !== 'function') {
                throw createIntentError('Intent onFail.rollback is required', 'INVALID_ROLLBACK');
            }

            return {
                type,
                payload: clonePayload(intentDescriptor.payload),
                traceId,
                timeoutMs,
                source: typeof intentDescriptor.source === 'string' && intentDescriptor.source.trim()
                    ? intentDescriptor.source.trim()
                    : undefined,
                target: typeof intentDescriptor.target === 'string' && intentDescriptor.target.trim()
                    ? intentDescriptor.target.trim()
                    : null,
                meta: isPlainObject(intentDescriptor.meta) ? { ...intentDescriptor.meta } : undefined,
                onFail: {
                    rollback: onFail.rollback,
                    label: typeof onFail.label === 'string' && onFail.label.trim() ? onFail.label.trim() : undefined,
                },
            };
        }

        _buildIntentEventPayload(descriptor, startedAt) {
            return {
                traceId: descriptor.traceId,
                type: descriptor.type,
                payload: descriptor.payload,
                source: descriptor.source,
                target: descriptor.target,
                timeoutMs: descriptor.timeoutMs,
                meta: descriptor.meta,
                startedAt,
            };
        }

        _finalizeSuccess(executionState) {
            if (executionState.isSettled) {
                return this._buildSettledResult(executionState, RESULT_STATUS.SUCCESS, undefined, {
                    attempted: false,
                    ok: false,
                });
            }

            executionState.isSettled = true;
            executionState.finishedAt = getNow();
            this._clearTimeout(executionState);
            this._removePending(executionState.descriptor.traceId);

            const successPayload = {
                traceId: executionState.descriptor.traceId,
                type: executionState.descriptor.type,
                payload: executionState.descriptor.payload,
                source: executionState.descriptor.source,
                target: executionState.descriptor.target,
                data: undefined,
                startedAt: executionState.startedAt,
                finishedAt: executionState.finishedAt,
                durationMs: executionState.finishedAt - executionState.startedAt,
            };

            this.emit(EVENT_NAMES.SUCCESS, successPayload);
            this.emit(EVENT_NAMES.SETTLED, {
                traceId: executionState.descriptor.traceId,
                type: executionState.descriptor.type,
                status: RESULT_STATUS.SUCCESS,
                startedAt: executionState.startedAt,
                finishedAt: executionState.finishedAt,
                durationMs: executionState.finishedAt - executionState.startedAt,
            });

            return this._buildSettledResult(executionState, RESULT_STATUS.SUCCESS, undefined, {
                attempted: false,
                ok: false,
            });
        }

        async _finalizeFailure(executionState, error, reason) {
            if (executionState.isSettled) {
                return this._buildSettledResult(executionState, RESULT_STATUS.FAILED, getErrorShape(error, 'Intent failed'), {
                    attempted: false,
                    ok: false,
                });
            }

            executionState.isSettled = true;
            executionState.finishedAt = getNow();
            this._clearTimeout(executionState);
            this._removePending(executionState.descriptor.traceId);

            const errorShape = getErrorShape(
                error,
                reason === FAILURE_REASONS.TIMEOUT ? 'Intent timed out' : 'Intent failed'
            );
            const durationMs = executionState.finishedAt - executionState.startedAt;

            if (reason === FAILURE_REASONS.TIMEOUT) {
                this.emit(EVENT_NAMES.TIMEOUT, {
                    traceId: executionState.descriptor.traceId,
                    type: executionState.descriptor.type,
                    payload: executionState.descriptor.payload,
                    source: executionState.descriptor.source,
                    target: executionState.descriptor.target,
                    timeoutMs: executionState.descriptor.timeoutMs,
                    startedAt: executionState.startedAt,
                    timedOutAt: executionState.finishedAt,
                    durationMs,
                });
            } else {
                this.emit(EVENT_NAMES.FAIL, {
                    traceId: executionState.descriptor.traceId,
                    type: executionState.descriptor.type,
                    payload: executionState.descriptor.payload,
                    source: executionState.descriptor.source,
                    target: executionState.descriptor.target,
                    error: errorShape,
                    startedAt: executionState.startedAt,
                    failedAt: executionState.finishedAt,
                    durationMs,
                });
            }

            const rollbackResult = await this._runRollback(executionState, reason, errorShape);
            const status = rollbackResult.ok
                ? (reason === FAILURE_REASONS.TIMEOUT ? RESULT_STATUS.TIMEOUT : RESULT_STATUS.FAILED)
                : RESULT_STATUS.ROLLBACK_FAILED;

            this.emit(EVENT_NAMES.SETTLED, {
                traceId: executionState.descriptor.traceId,
                type: executionState.descriptor.type,
                status,
                startedAt: executionState.startedAt,
                finishedAt: executionState.finishedAt,
                durationMs,
            });

            return this._buildSettledResult(executionState, status, errorShape, rollbackResult);
        }

        async _runRollback(executionState, reason, errorShape) {
            const rollbackContext = {
                traceId: executionState.descriptor.traceId,
                type: executionState.descriptor.type,
                payload: executionState.descriptor.payload,
                source: executionState.descriptor.source,
                target: executionState.descriptor.target,
                timeoutMs: executionState.descriptor.timeoutMs,
                reason,
                error: errorShape,
                startedAt: executionState.startedAt,
                failedAt: executionState.finishedAt,
                durationMs: executionState.finishedAt - executionState.startedAt,
            };

            this.emit(EVENT_NAMES.ROLLBACK_START, {
                traceId: executionState.descriptor.traceId,
                type: executionState.descriptor.type,
                payload: executionState.descriptor.payload,
                reason,
                rollbackLabel: executionState.descriptor.onFail.label,
                startedAt: executionState.finishedAt,
            });

            try {
                await Promise.resolve(executionState.descriptor.onFail.rollback(rollbackContext));
                this.emit(EVENT_NAMES.ROLLBACK_SUCCESS, {
                    traceId: executionState.descriptor.traceId,
                    type: executionState.descriptor.type,
                    payload: executionState.descriptor.payload,
                    reason,
                    rollbackLabel: executionState.descriptor.onFail.label,
                    rollbackFinishedAt: getNow(),
                });
                return {
                    attempted: true,
                    ok: true,
                };
            } catch (rollbackError) {
                const rollbackErrorShape = getErrorShape(rollbackError, 'Rollback failed');
                this.emit(EVENT_NAMES.ROLLBACK_FAIL, {
                    traceId: executionState.descriptor.traceId,
                    type: executionState.descriptor.type,
                    payload: executionState.descriptor.payload,
                    reason,
                    rollbackLabel: executionState.descriptor.onFail.label,
                    error: rollbackErrorShape,
                    rollbackFinishedAt: getNow(),
                });
                return {
                    attempted: true,
                    ok: false,
                    error: rollbackErrorShape,
                };
            }
        }

        _buildSettledResult(executionState, status, errorShape, rollbackResult) {
            const finishedAt = executionState.finishedAt || getNow();
            return {
                ok: status === RESULT_STATUS.SUCCESS,
                traceId: executionState.descriptor.traceId,
                type: executionState.descriptor.type,
                status,
                data: undefined,
                error: errorShape,
                rollback: {
                    attempted: rollbackResult.attempted,
                    ok: rollbackResult.ok,
                    error: rollbackResult.error,
                },
                startedAt: executionState.startedAt,
                finishedAt,
                durationMs: finishedAt - executionState.startedAt,
            };
        }

        _removePending(traceId) {
            if (!this._pendingIntents.has(traceId)) {
                return;
            }

            const nextPendingIntents = new Map(this._pendingIntents);
            nextPendingIntents.delete(traceId);
            this._pendingIntents = nextPendingIntents;
        }

        _clearTimeout(executionState) {
            if (executionState.timeoutId !== null) {
                clearTimeout(executionState.timeoutId);
                executionState.timeoutId = null;
            }
        }

        _assertEventName(eventName) {
            if (typeof eventName !== 'string' || eventName.trim() === '') {
                throw createIntentError('Event name must be a non-empty string', 'INVALID_EVENT_NAME');
            }
        }

        _assertHandler(handler) {
            if (typeof handler !== 'function') {
                throw createIntentError('Event handler must be a function', 'INVALID_EVENT_HANDLER');
            }
        }

        _reportHandlerError(eventName, error) {
            if (global.console && typeof global.console.error === 'function') {
                global.console.error(`[IntentBus:${eventName}]`, error);
            }
        }
    }

    global.IntentBus = new IntentBusImpl();
})(window);
