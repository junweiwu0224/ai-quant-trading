const fs = require('fs');
const path = require('path');
const { test, expect } = require('@playwright/test');

const PASSWORD = 'Playwright123!';
const INVITE_CODE = process.env.PLAYWRIGHT_INVITE_CODE || 'LOCAL1';
const REPORT_PATH = path.join(process.cwd(), 'test-results', 'data-display-audit', 'browser-report.json');
const HARD_BAD_TEXT = /(?:\b(?:NaN|undefined|Infinity)\b|\[object Object\]|\bInvalid Date\b)/gi;

const ROUTES = [
    { path: '/app/decision', heading: /把自选池变成可追溯决策/ },
    { path: '/app/intelligence', heading: /市场情报/ },
    { path: '/app/reports', heading: /报告/ },
    { path: '/app/research/CN/600519', heading: /600519/ },
    { path: '/app/validation', heading: /验证/ },
    { path: '/app/notifications', heading: /通知/ },
    { path: '/app/settings', heading: /工作区设置/ },
    { path: '/app/more', heading: /更多工具/ },
    { path: '/app/more/screener', heading: /条件筛选与 AI 选股/ },
    { path: '/app/more/portfolio-risk', heading: /持仓、绩效与风控/ },
    { path: '/app/more/paper', heading: /模拟盘与风控执行/ },
    { path: '/app/more/agents', heading: /AI 研究工作台/ },
    { path: '/app/more/conditional-orders', heading: /条件单/ },
    { path: '/app/more/alerts', heading: /告警规则/ },
    { path: '/app/more/strategies', heading: /策略工作台/ },
    { path: '/app/more/alpha-factors', heading: /Alpha/ },
    { path: '/app/more/formula-basket', heading: /公式系统与篮子计划/ },
    { path: '/app/more/broker-live', heading: /Broker 与实盘设置/ },
];

const MOBILE_ROUTES = [
    { path: '/app/decision', heading: /把自选池变成可追溯决策/ },
    { path: '/app/research/CN/600519', heading: /600519/ },
    { path: '/app/more', heading: /更多工具/ },
    { path: '/app/more/screener', heading: /条件筛选与 AI 选股/ },
    { path: '/app/more/agents', heading: /AI 研究工作台/ },
    { path: '/app/more/paper', heading: /模拟盘与风控执行/ },
];

function cookieDomain() {
    const baseUrl = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8001';
    return new URL(baseUrl).hostname || '127.0.0.1';
}

async function authenticate(page, suffix) {
    const username = `vue_health_${suffix}_${Date.now()}`
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

async function waitForShell(page) {
    await expect(page.locator('.app-shell')).toBeVisible();
    await expect(page.locator('nav[aria-label="主导航"]')).toBeAttached();
    await expect(page.locator('h1')).toBeVisible();
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

async function auditRoute(page, route) {
    const response = await page.goto(route.path, { waitUntil: 'domcontentloaded' });
    await waitForShell(page);
    await expect(page.locator('h1')).toContainText(route.heading);
    await page.waitForTimeout(150);
    const text = await page.locator('body').innerText();
    HARD_BAD_TEXT.lastIndex = 0;
    const hardMatches = [...new Set(text.match(HARD_BAD_TEXT) || [])];
    await assertNoHorizontalOverflow(page);
    return {
        path: route.path,
        url: page.url(),
        status: response ? response.status() : null,
        heading: await page.locator('h1').innerText(),
        hardMatches,
    };
}

function writeReport(report) {
    fs.mkdirSync(path.dirname(REPORT_PATH), { recursive: true });
    fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2), 'utf8');
}

test('Vue desktop route matrix renders without bad values or browser errors', async ({ page }) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width: 1440, height: 900 });
    const report = {
        generatedAt: new Date().toISOString(),
        baseUrl: process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8001',
        routes: [],
        consoleErrors: [],
        pageErrors: [],
        failedRequests: [],
        runError: null,
    };
    page.on('console', (message) => {
        if (message.type() === 'warning' && message.text() === 'Service Worker registration blocked by Playwright') return;
        if (['error', 'warning'].includes(message.type())) report.consoleErrors.push({ type: message.type(), text: message.text() });
    });
    page.on('pageerror', (error) => report.pageErrors.push({ message: error.message, stack: error.stack || '' }));
    page.on('requestfailed', (request) => {
        const failure = request.failure()?.errorText || '';
        // Route-matrix navigation intentionally cancels requests from the
        // previous view; these are not product failures.
        if (failure === 'net::ERR_ABORTED') return;
        report.failedRequests.push({ url: request.url(), method: request.method(), failure });
    });

    try {
        await authenticate(page, 'desktop');
        for (const route of ROUTES) report.routes.push(await auditRoute(page, route));

        await page.goto('/app/more/agents', { waitUntil: 'domcontentloaded' });
        await waitForShell(page);
        await expect(page.locator('body')).toContainText('不会修改确定性决策');
        await page.goto('/app/more/paper', { waitUntil: 'domcontentloaded' });
        await waitForShell(page);
        await expect(page.locator('body')).toContainText('不会调用 Broker 或真实下单接口');
        await page.goto('/app/more/broker-live', { waitUntil: 'domcontentloaded' });
        await waitForShell(page);
        await expect(page.locator('body')).toContainText(/禁止真实下单|显式禁用/);
    } catch (error) {
        report.runError = { message: error.message, stack: error.stack || '' };
    } finally {
        writeReport(report);
    }

    expect(report.runError, JSON.stringify(report, null, 2)).toBeNull();
    expect(report.routes, JSON.stringify(report, null, 2)).toHaveLength(ROUTES.length);
    expect(report.routes.every((route) => route.status === 200), JSON.stringify(report, null, 2)).toBeTruthy();
    expect(report.routes.flatMap((route) => route.hardMatches), JSON.stringify(report, null, 2)).toEqual([]);
    expect(report.consoleErrors, JSON.stringify(report, null, 2)).toEqual([]);
    expect(report.pageErrors, JSON.stringify(report, null, 2)).toEqual([]);
});

test('Vue mobile navigation and responsive tool routes stay within 390px', async ({ page }) => {
    test.setTimeout(90_000);
    await page.setViewportSize({ width: 390, height: 844 });
    await authenticate(page, 'mobile');
    await page.goto('/app/decision', { waitUntil: 'domcontentloaded' });
    await waitForShell(page);
    await expect(page.locator('nav[aria-label="移动导航"]')).toBeVisible();
    await expect(page.getByRole('button', { name: '打开导航' })).toBeVisible();

    for (const route of MOBILE_ROUTES) {
        await auditRoute(page, route);
        await expect(page.locator('nav[aria-label="移动导航"]')).toBeVisible();
    }
});
