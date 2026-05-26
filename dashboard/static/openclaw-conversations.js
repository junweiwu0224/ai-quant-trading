(function attachOpenClawConversations(global) {
    'use strict';

    const App = global.App;
    if (!App) return;

    const state = {
        workspaceId: '',
        railOpen: false,
        activeConversationId: '',
        items: [],
        query: '',
        bound: false,
        previews: {},
    };

    const Conversations = {
        state,

        async init({ workspaceId = '' } = {}) {
            state.workspaceId = workspaceId || '';
            state.railOpen = this._readRailOpen();
            state.activeConversationId = this._readActiveConversationId();
            this._bind();
            await this.refresh({ preserveMissingActive: false });
            this.render();
        },

        _bind() {
            if (state.bound) return;
            state.bound = true;

            document.addEventListener('click', (e) => {
                const item = e.target.closest('.openclaw-conversation-item');
                if (item && !e.target.closest('.openclaw-conversation-delete')) {
                    const conversationId = item.dataset.conversationId || '';
                    if (conversationId) {
                        void global.OpenClawWorkbench?.openConversation?.(conversationId);
                        return;
                    }
                }

                const btn = e.target.closest('[data-openclaw-conv-action]');
                if (!btn) return;
                const action = btn.dataset.openclawConvAction || '';
                const conversationId = btn.dataset.conversationId || '';

                if (action === 'toggle-rail') {
                    this.toggleRail();
                    return;
                }
                if (action === 'new-chat') {
                    global.OpenClawWorkbench?.startNewConversation?.();
                    return;
                }
                if (action === 'refresh') {
                    void this.refresh();
                    return;
                }
                if (action === 'conversation' && conversationId) {
                    void global.OpenClawWorkbench?.openConversation?.(conversationId);
                    return;
                }
                if (action === 'delete' && conversationId) {
                    e.preventDefault();
                    e.stopPropagation();
                    void global.OpenClawWorkbench?.deleteConversation?.(conversationId);
                }
            });

            document.addEventListener('input', (e) => {
                const input = e.target.closest('[data-openclaw-conv-action="search"]');
                if (!input) return;
                this.setQuery(input.value);
            });
        },

        async refresh({ preserveMissingActive = true } = {}) {
            const resp = await App.fetchJSON('/api/openclaw/conversations', { silent: true }).catch(() => null);
            state.items = (Array.isArray(resp?.items) ? resp.items : []).map((item) => ({
                ...item,
                preview: state.previews[item.id] || item.preview || '',
            }));
            const activeExists = state.items.some((item) => item.id === state.activeConversationId);
            if (!state.activeConversationId || (!activeExists && !preserveMissingActive)) {
                state.activeConversationId = state.items[0]?.id || '';
            }
            this._persistActiveConversationId();
            this.render();
            return state.items;
        },

        async openConversation(id) {
            const convId = String(id || '').trim();
            if (!convId) return null;
            const resp = await App.fetchJSON(`/api/openclaw/conversations/${encodeURIComponent(convId)}`, { silent: true }).catch(() => null);
            if (!resp?.data) return null;
            state.activeConversationId = convId;
            this._persistActiveConversationId();
            this.render();
            return resp.data;
        },

        async saveConversation(payload) {
            if (!payload?.id) return;
            const payloadId = String(payload.id || '').trim();
            const preview = this._previewFromMessages(payload.messages || []);
            state.previews[payloadId] = preview;
            await App.fetchJSON('/api/openclaw/conversations', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
                silent: true,
            });
            if (!state.activeConversationId) {
                state.activeConversationId = payloadId;
                this._persistActiveConversationId();
            }
            await this.refresh({ preserveMissingActive: true });
            state.items = state.items.map((item) => (
                item.id === payloadId ? { ...item, preview } : item
            ));
            this.render();
        },

        async deleteConversation(id) {
            const convId = String(id || '').trim();
            if (!convId) return { removed: false, wasActive: false };
            const wasActive = state.activeConversationId === convId;
            await App.fetchJSON(`/api/openclaw/conversations/${encodeURIComponent(convId)}`, {
                method: 'DELETE',
                silent: true,
            }).catch(() => null);
            state.items = state.items.filter((item) => item.id !== convId);
            if (wasActive) {
                state.activeConversationId = state.items[0]?.id || '';
                this._persistActiveConversationId();
            }
            this.render();
            await this.refresh();
            return { removed: true, wasActive };
        },

        createConversationId() {
            return `oc_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
        },

        ensureConversationId() {
            if (!state.activeConversationId) {
                state.activeConversationId = this.createConversationId();
                this._persistActiveConversationId();
            }
            return state.activeConversationId;
        },

        setActiveConversationId(id, { persist = true, render = true } = {}) {
            state.activeConversationId = String(id || '').trim();
            if (persist) {
                this._persistActiveConversationId();
            }
            if (render) {
                this.render();
            }
        },

        getActiveConversationId() {
            return state.activeConversationId;
        },

        toggleRail(force) {
            state.railOpen = typeof force === 'boolean' ? force : !state.railOpen;
            this._persistRailOpen();
            this.render();
        },

        setQuery(query) {
            state.query = String(query || '').trim();
            this.render();
        },

        filteredItems() {
            const query = state.query.toLowerCase();
            if (!query) return state.items;
            return state.items.filter((item) => {
                const title = String(item?.title || '').toLowerCase();
                const preview = String(item?.preview || '').toLowerCase();
                return title.includes(query) || preview.includes(query) || String(item?.id || '').toLowerCase().includes(query);
            });
        },

        _previewFromMessages(messages) {
            const source = Array.isArray(messages) ? messages : [];
            const firstUser = source.find((message) => message?.role === 'user' && String(message?.content || '').trim());
            return String(firstUser?.content || source[0]?.content || '').trim().slice(0, 120);
        },

        render() {
            const shell = document.querySelector('.openclaw-shell');
            if (shell) {
                shell.classList.toggle('is-rail-open', state.railOpen);
                shell.classList.toggle('is-rail-collapsed', !state.railOpen);
            }
            const rail = document.getElementById('openclaw-conversation-rail');
            if (!rail) return;
            const items = this.filteredItems();
            rail.innerHTML = `
                <div class="openclaw-rail-inner ${state.railOpen ? 'is-open' : 'is-collapsed'}">
                    <div class="openclaw-rail-top">
                        <button class="openclaw-rail-icon" type="button" title="${state.railOpen ? '收起会话栏' : '展开会话栏'}" aria-label="${state.railOpen ? '收起会话栏' : '展开会话栏'}" data-openclaw-conv-action="toggle-rail">${state.railOpen ? '⟨' : '☰'}</button>
                        <button class="openclaw-rail-icon" type="button" title="新建会话" aria-label="新建会话" data-openclaw-conv-action="new-chat">＋</button>
                        <button class="openclaw-rail-icon" type="button" title="刷新会话" aria-label="刷新会话" data-openclaw-conv-action="refresh">↻</button>
                    </div>
                    <div class="openclaw-rail-main">
                        <div class="openclaw-rail-header">
                            <div>
                                <div class="openclaw-side-title">会话</div>
                                <div class="openclaw-rail-subtitle">${App.escapeHTML(String(state.items.length))} 个会话</div>
                            </div>
                            <button class="openclaw-rail-icon" type="button" title="收起会话栏" aria-label="收起会话栏" data-openclaw-conv-action="toggle-rail">⟨</button>
                        </div>
                        <div class="openclaw-rail-search">
                            <input data-openclaw-conv-action="search" value="${App.escapeHTML(state.query)}" placeholder="搜索会话" />
                            <button class="openclaw-rail-icon" type="button" title="新建会话" aria-label="新建会话" data-openclaw-conv-action="new-chat">＋</button>
                        </div>
                        <div class="openclaw-conversation-list">
                            ${items.length ? items.map((item) => `
                                <div
                                    role="button"
                                    tabindex="0"
                                    class="openclaw-conversation-item ${item.id === state.activeConversationId ? 'is-active' : ''}"
                                    data-openclaw-conv-action="conversation"
                                    data-conversation-id="${App.escapeHTML(item.id || '')}"
                                >
                                    <span class="openclaw-conversation-dot"></span>
                                    <span class="openclaw-conversation-copy">
                                        <strong>${App.escapeHTML(item.title || '新对话')}</strong>
                                        <span>${App.escapeHTML(item.updated_at || item.created_at || '')}</span>
                                    </span>
                                    <span class="openclaw-conversation-tools">
                                        <button
                                            type="button"
                                            class="openclaw-conversation-delete"
                                            title="删除会话"
                                            aria-label="删除会话"
                                            data-openclaw-conv-action="delete"
                                            data-conversation-id="${App.escapeHTML(item.id || '')}"
                                        >×</button>
                                    </span>
                                </div>
                            `).join('') : '<div class="openclaw-empty">暂无会话</div>'}
                        </div>
                    </div>
                </div>
            `;
        },

        _persistRailOpen() {
            try {
                localStorage.setItem(this._railKey(), state.railOpen ? '1' : '0');
            } catch {}
        },

        _readRailOpen() {
            try {
                return localStorage.getItem(this._railKey()) === '1';
            } catch {
                return false;
            }
        },

        _persistActiveConversationId() {
            try {
                localStorage.setItem(this._activeKey(), state.activeConversationId || '');
            } catch {}
        },

        _readActiveConversationId() {
            try {
                return localStorage.getItem(this._activeKey()) || '';
            } catch {
                return '';
            }
        },

        _railKey() {
            return `openclaw:rail-open:${state.workspaceId || 'default'}`;
        },

        _activeKey() {
            return `openclaw:active-conversation:${state.workspaceId || 'default'}`;
        },
    };

    global.OpenClawConversations = Conversations;
})(window);
