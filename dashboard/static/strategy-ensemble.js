/* ── 多策略聚合 + AI 策略生成 ── */

const Ensemble = {
    _strategies: [],
    _actionsBound: false,

    bindActionDelegation() {
        if (this._actionsBound) {
            return;
        }

        this._actionsBound = true;
        document.addEventListener('click', (e) => {
            const actionEl = e.target.closest('[data-ensemble-action]');
            if (!actionEl) {
                return;
            }

            const action = actionEl.dataset.ensembleAction;
            const overlay = actionEl.closest('.modal-overlay');
            e.preventDefault();

            if (action === 'close-modal') {
                overlay?.remove();
                return;
            }

            if (action === 'run-ensemble') {
                this.runEnsemble(overlay);
                return;
            }

            if (action === 'generate-strategy') {
                this.generateStrategy(overlay);
                return;
            }

            if (action === 'copy-code') {
                this.copyCode(overlay);
            }
        });
    },

    async loadStrategies() {
        try {
            this._strategies = await App.fetchJSON('/api/strategy/list');
        } catch (e) {
            console.error('加载策略列表失败:', e);
        }
    },

    async showEnsembleModal() {
        this.bindActionDelegation();
        await this.loadStrategies();
        const strategies = this._strategies;
        if (!strategies.length) { App.toast('没有可用策略', 'error'); return; }

        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.dataset.ensembleModal = 'backtest';
        overlay.innerHTML = `
            <div class="modal" style="max-width:700px">
                <div class="modal-header">
                    <h2>多策略聚合回测</h2>
                    <button class="modal-close" data-ensemble-action="close-modal">&times;</button>
                </div>
                <div class="modal-body">
                    <div style="margin-bottom:12px">
                        <label style="font-size:13px;color:var(--text-secondary)">选择策略并设置权重</label>
                        <div id="ensemble-strategy-list" style="margin-top:8px">
                            ${strategies.map(s => `
                                <label style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border-color)">
                                    <input type="checkbox" value="${App.escapeHTML(s.name)}" class="ensemble-cb">
                                    <span style="flex:1">${App.escapeHTML(s.label || s.name)}</span>
                                    <input type="number" value="1.0" step="0.1" min="0.1" max="10"
                                        style="width:60px;padding:4px;border:1px solid var(--border-color);border-radius:4px;background:var(--bg-primary);color:var(--text-primary)"
                                        data-weight="${App.escapeHTML(s.name)}">
                                </label>
                            `).join('')}
                        </div>
                    </div>
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">
                        <div>
                            <label style="font-size:13px;color:var(--text-secondary)">聚合方式</label>
                            <select id="ensemble-agg" style="width:100%;padding:6px;border:1px solid var(--border-color);border-radius:4px;background:var(--bg-primary);color:var(--text-primary)">
                                <option value="weighted_average">加权平均</option>
                                <option value="majority_vote">多数投票</option>
                                <option value="unanimous">一致通过</option>
                            </select>
                        </div>
                        <div>
                            <label style="font-size:13px;color:var(--text-secondary)">买入阈值</label>
                            <input type="number" id="ensemble-buy-th" value="0.3" step="0.1" style="width:100%;padding:6px;border:1px solid var(--border-color);border-radius:4px;background:var(--bg-primary);color:var(--text-primary)">
                        </div>
                    </div>
                    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:12px">
                        <div>
                            <label style="font-size:13px;color:var(--text-secondary)">股票代码</label>
                            <input type="text" id="ensemble-codes" value="000001" placeholder="逗号分隔" style="width:100%;padding:6px;border:1px solid var(--border-color);border-radius:4px;background:var(--bg-primary);color:var(--text-primary)">
                        </div>
                        <div>
                            <label style="font-size:13px;color:var(--text-secondary)">开始日期</label>
                            <input type="date" id="ensemble-start" value="2024-01-01" style="width:100%;padding:6px;border:1px solid var(--border-color);border-radius:4px;background:var(--bg-primary);color:var(--text-primary)">
                        </div>
                        <div>
                            <label style="font-size:13px;color:var(--text-secondary)">结束日期</label>
                            <input type="date" id="ensemble-end" value="2024-12-31" style="width:100%;padding:6px;border:1px solid var(--border-color);border-radius:4px;background:var(--bg-primary);color:var(--text-primary)">
                        </div>
                    </div>
                    <div id="ensemble-result" style="margin-top:12px"></div>
                    <button class="btn btn-primary" id="ensemble-run-btn" data-ensemble-action="run-ensemble">运行聚合回测</button>
                </div>
            </div>`;
        document.body.appendChild(overlay);
        overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
    },

    async runEnsemble(overlay) {
        const modalOverlay = overlay?.isConnected ? overlay : null;
        const selected = modalOverlay ? [...modalOverlay.querySelectorAll('.ensemble-cb:checked')].map(cb => {
            const weightInput = [...modalOverlay.querySelectorAll('[data-weight]')]
                .find((input) => input.dataset.weight === cb.value);
            const weight = parseFloat(weightInput?.value || '');
            return {
                name: cb.value,
                weight,
            };
        }) : [];
        if (!selected.length) { App.toast('请至少选择一个策略', 'error'); return; }
        if (selected.some((item) => !Number.isFinite(item.weight) || item.weight <= 0)) {
            App.toast('策略权重必须是大于 0 的数字', 'error');
            return;
        }

        const buyThreshold = parseFloat(modalOverlay?.querySelector('#ensemble-buy-th')?.value || '');
        if (!Number.isFinite(buyThreshold)) {
            App.toast('买入阈值必须是有效数字', 'error');
            return;
        }

        const btn = modalOverlay?.querySelector('#ensemble-run-btn');
        if (btn) {
            btn.disabled = true;
            btn.textContent = '运行中...';
        }

        try {
            const codesStr = modalOverlay?.querySelector('#ensemble-codes')?.value || '';
            const result = await App.postJSON('/api/strategy/ensemble-backtest', {
                strategies: selected,
                aggregation: modalOverlay?.querySelector('#ensemble-agg')?.value,
                buy_threshold: buyThreshold,
                codes: codesStr.split(/[,，\s]+/).filter(Boolean),
                start_date: modalOverlay?.querySelector('#ensemble-start')?.value,
                end_date: modalOverlay?.querySelector('#ensemble-end')?.value,
            });

            if (!result.success) { App.toast(result.error || '回测失败', 'error'); return; }

            const el = modalOverlay?.querySelector('#ensemble-result');
            if (!el || !el.isConnected) {
                return;
            }
            const totalTrades = Number(result.total_trades);
            const totalTradesText = Number.isFinite(totalTrades) ? totalTrades : '--';
            el.innerHTML = `
                <div class="stats-grid stats-grid-4" style="margin-bottom:12px">
                    <div class="stat-card"><div class="stat-label">总收益</div><div class="stat-value">${(result.total_return * 100).toFixed(2)}%</div></div>
                    <div class="stat-card"><div class="stat-label">年化收益</div><div class="stat-value">${(result.annual_return * 100).toFixed(2)}%</div></div>
                    <div class="stat-card"><div class="stat-label">最大回撤</div><div class="stat-value">${(result.max_drawdown * 100).toFixed(2)}%</div></div>
                    <div class="stat-card"><div class="stat-label">夏普比率</div><div class="stat-value">${result.sharpe_ratio?.toFixed(2) || '--'}</div></div>
                </div>
                <div style="font-size:13px;color:var(--text-secondary)">
                    胜率 ${(result.win_rate * 100).toFixed(1)}% | 交易次数 ${totalTradesText}
                </div>`;
            App.toast('聚合回测完成', 'success');
        } catch (e) {
            App.toast('聚合回测失败: ' + e.message, 'error');
        } finally {
            if (btn && btn.isConnected) {
                btn.disabled = false;
                btn.textContent = '运行聚合回测';
            }
        }
    },

    // ── AI 策略生成 ──

    showAIModal() {
        this.bindActionDelegation();
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.dataset.ensembleModal = 'ai';
        overlay.innerHTML = `
            <div class="modal" style="max-width:700px">
                <div class="modal-header">
                    <h2>AI 策略生成</h2>
                    <button class="modal-close" data-ensemble-action="close-modal">&times;</button>
                </div>
                <div class="modal-body">
                    <div style="margin-bottom:12px">
                        <label style="font-size:13px;color:var(--text-secondary)">描述你想要的策略逻辑</label>
                        <textarea id="ai-strategy-desc" rows="4" placeholder="例如：当 RSI 低于 30 且 MACD 金叉时买入，RSI 高于 70 时卖出"
                            style="width:100%;padding:8px;border:1px solid var(--border-color);border-radius:6px;background:var(--bg-primary);color:var(--text-primary);margin-top:4px;resize:vertical"></textarea>
                    </div>
                    <div id="ai-strategy-result" style="margin-bottom:12px"></div>
                    <button class="btn btn-primary" id="ai-gen-btn" data-ensemble-action="generate-strategy">生成策略代码</button>
                </div>
            </div>`;
        document.body.appendChild(overlay);
        overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
    },

    async generateStrategy(overlay) {
        const modalOverlay = overlay?.isConnected ? overlay : null;
        const desc = modalOverlay?.querySelector('#ai-strategy-desc')?.value?.trim();
        if (!desc) { App.toast('请输入策略描述', 'error'); return; }

        const btn = modalOverlay?.querySelector('#ai-gen-btn');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'AI 生成中...';
        }

        try {
            const result = await App.postJSON('/api/llm/generate-strategy', { description: desc });
            if (!result.success) { App.toast(result.error || '生成失败', 'error'); return; }

            const el = modalOverlay?.querySelector('#ai-strategy-result');
            if (!el || !el.isConnected) {
                return;
            }
            el.innerHTML = `
                <div style="background:var(--bg-secondary);border:1px solid var(--border-color);border-radius:8px;padding:12px">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
                        <span style="font-size:13px;font-weight:600">生成的策略代码</span>
                        <button class="btn btn-sm" data-ensemble-action="copy-code">复制代码</button>
                    </div>
                    <pre style="font-size:12px;overflow-x:auto;white-space:pre-wrap;max-height:400px;overflow-y:auto"><code id="ai-gen-code">${App.escapeHTML(result.code)}</code></pre>
                </div>`;
            App.toast('策略代码已生成', 'success');
        } catch (e) {
            App.toast('生成失败: ' + e.message, 'error');
        } finally {
            if (btn && btn.isConnected) {
                btn.disabled = false;
                btn.textContent = '生成策略代码';
            }
        }
    },

    copyCode(overlay) {
        const code = overlay?.querySelector('#ai-gen-code')?.textContent;
        if (code) {
            navigator.clipboard.writeText(code).then(() => App.toast('已复制到剪贴板', 'success'));
        }
    },

    // ── AI 回测诊断 ──

    async diagnoseBacktest(resultData) {
        this.bindActionDelegation();
        const btn = document.getElementById('ensemble-diagnose-btn');
        if (btn) { btn.disabled = true; btn.textContent = 'AI 诊断中...'; }

        try {
            const result = await App.postJSON('/api/llm/diagnose-backtest', { result: resultData });
            if (!result.success) { App.toast(result.error || '诊断失败', 'error'); return; }

            const overlay = document.createElement('div');
            overlay.className = 'modal-overlay';
            overlay.innerHTML = `
                <div class="modal" style="max-width:700px">
                    <div class="modal-header">
                        <h2>AI 回测诊断</h2>
                        <button class="modal-close" data-ensemble-action="close-modal">&times;</button>
                    </div>
                    <div class="modal-body" style="font-size:14px;line-height:1.6">
                        ${this._renderMarkdown(result.report)}
                    </div>
                </div>`;
            document.body.appendChild(overlay);
            overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
        } catch (e) {
            App.toast('诊断失败: ' + e.message, 'error');
        } finally {
            if (btn) {
                btn.textContent = 'AI 诊断';
                if (typeof App._setBacktestDiagnoseEnabled === 'function') {
                    App._setBacktestDiagnoseEnabled(Boolean(App._lastBacktestData));
                } else {
                    btn.disabled = false;
                }
            }
        }
    },

    _renderMarkdown(text) {
        if (!text) return '';
        const formatInline = (value) => value.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        const escaped = App.escapeHTML(text);
        return escaped
            .split('\n')
            .map((line) => {
                if (!line.trim()) {
                    return '<div style="height:12px"></div>';
                }
                if (/^###\s+/.test(line)) {
                    return `<h3 style="margin:12px 0 6px;font-size:15px">${formatInline(line.replace(/^###\s+/, ''))}</h3>`;
                }
                if (/^##\s+/.test(line)) {
                    return `<h2 style="margin:16px 0 8px;font-size:17px;border-bottom:1px solid var(--border-color);padding-bottom:6px">${formatInline(line.replace(/^##\s+/, ''))}</h2>`;
                }
                if (/^-\s+/.test(line)) {
                    return `<div style="margin-left:16px">• ${formatInline(line.replace(/^-\s+/, ''))}</div>`;
                }
                const orderedMatch = line.match(/^(\d+)\.\s+(.+)$/);
                if (orderedMatch) {
                    return `<div style="margin-left:16px">${orderedMatch[1]}. ${formatInline(orderedMatch[2])}</div>`;
                }
                if (/^\|.*\|$/.test(line)) {
                    const cells = line.split('|').filter(Boolean).map((cell) => cell.trim());
                    if (cells.every((cell) => /^[-:]+$/.test(cell))) {
                        return '';
                    }
                    return `<div style="display:grid;grid-template-columns:repeat(${cells.length}, minmax(0, 1fr));gap:0;border:1px solid var(--border-color);margin:6px 0">${cells.map((cell) => `<div style="padding:4px 8px;border-right:1px solid var(--border-color)">${formatInline(cell)}</div>`).join('')}</div>`;
                }
                return `<div>${formatInline(line)}</div>`;
            })
            .join('');
    },
};
