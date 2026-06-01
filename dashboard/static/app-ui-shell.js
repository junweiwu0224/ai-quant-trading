/* ── App UI shell: theme, PWA, shortcuts, command palette ── */

if (!globalThis.App) {
    globalThis.App = {};
}

Object.assign(globalThis.App, {
    _initTheme() {
        const saved = localStorage.getItem('theme');
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        const theme = saved || (prefersDark ? 'dark' : 'light');
        document.documentElement.setAttribute('data-theme', theme);

        const btn = document.getElementById('theme-toggle');
        if (btn) {
            btn.addEventListener('click', () => {
                const current = document.documentElement.getAttribute('data-theme');
                const next = current === 'dark' ? 'light' : 'dark';
                document.documentElement.setAttribute('data-theme', next);
                localStorage.setItem('theme', next);
                if (typeof ChartFactory !== 'undefined') ChartFactory._colorCache = null;
            });
        }
    },

    _initPWA() {
        // Service Worker 注册
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.register('/sw.js?v=13', { scope: '/' }).then((reg) => {
                // 强制检查 SW 更新
                reg.update();
                reg.addEventListener('updatefound', () => {
                    const newWorker = reg.installing;
                    newWorker.addEventListener('statechange', () => {
                        if (newWorker.state === 'activated') {
                            location.reload();
                        }
                    });
                });
            }).catch(() => {});
        }

        // 安装提示
        window.addEventListener('beforeinstallprompt', (e) => {
            e.preventDefault();
            this._pwaInstallEvent = e;
            this._showInstallBanner();
        });
    },

    _showInstallBanner() {
        if (localStorage.getItem('pwa_install_dismissed')) return;
        const banner = document.createElement('div');
        banner.id = 'pwa-install-banner';
        banner.style.cssText = 'position:fixed;bottom:60px;left:50%;transform:translateX(-50%);z-index:9999;background:var(--bg-secondary);border:1px solid var(--border-color);border-radius:12px;padding:12px 16px;box-shadow:0 4px 16px rgba(0,0,0,0.3);display:flex;align-items:center;gap:12px;font-size:13px;max-width:90vw';
        banner.innerHTML = `
            <span>安装到桌面，获得更好体验</span>
            <button class="btn btn-sm btn-primary" id="pwa-install-btn">安装</button>
            <button class="btn btn-sm" id="pwa-dismiss-btn" style="opacity:0.6">×</button>
        `;
        document.body.appendChild(banner);
        document.getElementById('pwa-install-btn').onclick = async () => {
            if (this._pwaInstallEvent) {
                this._pwaInstallEvent.prompt();
                const result = await this._pwaInstallEvent.userChoice;
                if (result.outcome === 'accepted') this.toast('已安装到桌面', 'success');
                this._pwaInstallEvent = null;
            }
            banner.remove();
        };
        document.getElementById('pwa-dismiss-btn').onclick = () => {
            localStorage.setItem('pwa_install_dismissed', '1');
            banner.remove();
        };
    },

    _initTableSorting() {
        document.querySelectorAll('table.sortable').forEach(t => Utils.initTableSort(t));
    },

    _ensureUserShell() {
        let root = document.getElementById('user-shell-root');
        if (!root) {
            root = document.createElement('div');
            root.id = 'user-shell-root';
            document.body.appendChild(root);
        }
        return root;
    },

    async _loadAccountState() {
        try {
            const data = await this.fetchJSON('/api/account/me', { silent: true });
            this._accountState = data && data.authenticated ? data : null;
            this._renderUserShell();
            if (this._accountState) {
                this._setAuthGate(false);
            }
            return this._accountState;
        } catch {
            this._accountState = null;
            this._renderUserShell();
            return null;
        }
    },

    _setAuthGate(required, { reason = '' } = {}) {
        globalThis.__AUTH_GATE_REQUIRED__ = required;
        document.documentElement.classList.toggle('auth-required', required);
        document.body.classList.toggle('auth-required', required);
        this._authRequired = required;

        if (required) {
            this._pauseAuthenticatedSession?.();
            if (reason) {
                this._authGateReason = reason;
            }
            this._openAuthModal({ required: true, reason });
        } else {
            this._authGateReason = '';
            this._closeAuthModal();
            this._renderUserShell?.();
        }
    },

    _closeAuthModal() {
        document.getElementById('auth-modal')?.remove();
    },

    _handleUnauthorized(detail = '') {
        if (this._authRequired) {
            return;
        }
        this._accountState = null;
        this._renderUserShell();
        this._setAuthGate(true, { reason: detail || '登录已失效，请重新登录' });
        this.toast(detail || '登录已失效，请重新登录', 'warning');
    },

    _handleAuthenticated(data) {
        this._accountState = data && data.authenticated ? data : null;
        this._renderUserShell();
        this._setAuthGate(false);
        this._startAuthenticatedApp?.();
    },

    _validateRegisterPayload(payload) {
        const username = (payload?.username || '').trim();
        const password = payload?.password || '';
        const inviteCode = (payload?.invite_code || '').trim();
        const email = (payload?.email || '').trim();

        if (username.length < 3) return '用户名至少需要 3 个字符';
        if (!/^[A-Za-z0-9_.-]{3,32}$/.test(username)) return '用户名只能包含字母、数字、下划线、点和横线';
        if (password.length < 8) return '密码至少需要 8 位';
        if (inviteCode.length !== 6) return '邀请码必须是 6 位';
        if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return '邮箱格式不正确';
        return '';
    },

    _renderUserShell() {
            const root = this._ensureUserShell();
            const state = this._accountState;
            const user = state?.user || null;
            const workspace = state?.workspace || null;
            const initial = user?.display_name ? user.display_name.slice(0, 1).toUpperCase() : 'L';
            const isAuthRequired = document.body.classList.contains('auth-required');
            root.innerHTML = `
            <div class="user-shell-bar">
                <div class="user-shell-status">
                    <span class="user-shell-dot ${user ? 'online' : 'offline'}"></span>
                    <span>${user ? this.escapeHTML(user.display_name || user.username) : '未登录'}</span>
                </div>
                <button class="user-shell-avatar" id="user-shell-avatar" aria-haspopup="menu" aria-expanded="false" title="账户菜单" ${isAuthRequired ? 'disabled' : ''} style="${user ? `background:${user.avatar_color || 'var(--primary-color)'};` : ''}">
                    ${user ? this.escapeHTML(initial) : '登'}
                </button>
            </div>
            <div class="user-menu hidden" id="user-menu" role="menu" aria-hidden="true">
                ${user ? `
                    <div class="user-menu-head">
                        <div class="user-menu-name">${this.escapeHTML(user.display_name || user.username)}</div>
                        <div class="user-menu-sub">${this.escapeHTML(workspace?.name || '龙虾工作区')}</div>
                    </div>
                    <button class="user-menu-item" data-user-action="open-profile">个人资料</button>
                    <button class="user-menu-item" data-user-action="open-workspace">我的工作区</button>
                    <button class="user-menu-item" data-user-action="open-openclaw-settings">OpenClaw 设置</button>
                    <button class="user-menu-item" data-user-action="open-skills">Skill 管理</button>
                    <button class="user-menu-item" data-user-action="open-permissions">权限设置</button>
                    <button class="user-menu-item" data-user-action="open-audit">审计日志</button>
                    <button class="user-menu-item" data-user-action="open-reports">日报 / 复盘</button>
                    <button class="user-menu-item" data-user-action="open-security">API Key / 安全</button>
                    <button class="user-menu-item" data-user-action="open-login">切换账号</button>
                    <button class="user-menu-item danger" data-user-action="logout">退出登录</button>
                ` : `
                    <button class="user-menu-item" data-user-action="open-login">登录 / 注册</button>
                `}
            </div>
        `;

        const avatar = root.querySelector('#user-shell-avatar');
        const menu = root.querySelector('#user-menu');
        avatar?.addEventListener('click', (e) => {
            if (avatar.disabled) return;
            e.preventDefault();
            menu?.classList.toggle('hidden');
            avatar.setAttribute('aria-expanded', menu?.classList.contains('hidden') ? 'false' : 'true');
        });

        root.querySelectorAll('[data-user-action]').forEach((btn) => {
            btn.addEventListener('click', async () => {
                const action = btn.dataset.userAction;
                menu?.classList.add('hidden');
                avatar?.setAttribute('aria-expanded', 'false');
                if (action === 'open-login') return this._openAuthModal();
                if (action === 'logout') return this._logout();
                if (action === 'open-profile') return this._openOpenClawSettingsPage('profile');
                if (action === 'open-openclaw-settings') return this._openOpenClawSettingsPage();
                if (action === 'open-workspace') return this._openWorkspacePanel();
                if (action === 'open-skills') return this._openOpenClawSettingsPage('skills');
                if (action === 'open-permissions') return this._openOpenClawSettingsPage('permissions');
                if (action === 'open-audit') return this._openOpenClawSettingsPage('audit');
                if (action === 'open-reports') return this._openOpenClawSettingsPage('reports');
                if (action === 'open-security') return this._openOpenClawSettingsPage('security');
            });
        });

        if (!this._userShellOutsideClickHandler) {
            this._userShellOutsideClickHandler = (e) => {
                const currentRoot = document.getElementById('user-shell-root');
                if (!currentRoot) return;
                const menuEl = currentRoot.querySelector('#user-menu');
                const avatarEl = currentRoot.querySelector('#user-shell-avatar');
                if (currentRoot.contains(e.target)) return;
                menuEl?.classList.add('hidden');
                avatarEl?.setAttribute('aria-expanded', 'false');
            };
            document.addEventListener('click', this._userShellOutsideClickHandler);
        }
    },

    async _logout() {
        try {
            await this.fetchJSON('/api/account/logout', { method: 'POST' });
        } catch {}
            this._pauseAuthenticatedSession?.();
            this._accountState = null;
            this._renderUserShell();
            this._setAuthGate(true, { reason: '请先登录' });
            this.toast('已退出登录', 'info');
            this._openAuthModal({ required: true });
        },

    _openAuthModal({ required = false } = {}) {
        if (document.getElementById('auth-modal')) return;
        const overlay = document.createElement('div');
        overlay.id = 'auth-modal';
        overlay.className = 'modal-overlay';
        if (required) {
            overlay.dataset.required = 'true';
        }
        overlay.innerHTML = `
            <div class="modal auth-modal">
                <h2>登录 / 注册</h2>
                <div class="sub-tabs" style="margin-bottom:12px">
                    <button class="sub-tab active" data-auth-tab="login">登录</button>
                    <button class="sub-tab" data-auth-tab="register">注册</button>
                </div>
                <div class="auth-panels">
                    <form id="auth-login-form" class="auth-panel active">
                        <div class="form-group"><label>用户名</label><input id="auth-login-username" required></div>
                        <div class="form-group"><label>密码</label><input id="auth-login-password" type="password" required></div>
                        <div class="modal-actions"><button type="button" class="btn btn-ghost" data-auth-close ${required ? 'hidden' : ''}>取消</button><button class="btn btn-primary" type="submit">登录</button></div>
                    </form>
                    <form id="auth-register-form" class="auth-panel">
                        <div class="form-group"><label>用户名</label><input id="auth-register-username" required></div>
                        <div class="form-group"><label>密码</label><input id="auth-register-password" type="password" required></div>
                        <div class="form-group"><label>邀请码（6 位）</label><input id="auth-register-invite" maxlength="6" required></div>
                        <div class="form-group"><label>昵称</label><input id="auth-register-display" placeholder="可选"></div>
                        <div class="form-group"><label>邮箱</label><input id="auth-register-email" type="email" placeholder="可选"></div>
                        <div class="modal-actions"><button type="button" class="btn btn-ghost" data-auth-close ${required ? 'hidden' : ''}>取消</button><button class="btn btn-primary" type="submit">注册</button></div>
                    </form>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);

        overlay.querySelectorAll('[data-auth-tab]').forEach((tab) => {
            tab.addEventListener('click', () => {
                overlay.querySelectorAll('[data-auth-tab]').forEach((t) => t.classList.remove('active'));
                overlay.querySelectorAll('.auth-panel').forEach((p) => p.classList.remove('active'));
                tab.classList.add('active');
                overlay.querySelector(`#auth-${tab.dataset.authTab}-form`)?.classList.add('active');
            });
        });

        overlay.querySelectorAll('[data-auth-close]').forEach((btn) => btn.addEventListener('click', () => {
            if (required) return;
            overlay.remove();
        }));

        overlay.addEventListener('click', (e) => {
            if (!required && e.target === overlay) {
                overlay.remove();
            }
        });

        overlay.querySelector('#auth-login-form')?.addEventListener('submit', async (e) => {
            e.preventDefault();
            const username = overlay.querySelector('#auth-login-username').value.trim();
            const password = overlay.querySelector('#auth-login-password').value;
            this._authFlowActive = true;
            try {
                const data = await this.fetchJSON('/api/account/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password }),
                });
                this._handleAuthenticated(data);
                this.toast('登录成功', 'success');
            } finally {
                this._authFlowActive = false;
            }
        });

        overlay.querySelector('#auth-register-form')?.addEventListener('submit', async (e) => {
            e.preventDefault();
            const payload = {
                username: overlay.querySelector('#auth-register-username').value.trim(),
                password: overlay.querySelector('#auth-register-password').value,
                invite_code: overlay.querySelector('#auth-register-invite').value.trim(),
                display_name: overlay.querySelector('#auth-register-display').value.trim(),
                email: overlay.querySelector('#auth-register-email').value.trim(),
            };
            const validationMessage = this._validateRegisterPayload(payload);
            if (validationMessage) {
                this.toast(validationMessage, 'error');
                return;
            }
            this._authFlowActive = true;
            try {
                const data = await this.fetchJSON('/api/account/register', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                this._handleAuthenticated(data);
                this.toast('注册成功', 'success');
            } catch {
                // fetchJSON already shows a user-facing message.
            } finally {
                this._authFlowActive = false;
            }
        });
    },

    async _openWorkspacePanel() {
        await this.switchTab('openclaw');
    },

    async _openOpenClawSettingsPage(section = '') {
        this._openclawSettingsSection = section || '';
        await this.switchTab('openclaw-settings');
    },

    _initGlobalShortcuts() {
        const tabs = ['overview', 'intelligence', 'research', 'openclaw', 'openclaw-settings', 'trade', 'paper', 'stock'];
        document.addEventListener('keydown', (e) => {
            const tag = e.target.tagName;
            const isInput = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || e.target.isContentEditable;

            // Escape: 关闭弹窗/overlay/帮助/LLM面板
            if (e.key === 'Escape') {
                const help = document.getElementById('shortcuts-help');
                if (help && help.style.display !== 'none') { help.style.display = 'none'; e.preventDefault(); return; }
                const overlay = document.querySelector('.overlay.active, .modal.active, .drawer.open');
                if (overlay) { overlay.classList.remove('active', 'open'); e.preventDefault(); return; }
                const llmPanel = document.getElementById('llm-panel');
                if (llmPanel && llmPanel.classList.contains('open')) { llmPanel.classList.remove('open'); e.preventDefault(); return; }
            }

            // 以下快捷键在输入框中不生效
            if (isInput) return;

            // Ctrl+K / Cmd+K: 聚焦搜索框
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                const searchInput = document.getElementById('stock-detail-code') || document.querySelector('.search-input');
                if (searchInput) { searchInput.focus(); searchInput.select(); }
                return;
            }

            // /: 聚焦搜索框（无修饰键）
            if (e.key === '/') {
                e.preventDefault();
                const searchInput = document.getElementById('stock-detail-code') || document.querySelector('.search-input');
                if (searchInput) { searchInput.focus(); searchInput.select(); }
                return;
            }

            // Ctrl+1 ~ Ctrl+8: 切换 tab
            if ((e.ctrlKey || e.metaKey) && e.key >= '1' && e.key <= '8') {
                e.preventDefault();
                const idx = parseInt(e.key) - 1;
                if (idx < tabs.length) this.switchTab(tabs[idx]);
                return;
            }

            // Ctrl+0: 切换到总览
            if ((e.ctrlKey || e.metaKey) && e.key === '0') {
                e.preventDefault();
                this.switchTab('overview');
                return;
            }

            // r: 刷新当前 tab 数据
            if (e.key === 'r' && !e.ctrlKey && !e.metaKey) {
                e.preventDefault();
                const activeTab = document.querySelector('.nav-link.active')?.dataset.tab;
                if (activeTab === 'overview') {
                    void this.ensureBundle?.('overview').then(() => this.loadOverview());
                } else if (activeTab === 'paper') {
                    void this.ensureBundle?.('paper').then(() => globalThis.PaperTrading?.refreshAll?.());
                } else if (activeTab === 'trade') {
                    void this.ensureBundle?.('trade').then(() => this.loadTradeTab?.());
                }
                return;
            }

            // ?: 显示快捷键帮助
            if (e.key === '?' || (e.shiftKey && e.key === '/')) {
                e.preventDefault();
                this._toggleShortcutsHelp();
                return;
            }

            // Alt+H: 隐私模式
            if (e.altKey && e.key === 'h') {
                e.preventDefault();
                this.togglePrivacy();
                return;
            }
        });
    },

    _initCommandPalette() {
        if (globalThis.ENABLE_WORKSPACE_V2 === false) {
            return;
        }

        const palette = globalThis.CommandPalette;
        const root = document.getElementById('cmd-palette');
        const input = document.getElementById('cmd-palette-input');
        const list = document.getElementById('cmd-palette-list');

        if (!palette || typeof palette.mount !== 'function' || !root || !input || !list) {
            return;
        }

        palette.mount({ root, input, list });
        palette.attachKeyboardShortcuts({ target: document });
        palette.subscribe((state) => {
            root.hidden = state.isOpen !== true;
            root.classList.toggle('hidden', state.isOpen !== true);
            root.setAttribute('aria-hidden', state.isOpen === true ? 'false' : 'true');
            input.setAttribute('aria-expanded', state.isOpen === true ? 'true' : 'false');

            if (state.isLoading) {
                list.innerHTML = '<div class="cmd-palette-item"><span class="cmd-palette-label">搜索中...</span></div>';
                return;
            }

            if (state.error) {
                const message = typeof state.error.message === 'string' && state.error.message.trim()
                    ? state.error.message.trim()
                    : '命令面板加载失败';
                list.innerHTML = `<div class="cmd-palette-item"><span class="cmd-palette-label">${this.escapeHTML(message)}</span></div>`;
                return;
            }

            if (!Array.isArray(state.mergedResults) || state.mergedResults.length === 0) {
                list.innerHTML = '<div class="cmd-palette-item"><span class="cmd-palette-label">暂无可执行结果</span></div>';
                return;
            }

            list.innerHTML = state.mergedResults.map((item, index) => {
                const isActive = index === state.selectedIndex;
                const isDisabled = item.kind === 'action' && item.enabled !== true;
                const title = item.kind === 'stock'
                    ? `${item.code} ${item.name || ''}`.trim()
                    : (item.title || item.id || '未命名动作');
                const description = item.kind === 'stock'
                    ? (item.market || item.exchange || '股票')
                    : (item.description || item.category || '动作');
                const icon = item.kind === 'stock' ? '📈' : '⚡';
                const metaLabel = isDisabled ? '不可执行' : description;
                return `
                    <div class="cmd-palette-item ${isActive ? 'active' : ''} ${isDisabled ? 'is-disabled' : ''}" data-command-palette-index="${index}" role="option" aria-selected="${isActive ? 'true' : 'false'}" aria-disabled="${isDisabled ? 'true' : 'false'}">
                        <span class="cmd-palette-icon">${icon}</span>
                        <span class="cmd-palette-label">${this.escapeHTML(title)}</span>
                        <span class="cmd-palette-desc">${this.escapeHTML(metaLabel)}</span>
                    </div>
                `;
            }).join('');
        });
    },

    _toggleShortcutsHelp() {
        let el = document.getElementById('shortcuts-help');
        if (!el) {
            el = document.createElement('div');
            el.id = 'shortcuts-help';
            el.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);z-index:9999;background:var(--bg-secondary);border:1px solid var(--border-color);border-radius:12px;padding:24px;box-shadow:0 8px 32px rgba(0,0,0,0.3);max-width:400px;width:90%';
            el.innerHTML = `
                <h3 style="margin:0 0 16px;font-size:16px">键盘快捷键</h3>
                <div style="display:grid;grid-template-columns:auto 1fr;gap:8px 16px;font-size:13px">
                    <kbd>/</kbd><span>聚焦搜索框</span>
                    <kbd>Ctrl+K</kbd><span>聚焦搜索框</span>
                    <kbd>Ctrl+0~8</kbd><span>切换页面</span>
                    <kbd>r</kbd><span>刷新当前页</span>
                    <kbd>Alt+P</kbd><span>命令面板</span>
                    <kbd>?</kbd><span>显示/隐藏帮助</span>
                    <kbd>Esc</kbd><span>关闭弹窗/帮助</span>
                </div>
            `;
            document.body.appendChild(el);
        } else {
            el.style.display = el.style.display === 'none' ? '' : 'none';
        }
    },

    /** Command Palette (Alt+P) */
    _toggleCommandPalette() {
        const palette = globalThis.CommandPalette;
        if (palette && typeof palette.toggle === 'function') {
            void palette.toggle({
                source: 'app:shortcut',
                mode: 'mixed',
            });
            return;
        }

        let el = document.getElementById('cmd-palette');
        if (el) {
            el.classList.toggle('hidden');
            if (!el.classList.contains('hidden')) {
                el.querySelector('input')?.focus();
            }
            return;
        }

        // 首次创建
        el = document.createElement('div');
        el.id = 'cmd-palette';
        el.className = 'cmd-palette-overlay';
        el.innerHTML = `
            <div class="cmd-palette">
                <input type="text" class="cmd-palette-input" placeholder="输入命令或搜索..." autocomplete="off" aria-label="命令面板">
                <div class="cmd-palette-list" id="cmd-palette-list"></div>
                <div class="cmd-palette-footer">
                    <span><kbd>↑↓</kbd> 导航</span>
                    <span><kbd>Enter</kbd> 执行</span>
                    <span><kbd>Esc</kbd> 关闭</span>
                </div>
            </div>
        `;
        document.body.appendChild(el);

        const input = el.querySelector('input');
        const list = document.getElementById('cmd-palette-list');

        const commands = [
            { label: '监控', desc: '切换到监控页', icon: '📊', action: () => this.switchTab('overview') },
            { label: '情报', desc: '切换到情报页', icon: '📰', action: () => this.switchTab('intelligence') },
            { label: '研发', desc: '切换到研发页', icon: '🔬', action: () => this.switchTab('research') },
            { label: '龙虾', desc: '切换到龙虾工作台', icon: '🦞', action: () => this.switchTab('openclaw') },
            { label: '龙虾设置', desc: '切换到龙虾设置页', icon: '⚙️', action: () => this.switchTab('openclaw-settings') },
            { label: '交易', desc: '切换到交易页', icon: '💹', action: () => this.switchTab('trade') },
            { label: '模拟盘', desc: '切换到模拟盘', icon: '🎮', action: () => this.switchTab('paper') },
            { label: '刷新', desc: '刷新当前页数据', icon: '🔄', action: () => {
                const t = document.querySelector('.nav-link.active')?.dataset.tab;
                if (t === 'overview') void this.ensureBundle?.('overview').then(() => this.loadOverview());
            } },
            { label: '搜索', desc: '聚焦搜索框', icon: '🔍', action: () => { document.getElementById('stock-detail-code')?.focus(); } },
            { label: '帮助', desc: '显示快捷键帮助', icon: '❓', action: () => this._toggleShortcutsHelp() },
            { label: '主题', desc: '切换深色/浅色主题', icon: '🎨', action: () => { const t = document.documentElement.getAttribute('data-theme'); document.documentElement.setAttribute('data-theme', t === 'dark' ? 'light' : 'dark'); } },
            { label: '隐私', desc: '切换隐私模式 (Alt+H)', icon: '🙈', action: () => this.togglePrivacy() },
            { label: '导出', desc: 'Emergency Data Dump', icon: '💾', action: () => this.dumpAll() },
        ];

        let selectedIndex = 0;

        const render = (filter = '') => {
            const f = filter.toLowerCase();
            const filtered = f ? commands.filter(c => c.label.toLowerCase().includes(f) || c.desc.toLowerCase().includes(f)) : commands;
            selectedIndex = 0;
            list.innerHTML = filtered.map((c, i) => `
                <div class="cmd-palette-item ${i === 0 ? 'active' : ''}" data-index="${i}">
                    <span class="cmd-palette-icon">${c.icon}</span>
                    <span class="cmd-palette-label">${c.label}</span>
                    <span class="cmd-palette-desc">${c.desc}</span>
                </div>
            `).join('');
            return filtered;
        };

        let filtered = render();

        input.addEventListener('input', () => { filtered = render(input.value); });

        input.addEventListener('keydown', (e) => {
            const items = list.querySelectorAll('.cmd-palette-item');
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                selectedIndex = Math.min(selectedIndex + 1, items.length - 1);
                items.forEach((it, i) => it.classList.toggle('active', i === selectedIndex));
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                selectedIndex = Math.max(selectedIndex - 1, 0);
                items.forEach((it, i) => it.classList.toggle('active', i === selectedIndex));
            } else if (e.key === 'Enter') {
                e.preventDefault();
                if (filtered[selectedIndex]) {
                    filtered[selectedIndex].action();
                    el.classList.add('hidden');
                    input.value = '';
                }
            } else if (e.key === 'Escape') {
                el.classList.add('hidden');
                input.value = '';
            }
        });

        list.addEventListener('click', (e) => {
            const item = e.target.closest('.cmd-palette-item');
            if (item) {
                const idx = parseInt(item.dataset.index);
                if (filtered[idx]) {
                    filtered[idx].action();
                    el.classList.add('hidden');
                    input.value = '';
                }
            }
        });

        // 点击遮罩关闭
        el.addEventListener('click', (e) => {
            if (e.target === el) {
                el.classList.add('hidden');
                input.value = '';
            }
        });

        el.classList.remove('hidden');
        input.focus();
    },

});
