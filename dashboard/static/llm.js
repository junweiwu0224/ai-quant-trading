/**
 * LLM AI 助手核心层
 * 保留共享状态、容器解析和通用入口。
 */
(function () {
    'use strict';

    const App = globalThis.App || (globalThis.App = {});
    const LLM = App.LLM || (App.LLM = {});
    const $ = (id) => document.getElementById(id);

    Object.assign(LLM, {
        state: LLM.state || {
            history: [],
            streaming: false,
            currentConvId: null,
            autoSaveTimer: null,
            copilotOpen: false,
            lastFilters: null,
            initDone: false,
            actionDelegationBound: false,
            controlsBound: false,
            persona: '龙虾',
        },

        _isCopilot() {
            return this.state.copilotOpen && $('copilot-chat-area');
        },

        _resolveContainer(container) {
            if (container === 'alpha' || container === 'copilot') {
                return container;
            }

            const eventTarget = globalThis.event && typeof globalThis.event.currentTarget?.closest === 'function'
                ? globalThis.event.currentTarget
                : (globalThis.event && typeof globalThis.event.target?.closest === 'function' ? globalThis.event.target : null);
            if (eventTarget?.closest('#copilot-sidebar')) {
                return 'copilot';
            }
            if (eventTarget?.closest('#alpha-panel-llm')) {
                return 'alpha';
            }

            const activeElement = typeof document.activeElement?.closest === 'function' ? document.activeElement : null;
            if (activeElement?.closest('#copilot-sidebar')) {
                return 'copilot';
            }
            if (activeElement?.closest('#alpha-panel-llm')) {
                return 'alpha';
            }

            return this._isCopilot() ? 'copilot' : 'alpha';
        },

        chatArea(container) {
            return this._resolveContainer(container) === 'copilot' ? $('copilot-chat-area') : $('llm-chat-area');
        },

        inputEl(container) {
            return this._resolveContainer(container) === 'copilot' ? $('copilot-input') : $('llm-input');
        },

        sendBtn(container) {
            return this._resolveContainer(container) === 'copilot' ? $('copilot-send-btn') : $('llm-send-btn');
        },

        convSelect(container) {
            return this._resolveContainer(container) === 'copilot' ? $('copilot-conv-select') : $('llm-conv-select');
        },
    });

    window.LLM = LLM;
})();
