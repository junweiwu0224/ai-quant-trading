/**
 * LLM AI 助手模块
 * 双容器模式：Alpha子Tab (v1) + 全局Copilot侧边栏 (v2)
 * 基于 mimo-v2.5 大模型的量化对话界面
 */
(function () {
    'use strict';

    const _history = []; // {role, content}
    let _streaming = false;
    let _currentConvId = null;
    let _autoSaveTimer = null;
    let _copilotOpen = false;

    // ── DOM 工具：双容器自适应 ──

    const $ = (id) => document.getElementById(id);

    function _isCopilot() {
        return _copilotOpen && $('copilot-chat-area');
    }

    function _resolveContainer(container) {
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

        return _isCopilot() ? 'copilot' : 'alpha';
    }

    function chatArea(container) {
        return _resolveContainer(container) === 'copilot' ? $('copilot-chat-area') : $('llm-chat-area');
    }
    function inputEl(container) {
        return _resolveContainer(container) === 'copilot' ? $('copilot-input') : $('llm-input');
    }
    function sendBtn(container) {
        return _resolveContainer(container) === 'copilot' ? $('copilot-send-btn') : $('llm-send-btn');
    }
    function convSelect(container) {
        return _resolveContainer(container) === 'copilot' ? $('copilot-conv-select') : $('llm-conv-select');
    }

    // ── 简易 Markdown 渲染 ──

    function renderMarkdown(text) {
        let html = App.escapeHTML(text);
        html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="llm-code"><code>$2</code></pre>');
        html = html.replace(/`([^`]+)`/g, '<code class="llm-inline-code">$1</code>');
        html = html.replace(/\n(\|.+\|)\n(\|[-| :]+\|)\n((?:\|.+\|\n?)+)/g, (_, header, sep, body) => {
            const ths = header.split('|').filter(Boolean).map(h => `<th>${h.trim()}</th>`).join('');
            const rows = body.trim().split('\n').map(row => {
                const tds = row.split('|').filter(Boolean).map(d => `<td>${d.trim()}</td>`).join('');
                return `<tr>${tds}</tr>`;
            }).join('');
            return `<div class="table-wrap"><table class="llm-table"><thead><tr>${ths}</tr></thead><tbody>${rows}</tbody></table></div>`;
        });
        html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>');
        html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>');
        html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
        html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
        html = html.replace(/\n/g, '<br>');
        return html;
    }

    // ── 消息渲染 ──

    function appendMessage(role, content, isStreaming, container) {
        const area = chatArea(container);
        if (!area) return null;
        const welcome = area.querySelector('.llm-welcome');
        if (welcome) welcome.remove();

        const div = document.createElement('div');
        div.className = `llm-msg llm-msg-${role}`;
        if (isStreaming) div.classList.add('llm-streaming');

        const avatar = document.createElement('div');
        avatar.className = 'llm-avatar';
        avatar.textContent = role === 'user' ? '👤' : '🤖';

        const bubble = document.createElement('div');
        bubble.className = 'llm-bubble';
        if (role === 'assistant') {
            bubble.innerHTML = renderMarkdown(content);
        } else {
            bubble.textContent = content;
        }

        div.appendChild(avatar);
        div.appendChild(bubble);
        area.appendChild(div);
        area.scrollTop = area.scrollHeight;
        return bubble;
    }

    function updateStreamBubble(bubble, content, container) {
        if (!bubble) return;
        bubble.innerHTML = renderMarkdown(content);
        const area = chatArea(container);
        if (area) area.scrollTop = area.scrollHeight;
    }

    // ── 条件预览卡片 ──

    function renderFilterCard(filters, container) {
        const area = chatArea(container);
        if (!area) return;
        const div = document.createElement('div');
        div.className = 'llm-msg llm-msg-assistant';

        const avatar = document.createElement('div');
        avatar.className = 'llm-avatar';
        avatar.textContent = '🤖';

        const card = document.createElement('div');
        card.className = 'llm-filter-card';
        card.innerHTML = `
            <div class="llm-filter-title">已生成选股条件</div>
            <div class="llm-filter-list">
                ${filters.map((f, i) => `
                    <div class="llm-filter-item">
                        <span class="llm-filter-num">${i + 1}</span>
                        <span class="llm-filter-desc">${App.escapeHTML(f.desc || f.field + ' ' + f.op + ' ' + JSON.stringify(f.value))}</span>
                    </div>
                `).join('')}
            </div>
            <div class="llm-filter-actions">
                <button class="btn btn-sm btn-primary" data-llm-action="apply-filters">应用筛选</button>
                <button class="btn btn-sm" data-llm-action="copy-filters">复制 JSON</button>
            </div>
        `;

        div.appendChild(avatar);
        div.appendChild(card);
        area.appendChild(div);
        area.scrollTop = area.scrollHeight;
    }

    // ── 问财查询处理 ──

    async function _handleIwencai(query, container) {
        const bubble = appendMessage('assistant', '', true, container);
        try {
            updateStreamBubble(bubble, '🔍 正在查询问财...', container);
            const resp = await App.fetchJSON('/api/llm/iwencai', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query }),
            });

            if (!resp.success) {
                updateStreamBubble(bubble, `⚠️ ${resp.error || '查询失败'}`, container);
                return;
            }

            const data = resp.data || [];
            if (!data.length) {
                updateStreamBubble(bubble, '未找到匹配结果', container);
                return;
            }

            const cols = Object.keys(data[0]);
            let md = `**问财查询结果**（共 ${resp.total || data.length} 条，显示前 ${Math.min(data.length, 20)} 条）\n\n`;
            md += '| ' + cols.join(' | ') + ' |\n';
            md += '| ' + cols.map(() => '---').join(' | ') + ' |\n';
            for (const row of data.slice(0, 20)) {
                md += '| ' + cols.map(c => {
                    const v = row[c];
                    return v === null || v === undefined ? '' : String(v).replace(/\|/g, '\\|').substring(0, 30);
                }).join(' | ') + ' |\n';
            }

            updateStreamBubble(bubble, md, container);
            bubble.classList.remove('llm-streaming');
            _history.push({ role: 'assistant', content: md });
        } catch (err) {
            updateStreamBubble(bubble, `⚠️ 问财查询失败: ${err.message}`, container);
        }
    }

    // ── SSE 流式对话 ──

    async function sendMessage(text, container) {
        const resolvedContainer = _resolveContainer(container);
        if (_streaming || !text.trim()) return;
        _streaming = true;

        const sendBtnEl = sendBtn(resolvedContainer);
        if (sendBtnEl) sendBtnEl.disabled = true;

        appendMessage('user', text, false, resolvedContainer);

        // 自动附带当前页面上下文（不显示在聊天气泡中）
        let apiText = text;
        try {
            const ctx = App.getContext?.(App.currentTab);
            if (ctx) {
                apiText = `[用户当前在「${App.currentTab}」页面，上下文: ${JSON.stringify(ctx)}]\n${text}`;
            }
        } catch {}
        _history.push({ role: 'user', content: apiText });

        // 问财查询
        const iwencaiMatch = text.match(/^\/问财\s*(.+)/);
        if (iwencaiMatch) {
            await _handleIwencai(iwencaiMatch[1], resolvedContainer);
            _streaming = false;
            if (sendBtnEl) sendBtnEl.disabled = false;
            return;
        }

        const isScreenRequest = /选|筛|找|条件|PE|PB|ROE|涨幅|跌幅|换手|量比|市值/.test(text);

        let fullContent = '';
        const bubble = appendMessage('assistant', '', true, resolvedContainer);

        try {
            const ctrl = new AbortController();
            const timer = setTimeout(() => ctrl.abort(), 120000);
            const resp = await fetch('/api/llm/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text, history: _history.slice(-20) }),
                signal: ctrl.signal,
            });
            clearTimeout(timer);

            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop();

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    const data = line.slice(6).trim();
                    if (data === '[DONE]') continue;
                    try {
                        const parsed = JSON.parse(data);
                        if (parsed.error) {
                            fullContent += `\n\n⚠️ ${parsed.error}`;
                            updateStreamBubble(bubble, fullContent, resolvedContainer);
                        } else if (parsed.content) {
                            fullContent += parsed.content;
                            updateStreamBubble(bubble, fullContent, resolvedContainer);
                        }
                    } catch { /* 忽略非 JSON */ }
                }
            }

            if (bubble) bubble.classList.remove('llm-streaming');
            _history.push({ role: 'assistant', content: fullContent });
            _autoSave();

            if (isScreenRequest) tryParseFilters(fullContent, resolvedContainer);

        } catch (err) {
            if (bubble) bubble.classList.remove('llm-streaming');
            updateStreamBubble(bubble, fullContent + `\n\n⚠️ 请求失败: ${err.message}`, resolvedContainer);
        } finally {
            _streaming = false;
            if (sendBtnEl) sendBtnEl.disabled = false;
        }
    }

    // ── 选股条件解析 ──

    let _lastFilters = null;

    function tryParseFilters(content, container) {
        const jsonMatch = content.match(/\[[\s\S]*?\]/);
        if (!jsonMatch) return;
        try {
            const filters = JSON.parse(jsonMatch[0]);
            if (Array.isArray(filters) && filters.length > 0 && filters[0].field) {
                renderFilterCard(filters, container);
                _lastFilters = filters;
            }
        } catch { /* 忽略 */ }
    }

    // ── 快捷操作 ──

    async function generateFilters(description) {
        if (_streaming) return;
        _streaming = true;

        appendMessage('user', description);
        _history.push({ role: 'user', content: description });

        const bubble = appendMessage('assistant', '正在生成选股条件...', true);

        try {
            const data = await App.fetchJSON('/api/llm/generate-filters', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ description }),
                label: '生成选股条件',
            });

            if (data.success && data.filters) {
                updateStreamBubble(bubble, '✅ 已生成以下选股条件：');
                _lastFilters = data.filters;
                renderFilterCard(data.filters);
                _history.push({ role: 'assistant', content: `已生成 ${data.filters.length} 个选股条件` });
            } else {
                updateStreamBubble(bubble, `⚠️ ${data.error || '生成失败'}`);
            }
        } catch (err) {
            updateStreamBubble(bubble, `⚠️ 请求失败: ${err.message}`);
        } finally {
            _streaming = false;
        }
    }

    async function interpretStock(stockCode, stockName, prediction, shapValues) {
        const bubble = appendMessage('assistant', '正在分析...', true);
        try {
            const data = await App.fetchJSON('/api/llm/interpret', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    stock_code: stockCode,
                    stock_name: stockName,
                    prediction: prediction || {},
                    shap_values: shapValues || [],
                }),
                label: 'AI 解读',
            });
            if (data.success) {
                updateStreamBubble(bubble, data.interpretation);
            } else {
                updateStreamBubble(bubble, `⚠️ ${data.error || '解读失败'}`);
            }
        } catch (err) {
            updateStreamBubble(bubble, `⚠️ 请求失败: ${err.message}`);
        }
    }

    // ── 筛选条件操作 ──

    function applyFilters() {
        if (!_lastFilters) return;
        App.switchTab('research');
        requestAnimationFrame(() => {
            document.querySelector('.research-sub-tab[data-subtab="screener"]')?.click();
            requestAnimationFrame(() => {
                if (App.Screener?.init) App.Screener.init();
                if (App.Screener?.loadFilters) {
                    App.Screener.loadFilters(_lastFilters);
                } else {
                    localStorage.setItem('llm_filters', JSON.stringify(_lastFilters));
                    App.toast('条件已保存，请手动切换到选股页面', 'info');
                }
            });
        });
    }

    function copyFilters() {
        if (!_lastFilters) return;
        navigator.clipboard.writeText(JSON.stringify(_lastFilters, null, 2)).then(() => {
            App.toast('已复制到剪贴板', 'success');
        }).catch(() => {
            App.toast('复制失败', 'error');
        });
    }

    // ── 对话持久化 ──

    function _autoSave() {
        if (_history.length === 0) return;
        clearTimeout(_autoSaveTimer);
        _autoSaveTimer = setTimeout(() => _saveCurrentConversation(), 2000);
    }

    async function _saveCurrentConversation() {
        if (_history.length === 0) return;
        if (!_currentConvId) {
            _currentConvId = 'conv_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
        }
        const firstUser = _history.find(m => m.role === 'user');
        const title = firstUser ? firstUser.content.slice(0, 30) : '新对话';
        try {
            await App.fetchJSON('/api/llm/conversations', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: _currentConvId, title, messages: _history }),
                silent: true,
            });
        } catch { /* 静默 */ }
    }

    async function loadConversationList() {
        try {
            return await App.fetchJSON('/api/llm/conversations', { silent: true }) || [];
        } catch { return []; }
    }

    async function loadConversation(convId, container) {
        const resolvedContainer = _resolveContainer(container);
        try {
            const resp = await App.fetchJSON(`/api/llm/conversations/${convId}`, { silent: true });
            if (resp.success && resp.data) {
                _currentConvId = convId;
                _history.length = 0;
                const area = chatArea(resolvedContainer);
                if (area) area.innerHTML = '';
                for (const msg of resp.data.messages) {
                    _history.push(msg);
                    appendMessage(msg.role, msg.content, false, resolvedContainer);
                }
                App.toast('已加载对话', 'success');
            }
        } catch {
            App.toast('加载对话失败', 'error');
        }
    }

    function newConversation(container) {
        const resolvedContainer = _resolveContainer(container);
        _currentConvId = null;
        _history.length = 0;
        const area = chatArea(resolvedContainer);
        if (!area) return;
        area.innerHTML = `
            <div class="llm-welcome">
                <div class="llm-welcome-icon">🤖</div>
                <div class="llm-welcome-text">
                    <strong>你好！我是 MiMo 量化助手</strong>
                    <p>我可以帮你：</p>
                    <ul>
                        <li>用自然语言描述选股条件，自动生成筛选规则</li>
                        <li>解读 AI 模型的预测结果和因子贡献度</li>
                        <li>解释量化策略、因子含义和回测指标</li>
                        <li>分析股票技术面和基本面</li>
                    </ul>
                    <div class="llm-quick-actions" style="margin-top:12px">
                        <button class="btn btn-sm" data-llm-action="send-quick" data-llm-prompt="帮我选出PE低于20、ROE大于15%的股票">低PE高ROE</button>
                        <button class="btn btn-sm" data-llm-action="send-quick" data-llm-prompt="选出近5日涨幅超过10%的股票">近期强势</button>
                        <button class="btn btn-sm" data-llm-action="send-quick" data-llm-prompt="/问财 今日涨停的股票">问财涨停</button>
                    </div>
                </div>
            </div>
        `;
    }

    async function deleteConversation(convId, container) {
        const resolvedContainer = _resolveContainer(container);
        try {
            await App.fetchJSON(`/api/llm/conversations/${convId}`, { method: 'DELETE', silent: true });
            if (_currentConvId === convId) newConversation(resolvedContainer);
            App.toast('对话已删除', 'success');
            _refreshConvList(resolvedContainer);
        } catch {
            App.toast('删除失败', 'error');
        }
    }

    function _deleteSelected(container) {
        const resolvedContainer = _resolveContainer(container);
        const sel = convSelect(resolvedContainer);
        if (sel && sel.value) {
            if (confirm('确定删除该对话？')) deleteConversation(sel.value, resolvedContainer);
        } else {
            App.toast('请先选择一个对话', 'info');
        }
    }

    async function _refreshConvList(container) {
        const resolvedContainer = _resolveContainer(container);
        const sel = convSelect(resolvedContainer);
        if (!sel) return;
        const list = await loadConversationList();
        const current = sel.value;
        sel.innerHTML = '<option value="">历史对话...</option>';
        for (const c of list) {
            const opt = document.createElement('option');
            opt.value = c.id;
            opt.textContent = c.title || '新对话';
            sel.appendChild(opt);
        }
        if (current) sel.value = current;
    }

    // ── Copilot 侧边栏控制 ──

    function toggleCopilot() {
        _copilotOpen ? closeCopilot() : openCopilot();
    }

    function openCopilot() {
        // 排他性：打开 Copilot 时关闭行情抽屉
        if (App.closeOffcanvas) App.closeOffcanvas();

        const sidebar = $('copilot-sidebar');
        if (!sidebar) return;
        _copilotOpen = true;
        sidebar.classList.add('active');
        sidebar.setAttribute('aria-hidden', 'false');
        // 聚焦输入框
        setTimeout(() => {
            const el = inputEl();
            if (el) el.focus();
        }, 300);
        _refreshConvList();
        // Bug3修复: 侧边栏打开后触发 resize
        requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
    }

    function closeCopilot() {
        const sidebar = $('copilot-sidebar');
        if (!sidebar) return;
        _copilotOpen = false;
        sidebar.classList.remove('active');
        sidebar.setAttribute('aria-hidden', 'true');
        // Bug3修复: 侧边栏关闭后触发 resize
        requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
    }

    function bindConversationControls() {
        const alphaSendButton = $('llm-send-btn');
        if (alphaSendButton && alphaSendButton.dataset.bound !== 'true') {
            alphaSendButton.dataset.bound = 'true';
            alphaSendButton.addEventListener('click', (e) => {
                e.preventDefault();
                App.LLM.send();
            });
        }

        const copilotSendButton = $('copilot-send-btn');
        if (copilotSendButton && copilotSendButton.dataset.bound !== 'true') {
            copilotSendButton.dataset.bound = 'true';
            copilotSendButton.addEventListener('click', (e) => {
                e.preventDefault();
                App.LLM.send();
            });
        }
    }

    // ── 初始化 ──

    function bindActionDelegation() {
        document.addEventListener('click', (e) => {
            const actionEl = e.target.closest('[data-llm-action]');
            if (!actionEl) {
                return;
            }

            const action = actionEl.dataset.llmAction;
            e.preventDefault();

            if (action === 'apply-filters') {
                applyFilters();
                return;
            }

            if (action === 'copy-filters') {
                copyFilters();
                return;
            }

            if (action === 'send-quick') {
                const prompt = typeof actionEl.dataset.llmPrompt === 'string' ? actionEl.dataset.llmPrompt : '';
                if (prompt) {
                    App.LLM.sendQuick(prompt, 'copilot');
                }
                return;
            }

            if (action === 'new-conversation') {
                newConversation();
                return;
            }

            if (action === 'delete-selected') {
                _deleteSelected();
            }
        });

        document.addEventListener('change', (e) => {
            const select = e.target.closest('[data-llm-conversation-select]');
            if (!select) {
                return;
            }
            loadConversation(select.value);
        });
    }

    function init() {
        bindActionDelegation();
        bindConversationControls();
        // Alpha Tab 的输入框绑定
        const alphaInput = $('llm-input');
        if (alphaInput) {
            alphaInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    App.LLM.send();
                }
            });
            alphaInput.addEventListener('input', () => {
                alphaInput.style.height = 'auto';
                alphaInput.style.height = Math.min(alphaInput.scrollHeight, 120) + 'px';
            });
        }

        // Copilot 输入框绑定
        const copilotInput = $('copilot-input');
        if (copilotInput) {
            copilotInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    App.LLM.send();
                }
            });
            copilotInput.addEventListener('input', () => {
                copilotInput.style.height = 'auto';
                copilotInput.style.height = Math.min(copilotInput.scrollHeight, 100) + 'px';
            });
        }

        // Copilot 关闭按钮
        const closeBtn = $('copilot-close');
        if (closeBtn) closeBtn.addEventListener('click', closeCopilot);

        const copilotFab = $('copilot-fab');
        if (copilotFab && copilotFab.dataset.bound !== 'true') {
            copilotFab.dataset.bound = 'true';
            copilotFab.addEventListener('click', (e) => {
                e.preventDefault();
                toggleCopilot();
            });
        }

        // 全局快捷键 Ctrl+K / Cmd+K
        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                toggleCopilot();
            }
            // ESC 关闭 copilot
            if (e.key === 'Escape' && _copilotOpen) {
                closeCopilot();
            }
        });

        // 加载对话列表
        _refreshConvList();
    }

    // ── 公开接口 ──

    App.LLM = {
        init,
        send(container) {
            const resolvedContainer = _resolveContainer(container);
            const el = inputEl(resolvedContainer);
            if (!el) return;
            const text = el.value.trim();
            if (!text) return;
            el.value = '';
            el.style.height = 'auto';
            sendMessage(text, resolvedContainer);
        },
        sendQuick(text, container) {
            const resolvedContainer = container === 'alpha' ? 'alpha' : 'copilot';
            if (resolvedContainer === 'copilot' && !_copilotOpen) openCopilot();
            const el = inputEl(resolvedContainer);
            if (el) { el.value = ''; el.style.height = 'auto'; }
            sendMessage(text, resolvedContainer);
        },
        generateFilters,
        interpretStock,
        applyFilters,
        copyFilters,
        loadConversationList,
        loadConversation,
        newConversation,
        deleteConversation,
        _deleteSelected,
        toggleCopilot,
        openCopilot,
        closeCopilot,
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
