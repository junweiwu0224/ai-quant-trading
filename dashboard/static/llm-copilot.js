/* ── LLM Copilot 面板控制 ── */
(function () {
    'use strict';

    const App = globalThis.App || (globalThis.App = {});
    const LLM = App.LLM || (App.LLM = {});
    const state = LLM.state || (LLM.state = {});
    const $ = (id) => document.getElementById(id);

    Object.assign(LLM, {
        toggleCopilot() {
            state.copilotOpen ? this.closeCopilot() : this.openCopilot();
        },

        openCopilot() {
            if (App.closeOffcanvas) App.closeOffcanvas();

            const sidebar = $('copilot-sidebar');
            if (!sidebar) return;
            state.copilotOpen = true;
            sidebar.classList.add('active');
            sidebar.setAttribute('aria-hidden', 'false');
            setTimeout(() => {
                const el = this.inputEl();
                if (el) el.focus();
            }, 300);
            this._refreshConvList?.();
            requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
        },

        closeCopilot() {
            const sidebar = $('copilot-sidebar');
            if (!sidebar) return;
            state.copilotOpen = false;
            sidebar.classList.remove('active');
            sidebar.setAttribute('aria-hidden', 'true');
            requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
        },

        bindConversationControls() {
            if (state.controlsBound) return;
            state.controlsBound = true;

            const alphaSendButton = $('llm-send-btn');
            if (alphaSendButton && alphaSendButton.dataset.bound !== 'true') {
                alphaSendButton.dataset.bound = 'true';
                alphaSendButton.addEventListener('click', (e) => {
                    e.preventDefault();
                    this.send();
                });
            }

            const copilotSendButton = $('copilot-send-btn');
            if (copilotSendButton && copilotSendButton.dataset.bound !== 'true') {
                copilotSendButton.dataset.bound = 'true';
                copilotSendButton.addEventListener('click', (e) => {
                    e.preventDefault();
                    this.send();
                });
            }
        },

        bindActionDelegation() {
            if (state.actionDelegationBound) {
                return;
            }

            state.actionDelegationBound = true;
            document.addEventListener('click', (e) => {
                const actionEl = e.target.closest('[data-llm-action]');
                if (!actionEl) return;

                const action = actionEl.dataset.llmAction;
                e.preventDefault();

                if (action === 'apply-filters') {
                    this.applyFilters();
                    return;
                }
                if (action === 'copy-filters') {
                    this.copyFilters();
                    return;
                }
                if (action === 'send-quick') {
                    const prompt = typeof actionEl.dataset.llmPrompt === 'string' ? actionEl.dataset.llmPrompt : '';
                    if (prompt) this.sendQuick(prompt, 'copilot');
                    return;
                }
                if (action === 'new-conversation') {
                    this.newConversation();
                    return;
                }
                if (action === 'delete-selected') {
                    this._deleteSelected();
                }
            });

            document.addEventListener('change', (e) => {
                const select = e.target.closest('[data-llm-conversation-select]');
                if (!select) return;
                this.loadConversation(select.value);
            });
        },

        init() {
            if (state.initDone) return;
            state.initDone = true;

            this.bindActionDelegation();
            this.bindConversationControls();

            const alphaInput = $('llm-input');
            if (alphaInput) {
                alphaInput.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        this.send();
                    }
                });
                alphaInput.addEventListener('input', () => {
                    alphaInput.style.height = 'auto';
                    alphaInput.style.height = Math.min(alphaInput.scrollHeight, 120) + 'px';
                });
            }

            const copilotInput = $('copilot-input');
            if (copilotInput) {
                copilotInput.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        this.send();
                    }
                });
                copilotInput.addEventListener('input', () => {
                    copilotInput.style.height = 'auto';
                    copilotInput.style.height = Math.min(copilotInput.scrollHeight, 100) + 'px';
                });
            }

            const closeBtn = $('copilot-close');
            if (closeBtn) closeBtn.addEventListener('click', () => this.closeCopilot());

            const copilotFab = $('copilot-fab');
            if (copilotFab && copilotFab.dataset.bound !== 'true') {
                copilotFab.dataset.bound = 'true';
                copilotFab.addEventListener('click', (e) => {
                    e.preventDefault();
                    this.toggleCopilot();
                });
            }

            document.addEventListener('keydown', (e) => {
                if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                    e.preventDefault();
                    this.toggleCopilot();
                }
                if (e.key === 'Escape' && state.copilotOpen) {
                    this.closeCopilot();
                }
            });

            this._refreshConvList?.();
        },
    });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            if (globalThis.__AUTH_GATE_REQUIRED__ === true) return;
            LLM.init?.();
        });
    } else if (globalThis.__AUTH_GATE_REQUIRED__ !== true) {
        LLM.init?.();
    }
})();
