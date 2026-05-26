/**
 * LLM 消息渲染层
 * 负责 markdown、消息气泡和筛选卡片渲染。
 */
(function () {
    'use strict';

    const App = globalThis.App || (globalThis.App = {});
    const LLM = App.LLM || (App.LLM = {});

    Object.assign(LLM, {
        renderMarkdown(text) {
            let html = App.escapeHTML(text ?? '');
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
        },

        appendMessage(role, content, isStreaming, container) {
            const area = this.chatArea(container);
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
                bubble.innerHTML = this.renderMarkdown(content);
            } else {
                bubble.textContent = content;
            }

            div.appendChild(avatar);
            div.appendChild(bubble);
            area.appendChild(div);
            area.scrollTop = area.scrollHeight;
            return bubble;
        },

        updateStreamBubble(bubble, content, container) {
            if (!bubble) return;
            bubble.innerHTML = this.renderMarkdown(content);
            const area = this.chatArea(container);
            if (area) area.scrollTop = area.scrollHeight;
        },

        renderFilterCard(filters, container) {
            const area = this.chatArea(container);
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
        },
    });

    window.LLM = LLM;
})();
