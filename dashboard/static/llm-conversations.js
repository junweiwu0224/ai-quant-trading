/* ── LLM 对话与会话管理 ── */
(function () {
    'use strict';

    const App = globalThis.App || (globalThis.App = {});
    const LLM = App.LLM || (App.LLM = {});
    const state = LLM.state || (LLM.state = {});

    Object.assign(LLM, {
        _autoSave() {
            if ((state.history || []).length === 0) return;
            clearTimeout(state.autoSaveTimer);
            state.autoSaveTimer = setTimeout(() => this._saveCurrentConversation(), 2000);
        },

        async _saveCurrentConversation() {
            if ((state.history || []).length === 0) return;
            if (!state.currentConvId) {
                state.currentConvId = 'conv_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
            }
            const firstUser = state.history.find(m => m.role === 'user');
            const title = firstUser ? firstUser.content.slice(0, 30) : '新对话';
            try {
                await App.fetchJSON('/api/llm/conversations', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id: state.currentConvId, title, messages: state.history }),
                    silent: true,
                });
            } catch {}
        },

        async loadConversationList() {
            try {
                return await App.fetchJSON('/api/llm/conversations', { silent: true }) || [];
            } catch {
                return [];
            }
        },

        async loadConversation(convId, container) {
            const resolvedContainer = this._resolveContainer(container);
            try {
                const resp = await App.fetchJSON(`/api/llm/conversations/${convId}`, { silent: true });
                if (resp.success && resp.data) {
                    state.currentConvId = convId;
                    state.history.length = 0;
                    const area = this.chatArea(resolvedContainer);
                    if (area) area.innerHTML = '';
                    for (const msg of resp.data.messages) {
                        state.history.push(msg);
                        this.appendMessage(msg.role, msg.content, false, resolvedContainer);
                    }
                    App.toast('已加载对话', 'success');
                }
            } catch {
                App.toast('加载对话失败', 'error');
            }
        },

        newConversation(container) {
            const resolvedContainer = this._resolveContainer(container);
            state.currentConvId = null;
            state.history.length = 0;
            const area = this.chatArea(resolvedContainer);
            if (!area) return;
            area.innerHTML = `
                <div class="llm-welcome">
                    <div class="llm-welcome-icon">🤖</div>
                    <div class="llm-welcome-text">
                        <strong>你好！我是龙虾</strong>
                        <p>我可以帮你：</p>
                        <ul>
                            <li>把选股想法拆成可回测的筛选条件</li>
                            <li>从技术面、基本面、资金情绪和风控视角分析问题</li>
                            <li>解读回测指标、因子贡献和策略失效风险</li>
                            <li>把模糊判断改写成参数化策略假设</li>
                        </ul>
                        <div class="llm-quick-actions" style="margin-top:12px">
                            <button class="btn btn-sm" data-llm-action="send-quick" data-llm-prompt="帮我选出PE低于20、ROE大于15%的股票">低PE高ROE</button>
                            <button class="btn btn-sm" data-llm-action="send-quick" data-llm-prompt="选出近5日涨幅超过10%的股票">近期强势</button>
                            <button class="btn btn-sm" data-llm-action="send-quick" data-llm-prompt="/问财 今日涨停的股票">问财涨停</button>
                        </div>
                    </div>
                </div>
            `;
        },

        async deleteConversation(convId, container) {
            const resolvedContainer = this._resolveContainer(container);
            try {
                await App.fetchJSON(`/api/llm/conversations/${convId}`, { method: 'DELETE', silent: true });
                if (state.currentConvId === convId) this.newConversation(resolvedContainer);
                App.toast('对话已删除', 'success');
                this._refreshConvList(resolvedContainer);
            } catch {
                App.toast('删除失败', 'error');
            }
        },

        _deleteSelected(container) {
            const resolvedContainer = this._resolveContainer(container);
            const sel = this.convSelect(resolvedContainer);
            if (sel && sel.value) {
                if (confirm('确定删除该对话？')) this.deleteConversation(sel.value, resolvedContainer);
            } else {
                App.toast('请先选择一个对话', 'info');
            }
        },

        async _refreshConvList(container) {
            const resolvedContainer = this._resolveContainer(container);
            const sel = this.convSelect(resolvedContainer);
            if (!sel) return;
            const list = await this.loadConversationList();
            const current = sel.value;
            sel.innerHTML = '<option value="">历史对话...</option>';
            for (const c of list) {
                const opt = document.createElement('option');
                opt.value = c.id;
                opt.textContent = c.title || '新对话';
                sel.appendChild(opt);
            }
            if (current) sel.value = current;
        },
    });
})();
