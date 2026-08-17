const { test, expect } = require('@playwright/test');

const PASSWORD = 'Playwright123!';
const INVITE_CODE = process.env.PLAYWRIGHT_INVITE_CODE || 'LOCAL1';

function cookieDomain() {
    const baseUrl = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8001';
    return new URL(baseUrl).hostname || '127.0.0.1';
}

async function authenticate(page, suffix) {
    const username = `vue_${suffix}_${Date.now()}`
        .replace(/[^A-Za-z0-9_.-]/g, '')
        .slice(0, 32);
    const response = await page.request.post('/api/account/register', {
        data: {
            username,
            password: PASSWORD,
            invite_code: INVITE_CODE,
            display_name: username,
            email: null,
        },
    });
    let authResponse = response;
    if (!response.ok()) {
        authResponse = await page.request.post('/api/account/login', {
            data: { username: 'pw_shell', password: PASSWORD },
        });
    }
    expect(authResponse.ok()).toBeTruthy();
    const cookie = (authResponse.headers()['set-cookie'] || '').match(/quant_session=([^;]+)/)?.[1];
    expect(cookie).toBeTruthy();
    await page.context().addCookies([{
        name: 'quant_session',
        value: cookie,
        domain: cookieDomain(),
        path: '/',
        httpOnly: true,
        sameSite: 'Lax',
    }]);
}

async function assertNoHorizontalOverflow(page) {
    const dimensions = await page.evaluate(() => ({
        viewport: document.documentElement.clientWidth,
        scrollWidth: document.documentElement.scrollWidth,
        bodyScrollWidth: document.body.scrollWidth,
    }));
    expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.viewport + 1);
    expect(dimensions.bodyScrollWidth).toBeLessThanOrEqual(dimensions.viewport + 1);
}

async function waitForShell(page) {
    await expect(page.locator('.app-shell')).toBeVisible();
    await expect(page.locator('nav[aria-label="主导航"]')).toBeAttached();
}

test('Vue desktop workflow covers decision, validation, research, and legacy context', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await authenticate(page, 'desktop');

    await page.goto('/app/decision', { waitUntil: 'domcontentloaded' });
    await waitForShell(page);
    await expect(page.locator('h1')).toContainText('把自选池变成可追溯决策');
    await expect(page.getByRole('link', { name: '验证' }).first()).toBeVisible();
    const palette = page.getByRole('dialog', { name: '去哪里继续研究？' });
    await page.getByRole('button', { name: /打开快捷导航/ }).click();
    await expect(palette).toBeVisible();
    await palette.getByLabel('搜索工作流').fill('Agent');
    await expect(palette.getByRole('option', { name: /AI 研究工作台/ })).toBeVisible();
    await palette.getByRole('option', { name: /AI 研究工作台/ }).click();
    await expect(page).toHaveURL(/\/app\/more\/agents$/);
    await page.goto('/app/decision', { waitUntil: 'domcontentloaded' });
    await waitForShell(page);
    await page.keyboard.press('Control+k');
    await expect(palette).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(palette).not.toBeVisible();
    await assertNoHorizontalOverflow(page);

    await page.getByRole('link', { name: '验证' }).first().click();
    await expect(page).toHaveURL(/\/app\/validation$/);
    await expect(page.locator('h1')).toContainText('验证');
    await expect(page.getByRole('button', { name: /运行|验证|刷新/ }).first()).toBeVisible();
    await assertNoHorizontalOverflow(page);

    await page.goto('/app/research/US/AAPL?source=e2e', { waitUntil: 'domcontentloaded' });
    await waitForShell(page);
    await expect(page.locator('h1')).toContainText('AAPL');
    await expect(page.locator('body')).toContainText(/仅保留受控研究入口|研究能力未确认|来源/);
    await assertNoHorizontalOverflow(page);

    await page.goto('/?code=600519&market=US', { waitUntil: 'domcontentloaded' });
    await waitForShell(page);
    await expect(page).toHaveURL(/\/app\/research\/US\/600519\?code=600519&market=US&source=legacy-hash$/);
    await expect(page.locator('h1')).toContainText('600519');
    await assertNoHorizontalOverflow(page);

    await page.goto('/app/decision?code=600519&market=US', { waitUntil: 'domcontentloaded' });
    await expect(page).toHaveURL(/\/app\/research\/US\/600519\?code=600519&market=US&source=legacy-hash$/);

    await page.goto('/app/decision#alpha?code=600519&market=US', { waitUntil: 'domcontentloaded' });
    await expect(page).toHaveURL(/\/app\/more\/alpha-factors\?code=600519&market=US&source=legacy-hash$/);

    await page.goto('/app/more', { waitUntil: 'domcontentloaded' });
    await waitForShell(page);
    await expect(page.locator('h1')).toContainText('更多工具');
    const conditionalOrders = page.locator('.tool-card').filter({ hasText: '条件单' });
    await conditionalOrders.getByRole('link', { name: /打开 Vue 工作流/ }).click();
    await expect(page).toHaveURL(/\/app\/more\/conditional-orders$/);
    await expect(page.locator('h1')).toContainText('条件单');
    await assertNoHorizontalOverflow(page);
});

test('Vue mobile workflow exposes navigation and remains within 390px', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await authenticate(page, 'mobile');

    await page.goto('/app/decision', { waitUntil: 'domcontentloaded' });
    await waitForShell(page);
    await expect(page.locator('nav[aria-label="移动导航"]')).toBeVisible();
    await page.getByRole('button', { name: /打开快捷导航/ }).click();
    await expect(page.getByRole('dialog', { name: '去哪里继续研究？' })).toBeVisible();
    await page.keyboard.press('Escape');
    await assertNoHorizontalOverflow(page);

    await page.getByRole('button', { name: '打开导航' }).click();
    await expect(page.locator('.sidebar.open')).toBeVisible();
    await page.locator('.sidebar.open').getByRole('link', { name: '单股研究' }).click();
    await expect(page).toHaveURL(/\/app\/research\/CN\/600519/);
    await expect(page.locator('h1')).toContainText('600519');
    await assertNoHorizontalOverflow(page);

    await page.getByRole('link', { name: '决策中心' }).last().click();
    await expect(page).toHaveURL(/\/app\/decision$/);
    await expect(page.locator('h1')).toContainText('把自选池变成可追溯决策');
    await assertNoHorizontalOverflow(page);

    await page.locator('nav[aria-label="移动导航"]').getByRole('link', { name: '更多', exact: true }).click();
    await expect(page).toHaveURL(/\/app\/more$/);
    await expect(page.locator('h1')).toContainText('更多工具');
    await assertNoHorizontalOverflow(page);

    const screener = page.locator('.tool-card').filter({ hasText: '条件筛选与 AI 选股' });
    await screener.getByRole('link', { name: /打开 Vue 工作流/ }).click();
    await expect(page).toHaveURL(/\/app\/more\/screener$/);
    await expect(page.locator('h1')).toContainText('条件筛选与 AI 选股');
    await assertNoHorizontalOverflow(page);
});
