/**
 * LLM 请求与动作层
 * 负责聊天发送、问财、选股条件生成与股票解读。
 */
(function () {
    'use strict';

    const App = globalThis.App || (globalThis.App = {});
    const LLM = App.LLM || (App.LLM = {});

    Object.assign(LLM, {
        async _handleIwencai(query, container) {
            const bubble = this.appendMessage('assistant', '', true, container);
            try {
                this.updateStreamBubble(bubble, '🔍 正在查询问财...', container);
                const resp = await App.fetchJSON('/api/llm/iwencai', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query }),
                });

                if (!resp.success) {
                    this.updateStreamBubble(bubble, `⚠️ ${resp.error || '查询失败'}`, container);
                    return;
                }

                const data = resp.data || [];
                if (!data.length) {
                    this.updateStreamBubble(bubble, '未找到匹配结果', container);
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

                this.updateStreamBubble(bubble, md, container);
                if (bubble) bubble.classList.remove('llm-streaming');
                this.state.history.push({ role: 'assistant', content: md });
            } catch (err) {
                this.updateStreamBubble(bubble, `⚠️ 问财查询失败: ${err.message}`, container);
            }
        },

        async sendMessage(text, container) {
            const resolvedContainer = this._resolveContainer(container);
            if (this.state.streaming || !text.trim()) return;
            this.state.streaming = true;

            const sendBtnEl = this.sendBtn(resolvedContainer);
            if (sendBtnEl) sendBtnEl.disabled = true;

            this.appendMessage('user', text, false, resolvedContainer);

            let apiText = text;
            try {
                const ctx = App.getContext?.(App.currentTab);
                if (ctx) {
                    apiText = `[用户当前在「${App.currentTab}」页面，上下文: ${JSON.stringify(ctx)}]\n${text}`;
                }
            } catch {}

            this.state.history.push({ role: 'user', content: apiText });

            try {
                const iwencaiMatch = text.match(/^\/问财\s*(.+)/);
                if (iwencaiMatch) {
                    await this._handleIwencai(iwencaiMatch[1], resolvedContainer);
                    return;
                }

                const isScreenRequest = /选|筛|找|条件|PE|PB|ROE|涨幅|跌幅|换手|量比|市值/.test(text);

                let fullContent = '';
                const bubble = this.appendMessage('assistant', '', true, resolvedContainer);

                try {
                    const ctrl = new AbortController();
                    const timer = setTimeout(() => ctrl.abort(), 120000);
                    try {
                        const resp = await fetch('/api/llm/chat', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ message: text, history: this.state.history.slice(-20) }),
                            signal: ctrl.signal,
                        });

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
                                        this.updateStreamBubble(bubble, fullContent, resolvedContainer);
                                    } else if (parsed.content) {
                                        fullContent += parsed.content;
                                        this.updateStreamBubble(bubble, fullContent, resolvedContainer);
                                    }
                                } catch {}
                            }
                        }
                    } finally {
                        clearTimeout(timer);
                    }

                    if (bubble) bubble.classList.remove('llm-streaming');
                    this.state.history.push({ role: 'assistant', content: fullContent });
                    if (isScreenRequest) this.tryParseFilters(fullContent, resolvedContainer);
                } catch (err) {
                    if (bubble) bubble.classList.remove('llm-streaming');
                    this.updateStreamBubble(bubble, fullContent + `\n\n⚠️ 请求失败: ${err.message}`, resolvedContainer);
                }
            } finally {
                this.state.streaming = false;
                if (sendBtnEl) sendBtnEl.disabled = false;
                if (typeof this._autoSave === 'function') this._autoSave();
            }
        },

        tryParseFilters(content, container) {
            const jsonMatch = content.match(/\[[\s\S]*?\]/);
            if (!jsonMatch) return;
            try {
                const filters = JSON.parse(jsonMatch[0]);
                if (Array.isArray(filters) && filters.length > 0 && filters[0].field) {
                    this.renderFilterCard(filters, container);
                    this.state.lastFilters = filters;
                }
            } catch {}
        },

        async generateFilters(description) {
            if (this.state.streaming) return;
            this.state.streaming = true;

            this.appendMessage('user', description);
            this.state.history.push({ role: 'user', content: description });

            const bubble = this.appendMessage('assistant', '正在生成选股条件...', true);

            try {
                const data = await App.fetchJSON('/api/llm/generate-filters', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ description }),
                    label: '生成选股条件',
                });

                if (data.success && data.filters) {
                    this.updateStreamBubble(bubble, '✅ 已生成以下选股条件：');
                    this.state.lastFilters = data.filters;
                    this.renderFilterCard(data.filters);
                    this.state.history.push({ role: 'assistant', content: `已生成 ${data.filters.length} 个选股条件` });
                } else {
                    this.updateStreamBubble(bubble, `⚠️ ${data.error || '生成失败'}`);
                }
            } catch (err) {
                this.updateStreamBubble(bubble, `⚠️ 请求失败: ${err.message}`);
            } finally {
                this.state.streaming = false;
                if (typeof this._autoSave === 'function') this._autoSave();
            }
        },

        async interpretStock(stockCode, stockName, prediction, shapValues) {
            const bubble = this.appendMessage('assistant', '正在分析...', true);
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
                    this.updateStreamBubble(bubble, data.interpretation);
                } else {
                    this.updateStreamBubble(bubble, `⚠️ ${data.error || '解读失败'}`);
                }
            } catch (err) {
                this.updateStreamBubble(bubble, `⚠️ 请求失败: ${err.message}`);
            }
        },

        applyFilters() {
            if (!this.state.lastFilters) return;
            App.switchTab('research');
            requestAnimationFrame(() => {
                document.querySelector('.research-sub-tab[data-subtab="screener"]')?.click();
                requestAnimationFrame(() => {
                    if (App.Screener?.init) App.Screener.init();
                    if (App.Screener?.loadFilters) {
                        App.Screener.loadFilters(this.state.lastFilters);
                    } else {
                        localStorage.setItem('llm_filters', JSON.stringify(this.state.lastFilters));
                        App.toast('条件已保存，请手动切换到选股页面', 'info');
                    }
                });
            });
        },

        copyFilters() {
            if (!this.state.lastFilters) return;
            navigator.clipboard.writeText(JSON.stringify(this.state.lastFilters, null, 2)).then(() => {
                App.toast('已复制到剪贴板', 'success');
            }).catch(() => {
                App.toast('复制失败', 'error');
            });
        },

        send(container) {
            const resolvedContainer = this._resolveContainer(container);
            const el = this.inputEl(resolvedContainer);
            if (!el) return;
            const text = el.value.trim();
            if (!text) return;
            el.value = '';
            el.style.height = 'auto';
            this.sendMessage(text, resolvedContainer);
        },

        sendQuick(text, container) {
            const resolvedContainer = container === 'alpha' ? 'alpha' : 'copilot';
            if (resolvedContainer === 'copilot' && !this.state.copilotOpen && typeof this.openCopilot === 'function') {
                this.openCopilot();
            }
            const el = this.inputEl(resolvedContainer);
            if (el) {
                el.value = '';
                el.style.height = 'auto';
            }
            this.sendMessage(text, resolvedContainer);
        },
    });

    window.LLM = LLM;
})();
