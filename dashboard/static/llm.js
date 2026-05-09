/**
 * LLM AI 助手模块
 * 基于 mimo-v2.5 大模型的量化对话界面
 */
(function () {
    'use strict';

    const _history = []; // {role, content}
    let _streaming = false;
    let _currentConvId = null; // 当前对话 ID
    let _autoSaveTimer = null;

    // ── DOM 工具 ──

    const $ = (id) => document.getElementById(id);
    const chatArea = () => $('llm-chat-area');
    const input = () => $('llm-input');
    const sendBtn = () => $('llm-send-btn');

    // ── 简易 Markdown 渲染 ──

    function renderMarkdown(text) {
        let html = App.escapeHTML(text);
        // 代码块
        html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="llm-code"><code>$2</code></pre>');
        // 行内代码
        html = html.replace(/`([^`]+)`/g, '<code class="llm-inline-code">$1</code>');
        // 表格
        html = html.replace(/\n(\|.+\|)\n(\|[-| :]+\|)\n((?:\|.+\|\n?)+)/g, (_, header, sep, body) => {
            const ths = header.split('|').filter(Boolean).map(h => `<th>${h.trim()}</th>`).join('');
            const rows = body.trim().split('\n').map(row => {
                const tds = row.split('|').filter(Boolean).map(d => `<td>${d.trim()}</td>`).join('');
                return `<tr>${tds}</tr>`;
            }).join('');
            return `<div class="table-wrap"><table class="llm-table"><thead><tr>${ths}</tr></thead><tbody>${rows}</tbody></table></div>`;
        });
        // 加粗
        html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        // 标题
        html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>');
        html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>');
        // 列表
        html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
        html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
        // 换行
        html = html.replace(/\n/g, '<br>');
        return html;
    }

    // ── 消息渲染 ──

    function appendMessage(role, content, isStreaming) {
        const area = chatArea();
        // 移除欢迎消息
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

    function updateStreamBubble(bubble, content) {
        bubble.innerHTML = renderMarkdown(content);
        const area = chatArea();
        area.scrollTop = area.scrollHeight;
    }

    // ── 条件预览卡片 ──

    function renderFilterCard(filters) {
        const area = chatArea();
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
                <button class="btn btn-sm btn-primary" onclick="App.LLM.applyFilters()">应用筛选</button>
                <button class="btn btn-sm" onclick="App.LLM.copyFilters()">复制 JSON</button>
            </div>
        `;

        div.appendChild(avatar);
        div.appendChild(card);
        area.appendChild(div);
        area.scrollTop = area.scrollHeight;
    }

    // ── SSE 流式对话 ──

    async function sendMessage(text) {
        if (_streaming || !text.trim()) return;
        _streaming = true;

        const sendBtnEl = sendBtn();
        sendBtnEl.disabled = true;

        // 用户消息
        appendMessage('user', text);
        _history.push({ role: 'user', content: text });

        // 检查是否是选股请求（简单启发式）
        const isScreenRequest = /选|筛|找|条件|PE|PB|ROE|涨幅|跌幅|换手|量比|市值/.test(text);

        // AI 消息占位
        let fullContent = '';
        const bubble = appendMessage('assistant', '', true);

        try {
            const _chatCtrl = new AbortController();
            const _chatTimer = setTimeout(() => _chatCtrl.abort(), 120000);
            const resp = await fetch('/api/llm/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text, history: _history.slice(-20) }),
                signal: _chatCtrl.signal,
            });
            clearTimeout(_chatTimer);

            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop(); // 保留不完整的行

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    const data = line.slice(6).trim();
                    if (data === '[DONE]') continue;
                    try {
                        const parsed = JSON.parse(data);
                        if (parsed.error) {
                            fullContent += `\n\n⚠️ ${parsed.error}`;
                            updateStreamBubble(bubble, fullContent);
                        } else if (parsed.content) {
                            fullContent += parsed.content;
                            updateStreamBubble(bubble, fullContent);
                        }
                    } catch { /* 忽略非 JSON */ }
                }
            }

            bubble.classList.remove('llm-streaming');
            _history.push({ role: 'assistant', content: fullContent });

            // 自动保存对话
            _autoSave();

            // 如果是选股请求，尝试解析条件
            if (isScreenRequest) {
                tryParseFilters(fullContent);
            }

        } catch (err) {
            bubble.classList.remove('llm-streaming');
            updateStreamBubble(bubble, fullContent + `\n\n⚠️ 请求失败: ${err.message}`);
        } finally {
            _streaming = false;
            sendBtnEl.disabled = false;
        }
    }

    // ── 尝试从回复中提取选股条件 ──

    function tryParseFilters(content) {
        // 尝试提取 JSON 数组
        const jsonMatch = content.match(/\[[\s\S]*?\]/);
        if (!jsonMatch) return;
        try {
            const filters = JSON.parse(jsonMatch[0]);
            if (Array.isArray(filters) && filters.length > 0 && filters[0].field) {
                renderFilterCards(filters);
                // 缓存供 applyFilters 使用
                _lastFilters = filters;
            }
        } catch { /* 不是有效 JSON，忽略 */ }
    }

    let _lastFilters = null;

    function renderFilterCards(filters) {
        renderFilterCard(filters);
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

    // ── 应用筛选条件（跳转到条件选股并自动填入） ──

    function applyFilters() {
        if (!_lastFilters) return;
        // 切换到行情页（条件选股在行情页内）
        App.switchTab('stock');
        // 等待 tab 切换完成后填入条件
        requestAnimationFrame(() => {
            if (App.Screener?.loadFilters) {
                App.Screener.loadFilters(_lastFilters);
            } else {
                // 降级：存 localStorage
                localStorage.setItem('llm_filters', JSON.stringify(_lastFilters));
                App.toast('条件已保存，请手动切换到条件选股页面', 'info');
            }
        });
    }

    function copyFilters() {
        if (!_lastFilters) return;
        const text = JSON.stringify(_lastFilters, null, 2);
        navigator.clipboard.writeText(text).then(() => {
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
        // 生成或复用对话 ID
        if (!_currentConvId) {
            _currentConvId = 'conv_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
        }
        // 标题取第一条用户消息的前30字
        const firstUser = _history.find(m => m.role === 'user');
        const title = firstUser ? firstUser.content.slice(0, 30) : '新对话';
        try {
            await App.fetchJSON('/api/llm/conversations', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: _currentConvId, title, messages: _history }),
                silent: true,
            });
        } catch (e) { /* 静默失败 */ }
    }

    async function loadConversationList() {
        try {
            const list = await App.fetchJSON('/api/llm/conversations', { silent: true });
            return list || [];
        } catch { return []; }
    }

    async function loadConversation(convId) {
        try {
            const resp = await App.fetchJSON(`/api/llm/conversations/${convId}`, { silent: true });
            if (resp.success && resp.data) {
                _currentConvId = convId;
                _history.length = 0;
                const area = chatArea();
                if (area) area.innerHTML = '';
                for (const msg of resp.data.messages) {
                    _history.push(msg);
                    appendMessage(msg.role, msg.content);
                }
                App.toast('已加载对话', 'success');
            }
        } catch (e) {
            App.toast('加载对话失败', 'error');
        }
    }

    function newConversation() {
        _currentConvId = null;
        _history.length = 0;
        const area = chatArea();
        if (area) {
            area.innerHTML = `
                <div class="llm-welcome">
                    <div class="llm-welcome-icon">🤖</div>
                    <h3>AI 量化助手</h3>
                    <p>基于 mimo-v2.5 大模型，支持自然语言选股、策略解读、行情分析</p>
                    <div class="llm-quick-actions">
                        <button class="btn btn-sm" onclick="App.LLM.sendQuick('帮我选出PE低于20、ROE大于15%的股票')">选股：低PE高ROE</button>
                        <button class="btn btn-sm" onclick="App.LLM.sendQuick('选出近5日涨幅超过10%的股票')">选股：近期强势</button>
                        <button class="btn btn-sm" onclick="App.LLM.sendQuick('分析一下当前市场情绪')">市场情绪分析</button>
                    </div>
                </div>
            `;
        }
    }

    async function deleteConversation(convId) {
        try {
            await App.fetchJSON(`/api/llm/conversations/${convId}`, { method: 'DELETE', silent: true });
            if (_currentConvId === convId) {
                newConversation();
            }
            App.toast('对话已删除', 'success');
            _refreshConvList();
        } catch {
            App.toast('删除失败', 'error');
        }
    }

    function _deleteSelected() {
        const sel = $('llm-conv-select');
        if (sel && sel.value) {
            if (confirm('确定删除该对话？')) deleteConversation(sel.value);
        } else {
            App.toast('请先选择一个对话', 'info');
        }
    }

    async function _refreshConvList() {
        const sel = $('llm-conv-select');
        if (!sel) return;
        const list = await loadConversationList();
        const current = sel.value;
        sel.innerHTML = '<option value="">选择历史对话...</option>';
        for (const c of list) {
            const opt = document.createElement('option');
            opt.value = c.id;
            opt.textContent = c.title || '新对话';
            sel.appendChild(opt);
        }
        if (current) sel.value = current;
    }

    // ── 初始化 ──

    function init() {
        const inputEl = input();
        if (!inputEl) return;

        // Enter 发送（Shift+Enter 换行）
        inputEl.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                App.LLM.send();
            }
        });

        // 自动调整高度
        inputEl.addEventListener('input', () => {
            inputEl.style.height = 'auto';
            inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + 'px';
        });

        // 加载对话列表
        _refreshConvList();
    }

    // ── 公开接口 ──

    App.LLM = {
        init,
        send() {
            const el = input();
            if (!el) return;
            const text = el.value.trim();
            if (!text) return;
            el.value = '';
            el.style.height = 'auto';
            sendMessage(text);
        },
        sendQuick(text) {
            const el = input();
            if (el) { el.value = ''; el.style.height = 'auto'; }
            sendMessage(text);
        },
        generateFilters,
        interpretStock,
        applyFilters,
        copyFilters,
        loadConversationList,
        loadConversation,
        newConversation,
        deleteConversation,
    };

    // DOM 加载后初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
