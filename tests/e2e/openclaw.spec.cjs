const { test, expect } = require('@playwright/test');

const TEST_INVITE_CODE = process.env.PLAYWRIGHT_INVITE_CODE || 'LOCAL1';
const TEST_PASSWORD = 'Playwright123!';

async function waitForAppReady(page) {
    await expect(page.locator('body')).toBeVisible();
    await expect(page.locator('#stock-offcanvas')).toBeAttached();
    await page.waitForFunction(() => {
        return Boolean(
            window.App
            && window.IntentBus
            && window.GlobalStockStore
            && window.ActionRegistry
            && window.LocalMCP
            && window.BusinessAdapter
            && window.CommandPalette
            && window.RightRailController
            && window.PanelLifecycle
        );
    });
}

async function ensureAuthenticated(page, usernameSuffix = Date.now()) {
    const username = `pw_${usernameSuffix}`.replace(/[^A-Za-z0-9_.-]/g, '').slice(0, 32);
    const payload = {
        username,
        password: TEST_PASSWORD,
        invite_code: TEST_INVITE_CODE,
        display_name: username,
        email: null,
    };
    const auth = await page.request.post('/api/account/register', { data: payload });
    const response = auth.ok()
        ? auth
        : await page.request.post('/api/account/login', { data: { username, password: TEST_PASSWORD } });
    expect(response.ok()).toBeTruthy();
    const sessionCookie = response.headers()['set-cookie'] || '';
    const cookieValue = sessionCookie.match(/quant_session=([^;]+)/)?.[1] || '';
    expect(cookieValue).toBeTruthy();
    await page.context().addCookies([{
        name: 'quant_session',
        value: cookieValue,
        domain: '127.0.0.1',
        path: '/',
        httpOnly: true,
        sameSite: 'Lax',
    }]);
    return username;
}

async function openAvatarMenu(page) {
    const setupModal = page.locator('#openclaw-setup-modal');
    if (await setupModal.isVisible().catch(() => false)) {
        await page.locator('[data-openclaw-setup-action="skip"]').click();
        await expect(setupModal).toBeHidden();
    }
    await page.locator('#user-shell-avatar').click();
    await expect(page.locator('#user-menu')).toBeVisible();
}

async function dismissSetupModal(page) {
    const setupModal = page.locator('#openclaw-setup-modal');
    if (await setupModal.isVisible().catch(() => false)) {
        await page.locator('[data-openclaw-setup-action="skip"]').click();
        await expect(setupModal).toBeHidden();
    }
}

async function openOpenClaw(page, usernameSuffix) {
    await ensureAuthenticated(page, usernameSuffix);
    await page.goto('/#openclaw', { waitUntil: 'domcontentloaded' });
    await waitForAppReady(page);
    await expect(page.locator('#tab-openclaw')).toBeVisible();
    await dismissSetupModal(page);
}

test('openclaw avatar menu exposes the workspace and settings surfaces', async ({ page }) => {
    await ensureAuthenticated(page, 'openclaw_ui');
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await waitForAppReady(page);

    await expect(page.locator('#nav-openclaw')).toBeVisible();
    await page.locator('#nav-openclaw').click();
    await expect(page.locator('#tab-openclaw')).toBeVisible();
    await expect(page.locator('#openclaw-workbench')).toBeAttached();
    await dismissSetupModal(page);

    await openAvatarMenu(page);
    await expect(page.locator('[data-user-action="open-profile"]')).toContainText('个人资料');
    await expect(page.locator('[data-user-action="open-workspace"]')).toContainText('我的工作区');
    await expect(page.locator('[data-user-action="open-openclaw-settings"]')).toContainText('OpenClaw 设置');
    await expect(page.locator('[data-user-action="open-skills"]')).toContainText('Skill 管理');
    await expect(page.locator('[data-user-action="open-permissions"]')).toContainText('权限设置');
    await expect(page.locator('[data-user-action="open-audit"]')).toContainText('审计日志');
    await expect(page.locator('[data-user-action="open-reports"]')).toContainText('日报 / 复盘');
    await expect(page.locator('[data-user-action="open-security"]')).toContainText('API Key / 安全');
    await expect(page.locator('[data-user-action="logout"]')).toContainText('退出登录');

    await page.locator('[data-user-action="open-profile"]').click();
    await expect(page.locator('#tab-openclaw-settings')).toBeVisible();
    await expect(page.locator('#openclaw-settings-workbench')).toBeAttached();
    await expect(page.locator('#openclaw-settings-profile')).toBeVisible();
    await expect(page.locator('#openclaw-settings-security')).toBeVisible();

    await openAvatarMenu(page);
    await page.locator('[data-user-action="open-workspace"]').click();
    await expect(page.locator('#tab-openclaw')).toBeVisible();
    await expect(page.locator('#openclaw-workbench')).toBeAttached();

    await openAvatarMenu(page);
    await page.locator('[data-user-action="open-skills"]').click();
    await expect(page.locator('#tab-openclaw-settings')).toBeVisible();
    await expect(page.locator('#openclaw-settings-skills')).toBeVisible();

    await openAvatarMenu(page);
    await page.locator('[data-user-action="open-permissions"]').click();
    await expect(page.locator('#openclaw-settings-permissions')).toBeVisible();

    await openAvatarMenu(page);
    await page.locator('[data-user-action="open-audit"]').click();
    await expect(page.locator('#openclaw-settings-audit')).toBeVisible();

    await openAvatarMenu(page);
    await page.locator('[data-user-action="open-reports"]').click();
    await expect(page.locator('#openclaw-settings-reports')).toBeVisible();

    await openAvatarMenu(page);
    await page.locator('[data-user-action="open-security"]').click();
    await expect(page.locator('#openclaw-settings-security')).toBeVisible();
});

test('OpenClaw starts collapsed and stop cancels a pending reply', async ({ page }) => {
    await openOpenClaw(page, 'rail_stop');

    await expect(page.locator('.openclaw-shell')).toHaveClass(/is-rail-collapsed/);
    await expect(page.locator('.openclaw-rail')).toBeVisible();
    await expect(page.locator('.openclaw-chat-shell')).not.toContainText('原生面板');
    await expect(page.locator('.openclaw-chat-shell')).not.toContainText('兜底模式');
    await expect(page.locator('.openclaw-chat-shell')).not.toContainText('服务日志');
    await expect(page.locator('[data-openclaw-action="stop"]')).toBeHidden();

    await page.locator('[data-openclaw-conv-action="toggle-rail"]').first().click();
    await expect(page.locator('.openclaw-shell')).toHaveClass(/is-rail-open/);

    await page.route('**/api/openclaw/chat', async (route) => {
        await new Promise((resolve) => setTimeout(resolve, 1500));
        await route.fulfill({
            json: { success: true, mode: 'native', content: 'long reply' },
        });
    });

    await page.locator('#openclaw-input').fill('帮我分析 600519');
    await page.locator('[data-openclaw-action="send"]').click();
    await expect(page.locator('[data-openclaw-action="stop"]')).toBeVisible();
    await page.locator('[data-openclaw-action="stop"]').click();

    await expect(page.locator('.openclaw-message.is-canceled')).toContainText('已停止');
});

test('OpenClaw rail can create, search, switch, and reload its own history', async ({ page }) => {
    await page.route('**/api/openclaw/chat', async (route) => {
        const body = route.request().postDataJSON();
        await route.fulfill({
            json: { success: true, mode: 'native', content: `回复：${body.message}` },
        });
    });

    await openOpenClaw(page, 'rail_history');

    await page.locator('[data-openclaw-conv-action="new-chat"]').first().click();
    await page.locator('#openclaw-input').fill('今天 600519 怎么样');
    await page.locator('[data-openclaw-action="send"]').click();
    await expect(page.locator('.openclaw-message.is-assistant')).toContainText('600519');

    await page.locator('[data-openclaw-conv-action="new-chat"]').first().click();
    await page.locator('#openclaw-input').fill('帮我看 000001');
    await page.locator('[data-openclaw-action="send"]').click();
    await expect(page.locator('.openclaw-message.is-assistant')).toContainText('000001');

    await page.locator('[data-openclaw-conv-action="toggle-rail"]').first().click();
    await page.locator('[data-openclaw-conv-action="search"]').fill('600519');
    await expect(page.locator('.openclaw-conversation-item').first()).toContainText('600519');

    await dismissSetupModal(page);
    await page.locator('.openclaw-conversation-item').first().click();
    await expect(page.locator('.openclaw-conversation-item.is-active')).toContainText('600519');
    await page.waitForTimeout(500);
    await expect(page.locator('.openclaw-conversation-item.is-active')).toContainText('600519');
    await expect(page.locator('.openclaw-message.is-user')).toContainText('600519');

    await page.reload({ waitUntil: 'domcontentloaded' });
    await waitForAppReady(page);
    await expect(page.locator('.openclaw-conversation-item.is-active')).toContainText('600519');
    await expect(page.locator('.openclaw-message.is-user')).toContainText('600519');
});

test('OpenClaw skill commands show a local hint and backend skill-command status', async ({ page }) => {
    await page.route('**/api/openclaw/chat', async (route) => {
        const body = route.request().postDataJSON();
        await route.fulfill({
            json: {
                success: true,
                mode: 'skill-command',
                content: `已处理：${body.message}`,
            },
        });
    });
    await page.route('**/api/openclaw/status', async (route) => {
        await route.fulfill({
            json: {
                success: true,
                status: {
                    workspace: { name: 'OpenClaw', openclaw_workspace_id: 'ocw_test' },
                    skill_command_history: [
                        { title: '/skill record', status: 'approved', created_at: '2026-05-24 10:00' },
                    ],
                },
            },
        });
    });
    await page.route('**/api/openclaw/skills', async (route) => {
        await route.fulfill({
            json: {
                success: true,
                items: [],
                history: [
                    { title: '/skill record', status: 'approved', created_at: '2026-05-24 10:00' },
                ],
            },
        });
    });
    await page.route('**/api/openclaw/setup', async (route) => {
        await route.fulfill({ json: { success: true, setup_completed: true } });
    });

    await openOpenClaw(page, 'skill_cmd');
    await page.locator('#openclaw-input').fill('/skill record openclaw');
    await expect(page.locator('#openclaw-composer-hint')).toContainText('技能命令');
    await page.locator('[data-openclaw-action="send"]').click();

    await expect(page.locator('.openclaw-message.is-assistant')).toContainText('已处理：/skill record openclaw');
    await expect(page.locator('.openclaw-message.is-assistant .openclaw-message-meta')).toContainText('skill-command');
    await expect(page.locator('.openclaw-message.is-assistant .openclaw-message-meta')).toContainText('技能命令');

    await page.locator('[data-openclaw-action="open-settings"]').click();
    await expect(page.locator('#openclaw-skill-command-history .openclaw-item').first()).toContainText('/skill record');
    await expect(page.locator('#openclaw-skill-command-history .openclaw-item').first()).toContainText('approved');
});
