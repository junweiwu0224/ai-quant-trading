(function attachOpenClawWorkbench(global) {
    'use strict';

    const App = global.App;
    const Conversations = global.OpenClawConversations;
    if (!App) return;

    const state = {
        messagesByConversation: new Map(),
        pendingRequest: null,
        pendingConversationId: '',
        currentConversationId: '',
        lastLoadedConversationId: '',
        stateData: null,
        setupState: null,
        bound: false,
        activeTab: 'openclaw',
        skillCommandHint: '',
    };

    const Workbench = {
        _messages: [],
        _state: null,
        _setupState: null,

        _ACTION_LABELS: {
            'quant.watchlist.add': '加入自选',
            'quant.stock.open': '打开详情',
            'quant.paper.order': '模拟盘下单',
            'quant.paper.close_position': '模拟盘平仓',
            'quant.paper.summary': '查看模拟盘摘要',
            'quant.report.generate_daily': '生成日报',
            'quant.report.open': '查看日报',
            'quant.valuation.peg': '查看估值快照',
            'quant.data.snapshot': '查看数据底座',
            'quant.signals.top': '查看 AI信号 Top',
            'quant.qlib.top': '查看 AI信号 Top',
        },

        async init(tab = 'openclaw') {
            state.activeTab = tab || 'openclaw';
            if (!state.bound) {
                state.bound = true;
                this._bind();
            }
            if (state.activeTab === 'openclaw-settings') {
                await this.refreshSettings();
                return;
            }
            if (!Conversations) {
                throw new Error('OpenClawConversations 未加载');
            }
            await Conversations.init({
                workspaceId: App._accountState?.workspace?.id || '',
            });
            await this.refresh(tab);
        },

        _bind() {
            document.addEventListener('click', (e) => {
                const btn = e.target.closest('[data-openclaw-action]');
                if (!btn) return;
                const action = btn.dataset.openclawAction;
                if (action === 'refresh') void this.refresh();
                if (action === 'send') void this.send();
                if (action === 'stop') void this.stop();
                if (action === 'open-native') void this.openNativePanel();
                if (action === 'open-settings') App.switchTab('openclaw-settings');
                if (action === 'quick') void this.send(btn.dataset.prompt || '');
                if (action === 'clear-chat') this.clearChat();
                if (action === 'tool-action') void this.runSuggestedAction(btn);
            });

            document.addEventListener('keydown', (e) => {
                if (e.key !== 'Enter' || e.shiftKey) return;
                const input = e.target.closest('#openclaw-input');
                if (!input) return;
                e.preventDefault();
                void this.send();
            });

            document.addEventListener('input', (e) => {
                const input = e.target.closest('#openclaw-input');
                if (!input) return;
                state.skillCommandHint = this._skillCommandHint(input.value);
                this._updateComposerHint();
            });
        },

        async refresh(tab = 'openclaw') {
            state.activeTab = tab || state.activeTab || 'openclaw';
            if (tab === 'openclaw-settings') {
                return this.refreshSettings();
            }
            const root = document.getElementById('openclaw-workbench');
            if (!root) return;
            const draft = document.getElementById('openclaw-input')?.value || '';
            root.innerHTML = this._layout();
            Conversations?.render?.();
            this._restoreComposerDraft(draft);
            this._messages = this._messagesForActiveConversation();
            this._renderMessages();
            this._setStreaming(Boolean(state.pendingRequest));
            await this._restoreConversationIfNeeded();
            Conversations?.render?.();
            this._setStreaming(Boolean(state.pendingRequest));
            this._loadState()
                .then((data) => {
                    this._state = data;
                    this._renderStatus(data);
                })
                .catch((e) => {
                    console.warn('[OpenClaw] state refresh failed', e);
                });
        },

        async _loadState() {
            const [status, setup, memories, reports, skills, tools, audit] = await Promise.all([
                App.fetchJSON('/api/openclaw/status', { silent: true }).catch(() => null),
                App.fetchJSON('/api/openclaw/setup', { silent: true }).catch(() => null),
                App.fetchJSON('/api/openclaw/memories?limit=5', { silent: true }).catch(() => null),
                App.fetchJSON('/api/openclaw/reports/daily?limit=5', { silent: true }).catch(() => null),
                App.fetchJSON('/api/openclaw/skills', { silent: true }).catch(() => null),
                App.fetchJSON('/api/openclaw/tools', { silent: true }).catch(() => null),
                App.fetchJSON('/api/account/audit?limit=5', { silent: true }).catch(() => null),
            ]);
            this._setupState = setup;
            return { status, setup, memories, reports, skills, tools, audit };
        },

        _isSkillCommand(text) {
            return /^(?:\/skill|@skill|!skill)(?:\s|$)/i.test(String(text || '').trim());
        },

        _skillCommandHint(text) {
            return this._isSkillCommand(text) ? '已识别为技能命令，结果由服务端决定。' : '';
        },

        _skillCommandHistory(state) {
            const sources = [
                state?.skills?.history,
                state?.skills?.recent_history,
                state?.skills?.skill_command_history,
                state?.skills?.commands,
                state?.status?.skill_command_history,
                state?.status?.skill_commands,
                state?.setup?.skill_command_history,
            ];
            const source = sources.find((item) => Array.isArray(item) && item.length) || [];
            return source.map((item) => {
                if (typeof item === 'string') {
                    return { title: item, status: '', created_at: '', detail: '' };
                }
                if (!item || typeof item !== 'object') return null;
                return {
                    title: item.title || item.name || item.skill_name || item.command || item.skill || item.message || '--',
                    status: item.status || item.mode || item.outcome || item.result || '',
                    created_at: item.created_at || item.createdAt || item.timestamp || item.time || '',
                    detail: item.detail || item.content || item.note || item.reason || '',
                };
            }).filter(Boolean);
        },

        async refreshSettings() {
            const root = document.getElementById('openclaw-settings-workbench');
            if (!root) return;
            let account = App._accountState;
            if (!account) {
                account = await App._loadAccountState?.().catch(() => null);
            }
            if (!account) {
                App._setAuthGate(true, { reason: '请先登录' });
                return;
            }
            const renderSettings = (state, { focus = false } = {}) => {
                root.innerHTML = this._settingsLayout(account, state || {});
                this._bindSettings(root, account, state || {});
                if (focus) this._focusSettingsSection(root);
            };

            renderSettings(this._state || {}, { focus: true });

            try {
                this._state = await this._loadState();
                renderSettings(this._state);
            } catch (e) {
                console.warn('[OpenClaw] settings refresh failed', e);
            }
        },

        _settingsLayout(account, state) {
            const workspace = account?.workspace || {};
            const settings = workspace.settings || {};
            const confirmations = settings.tool_confirmations || {};
            const permissions = account?.permissions || {};
            const isAdmin = account?.user?.role === 'admin';
            const service = state?.status?.service || {};
            const managedService = state?.status?.managed_service || {};
            const setupCompleted = state?.status?.setup_completed ?? state?.setup?.setup_completed ?? settings.openclaw_setup_completed ?? false;
            const systemTools = state?.tools?.system_tools || [];
            const nativeToolList = this._normalizeToolList(state?.tools?.native_tools?.data ?? state?.tools?.native_tools);
            const nativeToolCount = nativeToolList.length;
            const nativeTools = state?.status?.bridge?.tool_manifest_url ? `已接入 · ${nativeToolCount} 项` : '未接入';
            const managedState = managedService.state || 'unknown';
            const managedLabel = {
                external: '外部服务模式',
                not_installed: '未安装',
                stopped: '已停止',
                starting: '启动中',
                running: '托管运行中',
                failed: '启动失败',
                unknown: '未知',
            }[managedState] || managedState;
            const statusClass = managedService.running || service.ok ? 'online' : 'offline';
            const workspaceUrl = workspace.openclaw_workspace_id
                ? `${location.origin}/?workspace=${encodeURIComponent(workspace.openclaw_workspace_id)}&user=${encodeURIComponent(account?.user?.id || '')}`
                : '';
            const toolConfirmRows = [
                ['模拟盘下单', 'write_paper_trade'],
                ['技能管理', 'manage_skills'],
                ['自选股操作', 'write_watchlist'],
            ];
            const memories = state?.memories?.items || [];
            const reports = state?.reports?.items || [];
            const skills = state?.skills?.items || [];
            const skillCommandHistory = this._skillCommandHistory(state);
            const auditItems = state?.audit?.items || [];
            return `
                <div class="openclaw-settings-page">
                    <div class="openclaw-settings-hero">
                        <div>
                            <div class="openclaw-kicker">完整龙虾设置页</div>
                            <h2>龙虾设置</h2>
                            <p>管理当前工作区的 OpenClaw 连接、权限、技能、记忆、日报和审计。</p>
                        </div>
                        <div class="openclaw-settings-hero-actions">
                            <button class="openclaw-ghost-btn" data-settings-action="refresh">刷新</button>
                            <button class="openclaw-primary-link" data-settings-action="open-chat">打开聊天</button>
                            <button class="openclaw-ghost-btn" data-settings-action="open-native">原生面板</button>
                        </div>
                    </div>
                    <div class="openclaw-settings-grid">
                        <section class="openclaw-settings-card" id="openclaw-settings-profile">
                            <div class="openclaw-side-title">个人资料</div>
                            <div class="openclaw-kv"><span>用户名</span><strong>${App.escapeHTML(account?.user?.username || '--')}</strong></div>
                            <div class="openclaw-kv"><span>昵称</span><strong>${App.escapeHTML(account?.user?.display_name || '--')}</strong></div>
                            <div class="openclaw-kv"><span>邮箱</span><strong>${App.escapeHTML(account?.user?.email || '--')}</strong></div>
                            <div class="openclaw-kv"><span>角色</span><strong>${App.escapeHTML(account?.user?.role || '--')}</strong></div>
                            <div class="openclaw-kv"><span>用户 ID</span><code>${App.escapeHTML(account?.user?.id || '--')}</code></div>
                        </section>
                        <section class="openclaw-settings-card" id="openclaw-settings-security">
                            <div class="openclaw-side-title">API Key / 安全</div>
                            <div class="openclaw-kv"><span>会话</span><strong>浏览器 Cookie 登录</strong></div>
                            <div class="openclaw-kv"><span>OpenClaw Bridge</span><strong>${App.escapeHTML(state?.status?.bridge?.auth || '--')}</strong></div>
                            <div class="openclaw-kv"><span>面板 URL</span><code>${App.escapeHTML(state?.status?.panel_url || '--')}</code></div>
                            <div class="openclaw-kv"><span>嵌入 URL</span><code>${App.escapeHTML(state?.status?.embed_url || '--')}</code></div>
                            <div class="openclaw-kv"><span>工作区 ID</span><code>${App.escapeHTML(workspace.openclaw_workspace_id || '--')}</code></div>
                        </section>
                        <section class="openclaw-settings-card" id="openclaw-settings-workspace">
                            <div class="openclaw-side-title">首次配置</div>
                            <div class="openclaw-status-pill ${setupCompleted ? 'online' : 'offline'}">${setupCompleted ? '已完成' : '待配置'}</div>
                            <div class="openclaw-kv"><span>状态</span><strong>${setupCompleted ? '这个工作区已完成初始化' : '第一次使用先完成向导'}</strong></div>
                            <div class="openclaw-kv"><span>默认入口</span><strong>${App.escapeHTML(settings.native_panel_mode || 'iframe')}</strong></div>
                            <div class="openclaw-kv"><span>工作区</span><code>${App.escapeHTML(workspace.openclaw_workspace_id || '--')}</code></div>
                            <div class="openclaw-service-actions">
                                <button class="btn btn-sm btn-primary" data-settings-action="open-setup">打开配置向导</button>
                                <button class="btn btn-sm" data-settings-action="mark-setup-complete">标记已完成</button>
                            </div>
                        </section>
                        <section class="openclaw-settings-card">
                            <div class="openclaw-side-title">服务状态</div>
                            <div class="openclaw-status-pill ${statusClass}">${service.ok ? 'OpenClaw 在线' : 'OpenClaw 未连接'}</div>
                            <div class="openclaw-status-pill ${statusClass}">${App.escapeHTML(managedLabel)}</div>
                            <div class="openclaw-kv"><span>工作区</span><strong>${App.escapeHTML(workspace.name || '--')}</strong></div>
                            <div class="openclaw-kv"><span>工作区 ID</span><code>${App.escapeHTML(workspace.openclaw_workspace_id || '--')}</code></div>
                            <div class="openclaw-kv"><span>面板模式</span><strong>${App.escapeHTML(settings.native_panel_mode || 'iframe')}</strong></div>
                            <div class="openclaw-kv"><span>桥接</span><strong>${App.escapeHTML(nativeTools)}</strong></div>
                            <div class="openclaw-kv"><span>系统工具</span><strong>${systemTools.length} 项</strong></div>
                            <div class="openclaw-kv"><span>托管模式</span><strong>${managedService.managed ? '启用' : '外部'}</strong></div>
                            <div class="openclaw-kv"><span>端口</span><strong>${App.escapeHTML(String(managedService.port || '--'))}</strong></div>
                            <div class="openclaw-kv"><span>CLI</span><code>${App.escapeHTML(managedService.bin || '--')}</code></div>
                            <div class="openclaw-kv"><span>面板地址</span><code>${App.escapeHTML(workspaceUrl || '--')}</code></div>
                            ${managedService.last_error ? `<div class="openclaw-service-error">${App.escapeHTML(managedService.last_error)}</div>` : ''}
                            <div class="openclaw-service-actions">
                                <button class="btn btn-sm btn-primary" data-settings-action="service-start">启动</button>
                                <button class="btn btn-sm" data-settings-action="service-restart">重启</button>
                                <button class="btn btn-sm btn-outline" data-settings-action="service-stop">停止</button>
                            </div>
                            <pre class="openclaw-log-box">${App.escapeHTML(managedService.recent_logs || '暂无日志')}</pre>
                        </section>
                        <section class="openclaw-settings-card">
                            <div class="openclaw-side-title">工作区设置</div>
                            <div class="form-group">
                                <label>工作区名称</label>
                                <input id="openclaw-workspace-name" value="${App.escapeHTML(workspace.name || '')}" maxlength="80">
                            </div>
                            <div class="form-group">
                                <label>原生面板模式</label>
                                <select id="openclaw-native-mode">
                                    <option value="iframe">嵌入工作台</option>
                                    <option value="external">外部打开</option>
                                </select>
                            </div>
                            <div class="form-group">
                                <label>工具确认</label>
                                <div class="openclaw-setting-stack">
                                    ${toolConfirmRows.map(([label, key]) => `
                                        <label class="openclaw-setting-check">
                                            <input type="checkbox" data-confirm-key="${key}" ${confirmations[key] !== false ? 'checked' : ''}>
                                            <span>${label}</span>
                                        </label>
                                    `).join('')}
                                </div>
                            </div>
                            <div class="openclaw-settings-footnote">这些开关控制当前工作区的默认行为，管理员工作区拥有全部权限。</div>
                        </section>
                        <section class="openclaw-settings-card" id="openclaw-settings-permissions">
                            <div class="openclaw-side-title">权限总览</div>
                            <div class="openclaw-permission-list">
                                ${Object.entries(permissions).map(([key, value]) => `
                                    <label class="openclaw-row openclaw-permission-row">
                                        <span>${App.escapeHTML(key)}</span>
                                        <input type="checkbox" data-permission-key="${App.escapeHTML(key)}" ${value ? 'checked' : ''} disabled>
                                    </label>
                                `).join('')}
                            </div>
                            <div class="openclaw-settings-footnote">${isAdmin ? '管理员工作区默认全开，不在这里单独修改。' : '普通用户仅能看见授权结果，权限由管理员统一配置。'}</div>
                        </section>
                        <section class="openclaw-settings-card" id="openclaw-settings-skills">
                            <div class="openclaw-side-title">Skills</div>
                            <div class="openclaw-actions slim">
                                <button class="btn btn-sm btn-primary" data-settings-action="save-skill">登记 Skill</button>
                            </div>
                            <div class="openclaw-list" id="openclaw-skill-list">
                                ${skills.length ? skills.map((item) => `
                                    <div class="openclaw-item">
                                        <strong>${App.escapeHTML(item.name || '--')}</strong>
                                        <div>${App.escapeHTML([item.version, item.status, item.source].filter(Boolean).join(' · ') || 'installed')}</div>
                                    </div>
                                `).join('') : '<div class="openclaw-empty">暂无 Skill</div>'}
                            </div>
                            <div class="openclaw-history-block">
                                <div class="openclaw-side-title">Skill 命令历史</div>
                                <div class="openclaw-list openclaw-history-list" id="openclaw-skill-command-history">
                                    ${skillCommandHistory.length ? skillCommandHistory.map((item) => `
                                        <div class="openclaw-item">
                                            <strong>${App.escapeHTML(item.title || '--')}</strong>
                                            <div>${App.escapeHTML([item.status, item.created_at, item.detail].filter(Boolean).join(' · ') || 'queued')}</div>
                                        </div>
                                    `).join('') : '<div class="openclaw-empty">暂无技能命令历史</div>'}
                                </div>
                            </div>
                        </section>
                        <section class="openclaw-settings-card">
                            <div class="openclaw-side-title">记忆</div>
                            <div class="openclaw-actions slim">
                                <button class="btn btn-sm btn-primary" data-settings-action="save-memory">保存记忆</button>
                            </div>
                            <div class="openclaw-list" id="openclaw-memory-list">
                                ${memories.length ? memories.map((item) => `
                                    <div class="openclaw-item">
                                        <strong>${App.escapeHTML(item.title || '--')}</strong>
                                        <div>${App.escapeHTML(item.content || '')}</div>
                                    </div>
                                `).join('') : '<div class="openclaw-empty">暂无记忆</div>'}
                            </div>
                        </section>
                        <section class="openclaw-settings-card" id="openclaw-settings-reports">
                            <div class="openclaw-side-title">日报</div>
                            <div class="openclaw-actions slim">
                                <button class="btn btn-sm btn-primary" data-settings-action="generate-report">生成日报</button>
                            </div>
                            <div class="openclaw-list" id="openclaw-report-list">
                                ${reports.length ? reports.map((item) => `
                                    <div class="openclaw-item">
                                        <strong>${App.escapeHTML(item.trade_date || '--')}</strong>
                                        <div>${App.escapeHTML(item.title || '收益日报')}</div>
                                        <button class="openclaw-action-btn" data-openclaw-action="tool-action"
                                            data-tool-name="quant.report.open"
                                            data-tool-native="false"
                                            data-tool-args='${App.escapeHTML(JSON.stringify({ trade_date: item.trade_date || '' }))}'>
                                            打开
                                        </button>
                                    </div>
                                `).join('') : '<div class="openclaw-empty">暂无日报</div>'}
                            </div>
                        </section>
                        <section class="openclaw-settings-card" id="openclaw-settings-audit">
                            <div class="openclaw-side-title">审计日志</div>
                            <div class="openclaw-list" id="openclaw-audit-list">
                                ${auditItems.length ? auditItems.map((item) => `
                                    <div class="openclaw-item">
                                        <strong>${App.escapeHTML(item.action || '--')}</strong>
                                        <div>${App.escapeHTML([item.created_at, item.status, item.reason].filter(Boolean).join(' · ') || '')}</div>
                                    </div>
                                `).join('') : '<div class="openclaw-empty">暂无审计记录</div>'}
                            </div>
                        </section>
                        <section class="openclaw-settings-card">
                            <div class="openclaw-side-title">工具中心</div>
                            <div class="openclaw-tool-grid">
                                ${systemTools.length ? systemTools.map((tool) => `
                                    <button class="openclaw-tool ${tool.allowed ? '' : 'disabled'}" data-tool-name="${App.escapeHTML(tool.name || '')}" data-tool-native="false" ${tool.allowed ? '' : 'disabled'}>
                                        <strong>${App.escapeHTML(tool.label || tool.name || '--')}</strong>
                                        <span>${App.escapeHTML(tool.permission || '')}</span>
                                        <small>${App.escapeHTML(tool.allowed ? '可执行' : '无权限')}</small>
                                    </button>
                                `).join('') : '<div class="openclaw-empty">暂无系统工具</div>'}
                            </div>
                            <div class="openclaw-settings-footnote">当前工作区可用工具与权限绑定，工具执行会进入审计。</div>
                        </section>
                        <section class="openclaw-settings-card">
                            <div class="openclaw-side-title">原生工具</div>
                            <div class="openclaw-tool-grid">
                                ${nativeToolList.length ? nativeToolList.map((name) => `
                                    <button class="openclaw-tool" data-tool-name="${App.escapeHTML(name)}" data-tool-native="true">
                                        <strong>${App.escapeHTML(name)}</strong>
                                        <span>native</span>
                                        <small>原生服务</small>
                                    </button>
                                `).join('') : '<div class="openclaw-empty">原生服务未返回工具</div>'}
                            </div>
                        </section>
                    </div>
                </div>
            `;
        },

        _bindSettings(root, account, state) {
            const workspace = account?.workspace || {};
            const settings = workspace.settings || {};
            const confirmations = settings.tool_confirmations || {};
            const modeInput = root.querySelector('#openclaw-native-mode');
            if (modeInput) {
                modeInput.value = settings.native_panel_mode || 'iframe';
            }
            const nameInput = root.querySelector('#openclaw-workspace-name');
            const saveWorkspace = async () => {
                const name = nameInput?.value.trim() || workspace.name || '';
                const mode = modeInput?.value || 'iframe';
                const nextConfirmations = {};
                root.querySelectorAll('[data-confirm-key]').forEach((box) => {
                    nextConfirmations[box.dataset.confirmKey] = box.checked !== false;
                });
                const nextSettings = {
                    native_panel_mode: mode,
                    tool_confirmations: {
                        ...confirmations,
                        ...nextConfirmations,
                    },
                };
                const updates = [];
                if (name && name !== workspace.name) {
                    updates.push(this._updateWorkspaceName(name));
                }
                updates.push(this._updateWorkspaceSettings(nextSettings));
                await Promise.all(updates);
                await App._loadAccountState?.();
                App.toast('龙虾设置已保存', 'success');
                await this.refreshSettings();
            };

            root.querySelectorAll('[data-settings-action]').forEach((btn) => {
                btn.addEventListener('click', async (e) => {
                    e.preventDefault();
                    const action = btn.dataset.settingsAction;
                    if (action === 'refresh') {
                        await this.refreshSettings();
                        return;
                    }
                    if (action === 'open-chat') {
                        App.switchTab('openclaw');
                        return;
                    }
                    if (action === 'open-setup') {
                        this._showSetupWizard(true);
                        return;
                    }
                    if (action === 'mark-setup-complete') {
                        await this.completeSetup({ setup_completed: true });
                        return;
                    }
                    if (action === 'open-native') {
                        await this.openNativePanel();
                        return;
                    }
                    if (action === 'service-start') {
                        await this.controlService('start');
                        return;
                    }
                    if (action === 'service-restart') {
                        await this.controlService('restart');
                        return;
                    }
                    if (action === 'service-stop') {
                        await this.controlService('stop');
                        return;
                    }
                    if (action === 'save-skill') {
                        await this.recordSkillFromPrompt();
                        return;
                    }
                    if (action === 'save-memory') {
                        await this.createMemoryFromPrompt();
                        return;
                    }
                    if (action === 'generate-report') {
                        await this.generateDailyReport();
                        return;
                    }
                });
            });

            root.querySelectorAll('[data-tool-name]').forEach((btn) => {
                btn.addEventListener('click', async () => {
                    const toolName = btn.dataset.toolName || '';
                    const native = btn.dataset.toolNative === 'true';
                    if (!toolName) return;
                    if (!confirm(`执行 ${toolName}？`)) return;
                    await App.fetchJSON('/api/openclaw/tools/invoke', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ tool: toolName, native, arguments: {} }),
                    });
                    await this.refreshSettings();
                });
            });

            root.querySelectorAll('[data-permission-key]').forEach((box) => {
                box.disabled = true;
            });

            root.querySelector('#openclaw-workspace-name')?.addEventListener('change', () => saveWorkspace().catch((e) => App.toast(e.message || '保存失败', 'error')));
            root.querySelector('#openclaw-native-mode')?.addEventListener('change', () => saveWorkspace().catch((e) => App.toast(e.message || '保存失败', 'error')));
            root.querySelectorAll('[data-confirm-key]').forEach((box) => {
                box.addEventListener('change', () => saveWorkspace().catch((e) => App.toast(e.message || '保存失败', 'error')));
            });
        },

        _focusSettingsSection(root) {
            const section = App._openclawSettingsSection || '';
            if (!section) {
                return;
            }
            const target = root.querySelector(`#openclaw-settings-${section}`);
            if (target && typeof target.scrollIntoView === 'function') {
                requestAnimationFrame(() => target.scrollIntoView({ block: 'start', behavior: 'smooth' }));
            }
            App._openclawSettingsSection = '';
        },

        async _updateWorkspaceName(name) {
            return App.fetchJSON('/api/account/workspace/name', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name }),
            });
        },

        async _updateWorkspaceSettings(settings) {
            return App.fetchJSON('/api/account/workspace/settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ settings }),
            });
        },

        async recordSkillFromPrompt() {
            const name = prompt('Skill 名称');
            if (!name) return;
            await App.fetchJSON('/api/openclaw/skills', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, version: '1.0.0', status: 'installed', source: 'manual', permissions: [] }),
            });
            await this.refreshSettings();
        },

        async createMemoryFromPrompt() {
            const content = prompt('记忆内容');
            if (!content) return;
            await App.fetchJSON('/api/openclaw/memories', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: content.slice(0, 40), content }),
            });
            await this.refreshSettings();
        },

        async generateDailyReport() {
            const tradeDate = prompt('交易日期（YYYY-MM-DD，可留空）') || '';
            const data = await App.fetchJSON('/api/openclaw/reports/daily/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ trade_date: tradeDate }),
            });
            const report = data?.result?.report || data?.report || null;
            await this.refreshSettings();
            if (report) {
                this._showReportPreview(report);
            }
        },

        async controlService(action) {
            const data = await App.fetchJSON(`/api/openclaw/service/${action}`, {
                method: 'POST',
                silent: true,
            });
            App.toast(`服务${action === 'start' ? '启动' : action === 'restart' ? '重启' : '停止'}完成`, 'success');
            await this.refreshSettings();
            return data;
        },

        async completeSetup(payload = {}) {
            const data = await App.fetchJSON('/api/openclaw/setup/complete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    setup_completed: payload.setup_completed !== false,
                    native_panel_mode: payload.native_panel_mode || 'iframe',
                    service_mode: payload.service_mode || 'managed',
                }),
            });
            await App._loadAccountState?.();
            await this.refresh('openclaw');
            return data;
        },

        _showSetupWizard(force = false) {
            if (!force && document.getElementById('openclaw-setup-modal')) return;
            if (document.getElementById('openclaw-setup-modal')) {
                document.getElementById('openclaw-setup-modal')?.remove();
            }
            const settings = App._accountState?.workspace?.settings || {};
            const serviceMode = settings.openclaw_service_mode || 'managed';
            const panelMode = settings.native_panel_mode || 'iframe';
            const overlay = document.createElement('div');
            overlay.id = 'openclaw-setup-modal';
            overlay.className = 'modal-overlay active';
            overlay.innerHTML = `
                <div class="modal openclaw-setup-modal">
                    <h2>初始化龙虾工作区</h2>
                    <p class="openclaw-setup-copy">先完成这个向导，后面就能直接进入聊天和设置页。</p>
                    <div class="form-group">
                        <label>默认面板模式</label>
                        <select id="openclaw-setup-panel-mode">
                            <option value="iframe" ${panelMode === 'iframe' ? 'selected' : ''}>嵌入工作台</option>
                            <option value="external" ${panelMode === 'external' ? 'selected' : ''}>外部打开</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>服务模式</label>
                        <select id="openclaw-setup-service-mode">
                            <option value="managed" ${serviceMode === 'managed' ? 'selected' : ''}>托管模式</option>
                            <option value="external" ${serviceMode === 'external' ? 'selected' : ''}>外部服务</option>
                        </select>
                    </div>
                    <label class="openclaw-setting-check">
                        <input type="checkbox" id="openclaw-setup-confirm" checked>
                        <span>我已经理解这只是初始化，不影响历史会话</span>
                    </label>
                    <div class="modal-actions">
                        <button class="btn btn-ghost" data-openclaw-setup-action="skip">稍后</button>
                        <button class="btn btn-primary" data-openclaw-setup-action="save">保存并继续</button>
                    </div>
                </div>
            `;
            document.body.appendChild(overlay);
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) {
                    overlay.remove();
                }
            });
            overlay.querySelector('[data-openclaw-setup-action="skip"]')?.addEventListener('click', () => {
                this._setSetupDismissed(true);
                overlay.remove();
            });
            overlay.querySelector('[data-openclaw-setup-action="save"]')?.addEventListener('click', async () => {
                const panelMode = overlay.querySelector('#openclaw-setup-panel-mode')?.value || 'iframe';
                const serviceModeValue = overlay.querySelector('#openclaw-setup-service-mode')?.value || 'managed';
                const confirmed = overlay.querySelector('#openclaw-setup-confirm')?.checked !== false;
                if (!confirmed) {
                    App.toast('请先确认后继续', 'warning');
                    return;
                }
                await this.completeSetup({
                    setup_completed: true,
                    native_panel_mode: panelMode,
                    service_mode: serviceModeValue,
                });
                this._setSetupDismissed(false);
                overlay.remove();
            });
        },

        _setupDismissed() {
            const workspaceId = App._accountState?.workspace?.openclaw_workspace_id || '';
            return workspaceId ? sessionStorage.getItem(`openclaw_setup_dismissed:${workspaceId}`) === '1' : false;
        },

        _setSetupDismissed(value) {
            const workspaceId = App._accountState?.workspace?.openclaw_workspace_id || '';
            if (!workspaceId) return;
            const key = `openclaw_setup_dismissed:${workspaceId}`;
            if (value) {
                sessionStorage.setItem(key, '1');
            } else {
                sessionStorage.removeItem(key);
            }
        },

        _normalizeToolList(payload) {
            if (!payload) return [];
            const source = Array.isArray(payload)
                ? payload
                : Array.isArray(payload.tools)
                    ? payload.tools
                    : Array.isArray(payload.items)
                        ? payload.items
                        : Array.isArray(payload.data)
                            ? payload.data
                            : [];
            return source.map((item) => {
                if (typeof item === 'string') return item.trim();
                if (!item || typeof item !== 'object') return '';
                return (item.name || item.label || item.id || item.tool || '').trim();
            }).filter(Boolean);
        },

        _layout() {
            return `
                <div class="openclaw-shell is-rail-collapsed">
                    <section class="openclaw-main">
                        <div class="openclaw-chat-shell">
                            <div class="openclaw-chat-top">
                                <div class="openclaw-title-stack">
                                    <span class="openclaw-kicker">AI 工作区助手</span>
                                    <h2>龙虾</h2>
                                    <p id="openclaw-chat-subtitle">随时可以开始新的对话。</p>
                                </div>
                                <div class="openclaw-header-actions">
                                    <button class="openclaw-ghost-btn" data-openclaw-action="clear-chat">清空</button>
                                    <button class="openclaw-ghost-btn" data-openclaw-action="open-settings">设置</button>
                                </div>
                            </div>
                            <div class="openclaw-messages" id="openclaw-messages"></div>
                            <div class="openclaw-quick-row">
                                <button class="openclaw-chip" data-openclaw-action="quick" data-prompt="帮我总结今天模拟盘的收益情况">收益日报</button>
                                <button class="openclaw-chip" data-openclaw-action="quick" data-prompt="把 600519 加入自选，并说明关注理由">加入自选</button>
                                <button class="openclaw-chip" data-openclaw-action="quick" data-prompt="打开 000001 的股票详情">股票详情</button>
                            </div>
                            <div class="openclaw-input-row">
                                <textarea id="openclaw-input" rows="2" placeholder="问龙虾：分析一只股票、加入自选、生成模拟盘日报..."></textarea>
                                <button class="openclaw-stop-btn" data-openclaw-action="stop">停止</button>
                                <button class="openclaw-send-btn" data-openclaw-action="send">发送</button>
                            </div>
                            <div class="openclaw-composer-hint-slot" id="openclaw-composer-hint"></div>
                        </div>
                    </section>
                    <aside class="openclaw-rail" id="openclaw-conversation-rail"></aside>
                </div>
            `;
        },

        _renderStatus(data) {
            const status = data?.status;
            const workspace = status?.workspace || App._accountState?.workspace || {};
            const service = status?.service || {};
            const permissions = status?.permissions || App._accountState?.permissions || {};
            const connected = service.ok === true;
            const subtitle = document.getElementById('openclaw-chat-subtitle');
            if (subtitle) {
                subtitle.textContent = '已准备好。';
            }
            const card = document.getElementById('openclaw-status-card');
            if (card) {
                card.classList.remove('openclaw-loading');
                card.innerHTML = `
                    <div class="openclaw-status-pill ${connected ? 'online' : 'offline'}">${connected ? '原生服务在线' : '本地兜底模式'}</div>
                    <div class="openclaw-context-row"><span>工作区</span><strong>${App.escapeHTML(workspace.name || '--')}</strong></div>
                    <div class="openclaw-context-row"><span>模式</span><strong>${connected ? 'OpenClaw' : '平台助手'}</strong></div>
                    <div class="openclaw-context-row"><span>权限</span><strong>${permissions.admin ? 'Admin' : 'User'}</strong></div>
                    <div class="openclaw-context-code">${App.escapeHTML(workspace.openclaw_workspace_id || '--')}</div>
                `;
            }
            this._renderMemoryList(data?.memories?.items || []);
            this._renderCompactList(data?.reports?.items || [], data?.skills?.items || []);
            this._renderSkillCommandHistory(data);
            this._updateComposerHint();
        },

        _renderMemoryList(items) {
            const el = document.getElementById('openclaw-memory-list');
            if (!el) return;
            el.classList.remove('openclaw-loading');
            el.innerHTML = items.length ? items.map((item) => `
                <div class="openclaw-item">
                    <strong>${App.escapeHTML(item.title || '--')}</strong>
                    <div>${App.escapeHTML(item.content || '')}</div>
                </div>
            `).join('') : '<div class="openclaw-empty">暂无记忆</div>';
        },

        _renderCompactList(reports, skills) {
            const el = document.getElementById('openclaw-compact-list');
            if (!el) return;
            el.classList.remove('openclaw-loading');
            const reportItems = reports.map((item) => `
                <div class="openclaw-item">
                    <strong>${App.escapeHTML(item.trade_date || '--')}</strong>
                    <div>${App.escapeHTML(item.title || '收益日报')}</div>
                </div>
            `);
            const skillItems = skills.map((item) => `
                <div class="openclaw-item">
                    <strong>${App.escapeHTML(item.name || '--')}</strong>
                    <div>${App.escapeHTML(item.status || 'installed')}</div>
                </div>
            `);
            el.innerHTML = [...reportItems, ...skillItems].join('') || '<div class="openclaw-empty">暂无日报或 Skill</div>';
        },

        _renderSkillCommandHistory(data) {
            const el = document.getElementById('openclaw-skill-command-history');
            if (!el) return;
            const history = this._skillCommandHistory(data);
            el.innerHTML = history.length ? history.map((item) => `
                <div class="openclaw-item">
                    <strong>${App.escapeHTML(item.title || '--')}</strong>
                    <div>${App.escapeHTML([item.status, item.created_at, item.detail].filter(Boolean).join(' · ') || 'queued')}</div>
                </div>
            `).join('') : '<div class="openclaw-empty">暂无技能命令历史</div>';
        },

        _updateComposerHint() {
            const el = document.getElementById('openclaw-composer-hint');
            if (!el) return;
            const input = document.getElementById('openclaw-input');
            state.skillCommandHint = this._skillCommandHint(input?.value || state.skillCommandHint || '');
            el.innerHTML = state.skillCommandHint ? `<span class="openclaw-composer-chip">${App.escapeHTML(state.skillCommandHint)}</span>` : '';
        },

        _restoreComposerDraft(draft) {
            const input = document.getElementById('openclaw-input');
            if (input && draft) {
                input.value = draft;
            }
            state.skillCommandHint = this._skillCommandHint(input?.value || '');
            this._updateComposerHint();
        },

        _messagesForActiveConversation() {
            const convId = Conversations?.getActiveConversationId?.() || '';
            if (!convId) return [];
            if (!state.messagesByConversation.has(convId)) {
                state.messagesByConversation.set(convId, []);
            }
            return state.messagesByConversation.get(convId);
        },

        _ensureActiveConversation() {
            const convId = Conversations?.ensureConversationId?.() || '';
            if (!state.messagesByConversation.has(convId)) {
                state.messagesByConversation.set(convId, []);
            }
            state.currentConversationId = convId;
            return convId;
        },

        async _restoreConversationIfNeeded() {
            const convId = Conversations?.getActiveConversationId?.() || '';
            if (!convId || convId === state.lastLoadedConversationId) {
                return;
            }
            const resp = await App.fetchJSON(`/api/openclaw/conversations/${encodeURIComponent(convId)}`, { silent: true }).catch(() => null);
            if ((Conversations?.getActiveConversationId?.() || '') !== convId) {
                return;
            }
            const currentMessages = state.messagesByConversation.get(convId) || [];
            if (currentMessages.length > 0) {
                state.currentConversationId = convId;
                state.lastLoadedConversationId = convId;
                return;
            }
            const conv = resp?.data || null;
            if (conv?.messages) {
                state.messagesByConversation.set(convId, conv.messages.map((m) => ({ ...m })));
                this._messages = state.messagesByConversation.get(convId);
                this._renderMessages();
            }
            state.currentConversationId = convId;
            state.lastLoadedConversationId = convId;
        },

        async startNewConversation(options = {}) {
            this.stop();
            this._dismissSetupWizard();
            const id = Conversations?.createConversationId?.() || `oc_${Date.now()}`;
            Conversations?.setActiveConversationId?.(id);
            state.messagesByConversation.set(id, []);
            this._messages = state.messagesByConversation.get(id);
            state.currentConversationId = id;
            state.lastLoadedConversationId = '';
            this._renderMessages();
            Conversations?.render?.();
            if (options.refresh === true) {
                await Conversations?.refresh?.();
            }
        },

        async openConversation(id) {
            this.stop();
            this._dismissSetupWizard();
            const convId = String(id || '').trim();
            if (!convId) return;
            const conv = await Conversations?.openConversation?.(convId);
            Conversations?.setActiveConversationId?.(convId);
            state.currentConversationId = convId;
            state.lastLoadedConversationId = convId;
            const messages = Array.isArray(conv?.messages) ? conv.messages.map((m) => ({ ...m })) : [];
            state.messagesByConversation.set(convId, messages);
            this._messages = messages;
            this._renderMessages();
            Conversations?.render?.();
        },

        async deleteConversation(id) {
            const convId = String(id || '').trim();
            if (!convId) return;
            const wasActive = Conversations?.getActiveConversationId?.() === convId;
            await Conversations?.deleteConversation?.(convId);
            state.messagesByConversation.delete(convId);
            if (wasActive) {
                const nextId = Conversations?.getActiveConversationId?.() || '';
                if (nextId) {
                    await this.openConversation(nextId);
                } else {
                    await this.startNewConversation({ refresh: false });
                }
            } else {
                Conversations?.render?.();
            }
        },

        async send(promptText = '') {
            const input = document.getElementById('openclaw-input');
            const text = (promptText || input?.value || '').trim();
            if (!text) return;
            state.skillCommandHint = this._skillCommandHint(text);
            if (input) input.value = '';
            if (state.pendingRequest) {
                this.stop(true);
            }
            this._dismissSetupWizard();

            const convId = this._ensureActiveConversation();
            const messages = state.messagesByConversation.get(convId) || [];
            messages.push({ role: 'user', content: text, skillCommandHint: Boolean(state.skillCommandHint) });
            messages.push({ role: 'assistant', content: '正在思考...', pending: true, skillCommandHint: Boolean(state.skillCommandHint) });
            Conversations?.markLocalConversation?.(convId, messages);
            this._messages = messages;
            this._renderMessages();

            const controller = new AbortController();
            state.pendingRequest = controller;
            state.pendingConversationId = convId;
            this._setStreaming(true);

            const history = messages
                .filter((m) => !m.pending)
                .slice(-20)
                .map((m) => ({ role: m.role, content: m.content }));
            try {
                const data = await App.fetchJSON('/api/openclaw/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: text, history }),
                    timeout: 60000,
                    signal: controller.signal,
                });
                const pending = messages.findLast?.((m) => m.pending) || messages.find((m) => m.pending);
                if (pending) {
                    pending.pending = false;
                    pending.content = data?.content || '龙虾没有返回内容。';
                    pending.mode = data?.mode || '';
                    pending.skillCommand = data?.mode === 'skill-command';
                    pending.skillCommandHint = Boolean(state.skillCommandHint);
                    pending.actions = this._extractSuggestedActions(data);
                    pending.toolResult = data?.tool_result || null;
                    pending.generatedAt = Date.now();
                    if (data?.mode === 'system-action' && data?.detected_action?.tool) {
                        this._runAfterToolAction(data.detected_action.tool, data.tool_result);
                    }
                }
            } catch (e) {
                const pending = messages.findLast?.((m) => m.pending) || messages.find((m) => m.pending);
                if (pending) {
                    pending.pending = false;
                    if (e?.name === 'AbortError') {
                        pending.canceled = true;
                        pending.content = '已停止';
                    } else {
                        pending.error = true;
                        pending.content = e.message || '发送失败';
                    }
                }
            } finally {
                if (state.pendingRequest === controller) {
                    state.pendingRequest = null;
                    state.pendingConversationId = '';
                }
                state.skillCommandHint = '';
                this._setStreaming(false);
                this._updateComposerHint();
            }
            state.messagesByConversation.set(convId, messages);
            if ((Conversations?.getActiveConversationId?.() || convId) === convId) {
                Conversations?.setActiveConversationId?.(convId, { persist: true, render: false });
                state.currentConversationId = convId;
                this._messages = messages;
            }
            this._renderMessages();
            await this._persistConversation(convId);
            await Conversations?.refresh?.();
        },

        stop(silent = false) {
            const convId = state.pendingConversationId || Conversations?.getActiveConversationId?.() || state.currentConversationId || '';
            if (state.pendingRequest) {
                state.pendingRequest.abort();
                state.pendingRequest = null;
                state.pendingConversationId = '';
            }
            this._setStreaming(false);
            const messages = (convId && state.messagesByConversation.get(convId)) || this._messages || [];
            if (convId && messages.length) {
                state.messagesByConversation.set(convId, messages);
                Conversations?.setActiveConversationId?.(convId, { persist: true, render: false });
                state.currentConversationId = convId;
                this._messages = messages;
            }
            const pending = messages.findLast?.((m) => m.pending) || messages.find((m) => m.pending);
            if (pending) {
                pending.pending = false;
                pending.canceled = true;
                pending.content = '已停止';
                this._renderMessages();
                this._persistConversation(convId || Conversations?.getActiveConversationId?.() || state.currentConversationId || '');
                if (!silent) {
                    App.toast('已停止本次回复', 'info');
                }
            }
        },

        _renderMessages() {
            const el = document.getElementById('openclaw-messages');
            if (!el) return;
            document.querySelector('.openclaw-chat-shell')?.classList.toggle('has-messages', Boolean(this._messages.length));
            if (!this._messages.length) {
                el.innerHTML = `
                    <div class="openclaw-welcome">
                        <span class="openclaw-welcome-label">开始对话</span>
                        <strong>你好，我是龙虾。</strong>
                        <p>我可以先陪你聊，也可以帮你处理自选股、股票详情、模拟盘复盘和收益日报。</p>
                    </div>
                `;
                return;
            }
            el.innerHTML = this._messages.map((msg) => `
                <div class="openclaw-message ${msg.role === 'user' ? 'is-user' : 'is-assistant'} ${msg.error ? 'is-error' : ''} ${msg.canceled ? 'is-canceled' : ''}">
                    <div class="openclaw-message-role">${msg.role === 'user' ? '你' : '龙虾'}</div>
                    <div class="openclaw-message-body">${this._renderText(msg.content)}</div>
                    ${this._renderMessageMeta(msg)}
                    ${this._renderSuggestedActions(msg)}
                </div>
            `).join('');
            el.scrollTop = el.scrollHeight;
            this._setStreaming(Boolean(state.pendingRequest));
        },

        _setStreaming(isStreaming) {
            document.querySelector('.openclaw-chat-shell')?.classList.toggle('is-streaming', Boolean(isStreaming));
        },

        _renderSuggestedActions(msg) {
            if (msg.role !== 'assistant') return '';
            const actions = Array.isArray(msg.actions) ? msg.actions : [];
            if (!actions.length) return '';
            return `
                <div class="openclaw-action-row">
                    ${actions.slice(0, 4).map((action) => `
                        ${this._renderActionButton(action)}
                    `).join('')}
                </div>
            `;
        },

        _renderActionButton(action) {
            const confirmation = action.confirmation || null;
            const isConfirm = Boolean(action.confirm || confirmation);
            const buttonClass = [
                'openclaw-action-btn',
                isConfirm ? 'is-confirm' : '',
                action.tool === 'quant.paper.close_position' ? 'is-danger' : '',
            ].filter(Boolean).join(' ');
            const tokenAttr = action.confirmation_token
                ? ` data-confirmation-token="${App.escapeHTML(action.confirmation_token)}"`
                : '';
            return `
                ${confirmation ? this._renderConfirmationCard(action) : ''}
                <button class="${buttonClass}" data-openclaw-action="tool-action"
                    data-tool-name="${App.escapeHTML(action.tool || '')}"
                    data-tool-native="${action.native ? 'true' : 'false'}"
                    data-confirm="${isConfirm ? 'true' : 'false'}"
                    data-tool-args='${App.escapeHTML(JSON.stringify(action.arguments || {}))}'${tokenAttr}
                    ${action.disabled ? 'disabled' : ''}>
                    ${App.escapeHTML(action.label || action.tool || '执行')}
                </button>
            `;
        },

        _renderConfirmationCard(action) {
            const confirmation = action.confirmation || {};
            const items = Array.isArray(confirmation.items) ? confirmation.items : [];
            return `
                <div class="openclaw-confirm-card">
                    <div class="openclaw-confirm-head">
                        <strong>${App.escapeHTML(confirmation.title || '需要确认')}</strong>
                        <span>模拟盘</span>
                    </div>
                    <div class="openclaw-confirm-grid">
                        ${items.map((item) => `
                            <div>
                                <span>${App.escapeHTML(item.label || '--')}</span>
                                <strong>${App.escapeHTML(item.value || '--')}</strong>
                            </div>
                        `).join('')}
                    </div>
                    <div class="openclaw-confirm-risk">${App.escapeHTML(confirmation.risk || '确认后会执行该操作。')}</div>
                </div>
            `;
        },

        _extractSuggestedActions(data) {
            const actions = Array.isArray(data?.actions) ? [...data.actions] : [];
            const content = String(data?.content || '');
            const toolResult = data?.tool_result || (data?.tool ? data : {});
            const result = toolResult?.result || toolResult?.output || {};

            const code = this._extractCode(content) || result?.code || '';
            const hasAction = (tool) => actions.some((action) => action?.tool === tool);
            if ((toolResult?.tool === 'quant.watchlist.add' || /加入自选/.test(content)) && !hasAction('quant.watchlist.add')) {
                if (code) {
                    actions.push({ tool: 'quant.watchlist.add', label: '加入自选', arguments: { code } });
                }
            }
            if ((toolResult?.tool === 'quant.stock.open' || /打开.*详情/.test(content)) && !hasAction('quant.stock.open')) {
                if (code) {
                    actions.push({ tool: 'quant.stock.open', label: '打开详情', arguments: { code } });
                }
            }
            if ((toolResult?.tool === 'quant.report.generate_daily' || /日报/.test(content)) && !hasAction('quant.report.generate_daily')) {
                actions.push({ tool: 'quant.report.generate_daily', label: '生成日报', arguments: {} });
            }
            if ((toolResult?.tool === 'quant.report.open' || /日报/.test(content)) && !hasAction('quant.report.open')) {
                const tradeDate = result?.report?.trade_date || '';
                actions.push({ tool: 'quant.report.open', label: '查看日报', arguments: { trade_date: tradeDate } });
            }
            if ((toolResult?.tool === 'quant.paper.summary' || /模拟盘摘要|持仓/.test(content)) && !hasAction('quant.paper.summary')) {
                actions.push({ tool: 'quant.paper.summary', label: '查看摘要', arguments: {} });
            }
            return this._dedupeActions(actions);
        },

        _dedupeActions(actions) {
            const seen = new Set();
            return (Array.isArray(actions) ? actions : []).filter((action) => {
                const key = `${action?.tool || ''}:${JSON.stringify(action?.arguments || {})}`;
                if (seen.has(key)) return false;
                seen.add(key);
                return Boolean(action?.tool);
            });
        },

        _extractCode(text) {
            const match = String(text || '').match(/\b(\d{6})\b/);
            return match ? match[1] : '';
        },

        async runSuggestedAction(btn) {
            const toolName = btn?.dataset?.toolName || '';
            const native = btn?.dataset?.toolNative === 'true';
            let args = {};
            try {
                args = JSON.parse(btn?.dataset?.toolArgs || '{}');
            } catch {}
            if (!toolName) return;
            const label = this._ACTION_LABELS[toolName] || toolName;
            const needsConfirmation = btn?.dataset?.confirm === 'true';
            const confirmationToken = btn?.dataset?.confirmationToken || '';
            if (needsConfirmation && !confirmationToken) {
                App.toast('确认凭证缺失，请重新发起这次操作', 'error');
                return;
            }
            const originalText = btn?.textContent || label;
            if (btn) {
                btn.disabled = true;
                btn.textContent = needsConfirmation ? '正在提交...' : '执行中...';
            }
            try {
                const data = await App.fetchJSON('/api/openclaw/tools/invoke', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        tool: toolName,
                        native,
                        arguments: args,
                        confirmed: needsConfirmation,
                        confirmation_token: confirmationToken,
                    }),
                    timeout: 60000,
                });
                const convId = Conversations?.getActiveConversationId?.() || this._ensureActiveConversation();
                const messages = state.messagesByConversation.get(convId) || [];
                messages.push({
                    role: 'assistant',
                    content: data?.content || `${label} 已执行。`,
                    mode: native ? 'native' : 'system',
                    actions: this._extractSuggestedActions(data),
                    toolResult: data,
                });
                state.messagesByConversation.set(convId, messages);
                this._messages = messages;
                this._renderMessages();
                this._runAfterToolAction(toolName, data);
                await this._persistConversation(convId);
            } catch (e) {
                const convId = Conversations?.getActiveConversationId?.() || this._ensureActiveConversation();
                const messages = state.messagesByConversation.get(convId) || [];
                messages.push({
                    role: 'assistant',
                    content: `执行失败：${e.message || '未知错误'}`,
                    error: true,
                });
                state.messagesByConversation.set(convId, messages);
                this._messages = messages;
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = originalText;
                }
            }
            this._renderMessages();
            Conversations?.refresh?.();
        },

        _runAfterToolAction(toolName, data) {
            this._afterToolAction(toolName, data).catch((e) => {
                console.warn('[OpenClaw] action follow-up failed', e);
            });
        },

        async _afterToolAction(toolName, data) {
            const result = data?.result || data?.tool_result?.result || {};
            const code = result?.code || result?.order?.code || '';
            if (toolName === 'quant.stock.open' && code && typeof App.openStockDetail === 'function') {
                await App.openStockDetail(code, { source: 'openclaw:tool-action' });
                return;
            }
            if (toolName === 'quant.report.open') {
                await App.switchTab('openclaw-settings');
                await this.refreshSettings();
                const report = data?.result?.report || data?.tool_result?.result?.report || {};
                this._showReportPreview(report);
                return;
            }
            if (toolName === 'quant.watchlist.add' || toolName === 'quant.watchlist.remove') {
                await globalThis.Watchlist?._refreshWatchlistTable?.();
                globalThis.App?.emit?.('data:watchlist-updated', { source: 'openclaw' });
                if (App.currentTab === 'overview') {
                    await App.loadOverview?.();
                }
                return;
            }
            if (toolName === 'quant.report.generate_daily' || toolName === 'quant.paper.summary') {
                this._state = await this._loadState();
                this._renderStatus(this._state);
                if (App.currentTab === 'openclaw-settings') {
                    await this.refreshSettings();
                }
            }
            if (toolName === 'quant.paper.order' || toolName === 'quant.paper.close_position') {
                await App.switchTab('paper');
                globalThis.PaperTrading?.switchSubTab?.('trade');
                await globalThis.PaperTrading?.loadOrders?.();
                await globalThis.PaperTrading?.loadPositions?.();
                globalThis.App?.emit?.('data:portfolio-updated', { source: 'openclaw' });
                this._state = await this._loadState();
                this._renderStatus(this._state);
            }
        },

        _renderText(text) {
            return App.escapeHTML(text || '').replace(/\n/g, '<br>');
        },

        _dismissSetupWizard() {
            this._setSetupDismissed(true);
            document.getElementById('openclaw-setup-modal')?.remove();
        },

        _renderMessageMeta(msg) {
            if (msg.role === 'user') {
                return msg.skillCommandHint ? '<div class="openclaw-message-meta"><span class="openclaw-status-chip is-local">技能命令候选</span></div>' : '';
            }
            const chips = [];
            if (msg.mode) chips.push(`<span class="openclaw-status-chip">${App.escapeHTML(msg.mode)}</span>`);
            if (msg.mode === 'skill-command') chips.push('<span class="openclaw-status-chip is-quiet">技能命令</span>');
            return chips.length ? `<div class="openclaw-message-meta">${chips.join(' ')}</div>` : '';
        },

        clearChat() {
            const convId = Conversations?.getActiveConversationId?.() || this._ensureActiveConversation();
            const messages = [];
            state.messagesByConversation.set(convId, messages);
            this._messages = messages;
            state.skillCommandHint = '';
            this._renderMessages();
            this._updateComposerHint();
            void this._persistConversation(convId);
        },

        async openNativePanel() {
            const data = await App.fetchJSON('/api/openclaw/panel', { silent: true }).catch(() => null);
            const url = data?.url || '';
            if (!url) {
                App.toast('OpenClaw 面板地址未配置', 'warning');
                return;
            }
            window.open(url, '_blank', 'noopener');
        },

        async _persistConversation(convId) {
            const id = String(convId || '').trim();
            if (!id) return;
            const messages = state.messagesByConversation.get(id) || [];
            const title = this._conversationTitle(messages);
            await Conversations?.saveConversation?.({
                id,
                title,
                messages: messages.filter((m) => !m.pending).map((m) => ({
                    role: m.role,
                    content: m.content,
                    mode: m.mode || '',
                    skillCommand: m.skillCommand === true,
                    skillCommandHint: m.skillCommandHint === true,
                    canceled: m.canceled === true,
                    error: m.error === true,
                })),
            });
        },

        _conversationTitle(messages) {
            const userMessage = (messages || []).find((m) => m.role === 'user' && String(m.content || '').trim());
            return userMessage ? String(userMessage.content).trim().slice(0, 30) : '新对话';
        },

        _showReportPreview(report = {}) {
            const existing = document.getElementById('openclaw-report-modal');
            if (existing) existing.remove();
            const overlay = document.createElement('div');
            overlay.id = 'openclaw-report-modal';
            overlay.className = 'modal-overlay';
            const content = report.content || {};
            const review = Array.isArray(content.review) ? content.review : [];
            overlay.innerHTML = `
                <div class="modal openclaw-report-modal">
                    <h2>${App.escapeHTML(report.title || '模拟盘收益日报')}</h2>
                    <p class="openclaw-setup-copy">${App.escapeHTML(report.trade_date || '--')}</p>
                    <div class="openclaw-report-grid">
                        <div><span>总权益</span><strong>${App.escapeHTML(String(content.summary?.total_equity ?? '--'))}</strong></div>
                        <div><span>当日收益</span><strong>${App.escapeHTML(String(content.summary?.daily_return ?? '--'))}</strong></div>
                        <div><span>累计收益</span><strong>${App.escapeHTML(String(content.summary?.cumulative_return ?? '--'))}</strong></div>
                        <div><span>最大回撤</span><strong>${App.escapeHTML(String(content.summary?.max_drawdown ?? '--'))}</strong></div>
                    </div>
                    <div class="openclaw-report-review">
                        ${review.length ? review.map((line) => `<p>${App.escapeHTML(line)}</p>`).join('') : '<p>暂无复盘内容</p>'}
                    </div>
                    <div class="modal-actions">
                        <button class="btn btn-ghost" data-openclaw-report-action="close">关闭</button>
                    </div>
                </div>
            `;
            document.body.appendChild(overlay);
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) overlay.remove();
            });
            overlay.querySelector('[data-openclaw-report-action="close"]')?.addEventListener('click', () => overlay.remove());
        },

        async maybeInitForTab(tab) {
            if (tab === 'openclaw') {
                await this.init('openclaw');
                return;
            }
            if (tab === 'openclaw-settings') {
                await this.init('openclaw-settings');
            }
        },
    };

    global.OpenClawWorkbench = Workbench;
})(window);
